# Structural locality evidence

Hashmarks can project fresh, bounded structural-locality facts for one exact repository symbol:

```bash
hashmarks --workspace . structural-locality path/to/file.py::qualified_symbol
```

The projection is repository evidence, not refactor policy. It is intended for external coding agents, review systems, and tools that need to compare the cost of understanding a structural edit without allowing Hashmarks to decide whether the edit is desirable.

## What the packet owns

A `hashmarks.structural-locality.v1` packet binds:

- the exact `path::qualname` target;
- the synchronized repository fingerprint;
- the exact target source identity;
- the measurement configuration identity;
- bounded reachable symbols and static call edges;
- exact observed caller evidence when the indexed target resolves unambiguously; this is a conservative lower bound, not a proof that no aliased or dynamically bound callers exist;
- unresolved call/caller candidates when exact resolution is not possible;
- syntactic forwarding-only classification where Hashmarks has a supported parser;
- file fan-out, symbol count, navigation depth, context-line closure and cross-file reach;
- structurally related verifier paths;
- freshness, bounds, provider version and one evidence identity.

Hashmarks does **not** infer that a helper is a good abstraction, that a wrapper is justified, that a responsibility should be split, or that the caller should edit anything.

## Fresh measurement

The CLI/API performs an explicit CodeMap sync by default before producing the packet. The packet therefore records `freshness.state = "current"` with basis `explicit-sync`.

The Python API may request `refresh=False` for diagnostic use. Such a packet retains the ordinary observer freshness state and may be `unknown` or `stale`. Consumers that need architectural authority should fail closed on non-current evidence.

## Ambiguity

Structural-locality evidence deliberately prefers incompleteness to a false exact edge.

For a static call such as `helper(...)`, Hashmarks resolves the target only when the indexed repository evidence identifies one unambiguous symbol. If two repository symbols can satisfy the same short identity, the edge is emitted in `unresolved_calls` with candidate symbol IDs and is **not** counted as exact reuse, exact ownership, or exact navigation closure.

The same rule applies to caller evidence. A candidate caller that cannot be proven to target the selected symbol remains unresolved. `exact_caller_count` is therefore safe as positive evidence (for example, two exact callers prove at least two callers) but must not be interpreted as global caller-set completeness or as proof that a symbol is single-use.

Each Python call keeps its indexed lexical source. Calls inside a nested function
or method belong to that declaration, and do not become direct calls of its
enclosing function. Decorator, default and class-base expressions belong to the
surrounding definition scope; they are not calls made by the declared body.
The per-symbol call limit applies after selecting that source's own calls.
Passing a callback to a task group does not establish an invocation edge, and
two observed direct edges do not establish a transitive shortcut or runtime path.

Import qualification uses the exact callable's lexical scope, including enclosing
function bindings. Another class's same-named method or an unrelated nested body
cannot shadow that import. Actual argument, assignment, function, class and
closure bindings preserve unresolved identity; duplicate declarations in the
same qualified scope also remain unresolved.
An immediately executed class body can explicitly write a module name through
`global`; those writes also prevent exact import qualification. Ordinary class
attributes and writes inside deferred function or method bodies do not escape
their own scope merely because a class is constructed.
Names declared `global` in a class cannot establish exact class-member or nested
class identity. Escaped module writes do not overwrite another class's namespace.

Structured, compact and text presentation preserve the complete, already bounded
`nodes`, `edges`, `unresolved_calls` and `external_or_unindexed_calls` collections.
Each collection is one finding: `details` is its native array, `source_refs`
identifies that array in the native packet, and `native_item_count` gives its
member count. Append an array index to that reference to locate a member.
The family's observed/omitted finding counts count collections for these kinds;
they do not count call edges. This removes repeated per-edge metadata without
applying another display cutoff to admitted segments or gaps. Other presentation
sections retain their existing bounds. Native traversal bounds, source qualifiers
and unresolved identity continue to define the observation scope. An empty
observed collection does not establish repository-wide or runtime absence.

For Python class methods, `self.member(...)` and `cls.member(...)` may be promoted to an exact call only when the containing method/class is statically known and the member has one unambiguous owner through the local/import-resolved class inheritance graph. Competing inherited owners, unsupported/dynamic bases, or receiver shapes other than proven `self`/`cls` remain unresolved or external evidence rather than being guessed.

## Forwarding-only syntax

For supported Python symbols, Hashmarks reports whether the function body is syntactically just one call/return-call after an optional docstring. This is a structural observation only.

A forwarding-only function may still be required by an external compatibility or protocol contract. Whether that cost is justified belongs to the consumer.

