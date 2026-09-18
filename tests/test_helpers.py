"""Tests for ami_mcp.tools._helpers."""

from __future__ import annotations

from collections import OrderedDict

from mcp.types import CallToolResult

from ami_mcp.tools._helpers import format_ami_result, format_error, rows_to_dicts


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
