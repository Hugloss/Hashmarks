# Backend E2E campaign

This is Hashmarks development qualification, not product execution or
certification authority. The target is independently supported 5/5 evidence
for all twenty backend capabilities. Current corpus membership is not a claim
that those capabilities have passed.

## Expected membership

The frozen campaign is
`benchmarks/repository_evaluation/manifests/backend-campaign-v1/campaign.json`.
It binds the three existing suites and their source-oracle digests. The shared
active schemas are `hashmarks.backend-evidence-campaign.v2` and
`hashmarks.backend-evidence-matrix.v3`; older reports are historical evidence.
The directory name identifies the frozen source corpus, not the active report
schema version. The shared
matrix owns the unchanged minima: twelve distinct genuine problems and three
repositories per capability. Formats and repeated variants do not add breadth.

| Capabilities | Existing catalog | Problems | Repositories |
| --- | --- | ---: | ---: |
| 1, 3, 5, 6, 7, 17 | backend-v1 | 12 | 3 |
| 10 | backend-model-v1 | 12 | 3 |
| 12 | backend-async-v1 | 12 | 4 |
| 2, 4, 8, 9, 11, 13, 14, 15, 16, 18, 19, 20 | No admitted campaign suite yet | 0 | 0 |

Separate debugging, dependency, heldout and native captures do not automatically
fill those rows. Their precise problems, semantic oracles and transport proof
must be admitted before they contribute.

## Observation contracts

Each workflow retains both stages, full/default and explicit initial profiles,
API packets, actual CLI/MCP responses, byte/token measurements and source delta.
Required observations use failure-preserving three-state composition:
known false dominates missing; missing is incomplete; an empty set is not proof.
Initial compact/text replies have a hard 4,000-token ceiling, counting the entire
actual CLI or MCP reply. Initial MCP carries one native v2 packet plus its
readable projection. Recall is a separate measurement. Every capability now
requires presentation preservation, rather than only capability 17.

Debugging correspondence uses frozen `debug_frame_units` and per-unit
`debug_frame_observations`, not one boolean per problem. Each observation has
`unit_id` and `correspondence` (true, false or null). Frame identities are local
to the repository and genuine problem; variants and transports cannot add units.
Missing reviewed units remain incomplete even if a summary boolean says true.
Recall fails when its best possible result cannot reach the threshold, otherwise
missing units remain incomplete. JSON oracle comparisons distinguish boolean,
integer and floating-point values recursively.

An optional stage-specific `owner_oracle` describes `scope` (`file` or `symbol`),
`resolution` (`unique`, `ambiguous` or `unknown`) and `candidates`. Symbol
candidates require path, qualified name and exact start/end lines bound to an
independent source label. A legacy path label alone cannot qualify an exact
symbol assertion. `initial_checks` must be independently frozen; their absence
is not a successful initial-evidence measurement.

Workflow v2 `transitions` entries carry `kind`, `before_path` and `after_path`.
Additions have a null before endpoint; deletions have a null after endpoint;
modifications keep the same path with changed bytes; renames explicitly nominate
different paths. `changed_paths`, when provided, must equal the endpoint union.
Sources remain immutable; workflow copies are disposable.

Native preparation includes all labelled files and only genuinely reviewed
optional verifiers. Explicit `native_observations` may nominate stage-specific
`language` and `paths`. Python and TypeScript specimens use their respective
installed producers. Native v3 reports retain source identities, observation
artifact hashes and capture artifact hashes. Their scope remains source binding
and native transport; they cannot prove an execution path or verifier recall.
Reports require every target's API/CLI/MCP and definition-token artifacts plus
exact target membership. Aggregation recomputes native gates from those bytes;
a supplied passing summary is not qualification proof. Disposable stage source
membership comes from the union of nominated files in the actual pinned trees,
not from the producer's selected capture files. An unchanged file can have a
matching source binding while its old capture remains generation-stale; neither
dimension strengthens the other.

## Remaining implementation tickets

The repair and disclosure foundation is implemented, but this campaign is not
5/5. Complete these dependencies before making that claim:

1. Freeze independently reviewed owner, essential-initial, display and authority
   oracles for each existing genuine workflow; migrate active workflow contracts
   to v2. Explicit-target variants do not count as blind-owner recall.
