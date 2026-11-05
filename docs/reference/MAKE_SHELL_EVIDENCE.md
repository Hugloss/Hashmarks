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
| Make target | Literal target names, prerequisite expression and plain literal prerequisite tokens with order-only syntax |
| Tab-prefixed Make recipe | Physical recipe span, associated target names, `@`/`+`/`-` prefixes after leading whitespace and supported command expressions |
| Shell variable or alias assignment | Declared name, quote-preserving expression and literal value when the small lexical subset permits it |
| Indexed shell array declaration | Authored element words and scope, without asserting effective array state |
| Braced shell function | Declaration name and source context for supported body statements |
| Simple command statement | Word expressions, constant-word projections, command-local environment assignments and preceding source separator |
| Named variable reference | Reference spelling and source declaration candidates with their physical sites and contexts |
| Literal function/alias invocation spelling | Same-file function/alias declaration candidates, with command binding unestablished |
| Simple quoted shell heredoc delimiter | Opaque data extent with exact UTF-8 byte ranges, never command candidates from the data |
| Make include or shell `source`/`.` expression | The source expression and the fact that included contents were not observed |

`literal_argv` is a lexical projection available only when every command word is
literal under this subset. Individual `words` remain available when another
word contains expansion. This field is source evidence; it is not an executable
plan, command recommendation or guarantee of the executable that would run.

`literal_prerequisite_tokens` preserves source order and duplicates for the small
plain-word Make prerequisite subset, including each token's position before or
after the authored order-only `|` separator. Expansions, escaping, globbing,
patterns, inline recipes, assignments and multiple separators leave that field
unavailable (`null`) while retaining the original expression. These are authored
tokens, never effective prerequisites or proof that any target executes.

For one explicitly selected Make file, Python callers may request
`MakeShellDeclarations(make_paths=("Makefile",), layout="file",
selected_targets=("check",))`. The intact file observation additionally carries
`selected_target_source`, a bounded source relationship projection. It retains
the exact target request and a separate `by_target` projection for each requested
name, reusing the one parsed file. Each projection retains authored literal prerequisite edges (including duplicate
occurrences), declaration fact indices, associated recipe/source fact indices,
source paths, observed cycles and unresolved prerequisites/source statements.
Consumers need not rebuild that source graph. A prerequisite without a target
declaration in this selected file remains unresolved; this does not establish
that a prerequisite file is absent. Includes and unobserved native expansion
cannot supply invented edges. This projection never selects effective Make work,
computes tools, decides closure sufficiency, chooses a branch, or executes work.

All requested targets share one operation-local projection budget: 1,000,000
work units, 65,536 copied path members and 2 MiB of encoded dynamic projection
payload. Traversal and target-index work, retained prerequisite/unknown rows,
internal path tuples and emitted target/candidate paths reserve their budget
before accumulation or copying. Target-name input shares the selected-source
256 KiB bound. Fixed request/status metadata remains bounded by that input and
the 64-target limit. `selected_target_source.projection_budget` records the
shared limits, consumption and exhausted dimension. Exhaustion leaves each
affected target's `source_truncation: stopped` and an unresolved
`selected-target-projection-budget-exhausted` reason. Observed prefixes remain
source evidence; omitted targets/candidates never become absence, effective
selection, or sufficient closure. Full-file parsing qualifications remain
separate from selected-projection truncation.

Single quotes, double quotes, escaped literal characters and backslash line
continuations are supported for simple statements. Multiline quoted shell words
are captured with the same incremental quote state, retaining their literal
newlines and physical source extent within the existing statement bound.
Separators inside quoted
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
bounded candidate derivation retains its exact supporting declarations; it never establishes an effective native binding.

## Conditional authored binding candidates

The `hashmarks.make-shell-syntax.v5` producer retains the existing
`static_binding_observation`. `state="conditional-static"` continues to name
simple source indirection. Broader supported forms use
`state="conditional-source"`: multiword Make fragments, `?=` authored defaults,
function-scoped scalar/array declarations and simple shell fallback expressions.
Their `words` are source candidates, not effective argv. `conditions`,
`source_features`, `supporting_declarations` and source-shaped
`command_local_environment` retain the limitations of that projection.
Unknown environment values stay unresolved even when adjacent command words
have a conditional source candidate.

An unobserved `source`, dynamic namespace operation or unsupported statement
does not erase independent authored declaration/use syntax. Such candidates
explicitly require the authored declarations to take effect, with no intervening
rebinding or readonly conflict; unobserved source state may change bindings.
These are conditional source relationships, never effective expansion or command
binding. Known conflicting declarations still prevent a unique candidate.

