# Standalone diagnostic-to-repository correspondence qualification

This receipt covers the Hashmarks-only HM-OBS-01..09 implementation. The starting
commit is `e36eb3944b3f4501d60225e8a68574e10b13c986`; the candidate is the local
working tree, not a published release or a merged/reviewed PR. Source identities,
JUnit hashes, exact selections and environment receipts live in `dist/hm-obs/`.
That directory is disposable qualification output, excluded from source control.
The frozen fixture, replay driver and regression tests are committed-source
artifacts and can regenerate evidence without another repository or service.

**Observer ownership: OBSERVER.** These changes qualify repository correspondence,
producer-claimed input, repository freshness and bounded evidence deltas. They add
no runtime sensor, target execution, log collection, consumer decision or durable
claim store. Repository freshness never attests producer freshness. Internal
cleanup is classified **REFACTOR INTERNALLY**: reuse existing semantic owners,
remove demonstrated dead wrappers, and avoid repeated stable reads; no ownership
is extracted merely to reduce file size.

## Checkpoint implementation and proof

| Checkpoint | Canonical implementation / result | Decisive evidence |
| --- | --- | --- |
| 01 | [Owner census](../plans/HM_OBS_REPOSITORY_EVIDENCE_OWNER_CENSUS.md): normalization → revision/line → correlation → ownership/dependency → existing public routes, persistence and duplicate review. | Exact pre-edit five-file 147-test selection; `baseline.json`, `baseline.xml`; selected defining-symbol/call references in `census-references.json`. This is a bounded inspected call-chain census, not a claim of exhaustive dynamic dispatch. |
| 02 | `diagnostic_observation.validated_diagnostic_endpoint` is reused by construction, delta, pure revision comparison and public validation. Finite JSON, bytes/cardinality/text/header/coordinate/scope/identity limits; detached input; deterministic duplicate treatment. | `test_diagnostic_envelope_contract.py`: malformed, oversized, conflicting duplicates, unsafe unlocated claims, authority/effect mutations, legacy v1 compatibility, MCP bypass attempts. |
| 03 | Existing member and `source_line_correspondence` owners retain exact physical bytes/revisions. Both columns may be omitted for a uniquely proven exact-line move. Existing import walk resolves alias declaration identity before call attribution; verifier owner composes qualified test callers. | Generated fixture plus source-line/revision suites: line/file moves, erased/replaced symbols, ambiguous names, CRLF/Unicode, direct/indirect renamed imports, actual test correspondence and stale claims. |
| 04 | `RepositoryDeltaMixin.external_observation_freshness` exposes repository-only freshness scope and unknown producer freshness; public validator rejects upgrades. Member, index, producer and comparison scopes remain distinct. | Current repository/stale producer; stale index/current claim; missing/partial source; deterministic concurrent edit rejection; existing `test_evidence_freshness_responsibility.py`. |
| 05 | Existing diagnostic delta retains unique fact identities, separate occurrence counts, changed producer metadata and separate source revisions/collection changes. Presentation retains claims without causal interpretation. | Duplicate counts, timestamp-only change, unavailable visibility without qualified removal, source revision mismatch; existing path-locality/source-line/delta negative cases and replay tests. |
| 06 | Existing `ImportResolutionMixin`, structural locality, task verification, dependency adapter/core and repository declarations remain separate owners. Re-exports retain exact declaration identity; declarations and lock observations preserve versions without a winner. | Local Python/pyproject/uv.lock fixture; unrelated same-name symbol; aliases/re-exports/indirect caller; changed dependency observation; incomplete cross-artifact declaration coverage; dependency resolution/derivation/uv suites. |
| 07 | Python, repository CLI, MCP surface/router and registered MCP tool retain the same core. Existing `evidence_comparison` adds paired source packets; no new tool. | Full-packet Python/MCP parity for task, locality, dependency, bindings, correlation and query routes; all four presentations through each supported CLI; source/endpoint parity; official SDK registration/forwarding, structured/compact/text claim preservation, MCP and public query suites. Unsupported CLI operations remain explicit rather than gaining another implementation. |
| 08 | Removed unused `diagnostic_path_locality.indexed_diagnostic_rows` and `RepositoryDeltaMixin._diagnostic_identity`. Pure source-revision comparison now shares endpoint validation. Exact-span captures reuse one request-local observation with per-binding copies and mutation checks. | Repository search found no callers/exports of removed private helpers. Canonical function binding assertions; byte-read instrumentation; changed-source and output-isolation regressions; existing authority/freshness/visibility/import-bound architecture guards. |
| 09 | Frozen local mini-repository, hard expected vectors, full golden packets, repeat identity checks, before/after source comparison and measured byte-read costs. | `tests/fixtures/diagnostic_correspondence/manifest.json`, `benchmarks/diagnostic_correspondence.py`, workflow/invariant tests, `economics-before.json`, `economics-after.json`, `economics-comparison.json`, JUnit and source artifact receipts. |

