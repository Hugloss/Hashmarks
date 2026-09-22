# Repository quality qualification

Hashmarks repository-quality qualification is development measurement infrastructure.
It evaluates frozen product evidence; it does not grant edit, execution, or release
authority to an agent.

## Ordering

Quality is compared lexicographically:

1. benchmark integrity and ground-truth authority;
2. zero false authority;
3. evidence sufficiency and overclaim correctness;
4. abstention correctness;
5. useful resolution coverage;
6. projection, generation, and provenance fidelity;
7. retrieval, verification, and evidence quality;
8. metamorphic and semantic stability;
9. economics.

Lower levels never compensate for a failure at a higher level.

## Ground truth

A case separates repository semantic truth from the evidence admitted to Hashmarks.
A unique owner with insufficient admitted evidence is expected to remain unresolved;
that is not a missed-resolution defect. The hard missed-resolution counters apply only
when admitted evidence is sufficient.

Missing measurements are unknown, never zero. Every validated ground-truth case receives a deterministic SHA-256 identity over its complete canonical JSON payload. Reports also carry an order-independent corpus identity over the exact evaluated case identities, so adding, removing, or relabeling a case changes the qualification evidence identity rather than silently changing the benchmark beneath a score.

## Benchmark readiness

Benchmark health is evaluated before product quality. Every case binds a ground-truth
status, corpus class, lifecycle, task family, risk class, and label basis. Only active,
valid qualification cases are score-bearing. Shadow, canary, fresh-dogfood, historical,
and superseded cases remain evidence but cannot silently change the qualification score.

An empty or non-score-bearing corpus is `benchmark-not-ready`. Invalid cases also make
the benchmark not ready. Ambiguous or insufficient ground truth requires
`needs-adjudication` before the harness may report `qualified` or `not-qualified`.
These are evaluator states, never edit or release permissions. Qualification also requires minimum active coverage of the critical semantic slices: unique owner, true ambiguity, non-edit, and explicit test edit. Missing a critical slice makes the benchmark not ready; zero observed violations in an unrepresentative corpus are not evidence of qualification.

## State confusion and abstention

The evaluator records one canonical semantic-truth × admitted-evidence × reported-state
confusion table for score-bearing cases. Abstention quality is derived from that table
and the same evaluated rows rather than from a second authority classifier. Reports
include true-ambiguity precision/recall, justified and unjustified unresolved rates,
and non-edit specificity. Hard-zero authority counters remain the non-compensatory
gates; positive abstention metrics describe usefulness after those gates.

## Hard-zero authority metrics

The canonical vocabulary is owned by
`scripts/agent_evaluation/repository_quality.py`. Authority violations are
non-compensatory qualification vetoes. Positive coverage and ranking metrics are
reported only after those gates.

The first implementation intentionally does not add a global numeric quality score,
product confidence probability, or agent permission state.

## Batched qualification stack

The qualification case now binds the benchmark registry, ground-truth schema, metric
policy, qualification policy, evaluation profile, and proof mode into its immutable
case identity. Profiles are descriptive evidence-use classes
(`navigation.v1`, `change-support.v1`, `release-critical.v1`), never permissions.

Reports distinguish the identity of the full evidence set from the active score-bearing
qualification corpus. Adding a shadow, canary, fresh-dogfood, historical, or superseded
case therefore changes the evidence-set identity without silently changing the
qualification-corpus identity.

Positive quality is sliced by task family, risk class, and evaluation profile. Ranking
quality is diagnostic and reports Recall@1, Recall@5, and MRR for owner and verification
ranking observations. Ranking never grants ownership or verification authority.

Stability observations cover paraphrase owner stability, retrieval-bound owner stability,
projection authority stability, and generation authority stability. Missing observations
remain unknown. Proof-mode coverage reports unit, boundary, lifecycle, adversarial, and
mutation evidence separately rather than treating raw test count as proof strength.

Economics are deliberately last in the lexicographic stack and diagnostic only. The
initial surface records sample counts and bounded observed latency, inspected rows,
candidate counts, and peak memory; absent measurements remain unknown.

## Second batched qualification stack

The next ten qualification increments are deliberately carried in one integration batch:
active-qualification adjudication is separated from diagnostic corpus health; reviewer and
adjudication provenance are identity-bound; producer, receipt, selection-membership,
required-provenance, command-conflict, synthetic-command, and false-premise authority
violations are hard vetoes; ranking adds nDCG; evidence-retention diagnostics cover
dependency, impact, call, import, and verification surfaces; metamorphic family
membership is explicit; and economics can be compared only with recorded environment
fingerprints and cold/warm/incremental modes.

Shadow, canary, fresh-dogfood, historical, and superseded cases remain visible diagnostics
but do not block qualification until promoted into the active qualification corpus.
This prevents exploratory evidence from silently becoming release authority while
preserving it for review and later promotion.

## Next increments

The same evaluator will be extended with:

- independent label review/adjudication metadata and corpus-registry manifests;
- descriptive uncertainty for positive metrics once the baseline corpus is large enough;
- projection/generation/provenance observations derived directly from frozen public outputs;
- nDCG and richer evidence-retention metrics after ranking ground truth is available;
- metamorphic family execution against frozen repository generations;
- selected mutation challenges for high-risk authority invariants;
- retained real-world cases including Oh-Goon 1267.0.993 / Hashmarks #67;
- economics environment fingerprints and cold/warm/incremental comparability.

This infrastructure remains separate from Hashmarks runtime authority.
