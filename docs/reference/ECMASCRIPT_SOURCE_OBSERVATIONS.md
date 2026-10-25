# ECMAScript source syntax observations

`CodeMap.source.ecmascript()` observes import aliases, binding initializers,
object destructuring, assignments, property access, and call sites in one
admitted JavaScript or TypeScript member. The facts come from the existing
native syntax provider and Source's canonical stable byte capture. This operation
does not resolve an alias chain, identify a runtime object, or resolve a call
target.

```python
from hashmarks import CodeMap

with CodeMap(".") as codemap:
    codemap.index.sync()
    observation = codemap.source.ecmascript("src/consumer.ts", limit=200)
    if observation["availability"] == "observed":
        facts = observation["facts"]
```

The CLI uses `source-observation PATH --result-mode ecmascript`. MCP uses
`source_observation` with one path and `result_mode="ecmascript"`. The flat
service-client method is `CodeMapServiceClient.source_ecmascript(path, ...)`.
These adapters invoke the Source operation and preserve its evidence envelope;
they do not parse a second source copy. CLI/MCP synchronize at their request
boundary; service consumers reconcile with `client.sync()` when needed.
Optional `max_bytes` selects the member budget. CLI/service use the core result
limit (default 200, maximum 500); MCP retains its existing limit of 50 results.

## Supported syntax and native capability

The supported filename suffixes are `.js`, `.jsx`, `.ts`, and `.tsx`, using the
existing source-language owner. JavaScript and JSX use the native `javascript`
grammar; TypeScript uses `typescript`, and TSX uses `tsx`. Other suffixes return
`unsupported-source-language`. This API does not guess a language from file
contents.

Install the optional syntax extra, `hashmarks[syntax]`, to supply the supported
native grammar package. The configured CodeMap range provider must expose native
syntax trees. An absent provider, an unsupported grammar, a parser failure, or a
recovered tree containing syntax errors returns unavailable/unknown evidence.
The advisory declaration parser is not used as a fallback. The parser's grammar
and versioned signature are present in `parser`; a global provider capability
being available does not by itself mean this member was observed.

The repository's neutral fixture is
`tests/fixtures/ecmascript_source/consumer.ts`.
For example:

```typescript
import { gateway as client } from "./gateway";
const transport = client;
const { send: transmit } = transport;
transport.send(payload);
transmit(payload);
transport[method]?.(payload);
```

This yields separate native observations for the import alias, the initializer
`client`, the object-pattern component `send: transmit`, the property syntax, and
each call. The final computed key retains the expression `method`; its property
name and resolved target are unknown. No fact asserts that `transmit`, `client`,
and `transport.send` designate the same callable. An unresolved import does not
prevent observing syntax in this member, and its implementation is never opened.

## Result contract

Schema: `hashmarks.ecmascript-source-observation.v1`.

```python
source.ecmascript(
    relpath: str,
    *,
    limit: int = 200,
    max_bytes: int = 1_048_576,
) -> dict[str, object]
```

| Field | Meaning |
| --- | --- |
| `member` | Canonical path, full-member revision, visibility, and index state supplied by Source. |
| `language`, `parser` | Canonical source language and the configured native provider's capability, selected grammar, and signature. |
| `facts` | A deterministic, bounded sequence of the supported native syntax facts. |
| `observed_fact_count` | Total supported facts in the fully traversed native tree, before the result cap; `null` when observation fails. |
| `returned_fact_count` | Number of facts included in this response. |
| `coverage` | The explicit fact categories, object-pattern component scope, and expression-preview convention. |
| `completeness`, `truncation` | Complete/untruncated for all covered facts in this member; incomplete/truncated when the result cap clips them; unknown when unavailable. |
| `generation`, `identity_generation`, `freshness` | Existing CodeMap read authority. Byte or syntax completeness cannot strengthen unknown or stale freshness. |
| `observation_identity` | Deterministic identity binding the canonical member, native parser, covered facts, total count, and projection truncation. `null` when unavailable. |
| `reason` | `null` after successful observation; a source, capability, encoding, parse, or traversal-bound reason otherwise. |
| `semantic_resolution` | Always `not-performed`. |
| `negative_evidence` | Always `not-admissible`. |
| `authority`, `execution_effect` | Always `repository-evidence-only` and `none`. |

`observation_scope` is `exact-admitted-member-native-syntax`. Every fact and
expression range uses `coordinate_system="zero-based-half-open-bytes"`:
`[start_byte, end_byte)` refers to the original UTF-8 bytes. CRLF and multibyte
characters are not normalized. Fact ranges include the entire native node.

Each fact has `kind`, `syntax_type`, `range`, `scope`, `syntax_context`,
`parent_syntax_type`, and `evidence_identity`. The scope is the nearest native
container, such as a program, function, or block. It is a syntactic location,
not a resolved JavaScript binding scope: for example, the operation does not
implement `var` hoisting. Identical text in different scopes remains distinct.
`syntax_context` distinguishes value, type, and ambient syntax. `value-syntax`
does not assert that an expression executes. Import/export facts additionally
preserve native `type_only` qualifiers.

