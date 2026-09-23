"""Tests for ami_mcp.tools._helpers."""

from __future__ import annotations

from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest
from mcp.types import CallToolResult

from ami_mcp.tools._helpers import (
    data_type_to_prod_step,
    format_ami_result,
    format_error,
    is_frequency_limited,
    is_transient,
    rows_to_dicts,
    run_ami_command,
    scope_to_catalog,
)

_FREQUENCY_MESSAGE = (
    "pyAMI exception: Max command frequency reached for this user/machine. "
    "Please optimize your script or use cache..."
)


class TestFormatAmiResult:
    def test_empty_returns_no_results(self) -> None:
        assert format_ami_result([]) == "No results."

    def test_markdown_table_header_row(self) -> None:
        rows = [OrderedDict([("NAME", "WeakBoson"), ("SCOPE", "PMGL1")])]
        result = format_ami_result(rows)
        assert "| NAME | SCOPE |" in result

    def test_markdown_table_separator_row(self) -> None:
        rows = [OrderedDict([("NAME", "WeakBoson"), ("SCOPE", "PMGL1")])]
        result = format_ami_result(rows)
        assert "| --- | --- |" in result

    def test_markdown_table_data_row(self) -> None:
        rows = [OrderedDict([("NAME", "WeakBoson"), ("SCOPE", "PMGL1")])]
        result = format_ami_result(rows)
        assert "| WeakBoson | PMGL1 |" in result

    def test_multiple_rows(self) -> None:
        rows = [
            OrderedDict([("NAME", "WeakBoson"), ("SCOPE", "PMGL1")]),
            OrderedDict([("NAME", "Vjets"), ("SCOPE", "PMGL2")]),
        ]
        result = format_ami_result(rows)
        lines = result.splitlines()
        # header + separator + 2 data rows
        assert len(lines) == 4

    def test_truncation_message(self) -> None:
        rows = [OrderedDict([("x", str(i))]) for i in range(5)]
        result = format_ami_result(rows, max_rows=3)
        assert "2 more rows" in result

    def test_non_dict_rows(self) -> None:
        result = format_ami_result(["alpha", "beta"])
        assert "alpha" in result
        assert "beta" in result

    def test_single_row_many_columns_renders_vertical(self) -> None:
        # More than 6 keys → vertical Field | Value table
        keys = [f"col{i}" for i in range(7)]
        rows = [OrderedDict((k, f"val{i}") for i, k in enumerate(keys))]
        result = format_ami_result(rows)
        assert "| Field | Value |" in result
        assert "| col0 | val0 |" in result

    def test_single_row_few_columns_renders_horizontal(self) -> None:
        # 2 keys → horizontal table (below threshold)
        rows = [OrderedDict([("NAME", "WeakBoson"), ("SCOPE", "PMGL1")])]
        result = format_ami_result(rows)
        assert "| NAME | SCOPE |" in result
        assert "| Field | Value |" not in result

    def test_multi_row_many_columns_renders_horizontal(self) -> None:
        # Multiple rows always use horizontal format regardless of column count
        keys = [f"col{i}" for i in range(7)]
        rows = [
            OrderedDict((k, f"row0_{k}") for k in keys),
            OrderedDict((k, f"row1_{k}") for k in keys),
        ]
        result = format_ami_result(rows)
        assert "| col0 |" in result
        assert "| Field | Value |" not in result


class TestFormatError:
    def test_returns_an_is_error_call_tool_result(self) -> None:
        result = format_error(ValueError("bad"))
        assert isinstance(result, CallToolResult)
        assert result.is_error is True
        assert result.structured_content is None

    def test_message_carries_the_exception_text(self) -> None:
        result = format_error(ValueError("bad thing happened"))
        assert "bad thing happened" in result.content[0].text  # type: ignore[union-attr]

    def test_context_is_appended(self) -> None:
        result = format_error(ValueError("bad"), context="extra context")
        assert "extra context" in result.content[0].text  # type: ignore[union-attr]

    def test_hints_are_appended(self) -> None:
        result = format_error(ValueError("bad"), hints=["Try again."])
        assert "Try again." in result.content[0].text  # type: ignore[union-attr]

    def test_transient_error_gets_a_retry_hint_ahead_of_callers_hints(self) -> None:
        result = format_error(
            Exception("pyAMI exception: Closed Connection"),
            hints=["Verify the LDN is complete."],
        )
        text = result.content[0].text  # type: ignore[union-attr]
        assert "transient" in text.lower()
        assert text.index("transient") < text.index("Verify the LDN is complete.")

    def test_non_transient_error_gets_no_retry_hint(self) -> None:
        result = format_error(ValueError("bad"), hints=["Try again."])
        assert "transient" not in result.content[0].text.lower()  # type: ignore[union-attr]

    def test_frequency_limited_error_gets_rate_limit_hint(self) -> None:
        result = format_error(
            Exception(_FREQUENCY_MESSAGE),
            hints=["Read the ami://query-language resource for command syntax."],
        )
        text = result.content[0].text  # type: ignore[union-attr]
        assert "rate" in text.lower()

    def test_frequency_limited_error_replaces_callers_hints(self) -> None:
        result = format_error(
            Exception(_FREQUENCY_MESSAGE),
            hints=["Read the ami://query-language resource for command syntax."],
        )
        text = result.content[0].text  # type: ignore[union-attr]
        assert "query-language" not in text


