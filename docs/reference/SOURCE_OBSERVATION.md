# Source observation and diagnostic correspondence

Hashmarks exposes additional **descriptive repository evidence** through the existing
CodeMap repository observer. It does not choose agent tools, run language servers,
execute verification, or create a second freshness/index authority.

## Exact source occurrence and physical source shape (H1 + H3)

Python API:

```python
from hashmarks import CodeMap

with CodeMap(".") as codemap:
    codemap.sync()
    observation = codemap.source_observation(
        "src/example.py",
        literal="example",
        limit=50,
    )
```

Schema: `hashmarks.source-observation.v1`.

This is a **single explicit member** observation, not a repository-wide text-search
completeness claim. The observer:

- Reuses repository file admission, evidence-visibility policy, and canonical
  stable member reads; a read is rejected when indexed revision and bytes differ.
- Returns literal case-sensitive, non-overlapping occurrences with 1-based physical
  line and Unicode-codepoint column coordinates. Enclosing symbols are reported
  only when a containing indexed symbol range is present.
- For Python sources, attaches tokenizer-qualified `identifier`, `string-literal`,
  or `comment` occurrence kinds when the entire occurrence fits one supported
  single-line token. Other languages and ambiguous tokens report `unknown`; this
  is lexical classification, not runtime or semantic identity.
- Records the canonical member revision on each occurrence, and a deterministic
  occurrence identity. It never invents ownership or dynamic binding.
- Reports UTF-8 BOM, byte size, physical line count, LF/CRLF terminators, maximum
  physical line length, a caller-bounded long-line count, and final LF presence.
  Counts come from the same stable byte capture used for textual occurrences.
- Refuses to expose source for denied, outline-only, unreadable, symlink, oversized,
  NUL-bearing, or invalid-UTF-8 members. For these, match count and completeness
  remain unknown rather than zero.
- Counts all observed occurrences within the single bounded member while returning
  at most `limit` locations. A truncated result is incomplete. A proven
  zero-match source scan can establish negative evidence **only within that exact
  member**, and only when repository freshness is current.

The default source byte ceiling is 1 MiB (maximum configurable ceiling 8 MiB).
No file is read in full if its preliminary size check already exceeds the bound;
stable reads and the post-read bound protect against concurrent enlargement.
No recursive dependency or repository scan is performed by this projection.

The exact member source observation is now also exposed through the existing
read-only `source_observation` MCP tool. This is transport over the same CodeMap
owner; it adds no independent index or execution backend.

## Optional contextual match excerpts (Hermes harness borrowing)

Hermes's `search_files` can return source context around matching lines. Hashmarks
already owns admitted, revision-bound exact literal occurrences, but a hit
previously returned a location without nearby source text. Consumers could
need another `sed` or file-read call even when a brief context window would
suffice to classify the match.

Use **the existing** source observer, not another search engine:

```python
with CodeMap(".") as codemap:
    codemap.sync()
    packet = codemap.source_observation(
        "src/example.py", literal="target", context_lines=1
    )
    hit = packet["occurrences"][0]
    excerpt = hit["context_excerpt"]
```

The existing read-only `source_observation` MCP tool accepts
`context_lines=1` in both `member` and `scope` modes. Omit it (or use
`context_lines=0`) for byte-for-byte-compatible existing packets.
Only `0` or `1` is valid; requesting context without an exact
single-line literal fails before source observation.

- A displayed match contains its original physical line and at most one
  neighbor on each side. Every excerpt line supplies its original 1-based
  `line`, 1-based `start_column`, `role` (`match` or `context`),
  source `text` clipped to **320 Unicode codepoints**, and explicit
  `truncated_left` / `truncated_right` flags. The match-line window is
  positioned to retain the entire literal (maximum 256 codepoints).
- Only the *original admitted and stable* member byte capture is used; no
  second filesystem read, recursive scan, index, cache, or persistent history.
  All source visibility, exact path admission, per-member and scoped byte
  budgets, and canonical revisions remain unchanged. Denied, unavailable,
  oversized, binary, invalid UTF-8 and unreconciled sources reveal no excerpt.
- Context is **display-only**, not an independent ownership assertion,
  negative-evidence proof, or verification result. An occurrence's existing
  `evidence_identity`, exact line/column and revision do not change when
  context is requested. The enclosing observation identity *does* distinguish
  a context-bearing request from the original location-only response.
- CRLF's terminal `\\r` is omitted from displayed text; line and column
  coordinates continue to refer to the original source. Long lines have
  explicit clipping metadata and may require a native source read to edit.
