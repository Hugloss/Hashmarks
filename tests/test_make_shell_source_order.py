"""Lexical source order and extent never establish native execution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap, MakeShellDeclarations


def _observation(tmp_path: Path, source: str, *, language: str = "shell") -> dict:
    path = "Makefile" if language == "make" else "demo.sh"
    (tmp_path / path).write_text(source, encoding="utf-8", newline="")
    with CodeMap(tmp_path) as native:
        native.index.sync()
        packet = native.declarations.discover(
            [
                MakeShellDeclarations(
                    make_paths=(path,) if language == "make" else (),
                    shell_paths=(path,) if language == "shell" else (),
                    layout="file",
                )
            ]
        )
    declarations = packet["declarations"]
    assert isinstance(declarations, dict)
    groups = declarations["groups"]
    assert isinstance(groups, list)
    rows = groups[0]["declarations"]
    assert isinstance(rows, list)
    return rows[0]["value"]


def _commands(value: dict) -> list[dict]:
    return [
        row["value"]
        for row in value["facts"]
        if row["kind"] == "shell-command-expression"
    ]


@pytest.mark.parametrize(
    "source",
    [
        'TOOL=runner; "$TOOL" inspect\n',
        'run() { local TOOL=runner; "$TOOL" inspect; }\nrun\n',
        'TOOL="fi; data"; "$TOOL" inspect\n',
    ],
)
def test_prior_same_line_shell_assignment_has_exact_lexical_origin(
    tmp_path: Path, source: str
) -> None:
    commands = _commands(_observation(tmp_path, source))
    use = next(row for row in commands if row["words"][0].get("reference"))
    observed = use["static_binding_observation"]
    expected = "fi; data" if "fi; data" in source else "runner"
    assert observed["words"] == [expected, "inspect"]
    assert use["logical_offset"] == source.index('"$TOOL"')
    assert use["logical_offset_coordinate"] == "zero-based-logical-line-characters"
    declaration = observed["supporting_declarations"][0]
    assert declaration["logical_offset"] < use["logical_offset"]
    assert observed["execution"] == observed["effective_command"] == "not-established"


@pytest.mark.parametrize(
    "source",
    [
        '"$TOOL" inspect; TOOL=runner\n',
        'run() { "$TOOL" inspect; local TOOL=runner; }\nrun\n',
        'TOOL=first; TOOL=second; "$TOOL" inspect\n',
    ],
)
def test_future_or_conflicting_shell_definitions_stay_unclassified(
    tmp_path: Path, source: str
) -> None:
    use = next(
        row
        for row in _commands(_observation(tmp_path, source))
        if row["words"][0].get("reference")
    )
    observed = use["static_binding_observation"]
    assert observed["state"] == "unclassified"
    assert "words" not in observed
    assert observed["authored_words"][0]["state"] == "unresolved-source-expression"


@pytest.mark.parametrize("operator", ["=", "?="])
def test_recursive_make_forward_reference_is_only_an_authored_candidate(
    tmp_path: Path, operator: str
) -> None:
    source = f"ALIAS {operator} $(LATER)\nLATER = runner\ncheck:\n\t$(ALIAS) inspect\n"
    use = _commands(_observation(tmp_path, source, language="make"))[0]
    observed = use["static_binding_observation"]
    assert observed["state"] == "conditional-source"
    assert observed["words"] == ["runner", "inspect"]
    assert "recursive-make-source-reference" in observed["conditions"]
    assert "native-make-evaluation-time-unestablished" in observed["conditions"]
    assert {row["start_line"] for row in observed["supporting_declarations"]} == {1, 2}
    assert observed["effective_command"] == "not-established"


def test_command_local_assignment_does_not_supply_the_same_statement_word(
    tmp_path: Path,
) -> None:
    use = _commands(_observation(tmp_path, 'launcher=python "$launcher" -m module\n'))[
        0
    ]
    assert use["static_binding_observation"]["state"] == "unclassified"
    assert use["words"][0]["reference"]["name"] == "launcher"
    assert (
        use["command_local_environment"][0]["value_expression"]["literal"] == "python"
    )


def test_command_local_assignment_does_not_replace_the_earlier_authored_binding(
    tmp_path: Path,
) -> None:
    uses = _commands(
        _observation(
            tmp_path,
            'launcher=base; launcher=environment "$launcher" inspect; "$launcher" later\n',
        )
    )
    assert [row["static_binding_observation"]["words"] for row in uses] == [
        ["base", "inspect"],
        ["base", "later"],
    ]
    assert (
        uses[0]["command_local_environment"][0]["value_expression"]["literal"]
        == "environment"
    )


@pytest.mark.parametrize("operator", [":=", "::="])
def test_immediate_make_binding_does_not_borrow_a_later_definition(
    tmp_path: Path, operator: str
) -> None:
    value = _observation(
        tmp_path,
        f"ALIAS {operator} $(LATER)\nLATER=runner\ncheck:\n\t$(ALIAS) inspect\n",
        language="make",
    )
    observed = _commands(value)[0]["static_binding_observation"]
    assert observed["state"] == "unclassified"
    assert "words" not in observed


def test_same_line_control_closures_do_not_accumulate_later_context(
    tmp_path: Path,
) -> None:
    value = _observation(
        tmp_path,
        "if observe; then printf '%s' 'fi'; fi\n" * 600
        + 'TOOL=runner\n"$TOOL" inspect\n',
    )
    assert len(value["facts"]) == 602
    assert len(json.dumps(value).encode()) < 1_048_576
    use = _commands(value)[0]
    assert use["context"] == []
    assert use["static_binding_observation"]["words"] == ["runner", "inspect"]
    assert value["negative_evidence_admissible"] is False


def test_nested_unclosed_control_and_argument_keywords_do_not_invent_closure(
    tmp_path: Path,
) -> None:
    value = _observation(
        tmp_path,
        "if observe; then if inspect; then printf '%s' fi; fi\n"
        'TOOL=runner\n"$TOOL" inside\nfi\n"$TOOL" after\n',
    )
    inside, after = _commands(value)
    assert inside["context"] == ["conditional-or-loop:1"]
    assert after["context"] == []
    assert all(row["execution"] == "not-established" for row in (inside, after))


def test_control_heredoc_keeps_data_uninterpreted_and_later_source_conditional(
    tmp_path: Path,
) -> None:
    value = _observation(tmp_path, "if reader <<'END'; then\ninert command\nEND\nfi\n")
    assert value["facts_completeness"] == "complete-supported-subset"
    assert _commands(value) == []
    data = next(
        row["value"] for row in value["facts"] if row["kind"] == "shell-heredoc-data"
    )
    assert data["body_observation"] == "uninterpreted-data"
    assert value["negative_evidence_admissible"] is False
