"""Authored source flow remains conditional around unobserved native state."""

from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap, MakeShellDeclarations


def _commands(tmp_path: Path, source: str) -> list[dict]:
    (tmp_path / "demo.sh").write_text(source)
    with CodeMap(tmp_path) as native:
        native.index.sync()
        packet = native.declarations.discover(
            [MakeShellDeclarations(shell_paths=("demo.sh",), layout="file")]
        )
    declarations = packet["declarations"]
    assert isinstance(declarations, dict)
    groups = declarations["groups"]
    assert isinstance(groups, list)
    group_declarations = groups[0]["declarations"]
    assert isinstance(group_declarations, list)
    value = group_declarations[0]["value"]
    assert value["negative_evidence_admissible"] is False
    assert value["facts_truncation"] == "not-truncated"
    return [
        row["value"]
        for row in value["facts"]
        if row["kind"] == "shell-command-expression"
    ]


@pytest.mark.parametrize(
    "uncertainty", ['source "$UNOBSERVED"', 'eval "$UNOBSERVED"', 'unknown > "$OUTPUT"']
)
def test_later_literal_declarations_retain_only_conditional_authored_use(
    tmp_path: Path, uncertainty: str
) -> None:
    commands = _commands(
        tmp_path,
        uncertainty + '\nTOOL=runner\nACTION=inspect\n"$TOOL" "$ACTION" selected\n',
    )
    observed = commands[-1]["static_binding_observation"]
    assert observed["state"] == "conditional-source"
    assert observed["words"] == ["runner", "inspect", "selected"]
    assert {row["name"] for row in observed["supporting_declarations"]} == {
        "TOOL",
        "ACTION",
    }
    assert "unobserved-source-state-may-change-bindings" in observed["conditions"]
    assert "authored-declarations-must-take-effect" in observed["conditions"]
    assert "no-unobserved-rebinding-or-readonly-conflict" in observed["conditions"]
    assert observed["effective_command"] == observed["execution"] == "not-established"
    assert observed["negative_evidence_admissible"] is False


def test_unknown_word_does_not_erase_other_authored_source_candidates(
    tmp_path: Path,
) -> None:
    commands = _commands(
        tmp_path,
        'source "$UNOBSERVED"\nENGINE="$(choose_native)"\nALIAS="$ENGINE"\n'
        'ARGS=("$ALIAS" -P -m module.native)\n"${ARGS[@]}" "$EXTERNAL" --workers 1\n',
    )
    observed = commands[-1]["static_binding_observation"]
    assert observed["state"] == "unclassified" and "words" not in observed
    words = observed["authored_words"]
    assert words[0]["state"] == "unresolved-source-expression"
    assert words[0]["source_word"]["expression"] == '"$(choose_native)"'
    assert words[0]["runtime_value"] == "not-established"
    assert [word.get("literal") for word in words[1:4]] == ["-P", "-m", "module.native"]
    assert words[4]["source_word"]["reference"]["name"] == "EXTERNAL"
    assert words[5:] == [
        {"state": "literal-source-candidate", "literal": "--workers"},
        {"state": "literal-source-candidate", "literal": "1"},
    ]
    assert {row["name"] for row in observed["supporting_declarations"]} == {
        "ENGINE",
        "ALIAS",
        "ARGS",
    }
    assert observed["effective_command"] == "not-established"


def test_helper_input_retains_one_source_edge_despite_unobserved_state(
    tmp_path: Path,
) -> None:
    commands = _commands(
        tmp_path,
        'source "$UNOBSERVED"\nrun() {\n local tool="$1"\n "$tool" inspect "$EXTERNAL"\n}\nrun runner\n',
    )
    body = next(row for row in commands if row["context"] == ["function:run:2"])
    observed = body["invocation_binding_observation"]["candidates"][0]["observation"]
    assert observed["state"] == "unclassified"
    assert observed["authored_words"][0] == {
        "state": "literal-source-candidate",
        "literal": "runner",
    }
    assert "one-observed-source-invocation-not-all-callers" in observed["conditions"]
    assert "unobserved-source-state-may-change-bindings" in observed["conditions"]
    assert observed["execution"] == "not-established"


def test_observed_rebinding_does_not_recover_an_old_literal_candidate(
    tmp_path: Path,
) -> None:
    commands = _commands(
        tmp_path, 'source "$UNOBSERVED"\nTOOL=first\nTOOL=second\n"$TOOL" inspect\n'
    )
    observed = commands[-1]["static_binding_observation"]
    assert observed["state"] == "unclassified"
    assert observed["authored_words"][0]["source_word"]["reference"]["name"] == "TOOL"
    assert observed["supporting_declarations"] == []


@pytest.mark.parametrize("option", ["-n", "-f"])
def test_export_options_do_not_invent_a_plain_variable_export(
    tmp_path: Path, option: str
) -> None:
    commands = _commands(
        tmp_path, f"VALUE=source\nexport {option} VALUE\nrunner --check\n"
    )
    assert (
        "authored_environment_bindings"
        not in commands[-1]["static_binding_observation"]
    )


def test_unresolved_statement_keeps_comment_free_tokens_without_runtime_claims(
    tmp_path: Path,
) -> None:
    (tmp_path / "demo.sh").write_text(
        'case "$SELECTED" in\n'
        " first) printf '%s' wrong/path ;; # expected/path\n"
        "esac\n"
    )
    with CodeMap(tmp_path) as native:
        native.index.sync()
        packet = native.declarations.discover(
            [MakeShellDeclarations(shell_paths=("demo.sh",))]
        )
    declarations = packet["declarations"]
    assert isinstance(declarations, dict)
    groups = declarations["groups"]
    row = next(
        group["declarations"][0]["value"]
        for group in groups
        if group["concept"]["kind"] == "shell-unresolved-statement"
    )
    assert "expected/path" in row["expression"]
    assert row["token_expressions"] == [
        "first",
        ")",
        "printf",
        "'%s'",
        "wrong/path",
        ";",
        ";",
    ]
    assert row["execution"] == "not-established"
    assert row["negative_evidence_admissible"] is False


@pytest.mark.parametrize("split", [False, True])
def test_exported_source_bindings_retain_unresolved_origin_and_export_sites(
    tmp_path: Path, split: bool
) -> None:
    export = (
        'VALUE="$ROOT/source"\nexport VALUE' if split else 'export VALUE="$ROOT/source"'
    )
    commands = _commands(
        tmp_path,
        'source "$UNOBSERVED"\n' + export + "\nexport MODE=isolated\nrunner --check\n",
    )
    exports = commands[-1]["static_binding_observation"][
        "authored_environment_bindings"
    ]
    assert [row["name"] for row in exports] == ["MODE", "VALUE"]
    assert exports[0]["binding"]["authored_words"] == [
        {"state": "literal-source-candidate", "literal": "isolated"}
    ]
    value = exports[1]
    assert (
        value["binding"]["authored_words"][0]["source_word"]["expression"]
        == '"$ROOT/source"'
    )
    assert value["export_sites"] and value["binding"]["supporting_declarations"]
    assert value["effective_environment"] == value["execution"] == "not-established"
    assert "authored-export-and-declaration-must-take-effect" in value["conditions"]