Tests are under `tests/`; implementation symbols above are under
`hashmarks/codemap/` unless stated otherwise. Existing correct behavior is qualified
by tests rather than replaced by another analyzer. No dependency resolver or
fixture program is executed to obtain claims; observations are fictional inputs.

## Public contract and internal convergence

The existing v1 diagnostic schemas remain. Additive delta fields are
`diagnostics.occurrence_counts` and `diagnostics.changed_claims`; legacy deltas
without them remain readable. Freshness adds `freshness_scope` and
`producer_freshness`. Invalid input that previously passed shallow normalization
now fails deterministically: strict header/coordinate types, finite bounded JSON,
row limits, conflicting same-fact metadata and malformed scope/revision claims.
This is validation hardening, not producer authentication.

| Before | Candidate |
| --- | --- |
| Unique fact counts obscure repeated occurrences. | Unique counts unchanged; explicit before/after producer occurrence counts. |
| Metadata changes under unchanged fact identity can disappear. | Full changed rows retained as producer claims; fact identity stays unchanged. |
| MCP comparison cannot forward paired source evidence. | Optional `before_source` + `after_source`, same validator and limits as Python. |
| Exact span repeated across opaque bindings rereads bytes. | One stable capture per exact span/request, independent outputs, end-of-request mutation check. |
| Imported alias spelling can lose the original declaration/test caller. | Existing bounded import walk carries exact declaration path/name; shadowed, hidden, cyclic or over-bound identities remain unresolved. |

See [source contract](../reference/SOURCE_OBSERVATION.md),
[bindings](../reference/REPOSITORY_EVIDENCE_BINDINGS.md),
[structural locality](../reference/STRUCTURAL_LOCALITY.md) and
[MCP](../integration/MCP.md) for limits and examples. Runtime freshness and cause
are outside scope. A diagnostic row lacking a safe location remains unlocated;
normalization never synthesizes a valid correspondence.

The removed helpers had zero repository callers: their forwarding/indexing work
is owned by `diagnostic_observation.diagnostic_identity` and its validated endpoint
index respectively. Re-export path ownership and exact callable declaration
ownership reuse `_OwnerWalk` but keep distinct qualification: outline evidence may
still establish its existing repository ownership relationship, while exact call
attribution cannot depend on hidden intermediate source. Later assignments do
not leave old declarations authoritative. The eight-hop/cycle guard remains.

Exact-span reuse is local acceleration, not another source authority/cache.
Canonical member admission and indexed digest still qualify each capture. Stamps
never become content identity. Mid-operation change raises `UnstableFileError`;
subsequent requests observe again. No persisted state/schema migration is needed.
Reverting the source changes restores the prior implementation without replaying
claims or changing consumer-owned state.

## Reproduction and evidence accounting

Use the committed lock and writable disposable caches:

```bash
export XDG_CACHE_HOME=/tmp/hashmarks-plan-cache
export UV_CACHE_DIR=/tmp/hashmarks-plan-uv
make init
uv run --frozen --offline --no-sync --group test python -m pytest -q \
  tests/test_diagnostic_repository_correspondence.py \
  tests/test_diagnostic_envelope_contract.py \
  tests/test_diagnostic_correspondence_workflows.py \
  tests/test_diagnostic_correspondence_invariants.py \
  --junitxml=dist/hm-obs/replay.xml
uv run --frozen --offline --no-sync --group test \
  python -m benchmarks.diagnostic_correspondence \
  --output dist/hm-obs/economics-replay.json
make agent-preflight
```

