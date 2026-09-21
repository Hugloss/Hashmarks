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

Missing measurements are unknown, never zero.

## Hard-zero authority metrics

The canonical vocabulary is owned by
`scripts/agent_evaluation/repository_quality.py`. Authority violations are
non-compensatory qualification vetoes. Positive coverage and ranking metrics are
reported only after those gates.

The first implementation intentionally does not add a global numeric quality score,
product confidence probability, or agent permission state.

## Next increments

The same evaluator will be extended with:

- benchmark registry identity and label lifecycle;
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
