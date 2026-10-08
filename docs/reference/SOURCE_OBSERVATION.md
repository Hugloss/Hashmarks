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

This is currently a Python CodeMap API. No new MCP tool, CLI command, or execution
backend is implied by its presence.

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

This remains a Python CodeMap evidence surface. It does not change the MCP
tool roster, cause editor actions, schedule verification, or make a new source
index.

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