`logical_offset` retains the existing tokenizer's zero-based character position
inside the logical source line; physical start/end lines still bind continuations.
This preserves the order of semicolon-separated declarations and uses without
inventing a value from a later shell assignment. Inline function bodies retain
their original lexical offsets. Recursive Make source references (`=` and the
conditional `?=` fallback) may refer to later authored declarations, with native
evaluation time explicitly unestablished. Immediate Make assignments do not
borrow a later definition.

Same-line control delimiters bound lexical context only. A completed
`if ...; then ...; fi` does not add a condition to every later statement, while
nested unclosed controls remain in the source context. Quoted keywords and
command arguments do not close a context. Bodies, branch results, heredoc data
and execution remain uninterpreted; context balance supplies no negative proof.

If any command word remains unresolved, the whole observation stays
`state="unclassified"` and has no `words` value. `authored_words` may retain
literal source candidates beside intact unresolved `source_word` expressions.
An alias or array may transport an opaque source expression without evaluating
it; an unknown interpreter, substitution or path never becomes a synthetic
runtime value. This partial view is emitted only when the complete word
candidate is unavailable and retains the same word, support and packet bounds.
`authored_environment_bindings` similarly retains authored export sites and
conditional declaration/use evidence, without observing the effective or
ambient process environment. Imports from sourced files remain unobserved.

A `?=` candidate is conditional on the variable not already being defined;
Hashmarks does not inspect the ambient environment or select the default.
`${NAME:-fallback}` and `${NAME-fallback}` retain the authored fallback's
unset/empty condition and explicitly leave the variable-present branch
unobserved. A quoted scalar containing spaces remains one source value; it
is never split into executable words. Indexed array element observations do
not establish effective array contents or support scalar/associative array
semantics. Native Make expansion, Bash field splitting/globbing and external
overrides remain outside these observations.

Function-body commands may additionally carry
`invocation_binding_observation`. Each candidate preserves one observed literal
helper invocation, its argument expressions and physical site, together with
conditional positional-source observations for that body. Separate callers
stay separate; one caller does not specialize every invocation. Recursive,
ambiguous and multi-edge helper flows remain unclassified. The observation
carries a one-edge and 64-candidate bound and cannot select or launch work.
Arguments are transported only within the exact matching authored function
context. A foreign function's assignment cannot borrow another caller's
parameters, and a later declaration cannot retroactively fill an earlier
scalar assignment. Bare multi-digit forms such as `$10` remain unresolved;
braced `${10}` may identify parameter ten. `$*` and `${ARRAY[*]}` joining remain
unclassified because IFS/native joining is not observed. Potential `shift` or
`set` positional writes withdraw the function's argument mapping rather than
interpreting the mutation.

`for`/`select` targets are opaque namespace-write observations. They invalidate
an old unique binding inside and after the loop, including a function-local
binding. No iteration value or runtime loop behavior is selected.

For a larger selected file, Python callers may request
`MakeShellDeclarations(shell_paths=("scripts/demo.sh",), layout="file")`.
A `make-shell-file-observation` group retains each fact's kind, physical lines
and original source value under `value.facts`; it uses the same parser and
binding owner as the default group layout. The whole selected member revision
binds this view. `facts_completeness="complete-supported-subset"` never means
complete semantics. A stopped here-document observation explicitly retains
`facts_completeness="incomplete"` and `remaining_source="not-observed"`.
No empty, bounded or stopped result grants negative evidence.

Literal dotted Make variable names, including special-variable spelling, remain
assignments rather than invented target declarations. Unsupported recipe-local
shell syntax stays attached to that recipe; it does not establish or overwrite
an unrelated Make variable's authored value. Includes and dynamic binding
mutators still prevent a closed candidate derivation.

When a simple leading command precedes an uninterpreted `&&`/`||` remainder,
the provider may retain that prefix separately with
`prefix_of_uninterpreted_statement=true` and an explicit source context.
The original unresolved full statement also remains. This does not interpret
the remainder, establish a branch result, or recover invocations from a
here-document, command substitution or backticks.

## Unsupported syntax and coverage

