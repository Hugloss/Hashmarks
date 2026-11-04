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

The additive consumer-evidence fields below are produced by
`hashmarks.source-binding-interpreter.v4`. Consumers bind the actual producer
identity and supported interpreter contract; the schema name alone does not
prove that a released installation supplies these fields.

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
are rejected. MCP retains its existing result limit of 50. Python, CLI and
service calls share the core default of 200 and an explicit maximum of 100,000.
The larger ceiling lets a consumer request all observed facts from a bounded
member without a second source scan or a page-stitching protocol. It does not
increase the byte, syntax-node, expression or alias bounds.

A consumer that needs the whole observed sequence must check `availability`,
`completeness`, `truncation` and both fact counts before applying its policy.
For example, it can request `limit=100_000` and require
`returned_fact_count == observed_fact_count` with `truncation="not-truncated"`.
Even that complete sequence retains incomplete semantic coverage, explicit
unknown facts and `negative_evidence="not-admissible"`. It cannot certify the
absence of forbidden runtime behavior. Unknown repository freshness also
remains unknown; a matching immediate member revision cannot strengthen it.

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

Python additionally emits `conditional-call-binding` when a conditional default
or single observed helper input has an exact symbolic call use of that same
parameter. The join uses the native parameter identity, not a matching private
name or another source walk. A qualified import plus a `Server` property use,
for example, can describe a conditional source candidate. The original
`call-site` still has its unknown target; it is never rewritten.

Each joined row retains `input_binding`, the helper's `input_call` when present,
the exact `parameter`, and `parameter_use` with the original unknown call,
symbolic relationship, range and reasons. Default/supplied alternatives remain
separate rows. Their conditions include the original binding/use conditions,
external callers not being observed and call-site execution not being
established. Every joined row still denies runtime target and negative-evidence
authority. Consumers may grade these conditional source observations under
their own declared-owner policy; they cannot call them unconditional runtime
ownership or use a missing row as evidence of absence.

Unused defaults, unrelated same-named parameters and unsupported/multihop inputs
do not manufacture joins. Later property mutation or supporting-evidence bounds
withdraw candidate qualification while retaining uncertainty and conditions.
At most 256 call uses per input binding and the existing 100,000-result internal
row budget qualify this family. Bound exhaustion fails full-scope qualification
before result projection. Ordinary output clipping retains the full observed
count and explicit incomplete/truncated status.

A parameter can still have an independently qualified authored property path.
For example, in `def publish(journal): finish = journal.finish_detail; finish()`,
the call's `target` remains null and its main `qualification` remains unknown.
Its `symbolic_reference` can identify the exact parameter declaration and
`properties=["finish_detail"]`. That descriptor carries its own qualification,
conditions, reasons and supporting ranges, plus
`runtime_identity="not-established"`. It describes how the source refers to a
supplied value, without establishing what value a caller supplies. Mutation,
shadowing, unsupported forms or an interpretation bound can withdraw that
independent qualification. Consumers must not replace the main unknown target
with this symbolic path or a default/helper argument fact.

### Unresolved lexical origins

Python preserves an authored unresolved name as a symbolic origin. For example,
`load = unprovided_loader; load("pkg")` carries a `symbolic_reference` with
`root.kind="unresolved-name"`, the original spelling, its exact source range and
lexical scope. Supported alias and property paths retain their supporting
ranges. The main fact stays `qualification="unknown"`, `target=null`, with
`unresolved-lexical-name`; the symbolic descriptor qualifies only that authored
source relationship. Its `runtime_identity` remains `not-established`.

Builtin-looking spellings such as `__import__` receive no special runtime
identity. A parameter with the same spelling retains its parameter root;
declared, rebound, dynamically written or star-imported namespaces cannot become
an unresolved unique origin. Alias depth and expression/support bounds still
withdraw unsupported provenance. Default and supplied-helper facts can carry
this origin with their existing conditions, but never substitute it for a
parameter's unknown runtime target. Consumers must inspect those separate
conditional facts when their policy concerns possible authored origins; an
unknown call target is not evidence that no such origin exists.

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

### Structured syntax for consumer policies

`call-site.arguments` preserves the authored argument slots in source order.
Each detail has an `index`, `kind`, optional keyword `name`, exact whole-argument
`range`, `expression` and the normal evidence qualifiers. Kinds are
`positional`, `keyword`, `spread` and `keyword-spread`, as supported by the
language. An index is a source slot, not an inferred runtime parameter position.
Python records the underlying value expression separately from its keyword or
spread wrapper. ECMAScript keeps its native spread expression unknown. Numeric,
boolean, collection and other unsupported values stay unknown rather than being
converted into a new general expression evaluator. The callee's qualification
does not strengthen any argument.

