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
    MAX_MAKE_SHELL_FACTS,
    MAX_STATEMENT_CHARS,
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
    assert len(unresolved) == 2
    assert all(row["execution"] == "not-established" for row in unresolved)
    array = _values(packet, "shell-array-declaration")[0]
    assert [word["literal"] for word in array["elements"]] == ["first", "second"]
    assert array["effective_value"] == "not-established"
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


def test_make_indirection_is_conditional_static_words_not_execution(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "Makefile",
        (
            "RUNNER := python # comment\n"
            "TOOL = $(RUNNER)\n"
            "check: fixture.txt\n"
            '\t@MODE="sample" $(TOOL) -m demo\n'
        ),
    )
    packet = _observe(tmp_path, MakeShellDeclarations(make_paths=("Makefile",)))
    command = _values(packet, "shell-command-expression")[0]
    observation = command["static_binding_observation"]
    assert command["literal_argv"] is None
    assert command["make_targets"] == ["check"]
    assert observation["state"] == "conditional-static"
    assert observation["words"] == ["python", "-m", "demo"]
    assert [row["name"] for row in observation["supporting_declarations"]] == [
        "RUNNER",
        "TOOL",
    ]
    assert [row["start_line"] for row in observation["supporting_declarations"]] == [
        1,
        2,
    ]
    assert command["command_local_environment"][0]["value_expression"]["literal"] == (
        "sample"
    )
    assert observation["effective_command"] == "not-established"
    assert command["execution"] == "not-established"
    assert observation["negative_evidence_admissible"] is False
    assert packet["providers"][0]["provenance"]["semantics"] == (
        "hashmarks.make-shell-syntax.v4"
    )


def test_shell_indirection_uses_only_prior_top_level_single_atoms(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "demo.sh",
        ("RUNNER=python\nTOOL=\"$RUNNER\"\n\"$TOOL\" -m demo\nprintf '%s' '$RUNNER'\n"),
    )
    packet = _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))
    commands = _values(packet, "shell-command-expression")
    conditional = commands[0]["static_binding_observation"]
    assert conditional["state"] == "conditional-static"
    assert conditional["words"] == ["python", "-m", "demo"]
    assert commands[0]["literal_argv"] is None
    assert commands[1]["literal_argv"] == ["printf", "%s", "$RUNNER"]
    assert commands[1]["static_binding_observation"]["state"] == "not-needed"


@pytest.mark.parametrize(
    ("source", "make"),
    [
        ('RUNNER=first\nRUNNER=second\n"$RUNNER" arg\n', False),
        ('A=$B\nB=$A\n"$A" arg\n', False),
        ('RUNNER=python\nsource external.sh\n"$RUNNER" arg\n', False),
        (
            'RUNNER=python\nif condition; then\n  RUNNER=other\nfi\n"$RUNNER" arg\n',
            False,
        ),
        ("RUNNER := python\nRUNNER := other\nall:\n\t$(RUNNER) arg\n", True),
        ("A = $(B)\nB = $(A)\nall:\n\t$(A) arg\n", True),
        ("RUNNER := python\ninclude override.mk\nall:\n\t$(RUNNER) arg\n", True),
        (
            "RUNNER := python\nSIDE := $(eval RUNNER := evil)\nall:\n\t$(RUNNER) arg\n",
            True,
        ),
        (
            'RUNNER=python\nmutate() { RUNNER=evil; }\n"$RUNNER" arg\n',
            False,
        ),
        ("RUNNER ?= python\nall:\n\t$(RUNNER) arg\n", True),
        ("RUNNER := python\nall: RUNNER=other\n\t$(RUNNER) arg\n", True),
    ],
)
def test_static_binding_unknown_with_ambiguous_or_dynamic_source(
    tmp_path: Path, source: str, make: bool
) -> None:
    path = "Makefile" if make else "demo.sh"
    _write(tmp_path, path, source)
    provider = (
        MakeShellDeclarations(make_paths=(path,))
        if make
        else MakeShellDeclarations(shell_paths=(path,))
    )
    packet = _observe(tmp_path, provider)
    commands = _values(packet, "shell-command-expression")
    if commands:
        assert all(
            row["static_binding_observation"]["state"] != "conditional-static"
            for row in commands
        )


