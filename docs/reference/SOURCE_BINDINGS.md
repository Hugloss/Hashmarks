# Qualified source binding observations

`CodeMap.source.bindings()` observes declarations, references, authored import
bindings, bounded aliases and string values in one admitted Python, JavaScript
or TypeScript member. It qualifies source expressions against that member's
lexical scopes and records the evidence and conditions behind each observation.
The result never establishes a runtime object or call target.

The operation extends the existing Source owner. Source supplies canonical
member admission, stable bytes, revision and freshness. Python's native AST
owner and the configured ECMAScript syntax provider supply the syntax. The
binding interpreters consume that already admitted syntax and introduce no
tokenizer, second source reader, persistent binding graph or registry.

```python
from hashmarks import CodeMap

with CodeMap(".") as codemap:
    codemap.index.sync()
    observation = codemap.source.bindings("src/consumer.py", limit=200)
    if observation["availability"] == "observed":
        for fact in observation["facts"]:
            print(fact["kind"], fact["qualification"], fact["target"])
```

For syntax without binding interpretation, the existing
[`source.ecmascript()`](ECMASCRIPT_SOURCE_OBSERVATIONS.md) operation remains
available with its own schema and `semantic_resolution="not-performed"`
contract. Its syntax facts do not gain the qualification of this operation.

## Public surfaces

Schema: `hashmarks.source-bindings.v1`.

```python
source.bindings(
    relpath: str,
    *,
    limit: int = 200,
    max_bytes: int = 1_048_576,
) -> dict[str, object]
```

| Surface | Request |
| --- | --- |
| Python | `codemap.source.bindings("src/consumer.py", limit=200)` |
| CLI | `hashmarks source-observation src/consumer.py --result-mode bindings --limit 200` |
| MCP | `source_observation(paths=["src/consumer.py"], result_mode="bindings", limit=50)` |
| Service client | `client.source_bindings("src/consumer.py", limit=200)` |
| Service protocol | Operation `source_bindings`; payload fields `path`, optional `limit`, optional `max_bytes`; response key `source_bindings`. |

The CLI and MCP synchronize the selected member at their request boundary. The
service client transports the native Source result; consumers call
`client.sync()` when reconciliation is needed. All adapters preserve the
packet's qualifiers and identities. Optional CLI presentation wraps that same
packet without interpreting its source again.

Binding mode requires exactly one path. Literal selectors, byte-range selectors
and line-context selectors belong to the other source-observation modes and
are rejected. MCP retains its existing result limit of 50; the Python, CLI and
service surfaces use the core default of 200 and maximum of 500.

## What qualification means

The operation describes authored source origins. An import target names the
module and imported symbol written in this member. A local target identifies
a declaration in this member. A lexical-global target describes a source name
with no qualifying local declaration. These are neutral source descriptors;
they are not identities of loaded implementations or runtime objects.

An import target has `kind="import"`, `module`, `name`, relative-import `level`,
`properties` and `module_resolution="not-performed"`. `name` may be null: a
Python module import identifies the module without selecting an imported symbol.
ECMAScript namespace imports preserve `name="*"`; default imports preserve
`name="default"`. Consumers must preserve these language distinctions instead
of treating a null name as a missing packet. A local target has
`kind="declaration"`, `name`, exact `range` and `properties`. An ECMAScript
unbound-name descriptor uses `kind="lexical-global"`, `name`, `properties` and
`runtime_identity="not-established"`; unqualified Python names remain unknown.
Appended `properties` describe an authored property path without resolving it
to an implementation.

| `qualification` | Meaning |
| --- | --- |
| `qualified` | The supported source form and complete bounded lexical scope establish this authored source relationship. Runtime identity remains unestablished. |
| `conditional` | The supported relationship additionally depends on the listed conditions, such as a parameter's default being selected or an argument being passed to a local helper. |
| `unknown` | Source, lexical ambiguity, a mutable or unsupported binding, an unsupported expression, or an interpretation bound prevents the claimed relationship. Reasons are retained. |

`conditions` and `reasons` belong to the individual fact. Consumers must retain
them alongside `qualification`; a non-null `target` is not permission to drop
the conditions. Every fact carries `runtime_target="not-established"`.

The operation qualifies the complete bounded member before applying the
returned-fact limit. A later write, parameter shadow or same-scope declaration
cannot disappear semantically merely because it is outside the returned
prefix. Reassignment, unsupported binding patterns and dynamic behavior remain
unknown where they prevent a unique source relationship. This is conservative
source interpretation, not full dataflow, type analysis or execution simulation.

### Parameters, defaults and local helper calls

Consider a Python member:

```python
from subprocess import Popen as launch

runner = launch


def invoke(factory=runner):
    return factory(["example"])


invoke()
```

