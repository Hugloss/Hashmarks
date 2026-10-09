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

### Qualified owner labels must match producer proof

An agent-visible `qualified_owner` row is now displayed only when the
**same native `task_evidence` packet** declares all of:

- `ownership.status == "resolved"` and
  `ownership.proof_scope_complete is True`;
- `ownership.authority == "repository-ownership-only"` and a nonempty
  `ownership.owner.path`;
- `freshness.state == "current"` at the top-level canonical task endpoint.

These checks do not re-resolve a repository owner, authenticate producer
claims, or grant execution authority. They govern **presentation labels only**.
A stale/unknown/missing freshness state, unresolved/ambiguous status, missing
owner path, or incomplete proof can no longer appear as an unqualified
`observed_fact` under the misleading `qualified_owner` name.

When a producer packet still contains an owner/source object under those
conditions, it remains visibly available as `unqualified_owner` and
`unqualified_owner_source` with `assertion: producer_claim` and exact native
`/ownership/owner` and `/ownership/source_evidence` pointers. The
`task_ownership` source context preserves the original status, scope proof,
authority/proof identity, owner path, freshness state, and descriptive
`display_qualification`. Candidate and discrimination read rows always remain
producer claims; verifier selection and plan remain separate producer claims.
No missing proof or freshness is silently filled in by the renderer.

The full native packet, `evidence_receipt`, original scope semantics, and
uncertainty remain intact. This strengthens the **display boundary**, not
CodeMap owner resolution or the agent's next-tool policy. Regression:
`tests/test_task_owner_presentation_qualification.py`.

For `source_observation`, the compact source group displays exact literal
`occurrences` before `member_observations`. An explicit scope with many
members must not displace the actual matches under the five-row display cap.
Observed source counts and `omitted_from_presentation` still refer only to
the supplied packet; they never prove repository-wide completeness or absence.

This is not another parser, regex engine, multi-literal index, test runner,
or agent-routing layer. The consumer uses `task_evidence` for unknown-path
semantic localization, `source_observation` for exact literals in known
paths, and native source reads when the full implementation matters.

### Direct SCIP relationship discovery on an admitted owner

`task_evidence` optionally emits `semantic_relationships` only when the
canonical ownership result has a resolved, complete, admitted owner and
Hashmarks can observe SCIP relationship flags or explicitly supplied LSP
captures mentioning that exact indexed symbol. This is a **separate repository evidence claim**,
not a different ownership selector or a reason to choose an action.

The compact record reports an exact `path::qualname` subject, direct observed
relationship count and kinds, producer bindings, truncation, and the
existing `structural_locality` detail surface.
`observed_relationship_count_scope` explicitly identifies which count the
summary represents: `exact-owner-scip-definition-outgoing` for captured SCIP
definition flags, or `explicit-producer-claims-associated-with-owner` when
there is no exact SCIP definition. The independently reported
`associated_observed_relationship_count` counts the direct producer claims
retained in `evidence`, which may include incoming SCIP relationships and
request-local LSP captures. Its
`associated_observed_relationship_count_scope` describes that wider scope.
The two counts can differ without contradiction: a symbol can have **zero
outgoing flags** while another definition contains a direct claim pointing
to it. These counts are bounded observations, never exhaustive edge counts
or agent-priority signals. Its `evidence` field adds up to
eight direct claims, provider capability/collection/freshness qualifications,
source correspondence and unresolved candidates, plus explicit presentation
omission counts. `evidence_refs` point to the packet's admitted ownership,
source evidence, and verifier evidence without changing their selection.
It never includes the full
relationship graph, callers, source bodies, or a second semantic index.
A provider-current import is not proof that the external SCIP index was
generated from the same source bytes: `source_equivalence` and
`completeness` remain `unknown`, with
`negative_evidence_admissible: false`. Repository freshness is carried
separately (`current` or `unknown`); a stale task packet is not enriched.

An exact, current SCIP definition that reports no relationship flags is
**observed evidence**, not the same thing as no provider observation:
`observation_state: definition-observed-no-direct-claims` records zero
observed flags and the SCIP producer binding. A positive count uses
`direct-claims-observed`. Both remain non-exhaustive producer claims;
neither zero flags nor an absent record proves that no relationships exist.

`repository_revision_observation` records whether the current CodeMap file
digest matches the repository bytes Hashmarks observed at SCIP import
(`same-as-import-observation`, `differs-from-import-observation`, or
`unknown`). This is **not** evidence that the SCIP producer analyzed those
bytes and never upgrades `source_equivalence: unknown` into proven identity.

No admitted owner, no unique current indexed symbol, no current SCIP
definition or a deny policy means a SCIP discovery claim is absent.
Retained stale SCIP claims keep their explicit stale qualification in the
full evidence; supplied empty/error LSP captures keep collection/source evidence.
For individual resolutions, full source bindings, and qualified deltas, query
`structural_locality` with that exact subject and `result_mode="relationships"`.
The optional `supplied_observations` argument (CLI `--supplied-observations`)
uses the [captured LSP contract](STRUCTURAL_LOCALITY.md#supplied-lsp-captures)
and remains request-local.
`supplied_observation_accounting` retains capture identities and received,
retained, and omitted counts when captures are supplied. An unqualified owner
or stale task keeps explicit exclusion accounting rather than silently
discarding those inputs.

The structured evidence presentation exposes
`/semantic_relationships` as `scip_semantic_discovery` with
`assertion: producer_claim`, before the aggregate related-evidence
projection. The existing source/owner/verification authority and MCP tool
count are unchanged.

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