def test_multiword_make_fragment_is_conditional_source_not_effective_argv(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "Makefile",
        "TOOL = python -m unsafe\nall:\n\t$(TOOL) demo\n",
    )
    packet = _observe(tmp_path, MakeShellDeclarations(make_paths=("Makefile",)))
    command = _values(packet, "shell-command-expression")[0]
    observed = command["static_binding_observation"]
    assert observed["state"] == "conditional-source"
    assert observed["words"] == ["python", "-m", "unsafe", "demo"]
    assert "authored-make-word-fragment-only" in observed["conditions"]
    assert observed["effective_command"] == observed["execution"] == "not-established"
    assert observed["negative_evidence_admissible"] is False
    assert command["literal_argv"] is None


@pytest.mark.parametrize("value", ['"two words"', '""', ""])
def test_non_atom_make_values_do_not_acquire_single_atom_qualification(
    tmp_path: Path, value: str
) -> None:
    _write(tmp_path, "Makefile", f"TOOL = {value}\ncheck:\n\t$(TOOL) selected\n")
    packet = _observe(tmp_path, MakeShellDeclarations(make_paths=("Makefile",)))
    observed = _values(packet, "shell-command-expression")[0][
        "static_binding_observation"
    ]
    assert observed["state"] == "conditional-source"
    assert observed["effective_command"] == observed["execution"] == "not-established"


def test_nested_make_command_fragments_keep_unknown_environment_and_default_conditions(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "Makefile",
        "SHELL := bash\nSCRIPT ?= scripts/check.sh\n"
        "LAUNCH = $(SHELL) $(SCRIPT)\n"
        'FRONT = LOG_DIR="$(UNSUPPLIED)" $(LAUNCH)\n'
        "check:\n\t@$(FRONT) selected\n",
    )
    packet = _observe(tmp_path, MakeShellDeclarations(make_paths=("Makefile",)))
    command = _values(packet, "shell-command-expression")[0]
    observed = command["static_binding_observation"]
    assert observed["state"] == "conditional-source"
    assert observed["words"] == ["bash", "scripts/check.sh", "selected"]
    assert "make-variable-not-already-defined" in observed["conditions"]
    environment = observed["command_local_environment"]
    assert environment[0]["name"] == "LOG_DIR"
    assert environment[0]["value_expression"]["state"] == "unresolved-expansion"
    assert environment[0]["value_expression"]["literal"] is None
    assert {row["name"] for row in observed["supporting_declarations"]} == {
        "SHELL",
        "SCRIPT",
        "LAUNCH",
        "FRONT",
    }
    assert observed["effective_command"] == "not-established"
    assert command["literal_argv"] is None


def test_shell_arrays_preserve_elements_without_splitting_quoted_scalars(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "demo.sh",
        'TOOLS=(runner "two words")\n"${TOOLS[@]}" selected\n'
        'SCALAR="runner two words"\n"$SCALAR" selected\n"$TOOLS" selected\n"${TOOLS[*]}" selected\n',
    )
    packet = _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))
    array, scalar, unsupported_scalar_array, joined_array = _values(
        packet, "shell-command-expression"
    )
    assert array["static_binding_observation"]["words"] == [
        "runner",
        "two words",
        "selected",
    ]
    assert scalar["static_binding_observation"]["words"] == [
        "runner two words",
        "selected",
    ]
    assert (
        unsupported_scalar_array["static_binding_observation"]["state"]
        == "unclassified"
    )
    assert array["literal_argv"] is scalar["literal_argv"] is None
    assert joined_array["static_binding_observation"]["state"] == "unclassified"
    assert array["static_binding_observation"]["execution"] == "not-established"


