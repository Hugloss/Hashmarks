# Repository-evaluation scripts

These scripts are **developer/research measurement tools**, not Hashmarks product runtime.

They make repository-intelligence experiments reproducible across Hashmarks itself and external repositories that consume Hashmarks. They do not own agent execution, process retry, scheduling, certification, or experiment orchestration.

Use them from a Hashmarks checkout and point `--workspace` at the repository under study. Keep the public case manifest separate from grader expectations so expected answers are never passed into `CodeMap`.

Example:

```bash
uv run --frozen python -m scripts.repository_evaluation.run_cases \
  --workspace /path/to/repository \
  --cases benchmarks/repository_evaluation/manifests/exact_identifier_ownership.cases.json \
  --receipts .hashmarks/repository-evaluation/receipts \
  --output .hashmarks/repository-evaluation/run.json

uv run --frozen python -m scripts.repository_evaluation.grade_cases \
  --run .hashmarks/repository-evaluation/run.json \
  --grader benchmarks/repository_evaluation/manifests/exact_identifier_ownership.grader.json \
  --output .hashmarks/repository-evaluation/report.json
```

`.hashmarks/` is already ignored by Git and is the default place for generated run state. Long-running hosted experiments may persist exact completed receipts/evidence capsules outside the ephemeral runtime, but that persistence remains external to Hashmarks product authority.

A receipt is reusable only when protocol, repository identity, producer implementation identity, and case identity match. Any reused receipt makes aggregate timing non-comparable to a clean run.

## Stable correctness and performance lanes

Correctness runs may be split with `run_cases.py --shard-count N --shard-index I`.
Each shard uses an isolated CodeMap state directory under the external receipt
root. `merge_runs.py` accepts only identity-compatible shards and rejects
missing/duplicate membership. Grading distinguishes false-safe/false-unique
from conservative ambiguity and records the failure stage from retrieval to
action projection.

Performance is deliberately separate. `profile_cases.py` uses warmups plus
repeated clean samples and records median, p95, MAD, and a semantic fingerprint.
Use a same-version repeat as `compare_profiles.py --repeat ...`; an apparent
speedup that does not exceed the observed same-version noise floor is
`NOISE_BAND`, not a performance win. Never compare receipt-reused correctness
wall time as performance evidence.

## Retrieval ordering characterization

`retrieval_order_characterization.py` owns evidence for capped broad-candidate
ordering. It deliberately does not rewrite product SQL. The characterization
compares independent cold indexes with an edit/revert ABA history and records
whether identical repository content can produce a different visible fallback
retrieval subset. A `STABLE_CONTRACT_REQUIRED` decision is correctness evidence,
not permission to treat an ordering rewrite as a transparent optimization.