The import and direct alias can expose their authored origin. The default
expression can expose that origin in a separate conditional `default-binding`
fact. The call through `factory` remains unknown: a caller can supply another
value, and source syntax does not establish the function's runtime arguments.
The interpreter does not turn the default into a permanent parameter alias.

An admitted direct call to a local helper can produce a separate conditional
`argument-binding` fact. Its `parameter` and `call` locators identify the exact
parameter, call and callee behind the relationship. This does not rewrite every
use of that parameter, infer all callers, or traverse a call graph. At most one
local helper edge is interpreted. Mutable globals, rebinding and unsupported
call shapes cannot be promoted into runtime target certainty.

### Strings and computed properties

The interpreters may qualify bounded supported string expressions and use a
qualified string as a computed-property key. A literal value is derived from
the complete admitted expression, not its display preview. Python string values
and escapes come from the native AST; supported literal concatenations may be
interpreted. ECMAScript admits plain unescaped native string tokens and bounded
literal concatenations; escape decoding, template strings and dynamic strings
remain unknown. Interpolation, mutable dependencies or a bound violation remain
unknown according to each language interpreter's supported forms.

Python also recognizes the source form `getattr(base, name)` only for an
unshadowed builtin spelling, exactly two positional arguments, no keywords and
a qualified identifier-valued string name. The resulting property relationship
is conditional on `unshadowed-builtin-getattr`. Python helper argument
relationships require one observed local call; competing or dynamic callers
remain unknown. These restrictions describe supported source forms and do not
establish builtin runtime identity or exclude external callers.

A property named `fetch`, `send`, `run` or any other spelling remains a neutral
source property. Hashmarks does not classify it as a browser API, approve a
consumer architecture rule or determine what implementation will execute.

## Result and evidence contract

| Field | Meaning |
| --- | --- |
| `member` | Canonical path, full-member revision, visibility and index qualification supplied by Source. |
| `language`, `parser` | Canonical language and the native parser's grammar, signature and capability. |
| `producer` | Versioned binding-interpreter signature, separate from the native parser signature. |
| `facts` | Deterministic bounded projection of source binding observations. |
| `observed_fact_count`, `returned_fact_count` | Total facts from the fully qualified bounded member and the number returned. The total is `null` when observation is unavailable. |
| `coverage` | Fact kinds, qualification-before-projection scope, expression-preview convention and import-resolution boundary. |
| `semantic_coverage` | Explicitly incomplete coverage of bounded supported source forms, with unknowns retained in per-fact reasons. Complete traversal does not mean full language semantics. |
| `availability`, `reason` | Whether the member was observed; source, parser or bound failure reason otherwise. |
| `completeness`, `truncation` | Complete/not-truncated for the observed fact sequence, incomplete/truncated when clipped, and unknown when unavailable. These do not strengthen semantic coverage. |
| `generation`, `identity_generation`, `freshness` | Existing CodeMap read authority. A complete syntax traversal cannot strengthen stale or unknown repository freshness. |
| `observation_identity` | Deterministic identity binding this member, parser, interpreter, facts and projection; `null` when unavailable. |
| `module_resolution` | Always `not-performed`. No imported implementation is opened or followed. |
| `runtime_target_resolution` | Always `not-performed`. |
| `negative_evidence` | Always `not-admissible`, including an empty complete result. |
| `authority`, `execution_effect` | Always `repository-evidence-only` and `none`. |

`observation_scope` is `exact-admitted-member-source-bindings`. Ranges use
`coordinate_system="zero-based-half-open-bytes"`: `[start_byte, end_byte)`
addresses the exact original UTF-8 bytes. CRLF and multibyte characters are
not normalized. A scope locator has `kind`, exact `range` and optional `name`;
it distinguishes identical names in different containers. Language-specific
scope rules determine qualification. An expression descriptor has `syntax_type`,
exact `range`, preview `text` and `text_truncated`. The fact's range, bound-name
range and expression range can differ, so consumers must use the requested
locator rather than infer coordinates from preview text.

Each fact carries its `kind`, exact `range`, `scope`, source `expression`,
`qualification`, `target`, `literal`, `binding_range`, `supporting_ranges`,
`conditions`, `reasons`, `runtime_target` and `evidence_identity`. Fields that
cannot be established remain null or explicitly unknown. `binding_range`
locates the row's explicit bound name or parameter when supplied. A reference
may instead locate its origin through `target.range` or `supporting_ranges`;
consumers must not require every reference to have a non-null binding range.
`supporting_ranges` retain the source locations needed to explain an alias or
literal chain even when other facts at those locations are outside the returned
projection. Evidence ranges refer to the packet's full-member revision.