def test_helper_arguments_are_separate_conditional_source_invocations(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "demo.sh",
        'run() {\n  local tool="$1"\n  local action="$2"\n'
        '  "$tool" "$action" "$3"\n}\n'
        "run first inspect 'one; inert'\nrun second check other\nrun \"$EXTERNAL\" check other\n",
    )
    packet = _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))
    body = _values(packet, "shell-command-expression")[0]
    assert body["static_binding_observation"]["state"] == "unclassified"
    invocations = body["invocation_binding_observation"]
    assert invocations["max_helper_edges"] == 1
    first, second, unknown = invocations["candidates"]
    assert first["observation"]["words"] == ["first", "inspect", "one; inert"]
    assert second["observation"]["words"] == ["second", "check", "other"]
    assert unknown["observation"]["state"] == "unclassified"
    assert first["invocation_site"]["start_line"] == 6
    assert second["invocation_site"]["start_line"] == 7
    assert (
        "one-observed-source-invocation-not-all-callers"
        in first["observation"]["conditions"]
    )
    assert first["observation"]["effective_command"] == "not-established"
    assert invocations["negative_evidence_admissible"] is False


def test_function_local_names_do_not_merge_across_source_scopes(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "demo.sh",
        'first() {\n local tool=alpha\n "$tool" inspect\n}\n'
        'second() {\n local tool=beta\n "$tool" check\n}\n',
    )
    packet = _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))
    first, second = _values(packet, "shell-command-expression")
    assert first["static_binding_observation"]["words"] == ["alpha", "inspect"]
    assert second["static_binding_observation"]["words"] == ["beta", "check"]
    assert (
        "source-context-applies:function:first:1"
        in first["static_binding_observation"]["conditions"]
    )
    assert (
        "source-context-applies:function:second:5"
        in second["static_binding_observation"]["conditions"]
    )


def test_authored_shell_fallback_does_not_claim_the_ambient_value(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "demo.sh", 'TOOL="${EXTERNAL:-fallback}"\n"$TOOL" inspect\n')
    packet = _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))
    observed = _values(packet, "shell-command-expression")[0][
        "static_binding_observation"
    ]
    assert observed["state"] == "conditional-source"
    assert observed["words"] == ["fallback", "inspect"]
    assert "parameter-unset-or-empty" in observed["conditions"]
    assert "parameter-present-branch-unobserved" in observed["conditions"]
    assert observed["effective_command"] == "not-established"
    assert observed["negative_evidence_admissible"] is False


def test_recursive_and_multihop_helpers_are_not_expanded_into_execution(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "demo.sh",
        'second() { "$1" "$2"; }\n'
        'first() { second "$1" "$2"; first "$1" next; }\n'
        "first runner inspect\n",
    )
    packet = _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))
    commands = _values(packet, "shell-command-expression")
    second = commands[0]["invocation_binding_observation"]
    assert second["candidates"][0]["observation"]["state"] == "unclassified"
    recursive = commands[1]["invocation_binding_observation"]["candidates"][0]
    assert recursive["observation"]["reason"] == "recursive-helper-edge-not-interpreted"


def test_file_projection_retains_more_than_legacy_group_bound_without_absence_claims(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "demo.sh", "".join(f"echo value{index}\n" for index in range(160)))
    with pytest.raises(RepositoryDeclarationProviderError):
        _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))
    packet = _observe(
        tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",), layout="file")
    )
    group = _groups(packet, "make-shell-file-observation")[0]
    observation = group["declarations"][0]["value"]
    assert len(packet["declarations"]["groups"]) == 1
    assert observation["observed_fact_count"] == len(observation["facts"]) == 160
    assert observation["facts_truncation"] == "not-truncated"
    assert observation["facts"][159]["start_line"] == 160
    assert observation["facts"][159]["value"]["literal_argv"] == ["echo", "value159"]
    assert observation["negative_evidence_admissible"] is False
    assert (
        _evidence(packet, group)[0]["member_revision"]
        == packet["providers"][0]["inputs"][0]["member_revision"]
    )


