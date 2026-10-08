# Agent-native evidence presentation and exposure

Hashmarks separates producer evidence from its presentation. Formatting is a
pure projection of an already observed packet: it performs no repository reads,
changes no producer identity, and acquires no reasoning or execution authority.

## Optional MCP formats

All thirteen current MCP tools accept `presentation` with the ordered values
`none`, `structured`, `compact`, and `text`. The default remains `compact` for
`repository_intelligence_query` and `none` for the other twelve tools.
Snapshot density (`compact`, `standard`, `audit`) is an independent selector.

`none` returns the native response unchanged. For the other tools, a selected
format returns this envelope:

```json
{
  "schema": "hashmarks.evidence-presentation-envelope.v1",
  "operation": "find",
  "result_mode": "default",
  "result": {"schema": "hashmarks.find.v2", "results": []},
  "presentation": {"schema": "hashmarks.evidence-presentation.v1"},
  "authority": "descriptive-only",
  "execution_effect": "none"
}
```

The example abbreviates the projection. `repository_intelligence_query` keeps
its existing query envelope: the canonical producer is `result`, with a sibling
`presentation`; it never receives a second envelope. Its own query identity
covers the requested presentation, while producer identities remain unchanged.
The warm service transports the selector; a requested format ignored by an older
service produces an explicit unsupported-presentation error.

The operation contract owns both presentation schemas. MCP advertises optional
presentation separately from native response modes and validates the enclosing
operation, result mode, native schema, projection schema, source identity,
selected format, and descriptive authority. Input schemas advertise enums for
presentation, query surfaces, and profile names. Tool names and read-only
annotations remain unchanged.

## Projection contract

Every displayed finding has `family`, via its group, plus `kind`, `assertion`,
`basis`, `details`, `source_refs`, and `source_context`. `details` retains the
exact native value, including locations, versions, targets, reasons, native
recommendations, and counter-evidence. `source_refs` are escaped JSON pointers
relative to the supplied producer packet. Flattened locators remain available.
Native recommendations remain attributed source claims; the renderer generates
no actions.

Subject families are `source`, `relationship`, `dependency`, `diagnostic`,
`verification`, `correspondence`, `qualification`, `repository_structure`,
`retrieval_evidence`, `ownership_evidence`, and `evidence_measurement`.
Assertions are independent: `observed_fact`, `observed_change`,
`candidate_correspondence`, or `producer_claim`. Dependencies, external
observations, and declaration correspondence retain caller/provider authority;
formatting never promotes them into repository truth or causality.

`source_schema`, `source_evidence_identity`, and `source_identities` refer to
existing producer identities and endpoint identities. When the producer has no
aggregate evidence identity, that field is null and `identity_limitation`
explains the limitation. The renderer never fabricates one. Qualification and
provenance are preserved in `source_context`, outside displayed-row caps.
Completeness, freshness, coverage, truncation, ambiguity, and negative-evidence
admissibility retain their native meanings and remain independent.

`structured` displays at most 48 findings per family; `compact` and `text`
display at most five. Arrays retain producer order; keyed mappings use sorted
keys so JSON transport cannot change the selection. Each group reports
`count_observed_in_packet` and exact `omitted_from_presentation`. These count
projected native records, not the repository universe. A compound native claim
retains its internal details; row caps are not byte or token budgets.
`coverage: projection-only` never proves repository completeness.
`unprojected_sections` names native sections not represented by a projector.
Unsupported schemas return explicit unsupported coverage. Malformed required
collections fail clearly. Empty text says “No displayed findings in this
projection”; it never claims repository absence.

Text encodes the same selected findings, locators, qualifications, source
identities, references, and exclusions as its structured backing. JSON escaping
keeps multiline native values identifiable without inventing new assertions.

## Current producer coverage

The projector covers all eight query surfaces: change intelligence, verification
explanation, freshness, snapshot, profile, delta, cross-repository evidence, and
economics; all three profile densities are supported. It also covers native
responses from repository context, find, task evidence, change impact,
post-change, source observation (member/scope), structural locality, repository
findings, repository evidence (observation/coverage), dependency CodeMap
(observation/explain/compare), correlation, and repository declarations
(observation/explain).

Source revisions and body-only delta changes remain visible even when symbol
signatures do not change. Snapshot-member changes do not imply file creation or
deletion. Diagnostic disappearance remains a producer claim, and possible
source moves or diagnostic relocations remain candidates. Dependency additions,
removals, transitions, and change axes retain endpoint provenance. Declaration
claims stay explicit and producer-owned: no transitive correspondence,
provider-name joins, or previous-observation replay state is introduced.

## Qualification and ownership

See [Format qualification](../qualification/AGENT_EVIDENCE_FORMATS.md) for
production-response and information-matched encoding trials. Tests establish
preservation and transport correctness; they do not establish model preference
or agent comprehension gains. External harnesses own model runs, grading, and
capture of the actual post-host model-visible response.

Observed repository fact/evidence: existing producer packets and their bounded
presentation, including previously hidden details and qualifications.
Authority source: existing CodeMap/domain producers and operation contracts.
Completeness/freshness behavior: preserved independently of display bounds.
Existing Hashmarks owner extended: evidence presentation, MCP, and query transport.
Consumer/execution responsibility explicitly not acquired: interpretation,
actions, agent execution, scheduling, and certification.
Decision: **OBSERVER**.