- Up to the existing 50 MCP occurrence rows may be returned, with at most
  three short excerpt lines each. Returned context never proves unseen
  matches or missing symbols; completeness, freshness and negative-evidence
  qualifications remain under the existing source owner.

This borrows a useful evidence **shape** from Hermes without taking over
agent tool selection, arbitrary regex search, code-editing, or runtime
read-deduplication. Regression coverage:
`tests/test_source_context_excerpts.py`.

## Explicit diagnostic-line context (Hermes follow-up)

An LSP/compiler diagnostic often supplies a known path and physical line but
no literal to search. The existing single-member source observer can return
bounded display excerpts next to its **existing exact byte-line anchors**,
without launching an LSP, resolving a symbol, rereading a source file, or
asserting that the external diagnostic is correct:

```python
with CodeMap(".") as codemap:
    codemap.sync()
    packet = codemap.source_observation(
        "src/example.py", lines=(12,), anchor_context_lines=1
    )
    rows = packet["line_anchors"][0]["context_excerpt"]
```

The existing MCP `source_observation` tool also supports this in `member`
mode with **no literal**:

```json
{
  "paths": ["src/example.py"],
  "result_mode": "member",
  "context_lines": {"lines": [12], "radius": 1},
  "presentation": "compact"
}
```

The numeric `context_lines=0/1` form still means **literal match** context.
The object form selects explicit physical lines only; it does not search.
It requires exactly `lines` (1–8 distinct positive integers) and
`radius: 1`. A requested blank or out-of-range line remains an **unknown
anchor with no excerpt**; it never becomes a zero-match or missing-diagnostic
claim. The default Python `anchor_context_lines=0` preserves the existing
line-anchor packet, identity and byte-line digest. An opt-in context-bearing
observation has a different observation identity, while the original
`line_sha256`, coordinates and source revision remain unchanged.

Only an already admitted, stable, complete UTF-8 member capture supplies
context. Denied, oversized, binary, invalid-UTF-8, changed/unreconciled and
unstable members disclose no excerpt. Each anchor excerpt has at most three
physical lines, each clipped to 320 Unicode codepoints with original 1-based
line/start-column and explicit left/right truncation. Its center
`role: "anchor"` distinguishes a known line from literal `role: "match"`;
neighbors have `role: "context"`. CRLF trailing carriage returns are
omitted from displayed text, not from the original byte-line digest.

Agent-native source presentation places explicit `line_anchors` after
literal `occurrences`, before member inventories. All details and exact
`/line_anchors/N` pointers survive compact rendering; omitted row counts
remain projection-only. The native packet remains the sole source authority,
and line excerpt display does not imply that the diagnostic producer observed
these bytes, passed verification, or reached a complete diagnostic collection.

## Exact scoped multi-member observation (H1 follow-up)

```python
with CodeMap(".") as codemap:
    codemap.sync()
    packet = codemap.scoped_source_occurrences(
        ["src/core.py", "tests/test_core.py"],
        "example",
        limit=100,
        max_total_bytes=4_194_304,
        max_member_bytes=1_048_576,
    )
```

Schema: `hashmarks.scoped-source-occurrences.v1`. This is a request-local
composition of the **same** source-observation owner, never another index,
repository crawler, persistent cache, or agent tool-routing policy.

The caller provides a nonempty explicit path set (at most 32 requested entries).
Paths are validated before work, deduplicated, and sorted deterministically.
Discovery does **not** expand directories or silently add other files.

Each path goes through canonical admission, source visibility, stable byte reads,
member revision and repository generation checks. The batch has a bounded total
source-byte budget (4 MiB by default, hard maximum 8 MiB) as well as the
per-member byte bound. Exhaustion, ignored/denied paths, missing members,
unreconciled edits, binary/invalid text and unstable reads remain observable
as per-member unknown/unsupported outcomes; none become zero matches.

`observed_match_count` is the number of matches in successfully scanned
members. `exact_match_count` is reported **only** when *all* requested
members were successfully scanned in the same repository generation. Result
locations may still be truncated by the independent `limit`; the exact count
remains valid because the underlying member observer scans the entire bounded
member. Per-member summaries explain unavailable and budget-exhausted members,
the count observed, and the number of emitted locations.

A qualified zero-match claim is **restricted to the exact explicitly named
set**, requires complete source coverage and current freshness, and never
asserts repository-wide absence. Partial, stale or mixed-generation batches
refuse negative evidence. Every emitted location retains its original exact
member revision and evidence identity.