The subset deliberately does not implement a Make or shell interpreter. Command
substitution, backticks, associative/index-mutated arrays, arithmetic,
redirections, `eval`, source loading,
Make functions, inline Make recipes, target-specific assignments and effective
external overrides remain unresolved or uninterpreted source expressions.
Simple line-oriented conditional/function contexts are retained; general
compound-language interpretation remains outside this provider.
Unsupported statement facts retain the original raw expression and the existing
tokenizer's comment-free `token_expressions`. Quoted comment characters remain
data; the token projection does not establish command or control execution.

Make `define` bodies are uninterpreted macro source. A custom `.RECIPEPREFIX`
prevents later tabbed lines from being promoted to established recipes.
Escaped target names and target patterns remain unresolved; their following
recipes do not acquire invented literal target names.
A shell heredoc with one simple quoted identifier delimiter, such as
`<<'PAYLOAD'`, retains an opaque `shell-heredoc-data` fact. The body and terminator
have exact half-open UTF-8 byte ranges in the original selected member. Body
lines bypass command, quote and control interpretation, including command-like
text and unmatched quotes; observation resumes only after the exact literal
terminator. No effective input, command execution or branch result is claimed.
Unquoted, dynamic, multiple and tab-stripping delimiters remain outside this
subset and stop observation for the rest of the file. A missing terminator
retains an unterminated data extent and incomplete remaining-source coverage.
The distinct `<<<` here-string operator remains uninterpreted input on its
source line and does not consume later statements as heredoc data. Heredoc
framing uses physical LF boundaries; Unicode line-separator data cannot invent
a terminator.
Shell token boundaries use space, tab and LF. Other whitespace code points
remain authored word data; a quoted identifier followed by CR or Unicode word
data is an unsupported composite delimiter, never shortened into a supported
one. Make's CRLF source-line transport is normalized separately before recipe
lexing. Source coordinates still refer to the original captured member.
Malformed/unclosed quotes and exceeded source, statement or data-line bounds
refuse the observation rather than returning an apparently complete prefix.

Bounds are 16 selected files across both languages, 262,144 bytes per file,
16,384 characters per logical statement, 256 tokens per statement and the
existing 128 declaration-group limit. The explicit Python `layout="file"`
projection instead retains up to 4,096 facts in one group per selected file,
without raising the shared declaration-group or one-MiB result limits.
Candidate composition is bounded to 256 words and 2,048 supporting declaration
references; invocation and accumulated binding metadata retain the same
one-MiB evidence bound. Existing declaration request/result byte bounds also
apply. Exceeding a bound fails the call; it never produces an apparently
complete prefix.

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
repository-supplied provider code is never loaded by this selector.

### CLI

The existing declaration-discovery command accepts repeatable source paths:

```sh
hashmarks --workspace /repo repository-declarations \
  --make-path Makefile --shell-path scripts/demo.sh --shell-path scripts/other.sh
```

Alternatively, `--source-selection-json selection.json` reads the same inner
`source_selection` object shown above. It can combine this provider with other
registered providers. JSON selection and source-selection flags are mutually
exclusive. An explicit empty JSON object selects no providers; a supplied
`--previous-observation previous.json` remains comparison input and cannot
restore old selections. The normal evidence-presentation options remain available.

### CodeMap service

With the existing CodeMap service running for the workspace:

```python
from hashmarks.codemap import CodeMapServiceClient

client = CodeMapServiceClient("/repo")
observation = client.repository_declarations(
    [],
    result_mode="discovery",
    source_selection={
        "make_shell": {
            "make_paths": ["Makefile"],
            "shell_paths": ["scripts/demo.sh"],
        }
    },
)
```

CLI, MCP and service discovery all delegate to the same selector and
`RepositoryDeclarations.operation()`. The service retains its existing warm
CodeMap, request/response limits and explicit `sync()` behavior. Stale inputs
cannot become current through transport; previous packets remain explicit
comparison inputs. No transport accepts provider import paths or executes
repository-supplied Python providers.

### Standalone example

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
Observed repository fact/evidence: Selected Make/shell declarations, invocation expressions, literal words, conditional scoped word candidates, one-edge invocation provenance and physical source-reference candidates.
Authority source: Explicit admitted source bytes read through RepositoryDeclarationProviderContext.
Completeness/freshness behavior: Supported syntax only; semantic coverage remains incomplete; bounds fail closed; existing discovery revalidates member revisions.
Existing Hashmarks owner extended: Source and RepositoryDeclarations, through an explicit syntax provider and the existing selector adapter.
Consumer/execution responsibility explicitly not acquired: Effective native evaluation, executable/environment policy, execution, scheduling, retries and result authority.
Decision: OBSERVER
```
