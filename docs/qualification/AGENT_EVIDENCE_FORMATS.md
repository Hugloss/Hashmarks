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

## Frozen trial identities and host-capture reconciliation

Every emitted trial has a deterministic `trial_identity` SHA-256 digest of
its case, variant, prompt, axis, source schema, and exact `tool_response`.
This is **experimental payload identity**, never repository evidence authority,
a signed receipt, a host attestation, or evidence of model comprehension.
Changing a payload after emission invalidates that trial identity.

External harnesses may supply `--captures host-captures.json` when summarizing
grades. The JSON array contains one record per received variant and model:

```json
{
  "case_id": "candidate-not-move",
  "model": "model-a",
  "variant": "compact-json",
  "trial_identity": "sha256:<digest-from-exported-trial>",
  "model_visible_response": "<exact UTF-8 text handed to the model>"
}
```

The model-visible text is recorded by the **consumer harness**, not generated
by Hashmarks. Missing, duplicated, mismatched or unexpected capture identities
cannot silently become verified evidence. A capture may be at most 1 MiB in UTF-8.
For `production-response`, the model-visible text must parse as JSON with
content equivalent to the exported native response; this is not byte-for-byte
rendering identity, and host formatting can still affect tokens. For
`encoding-only`, the entire visible text must match the selected encoding
exactly (including whitespace and field order). A different string cannot be
credited as evidence for the claimed encoding. The audit retains the SHA-256
digest of each *exact captured UTF-8 text*, independently of the semantic
content comparison, so host text reformatting remains visible to reviewers.

Results distinguish **all externally graded complete pairs** (`arms`) from
`capture_equivalent_arms`, whose *every* variant in the pair has an equivalent
host capture. Missing or differing captures remain explicit. Without
`--captures`, the capture audit and equivalent-pair count are null, **not
zero verified pairs**. The audit's authority is
`consumer-supplied-capture-content-only`: Hashmarks cannot independently
authenticate the execution host, verify the model actually saw the bytes, or
grade the answer. The external harness must persist its own native trace,
host delivery evidence and answer oracle. Treat any equivalence result as a
reproducibility check, not a causal explanation or a format winner.

## Fixed MCP exposure for format comparisons

Hashmarks now supports optional binding to the explicit MCP tool projections
introduced by the canonical MCP projection contract. For a controlled
format-only study, use the `projection` object from
`hashmarks doctor --mcp --mcp-tool find --mcp-tool task_evidence` as the
top-level `mcp_projection` in the export manifest. It is normalized to its
canonical `schema`, `source_contract_identity`, ordered `tools`,
`instructions`, and `projection_identity` fields. Invalid projections,
unknown tools, duplicate tools, arbitrary instructions and forged identities
fail admission. The same projection is frozen into every format arm and its
`trial_identity`; the tool response itself does not gain experimental
metadata.

For a projection-bound case, each consumer-supplied host capture also provides:

```json
{
  "observed_tools": ["find", "task_evidence"],
  "observed_contract_identity": "sha256:<contract-digest>",
  "observed_projection_identity": "sha256:<projection-digest>"
}
```

These fields are added to the `model_visible_response` capture envelope
documented above. A pair enters `capture_equivalent_arms` only if *every*
variant has both content-equivalent response bytes (according to the study
axis) **and** an exactly matching observed tool catalog, contract identity,
and projection identity. Unknown, reordered, omitted or extra observed tools
cannot masquerade as a controlled format experiment. Content and catalog
failures are reported separately: `content_mismatches` versus
`projection_catalog_mismatches`. Missing projection reports leave the
format pair unqualified; an unprojected legacy manifest reports a null
projection-equivalent count, not false proof of verified tool exposure.

This is **not** tool-exposure ablation: format comparisons must hold one MCP
projection constant across every case and arm. Actual ablation with different
tool catalogs is a distinct experiment in the external harness, which owns
runtime model execution, assignment, trajectory evidence and correctness.
Consumer-reported catalogs are not authenticated MCP transcripts. Hashmarks
checks internal consistency with the frozen experiment, not whether the host
honestly reported what the model saw.

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
  --model model-a --model model-b \
  --captures host-captures.json --output production-comparison.json
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
