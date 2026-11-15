"""Tests for the cached AMI entity-schema lookup."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pyAMI.exception
import pytest

from ami_mcp.tools._schema import (
    FieldInfo,
    SchemaCache,
    find_unknown_fields,
    parse_entity_fields,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock


@pytest.fixture
def schema_client(mock_ami_client: MagicMock, entity_info_result: Any) -> MagicMock:
    mock_ami_client.execute.return_value = entity_info_result
    return mock_ami_client


class TestParseEntityFields:
    def test_parses_name_type_and_description(self, entity_info_result: Any) -> None:
        fields = parse_entity_fields(entity_info_result)
        by_name = {f.name: f for f in fields}
        assert by_name["datasetNumber"] == FieldInfo(
            name="datasetNumber", type="INT", description="Dataset number (DSID)"
        )
        assert by_name["logicalDatasetName"].type == "VARCHAR(255)"

    def test_keeps_every_row_regardless_of_show_type(
        self, entity_info_result: Any
    ) -> None:
        # showType=0 fields (physicsCategory, jobConfig) are still queryable.
        names = {f.name for f in parse_entity_fields(entity_info_result)}
        assert {"physicsCategory", "jobConfig"} <= names


class TestSchemaCache:
    async def test_fetches_with_get_entity_info_command(
        self, mock_ctx: MagicMock, schema_client: MagicMock
    ) -> None:
        await SchemaCache().get(mock_ctx, "mc23_001:production", "dataset")
        command = schema_client.execute.call_args.args[0]
        assert command == 'AMIGetEntityInfo -catalog="mc23_001:production" -entity="dataset"'

    async def test_second_lookup_is_served_from_cache(
        self, mock_ctx: MagicMock, schema_client: MagicMock
    ) -> None:
        cache = SchemaCache()
        first = await cache.get(mock_ctx, "mc23_001:production", "dataset")
        second = await cache.get(mock_ctx, "mc23_001:production", "dataset")
        assert first == second
        assert schema_client.execute.call_count == 1

    async def test_cache_is_keyed_by_catalog_and_entity(
        self, mock_ctx: MagicMock, schema_client: MagicMock
    ) -> None:
        cache = SchemaCache()
        await cache.get(mock_ctx, "mc23_001:production", "dataset")
        await cache.get(mock_ctx, "mc20_001:production", "dataset")
        await cache.get(mock_ctx, "mc23_001:production", "files")
        assert schema_client.execute.call_count == 3

    async def test_entry_expires_after_ttl(
        self, mock_ctx: MagicMock, schema_client: MagicMock
    ) -> None:
        now = [1000.0]
        cache = SchemaCache(ttl_s=60, clock=lambda: now[0])
        await cache.get(mock_ctx, "mc23_001:production", "dataset")
        now[0] += 59
        await cache.get(mock_ctx, "mc23_001:production", "dataset")
        assert schema_client.execute.call_count == 1
        now[0] += 2
        await cache.get(mock_ctx, "mc23_001:production", "dataset")
        assert schema_client.execute.call_count == 2

    async def test_concurrent_lookups_share_one_fetch(
        self, mock_ctx: MagicMock, schema_client: MagicMock
    ) -> None:
        cache = SchemaCache()
        results = await asyncio.gather(
            *(cache.get(mock_ctx, "mc23_001:production", "dataset") for _ in range(8))
        )
        assert all(r == results[0] for r in results)
        assert schema_client.execute.call_count == 1

    async def test_failed_fetch_is_not_cached(
        self, mock_ctx: MagicMock, schema_client: MagicMock, entity_info_result: Any
    ) -> None:
        schema_client.execute.side_effect = [
            pyAMI.exception.Error("pyAMI exception: boom"),
            entity_info_result,
        ]
        cache = SchemaCache()
        with pytest.raises(pyAMI.exception.Error):
            await cache.get(mock_ctx, "mc23_001:production", "dataset")
        assert await cache.get(mock_ctx, "mc23_001:production", "dataset")


class TestFindUnknownFields:
    @pytest.fixture
    def fields(self, entity_info_result: Any) -> list[FieldInfo]:
        return parse_entity_fields(entity_info_result)

    def test_known_fields_yield_nothing(self, fields: list[FieldInfo]) -> None:
        assert find_unknown_fields(["nFiles", "totalEvents"], fields, "dataset") == {}

    def test_snake_case_alias_suggests_the_ami_name(
        self, fields: list[FieldInfo]
    ) -> None:
        unknown = find_unknown_fields(["dataset_number"], fields, "dataset")
        assert unknown == {"dataset_number": ["datasetNumber"]}

    def test_wrong_case_suggests_the_right_case(self, fields: list[FieldInfo]) -> None:
        unknown = find_unknown_fields(["ntotalevents", "NFILES"], fields, "dataset")
        assert unknown["NFILES"] == ["nFiles"]

    def test_typo_gets_close_match(self, fields: list[FieldInfo]) -> None:
        unknown = find_unknown_fields(["totalEvent"], fields, "dataset")
        assert unknown["totalEvent"][0] == "totalEvents"

    def test_no_match_gives_empty_suggestions(self, fields: list[FieldInfo]) -> None:
        assert find_unknown_fields(["zzzzqqqq"], fields, "dataset") == {
            "zzzzqqqq": []
        }

    def test_aliases_are_only_used_for_the_dataset_entity(self) -> None:
        # The aliases map to dataset-entity names; a files entity has no such field.
        files = [FieldInfo(name="LFN", type="VARCHAR(255)", description="")]
        assert find_unknown_fields(["dataset_number"], files, "files") == {
            "dataset_number": []
        }
