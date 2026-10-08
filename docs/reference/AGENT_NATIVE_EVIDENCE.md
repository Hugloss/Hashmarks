# Agent-native evidence presentation and exposure

Hashmarks separates **evidence semantics** from **transport formatting**. This
feature is read-only repository intelligence, not an agent planner, Git history
engine, repository mutator, or execution/certification authority.

## Finding vocabulary

Seven families describe different kinds of facts: `source_change`,
`relationship_change`, `dependency_change`, `diagnostic_observation`,
`verification_evidence`, `correspondence`, and `evidence_qualification`.

Assertions distinguish `observed_fact`, `observed_change`,
`candidate_correspondence`, and `producer_claim`. The last never becomes
proof of a fixed diagnostic, runtime causation, or complete test coverage.
Completeness/freshness is an independent axis; absence only means absence within
an explicitly qualified producer scope.

## Formats

`structured` gives bounded typed findings; `compact` caps displayed rows
per family; `text` supplies a short section-count summary backed by the same
typed fields. Formatting **never changes the original producer result**.
`source_schema` and `source_evidence_identity` link the rendering back to the
authoritative producer. When no supported projector exists, the renderer
reports `supported: false`, not an invented generic finding.

The existing `compact`, `standard`, and `audit` snapshot density profiles
are separate from the optional `presentation` selector. Their canonical
snapshot identity and payloads are unchanged.

## MCP exposure (existing producers only)

* `repository_intelligence_query`: existing read-only query surfaces:
  `change-intelligence`, `verification-explanation`, `freshness`,
  `snapshot`, `profile`, `delta`, `cross-repository`, `economics`.
  Snapshot comparison requires the caller's previous snapshot; Hashmarks
  does not retain or reconstruct historical Git state.
* `source_observation`: existing single-member or explicit scoped source
  occurrence evidence with native freshness, limits, and uncertainty.
* `structural_locality`: existing bounded exact-symbol structural and
  caller evidence, including unresolved references.
* `repository_evidence`: existing exact evidence bindings and qualified
  changed-path coverage with independent observation/coverage modes.
* `repository_findings`: existing bounded import, cache and concurrency facts.

The paired-format export and externally graded comparison are described in
[Format qualification](../qualification/AGENT_EVIDENCE_FORMATS.md).

MCP is a transport. It must obtain schemas from
`hashmarks.operation_contract` and validate returned core schemas.
The core CodeMap owns identity, source admission, matching, completeness,
freshness, and comparison. External execution remains consumer-owned.

## Qualifying agent format preference

Do **not** equate byte-count reduction with model improvement. Run paired
held-out tasks with the same evidence and model, first varying **format only**
(current/native vs structured vs compact vs text), then varying evidence
content (native vs enriched). Evaluate correctness, unsupported assertions,
token consumption, extra tool calls, redundant reads, and wall time.
Keep raw response and normalized answer traces for replay; never use
randomly generated gold labels. Use agentsCookbook as the external execution
and scoring authority; the repository-only fixture test here validates
semantics and transport contracts rather than claiming that one format wins.

## Non-goals

No new search engine, Git diff parser, diagnostic executor, LSP lifecycle,
history store, agent routing, task planning, or independent provenance owner.
Further existing-core exposure must meet the same admission and A/B criteria.
