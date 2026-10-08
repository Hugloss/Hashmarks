# Evidence format qualification

This is an **experimental export and score aggregation** boundary; it does not
launch an agent and cannot assert which evidence format an agent prefers.

Use frozen repository evidence and the same held-out prompt across four arms:

* `native-json`: original producer packet.
* `typed-json`: structured typed finding projection.
* `compact-json`: bounded finding projection.
* `grouped-text`: concise, assertion-labeled finding text.

The arms may carry **different information densities**. Do not attribute a gain
to encoding alone without a separate information-matched experiment.
Do not put an oracle, answer key, or grading metadata into agent tool payloads.

A sample manifest contains `cases`, each with `id`, `prompt`, and
`packet` (the existing schema-bearing Hashmarks producer response). Optionally
keep an `oracle` outside the exported arm: it is not transported.

Export with the repository's locked uv environment:

```bash
uv run --frozen -m scripts.agent_evaluation.agent_evidence_format_study emit \
  --input evidence-cases.json --output evidence-trials.jsonl
```

Run the generated trials through agentsCookbook or another *external* agent
harness. Grade answers against held-out task truth, not against Hashmarks's
presentation wording. Record model, case_id, variant, correct (boolean),
unsupported_claims (nonnegative integer) and tokens (nonnegative integer).
Include nonresponses and failures in the harness's authoritative report;
do not reclassify them as correct.

For the exact, complete paired subset, aggregate already-graded run records:

```bash
uv run --frozen -m scripts.agent_evaluation.agent_evidence_format_study summarize \
  --input external-grades.json --output format-comparison.json
```

The result names incomplete pairs excluded from the paired comparison. It does
not issue a winning-format recommendation. Compare correctness, false claims,
actual total tokens, tool calls and wall time in the external harness before
choosing any default. Test more than one agent/model and include ambiguous
symbols, shifted diagnostics, stale/partial observations and real dependency
upgrades. Preserve both the original packet and exact answer traces for review.