2. Finish source-bound gate witnesses and shared pure regrading for all claim
   families. Bind every admitted test, callee, diagnostic frame and declaration
   source revision, not only the candidate owner file.
3. Qualify every prior native target across unchanged/modified/deleted and
   capture-scope transitions. Separate fresh acquisition from replay. Missing
   producers or unsupported token encodings are incomplete, not passing proof.
4. Add independently admitted genuine corpora for the twelve missing capability
   rows above, including real failures, contracts, messaging, transactions,
   dependency/build transitions and declared cross-repository boundaries.
5. Repair each demonstrated source/verification omission generically through its
   existing observer owner; do not put oracle names or framework exceptions in
   production ranking or analysis.
6. Freeze comparable cold/warm/incremental/churn economics after correctness
   repairs, then measure five paired samples and same-version noise controls.
7. Requalify all twenty rows, all stages/profiles/formats/transports, genuine
   native/dependency rings, heldout owners, bounded development batches and the
   final independent source artifact. Preserve FAIL and INCOMPLETE until that
   exact evidence exists.

## Read-only aggregation

Run each suite through the existing entrypoints. `BACKEND_SUITE` selects the
suite without duplicating Make targets. Use distinct output directories for
different candidate identities.

```sh
make backend-evidence-dogfood \
  BACKEND_SUITE=benchmarks/repository_evaluation/manifests/backend-model-v1/suite.json \
  BACKEND_SOURCES=/absolute/path/to/model-sources.json \
  BACKEND_OUTPUT=/absolute/path/to/model-report
```

Supply a sources JSON mapping campaign source IDs to exact extracted trees.
Supply a reports JSON keyed by campaign suite IDs:

```json
{
  "backend-v1": {
    "workflow_report": "/absolute/path/to/workflow/summary.json",
    "native_report": "/absolute/path/to/native/summary.json",
    "capture_root": "/absolute/path/to/native-captures"
  }
}
```

Missing suite reports remain incomplete. Optional native report fields are
required when native proof is supplied. The aggregator validates current
observer/evaluator identity, pinned source/oracle identity, completed receipts,
retained artifact bytes and native acquisition/binding scope. Historical v1
native reports cannot provide the newly required v2 artifact proof.

```sh
uv run --frozen python -m scripts.repository_evaluation.aggregate_backend \
  --campaign benchmarks/repository_evaluation/manifests/backend-campaign-v1/campaign.json \
  --sources-file /absolute/path/to/campaign-sources.json \
  --reports-file /absolute/path/to/reports.json \
  --output-dir .hashmarks/backend-e2e/campaign/aggregate
```

The command emits `summary.json` and `summary.md`. It only reads admitted
measurements; it never launches producers or selected work. Exit zero requires
the complete campaign to pass. Rejected or incompatible inputs cannot qualify.

## Remaining work before 5/5

1. Review explicit owner scopes and essential initial facts for existing cases.
2. Finish scoped authority checks for every exact relationship family and freeze
   eligibility for blind owner, debugging-frame and initial-recall measurements.
3. Qualify genuine add/delete/rename workflows, beyond controlled regressions.
4. Extend native qualification to every nominated required target and prove
   unchanged bindings separately from deliberate invalidation adversaries.
5. Admit runtime-debugging, dependency, language and economics measurements under
   matching identities and scopes; do not substitute SCIP binding proof for them.
6. Reduce actual initial MCP size without losing admitted verifier alternatives,
   source facts, uncertainty or omission accounting. Readable text alone does
   not close the size requirement.
7. Repair reproduced generic verification misses using qualified identity and
   locality rather than oracle hints or larger retrieval bounds.
8. Complete the twelve missing capability catalogs with twelve genuine problems
   across three repositories each, reviewed independently of candidate output.
9. Run current fresh native captures, all CLI/MCP formats, comparable economics
   controls and the complete campaign aggregate.
10. Complete configured lint/type checks, deterministic bounded regression
    batches and the repository's final artifact qualification.

Do not mark this campaign complete while any required proof is missing or any
hard authority, freshness, presentation or initial-size violation remains.
