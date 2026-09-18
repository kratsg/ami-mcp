"""Tests for ami_mcp.policy."""

from __future__ import annotations

import pytest

from ami_mcp.nomenclature import AMI_QUERY_LANGUAGE
from ami_mcp.policy import (
    DEFAULT_ALLOWED_COMMANDS,
    command_verb,
    describe_allowed,
    is_command_allowed,
    parse_allowed_commands,
    resolve_allowed_commands,
)

# The command verbs the other 10 tools hardcode, cited by file:line so a
# reviewer can verify the claim without re-deriving it:
#   tags.py:57, datasets.py:92,193,374, hashtags.py:105,188, physics.py:63,
#   validate.py:171,204
_VERBS_HARDCODED_BY_OTHER_TOOLS = frozenset(
    {
        "SearchQuery",
        "AMIGetDatasetInfo",
        "AMIGetDatasetProv",
        "AMIGetAMITagInfo",
        "GetPhysicsParamsForDataset",
        "DatasetWBListHashtags",
    }
)


class TestCommandVerb:
    def test_extracts_first_token(self) -> None:
        cmd = 'SearchQuery -catalog=mc23_001:production -entity=HASHTAGS -mql="SELECT ..."'
        assert command_verb(cmd) == "SearchQuery"

    def test_ignores_leading_whitespace(self) -> None:
        assert command_verb('   AMIGetDatasetInfo -logicalDatasetName="x"') == (
            "AMIGetDatasetInfo"
        )

    def test_handles_embedded_newlines_and_tabs(self) -> None:
        cmd = 'SearchQuery\n  -catalog=x\n\t-mql="SELECT 1"'
        assert command_verb(cmd) == "SearchQuery"

    def test_handles_command_without_arguments(self) -> None:
        assert command_verb("SearchQuery") == "SearchQuery"

    def test_empty_string_has_no_verb(self) -> None:
        assert command_verb("") == ""

    def test_whitespace_only_has_no_verb(self) -> None:
        assert command_verb("   \t\n") == ""

    def test_survives_unbalanced_quotes_in_mql(self) -> None:
        # MQL escapes ' as '', so a command can carry an odd number of quote
        # characters. shlex.split would raise ValueError on this; plain
        # str.split must not.
        cmd = "SearchQuery -mql=\"WHERE physicsShort LIKE '%Zee%'\""
        assert command_verb(cmd) == "SearchQuery"


class TestParseAllowedCommands:
    def test_none_returns_empty(self) -> None:
        assert parse_allowed_commands(None) == frozenset()

    def test_empty_list_returns_empty(self) -> None:
        assert parse_allowed_commands([]) == frozenset()

    def test_repeated_values(self) -> None:
        assert parse_allowed_commands(["A", "B"]) == frozenset({"A", "B"})

    def test_comma_separated_in_one_value(self) -> None:
        assert parse_allowed_commands(["A,B"]) == frozenset({"A", "B"})

    def test_comma_and_whitespace_mixed(self) -> None:
        assert parse_allowed_commands(["A, B ,C"]) == frozenset({"A", "B", "C"})

    def test_whitespace_separated(self) -> None:
        assert parse_allowed_commands(["A B"]) == frozenset({"A", "B"})


class TestResolveAllowedCommands:
    def test_defaults_when_no_extra(self) -> None:
        assert resolve_allowed_commands(None) == DEFAULT_ALLOWED_COMMANDS
        assert len(DEFAULT_ALLOWED_COMMANDS) == 7

    def test_extends_defaults(self) -> None:
        resolved = resolve_allowed_commands(["GetElementInfo"])
        assert "GetElementInfo" in resolved
        assert resolved >= DEFAULT_ALLOWED_COMMANDS

    def test_cannot_narrow_defaults(self) -> None:
        # Passing only a subset of the defaults must not shrink the set --
        # extend-only, never narrow.
        assert resolve_allowed_commands(["SearchQuery"]) == DEFAULT_ALLOWED_COMMANDS


class TestIsCommandAllowed:
    def test_accepts_a_default_verb(self) -> None:
        assert is_command_allowed(
            'SearchQuery -catalog=x -mql="SELECT 1"', DEFAULT_ALLOWED_COMMANDS
        )

    def test_matches_case_insensitively(self) -> None:
        assert is_command_allowed("searchquery -x", DEFAULT_ALLOWED_COMMANDS)
        assert is_command_allowed("SEARCHQUERY", DEFAULT_ALLOWED_COMMANDS)

    def test_rejects_a_non_allowlisted_verb(self) -> None:
        assert not is_command_allowed("GetElementInfo -x", DEFAULT_ALLOWED_COMMANDS)

    def test_rejects_empty_command(self) -> None:
        assert not is_command_allowed("", DEFAULT_ALLOWED_COMMANDS)
        assert not is_command_allowed("   ", DEFAULT_ALLOWED_COMMANDS)

    def test_rejects_a_verb_hidden_in_the_query_body(self) -> None:
        # First-token match only -- never a substring search of the whole
        # command, which would let a disallowed verb hide inside an allowed
        # one's arguments.
        assert not is_command_allowed(
            'Evil -mql="SearchQuery"', DEFAULT_ALLOWED_COMMANDS
        )

    def test_accepts_a_verb_added_via_configuration(self) -> None:
        allowed = resolve_allowed_commands(["GetElementInfo"])
        assert is_command_allowed("GetElementInfo -x", allowed)


class TestDefaultSetProvenance:
    def test_defaults_are_documented_in_the_query_language_resource(self) -> None:
        for verb in DEFAULT_ALLOWED_COMMANDS:
            assert verb in AMI_QUERY_LANGUAGE


class TestDefaultSetCoversBuiltinTools:
    def test_every_hardcoded_verb_is_allowlisted_by_default(self) -> None:
        # Drift guard: if a tool starts issuing a new hardcoded command verb,
        # this test fails until DEFAULT_ALLOWED_COMMANDS is updated to match --
        # keeps the default allowlist a provable superset of the repo's own
        # usage, so ami_execute's gate can never be stricter than what the
        # curated tools already do unchecked.
        assert _VERBS_HARDCODED_BY_OTHER_TOOLS <= DEFAULT_ALLOWED_COMMANDS


class TestDescribeAllowed:
    def test_renders_a_stable_sorted_list(self) -> None:
        assert describe_allowed({"B", "A"}) == "A, B"


@pytest.mark.parametrize("case", [str.upper, str.lower])
def test_is_command_allowed_is_insensitive_to_allowed_set_casing(case) -> None:
    allowed = {case("SearchQuery")}
    assert is_command_allowed("SearchQuery -x", allowed)
