# Selected Make and shell source evidence

**Status: public explicit declaration provider.**

`MakeShellDeclarations` observes a bounded subset of caller-selected Make and
shell files. It reports declarations, command expressions and physical source
origins through the existing [repository declaration contract](REPOSITORY_DECLARATIONS.md).
Every result describes source syntax. Effective expansion, the environment,
command binding and whether a command executes remain unestablished.

## Public Python usage

```python
from hashmarks.codemap import CodeMap, MakeShellDeclarations

with CodeMap(".") as repository:
    repository.index.sync()
    evidence = repository.declarations.discover(
        [
            MakeShellDeclarations(
                make_paths=("Makefile", "build/common.mk"),
                shell_paths=("scripts/demo.sh",),
            )
        ]
    )
```

The caller explicitly assigns each path to Make or shell syntax. The provider
accepts canonical repository-relative paths and reads only through
`RepositoryDeclarationProviderContext`. Source admission, visibility, member
revision, currentness and input revalidation retain their existing owners.

The returned schema is `hashmarks.repository-declaration-discovery.v1`. Provider
provenance and input revisions are under `providers`. Facts are under
`declarations.groups`; each normalized declaration's `binding_id` identifies
its exact evidence in `declarations.repository_evidence.bindings`.

For a subsequent observation, refresh the caller-reported changed paths and
provide the previous discovery packet explicitly:

```python
repository.index.sync(["scripts/demo.sh"])
current = repository.declarations.discover(
    [MakeShellDeclarations(shell_paths=("scripts/demo.sh",))],
    previous_observation=evidence,
)
changes = current["delta_from_previous"]
```

The old packet is comparison input. Current selection and current source alone
produce current declarations; old selections never restore facts.

## Observed source facts

| Source form | Observation |
| --- | --- |
| Make variable assignment | Name, authored value expression, assignment operator and `export`/`override`/`private` syntax |
| Make target | Literal target names and prerequisite expression |
| Tab-prefixed Make recipe | Physical recipe span, associated target names, `@`/`+`/`-` prefixes after leading whitespace and supported command expressions |
| Shell variable or alias assignment | Declared name, quote-preserving expression and literal value when the small lexical subset permits it |
| Braced shell function | Declaration name and source context for supported body statements |
| Simple command statement | Word expressions, constant-word projections, command-local environment assignments and preceding source separator |
| Named variable reference | Reference spelling and source declaration candidates with their physical sites and contexts |
| Literal function/alias invocation spelling | Same-file function/alias declaration candidates, with command binding unestablished |
| Make include or shell `source`/`.` expression | The source expression and the fact that included contents were not observed |

`literal_argv` is a lexical projection available only when every command word is
literal under this subset. Individual `words` remain available when another
word contains expansion. This field is source evidence; it is not an executable
plan, command recommendation or guarantee of the executable that would run.

Single quotes, double quotes, escaped literal characters and backslash line
continuations are supported for simple statements. Separators inside quoted
strings remain data. For example, `printf '%s' 'one; two'` is one command
expression, and `'$NAME'` is a literal shell word rather than a variable read.
Make recipe expansion is qualified separately: Make variable syntax inside
shell quotes can still be a Make reference.

Make `=`, `:=`, `?=` and `+=` retain their different operators. Other recognized
assignment operators are also retained as source text. The provider does not
collapse them into one effective value. Shell variable references support
`$NAME` and `${NAME}`; Make references support `$(NAME)` and `${NAME}`. Candidate
declarations retain their operators, order locations and source contexts.
Multiple same-named declarations remain multiple candidates. Source spelling
does not establish which candidate supplies an effective runtime value, and
the provider does not compose candidates into transitive alias resolution.

## Unsupported syntax and coverage

The subset deliberately does not implement a Make or shell interpreter. Command
substitution, backticks, arrays, arithmetic, redirections, `eval`, source loading,
Make functions, inline Make recipes, target-specific assignments and effective
external overrides remain unresolved or uninterpreted source expressions.
Simple line-oriented conditional/function contexts are retained; general
compound-language interpretation remains outside this provider.

Make `define` bodies are uninterpreted macro source. A custom `.RECIPEPREFIX`
prevents later tabbed lines from being promoted to established recipes.
Escaped target names and target patterns remain unresolved; their following
recipes do not acquire invented literal target names.
An encountered here-document stops command observation for the rest of that
selected file so body text cannot become invented invocations. Multiline quoted
shell strings outside the supported continuation subset and malformed quoting
fail the observation rather than yielding partial executable-looking facts.

Bounds are 16 selected files across both languages, 262,144 bytes per file,
8,192 characters per logical statement, 256 tokens per statement and the
existing 128 declaration-group limit. Existing declaration request/result byte
bounds also apply. Exceeding a bound fails the call; it never produces an
apparently complete prefix.

All groups retain incomplete semantic coverage and unresolved correspondence.
`value_state="resolved"` means the normalized **syntax observation** was
constructed; it does not mean variable expansion or native execution was
resolved. `execution="not-established"` and
`negative_evidence_admissible=false` make this distinction explicit. Missing
selected paths are reported in provenance. An empty result cannot establish
that the repository contains no commands or environment uses.

## MCP and example

The existing registered `repository_declarations` MCP tool accepts:

```json
{
  "groups": [],
  "result_mode": "discovery",
  "source_selection": {
    "make_shell": {
      "make_paths": ["Makefile"],
      "shell_paths": ["scripts/demo.sh"]
    }
  }
}
```

This uses the same built-in provider selector as direct adapter calls. Arbitrary
repository-supplied provider code is never loaded by this selector. Dedicated
CLI flags and service-client parity are not part of this provider addition.

The standalone [consumer example](../../examples/make_shell_declarations.py)
creates a neutral temporary repository, observes selected sources and a missing
path, changes one source as the external consumer, and compares observations.
With the Hashmarks project environment materialized, run:

```sh
uv run --frozen --no-sync python examples/make_shell_declarations.py
```

The example imports supported installed-package APIs. It does not execute any
observed command expression.

## Observer ownership note

```text
Observed repository fact/evidence: Selected Make/shell declarations, invocation expressions, literal words and physical source-reference candidates.
Authority source: Explicit admitted source bytes read through RepositoryDeclarationProviderContext.
Completeness/freshness behavior: Supported syntax only; semantic coverage remains incomplete; bounds fail closed; existing discovery revalidates member revisions.
Existing Hashmarks owner extended: Source and RepositoryDeclarations, through an explicit syntax provider and the existing selector adapter.
Consumer/execution responsibility explicitly not acquired: Effective native evaluation, executable/environment policy, execution, scheduling, retries and result authority.
Decision: OBSERVER
```
