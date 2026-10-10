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

Python uses `CodeMap.structural_locality(target, result_mode="relationships",
supplied_observations=[...])` and `semantic_relationship_delta(before, after)`.
MCP uses the same structural mode and `evidence_comparison(...,
result_mode="relationships")`. Existing structural and comparison tools own
these modes; no language-server process is started.

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
Observed repository fact/evidence: bounded direct producer implementation/type/definition claims and qualified deltas.
Authority source: explicit SCIP records or caller-supplied LSP captures, correlated with existing stable member and CodeMap authorities.
Completeness/freshness behavior: independent producer collection, source correspondence, repository freshness, candidates, and projection bounds; no negative evidence.
Existing Hashmarks owner extended: CodeMap native evidence, structural endpoint comparison, task evidence, and presentation.
Consumer/execution responsibility explicitly not acquired: server lifecycle, semantic inference, edit/verification decisions, execution, or certification.
Decision: OBSERVER
```
