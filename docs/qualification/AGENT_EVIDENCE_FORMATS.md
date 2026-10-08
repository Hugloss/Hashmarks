# Evidence format qualification

This experiment exports frozen evidence and aggregates external grades. It
launches no agents, issues no winner, and cannot establish comprehension gains
from byte savings alone. Model execution and grading remain external.

## Two distinct study axes

`production-response` reproduces the live response shape. Its four arms are
`native-json` (`none`), `typed-json` (`structured`), `compact-json` (`compact`),
and `grouped-text` (`text`). Formatted responses retain the canonical native
result alongside their presentation. Query responses retain their query envelope
and owner-derived query identity. This measures the actual optional product
contract, including information density and envelope overhead.

`encoding-only` renders one compact selection three ways: pretty JSON,
minified JSON, and grouped text. All three retain the same selected records,
qualifications, identities, references, and exclusions. Raw native JSON is not
an information-matched arm. Neither experiment rescans the repository between
arms.

A manifest contains `cases`, each with unique `id`, `prompt`, and a frozen
schema-bearing `packet`. Production cases also require `operation` and
`result_mode` describing the canonical native response. A query case supplies
the native query envelope, including its `surface` and `result`. Grading oracles
may remain in the input case metadata but are never exported into trials or
model-visible tool responses.

```bash
uv run --frozen -m scripts.agent_evaluation.agent_evidence_format_study emit \
  --axis production-response --input evidence-cases.json \
  --output production-trials.jsonl
uv run --frozen -m scripts.agent_evaluation.agent_evidence_format_study emit \
  --axis encoding-only --input evidence-cases.json \
  --output encoding-trials.jsonl
```

## External execution and grades

Use agentsCookbook or another external harness to run held-out prompts against
at least two models. Preserve the exported trial, actual serialized MCP/host
response delivered to the model, answer trace, and grading evidence. The export
alone is not a measurement of what a host ultimately exposes.

Each grade names `case_id`, `model`, and `variant`. `status` is `completed`
(default), `failure`, or `nonresponse`. Completed responses require boolean
`correct`; failures and nonresponses count as incorrect. `tokens` and
`unsupported_claims` are nonnegative integers or null/missing when unknown.
Booleans are not integer metrics. Unknown metrics remain unknown rather than
becoming zero. Other costs, tool calls, redundant reads, and wall time remain in
the external harness report.

Summarization requires the emitted trial manifest and explicit expected models,
so an entirely missing case or model cannot disappear from the denominator:

```bash
uv run --frozen -m scripts.agent_evaluation.agent_evidence_format_study summarize \
  --input external-grades.json --trials production-trials.jsonl \
  --model model-a --model model-b --output production-comparison.json
```

The summary reports expected and complete pairs, names every excluded pair and
missing variant, and aggregates the complete paired subset. Every supplied grade
is validated, including excluded pairs. Duplicate or unexpected grades fail.
Partial metric sums are labelled observed sums with unknown-run counts; the
authoritative total stays null when any paired measurement is unknown.

Use ambiguous owners, possible moves, shifted diagnostics, partial and stale
observations, qualified negative evidence, dependency version changes, body-only
revisions, and bounded projections in held-out cases. Review correctness and
unsupported claims before choosing defaults. No new default or demonstrated
agent benefit follows from the repository-only tests.