def test_file_projection_marks_unsupported_remaining_source_explicitly(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "demo.sh", "cat <<EOF\nnot-a-command\nEOF\necho unobserved\n")
    packet = _observe(
        tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",), layout="file")
    )
    observation = _values(packet, "make-shell-file-observation")[0]
    assert observation["facts_completeness"] == "incomplete"
    assert observation["remaining_source"] == "not-observed"
    assert observation["facts_truncation"] == "not-truncated"
    assert observation["negative_evidence_admissible"] is False


def test_file_projection_source_fact_limit_refuses_without_a_prefix(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "demo.sh", "echo source\n" * (MAX_MAKE_SHELL_FACTS + 1))
    with pytest.raises(RepositoryDeclarationProviderError):
        _observe(
            tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",), layout="file")
        )


def test_long_bounded_authored_statement_remains_source_only(tmp_path: Path) -> None:
    literal = "x" * 8_300
    _write(tmp_path, "demo.sh", "printf '%s' '" + literal + "'\n")
    packet = _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))
    assert _values(packet, "shell-command-expression")[0]["literal_argv"] == [
        "printf",
        "%s",
        literal,
    ]
    _write(tmp_path, "demo.sh", "echo '" + "x" * MAX_STATEMENT_CHARS + "'\n")
    with pytest.raises(RepositoryDeclarationProviderError):
        _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))


def test_dotted_make_assignments_are_not_invented_target_declarations(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "Makefile",
        ".DEFAULT_GOAL := check\nLOCAL.TOOL := runner\ncheck:\n\t$(LOCAL.TOOL) inspect\n",
    )
    packet = _observe(tmp_path, MakeShellDeclarations(make_paths=("Makefile",)))
    assert [row["name"] for row in _values(packet, "make-variable-declaration")] == [
        ".DEFAULT_GOAL",
        "LOCAL.TOOL",
    ]
    assert [row["targets"] for row in _values(packet, "make-target-declaration")] == [
        ["check"]
    ]
    assert _values(packet, "shell-command-expression")[0]["static_binding_observation"][
        "words"
    ] == ["runner", "inspect"]


def test_uninterpreted_recipe_tail_does_not_rewrite_make_source_bindings(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "Makefile",
        "TOOL := runner\nother:\n\tprintf x >/dev/null\ncheck:\n"
        '\t@test -x "$(TOOL)" || { printf unavailable >&2; exit 2; }\n'
        "\t$(TOOL) inspect\n",
    )
    packet = _observe(tmp_path, MakeShellDeclarations(make_paths=("Makefile",)))
    unresolved = _values(packet, "shell-unresolved-statement")
    assert len(unresolved) == 2
    prefix, command = _values(packet, "shell-command-expression")
    assert prefix["prefix_of_uninterpreted_statement"] is True
    assert prefix["static_binding_observation"]["words"] == ["test", "-x", "runner"]
    assert (
        "source-context-applies:uninterpreted-remainder:5"
        in prefix["static_binding_observation"]["conditions"]
    )
    assert command["static_binding_observation"]["words"] == ["runner", "inspect"]
    assert (
        command["static_binding_observation"]["effective_command"] == "not-established"
    )


def test_candidate_fanout_refuses_before_unbounded_word_accumulation(
    tmp_path: Path,
) -> None:
    aliases = ["A0 = first second"]
    aliases.extend(
        f"A{index} = $(A{index - 1}) $(A{index - 1})" for index in range(1, 8)
    )
    _write(tmp_path, "Makefile", "\n".join((*aliases, "check:", "\t$(A7) $(A7)")))
    with pytest.raises(RepositoryDeclarationProviderError):
        _observe(tmp_path, MakeShellDeclarations(make_paths=("Makefile",)))


def test_file_layout_preserves_the_shared_result_byte_limit(tmp_path: Path) -> None:
    _write(tmp_path, "demo.sh", "echo source\n" * 3_000)
    with pytest.raises(ValueError, match="groups exceeds .* encoded bytes"):
        _observe(
            tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",), layout="file")
        )