The same scoped observation is also available through the `source_observation`
MCP tool in `scope` mode. Neither Python nor MCP requests expand the given
scope, schedule verification, or create a new source index.

## External diagnostic collection and correspondence (H2)

```python
from hashmarks.codemap.repository_delta import (
    RepositoryDeltaMixin,
    RepositoryGenerationBinding,
)

before = RepositoryDeltaMixin.external_diagnostic_observation(
    producer="pyright",
    binding=RepositoryGenerationBinding("repository-id", 7),
    diagnostics=[
        {
            "tool": "pyright",
            "rule": "E1",
            "path": "src/example.py",
            "line": 10,
            "message": "Undefined variable",
        }
    ],
    outcome="fail",
    collection_state="fresh-complete",
    scope_paths=["src/example.py"],
)
```

The optional `collection_state` field is explicitly **producer-claimed** and is
not silently upgraded to canonical repository or execution authority. Supported
states are `fresh-complete`, `fresh-partial`, `timed-out`, `unavailable`,
`source-mismatch`, and `unknown`. The existing execution outcome remains
separate.

The existing diagnostic identity remains strict and includes the location. The
diagnostic delta now additionally projects `possible_relocations` when exactly
one removed and exactly one added diagnostic share tool, rule, path, symbol,
and message but differ in location.

**This is candidate correspondence, not proven relocation.** It does not erase
the added/removed observations, claim causal continuity, or make any test pass.
Multiple same-fact candidates remain unresolved. Without independently qualified
source-span relocation evidence, matching diagnostic messages is insufficient
to assert identical diagnostic identity.

### Producer-claimed source revisions (Hermes file-version borrowing)

A diagnostic batch can now preserve **which exact Hashmarks file revisions its
external producer claims to have observed**, independently of message, line,
column, diagnostic identity, and collection completeness:

```python
diagnostic = RepositoryDeltaMixin.external_diagnostic_observation(
    producer="pyright",
    binding=RepositoryGenerationBinding("repo-id", 7),
    outcome="fail",
    collection_state="fresh-complete",
    scope_paths=["src/example.py"],
    source_revisions={"src/example.py": claimed_member_revision},
    diagnostics=[{"tool": "pyright", "rule": "E1", "path": "src/example.py"}],
)
```

`source_revisions` is optional and never backfilled from a later source
observation. Entries are **producer-claimed** 64-character lowercase Hex file
revisions in the same digest domain as
`source_observation["member"]["member_revision"]`. They are *not* Git SHAs,
document-version counters, or new evidence identities. The existing diagnostic
identity excludes this provenance so the same diagnostic fact does not appear
added or removed merely because its revision claim changed.

Diagnostic deltas preserve a separate `source_revisions` axis with normalized
`before` and `after` claims, a `changed` flag, and
`claim_authority="producer-claimed"`. Missing claims remain `None`; changing,
adding, or removing a claim does not change diagnostic fact identity or imply
that repository source bytes changed.

Claims are limited to 32 normalized, explicitly scoped members; absolute or
escaping paths, duplicate normalized aliases, wrong digest format, and claims
outside the collection's declared path scope fail before rows are published.
Omitting a claim means **unknown**, not unchanged source. The supplied scope
and collection-state claims remain external producer authority.

After obtaining explicit up-to-date `CodeMap.source_observation` member
packets, the consumer may compare them **without launching** a diagnostic
producer or letting Hashmarks track agent reads:

```python
source = codemap.source_observation("src/example.py")
evidence = RepositoryDeltaMixin.diagnostic_source_revision_evidence(
    diagnostic, [source]
)
```

Schema: `hashmarks.diagnostic-source-revision-evidence.v1`. For each declared
path, the comparison reports `matching`, `different`, or `unknown` with
producer-claimed and observed member revisions, source observation identity,
source generation and freshness, and exact qualifications:

- **matching** means a claimed revision equals a single caller-supplied,
  complete, stable canonical member observation; it does **not** prove
  the LSP read those bytes or that repository-wide verification is current.
- **different** means the observed member bytes differ from the claimed
  source revision; it does **not** decide whether or how to rerun verification.
- **unknown** means absent/ambiguous source packets, unreadable/denied/oversized
  source, incomplete/truncated source evidence, unsupported source schemas, or
  stale or invalid repository freshness. It is not a file-absence assertion.

A stable, revision-verified member can support exact byte comparison even when
repository-wide freshness is `unknown`. Each row preserves that freshness as
`source_freshness`; `matching` never upgrades it to `current`.

