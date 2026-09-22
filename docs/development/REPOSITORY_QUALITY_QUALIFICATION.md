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

## Next increments

The same evaluator will be extended with:

- benchmark registry label lifecycle and independent review metadata;
- semantic-slice floors and minimum case counts;
- macro and micro positive metrics with descriptive uncertainty;
- projection/generation/provenance observations derived from frozen public outputs;
- verification relevance separate from verification authority;
- metamorphic families (irrelevant mutation, decisive evidence removal, duplicate
  owner introduction, stale/denied evidence);
- proof-mode registry: unit, boundary, lifecycle, adversarial, mutation;
- retained real-world cases including Oh-Goon 1267.0.993 / Hashmarks #67;
- economics with environment fingerprints and cold/warm/incremental states.

This infrastructure remains separate from Hashmarks runtime authority.
