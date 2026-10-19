"""Neutral source fixtures qualify Make/shell syntax without execution claims."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from hashmarks.codemap import (
    CodeMap,
    MakeShellDeclarations,
    RepositoryDeclarationProviderError,
)
from hashmarks.codemap.make_shell_declarations import (
    MAX_MAKE_SHELL_BYTES,
    MAX_STATEMENT_WORDS,
)


def _write(root: Path, path: str, source: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")


def _observe(root: Path, provider: MakeShellDeclarations) -> dict:
    with CodeMap(root) as codemap:
        codemap.index.sync()
        return codemap.declarations.discover([provider])


def _groups(packet: dict, kind: str) -> list[dict]:
    return [
        row
        for row in packet["declarations"]["groups"]
        if row["concept"]["kind"] == kind
    ]


def _values(packet: dict, kind: str) -> list[dict]:
    return [group["declarations"][0]["value"] for group in _groups(packet, kind)]


def _evidence(packet: dict, group: dict) -> list[dict]:
    binding_id = group["declarations"][0]["binding_id"]
    return next(
        row["evidence"]
        for row in packet["declarations"]["repository_evidence"]["bindings"]
        if row["binding_id"] == binding_id
    )


def test_make_aliases_operators_targets_and_recipe_have_exact_source_origins(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "Makefile",
        (
            "RUNNER := python\n"
            "ALIAS = $(RUNNER)\n"
            "MODE ?= local\n"
            "ARGS += --quiet\n"
            "check: input.txt\n"
            '\t@MODE="two words" $(ALIAS) -m demo \\\n'
            "\t  --check\n"
        ),
    )
    packet = _observe(tmp_path, MakeShellDeclarations(make_paths=("Makefile",)))
    variables = _values(packet, "make-variable-declaration")
    assert [row["assignment_operator"] for row in variables] == [":=", "=", "?=", "+="]
    assert all(row["effective_value"] == "not-established" for row in variables)
    alias = variables[1]["variable_references"][0]
    assert alias["name"] == "RUNNER"
    assert alias["binding"] == "unresolved"
    assert alias["declaration_candidates"][0]["start_line"] == 1
    command = _values(packet, "shell-command-expression")[0]
    assert command["make_targets"] == ["check"]
    assert command["recipe_prefixes"] == "@"
    assert command["literal_argv"] is None
    assert [row["literal"] for row in command["words"][1:]] == ["-m", "demo", "--check"]
    assert (
        command["command_local_environment"][0]["value_expression"]["literal"]
        == "two words"
    )
    assert (
        command["variable_references"][0]["declaration_candidates"][0]["start_line"]
        == 2
    )
    evidence = _evidence(packet, _groups(packet, "shell-command-expression")[0])[0]
    assert (evidence["start_line"], evidence["end_line"]) == (6, 7)
    assert (
        evidence["member_revision"]
        == packet["providers"][0]["inputs"][0]["member_revision"]
    )


def test_shell_quotes_aliases_functions_and_local_environment_remain_syntax(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "scripts/demo.sh",
        (
            "# hidden-command never becomes an invocation\n"
            "RUNNER=python\n"
            'ALIAS="$RUNNER"\n'
            "alias short='python -m demo'\n"
            'run() { "$ALIAS" "$@"; }\n'
            "export MODE=declared\n"
            "MODE=local run 'inert; hidden-command'\n"
            "printf '%s' '$RUNNER' a\\ b\n"
            "short --help\n"
        ),
    )
    packet = _observe(tmp_path, MakeShellDeclarations(shell_paths=("scripts/demo.sh",)))
    commands = _values(packet, "shell-command-expression")
    assert len(commands) == 4
    assert commands[0]["context"] == ["function:run:5"]
    assert commands[0]["words"][1]["state"] == "unresolved-expansion"
    assert commands[1]["literal_argv"] == ["run", "inert; hidden-command"]
    assert commands[1]["command_declaration_candidates"][0]["start_line"] == 5
    assert commands[1]["command_local_environment"][0]["name"] == "MODE"
    assert commands[2]["literal_argv"] == ["printf", "%s", "$RUNNER", "a b"]
    assert commands[2]["variable_references"] == []
    assert (
        commands[3]["command_declaration_candidates"][0]["kind"]
        == "shell-alias-declaration"
    )
    exported = _values(packet, "shell-variable-declaration")[-1]
    assert exported["modifier"] == "export"
    assert all(row["execution"] == "not-established" for row in commands)


@pytest.mark.parametrize("target", ["one\\ two", "*.o", "file?.o", "[ab].o"])
def test_make_escaped_and_pattern_targets_leave_recipe_ownership_unresolved(
    tmp_path: Path,
    target: str,
) -> None:
    _write(tmp_path, "Makefile", f"{target}:\n\techo fixture\n")
    packet = _observe(tmp_path, MakeShellDeclarations(make_paths=("Makefile",)))
    assert _values(packet, "make-target-declaration") == []
    assert _values(packet, "shell-command-expression") == []
    assert len(_values(packet, "make-unresolved-statement")) == 1
    assert len(_values(packet, "make-unresolved-recipe")) == 1


def test_make_recipe_whitespace_precedes_prefix_processing(tmp_path: Path) -> None:
    _write(tmp_path, "Makefile", "all:\n\t  @-+echo ready\n")
    packet = _observe(tmp_path, MakeShellDeclarations(make_paths=("Makefile",)))
    command = _values(packet, "shell-command-expression")[0]
    assert command["literal_argv"] == ["echo", "ready"]
    assert command["recipe_prefixes"] == "@-+"
    assert command["make_targets"] == ["all"]
    evidence = _evidence(packet, _groups(packet, "shell-command-expression")[0])[0]
    assert (evidence["start_line"], evidence["end_line"]) == (2, 2)


def test_ambiguous_alias_declarations_do_not_acquire_precedence(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "demo.sh",
        ('COMMAND=first\nif condition; then\n  COMMAND=second\nfi\n"$COMMAND" arg\n'),
    )
    packet = _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))
    reference = _values(packet, "shell-command-expression")[-1]["variable_references"][
        0
    ]
    assert [row["start_line"] for row in reference["declaration_candidates"]] == [1, 3]
    assert reference["declaration_candidates"][1]["context"] == [
        "conditional-or-loop:2"
    ]
    assert reference["binding"] == "unresolved"


def test_quoted_escape_projection_and_inline_function_comment_are_exact(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "demo.sh",
        (
            'show() { printf "%s" "\\$VALUE" a\\ b; } # comment\n'
            'show "a\\q"\n'
            'printf "%s" $V""AR\n'
        ),
    )
    packet = _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))
    commands = _values(packet, "shell-command-expression")
    assert commands[0]["literal_argv"] == ["printf", "%s", "$VALUE", "a b"]
    assert commands[1]["literal_argv"] == ["show", "a\\q"]
    assert commands[1]["context"] == []
    assert commands[2]["variable_references"][0]["name"] == "V"


def test_dynamic_expansion_includes_and_make_macros_are_observed_without_execution(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "must-not-exist"
    _write(
        tmp_path,
        "demo.sh",
        (
            f'VALUE="$(touch {marker})"\n'
            f"echo `touch {marker}`\n"
            "source external.sh\n"
            "array=(first second)\n"
            "eval dynamic_command\n"
        ),
    )
    _write(
        tmp_path,
        "Makefile",
        (
            f"DYNAMIC = $(shell touch {marker})\n"
            "include external.mk\n"
            "define WRAPPER\n"
            "\tmacro-data-not-a-command\n"
            "endef\n"
            "run:\n"
            "\t$(DYNAMIC)\n"
        ),
    )
    packet = _observe(
        tmp_path,
        MakeShellDeclarations(
            make_paths=("Makefile",),
            shell_paths=("demo.sh",),
        ),
    )
    assert not marker.exists()
    assert (
        _values(packet, "make-include-declaration")[0]["included_contents"]
        == "not-observed"
    )
    unresolved = _values(packet, "shell-unresolved-statement")
    assert len(unresolved) == 3
    assert all(row["execution"] == "not-established" for row in unresolved)
    commands = _values(packet, "shell-command-expression")
    assert all("macro-data-not-a-command" not in row["expression"] for row in commands)
    sourced = next(row for row in commands if row["expression"] == "source external.sh")
    assert sourced["sourced_file_contents"] == "not-observed"


@pytest.mark.parametrize("make", [False, True])
def test_heredoc_data_never_becomes_commands(tmp_path: Path, make: bool) -> None:
    source = "cat <<EOF\nnot-a-command\nEOF\necho later\n"
    path = "Makefile" if make else "demo.sh"
    if make:
        source = "all:\n" + "".join(
            "\t" + line for line in source.splitlines(keepends=True)
        )
    _write(tmp_path, path, source)
    provider = (
        MakeShellDeclarations(make_paths=(path,))
        if make
        else MakeShellDeclarations(shell_paths=(path,))
    )
    packet = _observe(tmp_path, provider)
    assert _values(packet, "shell-command-expression") == []
    assert len(_values(packet, "shell-unresolved-statement")) == 1
    assert all(
        group["absence"]["state"] == "unknown"
        for group in packet["declarations"]["groups"]
    )


def test_explicit_empty_and_missing_source_preserve_unknown_coverage(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "empty.sh", "# only a comment\n")
    packet = _observe(
        tmp_path, MakeShellDeclarations(shell_paths=("empty.sh", "missing.sh"))
    )
    assert packet["declarations"]["groups"] == []
    provenance = packet["providers"][0]["provenance"]
    assert provenance["missing_selected_paths"] == ["missing.sh"]
    assert provenance["negative_evidence_admissible"] is False


def test_changed_source_requires_refresh_and_updates_existing_delta(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "demo.sh", "echo before\n")
    provider = MakeShellDeclarations(shell_paths=("demo.sh",))
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        before = codemap.declarations.discover([provider])
        _write(tmp_path, "demo.sh", "echo after\n")
        with pytest.raises(RepositoryDeclarationProviderError):
            codemap.declarations.discover([provider])
        codemap.index.sync(["demo.sh"])
        after = codemap.declarations.discover([provider], previous_observation=before)
    assert after["observation_identity"] != before["observation_identity"]
    assert _values(after, "shell-command-expression")[0]["literal_argv"] == [
        "echo",
        "after",
    ]
    delta = cast("dict", after["delta_from_previous"])["declarations"]
    assert delta["changed_groups"][0]["value_changed_declaration_ids"] == [
        "selected-source-syntax"
    ]


@pytest.mark.parametrize(
    "source",
    [
        "echo " + "arg " * MAX_STATEMENT_WORDS,
        "#" * (MAX_MAKE_SHELL_BYTES + 1),
        "echo 'multiline\nstring'\n",
    ],
)
def test_bounds_and_unsupported_quoting_fail_without_partial_evidence(
    tmp_path: Path,
    source: str,
) -> None:
    _write(tmp_path, "demo.sh", source)
    with pytest.raises(RepositoryDeclarationProviderError):
        _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"make_paths": ("../outside",)},
        {"make_paths": ("Makefile",), "shell_paths": ("Makefile",)},
        {"shell_paths": tuple(f"{index}.sh" for index in range(17))},
    ],
)
def test_selected_scope_is_explicit_canonical_and_bounded(options: dict) -> None:
    with pytest.raises(ValueError):
        MakeShellDeclarations(**options)