Diagnostic collection outcomes and repository generation remain separate;
different diagnostic/source generations are exposed without inventing
cross-generation history. The comparison is **caller-retained endpoint
evidence**, not an independently authenticated execution trace. Its
`complete-for-declared-members` coverage applies only to the claimed member
set, not every source file or diagnostic path. Unclaimed diagnostic paths and
ignored source packets are counted separately.

The public `validate_repository_intelligence_evidence()` validator recognizes
this comparison schema and checks its bounded rows, revision comparisons,
counts, coverage, and authority labels. Its normalized projection retains
`source_revision_rows` and `source_revision_coverage`. Diagnostic observations
also retain normalized `source_revisions` through validation and reject malformed
or out-of-scope claims. A revision comparison supplies no repository-wide fresh
authority, so `require_fresh=True` rejects it even when all claimed bytes match.

The producer owns acquisition timing and LSP document versions; the agent
harness owns read/edit coordination, verification execution and decisions.
Hashmarks keeps only descriptive revision correspondence, reusing its existing
member observation and diagnostic normalization. No persistent history, LSP
engine, external runner, or ninth MCP tool is added.

Regression tests: `tests/test_diagnostic_source_revisions.py`.

### Document-version provenance and the external producer handoff

`external_diagnostic_observation` also accepts optional `source_provenance`:

```python
from hashmarks.digest import FILE_DOMAIN, hash_bytes

# The external client retains this snapshot when synchronizing the document,
# rather than reading whichever bytes happen to exist when diagnostics arrive.
captured_text = "print(missing)\r\n"
revision = hash_bytes(captured_text.encode("utf-8"), domain=FILE_DOMAIN).hash
diagnostic = RepositoryDeltaMixin.external_diagnostic_observation(
    producer="pyright",
    binding=RepositoryGenerationBinding("repo-id", 7),
    environment_identity="producer-config-id",
    outcome="fail",
    collection_state="fresh-complete",
    scope_paths=["src/example.py"],
    source_revisions={"src/example.py": revision},
    source_provenance={
        "src/example.py": {
            "producer_session": "server-session:1",
            "document_lifetime": "document-open:3",
            "document_version": 12,
            "source_kind": "buffer",
            "binding_basis": "reported-version",
        }
    },
    diagnostics=[],
)
```

Each provenance record has exactly these five fields. Session and document
lifetime are nonempty opaque strings of at most 256 characters. The version is
a signed 32-bit integer or null; Hashmarks preserves it without choosing an LSP
publication winner. `source_kind` is `buffer` or `disk`. `binding_basis` is
`reported-version`, `synchronized-request`, `producer-snapshot`, or `unknown`.
`reported-version` requires a non-null version. A known binding requires an
explicit `source_revisions` entry; an explicitly unknown binding forbids one.
Legacy revision claims without provenance remain accepted.

Both maps use canonical repository-relative paths, are bounded to 32 members,
and must stay inside the explicit diagnostic scope. Aliases are normalized;
duplicate normalized members and unknown provenance fields are rejected.
Records are copied, so later mutation of producer input does not alter evidence.

The external producer must implement the acquisition side of this contract:

1. Retain immutable snapshots keyed by producer session, document lifetime,
   path, and document version. A reopen starts a new document lifetime; a server
   restart starts a new producer session. Counters alone are not identities.
2. Bind a publication's reported version to its retained snapshot, including
   delayed publications. Never replace the revision with the latest disk or
   editor content. Snapshot eviction makes binding unknown rather than granting
   permission to reconstruct the old revision from newer bytes.
3. Hash disk bytes in the existing file digest domain. For unsaved buffers,
   hash the exact synchronized text encoded as UTF-8 without newline or Unicode
   normalization. Encoding or BOM differences can therefore produce different
   byte identities even when displayed text looks alike.
4. Versionless push publications stay unbound unless the producer supplies an
   independent exact snapshot guarantee. Receipt order, a quiet interval, and
   the latest editor version are insufficient. `synchronized-request` describes
   a producer-bound pull acquisition with stable synchronized input, not a
   guarantee inferred by Hashmarks.
5. Pull reports marked unchanged may reuse diagnostic facts only. Bind the new
   acquisition to its own source snapshot, or report unknown. A pull result ID
   is not a member revision. Related-document reports need their own bindings;
   the requested document's version does not identify another file's bytes.