| Fact kind | Native fields exposed |
| --- | --- |
| `import-binding` | Named, default, and namespace import names and aliases; exact source-module token; type-only qualifier; name/alias token expressions. |
| `export-binding` | Named export specifier's name and exported alias, optional source-module token, and type-only qualifier. |
| `binding` | Variable declarator's exact binding pattern and optional initializer, plus `const`, `let`, or `var` token. |
| `destructured-binding` | Object-pattern key, binding, optional default, computed/rest flags, containing pattern range, and enclosing variable-declarator range when applicable. |
| `assignment` | Native simple or augmented assignment's left side, right side, and operator. This does not update an alias graph. |
| `property-access` | Exact object and property expressions, computed flag, and optional-chain token on this native node. It makes no read-versus-write or runtime-object claim. |
| `call-site` | Native call/new expression's callee, arguments, call/construct kind, optional token on this node, and `resolved_target=null`. |

Object-pattern components preserve nesting through their ranges rather than
flattening an alias chain. Defaults are separately exposed. A rest binding has no
known property name. Function-parameter patterns never acquire an enclosing
variable declaration's range, including parameters in TypeScript function types,
constructor types, and callable object signatures. Array patterns remain whole
binding expressions; this version does not expand their elements. Side-effect-only imports,
TypeScript import-equals declarations, namespace re-exports, and other syntax
outside the listed node forms do not acquire binding facts.

Property descriptors carry an exact expression, a direct identifier `name` when
available, and `literal_text` for a complete unescaped native string token. A
computed identifier such as `[method]` has no property name. `['send']` preserves
the literal contents `send`; `['se' + 'nd']` and escaped string tokens remain
unresolved. Escaped identifier tokens also retain their expression without a
decoded name. No constant folding, escape interpreter, symbol lookup, or browser
API classification is introduced. Optional-chain flags refer to the particular
native node; a call may also depend on optional syntax in its callee expression.

## Bounds, identity, and freshness

`limit` accepts integers from 1 to 500; its default is 200. The byte budget covers
the whole source member required to establish its revision. `max_bytes` defaults
to 1 MiB and accepts integers from 1 byte to 8 MiB. Booleans are rejected for both
arguments before source access. Native traversal is capped at 100,000 named
nodes; exceeding it discards partial facts and leaves the total count unknown.
The native parser itself receives only the bounded member bytes.

Expression text is a display preview capped at 256 original bytes. A clipped
preview has `text_truncated=true`, while its full byte range remains exact.
Clipping a preview does not remove its fact or imply that the preview is the full
expression. The response's fact completeness is separate from preview text
completeness. A complete observation of an empty file or a file containing no
covered nodes has zero counts but still supplies no negative semantic or
repository-wide evidence.

Each fact identity binds the full-member revision, path, parser, native location,
and projected fields. An edit elsewhere in the member changes its fact identities
even when a local expression is unchanged. Repeating a successful observation
with another adequate byte budget preserves identity; clipping the fact sequence
changes the observation identity and preserves identities of retained facts.

Source admission, denied/outline visibility, symlink rejection, and stable-read
rules apply unchanged. Missing, denied, linked, unreadable, unstable, oversized,
or unreconciled indexed members publish no facts and no observation identity.
Invalid UTF-8 and NUL-containing source are unavailable for this textual syntax
operation; exact byte transport remains the responsibility of
[range receipts](SOURCE_RANGE_RECEIPTS.md).

Generation status is sampled after native projection. A generation change during
observation marks the result stale. Without an available canonical Identity
observation, freshness remains unknown even when native syntax was completely
observed. The result describes captured bytes at an observation point, not future
filesystem contents.

## Observer ownership

- **Observed repository fact/evidence:** exact import, binding, property, assignment, and call syntax in a bounded admitted source member.
- **Authority source:** Source's canonical stable member bytes and the configured native tree-sitter range provider's grammar.
- **Completeness/freshness behavior:** explicit native-node coverage and limits; canonical generation authority; unknown on unavailable evidence; no semantic negative evidence.
- **Existing Hashmarks owner extended:** `RepositorySource` and `TreeSitterRangeProvider`; the syntax projection is request-local and owns no source cache, index, generation, or relationship graph.
- **Consumer/execution responsibility explicitly not acquired:** application architecture rules, runtime behavior, alias/type resolution, execution decisions, browser allowlists, and imported implementation inspection.
- **Decision:** OBSERVER.

Runnable consumer example: [`examples/ecmascript_source.py`](../../examples/ecmascript_source.py).
Repository regression coverage: `tests/test_source_ecmascript.py`.