Each call retains `argument_count`, `arguments_completeness` and
`arguments_truncation`. Python class declarations similarly carry ordered
`bases` with independent evidence, `base_count`, `bases_completeness` and
`bases_truncation`. `declaration_kind` distinguishes Python classes, functions
and parameters. These nested lists have their own 256-detail bound; a complete
outer fact sequence does not imply a complete nested list.

Python `import-binding.import_syntax` preserves the authored `module`, `name`,
relative-import `level` and `local_name` even when binding qualification is
unknown. Star imports retain their authored spelling with an unknown target.
ECMAScript `module-declaration` rows reuse the existing native static module
projection for imports, side-effect imports and re-exports. They also observe
native dynamic imports and supported calls to an unshadowed lexical `require`,
including supported aliases. Each row retains its `declaration_kind`, `source`,
`module_specifier`, `type_only` and `module_resolution="not-performed"`.
Unsupported specifiers or shadowed loaders stay unknown. Type-only imports do
not become runtime call or reference facts.

`literal-expression` identifies native string occurrences and supported string
expressions. Unsupported interpolated strings remain unknown. Python suppresses
the native AST's internal f-string text fragments so they cannot masquerade as
complete strings. Python literals inside call arguments may carry
`call_argument={call_range, range, kind, name}` for their nearest argument source
container. This is containment evidence, not the runtime value of that argument.
ECMAScript retains its existing conservative escape and template handling.

`property-write` records authored destinations with `access_kind`, `property`,
`context` (`store` or `delete`) and independent `receiver` evidence. Python
currently emits native attribute stores and deletes; its ordinary outer target
resolution stays unknown when the member's own mutation prevents qualification.
ECMAScript additionally records a `destination`, `write_kind`, `operator`,
`reads_previous_value` and optional value expression. It qualifies a write
address from the normally qualified receiver and property key without reading
the previous value of the final property. Thus `d[key] = value` can identify an
authored `document.cookie` destination while ordinary reads of that property
remain unknown. Mutation of a receiver or an ancestor property still blocks
that address qualification. A write fact does not prove that the write runs or
that a runtime object is a browser, network or filesystem API.

ECMAScript `callable-signature` rows preserve native method signatures, their
direct interface or class `container`, `syntax_context`, method name and ordered
`parameters`. Each parameter records its native name, range, optional/rest flags
and an independent `type` descriptor. Only a native predefined type token can
have a qualified type name; aliases, unions and unsupported annotations remain
unknown because type resolution is not performed. Parameter collections retain
`parameter_count`, `parameters_completeness` and `parameters_truncation`.
Nested object-type methods are not attributed to an enclosing interface, and
overloads or merged declarations remain separate source observations. Consumers
must select the exact container and handle multiplicity themselves; these rows
do not establish a unique effective interface or runtime callable.

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
exact `range`, preview `text`, `text_truncated` and native `name` when available.
The name is syntax only: Python supplies it for native names and attributes;
ECMAScript supplies complete, unescaped native identifier tokens. It is never
recovered by parsing the preview. The fact's range, bound-name
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
| `literal-expression` | An authored string occurrence or supported string expression, with unknowns retained. |
| `property-write` | An authored property destination and separately qualified receiver evidence. |
| `module-declaration` | ECMAScript static, re-export, side-effect or supported dynamic module syntax, without module resolution. |
| `callable-signature` | Native ECMAScript method-signature syntax, direct container and bounded ordered parameter/type details. |

Default and argument facts may additionally contain
`parameter={name, range, scope}` and `call={range, callee_range}`. A conditional
fact retains both its expression qualification and the conditions needed to
apply it. Type-only and ambient ECMAScript syntax cannot establish a runtime
binding. Unsupported language constructs retain unknown qualifications rather
than borrowing certainty from nearby text.

## Bounds and failure behavior

| Bound | Value |
| --- | --- |
| Returned facts | Default 200, range 1–100,000; MCP maximum 50. |
| Complete member bytes | Default 1 MiB, range 1 byte–8 MiB. |
| Syntax nodes | At most 100,000. |
| Alias depth | At most eight. |
| Nested expression depth | At most 32. |
| Supporting source ranges per fact | At most 64. |
| Nested source details | At most 256 per call-argument, class-base or method-parameter list, with explicit collection counts and clipping qualifiers. |
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