class TestRowsToDicts:
    def test_ordered_dict_rows_pass_through_as_plain_dicts(self) -> None:
        rows = [OrderedDict([("NAME", "WeakBoson")])]
        assert rows_to_dicts(rows) == [{"NAME": "WeakBoson"}]

    def test_non_dict_rows_are_wrapped_in_a_value_key(self) -> None:
        assert rows_to_dicts(["alpha", "beta"]) == [
            {"value": "alpha"},
            {"value": "beta"},
        ]

    def test_empty_list_returns_empty_list(self) -> None:
        assert rows_to_dicts([]) == []


class TestDataTypeToProdStep:
    @pytest.mark.parametrize("data_type", ["EVNT", "HEPMC"])
    def test_evgen_data_types(self, data_type: str) -> None:
        assert data_type_to_prod_step(data_type) == "evgen"

    def test_hits_is_sim(self) -> None:
        assert data_type_to_prod_step("HITS") == "sim"

    @pytest.mark.parametrize(
        "data_type",
        ["AOD", "DAOD_PHYS", "DAOD_PHYSLITE", "RDO", "ESD"],
    )
    def test_derivation_and_reco_types_are_reco(self, data_type: str) -> None:
        assert data_type_to_prod_step(data_type) == "reco"

    def test_none_defaults_to_reco(self) -> None:
        assert data_type_to_prod_step(None) == "reco"


class TestScopeToCatalog:
    @pytest.mark.parametrize(
        ("project", "prod_step", "expected"),
        [
            ("mc16_13TeV", "evgen", "mc15_001:production"),
            ("mc16_13TeV", "sim", "mc16_001:production"),
            ("mc16_13TeV", "reco", "mc16_001:production"),
            ("mc20_13TeV", "evgen", "mc15_001:production"),
            ("mc20_13TeV", "sim", "mc16_001:production"),
            ("mc20_13TeV", "reco", "mc20_001:production"),
            ("mc21_13p6TeV", "evgen", "mc21_001:production"),
            ("mc21_13p6TeV", "sim", "mc21_001:production"),
            ("mc21_13p6TeV", "reco", "mc21_001:production"),
            ("mc23_13p6TeV", "evgen", "mc23_001:production"),
            ("mc23_13p6TeV", "sim", "mc23_001:production"),
            ("mc23_13p6TeV", "reco", "mc23_001:production"),
        ],
    )
    def test_known_projects(self, project: str, prod_step: str, expected: str) -> None:
        assert scope_to_catalog(project, prod_step) == expected

    def test_unknown_project_falls_back_to_prefix(self) -> None:
        assert scope_to_catalog("data22_13p6TeV", "reco") == "data22_001:production"

    def test_unknown_project_falls_back_regardless_of_prod_step(self) -> None:
        assert scope_to_catalog("data22_13p6TeV", "evgen") == "data22_001:production"


class TestIsTransient:
    @pytest.mark.parametrize(
        "message",
        [
            "pyAMI exception: No more data to read from socket",
            "pyAMI exception: Closed Connection",
            "Connection reset by peer",
            "Broken pipe",
            "EOF occurred in violation of protocol",
            "could not connect to `https://atlas-ami.cern.ch:443...`: timed out",
            "service temporarily unreachable",
            "Read timed out.",
        ],
    )
    def test_transient_connection_messages(self, message: str) -> None:
        assert is_transient(Exception(message)) is True

    @pytest.mark.parametrize(
        "message",
        [
            "pyAMI exception: unknown command `Bogus`",
            "pyAMI exception: invalid format `xml`, not in [dom_object]",
            "command parsing error, please contact ami@lpsc.in2p3.fr",
        ],
    )
    def test_semantic_ami_errors_are_not_transient(self, message: str) -> None:
        assert is_transient(Exception(message)) is False

    def test_matching_is_case_insensitive(self) -> None:
        assert is_transient(Exception("CLOSED CONNECTION")) is True

    def test_frequency_limit_message_is_not_transient(self) -> None:
        assert is_transient(Exception(_FREQUENCY_MESSAGE)) is False


