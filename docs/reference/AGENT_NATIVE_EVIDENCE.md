# Agent-native evidence presentation and exposure

Hashmarks separates producer evidence from its presentation. Formatting is a
pure projection of an already observed packet: it performs no repository reads,
changes no producer identity, and acquires no reasoning or execution authority.

## Optional MCP formats

All fourteen current MCP tools accept `presentation` with the ordered values
`none`, `structured`, `compact`, and `text`. The default remains `compact` for
`repository_intelligence_query` and `none` for the other thirteen tools.
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

## Discovery evidence for coding agents

The existing `task_evidence` producer already separates retrieval, ownership,
source evidence, next-read discrimination and verification. Optional presentation
now additionally emits distinct, native-pointer-backed findings for admitted
owner, owner candidate, owner source evidence, unresolved discrimination read,
selected verifier, and verification plan. These are **presentations of existing
records** rather than new owner selection or verification execution.

The source row's context includes the native owner path, owner status and
proof-scope completeness because the compact source record itself omits its
containing owner path. An ambiguous candidate/next-read is a
`producer_claim`, not a qualified owner, and a selected verifier or plan
remains a producer claim. The complete native ownership/verification records
remain visible in the original result. All projections preserve source
pointers, current freshness and their producer-owned qualifications.

For `source_observation`, the compact source group displays exact literal
`occurrences` before `member_observations`. An explicit scope with many
members must not displace the actual matches under the five-row display cap.
Observed source counts and `omitted_from_presentation` still refer only to
the supplied packet; they never prove repository-wide completeness or absence.

This is not another parser, regex engine, multi-literal index, test runner,
or agent-routing layer. The consumer uses `task_evidence` for unknown-path
semantic localization, `source_observation` for exact literals in known
paths, and native source reads when the full implementation matters.

## Qualified endpoint comparisons

The read-only `evidence_comparison` MCP tool transports two explicit,
caller-supplied producer packets to their existing CodeMap comparison owners.
Its `result_mode` is one of `structural`, `bindings` or `diagnostics`.
Each mode retains its native schema; no additional persistent history, new
observation or Git lifecycle is created.

- `structural` invokes the existing locality delta. Unmatched provider,
  target, evidence identity, measurement settings, freshness or repository
  state yields explicit incomparability, not a proven structural change.
- `bindings` invokes the current repository binding delta, which rejects
  invalid, foreign or mismatched binding packets.
- `diagnostics` accepts existing producer-claimed diagnostic observation
  packets with normalized diagnostic identities. Added/removed identities
  remain observations; disappearance is not a proven fix. Producer collection
  completeness, environment, path scope and candidate relocation authority
  stay visible. `changed_paths` is accepted only in this mode.

Diagnostic comparisons now also expose `diagnostics.path_locality`, which
separates added and removed diagnostics *on* reported edited members from
diagnostics observed on *other* members. An empty or partial edited-path list
does not become complete negative evidence; unreported scope remains unknown.
The locality rows retain diagnostic identity, before/after membership, external
collection qualification, and an explicit `causality: not-asserted`.
The native packet and agent-native formatter preserve this distinction without
turning cross-file coincidence into a proved dependency or an execution result.

Two packets are required and individually bounded. This tool never starts
a diagnostic producer, runs tests, mutates Git, derives historical snapshots,
or chooses an agent action. The structural presenter renders incomparable
endpoints as qualification evidence rather than observed change claims.
Their native comparability flag and reasons remain visible outside row caps;
suppressed change collections are listed in `unprojected_sections` with native
item counts. Comparable dimension deltas retain the exact native mapping and
its source reference.

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