def test_invocation_cannot_retroactively_bind_an_earlier_scalar_assignment(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "demo.sh",
        'run() { "$TOOL" inspect; }\nTOOL="$LATER"\nLATER=runner\nrun\n',
    )
    packet = _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))
    body = _values(packet, "shell-command-expression")[0]
    invocation = body["invocation_binding_observation"]["candidates"][0]
    assert invocation["observation"]["state"] == "unclassified"
    assert body["literal_argv"] is None


def test_one_helpers_arguments_cannot_bind_another_helpers_global_assignment(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "demo.sh",
        'g() {\n x="$1"\n}\nf() {\n echo "$x"\n}\nf wrong\n',
    )
    packet = _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))
    body = _values(packet, "shell-command-expression")[0]
    invocation = body["invocation_binding_observation"]["candidates"][0]
    assert invocation["observation"]["state"] == "unclassified"


@pytest.mark.parametrize(
    "word,expected", [('"$10"', None), ('"${10}"', "ten"), ('"$*"', None)]
)
def test_positional_source_forms_do_not_invent_native_word_boundaries(
    tmp_path: Path, word: str, expected: str | None
) -> None:
    _write(
        tmp_path,
        "demo.sh",
        f"run() {{ echo {word}; }}\nrun one two three four five six seven eight nine ten\n",
    )
    packet = _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))
    body = _values(packet, "shell-command-expression")[0]
    observed = body["invocation_binding_observation"]["candidates"][0]["observation"]
    if expected is None:
        assert observed["state"] == "unclassified"
    else:
        assert observed["words"] == ["echo", expected]
        assert observed["execution"] == "not-established"


@pytest.mark.parametrize("after", [False, True])
@pytest.mark.parametrize("loop", ["for", "select"])
def test_loop_target_write_prevents_reuse_of_an_old_unique_binding(
    tmp_path: Path, after: bool, loop: str
) -> None:
    source = f"TOOL=first\n{loop} TOOL in second; do\n"
    source += " :\n" if after else ' "$TOOL" action\n'
    source += "done\n" + ('"$TOOL" action\n' if after else "")
    _write(tmp_path, "demo.sh", source)
    packet = _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))
    command = next(
        row
        for row in _values(packet, "shell-command-expression")
        if row["expression"].endswith("action")
    )
    assert command["static_binding_observation"]["state"] == "unclassified"
    write = _values(packet, "shell-binding-write")[0]
    assert write["name"] == "TOOL" and write["effective_value"] == "not-established"


@pytest.mark.parametrize("mutation", ["shift", "set -- changed"])
def test_positional_mutation_is_not_interpreted_as_the_original_caller_arguments(
    tmp_path: Path, mutation: str
) -> None:
    _write(
        tmp_path,
        "demo.sh",
        f'run() {{\n {mutation}\n echo "$1"\n}}\nrun first second\n',
    )
    packet = _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))
    body = next(
        row
        for row in _values(packet, "shell-command-expression")
        if row["expression"].startswith("echo")
    )
    assert (
        body["invocation_binding_observation"]["candidates"][0]["observation"]["state"]
        == "unclassified"
    )


@pytest.mark.parametrize("loop", ["for", "select"])
def test_loop_target_also_invalidates_function_local_source_bindings(
    tmp_path: Path, loop: str
) -> None:
    _write(
        tmp_path,
        "demo.sh",
        f'run() {{\n local TOOL=first\n {loop} TOOL in second; do\n :\n done\n "$TOOL" action\n}}\nrun\n',
    )
    packet = _observe(tmp_path, MakeShellDeclarations(shell_paths=("demo.sh",)))
    body = next(
        row
        for row in _values(packet, "shell-command-expression")
        if row["expression"].endswith("action")
    )
    assert body["static_binding_observation"]["state"] == "unclassified"
    assert (
        body["invocation_binding_observation"]["candidates"][0]["observation"]["state"]
        == "unclassified"
    )
