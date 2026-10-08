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
        "src/example.py", literal="example", limit=50,
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

## External diagnostic collection and correspondence (H2)

```python
from hashmarks.codemap.repository_delta import (
    RepositoryDeltaMixin,
    RepositoryGenerationBinding,
)

before = RepositoryDeltaMixin.external_diagnostic_observation(
    producer="pyright",
    binding=RepositoryGenerationBinding("repository-id", 7),
    diagnostics=[{"tool": "pyright", "rule": "E1",
                  "path": "src/example.py", "line": 10,
                  "message": "Undefined variable"}],
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