Hashmarks preserves provenance through observation validation, source revision
comparison, diagnostic deltas, and evidence presentation. The separate
`source_provenance` delta axis reports before/after claims and whether they
changed; changing document versions never changes diagnostic fact identity.
Source revision comparison still describes equality with explicitly supplied
repository bytes, not producer execution or repository-wide freshness.

### Per-file diagnostic changes and collection coverage

`external_diagnostic_observation` accepts optional `collection_by_path`, mapping
up to 32 explicitly scoped members to the existing collection states:
`fresh-complete`, `fresh-partial`, `timed-out`, `unavailable`, `source-mismatch`,
or `unknown`. When this map is omitted or null, the batch collection claim
applies to its declared paths. When a map is supplied, an omitted member is
unknown: a complete report for one file cannot fill in another file's missing
report. A complete empty report remains distinct from an unavailable, partial,
or missing report.

```python
delta = RepositoryDeltaMixin.diagnostic_observation_delta(
    diagnostic_before,
    diagnostic_after,
    changed_paths=["src/example.py"],
    change_set_complete=False,
    relationship_evidence=explicit_current_correlation,  # optional
)
rows = delta["diagnostics"]["path_deltas"]
```

The same optional `change_set_complete` and `relationship_evidence` parameters
are available through MCP `evidence_comparison(result_mode="diagnostics")`.
Other comparison modes reject diagnostic qualification inputs. The external
producer's existing `source_revisions`, `source_provenance`, and
`collection_by_path` travel inside the supplied observation endpoints.

Every diagnostic identity is accounted for in deterministic `path_deltas`,
including unchanged facts, explicitly scoped empty files, unscoped diagnostic
paths, and a null-path group for diagnostics without a valid relative
locator. Each row contains before/after, added, removed, and unchanged identity
lists; endpoint scope and collection claims; member revision and document
provenance claims; edit relation; relationship evidence; and
`causation="not-inferred"`.

`edit_relation` is `reported-changed` for explicitly listed paths. Other paths
are `unknown` by default, or `caller-claimed-unchanged` when the external caller
explicitly declares the change set complete. An unlocated diagnostic always
keeps unknown edit status. These are path-reporting claims, not canonical proof
that the caller reported every edit. Changes in other files remain present
regardless of relatedness, and unchanged member bytes do not imply unchanged
diagnostics.

Optional relationship annotations consume an existing canonical
`hashmarks.evidence-correlation.v2` packet. Hashmarks reuses its native
correlation and binding integrity validators and requires a current repository
binding matching the after endpoint's repository and generation. An indexed
edge must correspond to an explicit, uniquely resolved qualified module/symbol
anchor. Short-name calls never supply that proof. Retained annotations name the
original directed edge and target-resolution JSON pointers; they do not derive
transitive relationships or claim the edit caused a diagnostic change.
Positive edges retain their native bounds. Missing, stale, foreign, ambiguous,
or unobserved relationships stay unknown rather than proving unrelatedness.

Per-file complete coverage qualifies external additions/removals using the
existing endpoint-context rules. Explicit document provenance additionally
requires matching sessions and document lifetimes, with known bindings on both
sides. Unknown bindings or changed acquisition contexts never upgrade a missing
diagnostic into a qualified removal. Raw additions/removals remain visible.
The delta retains both scope and producer/environment contexts, so public
validation can re-prove per-file membership, counts, edit classifications,
collection states, revision claims, relationship annotations, and qualification.

Structured, compact, and text presentation expose these as producer claims and
account for omitted records without changing the native delta. No view claims
that an empty bounded projection proves no cross-file diagnostics.

Ownership note:

```text
Observed repository fact/evidence: exact claimed source provenance and per-file diagnostic changes.
Authority source: external producer claims plus separately qualified canonical member/relationship observations.
Completeness/freshness behavior: per-member collection and changed-path completeness remain explicit; unknown stays unknown.
Existing Hashmarks owner extended: external diagnostic observation, source revision correspondence, and evidence comparison.
Consumer/execution responsibility explicitly not acquired: LSP synchronization, snapshot retention, publication precedence, collection, edits, or reruns.
Decision: SPLIT — descriptive evidence belongs here; producer acquisition stays external.
```

Regression and handoff fixtures: `tests/test_diagnostic_member_evidence.py`.

### Source-backed diagnostic line correspondence

The canonical `CodeMap.source_observation(path, lines=[N])` can now include up to
32 explicitly requested **physical-line anchors**. Anchors are derived from the
same stable, visibility-checked source bytes and carry the canonical member
revision, exact byte-line SHA-256 digest, number of identical nonblank lines in
the fully observed member, and the explicit physical line number. No line text,
secondary repository history, or new persistent index is introduced. Blank,
out-of-range, denied, stale and unreadable lines remain unknown.