| Fact kind | Observation |
| --- | --- |
| `declaration` | A source declaration and its lexical location. |
| `import-binding` | An authored module/symbol binding and local alias; this does not resolve the imported implementation. |
| `alias-binding` | A supported source initializer or alias with its bounded origin and supporting locations. |
| `literal-binding` | A supported binding with a qualified string value, or an explicit unknown when it cannot be established. |
| `default-binding` | A separate conditional parameter-default relationship. |
| `argument-binding` | A separate conditional relationship between an argument and a parameter on one admitted local helper call. |
| `reference` | A source expression's qualified, conditional or unknown relationship to its lexical binding. |
| `call-site` | A call expression and the source qualification of its callee; its runtime target remains unestablished. |

Default and argument facts may additionally contain
`parameter={name, range, scope}` and `call={range, callee_range}`. A conditional
fact retains both its expression qualification and the conditions needed to
apply it. Type-only and ambient ECMAScript syntax cannot establish a runtime
binding. Unsupported language constructs retain unknown qualifications rather
than borrowing certainty from nearby text.

## Bounds and failure behavior

| Bound | Value |
| --- | --- |
| Returned facts | Default 200, range 1–500; MCP maximum 50. |
| Complete member bytes | Default 1 MiB, range 1 byte–8 MiB. |
| Syntax nodes | At most 100,000. |
| Alias depth | At most eight. |
| Nested expression depth | At most 32. |
| Supporting source ranges per fact | At most 64. |
| Local helper edges | At most one. |
| Import hops | Zero. |
| Interpreted string value | At most 256 UTF-8 bytes. |
| Expression text preview | At most 256 original source bytes, with explicit truncation. |

Booleans are rejected as limits before source access. Whole-member and syntax
traversal bounds qualify the required scope: if they prevent that scope from
being observed, partial facts are discarded, counts remain unknown and
availability is unavailable. Per-expression interpretation bounds retain
explicit unknowns rather than guessing a target or value. The result limit is
only a final projection bound; it never narrows the lexical scope used to
qualify a retained fact.

Python uses the native Python AST for `.py` and `.pyi` members. ECMAScript uses the existing
native grammar selection for `.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.mts`
and `.cts`; install the optional `hashmarks[syntax]` extra for that capability.
Missing or failed native syntax, recovered parse errors, unsupported suffixes,
invalid encoding and unavailable member bytes yield unavailable evidence.
There is no regex, local tokenizer or advisory parser fallback.

Source admission, visibility, symlink rejection and stable-read rules apply
unchanged. Denied, missing, unreadable, oversized or unreconciled members publish
no binding facts. Source rechecks the canonical member and parser/interpreter
identity after interpretation; drift suppresses facts and remains
unavailable/stale. An ordinary generation change also marks freshness stale.
Without canonical Identity evidence, freshness remains unknown even when the
source forms were fully traversed.

Fact identities bind the member revision, parser, interpreter and projected
fact, including source ranges and qualification. An edit elsewhere in the member
changes those identities. Another adequate byte budget preserves identities;
clipping the fact sequence changes the observation identity while preserving
identities of retained facts.

Python full-module parsing goes through
`hashmarks.python_ast_cache.parse_python_ast`; file-backed tooling continues to
use `read_python_ast`, which delegates parsing to that same owner. Indexing and
binding interpretation can share the admitted AST in one existing observation
scope. Reuse is keyed by the exact UTF-8 source and native Python grammar
signature, never just a path or modification time. Python's context-local
`python_ast_session()` retains at most 32 trees and 8 MiB of source; nested
operations share it, and exit or failure clears it. The ECMAScript provider
applies the same bounded operation-lifetime principle to its native trees.
Eviction can cause another parse through the same owner without changing
evidence. Syntax reuse creates no durable observation, generation or freshness
authority, and consumers treat shared trees as immutable.

## Observer ownership

- **Observed repository fact/evidence:** source-local declarations, references, authored imports, bounded aliases and string values, and explicitly conditional default/argument relationships.
- **Authority source:** Source's admitted stable member bytes and revision, native Python or ECMAScript syntax, and a versioned bounded interpreter over that syntax.
- **Completeness/freshness behavior:** whole bounded scope qualified before projection, explicit incomplete semantic coverage and per-fact unknowns, existing generation authority and final member/provider recheck; no negative semantic evidence.
- **Existing Hashmarks owner extended:** `RepositorySource`; language interpreters consume supplied syntax and own no source cache, repository state, import graph or read lifecycle.
- **Consumer/execution responsibility explicitly not acquired:** application architecture policy, browser/API allowlists, runtime object identity, imported implementation inspection, execution decisions or certification.
- **Decision:** OBSERVER.

`RepositoryImports` remains the separate owner of qualified repository import
resolution. It already consumes Source, so Source's binding observation does
not call back through that owner. No new import walk or semantic registry is
introduced. Consumer migration can replace duplicate binding interpreters with
this producer packet while retaining the consumer's own policy and runtime
decisions.

Transport and registration regressions live in
`tests/test_source_bindings_transport.py` and `tests/test_operation_contract.py`.
Language-specific semantic regressions and canonical-source drift regressions
qualify the producer independently of those adapters.