The original 147-test invocation and test IDs are in the historical census and
`baseline.json`, not inferred from a replacement count. New focused regressions
are additive; original baseline files, `pyproject.toml` and `uv.lock` are unchanged.
The pre-review supported-host checkpoint ring passed **347 tests**, zero failures/skips.
That earlier combined owner/contract/delivery ring passed **875 tests** with zero
failures/errors/skips; the subsequently added changed-verifier and six full-packet parity regressions
passed separately, giving **882 distinct passing tests** on that pre-repair candidate.
The current repair receipt supersedes that count; current validation is recorded
below. `qualification.json` records exact test IDs rather than summing overlapping runs. JUnit files preserve failed attempts as well as
corrected reruns; they are never silently relabeled PASS.

Named development batch 6 selected shards 24..27 of the repository's 64-shard
plan. On the supported host: shard 24 passed 84, shard 25 passed 62, shard 26
passed 64 and failed one, shard 27 passed 76. The failure is
`test_task_evidence_v5.py::test_natural_language_prefix_path_owner_does_not_drift_to_query_neighbor`.
It also fails on the untouched starting commit (`batch-failure-before.txt`), so
this batch is **not a green full-suite qualification**. Completed shards were not
repeated when finishing shard 27. The regression rings and baseline are distinct
from this wider pre-existing failure.

The restricted sandbox cannot bind the service Unix sockets or run the official
SDK coroutine path reliably. Supported-host reruns exercised those capabilities;
absence of sandbox capability was not counted as successful native qualification.
An initial owner-ring outline regression was repaired and rechecked against both
the original outline contract and exact-call visibility negatives. An invocation
that omitted the cache environment failed in the read-only home; it provides no
product proof. The final source archive also passed its independently extracted focused smoke
ring; the SDK-specific test is explicitly deselected there and was exercised in
the supported-host ring. Source-only evidence does not require external runtime/kernel
qualification; none is claimed. Optional SDK absence is an explicit pytest skip,
not an SDK PASS.

`make agent-preflight` passed full Ruff/formatting and zero complexity/size excess.
Focused ty and Pyright pass for new tests/benchmark; focused ty also covers the
modified diagnostic/import/line owners. Shared legacy modules still have existing
typing diagnostics: the same selection reports 57 error messages on the archived
base and 48 on the candidate, with no new message multiplicities. This comparison
is not a full-project typecheck PASS. `type-shared-*.txt` preserve exact diagnostics.

## Local economics and quality

Frozen fixture SHA-256:
`8d8918a171049a5ed064b69b63e30a8ababd8fcca0c9ba99f284f1b6c4c7e04c`.
The same benchmark file and fixture ran against an independent extraction of the
starting commit and the candidate, using the same interpreter/dependencies.
Six hard vectors pass on both. The candidate additionally proves the expected
direct call, indirect call and verifier correspondence; selected edit owner and
verifier remain correct on both. Every required boolean must pass; unrelated
positive results cannot compensate for a false owner or authority violation.

For five warm requests of sixteen independently named bindings to one exact
span, stable byte reads drop **80 → 5 (93.75%)** with identical binding evidence.
Latency is recorded in the raw paired receipts; a five-sample local measurement
does not establish a general speedup. Full packets include exact member/source
and producer identities. Workspace IDs intentionally differ between temporary
repositories; cross-run comparison checks frozen semantics and exact binding
facts, not fabricated equality of workspace identity. This is a single local
corpus and makes no claim about external fault diagnosis or runtime health.

## Review bundles

The changes are separable for review: A census/envelope guards; B source/revision,
freshness and delta preservation; C import/verifier and existing MCP parity;
D private-path removal, request-local read reuse and local qualification. Each
bundle's canonical owner and tests are named above. There is no consumer cutover,
foreign API deletion or external owner prerequisite. Publication, code review and
merge have not been performed by this local implementation receipt.


## Review repairs and current candidate

A subsequent review reproduced three gaps missed by the initial regression set.
The additional implementation closes them under the same repository-observer scope:

| Reproduction | Repair and regression |
| --- | --- |
| Overwritten exports still resolved exactly through aliases. | One ordered syntax classifier tracks unpacking, ordinary imports, deletion, augmented/conditional writes and annotation-only statements. Functions and classes use this qualifier. `test_diagnostic_correspondence_repairs.py` preserves unknown for invalidated bindings and retains valid current declarations. |
| Outgoing alias calls resolved while reverse callers were empty. | Bounded request-local reverse nomination over existing indexed import/reference rows, followed by the existing forward qualifier. The local fixture covers renamed relative re-exports, test callers, unrelated same-name symbols, hidden/ambiguous source, reference exhaustion and the eight/nine-hop boundary. |
| Python equality collapsed `true`/`1`, while tuple/list transport invented changes. | Immutable runtime-validated `CanonicalJsonValue` equality compares canonical bytes. Diagnostics and declaration values share it; detached decoding preserves ownership. New primitive, envelope, retained-header and MCP tests cover nested boolean/integer/float distinctions, duplicates, transport, invalid keys, non-finite values and cycles. |

This is a bounded shared-owner repair, not a repository-wide JSON/type-safety
audit. The value dataclass does not validate arbitrary consumer decisions or
replace kind-specific scalar guards. Existing v1 wire schemas remain; malformed
Python input with non-string object keys now rejects instead of undergoing key
coercion. The Python parser cache signature advances to v6 because relative
`from . import name` target spelling is now shared by indexing and qualification.
No persistent schema or alias registry is introduced; existing indexing invalidation
rebuilds outdated derived parse artifacts.

Current raw receipts are under `dist/hm-obs/repairs/`; the top-level
`qualification.json` and `source-artifact.json` identify the current candidate.
The handoff evidence ZIP preserves the original baseline, current JUnit, exact
selection/environment, source manifest, golden packets and comparable economics.
Keep that ZIP with a PR/CI artifact or other immutable handoff; ignored `dist/`
output will not accompany an ordinary Git commit. Previous receipts are historical,
not current qualification authority.

Replay the added repairs with the cache environment above:

```bash
uv run --frozen --offline --no-sync --group test python -m pytest -q \
  tests/test_json_value.py tests/test_diagnostic_correspondence_repairs.py \
  tests/test_diagnostic_envelope_contract.py tests/test_repository_declarations.py \
  tests/test_import_resolution_adversarial_bounds.py \
  --junitxml=dist/hm-obs/repairs/replay.xml
```


The shared value implementation is classified **EXTRACT RESPONSIBILITY**: JSON
representation/equality moves to `hashmarks/json_value.py`, which names its
responsibility and has direct behavioral tests in `test_json_value.py`. Diagnostic
and declaration admission, schema, identity and bounds remain in their original
owners, depending one way on the stateless value primitive. Six local JSON serialization sites now delegate to one canonical byte representation;
new nested-type and transport tests prove the correctness benefit. No global
cache or persisted value state is added. The class-syntax lookup is an internal
convergence onto the existing Python binding owner, not a file-size extraction.
The static filesystem consumer now uses canonical module-import bindings; its
obsolete `_module_imports` parser has no remaining callers and was removed.

The current expanded regression selection passed **1,159 tests**, with zero
failures, errors or skips. It covers the original 147-test baseline plus the
additional JSON, declaration, import, parser/cache, filesystem observer, CLI/MCP
and correspondence suites. An independent source extraction passed the same selection, including the
typing-only mixin clarification. After correcting this report's batch counts,
the final ZIP receives a focused extraction check; production, test and
configuration bytes match the full-run artifact. Both source manifests and
JUnit records are preserved.

Development batch 6 remains **NOT_GREEN**: shards 24 and 25 passed 81 and 78;
shard 26 passed 76 and failed the existing natural-language task-owner case;
shard 27 passed 71. The unchanged base reproduces that same failure. The earlier
filesystem observation regression was repaired, and the owning suite passes.
The batch's 306 passes and one baseline failure are not presented as a clean
full-suite run. No skipped native capability is counted as qualified.

Focused ty covers the shared value, diagnostic/declaration/import syntax owners
and their new tests; focused Pyright covers the value and new repair tests.
The broader shared-module typing comparison is retained separately rather than
claimed as a full-project typing PASS. Formatting, full Ruff and size/complexity
gates pass. The frozen seven-row v1 observation compatibility specimen produces
identical endpoint data and diagnostic fact identities on the archived base and
current producer (`repairs/v1-compatibility.json`).

The comparable read benchmark retains **80 → 5 stable byte reads**, all six local
vectors and all five owner/call/verifier checks passing, with identical exact
binding evidence. Raw latency remains reported without a general speedup claim.
`repairs/economics-comparison.json` records the final measurement; none of these
results certifies external diagnostic truth or runtime state.