class TestIsFrequencyLimited:
    def test_frequency_limit_message(self) -> None:
        assert is_frequency_limited(Exception(_FREQUENCY_MESSAGE)) is True

    def test_matching_is_case_insensitive(self) -> None:
        assert is_frequency_limited(Exception("MAX COMMAND FREQUENCY REACHED")) is True

    @pytest.mark.parametrize(
        "message",
        [
            "pyAMI exception: Closed Connection",
            "pyAMI exception: unknown command `Bogus`",
            "Connection reset by peer",
        ],
    )
    def test_other_messages_are_not_frequency_limited(self, message: str) -> None:
        assert is_frequency_limited(Exception(message)) is False


class _FakeClient:
    """A pyAMI-client stand-in whose ``execute`` fails a fixed number of times."""

    def __init__(self, failures: list[Exception], result: Any = "ok") -> None:
        self._failures = list(failures)
        self._result = result
        self.execute_calls = 0

    def execute(self, command: str, format: str = "dom_object") -> Any:  # noqa: ARG002
        self.execute_calls += 1
        if self._failures:
            raise self._failures.pop(0)
        return self._result


class _FakeFactory:
    """A client factory spy that counts how many times a client was acquired."""

    def __init__(self, client: _FakeClient) -> None:
        self._client = client
        self.get_client_calls = 0

    def get_client(self, ctx: Any) -> Any:  # noqa: ARG002
        self.get_client_calls += 1
        return self._scoped()

    @asynccontextmanager
    async def _scoped(self) -> Any:
        yield self._client


def _make_ctx(factory: _FakeFactory) -> MagicMock:
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {"client_factory": factory}
    return ctx


class TestRunAmiCommandRetry:
    async def test_succeeds_on_first_attempt_without_retry(self) -> None:
        client = _FakeClient(failures=[], result="ok")
        factory = _FakeFactory(client)
        result = await run_ami_command(_make_ctx(factory), "SearchQuery -x=1")
        assert result == "ok"
        assert factory.get_client_calls == 1
        assert client.execute_calls == 1

    async def test_retries_once_on_transient_error_then_succeeds(self) -> None:
        client = _FakeClient(
            failures=[Exception("pyAMI exception: No more data to read from socket")],
            result="ok",
        )
        factory = _FakeFactory(client)
        result = await run_ami_command(
            _make_ctx(factory), "SearchQuery -x=1", retry_delay=0
        )
        assert result == "ok"
        # A fresh client is re-acquired per attempt (broker mode redeems a
        # fresh proxy per get_client() call).
        assert factory.get_client_calls == 2
        assert client.execute_calls == 2

    async def test_non_transient_error_raises_immediately(self) -> None:
        client = _FakeClient(
            failures=[Exception("pyAMI exception: unknown command `Bogus`")],
        )
        factory = _FakeFactory(client)
        with pytest.raises(Exception, match="unknown command"):
            await run_ami_command(_make_ctx(factory), "Bogus", retry_delay=0)
        assert factory.get_client_calls == 1

    async def test_transient_error_on_every_attempt_raises_original(self) -> None:
        client = _FakeClient(
            failures=[
                Exception("Closed Connection"),
                Exception("Closed Connection"),
            ],
        )
        factory = _FakeFactory(client)
        with pytest.raises(Exception, match="Closed Connection"):
            await run_ami_command(_make_ctx(factory), "SearchQuery -x=1", retry_delay=0)
        assert factory.get_client_calls == 2
        assert client.execute_calls == 2

    async def test_attempts_one_disables_retry(self) -> None:
        client = _FakeClient(
            failures=[Exception("Closed Connection")],
        )
        factory = _FakeFactory(client)
        with pytest.raises(Exception, match="Closed Connection"):
            await run_ami_command(
                _make_ctx(factory), "SearchQuery -x=1", attempts=1, retry_delay=0
            )
        assert factory.get_client_calls == 1

    async def test_frequency_limit_error_is_never_retried(self) -> None:
        client = _FakeClient(failures=[Exception(_FREQUENCY_MESSAGE)])
        factory = _FakeFactory(client)
        with pytest.raises(Exception, match="Max command frequency reached"):
            await run_ami_command(_make_ctx(factory), "SearchQuery -x=1", retry_delay=0)
        assert client.execute_calls == 1
        assert factory.get_client_calls == 1

    async def test_transient_then_frequency_limit_surfaces_frequency_error(
        self,
    ) -> None:
        # The transient Closed Connection is retried once (per #27); if that
        # retry itself lands on AMI's frequency throttle, the frequency error
        # must surface as-is -- not be retried again, and not be reported as
        # a generic transient failure.
        client = _FakeClient(
            failures=[
                Exception("pyAMI exception: Closed Connection"),
                Exception(_FREQUENCY_MESSAGE),
            ],
        )
        factory = _FakeFactory(client)
        with pytest.raises(Exception, match="Max command frequency reached"):
            await run_ami_command(_make_ctx(factory), "SearchQuery -x=1", retry_delay=0)
        assert client.execute_calls == 2
        assert factory.get_client_calls == 2
