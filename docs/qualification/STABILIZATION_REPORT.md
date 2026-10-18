# Architecture stabilization and backend baseline

Status: INCOMPLETE — final candidate validation is running.
Scope approved by the user on 2026-10-18:
[`STABILIZATION_PLAN.md`](../plans/STABILIZATION_PLAN.md), S1–S6.
This report does not claim backend 5/5 or release certification.
The user made the 6,000-token target advisory; size-only deviations are reported
for later optimization and do not block stabilization correctness.

## Required evidence

| Requirement | Current final-candidate result | Required proof |
| --- | --- | --- |
| S1 canonical ownership | PENDING | Existing component, architecture, binding and lifecycle contracts in the full selected regression run; owner map and obsolete API removal |
| S2 configured quality | PASS | Full Ty/Pyright: zero errors; preflight: zero lint debt; lock convergence and source compilation pass |
| S3 deterministic regressions | PENDING | Complete final 64-shard selection, all named batches and selected membership, no unresolved selected-test failures |
| S4 representative public workflows | PASS; budget advisory recorded | All three before/after API/CLI/official MCP workflows pass required correctness gates and all 1,109/1,109 frozen witnesses; maximum reply 6,131 estimated tokens |
| S5 source artifact | ADMITTED; final drift check pending | Deterministic ZIP and extraction below; actual import/producer identity and frozen membership admitted |
| S6 handoff | PENDING | This report completed with exact results and limitations |

Final source ZIP:
`.hashmarks/canonical-component-rewrite/stabilization-candidate-03/source.zip`.
SHA-256: `ad8459e919520b360641a75b8654fbcb3533bbee620378c38007ed7399aa0eac`.
Source identity:
`sha256:e2df3a6fa9e1ddcf0fd3c6b33a974ebb786f2b8b6a89fa4279c199d296672691`.
Producer identity:
`sha256:482c312e62ad01e87ae8b0590f568c75d6dff68e74841f2fca3f05eb3fb3b502`.
Independent extraction: `/tmp/hashmarks-stabilization-candidate-03-p7wlzp5u`.

The extracted import origin, unchanged producer identity and test-only correction
are verified in `stabilization-final/comparability.json`,
`documentation-comparability.json` and `artifact-audit.json`. Current selection has
3,562 static nodes over 64 shards, identity
`sha256:a55090a1f283a80aced5c0cbf58c8f12b4a2c2ade4c336e6ea4235e5d2e55be6`.
The original execution grouping is retained with grouping-independent membership
identity `sha256:0a898b4948ab5d3de3d95a4d542a515e2a2b15062026e3b4fb5ab97bd6b97daf`.
The fixed public witness set has 1,109 required units, frozen before acquisition.
Complete logs and witness closure fill the remaining rows from actual results
or explicitly proven byte-identical inputs, retaining original execution identity.

Quality command: `make agent-preflight lock-check typecheck compile`.
Its complete output is retained in
`.hashmarks/canonical-component-rewrite/stabilization-final/quality.log`.
The result report is written after source freeze; it does not modify qualified
production, test, tool configuration or oracle inputs.

Batch eight exposed a test that required one private provenance edge to occupy
position zero. The supported contract requires bounded project membership,
complete admitted links/confidence and deterministic output, not that incidental
position. The corrected test checks all expected edges, excludes unselected
projects and compares results after reversing the input order. Thirty focused
freshness/provenance/scale tests pass. Production, evaluator and oracle bytes
are unchanged. Comparability proves all 1,191 protected inputs unchanged, exact
selected membership and identical isolation requirements. Completed batches
0, 1, 3, 4, 5, 6 and 7 are retained from candidate 01. Batches 2 and 8 contain
the edited file and pass on candidate 02 with batches 9–10. Batch 11 then caught
two missing entries in the central documentation catalog. Both entries are now
present, all documentation tests pass from the extraction, and candidate 03
changes documentation only. Batch 11 and remaining batches 12–15 run on candidate
03 with the original frozen membership. This is external QA execution;
Hashmarks chooses no execution grouping or resume behavior.

## Representative workflow results

The existing backend runner acquired both revisions, default/initial profiles
and all required formats for the three fixed workflows. Pure regrading verifies
every retained artifact hash, receipt identity, source revision and oracle
pointer without constructing CodeMap or starting a process. All 1,109 required
source/call/task/delta witnesses are present and PASS. The newly admitted exact
test declaration retains its uncertainty in all six readable CLI/MCP formats.

The complete reply maximum is **6,131 estimated tokens**, on the Iterable
workflow. Four compact/text captures exceed the advisory target: 6,128, 6,129,
6,130 and 6,131. This remains a future compression opportunity. The original
backend evaluator report is retained as **FAIL** for `initial_size` alone;
fact, authority, revision, freshness, CLI, MCP and presentation gates all pass.
The stabilization verdict follows the user's explicit advisory-budget decision
and does not relabel that evaluator result or claim a higher capability score.

Evidence is retained under
`.hashmarks/canonical-component-rewrite/stabilization-qualification/`:
`required-witnesses.json`, `public-audit.json`, `public/summary.json` and each
workflow's exact receipt and observations. Final regrading in
`stabilization-final/public-audit.json` retains candidate 01 as the actual
execution artifact and proves the production/evaluator/oracle/source-input
protocol unchanged through candidates 02 and 03. Public workflows are not rerun
for test-only or documentation-only corrections. The final archive includes the advisory-budget clarification;
no production change was made to chase the size target.

## Implemented responsibilities and repairs

The 23 canonical owners are documented in
[`STATE_AND_SEMANTIC_OWNERS.md`](../reference/STATE_AND_SEMANTIC_OWNERS.md).
CodeMap composes owners and manages resource lifetime. Existing domain owners
retain source, import, relationship, retrieval, verification, task and delta
authority. Retired root APIs remain removed.

The current source includes generic repairs for read-scope failure cleanup,
explicit project-provenance preservation, duplicate project-name ambiguity,
bounded verification/source disclosure, lossless compact source qualification,
distinct matching test declaration disclosure and selected-verifier freshness.
The freshness repair preserves the originally selected stale test instead of
refreshing it through optional keyword enrichment and losing the binding.

## Preserved limitations and deferred work

- Static syntax and nominated endpoints do not prove runtime compatibility,
  transitive execution paths or test sufficiency. Missing before-test relevance
  and unresolved/ambiguous source identities stay explicit.
- Bounded observations do not prove absence. Locality candidate IDs for
  external/unindexed calls remain candidates, not exact call edges.
- The representative genuine set is a supported source/public-surface baseline,
  not an independent 20-capability qualification or a repository-wide test oracle.
- Exhaustive private-stage correspondence/locality, missing corpora, independent
  full-population semantic/test/adversarial review, unseen heldouts and broad
  economics are deferred in
  [`BACKEND_E2E_REMAINING_PLAN.md`](BACKEND_E2E_REMAINING_PLAN.md).
- Fresh full native campaigns and independent release rebuild/wheel/sdist proof
  are deferred. The source milestone is not a release or a runtime certification.
- The broad backend matrix remains INCOMPLETE. No score, review flag, minimum
  population, threshold or historical failure is changed by this scope decision.

Historical source and failure evidence remains under
`.hashmarks/canonical-component-rewrite/` with its original candidate identities.
