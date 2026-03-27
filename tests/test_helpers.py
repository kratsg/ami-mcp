"""Tests for ami_mcp.tools._helpers."""

from __future__ import annotations

from collections import OrderedDict

from ami_mcp.tools._helpers import format_ami_result


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
