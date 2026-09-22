# Masked Splunk CSV dogfood — 2026-09-22

## Authority

This dogfood campaign started from Hashmarks `main` at:

- commit: `d3e017476c3789360986120b8c2b63cb87c80aeb`
- branch: `context-economics-csv-stress-20260921`
- original pre-rebase branch head preserved at:
  `archive/context-economics-csv-stress-20260921-pre-rebase`

The retained masked Splunk export is external test evidence and is not committed to
the repository.

Exact masked export identity:

- size: 37,287,516 bytes
- SHA-256:
  `4064bf366fb1f3de943737cee93182db76a6c90d8bf4c3bc8aba2922183bae1f`

## Boundary

Hashmarks remains a repository/evidence correlation product, not a log ingestion
platform.

The producer-side dogfood adapter lives under `scripts/agent_evaluation/`. It:

- streams the external CSV;
- preserves exact source identity;
- reports strict/recovered parsing state;
- produces bounded normalized anchors;
- preserves Python traceback path/line/symbol evidence;
- aggregates repeated module observations;
- never uses Splunk `_serial` as event identity;
- never infers causation, diagnosis, incident identity, or repair authority.

The normalized bundle is then passed to the existing
`CodeMap.correlate_evidence(...)` repository owner.

## Real-data observations

The exact masked export produced:

- 131,854 logical events;
- 137,887 physical lines;
- 130,577 strict-valid CSV records;
- 1,277 recovered records;
- 0 unrecoverable logical records in the bounded fallback;
- 336 widened records caused by malformed quoting/commas in `_raw`;
- 7 Python traceback frame observations;
- 9 observed `name=` module identities.

The export also proved that `_serial` is not globally unique, so event identity
is instead bound to event ordinal plus SHA-256 of the exact logical record.

## Defects exposed and repaired

### 1. Recovered traceback frames were being discarded

Real malformed quoting transformed traceback text enough that the initial strict
traceback pattern missed all seven frames.

Repair:

- tolerate the quote damage produced by the bounded CSV recovery path;
- preserve the external runtime path, line number, and function name;
- prefer traceback anchors over weaker module-only anchors when the anchor budget
  is tight.

Focused regressions cover both malformed quoting and explicit path mapping.

### 2. Final physical line was under-counted

The export does not end with a newline. Counting physical lines only from newline
characters under-reported the source by one line.

Repair:

- count a non-empty final unterminated line explicitly.

A focused EOF regression preserves the exact behavior.

### 3. Correlation identity depended on caller anchor order

Reversing the same normalized external evidence anchors produced a different
`correlation_identity`.

This was a Hashmarks core defect, not an adapter defect.

Repair:

- canonicalize anchors within each bundle by `anchor_id`;
- preserve semantic producer ordering only when the producer explicitly carries
  that ordering in metadata or provenance;
- document container order as presentation-only.

Focused regression:
`test_anchor_reordering_within_bundle_does_not_change_correlation_identity`.

An existing module-correlation test was updated to address anchors by canonical
identity instead of relying on caller input order.

## Exact wheel replay

CI run #968 built an exact consumer wheel from branch head
`7a1181b6ac1967391df8d22fa5b401274a2f7927`.

Artifact identities:

- workflow artifact ZIP SHA-256:
  `2a36728301b6c7a7288bfde375d0e10feabcb05098cbf9254ddbf33be288ecba`
- wheel SHA-256:
  `f537e01b58fcbeeefc05acb746bc1442ea8b181313f1e18063bd57b2667f7d80`

Using that exact wheel:

- reversing the ten real-shape anchors produced the same
  `correlation_identity`;
- nine repository-backed anchors resolved uniquely in the synthetic repository;
- external `httpx` remained unresolved instead of being fabricated;
- the traceback
  `/app/src/utils/__init__.py:280 process_output_data` resolved uniquely through
  explicit `/app/src -> repository root` mapping;
- authority remained `repository-intelligence-only`;
- interpretation authority remained `consumer-owned`;
- causation remained `not-inferred`;
- caller-declared completeness remained `unknown` and therefore negative
  evidence was not admitted.

## Qualification state before final CI

On the canonical-order semantics, CI #968 proved:

- Python 3.11 tests: PASS;
- Python 3.14 tests: PASS;
- release qualification environment: PASS;
- repository evidence binding diagnostics: PASS;
- workspace authority diagnostics: PASS;
- MCP minimum/latest supported lanes: PASS;
- pre-commit: PASS;
- consumer wheel build: PASS.

The only failing authoritative lane was the fast validation gate due to one Ruff
formatting-only line in the new EOF regression. That exact formatter output was
applied after the semantic lanes completed.

Final merge authority must come from a subsequent clean CI run on the final head.
