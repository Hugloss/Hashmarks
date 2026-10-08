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
  current, complete, stable canonical member observation; it does **not** prove
  the LSP read those bytes or that repository-wide verification is current.
- **different** means the observed member bytes differ from the claimed
  source revision; it does **not** decide whether or how to rerun verification.
- **unknown** means absent/ambiguous source packets, unreadable/denied/oversized
  source, incomplete/truncated source evidence, unsupported source schemas, or
  stale/unknown repository freshness. It is not a file-absence assertion.

Diagnostic collection outcomes and repository generation remain separate;
different diagnostic/source generations are exposed without inventing
cross-generation history. The comparison is **caller-retained endpoint
evidence**, not an independently authenticated execution trace. Its
`complete-for-declared-members` coverage applies only to the claimed member
set, not every source file or diagnostic path. Unclaimed diagnostic paths and
ignored source packets are counted separately.

The producer owns acquisition timing and LSP document versions; the agent
harness owns read/edit coordination, verification execution and decisions.
Hashmarks keeps only descriptive revision correspondence, reusing its existing
member observation and diagnostic normalization. No persistent history, LSP
engine, external runner, or ninth MCP tool is added.

Regression tests: `tests/test_diagnostic_source_revisions.py`.

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

All new facts stay within `RepositoryDeltaMixin` and its existing canonical
member observation, repository index, freshness, and diagnostic-delta owners.

No new daemon protocol, persistence schema, source corpus, agent-call cache,
workflow state, native verifier invocation, model tool-routing rule, or
history/branch/merge authority is introduced.

## Qualification

Regression tests: `tests/test_source_observation_evidence.py`.

Relevant negative scenarios include denied source, unchanged repeated observations,
unreconciled same-path replacement, byte-size ceilings, partial location results,
Unicode/CRLF source shape, shifted diagnostics, ambiguous same-message diagnostics,
and invalid collection states.

Runtime/benchmark scores are separate from the repository evidence contract.