## Delta

Two packets measured with the same target and measurement configuration can be compared with:

```bash
hashmarks structural-locality-delta --before before.json --after after.json
```

The `hashmarks.structural-locality-delta.v1` result reports:

- introduced and removed symbol IDs;
- dimension deltas;
- verifier-path additions/removals;
- exact before/after evidence and repository identities;
- comparability/incomparability reasons.

It intentionally contains no architectural score, recommendation, winner, edit instruction, or merge authority.

## Consumer split

The intended ownership boundary is:

```text
repository bytes
    |
    v
Hashmarks structural-locality facts
    |
    +--> external refactor methodology / agent economics
    |
    +--> repository-owned semantic contracts
```

Hashmarks owns what is structurally observable. A consumer such as agentsCookbook may combine those facts with repository-owned semantic evidence to decide whether new helpers, wrappers, shims, adapters, or modules actually earn their existence.


## Direct SCIP semantic relationship evidence

SCIP relationship kinds describe producer flags, independently of CodeMap's
static call/reference graph. In particular, `reference` represents SCIP
`is_reference`: inclusion of related symbols in reference searches. It does
not assert a source occurrence, call edge, or inverse repository relationship.
`implementation`, `type_definition`, and `definition` retain their explicit
SCIP flag meanings and original source-to-target direction. See the
[SCIP relationship protocol](https://github.com/scip-code/scip/blob/main/scip.proto).

For an exact target definition, `structural_locality` carries a bounded
`native_semantic_relationships` observation if an already imported, current
SCIP producer supplies matching `SymbolInformation.relationships`.

- A row retains the original source SCIP symbol, related symbol, exact
  provider-declared flag (`reference`, `implementation`, `type_definition`
  or `definition`), admitted definition location, producer, and source identity.
- Association with the CodeMap target requires matching admitted path,
  display name and definition start line. Otherwise Hashmarks does not guess
  a symbol-to-definition association.
- At most 64 flags per native definition and 128 definitions per path are
  considered. `truncated` is explicit. Relations are neither reversed nor
  transitively inferred, and they are never counted as proven callers.
- The default structural projection retains the import-time and current
  CodeMap revisions and conservatively reports producer source equivalence
  as unknown. Use the qualified relationship mode below for separately
  captured producer revisions, capabilities, and collection scope.
- Provider capability is reported separately from observed flags. Producer
  capability is not currently captured, so unobserved kinds remain
  `unknown-not-unsupported`. Coverage names the exact target-definition
  scope, provider freshness, definition/relationship limits, truncation, and
  candidate-search budget.
- Each target symbol is matched only against retained fresh definitions from
  the same SCIP producer. Unique and ambiguous CodeMap candidates are exposed;
  unresolved and budget-limited searches remain explicit, and an empty
  candidate set never proves absence.
- `negative_evidence_admissible` is always false: indexers may omit
  relationships, so an empty result is not evidence of absence.
- A structural-locality comparison reports added/removed **SCIP producer claims**
  only when the structural endpoints are comparable and both relation
  observations are untruncated with identical nonempty producer bindings. The
  MCP structured/compact/text projection exposes these changes as relationship
  findings while retaining the native delta. It is not evidence of causal
  change or complete Git history.

These are fields on the existing structural-locality evidence packet,
not a new MCP tool or general-purpose semantic knowledge graph. Hashmarks
does not launch or manage language servers for this feature. The data remains
in disposable CodeMap state with the same SCIP generation/freshness authority.

## Qualified direct relationship observations

```sh
hashmarks --workspace . structural-locality contract.py::Interface --result-mode relationships
hashmarks --workspace . structural-locality contract.py::Interface --result-mode relationships --supplied-observations captures.json
hashmarks structural-locality-delta --result-mode relationships --before before.json --after after.json
hashmarks structural-locality-delta --result-mode relationships --before before.json --after after.json --presentation text
```

Python uses `CodeMap.structure.locality(target, result_mode="relationships",
supplied_observations=[...])` and `semantic_relationship_delta(before, after)`.
MCP uses the same structural mode and `evidence_comparison(...,
result_mode="relationships")`. Existing structural and comparison tools own
these modes; no language-server process is started.

Relationship mode also accepts an exact `path::display_name` present only in
the native index, such as a TypeScript method that the lexical parser does not
index. The existing native-definition store must return exactly one admitted,
current definition for that path and name within its bounded read. Duplicate
method names, missing definitions, denied paths, and stale producers remain
unresolved. Hashmarks does not infer a qualified class/member name from SCIP
descriptors. This native lookup applies only to relationship observations;
default structural locality and edit ownership retain their existing owners.

`hashmarks.semantic-relationship-observation.v1` retains direct producer
claims mentioning the exact subject, including incoming SCIP claims in their
original direction and relationship-only records lacking a definition.
Incoming selection does not import the source's unrelated relationships or
infer an inverse, transitive relationship, or component. SCIP local symbol IDs
are scoped to their document. Producer identities remain provenance.

Each observation retains its producer/configuration/capture identities,
capability snapshot, declared collection state, freshness, source bindings,
claims, and accounting. Each claim retains producer symbol or supplied locator
identity, kind, direction, ranges/position encoding, candidate resolutions,
and independent source correspondence. Candidate uniqueness requires a current
indexed declaration, exact revision correspondence, a valid encoded character
boundary, and the declaration name at that position. Unknown encodings,
missing target snapshots, unsaved buffers that differ from disk, ambiguity,
and bounded searches remain unresolved. A unique candidate is locator
correspondence, not independent proof of the producer's semantic claim.

SCIP import accepts an optional `provenance` object (CLI `map import-scip
--provenance manifest.json`) with `configuration_identity`, `collection_state`,
`capabilities`, `source_revisions`, and `source_provenance`. Revisions use the
canonical member digest; manifest revision/provenance maps admit at most 32
members, sharing the existing member-claim bound. Embedded SCIP `Document.text` supplies a separately
labelled UTF-8 document-text digest when no explicit byte revision is supplied.
The hash observed during import never substitutes for a producer claim.
The manifest and orphan claims publish atomically with the existing native
producer snapshot and survive the existing CodeMap reopen path.

`hashmarks.semantic-relationship-delta.v1` retains both validated endpoints.
Qualified claim-set additions/removals require matching subject, repository
scope, observer, producer scope and configuration; complete, untruncated
collection; current producer freshness; and exact retained source
correspondence. Incompatible observations expose reasons and delivered-subset
changes while withholding qualified fact removals. Locator movement, source
bindings/document versions, capabilities, configuration, collection, and
candidate resolution are independent axes. Moving a qualified declaration
does not change its semantic claim identity. Unresolved LSP locators lack
stable declaration identity and retain locator-based identity explicitly.
These are producer-claim comparisons, never repository absence or causation.
Capture changes and all retained evidence variants sharing one fact identity
remain explicit; fact deduplication does not discard their differing locators,
basis, or declaration metadata.

Observation bounds are 32 producer observations, 128 claims per observation,
64 candidates per resolution, and 512 KiB per packet. Input captures are
bounded to 1 MiB in total and 32 snapshots per capture. The SCIP adapter also
retains its existing 64 flags per symbol bound. Counts, truncation, excluded
claims, omitted observations, and byte/count bound reasons remain explicit.
The compact task view returns eight claims, four candidates per resolution,
and four source bindings per observation with presentation omission counts.
Full details use the existing relationship mode. Presentation bounds never
alter qualification. Public validation recomputes content identities and
re-proves deltas from the retained endpoints.

### Supplied LSP captures

The CLI file is an object containing an `observations` array. Each entry has
this narrow capture shape (positions are zero-based):

```json
{
  "schema": "hashmarks.lsp-relationship-capture.v1",
  "producer": "language-server:version",
  "configuration_identity": "caller-owned-config-identity",
  "request": {
    "jsonrpc": "2.0", "id": 1, "method": "textDocument/implementation",
    "params": {
      "textDocument": {"uri": "file:///repo/contract.py"},
      "position": {"line": 0, "character": 6}
    }
  },
  "response": {"jsonrpc": "2.0", "id": 1, "result": []},
  "capabilities": {"implementationProvider": true},
  "position_encoding": "utf-16",
  "collection_state": "fresh-complete",
  "documents": {
    "contract.py": {
      "text": "class Interface:\n    pass\n",
      "revision_kind": "utf8-document-text",
      "text_encoding": "utf-8",
      "provenance": {
        "producer_session": "session:1", "document_lifetime": "open:1",
        "document_version": 3, "source_kind": "buffer",
        "binding_basis": "producer-snapshot"
      }
    }
  }
}
```

Accepted methods are `textDocument/implementation`,
`textDocument/typeDefinition`, and `textDocument/definition`. Results accept
LSP `Location`, `LocationLink`, arrays, or null; explicitly supplied
`partial_results` arrays and JSON-RPC errors are preserved. Implementation
direction is result-to-query; definition/type-definition direction is
query-to-result. An error cannot claim a fresh complete collection. A null
result without complete collection does not prove an empty semantic scope.
Snapshots accept `revision` instead of `text`; text is hashed and discarded
after normalization, while its revision and producer provenance remain.
Contradictory supplied text/revision pairs fail before repository reads.
External locations remain uncorrelated claims without dependency traversal;
denied or unadmitted repository locations are excluded with accounting. Every
supplied document snapshot is retained as a source binding; a snapshot that
cannot be admitted remains an explicit unknown/unsupported binding with its
document count and unadmitted count exposed.
Captures affect only the current observation or comparison and never hydrate
durable provider state or later calls.

Ownership note:

```text
Observed repository fact/evidence: bounded direct producer implementation/type/definition claims, exact native-only relationship subjects, and qualified deltas.
Authority source: explicit SCIP records or caller-supplied LSP captures, correlated with existing stable member and CodeMap authorities.
Completeness/freshness behavior: independent producer collection, source correspondence, repository freshness, candidates, and projection bounds; no negative evidence.
Existing Hashmarks owner extended: CodeMap native evidence, structural endpoint comparison, task evidence, and presentation.
Consumer/execution responsibility explicitly not acquired: server lifecycle, semantic inference, edit/verification decisions, execution, or certification.
Decision: OBSERVER
```

## Additional read-only LSP observations (reference and call hierarchy)

The existing caller-supplied `hashmarks.lsp-relationship-capture.v1`
contract also admits `textDocument/references`,
`textDocument/prepareCallHierarchy`, `callHierarchy/incomingCalls`,
and `callHierarchy/outgoingCalls`.

- Reference requests include `textDocument`, `position`, and a real
  `context.includeDeclaration` boolean. Each result is a reference-site
  **producer claim** pointing to the queried symbol, not a proven index edge.
- Prepare requests contain `textDocument` and `position`. Returned
  `CallHierarchyItem` records are preserved as qualified *navigation
  candidates*, never fabricated call edges.
- Incoming and outgoing requests contain a validated `params.item`
  `CallHierarchyItem`. Responses use the corresponding
  `{from, fromRanges}` or `{to, fromRanges}` protocol shape. Incoming
  evidence retains caller → queried callee, and outgoing retains queried
  caller → callee. `fromRanges` remain caller-provided **call-site** ranges,
  distinct from both declaration/selection ranges.
- Only explicit bounded captures are interpreted. Capabilities, request IDs,
  producer session, source snapshots, UTF-8/16/32 position encoding, partial
  collection, errors, source equivalence and omissions remain separate.
- Unresolved/ambiguous locators, missing snapshots, changed buffers, exterior
  paths and bounded result sets remain non-authoritative; no empty capture
  proves missing repository references or callers.

The native `producer_correspondence` section compares direct, revision-bound
producer claims sharing comparable CodeMap symbols. `aligned_claims` means
two independent producers described a matching *claim*; it does not prove
truth. `distinct_observed_claims` is not a contradiction or negative fact.
Incomparable/partial observations and unresolved endpoints are accounted
separately. The report is a request-local projection and does not form a new
cross-provider graph or an execution policy.

## H06: explicitly captured LSP hover (non-relationship evidence)

The existing `structural_locality(..., result_mode="relationships",
supplied_observations=[...])` method accepts the caller-supplied LSP
`textDocument/hover` request/response pair under
`hashmarks.lsp-relationship-capture.v1`. No LSP server is launched, no
repository discovery is performed on behalf of the agent, and the existing
fourteen MCP tools and operation defaults are unchanged.

The capture supplies the same request ID, explicit file URI/cursor, producer,
configuration, declared `hoverProvider` capability, collection state, source
snapshot(s), revision and position encoding required by other direct LSP
observations. Hover requests may also carry the optional `workDoneToken`, a
string or signed 32-bit integer. The token is retained as request provenance;
it adds no progress-tracking or execution responsibility. Hover does not admit
`partialResultToken` or other extra request fields. The response may be:

- an LSP `Hover` with `contents` (plain `MarkedString`, language/value
  marked string, bounded list of marked strings, or `MarkupContent` with
  `kind: plaintext|markdown`) and optional LSP `range`;
- JSON-RPC `result: null`, recorded as `no-hover-returned`;
- a captured JSON-RPC error, recorded as `producer-error`, but never as a
  fresh complete response.

The native observation retains `capability.hover_observation` with exactly
the supplied bounded contents, optional protocol range and one of the states
`hover-returned | no-hover-returned | producer-error`. Markdown and raw
strings remain **untrusted producer text**; Hashmarks does not execute them,
interpret their instructions, convert them into authoritative type/signature
facts, or infer a source-level symbol relationship from the hover range.
`semantic_correspondence: not-established`,
`authority: caller-supplied-producer-claim` and
`negative_evidence_admissible: false` are invariant.

Hover creates **zero relationship claims**. A null, empty or error response
does not prove a symbol has no documentation, type or references. The
qualified cursor and source binding live in the existing observation scope
and `source_bindings`: if the supplied document revision does not match the
current admitted member, producer freshness remains unknown and text is never
promoted into repository truth. The exact request/response bytes still
participate in the caller-supplied capture identity.

Admission rejects malformed JSON-RPC, mixed/extra hover fields, invalid LSP
ranges, unsupported markup kinds, non-text values, unexpected nonempty partial
result batches and oversized content before repository reads. Bounds are
4,096 UTF-8 bytes per text block, eight marked strings and 8,192 UTF-8
serialized bytes total per hover result, in addition to the existing capture
and packet bounds. A user-supplied packet that rehashes maliciously altered
hover authority or includes fabricated hover relationship edges is rejected
by public packet validation.

As with prepared call hierarchy, the hover observation is carried on an
existing read-only evidence surface rather than emitted as an edge. Consumer
routing, tool selection, model visibility, LSP lifecycle and verification
remain external responsibilities.

## Call-site source correspondence

A caller-supplied LSP `incomingCalls` or `outgoingCalls` result carries
`fromRanges` in the **caller document**, which is distinct from the
declaration/selection range of either endpoint. The direct claim's existing
`basis.fromRanges` remains verbatim producer data. New packets add
`basis.call_site_source`: explicit caller path, UTF-8/16/32 position encoding,
source snapshot binding, and a qualified range state.

`source-range-matching` requires the caller's admitted repository member,
an exact captured source revision, positions at valid encoded character
boundaries, and ranges inside the caller's declared `CallHierarchyItem.range`.
`revision-different`, `snapshot-unavailable`, `outside-repository`,
`unadmitted`, `outside-caller-item`, `invalid-position`, `empty-call-sites`
and `unknown`
remain descriptive, non-authoritative evidence. A matching call-site *range*
does not prove that a semantic call exists or that the LSP server was correct.

The source observation is request-local, uses the existing bounded/stable
source-read owner, and does not start an LSP server, execute code, interpret
a call expression or infer any missing calls. Legacy relationship packets
without the optional `call_site_source` remain valid, while claims that
present it must pass the native non-strengthening validator, even if packet
hashes have been recomputed.

## Imported call spelling and verification correspondence

Plain Python call candidates may use the declared name reached through the
existing bounded import/re-export resolver, including `as` aliases and
`from . import name`. Candidate nomination alone proves no relationship: exact
repository declaration identity, source visibility, shadowing, ambiguity, cycles
and the eight-hop bound still qualify resolution. Later assignments do not leave
an earlier function declaration authoritative. Renamed facade chains retain the
actual declaration's path and qualified name.

Static `__all__` declarations define star-export membership, including explicitly
listed leading-underscore names. Implicit exports exclude those names; dynamic
or deleted `__all__` declarations retain unresolved export authority.

The verification projection composes existing impact-test evidence with already
qualified test callers of the selected symbol. It preserves the selected edit
owner, the existing bounds and alternatives; it neither executes tests nor claims
that any verifier is sufficient.


Reverse caller discovery follows explicit import aliases and re-exports through
the existing reference index and the same forward identity qualifier. It reads
cached ASTs only for admitted candidate files. The reference limit bounds the
aggregate candidate search across aliases, and the eight-hop import limit still
applies. A truncated, hidden or unresolved search cannot report complete caller
coverage. There is no whole-tree fallback or persistent alias graph.

The syntax owner distinguishes declarations from later assignments (including
unpacking and augmented assignment), ordinary imports, deletion and conditional
writes. Unsupported or conditional rebinding preserves uncertainty. Annotation-only
statements preserve an existing declaration; locals inside unrelated nested scopes
do not overwrite module exports. Class/member qualification uses the same ordered
binding analysis. Indexing and qualification share relative-import target spelling;
the Python parser cache version changes so prior derived import artifacts rebuild.

Lambda parameters, lambda-local assignments and comprehension targets qualify
calls in their own expression scope. Lambda defaults and the first comprehension iterable retain the outer
scope; later iterables, filters and results use the comprehension's local bindings.
The compact call index has line coordinates, so a same-line collision between
outer and shadowed calls remains unresolved.