A caller retains the before and after source observations and supplies them
together with the corresponding external diagnostic observations:

```python
delta = RepositoryDeltaMixin.diagnostic_observation_delta(
    diagnostic_before,
    diagnostic_after,
    before_source=source_before,
    after_source=source_after,
)
correspondence = delta["diagnostics"]["source_correspondence"]
```

The optional projection describes `supported` source-line correspondences
separately from `unresolved` candidate reasons. It requires both source packets
to have complete line evidence, matching diagnostic generations, stable
revision-verified member bytes (never `stale`), different canonical member
revisions from distinct admitted CodeMap generations, the same admitted path, the same nonblank
producer/repository/environment identity, eligible diagnostic
collection states, and explicit diagnostic scopes containing the source path.
If a producer supplies a source revision for that path, it must match the
corresponding canonical member revision. A contradictory claim leaves the
candidate unresolved with `diagnostic-source-revision-mismatch`; malformed
claims are rejected. Omitted revision claims keep the existing generation-bound
correspondence semantics and are never backfilled from a source observation.

The repository-wide freshness axis remains explicit: a directly read,
revision-verified member can support a **source-local** byte correspondence
even when daemon-wide freshness is `unknown`. In that case the supported row
includes both endpoint repository freshness states and does **not** upgrade
them to `current`. A source packet marked `stale` cannot support correspondence.

A candidate is supported only when its exact physical source line is
**byte-identical, nonblank and unique in both member revisions**, and its
diagnostic column remains unchanged. A preserved error message or shifted line
number is insufficient. Duplicated lines, changed content/columns, mismatched
generations, missing anchors or blocked observation fail closed with a reason.

`state: source-line-correspondence` means only that the same unique
source line can be located after the edit. It **does not claim the diagnostic
is the same semantic fault**, certify a fix, replace the strict diagnostic
identity, infer runtime behavior, or suppress raw added/removed rows. Source
correspondence is a descriptive projection from caller-retained endpoint facts,
not a stored history/merge/tracking engine. The byte-derivation helpers are
stateless; all source admission and freshness remain with the existing CodeMap
member owner.

### Diagnostic delta claim qualification

The diagnostic delta preserves raw `added` and `removed` identity comparisons;
these rows mean **seen in one supplied observation, not the other**. They are
not automatically evidence that the diagnostic appeared or was resolved.

`diagnostics.qualification` separately reports qualified and unqualified
identity lists. Claim qualification requires both observations to share a
nonempty repository identity, producer and environment identity; both must
represent executed `pass` or `fail` outcomes; and the diagnostic's
explicit path must be in both declared collection scopes.

A **newly observed** diagnostic is qualified only when the earlier collection
was `fresh-complete` and the later one was `fresh-complete` or
`fresh-partial`. A **no-longer-observed** diagnostic is qualified
only when the later collection was `fresh-complete` and the earlier
collection was `fresh-complete` or `fresh-partial`.
Timeout, blocked execution, unavailable sources, source mismatch, unknown
coverage, absent scope, or changed environment never prove absence.

All collection qualifiers are **producer-claimed**, not independent verification
of the producer, causal error resolution, source-span continuity, or execution
authority. The strict existing diagnostic identity and non-authoritative
possible relocation projection remain unchanged.

## Existing owners and non-goals

`RepositoryDeltaMixin` retains the public diagnostic methods. Their pure
normalization and comparison owner is `codemap/diagnostic_observation.py`;
`diagnostic_provenance.py` owns bounded member claims and
`diagnostic_path_delta.py` owns conserved path projections. Canonical member
observation, repository indexes, and freshness remain with their existing
owners.

No new daemon protocol, persistence schema, source corpus, agent-call cache,
workflow state, native verifier invocation, model tool-routing rule, or
history/branch/merge authority is introduced.

## Qualification

Regression tests: `tests/test_source_observation_evidence.py`,
`tests/test_diagnostic_member_evidence.py`, `tests/test_diagnostic_source_revisions.py`,
and `tests/test_mcp_endpoint_comparison.py`.

Relevant negative scenarios include denied source, unchanged repeated observations,
unreconciled same-path replacement, byte-size ceilings, partial location results,
Unicode/CRLF source shape, shifted diagnostics, ambiguous same-message diagnostics,
and invalid collection states.

Runtime/benchmark scores are separate from the repository evidence contract.
