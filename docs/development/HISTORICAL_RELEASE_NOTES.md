# Historical Hashmarks release/development notes

> **Historical, non-normative record.** This file preserves earlier documentation for archaeology and evidence. For current product behavior use `docs/reference/`, `docs/integration/`, and the root `README.md`.

---

# Hashmarks 0.13.0



### Bounded qualification selection

Hashmarks test selection permanently separates statically known expensive benchmark/reproducibility nodes from ordinary product tests. Those nodes are emitted as singleton `isolated_process` shards and are never mixed with ordinary nodes. This prevents one expensive benchmark from making an otherwise healthy product-test shard appear to time out.

This is selection evidence, not execution authority: Hashmarks does not choose runtime deadlines, retries, resume order, worker counts, or environment recovery. An external runner such as Oh-Goon/CI may further split ordinary selected membership as needed, provided exact admitted membership is conserved.

## Architectural constitution: repository intelligence vs execution authority

> **Normative feature-admission contract:** [`docs/reference/PRODUCT_BOUNDARY.md`](../reference/PRODUCT_BOUNDARY.md). **Every finding or proposed improvement must be classified against the Hashmarks product profile before implementation.** Historical release notes, compatibility APIs, benchmarks, and technically useful ideas are evidence to evaluate, not authority to expand the product boundary.

**Shortest rule:** Hashmarks owns repository intelligence. A capability belongs here only when its primary purpose and source of authority are repository intelligence; consumer reasoning/workflow and runtime execution remain outside. When uncertain, prefer the smaller Hashmarks and split out only the neutral repository-evidence primitive.

**This boundary is permanent unless a future canonical release explicitly changes the architecture contract:**

> **Hashmarks tells the agent what the repository means, who owns what, what is risky, what should probably change, and what should verify it. Oh-Goon decides whether execution is admitted, runs it safely, manages processes/timeouts/recovery, and certifies the result.**

Consequences:

- Hashmarks owns repository meaning, topology, ownership/authority evidence, ambiguity, change impact, repair-surface nomination, verification relevance, provenance, and evidence economics.
- Hashmarks may identify execution-related repository risks (for example PATH resampling, unreaped process code, or unsafe read-modify-write structure), but those findings are evidence for an agent/execution owner; they do not grant Hashmarks runtime authority.
- Hashmarks must not become a scheduler, retry engine, timeout manager, subprocess supervisor, sandbox, deployment system, or certification authority.
- Oh-Goon may consume Hashmarks evidence, but external admission, execution policy, isolation, process lifecycle, retry/recovery, and certification remain Oh-Goon-owned.
- A coding agent chooses and implements repairs from Hashmarks evidence. Static Hashmarks findings never silently rewrite repository code.



## v0.12.0 — atomic repository observation authority

Hashmarks v0.12.0 intentionally breaks the v0.11 daemon/client observation contract. `IdentityClient.observe()` is removed. Consumers use `IdentityClient.repository_observation()`, which returns one typed `RepositoryObservation` containing observation state, generation, bounded dirty paths, dirty-path count, completeness, and reason from one request-time observer barrier. Daemon protocol and semantics are v3; protocol-v2 clients/daemons fail compatibility rather than silently mixing freshness semantics.

CodeMap owns one reusable Identity client and makes each readiness decision from a single repository observation. Complete bounded dirty sets may drive existing incremental CodeMap reconciliation; incomplete, malformed, unknown, or oversized evidence fails closed to full reconciliation. This is repository-intelligence freshness authority only and does not transfer execution, admission, retry, certification, or promotion authority into Hashmarks.

## v0.11.21 qualification identity and repository-evidence closure

Hashmarks v0.11.21 adds stable verification-membership and qualification-owner identities, fail-closed ownership-decision traces, downstream repository-intelligence contracts, symbolic nomination, cold/warm semantic-equivalence checks, repository-economics receipts, executable product acceptance, and deterministic classification of correctness, process-sensitive, and empirical benchmark qualification membership. Physical grouping, subprocess lifecycle, deadlines, retries, result authority, and certification remain external execution-layer responsibilities.


Canonical promotion is fail-closed around one external native-host gate. `scripts/promotion_gate.py` emits the exact repository-bound gate identity and validates an externally produced Ruff receipt. The receipt must bind `ruff 0.16.6`, the configured `B,I,UP,FAST,SIM,C4,TID25,T20,G,TC` rule families, `make lint`, exit code 0, exact `ruff 0.16.6` version output, and a SHA-256 identity for the captured command output. Hashmarks validates that evidence but does not run Ruff or create PASS authority.


### Native producer and qualification provenance boundary

Hashmarks evidence now separates semantic version from exact implementation provenance. Verification-selection envelopes and downstream contracts carry a native `producer_implementation_identity`; envelope and contract identities bind it, and same-version/different-bytes evidence cannot be cross-paired. Consumers verify the provided identity and linkage rather than reproducing Hashmarks' implementation-identification algorithm.

Qualification classification is repository-owned in `qualification-classification.json`. Hashmarks emits a deterministic, repository-bound classification artifact and owner plan covering `release-correctness`, `process-sensitive`, and `empirical-benchmark`. Classification changes alter provenance identities; measurements may nominate changes but cannot mutate authoritative classification.

Qualification coverage and external results are distinct contracts. `validate_external_qualification_coverage()` validates repository/plan/unit/membership/provenance linkage only. It never declares an external PASS trustworthy. Execution, result, and certification authority remain external. `native_qualification_handoff()` exposes repository identity → exact membership → classification/owner → preferred granularity → provenance → producer identity while keeping `may_regroup=true` and all execution-layout authority external.

`qualification_classification_economics()` compares all-ordinary membership with classified membership and reports membership counts, owner-unit counts, singleton counts, granularity distribution, and identity-bound classification deltas. It does not schedule, execute, retry, bisect, or manage processes.

### Downstream consumer conformance kit

`hashmarks.consumer_conformance` provides consumer-side validators and deterministic interoperability vectors for verification-selection envelopes, downstream contracts, native qualification handoffs, producer implementation identity pins, and same-version implementation drift. Producer implementation identity is intentionally treated as an opaque Hashmarks-issued value: consumers compare and cross-bind it but do not reproduce Hashmarks' package-byte identification algorithm. `scripts/consumer_conformance.py --root .` emits the self-checking vectors as JSON. Execution, result, and certification authority remain external.

### Qualified cross-repository identity

`hashmarks.qualified_identity` composes existing import-owner and declared-project evidence into deterministic qualified identity records. Equivalent Python import forms resolve to the same qualified owner identity when Hashmarks proves the same owner surface; ambiguous re-export frontiers remain identity-less and fail closed. Declared shared inputs bind repository identity, exact shared-input content digest, project IDs/link kinds, freshness, and producer implementation identity. A shared-input edit invalidates the qualified identity until the existing declared-project freshness authority rebinds it. These records are repository intelligence only and carry no scheduling or execution authority.

### Residual repository economics

`hashmarks.residual_economics` composes the existing isolated-query, related-query reuse, top-N, changed-impact, scale-class, and qualification-classification measurement surfaces into one repository-intelligence economics report. The real Hashmarks-tree HM-10 measurement exposed a limit-dependent `find_task()` candidate-frontier defect; the retrieval surface now uses a stable internal evidence frontier through the normal 20-result agent surface and slices only the requested output prefix. Permanent regression coverage proves 5/10/20 prefix semantics on the real repository. Measurements remain observational and never own workers, scheduling, subprocesses, timeout/retry, editing, PASS/FAIL, or certification.

The qualification contract deliberately preserves logical membership when an external runner regroups work for bounded execution. Empirical benchmark nodes and process-sensitive nodes are identified explicitly rather than being allowed to distort ordinary correctness qualification.

## v0.11.20 one-command developer verification

Hashmarks now exposes `make dev-check` as the normal developer PASS/FAIL boundary: locked sync, doctor, compileall, CodeMap sync, and deterministic bounded test shards. Failures identify the stage and print a copy/paste reproduction command. `make verify` aliases this safer bounded path. `make release-check` is explicitly a local preflight only and cannot be confused with canonical artifact/persistence/readback proof. This changes developer orchestration only; repository-intelligence and execution-authority boundaries are unchanged.


Long developer qualification is resumable in named batches. `make dev-check-batch DEV_BATCH=0` runs four deterministic test shards by default; if a runtime window expires during batch N, rerun only `make dev-check-batch DEV_BATCH=N`. After that batch passes, continue with `make dev-check-tests DEV_BATCH_START=$((N + 1))`. A timeout without an assertion result is never counted as a failure or proof.

File-backed Python AST consumers share a freshness-bound process-local cache through `hashmarks.python_ast_cache.read_python_ast`. Unchanged device/inode/size/mtime/ctime metadata reuses the parsed source/AST snapshot; a changed or unstable file misses/retries. This is an I/O/CPU optimization only and never replaces content identity or CodeMap freshness authority.

## v0.11.19 Authority & Ownership Graph v3 risk-composition closure

Hashmarks v0.11.19 composes the existing static concurrency/read-modify-write nominations into the single Authority & Ownership Graph. `hashmarks.authority-ownership-graph.v3` now adds `concurrency-risk` nodes and `contains-concurrency-risk` edges from the exact repository file that owns the nominated sequence. The graph also reports total and unguarded concurrency-risk counts alongside the v0.11.17 invalidation-owner summary.

This is composition, not a stronger runtime claim. An unguarded edge means only that Hashmarks observed a same-lexical-owner read followed by a write without a visible lock/transaction/CAS guard. A guarded edge means only that such a visible guard was present. Neither proves whether concurrent callers exist, whether the guard is sufficient at runtime, nor who may change synchronization policy. Hashmarks does not acquire locking, execution, scheduling, retry/recovery, admission, or certification authority.

## v0.11.17 Authority & Ownership Graph v2 composition closure

Hashmarks v0.11.17 composes the exact cache-invalidation evidence introduced in v0.11.16 into the existing Authority & Ownership Graph. `hashmarks.authority-ownership-graph.v2` now emits `invalidates-cache` edges from proven repository invalidators to exact cache owners, adds invalidator nodes, and computes resolved versus unresolved invalidation owners from those exact edges rather than relying only on same-file cache heuristics. Imported/aliased invalidators therefore become visible in the single composed ownership view without turning lexical same-name coincidence into mutation authority.

The composition remains fail-closed. An invalidation edge is admitted only when the v0.11.16 resolver proves the target through local ownership or qualified import/alias identity; shadowed names and unresolved same-name caches remain ambiguous. Hashmarks still never executes an invalidator, mutates cache state, decides runtime cache lifecycle, admits execution, manages retries/timeouts, or certifies a repair.

## v0.11.16 warm-service parity / cache invalidation ownership phase

Hashmarks v0.11.16 closes a warm-service API parity defect in v0.11.15: `CodeMapServiceClient` exposed cache ownership, authority ownership, concurrency risk, and verification ownership methods, but the service dispatcher did not admit those operation names. The service now exposes the same bounded repository-intelligence surfaces as direct `CodeMap`/CLI calls, with the same validation limits and no new execution authority.

This phase also adds `hashmarks.cache-invalidation-ownership.v1`. It resolves repository-visible Python cache invalidation calls (`clear`, `cache_clear`, `invalidate`, `invalidate_all`) to exact cache owners using local ownership, simple aliases, qualified symbol imports, qualified module imports, and bounded relative-import identity. Duplicate same-named caches are never joined by lexical name alone; unresolved targets remain unresolved. The graph answers which repository function/module contains visible invalidation evidence and which cache owner that call targets. It never imports repository modules, executes an invalidator, mutates cache state, or grants runtime mutation authority.

The new CLI surface is `hashmarks map cache-invalidation-ownership`; the warm CodeMap service/client exposes the same graph. This composes with v0.11.15 cache/import/authority/concurrency/verification evidence while preserving the permanent Hashmarks/Oh-Goon boundary.

## v0.11.15 Import Ownership v2 / canonical-module identity phase

This development phase extends v0.11.14 import ownership from dynamic-loader detection to canonical module-identity reasoning. When a repository-owned file is loaded under a literal module name different from the package identity Hashmarks can prove from repository structure, Hashmarks reports `python-duplicate-module-identity`, exposes both identities, and recommends the canonical package identity. This remains static repository evidence only.

## v0.11.15 ownership-intelligence phases

The v0.11.15 development line composes four repository-intelligence surfaces on top of Import Ownership v2:

1. **Cache Ownership Intelligence** maps explicit process-local cache owners, decorator-managed caches, visible invalidation evidence, and import-identity risks that can duplicate cache state.
2. **Authority & Ownership Graph** composes dynamic-loader, canonical module, cache-owner, reader/reference, and unresolved-invalidation evidence into one bounded graph. It reports ambiguity rather than inventing writer/runtime authority.
3. **Verification Ownership Graph** projects task-local verification owners and bounded verification plans from existing relevance evidence. It nominates what should verify a change; it does not run or certify verification.
4. **Concurrency/RMW Risk Map** nominates same-owner read-then-write sequences and records whether a lexical lock/transaction guard is visible. It is deliberately a risk nomination, not proof that a runtime race exists.

These surfaces are designed to compose: an agent can see that a dynamically loaded module owns a cache, that the cache has unresolved invalidation, which repository readers depend on it, what verification surface is relevant, and whether the owning implementation contains a suspicious read-modify-write sequence—without Hashmarks acquiring execution authority.

## v0.11.14 module-ownership / concurrency correctness closure

Hashmarks v0.11.14 is built from exact canonical v0.11.13. It adds static Python module/cache ownership diagnostics for repository-owned dynamic loaders, closes a lost-update race in durable CodeMap generation advancement, removes a daemon-wide serialization bottleneck by giving the Unix identity service concurrent request handling with narrow daemon-state locks, carries the exact resolved PATH in execution-identity evidence so standalone Hashmarks execution cannot drift from admission, and fully reaps a terminated metrics service after forced kill. These are repository-intelligence, identity/provenance, and local correctness improvements only; Hashmarks still does not own external execution supervision, retry, timeout recovery, scheduling, or certification.

Current cross-repository validation uses canonical Oh-Goon **1267.0.147** (ZIP SHA-256 `e7c494892601892d1baa0988c653639af7fa294fa8b511b49bf4710c1abbc8ec`). Earlier Oh-Goon versions mentioned below are retained only as historical measurement context.

## v0.11.13 qualified import identity / stale-indirect verification closure

A fresh post-B2 64-task adversarial corpus exposed one localized repository-intelligence failure in v0.11.12: stale tests importing a same-named legacy symbol could be counted as direct reverse-reference evidence for the active implementation when only the short symbol name matched. That stale evidence could defeat the real product verification path when the active verifier reached the live owner indirectly through a public API.

v0.11.13 resolves Python import identity before accepting same-name reverse references when resolution evidence is available, including normalized relative imports, bounded qualified re-export chains, `as` aliases, and name-scoped star re-exports. A qualified re-export chain may traverse at most eight repository import hops; ambiguity, cycles, or evidence continuing beyond that bound remain unresolved and require discrimination rather than silently degrading to short-name authority. It also preserves a uniquely anchored non-archive edit candidate against archive-like structural decoys, and multiple live same-symbol owners behind an archive hit are explicitly ambiguous instead of falling back to the archive path. These are evidence-selection rules only: no test execution, retry, timeout, resume, scheduling, process management, environment recovery, or certification authority is added.

On the frozen fresh corpus, exact full correctness moves from 48/64 on v0.11.12 to 64/64 on this candidate. All 16 stale-adjacent + indirect-verification failures are rescued with zero harms across the 48 ambiguous-owner, verification-scale, and cross-repository-provenance controls. A second frozen 16-case identity-composition matrix moves from 1/16 on the pre-hardening candidate to 16/16: supported re-export/alias/star forms resolve exactly, while over-bound chains and multiple live same-symbol owners fail closed with scouting. Worker-facing evidence does not grow to obtain the rescue.

A real-world ownership sweep against the persisted Oh-Goon 1267.0.139 backend then exposed a different neighboring failure class: natural maintenance tasks could confuse production `src/**/test_*.py` modules with tests, could not admit a test file as the edit surface when the task explicitly requested test maintenance, allowed generic policy/contract wording to displace a stronger symbol owner, and treated CamelCase task identifiers as unrelated to snake_case repository symbols. The frozen 12-task sweep moved from 1/12 exact edit owners with four confident wrong-owner outcomes to 9/12 exact owners with zero confident wrong-owner outcomes; the remaining three model-vs-runtime ownership pairs are explicitly unresolved and require scouting. Explicit pytest shard/batch tuning may project a uniquely evidenced build surface such as the Makefile, but Hashmarks still does not choose runtime batching, timeout, retry, concurrency, or execution policy.

The same real-world sweep exposed a repository-economics weakness in the persistent lexical surface. On an 894-file Oh-Goon backend slice, the previous rowid lexical table plus overlapping token indexes produced a 246.8 MB CodeMap for roughly 8.1 MB of source and spent about 16.5 s of a 25.6 s cold sync in file materialization. The compact layout now stores lexical identity once in a `WITHOUT ROWID` `(token,path,line)` primary key plus one path index for bounded file replacement, and cold sync commits file materialization in bounded 32-file chunks. The same slice falls to 170.6 MB and about 18.7 s cold / 0.35 s warm while preserving the 9/12 + 3 fail-closed ownership result. More importantly, the full 1,584-indexable-file Oh-Goon tree, which previously exceeded this environment's 120 s command window, now completes cold sync in about 29.4 s with zero parse errors and warms in about 0.58 s. Existing legacy CodeMaps are transactionally migrated; compaction is best-effort and never changes repository evidence semantics.

## v0.11.12 compact worker authority receipt / evidence-economics closure

Hashmarks now keeps the rich decision packet as addressable authority/debug evidence while its compact worker projections carry a shared `hashmarks.decision-authority-receipt.v1`. The receipt binds repository identity, task identity, selected edit/verification/contract authority, ownership path, ambiguity state, negative evidence, and verification-plan identity without embedding the large `verification_relevance` and `work_context` bodies. `task_decision_packet`, `task_decision_brief`, `task_agent_action_brief`, and `task_agent_start` generated from the same decision therefore share one budget-independent authority identity. Ranking, ownership, verification selection, and execution boundaries are unchanged.


## v0.11.11 B2 authority discrimination / bounded indirect verification closure

This release is derived from the fresh 64-task Benchmark B2 rather than a preselected feature list. It keeps canonical retrieval authority unchanged while closing three deterministic residuals: multiple task-local verification origins that resolve to different live implementation owners now remain ambiguous and require scout/discrimination; explicit configuration/policy tasks use verification-backed active-owner locality before lexical source locality; and verification relevance may follow one bounded source-reference hop so nonstandard `checks/**/*_spec.py` verification can be nominated from an already-selected edit owner. The bounded indirect hop is repository evidence only and never executes verification.

B2 moved from 40/64 fully correct after corrected authority-safety grading to 64/64, with unsafe autonomy 8→0 and unnecessary blocking remaining 0. The full packet became larger because it carries richer reference/discrimination evidence, while the compact decision brief remained roughly 142 estimated tokens on the benchmark; whole-packet compression therefore remains a separately measured next lane rather than being mixed into this correctness release. Semantic/vector nomination remains unadmitted.

## v0.11.10 strict consumer conformance / membership-conservation closure

Hashmarks now exposes a strict, execution-free conformance layer for `hashmarks.test-shards.v3` and `hashmarks.repository-work-selection.v1`. `validate_test_shard_plan()` rejects malformed counts/indexes, duplicate test-node ownership, missing or unexpected fields, altered process-isolation requirements, and recomputed identities that try to smuggle new fields into the v3 contract. `validate_work_selection_envelope()` applies the same exact-field discipline to producer, repository, authority, and envelope surfaces and freezes the Hashmarks-vs-execution authority declaration instead of accepting arbitrary non-empty capability lists.

`hashmarks.test-shard-membership.v1` is a derived, grouping-independent identity over the exact selected test-node set. `node_membership_identity()` and `selection_membership_identity()` let an external execution layer preserve the same membership identity while regrouping work after a timeout; omission or duplication changes/fails the identity. This does not give Hashmarks timeout, retry, concurrency, or refinement authority. `validate_work_selection_repository_binding()` optionally re-proves an imported envelope against current repository bytes by recomputing only Hashmarks-owned repository content identity, selection-input identity, and deterministic v3 selection. It never launches pytest or admits execution.

## v0.11.9 generation-bound repository-work selection envelope

Hashmarks now wraps an unchanged `hashmarks.test-shards.v3` plan in a `hashmarks.repository-work-selection.v1` envelope for external execution/certification systems such as Oh-Goon. The outer envelope binds the exact v3 membership and `isolated_process` requirements to Hashmarks' canonical repository content identity, a separate exact selection-input identity, producer version, shard-algorithm identity, implementation identity, and optional released-artifact SHA-256 provenance. A non-test source change therefore invalidates the outer envelope even when deterministic test membership remains byte-for-byte unchanged; a test-source change invalidates both selection input and the inner plan.

The envelope is deliberately one-way repository evidence. It carries no command argv, timeout, retry count/delay, worker/concurrency setting, schedule, machine placement, process state, or environment-recovery policy. Hashmarks still owns only repository content/selection evidence and process-isolation requirements; the external execution layer owns launch, deadline, retry/resume, concurrency, scheduling, environment recovery, result authority, and certification. Raw `test-shards.v3` output remains available and unchanged for compatibility.

> **Rename compatibility:** Hashmarks was developed under the working name FastIdentity. Public package/import/CLI/state names are now `hashmarks` / `.hashmarks`, but existing `fastidentity.*` cryptographic domain and wire/schema identifiers are intentionally frozen so the rename does not invalidate previously computed identities. Legacy `.fastidentity` state is always excluded from workspace identity.

Hashmarks is a **fast incremental identity, impact-analysis, and repository-map engine for builds, tests, and coding agents**.

Hashing is the mechanism. **Identity** is the public abstraction.

## Non-negotiable agent boundary and execution boundary

**Hashmarks is repository intelligence, not the system that reasons about, orchestrates, or executes the consumer's work. Hashmarks must never become the coding agent's solution loop or Oh-Goon's execution/certification motor.**

Every proposed capability must be admitted by `docs/reference/PRODUCT_BOUNDARY.md` before implementation. The test is not whether the idea is useful; it is whether Hashmarks is the correct owner. Repository-derived identity, topology, ownership, impact, ambiguity, freshness, verification relevance, provenance, and evidence economics fit the profile. Consumer reasoning/workflow and runtime execution/certification do not.

Existing surfaces that cross this boundary are historical debt, not precedent. Preserve any useful neutral repository-evidence primitive, but prefer containment, migration, or removal of misplaced responsibility over expanding it. `AGENTS.md` is the contributor/agent-facing guardrail for this boundary.

## v0.11.8 verification relevance at scale / bounded reverse-reference closure

When many verification surfaces reference the same implementation symbol, generic task retrieval can legitimately return a broad regression test ahead of the narrow package-local test. `task_action_map()` now projects a bounded `hashmarks.verification-relevance.v1` surface around the already-selected edit owner. It reuses indexed reverse references, test-domain classification, namespace locality, task anchors, and existing verification-plan availability. It may replace the canonical verification candidate only when one visible test surface has a direct symbol reference, non-generic namespace overlap with the edit owner, and uniquely stronger evidence than the alternatives. Canonical `find_task()` ranking and edit authority remain unchanged.

The public `verification_relevance()` API, CLI, and warm service expose the same bounded evidence. The projection reports its candidate bound and reference-walk bound, but it does not read test bodies to invent relevance, run verification, judge sufficiency, or choose a recovery action. On the retained adversarial scale corpus with 10, 50, 100, and 500 broad regression distractors, the prior canonical verification candidate was 0/4 package-local while v0.11.8 selected the intended package-local test 4/4 with 0 unsafe regressions; the 500-distractor case contained 501 plausible test surfaces. Expected paths remain scorer-only and `secret_knowledge_used` stays false.

## v0.11.2 declared cross-repository impact provenance / shared-input refresh

Declared cross-repository relationships remain repository evidence, never orchestration. `task_agent_change_impact()` now projects bounded project-impact chains from the existing fresh project graph with explicit edge provenance (`from`, `to`, relation kind, confidence, producer). When the external agent reports a change to a freshness-bound `[[shared_input]]` declared in `.hashmarks-project-links.toml`, Hashmarks recollects only the existing `declared-project-links` provider before impact projection so the declared topology is rebound to the current input bytes. It does not discover new repositories, schedule downstream work, execute verification, delegate agents, choose follow-up edits, or coordinate repositories.

## v0.11.1 indexed exact-import resolution / large-impact latency closure

Large-repository profiling of the v0.11.0 changed-impact path found a performance bottleneck rather than a new evidence gap: JavaScript/TypeScript and Go exact import resolution repeatedly materialized the complete indexed file map even though the candidate path set was already mechanically bounded. v0.11.1 replaces that whole-repository materialization with primary-key candidate probes for JavaScript/TypeScript and package-scoped path lookup for Go. Resolution rules, admitted owners, ownership graphs, changed-impact packet schema, and visibility policy are unchanged.

This is an index/evidence-engine optimization only. It does not add planning, delegation, scheduling, model routing, autonomous tool use, test execution, recovery behavior, or any other agentic-orchestration capability. Hashmarks remains repository intelligence consumed by external agents; it is not another ChatGPT/Codex/OpenCode runtime. The retained large-impact qualification remains answer-blind and verifies that packet size/correctness are unchanged while measuring latency separately.

## v0.11.0 large-repository changed-impact economics / direct-owner relation reconstruction

Large-repository stress exposed one concrete evidence gap in v0.10.99: when task admission directly selected the correct edit symbol, `task_action_map()` could legitimately omit `owner_path`. The later changed-impact call then had only the deliberately conservative generic reverse graph, which missed same-package Go dependency chains even though the selected verification surface and existing ownership relation graph could prove them. v0.11.0 reconstructs **the same bounded ownership relation graph** from the already-selected verification surface only when no owner path was retained, and accepts that reconstructed path only if it terminates at the already-admitted edit authority. For same-package Go tests, the existing unique visible non-test sibling rule may nominate the graph entry point; it still cannot nominate or replace the edit owner. Any disagreement is ignored rather than used to rerank the task.

The retained large-impact economics matrix spans Python, TypeScript, Go, and polyglot repositories at 250, 1,000, 3,000, and 10,000 noise-file tiers. Across 16 scenarios / 112 tasks, v0.11.0 preserves 112/112 edit authority, 112/112 exact verification relevance, 112/112 structural dependency relevance, and 112/112 no source-body or verification-argv replay. Impact evidence stays nearly flat at 648.31 serialized UTF-8 bytes/task overall even at ~10,026 files. Mean impact latency grows with repository size on the exact canonical ZIP: 12.449 ms at the 250 tier, 22.631 ms at 1,000, 48.754 ms at 3,000, and 152.927 ms at 10,000; this scaling cost is reported rather than hidden.

On the exact canonical v0.10.99 runtime using the same 250-file scenarios, edit and verification relevance were already 32/32, but structural dependency relevance was only 22/32: Python 8/8, TypeScript 8/8, Go 0/8, polyglot 6/8. The v0.11.0 candidate is 32/32 on the same tier. This is deterministic repository-intelligence/context/latency qualification, not a fresh model-directed experiment, and UTF-8 bytes are not relabeled as model tokens. The result does **not** justify a new cross-repository planner or orchestration layer; cross-repository impact should be stressed separately before adding another primitive.

## v0.10.99 changed-code impact + verification relevance

`CodeMap.task_agent_change_impact()` and `hashmarks agent-change-impact` expose a bounded post-change impact surface for an external coding agent. The surface composes the existing reverse/project impact authority with the task's already-proven ownership path and selected verification authority, so parser/module-resolution gaps in generic reverse impact do not force the agent to rediscover a test that Hashmarks already proved during task admission. Rows carry explicit provenance such as `reverse-impact`, `task-owner-path`, or `task-selected-verification`; denied paths are excluded. Verification relevance exposes only bounded runner/scope/confidence metadata and never replays argv or executes the test.

This remains repository intelligence, not a follow-up planner: Hashmarks does not choose which impacted path to edit, prioritize work, run verification, judge the patch, or select recovery.

### Lossless cross-repository provenance compression

`agent-change-impact` can independently bound project provenance with `--project-impact-limit` and can emit that provenance as `--project-impact-encoding compact`. Compact encoding is lossless dictionary coding: project ids, edge kinds, and producers are interned once, while each affected project carries its depth and admitted provenance edge as a numeric row. `hashmarks.codemap.expand_project_impact()` reconstructs the existing verbose representation exactly. Verbose remains the compatibility default; compact is the lower-byte transport for large cross-repository packets. Compression changes representation only and never changes graph traversal, affected-project authority, freshness, or execution ownership.

On the 60-task hard PUBLIC/SECRET corpus, the compact surface preserves 60/60 exact task-local verification relevance and 60/60 structural dependency coverage, with no source-body or verification-argv replay. It averages 551.03 serialized UTF-8 bytes/task. The generic reverse-impact lane alone is intentionally conservative and produced no hard-corpus test surface for these relative-import ownership chains; the additional task-owner-path lane reuses only relationships already proven by the existing ownership graph rather than inventing another impact graph. This is deterministic contract/context qualification, not a fresh model-directed experiment.

## v0.10.98 incremental post-edit evidence delta

`task_agent_post_edit_delta()` is the external-agent handoff after an edit. The caller supplies the exact prior `agent-start` packet plus the repository-relative paths it changed. Hashmarks reconciles only those paths, compares the new repository evidence against the frozen prior packet, and emits a compact delta: changed path revision state, CodeMap generation invalidation, which edit/verification/owner/provenance authorities remain reusable, and replacement authority only when one actually moved. Unchanged source bodies and verification commands are not replayed.

The delta is evidence, not recovery behavior. Hashmarks does not inspect the patch intent, decide whether the edit was good, execute verification, choose a recovery strategy, or perform another edit. `agent-post-edit` and the warm CodeMap service expose the same contract for external harnesses. Existing semantic invalidation shields are surfaced as bounded counters so a body-only edit can show that higher-level repository semantics were preserved without pretending the source revision itself stayed valid.

On the retained 60-task hard corpus, a syntax-preserving external edit was applied to each PUBLIC-only selected edit path before SECRET grading. All 60 deltas correctly detected the changed path/revision and generation invalidation while reusing all 60 edit authorities, verification surfaces, and selection provenance; no replacement authority was emitted. The compact delta averages 584.88 serialized UTF-8 bytes versus 853.83 bytes for a full refreshed `agent-start`, a 31.50% context reduction. This is deterministic contract/economics qualification, not a fresh model-directed experiment.

## v0.10.97 provenance + freshness-rich agent-start evidence

`task_agent_start()` now carries a compact `provenance` object over the already-selected edit authority: `why` records the mechanical selection route, `revision` is Hashmarks' domain-separated canonical file-content digest for the selected edit source, and `freshness` is explicitly `proven`, `stale`, or `unknown`. Freshness is never inferred from a recent timestamp. `proven` requires an active generation-bound continuity authority; `unknown` means the indexed/source revision is known but filesystem continuity since reconciliation is not proven; `stale` means Hashmarks observed a changed continuity/generation boundary and the external agent should refresh before acting.

The model-facing packet stays intentionally smaller than the full decision packet: routine proven/unknown starts do not carry identity-generation diagnostics, while stale starts add the generation details needed to explain the invalidation. The existing top-level status field is retained for compatibility; `provenance.freshness` is the precise continuity-proof signal. This phase does not add planning, editing, execution, recovery, orchestration, or a second provenance authority.

On the 60-task exact agent-start corpus, edit/verification/source correctness remains 60/60, all 60 packets have current source revisions and complete provenance, and all 60 correctly report freshness `unknown` on the qualification host because no daemon/watcher continuity proof was active. The compact metadata raises serialized start-packet evidence from 712.67 bytes/task in v0.10.96 to 853.83 bytes/task (+19.8%); that measured cost is retained rather than hidden and should be challenged in later real-agent economics.

## v0.10.96 bounded configuration key/section evidence

`task_agent_start()` can now replace a symbol-less configuration `next_read` with a bounded TOML, JSON, YAML, or YML key/section range when the already-selected configuration owner contains one unique task-mentioned structural key. The projection happens **after** `task_action_map()` has selected the edit authority: it cannot nominate another file, infer the desired value, edit configuration, or execute anything. The task must lexically support every component used to authorize the range, and ambiguity, invalid JSON/TOML syntax, unsupported/multiline shapes, denied source, and source-budget overflow remain fail-closed `next_read` outcomes.

On the 60-task hard agent-start corpus, the existing 60/60 edit and 60/60 verification correctness is preserved while source-complete start packets improve from 50/60 in v0.10.93 to 60/60: all ten configuration-ownership cases now expose the exact `mode = ...` key range instead of `no-exact-symbol-range`. This is repository evidence compression only; external agents retain interpretation, editing, verification execution, and solution behavior.

## v0.10.95 verification-surface provenance / fresh agent-start proof

`task_agent_start()` now preserves the exact selected verification surface as `verify_path` alongside the executable `verify` argv. This matters when the mechanically safe runner necessarily widens scope: for example, a TypeScript test may be selected as the task-local behavior authority while the only recognized executable plan is project-wide `tsc --noEmit`. The path is repository evidence only; the external agent still decides whether and how to inspect or execute it. Test bodies remain unloaded by default.

A fresh randomized ChatGPT model-directed A/B proof used independent Native and Hashmarks lanes across Python, TypeScript, and Go. All decisions and real verification outcomes were frozen before SECRET was opened. The first corpus exposed four TypeScript fallback searches because the exact test path was hidden behind the project-wide compiler argv. After this additive evidence fix, that corpus was retired for grading and a new fresh replacement corpus was generated. On the replacement, Native and Hashmarks each reached 12/12 exact edit owners, 12/12 exact verification paths, and 12/12 green outcomes. Hashmarks used 31.4% less visible decision evidence (7,004 vs 10,212 UTF-8 bytes), 50% fewer decision interactions (12 vs 24), and no TypeScript fallback searches; warm evidence latency was also 8.8% lower in this local run. Exact model token telemetry was unavailable, so byte counts are not relabeled as token counts.

The experiment reinforces the product boundary rather than expanding it: Hashmarks supplied compact repository intelligence; ChatGPT performed the reasoning, edits, and verification execution. No external Codex CLI was available in the execution environment, so this release makes a fresh ChatGPT model-directed claim only, not a Codex claim.

## v0.10.93 native agent-start evidence packet

`CodeMap.task_agent_start()` is the first single-call repository-intelligence surface intended to be handed directly to an external coding agent. It composes the existing action-map and mechanical verification authorities, then attaches only bounded, policy-authorized evidence from the already-selected edit surface. It does **not** reason about the solution, edit files, execute arbitrary shell commands, judge patches, or own git lifecycle.

The same contract is available through the warm `CodeMapServiceClient.task_agent_start()` path and `hashmarks agent-start`. The verification argv and contract path remain typed authorities but their bodies are not preloaded. Exact edit-source ranges are returned only when the whole current indexed symbol range fits the caller's source-evidence budget. A range that does not fit is never silently clipped; the packet instead exposes a `next_reads` requirement. `agent=outline` paths can contribute only signatures/outlines, and `agent=deny` paths are excluded from structural ownership traversal as well as source projection.

This phase also closes an older role-projection inconsistency: because repository domains are non-exclusive, test files are both `TEST` and parser-level `SOURCE`, but `task_entry_points()` can no longer promote them to implementation authority. Within the implementation role it may prefer stronger exact symbol evidence while retaining each candidate's original canonical rank and leaving `find_task()` unchanged.

It borrows the useful invariants from Buck2/DICE and Bazel without becoming a build system:

- file bytes define canonical content identity;
- real directories compose into Merkle identities;
- large explicit manifests compose into an incremental synthetic Merkle trie;
- exact dirty paths invalidate only affected branches;
- unchanged bytes are not reread;
- unchanged manifests do not re-`stat()` their members;
- a long-lived daemon preserves proven state across CLI processes;
- a request-time inotify barrier drains already-queued Linux events before hot state is trusted;
- observer uncertainty becomes `UNKNOWN` and forces safe reconciliation;
- Step identity can key an action cache and outputs can live in a CAS;
- `verify=True` strengthens verification without creating a second identity model.

There is deliberately **no HashWire, range-proof, or run-history hash-chain machinery**.


## v0.10.89 polyglot agent-evidence closure

Hashmarks keeps the agent/harness boundary unchanged while extending bounded repository evidence across Python, JavaScript/TypeScript, Go, and SQL. Agent action briefs can now derive local Vitest, Node test, TypeScript compiler, Go test, and pytest verification plans; JS/TS parent-relative imports and Go module imports participate in bounded owner-path evidence; SQL tests may nominate an exact referenced `.sql` source file. Parent-relative resolution remains workspace-confined and fails closed on repository escapes. These are evidence projections only: Hashmarks does not execute model reasoning, patches, arbitrary shell commands, or git workflows.

The release qualification contains two answer-blind evidence tiers. A reproducible paired 30-task polyglot run reached 30/30 exact edit ownership and 30/30 verified outcomes in both Native and Hashmarks lanes; Hashmarks used 90.4% less raw repository evidence, 46.3% less total visible decision evidence, and 47.8% fewer decision interactions. A separate model-directed ChatGPT run reached 6/6 exact edit ownership and 6/6 verified outcomes in both lanes while Hashmarks used 88.5% less raw repository evidence and 35.3% less total visible decision evidence against a stronger Native strategy that reused grep output instead of rereading route/test files. Exact model token telemetry is not inferred from byte counts.

Release packaging also fails closed when `pyproject.toml` and `hashmarks/_version.py` disagree, preventing package metadata/runtime-version drift.

## Identity stays hot; CodeMap is derived

Hashmarks now has a hard performance boundary between authoritative identity and agent-oriented repository understanding:

```text
                        Hashmarks
                           |
          +----------------+----------------+
          |                |                |
       Identity          Impact           CodeMap
          |                |                |
      authoritative     work reuse       derived/advisory
      latency-critical                    background/on-demand
```

The Identity lane never imports CodeMap. AST parsing, lexical indexing, repository maps and context construction therefore cannot enter the daemon's hot identity request path.

CodeMap is the agent-facing structural index. It can be cold-built once and then maintained incrementally in a separate watcher process:

```bash
hashmarks map sync
hashmarks map watch
```

Agents do not need to read the whole repository to orient themselves. The progressive interface is:

```bash
hashmarks orient
hashmarks find "terminal cancellation"
hashmarks grep "request-time observation barrier"
hashmarks outline hashmarks/identity.py
hashmarks symbol Identity.impact_engine
hashmarks deps Identity.impact_engine
hashmarks affected src/users.py
hashmarks tests src/users.py
hashmarks source hashmarks/identity.py::Identity.impact_engine --budget 800
hashmarks context "terminal cancellation" --budget 4000
```

The intended disclosure ladder is:

```text
L0  repository capsule / path existence
L1  outline: symbols + signatures + line ranges
L2  dependencies / references / related tests
L3  one exact symbol source range under an explicit token budget
L4  whole-file reads only when the agent still needs them
```

`hashmarks context` is allowed to abstain. Insufficient retrieval confidence returns no guessed context and tells the caller to fall back to repository search.

### Agent-content policy is separate from identity

Hashing a file, structurally indexing it, and disclosing its implementation to an agent are separate authorities. Secret-like paths are denied from CodeMap by default, source symlinks are never followed, and repo-specific policy can further restrict agent visibility:

```toml
# .hashmarks-context.toml
[[rule]]
pattern = "vendor/**"
agent = "outline"

[[rule]]
pattern = "private/**"
index = false
agent = "deny"
```

`agent = "outline"` permits structural names/signatures/relationships but not source bodies or lexical grep results. `index = false` removes the path from the workspace CodeMap; a later policy transition to index-denied also purges its shared parsed artifact.

### Content-addressed parse artifacts

Parsed artifacts are keyed by:

```text
file content digest
+ language
+ parser/version
+ CodeMap schema
```

Git worktrees of the same repository can therefore reuse identical parsed artifacts without sharing workspace-specific dependency state. Workspace relationships and generations stay in `.hashmarks/codemap.sqlite3`; reusable parse artifacts live in a repository-keyed user cache and can be removed explicitly:

```bash
hashmarks map clean
hashmarks map clean --shared-artifacts
```

Python uses stdlib AST structural evidence. JS/TS, Go and Rust retain clearly provenance-tagged lightweight fallback outlines/imports. Hashmarks 0.10.0 can additionally use an optional Tree-sitter range provider when `tree-sitter-language-pack` is already installed, import existing SCIP definitions/references, call the repository's own TypeScript compiler API for tsconfig-aware module resolution, and delegate structural queries to a local `ast-grep`. These are derived-lane precision providers: none is imported or executed by Identity.

### Native CodeMap enrichment

Slower ecosystem intelligence is explicit. Ordinary `map sync`, Identity, and the identity daemon never launch build tools:

```bash
hashmarks map enrich
hashmarks map enrich --provider nx-project-graph
hashmarks map enrich --provider pants-target-graph
hashmarks map enrich --provider npm-package-graph
hashmarks map enrich --provider maven-pom-graph
hashmarks map enrich --provider gradle-project-graph
hashmarks map enrich --provider go-list
hashmarks map enrich --provider cargo-metadata
hashmarks map enrich --provider declared-project-links
hashmarks map enrich --provider typescript-resolver
hashmarks map enrich --provider pyright-typeserver
hashmarks map enrich --provider vitest-vite
hashmarks map projects
```

`map enrich` consumes native/manifest project evidence from Nx, Pants, npm workspaces, Maven, Gradle, Go, Cargo, TypeScript, Vite/Vitest, and Pyright Type Server when those authorities exist in the repository. `.hashmarks-project-links.toml` can explicitly compose otherwise independent provider graphs (for example a backend, frontend, and shared OpenAPI contract). Native evidence is retained separately from heuristic CodeMap edges and is freshness-bound to the source generation and/or the manifest bytes that produced it. When those inputs move, stale native evidence remains cached but stops participating in `find`, `deps`, `affected`, and context ranking until explicitly refreshed.

Python import resolution can use the separately installed `pyright-typeserver` through its published Type Server Protocol. Hashmarks performs the LSP/TSP handshake, binds queries to a snapshot, retries a stale-snapshot cancellation once, accepts only workspace-local file results, and currently supports the `0.4.x` TSP line conservatively. This is explicit CodeMap enrichment only; it never enters Identity or grants execution/reuse authority. SCIP remains the preferred source for cross-language definitions/references.

Python module/cache ownership can also be inspected as derived repository evidence:

```bash
hashmarks map import-ownership
hashmarks map import-ownership --path scripts/research.py
```

This diagnostic uses CodeMap lexical evidence only to shortlist candidates and then requires an AST-proven `spec_from_file_location` → `module_from_spec` → `exec_module` chain. When the target is a unique repository package module, Hashmarks reports that normal import identity. Test/plugin loaders and explicit `sys.modules` ownership are advisories rather than production warnings. Hashmarks does not rewrite or execute imports.

Existing SCIP indexes can be imported without making SCIP a runtime dependency:

```bash
hashmarks map import-scip index.scip
```

When the `scip` CLI is available, binary indexes are converted through its official JSON output. Pre-exported SCIP JSON is accepted too. Syntax-aware search is similarly optional:

```bash
hashmarks structural '$A.login($B)' --lang python
```

A local `ast-grep` is used when available; Hashmarks still enforces its own agent-content policy on returned matches.

### Persistent grep accelerator

CodeMap stores lexical occurrences, not whole source copies, and uses them to narrow exact-text searches to candidate lines. The candidate line is re-read from the current workspace before disclosure. This lets agents replace many repository-wide `grep -> read -> grep` loops with one small query while keeping actual source bytes authoritative.

### Separate freshness generations

CodeMap never pretends derived state is newer than the evidence supporting it. With the identity daemon available, a lightweight observer barrier binds a full CodeMap sync to a stable filesystem observation generation. `hashmarks map watch` can instead own CodeMap continuity independently. If neither continuity source exists, freshness is reported as unproven rather than silently assumed.

Hashmarks deliberately does not run whole-repository PageRank during a query. v0.10.0 retains cheap caller/reference expansion and local relation boosts because a request-time global rank measurably regressed `find` latency. Retrieval quality is gated by a retained real-task corpus (file/symbol recall, first-hit rate, fallback-search rate, and context budget), not by ranking complexity for its own sake.


## Multi-repository agent retrieval gate (0.10.0)

Hashmarks no longer accepts a retrieval change merely because it works on Hashmarks itself. The retained release gate replays localization corpora against both Hashmarks and a real Oh-Goon checkpoint and fails on recall, fallback-search, or query-latency regressions.

```bash
python scripts/agent_evaluation/metrics_agent_suite.py \
  --repo "hashmarks=.::benchmarks/agent_tasks.json" \
  --repo "oh-goon=/path/to/oh-goon::benchmarks/external/oh_goon_1267_0_49_agent_tasks.json" \
  --budget 1200 --limit 20 \
  --min-file-recall 1 --min-symbol-recall 1 --max-fallback-rate 0
```

The current retained two-repository corpus contains 39 tasks. The release gate targets 100% expected-file recall, 100% expected-symbol recall and zero fallback repository searches before token reduction is considered. Latency is measured separately so ranking/index ideas cannot silently reintroduce graph-size request latency.

v0.10.0 also fixes real mixed-repository issues found by that gate: duplicate structural symbol candidates are canonicalized before persistence; small control files such as `Makefile` are searchable without admitting noisy lockfiles; lexical queries narrow to indexed candidate files; caller expansion uses an indexed short-target field instead of repeated suffix scans; query tokenization is cached per request; JS/TS `const` bindings are represented structurally; file-level lexical coverage can rank symbol-less control files; and `find` reserves limited path diversity so one rich file cannot crowd out another required file.

### Real agent trace accounting

Localization metrics estimate how much source an agent can avoid reading, but they are not a claim about actual model-token savings. `scripts/agent_evaluation/metrics_agent_trace.py` reads legacy `hashmarks.agent-trace.v1` records and the hardened `hashmarks.agent-trace.v2` contract for Codex, Pi, or other agents. v2 binds each run to a run ID, repository identity, task revision, and model/config identity. Correctness is not trusted from the agent trace itself: strict comparison requires separate `hashmarks.agent-verdict.v1` evidence from an independent grader. Exact token accounting is independently owned too: strict comparison also requires `hashmarks.agent-model-usage.v1` provider evidence keyed to the exact task/mode/run. A trace may contain an advisory token count, but external provider usage overrides it and only provider-owned usage can authorize a strict token-saving claim. Baseline and Hashmarks runs must match repository/task/model identities before any claim is eligible. Duplicate or unpaired traces, duplicate usage/verdict evidence, self-attested correctness, missing provider token evidence, identity mismatch, or correctness regression all fail closed. Aggregate token reduction is computed from total paired provider-reported model-input tokens rather than averaging per-task percentages, so tiny tasks cannot distort the claim.

## Canonical real-agent experiments

`hashmarks.agent-experiment.v1` turns real Codex/Pi evidence from a loose bag of files into one fail-closed experiment manifest. The manifest enumerates every expected baseline/Hashmarks run and binds task/repository revision, model/config identity, runner identity, trace, independent verdict, provider usage, and the exact retained subject artifact graded for that run. `scripts/agent_evaluation/metrics_agent_experiment.py` rejects duplicate or unpaired runs, identity drift, path escape, missing evidence, and verdicts whose `subject_digest` does not match the exact retained patch/output bytes.

With `--strict-raw-evidence`, each verdict and provider-usage record must also point through the manifest to retained raw grader/provider evidence bytes whose SHA-256 exactly matches the record's `evidence_digest`. This means a claim-grade experiment has four bound layers: agent activity trace, exact patch/output subject, independent grading evidence, and independent provider usage evidence. The experiment manifest itself is SHA-256 identified in the resulting report.

`make metrics-agent-experiment EXPERIMENT=/path/to/experiment.json` runs this strict manifest gate. It does not generate or invent Codex/Pi results; it only validates evidence actually retained by the runner/provider/grader.

## One-command developer verification

For normal development, run:

```bash
make dev-check
```

This is the supported junior-friendly “is my branch OK?” boundary. It performs a locked dependency sync, local runtime doctor, source compilation, CodeMap sync, and deterministic bounded pytest shards. A failure prints the failed stage and a copy/paste reproduction command. `make verify` is an alias for the same boundary.

`make release-check` runs the same local preflight but deliberately does **not** claim canonical release proof. Deterministic source-artifact reconstruction, exact-parent replay/package proof, persistent archive storage, and independent readback remain maintainer/release gates.

## Fast bootstrap + reproducible metrics

The repository now has one deliberately small developer entrypoint. It does **not** invent a second environment manager; Make only delegates to locked uv commands.

```bash
make init
make bootstrap
```

`make init` is the explicit native-uv preparation boundary: it resolves the committed test dependency intent using the operator-configured package index and writes only local, gitignored `uv.lock` state. `bootstrap` then consumes that prepared state with frozen/offline semantics. Private registry configuration and credentials remain external to the repository.

Start the maintained identity daemon:

```bash
make start
```

Collect the quick baseline used to decide whether a later optimization phase is justified:

```bash
make metrics
```

Or bootstrap + metrics as one entrypoint:

```bash
make baseline
```

The metrics artifact is written under:

```text
.hashmarks/metrics/baseline-<UTC>.json
.hashmarks/metrics/latest.json
```

The baseline records:

- the real repository hot identity path;
- synthetic directory-manifest identity;
- synthetic explicit-file manifest identity;
- daemon continuity for both manifest shapes;
- Impact first-run / unchanged-reuse / relevant-edit timings;
- Python/platform/uv/version parameters.

Scale is explicit rather than accidental:

```bash
make metrics-scale     # 100k synthetic files
make metrics-500k      # intentionally heavy 500k profile
make metrics FILES=50000 HOT_REQUESTS=50
```

Compare a later phase against a retained baseline:

```bash
make metrics-compare BASE=.hashmarks/metrics/baseline-OLD.json
```

The comparison reports every common timing metric with absolute and percentage deltas, so an optimization phase can prove what improved and what regressed.

For a fast smoke without daemon benchmarks:

```bash
make metrics-fast
```

This is measurement tooling, not an execution authority. Metrics files live under `.hashmarks` and therefore never participate in source identity.

## Small public API

Most developers should start here:

```python
from hashmarks import Directory, File, Identity

with Identity(".") as identity:
    snapshot = identity.snapshot(
        Directory("src"),
        File("pyproject.toml"),
        File("uv.lock"),
    )

    step = identity.step(
        snapshot,
        argv=["pytest", "-q"],
        toolchain={"python": "3.14"},
    )

    print(snapshot.hash)
    print(step.hash)
```

`Identity` defaults to `mode="auto"`:

```text
running daemon available
        -> use maintained daemon state

daemon unavailable
        -> safe local reconciliation
```

The fallback changes performance, **never canonical identity semantics**.

Force a mode when needed:

```python
Identity(".", mode="daemon")
Identity(".", mode="local")
```

Local long-lived observation is explicit:

```python
# Safest default: reconcile every local read.
Identity(".", mode="local", local_observer="reconcile")

# Linux/WSL: hot local object with request-time inotify barrier.
Identity(".", mode="local", local_observer="watcher")

# Expert embedding: caller owns record_changes().
Identity(".", mode="local", local_observer="manual")
```

## Typed inputs

```python
from hashmarks import Directory, File, Glob

Directory("src")        # must be a real directory
File("uv.lock")         # must be a file or symlink leaf
Glob("tests/**/*.py")   # must contain glob syntax
```

Plain strings remain supported for compact integrations.

## Snapshots and explanations

A `Snapshot` is the canonical identity of resolved inputs at a point in the observation lifecycle:

```python
before = identity.snapshot(File("src/a.py"))
# edit file...
after = identity.snapshot(File("src/a.py"))

print(after.diff(before).as_dict())
```

Step snapshots explain cache-key changes by component:

```python
old_step = identity.step(before, argv=["pytest"])
new_step = identity.step(after, argv=["pytest"])

print(new_step.diff(old_step).as_dict())
# changed_components: ["inputs"]
```

## CLI: daemon optional by default

Start the daemon when you want continuity across CLI processes:

```bash
uv run --extra daemon hashmarks daemon start --workspace .
```

Then normal commands automatically use it:

```bash
uv run hashmarks root \
  --workspace . \
  --input src \
  --input pyproject.toml
```

If no daemon is running, `root`/`snapshot`/`step` safely fall back to local reconciliation.

Force behavior:

```bash
uv run hashmarks root --mode daemon --workspace . --input src
uv run hashmarks root --mode local  --workspace . --input src
```

Snapshot alias:

```bash
uv run hashmarks snapshot --workspace . --input src
```

Diagnostics:

```bash
uv run hashmarks doctor --workspace .
uv run hashmarks stats --workspace .
```

Daemon lifecycle:

```bash
uv run --extra daemon hashmarks daemon start --workspace .
uv run hashmarks daemon status --workspace .
uv run hashmarks daemon stop --workspace .
```

## Linux/WSL daemon safety

Linux/WSL uses native `inotify` through stdlib + `ctypes`; there is no mandatory third-party runtime dependency.

The daemon deliberately separates persistent state from runtime IPC:

```text
/mnt/c/.../repo/.hashmarks/       persistent SQLite/CAS/logs
/run/user/UID/hashmarks/...sock   ephemeral Unix socket
```

If the preferred runtime path would exceed the AF_UNIX path limit, Hashmarks falls back to a short `/tmp/fi-UID/...` namespace.

Before an identity request trusts hot state, the native watcher performs a **request-time barrier**: it drains already-queued inotify events into `ChangeTracker`. If a watcher backend cannot establish that barrier, Hashmarks transitions to `UNKNOWN` and reconciles instead of returning possibly stale hot state.

## Huge explicit manifests: register once

Sending 500,000 file paths as JSON on every daemon request would destroy the hot path. Hashmarks therefore supports registered manifests.

```python
from hashmarks import InputManifest
from hashmarks.client import IdentityClient

manifest = InputManifest(tuple(paths))
client = IdentityClient(".")
handle = client.register_manifest(manifest)

first = client.input_root_manifest(handle)
hot = client.input_root_manifest(handle)
```

The manifest is uploaded once in bounded chunks. Subsequent requests send only the small fingerprint handle.

`Identity.snapshot_manifest(manifest)` manages this registration automatically.

## Measured behavior

User benchmark on 0.3.2, 500,000 explicit files:

```text
hot unchanged           1.18 ms
one-file edit          20.76 ms
100-file edit          23.37 ms
```

User benchmark on 0.3.2, 500,000 files with daemon continuity:

```text
hot IPC average         0.484 ms
hot IPC minimum         0.271 ms
one-file edit          77.3 ms
```

0.4.0 registered-manifest sanity check in the build environment, 100,000 explicit files:

```text
manifest registration  ~2.55 s   one-time IPC upload
first identity          ~6.47 s
hot IPC average         ~0.264 ms
hot IPC minimum         ~0.172 ms
one-file edit           ~2.3 ms
```

The design target is therefore achieved: **hot work scales with the changed set, not total repository size**.

## Stats

`Identity.stats()` / `hashmarks stats` exposes useful counters including:

```text
file metadata checks
content hashes
digest reuses
SQLite lookup batches
rows written
directory cache hits
directory recomputes
path-cache hits
manifest-tree hits/misses
manifest digest calls
verify calls
hot-cache drops
action-cache entries
CAS bytes
observation state/generation
```

These are diagnostics only; none participate in canonical identity.

## Canonical vs observation

Canonical:

```text
file bytes
   -> File Digest
   -> Directory Merkle / Manifest Merkle Trie
   -> Input Root
   -> Step Identity
```

Accelerators only:

```text
mtime / ctime / inode
SQLite rows
watcher events
daemon lifetime
hot leaf/Merkle/manifest nodes
```

An accelerator may decide **what does not need recomputation**. It never changes what an identity means.

## Impact: prove what work does not need to run

Hashmarks 0.5.0+ adds a generic **Impact** layer above canonical identity. The core does not know pytest, npm, Go, Rust, Java, or any other build system. Adapters supply dependency evidence; Hashmarks owns the reusable WorkIdentity and the safe decision.

Every work unit is classified as exactly one of:

```text
AFFECTED             -> run
VERIFIED_UNAFFECTED  -> reuse previous PASS
UNKNOWN              -> run conservatively
```

The invariant is strict: **UNKNOWN means run. A previous result may be reused only when the previous result was PASS, the current WorkIdentity is identical, the dependency evidence is complete, and the current runner policy trusts the authority that asserted completeness.**

### Universal declared-input mode

Any repository can opt in without a language adapter. Create `.hashmarks-impact.toml`:

```toml
[[work]]
id = "unit-tests"
kind = "test"
inputs = ["src/**", "tests/**", "pyproject.toml", "uv.lock"]
complete = true
execution_complete = true
command = ["pytest", "tests"]

[[work]]
id = "lint"
kind = "lint"
inputs = ["src/**", "pyproject.toml"]
complete = true
execution_complete = true
command = ["ruff", "check", "src"]
```

Then inspect the decision:

```bash
uv run hashmarks impact assess \
  --workspace . \
  --config .hashmarks-impact.toml \
  --trust-declared-config
```

On the first run there is no reusable PASS, so work is `UNKNOWN`. Execute and record successful identities automatically:

```bash
uv run hashmarks impact run \
  --workspace . \
  --config .hashmarks-impact.toml \
  --trust-declared-config
```

Run the same command again with unchanged inputs and the successful units are `VERIFIED_UNAFFECTED` and reused rather than executed. If a relevant input changes, that unit becomes `AFFECTED`.

`complete = true` is an **assertion**, not an authority. Declared work defaults to partial (`complete = false`), and even an explicit dependency-completeness claim cannot authorize reuse unless the runner opts in with `--trust-declared-config` (or supplies an equivalent `ImpactTrustPolicy`). Command-bearing work also requires a separate `execution_complete = true` claim before a PASS can be reused. Hashmarks automatically resolves and fingerprints the executable (and shebang interpreter when present), but it does not pretend that executable bytes alone prove every package/runtime/toolchain dependency. The trusted completeness claim is therefore still explicit. Empty complete input sets are rejected.

### Generic native/observed evidence interchange

Hashmarks deliberately does not reimplement mature dependency resolvers. Native tools can emit `.hashmarks-observed.json`:

```json
{
  "schema": "fastidentity.observed-dependencies.v1",
  "producer": "my-test-runner",
  "work": [
    {
      "id": "test:auth",
      "kind": "test",
      "inputs": ["tests/test_auth.py", "src/auth.py", "src/users.py"],
      "command": ["pytest", "tests/test_auth.py"],
      "complete": true,
      "execution_complete": true
    }
  ]
}
```

`complete: true` means the producer asserts that the listed dependency set is complete enough to justify reuse. `complete: false` is still useful evidence, but unchanged work remains `UNKNOWN`. **Generic observed JSON is not trust-eligible by default**, even if it claims an allowlisted producer name. A trusted integration must create the observed adapter/channel with `trust_eligible=True`, and the runner must separately allowlist that producer. This prevents a repo-controlled JSON file from spoofing a trusted producer name. This is the intended bridge for pytest-testmon/Coverage-style observations, Vitest/Vite, Nx/Pants, compiler depfiles, Go/Cargo metadata, and custom harnesses.

### Conservative built-in discovery

Detect available adapters:

```bash
uv run hashmarks impact detect --workspace .
```

Built-in Python and Node adapters provide **partial** dependency evidence, and 0.6.x prefers native ecosystem discovery where it is already available:

```bash
uv run hashmarks impact assess --workspace . --adapter python
uv run hashmarks impact assess --workspace . --adapter node
uv run hashmarks impact assess --workspace . --adapter coverage
```

Python:

- if the repository has a project-local `.venv/bin/pytest` (or `venv/bin/pytest`), Hashmarks asks `pytest --collect-only -q` which test files really exist;
- dependency edges are still built conservatively from Python AST imports;
- a Coverage.py `coverage.json` generated with `coverage json --show-contexts` can provide observed test-file -> executed-code evidence.

Node/Vitest:

- if `node_modules/.bin/vitest` exists, Hashmarks uses `vitest list --filesOnly` for native test-file discovery;
- relative JS/TS imports remain a conservative fallback dependency graph;
- bare aliases, plugins, dynamic imports, assets and runtime resources keep evidence partial.

Native discovery does **not** automatically mean complete evidence. Pytest collection and Vitest listing improve correctness of test discovery; Coverage contexts improve precision of observed code dependencies. None of those alone proves that every data file, subprocess, service or plugin input was captured, so unchanged work remains `UNKNOWN -> run` unless completeness is explicitly asserted **and** separately authorized by trusted runner policy.

Hashmarks 0.9.0 also includes conservative native Impact adapters for Nx, Pants, Go, Cargo, Maven, Gradle, and declared compiler depfiles. These adapters use native project/package metadata where possible, but remain **partial evidence by default**: they can prove work is affected and narrow execution, but cannot authorize a skip unless the normal completeness + trust policy independently proves that reuse is safe.

The generic `.hashmarks-observed.json` interchange remains the route for pytest-testmon, richer Vite/Vitest integrations, custom harnesses, and other authorities that can provide a complete input set.

Adapter discovery prunes `.git`, `.hashmarks`, `.venv`, `node_modules`, build outputs, and common cache directories before traversal.

### Positive-only native test selection (0.9.0+)

Hashmarks keeps **selection** separate from **reuse authority**. A native tool may prove that a test must run; omission from that tool's selection can never, by itself, prove the test reusable.

```bash
hashmarks impact detect --workspace .
hashmarks impact select --workspace . --selector testmon
hashmarks impact select --workspace . --selector vitest-vite --changed src/auth.ts
```

`testmon` uses pytest-testmon's public CLI (`--testmon --testmon-nocollect --collect-only`) and deliberately never parses private `.testmondata`. `vitest-vite` asks the repository's own Vitest/Vite module graph for affected test files without executing the tests. A precomputed `vitest-related` export remains available as a generic bridge. Every result is **positive-only**: selected tests should run; omitted tests receive no skip authority. The Vite-resolved file graph can also be retained in CodeMap as freshness-bound native dependency evidence.

### Library API

```python
from hashmarks import Identity, ImpactTrustPolicy, WorkUnit

unit = WorkUnit.declared(
    "unit-tests",
    inputs=("src", "tests", "pyproject.toml"),
    command=("pytest", "tests"),
    complete=True,
    execution_complete=True,
)

with Identity(
    ".",
    impact_trust_policy=ImpactTrustPolicy.trusted_declared(),
) as identity:
    impact = identity.impact_engine()
    assessment = impact.assess_one(unit)

    if assessment.must_run:
        # Execute assessment.execution.resolved_argv, then promote only if
        # WorkIdentity is still unchanged after the successful command.
        promotion = impact.promote_pass(assessment)
```

The persistent impact-result database is workspace-scoped even when multiple workspaces share an explicitly configured state directory.

Execution-start failures are persisted as `ERROR`. Missing commands, missing working directories, and OS launch failures therefore invalidate any older reusable PASS instead of leaving stale success state behind.

### Execution and result authority (0.6.2)

`WorkIdentity` now binds the executable authority selected for the command. `impact run` resolves `argv[0]` once, fingerprints its bytes (and a shebang interpreter when present), executes that exact resolved path, and re-checks WorkIdentity after a zero exit code before promoting PASS. If inputs or execution authority change while the command runs, the result is `stale` and is not promoted.

Work units have an explicit reuse policy:

- `validation` — a PASS may be reused when dependency + execution identity are complete, trusted and unchanged;
- `artifact` — the same rules apply, and declared `outputs` must still match the output identity recorded with PASS;
- `never` — side-effect work always runs.

Example artifact work:

```toml
[[work]]
id = "build"
kind = "build"
inputs = ["src/**", "package.json", "package-lock.json"]
outputs = ["dist"]
reuse = "artifact"
complete = true
execution_complete = true
command = ["npm", "run", "build"]
```

Hashmarks currently reruns artifact work when outputs are missing or changed. A future CAS integration may restore the exact recorded outputs instead, without changing the reuse proof.

Daemon compatibility is also semantic, not merely transport-level: v0.6.2 clients require the current protocol, daemon semantics identifier, and capabilities including the request-time observer barrier. `auto` mode falls back to safe local reconciliation when an older daemon is present; explicit `daemon` mode rejects it.

Auto-discovered repository TOML/observed JSON is also **not automatically an execution authority**. `impact assess` can consume it safely as evidence, but `impact run` refuses repo-supplied commands discovered implicitly unless the caller explicitly selects the config or passes `--allow-repo-commands`. Dependency trust (`--trust-declared-config`) and permission to execute repository commands are intentionally separate decisions.

## Using Hashmarks from Oh-Goon or another orchestrator

Keep Hashmarks as a standalone dependency. An orchestrator should use the library for assessment/identity and keep its own process/sandbox authority. In particular, Oh-Goon should execute work through its normal executor and call `ImpactEngine.promote_pass(pre_run_assessment)` only after a successful execution. Do not delegate Oh-Goon process execution to the convenience `hashmarks impact run` command. See `docs/integration/OH_GOON_INTEGRATION.md` for the intended ownership boundary.

`hashmarks version` and `hashmarks.__version__` expose the package version for provenance; daemon status exposes protocol, semantics and capabilities.

## Advanced primitives

The lower-level APIs remain available for build-system and execution-engine authors:

```text
IdentityEngine
MerkleTree
FileDigestStore
ChangeTracker
CAS
ActionCache
ExecutionCache
IdentityGraph
```

`CASBackend` and `ActionCacheBackend` protocols define the storage boundary so remote backends can be added without changing identity computation. Advanced callers can inject them directly:

```python
engine = IdentityEngine(
    ".",
    cas_backend=my_remote_cas,
    action_cache_backend=my_remote_action_cache,
)
```

Injected backends remain caller-owned; `IdentityEngine.close()` only closes backends it created itself.

## Benchmarks

Synthetic local identity:

```bash
uv run python benchmarks/bench_identity.py --files 500000 --manifest directory
uv run python benchmarks/bench_identity.py --files 500000 --manifest files
```

Daemon continuity, including explicit-file registration:

```bash
uv run --offline python benchmarks/bench_daemon.py --files 500000 --manifest directory
uv run --offline python benchmarks/bench_daemon.py --files 500000 --manifest files
```

Existing repository:

```bash
uv run python benchmarks/bench_repo.py \
  --workspace . \
  --input hashmarks \
  --input tests \
  --input pyproject.toml
```

## Tests

The package itself has no registry dependency. Supply pytest explicitly:

```bash
uv run --with pytest pytest -q
```

## Identity schemas

Canonical objects are domain/version separated. Public metadata exposes names such as:

```text
fastidentity.identity.v1
fastidentity.file.v1
fastidentity.directory.v1
fastidentity.input-manifest.v1
fastidentity.input-root.v1
fastidentity.step.v1
fastidentity.snapshot.v1
```

Identity-format evolution must change the relevant schema/domain rather than silently reinterpreting old cache keys.


## Multi-experiment claim authority (0.10.5)

`hashmarks.agent-experiment-set.v1` aggregates already-valid `hashmarks.agent-experiment.v1` manifests without turning repeated rows into fake breadth. Each set member is bound by path **and expected manifest SHA-256**. Set ingestion reruns the underlying strict experiment validation, rejects duplicate experiment IDs, duplicate manifest bytes, reused run IDs, and reused `(repository_identity, task_id, task_revision)` identities, and requires consistent model, model-config, task-policy, and any declared runner/grader/provider/benchmark-protocol identities.

The resulting report distinguishes a narrowly described controlled result from a broader/public claim. Broad/public eligibility uses fixed non-user-lowerable breadth floors of **3 experiments, 3 distinct repositories, and 30 unique tasks**. Meeting those floors is only an evidence-breadth gate; it does not by itself prove statistical significance or authorize claims beyond the measured model/config/task policy. Use `--require-public-broad-claim` when a publication/release gate must fail unless those floors are met.

No synthetic fixture, source-estimated token ratio, or duplicated task can authorize a real-world token-saving claim.


### Replication and descriptive uncertainty (0.10.6)

`hashmarks.agent-experiment-set.v2` adds explicit `replication_group` ownership and a replication policy. Repeated controlled experiments can now describe run-to-run variation and a deterministic bootstrap confidence interval over the exact retained experiments. Repetitions never count as extra repository/task breadth, and the interval is explicitly descriptive: it does not establish population generalization or authorize a broad public claim by itself. v1 manifests remain readable with unchanged semantics.


## Retrieval Regret Observatory (0.10.7)

Hashmarks can now replay a real agent trace against an independently authored `hashmarks.agent-retrieval-evidence.v1` manifest. The manifest binds task/repository identity and names the repository-relative paths that constitute required evidence; the agent trace cannot self-declare usefulness. `scripts/agent_evaluation/metrics_agent_regret.py` reports tokens/searches/reads before first required evidence, duplicate queries, duplicate reads, irrelevant-read estimated tokens, discovery order, and explicitly missing required evidence. Missing evidence is never scored as zero regret. This phase is observational only: it does not alter CodeMap ranking or authorize a real-world token-saving claim.

Use `make metrics-agent-regret TRACE=... EVIDENCE=...` to produce `.hashmarks/metrics/agent-regret-latest.json`.


## Derived Intelligence Graph (0.10.8)

CodeMap now records dependency-tracked derived values for each indexed file: `content`, `symbol_surface`, `relationship_surface`, `outline_surface`, and `lexical_surface`. Each node stores both a stable identity of the derived semantic value and the upstream identities that were consumed to compute it. Those are deliberately separate: after a source-byte change, a later phase can recompute a surface and stop invalidation when the semantic identity is unchanged.

`CodeMap.derived_graph(path)` exposes the graph diagnostically. Retrieval/ranking does not consume the graph in 0.10.8, so this phase changes no search/context semantics. Existing CodeMap databases are backfilled lazily on their next sync.


## Semantic Invalidation Shields (0.10.9)

CodeMap sync now compares the previous and recomputed derived semantic identities and reports `derived_surfaces_changed`, `derived_surfaces_preserved`, and `semantic_invalidation_shields`. A shield occurs when upstream input identity changed but the derived semantic value identity did not. This creates the Salsa/DICE-style propagation stop needed by later derived caches.

The shield deliberately does **not** skip line-level source-index refresh. A body edit or inserted line may preserve an agent-facing symbol signature while moving source locations; Hashmarks refreshes those rows for correctness while preventing unchanged higher-level semantic identities from propagating invalidation to future derived consumers.


## Branch/worktree base snapshots + local overlays (0.10.10)

A clean Git HEAD can now publish an immutable shared CodeMap base snapshot under the repository-common cache. Sibling worktrees at the same Git tree reuse the retained SHA-256 file digest and shared parsed artifact for paths that Git proves are unchanged, avoiding redundant hashing/parsing when materializing their local workspace map. Staged, unstaged, deleted, renamed and untracked paths form the local overlay and always fall back to ordinary workspace processing. Hashmarks' own `.hashmarks/` / `.fastidentity/` state is excluded from overlay identity.

The snapshot never becomes Identity authority: it is CodeMap-only advisory reuse and is accepted only when the Git base tree, language, visibility and retained content-addressed artifact all match. Failure to prove the overlay simply disables snapshot reuse. Sync reports `base_snapshot_reused`, `base_identity`, and `overlay_paths`.


### Query intent routing (0.10.11)

CodeMap now classifies deterministic query intent before candidate expansion: identifier, path, relationship, config, test, structural, conceptual, or hybrid. Strong path/config/test intent can skip irrelevant native-definition expansion, relationship intent keeps broader caller expansion, and ambiguous queries retain the complete hybrid retrieval path. `CodeMap.query_route()` exposes the route as diagnostic evidence without executing search. Routing is an optimization policy only and never grants recall authority.


## Progressive context protocol (0.10.12)

Hashmarks context is now an explicit progressive-disclosure protocol rather than one all-or-nothing context request. All levels use the same CodeMap generation and ranked evidence; escalation therefore adds detail without changing repository truth.

```bash
hashmarks context "terminal cancellation" --level orient   --budget 400
hashmarks context "terminal cancellation" --level outline  --budget 700
hashmarks context "terminal cancellation" --level evidence --budget 1000
hashmarks context "terminal cancellation" --level source   --budget 1200
```

`orient` returns only ranked candidate identities. `outline` adds signatures and structural outlines. `evidence` adds bounded dependency/relationship signatures. `source` is the only level permitted to upgrade strong, agent-visible symbols to exact source ranges. The JSON response uses `hashmarks.context-pack.v2`, records the current `disclosure`, and advertises `next_disclosure` so an agent can escalate deterministically. Calling `context()` without a level still means `source`, preserving the earlier API behavior.


## Bounded candidate/rerank pipeline (0.10.13)

`find()` now has an explicit two-stage scaling boundary. Persistent lexical/path/symbol/relationship indexes generate a broad candidate pool cheaply. Normal candidate sets are passed through unchanged. Only unusually broad pools are reduced to a generous, path-diverse rerank working set before the full scorer runs. This means a future semantic or model reranker can operate over hundreds of candidates rather than repository scale, while the existing deterministic hybrid retrieval remains the recall floor.


## Content-addressed context reuse (0.10.14)

Context generation is now an identity-bound action. Hashmarks hashes the exact workspace fingerprint, CodeMap generation, policy fingerprint, query, budget, limit, disclosure level, retrieval protocol and ranked hit evidence. The derived context payload is stored in the local CAS and the response exposes both the context action hash and content digest. Repeating an equivalent structural context request can therefore reuse the payload without rebuilding graph/outline assembly.

Freshness is deliberately outside the cached payload: generation/staleness/warnings are rebuilt on every request. Exact source-range context is cached only when filesystem freshness is positively proven; without that proof Hashmarks rereads source live and leaves the cache identity empty.


## Multi-agent shared retrieval (0.10.15)

Hashmarks now single-flights equivalent concurrent repository-intelligence requests inside one process. Multiple agents asking the same `find` or structural `context` question for the same repository generation/policy join one computation and receive the same immutable result. The in-flight entry is deleted immediately after completion; longer-lived reuse remains the separately verified Context CAS.

This is intentionally not an agent-state cache. Prompts beyond the exact retrieval query, conversation/session history, intermediate exploration and mutable tool state are never shared. Exact source-context requests join a flight only when filesystem freshness is positively proven; otherwise each request rereads source independently.

The release gate also exposed a ranking cliff caused by many newly added test symbols. Hashmarks closes that generally rather than demoting tests: Python annotations now contribute bounded structural type edges (`return-type`, `parameter-type`, `inherits`, `attribute-type`). Exact query-name symbols may expand through those edges to local type symbols, with at most two directly related type hits protected from lexical crowding. The Python parser identity is bumped to `hashmarks.python-ast.v5` so older parsed artifacts cannot masquerade as type-aware evidence.

Because the richer relationship surface grows the edge table materially on mixed repositories, CodeMap now maintains composite `edge(path,line)` and `edge(path,source,line)` indexes. This keeps path/source relationship lookup bounded as semantic evidence grows; it remains entirely inside the derived CodeMap lane and does not enter Identity latency.


## Real-agent trace intake and regret triage (0.10.16)

Hashmarks now has a runner-neutral intake boundary for genuine Codex/Pi/other-agent navigation logs without guessing tool semantics. `hashmarks.agent-runner-log.v1` requires an explicit `tool_map`; every observed tool must either map to a canonical navigation kind or be explicitly mapped to `null` as intentionally ignored. The normalization-policy identity is recomputed from the exact mapping, the raw runner-log SHA-256 is retained, event order must be monotonic, and repository-relative paths fail closed on escape attempts. `scripts/agent_evaluation/normalize_agent_trace.py` emits the existing hardened `hashmarks.agent-trace.v2` contract, so runner-specific collection does not create a second correctness/token authority.

Retrieval-regret reports are upgraded to v2. In addition to work before the first required path, they report work before **all** independently required evidence is discovered, plus estimated tokens attached to repeated queries and repeated reads. `hashmarks.agent-retrieval-regret-suite.v1` byte-binds exact trace/evidence files across runs and produces a ranked optimization-triage view. These opportunity categories can overlap and MUST NOT be summed into a token-saving claim. They remain observational evidence; independent verdict/provider authorities still own correctness and model-token claims.

Use `make metrics-agent-trace-normalize RUNNER_LOG=...`, then `make metrics-agent-regret ...` or `make metrics-agent-regret-suite REGRET_SUITE=...`. No synthetic example or normalized runner log is real Codex/Pi evidence.


## Repository control-surface intelligence (0.10.18)

Hashmarks now treats repository understanding as more than source symbols. Bounded Markdown/docs and shell/script files join the CodeMap lane, and paths are classified into non-exclusive agent-facing domains: SOURCE, TEST, ARCHITECTURE, OWNERSHIP, BUILD, PLAN, CONFIG, SCRIPT, CONTRACT, and DOC. Query routing derives preferred domains only from the query itself; matching domains receive bounded ranking/reservation help, so ownership/build/plan questions can surface AGENTS.md, READMEs, Makefiles, Plan/Goon YAML, scripts, and contracts without globally promoting those files for ordinary source/test queries.

This phase was selected from the blind Oh-Goon Repository Understanding A/B: v0.10.17 condensed retrieval found at least one SECRET-expected evidence file for 61.9% of 147 PUBLIC questions. The accepted v0.10.18 mechanism raises that retained read-only benchmark to 72.1%, while a broader domain-seeding experiment was rejected because it crowded out source evidence. These are repository-local retrieval measurements, not model-token or correctness claims.

## Crash-safe runner capture journal (0.10.17)

Real runner evidence no longer has to be assembled as one fragile JSON object after the run. `scripts/agent_evaluation/agent_runner_journal.py` provides a create-only journal directory with immutable per-sequence event files. Wrappers explicitly initialize run/repository/model/tool-map identity, then record each observed tool invocation with an explicit sequence number. Each event file is published through an atomic create; duplicate sequence numbers fail rather than overwrite evidence. Finalization requires the exact contiguous `0..N` sequence, sorts files deterministically, validates every tool/path/value through the 0.10.16 normalizer, and emits `hashmarks.agent-runner-log.v1` plus an optional normalized `hashmarks.agent-trace.v2`.

Optional `started_at_ns` / `finished_at_ns` fields are preserved and validated (`finish >= start`). Retrieval regret uses them, when present, to report navigation milliseconds before the first and before all independently required evidence plus total observed navigation duration. Timing is still observational runner telemetry, not provider-token or correctness authority.

The journal deliberately does not infer Codex/Pi tool names, intercept processes, or own execution. Oh-Goon/Codex/Pi wrappers decide which native tool names they emit and provide the explicit mapping. A missing sequence, undeclared tool, duplicate sequence, path escape, invalid timing, or normalization mismatch fails closed.

## 0.10.19 — task-query formulation and bounded multi-view retrieval

`CodeMap.find_task(task)` accepts a full candidate-visible repository task and derives two deterministic retrieval views: a corpus-rarity/identifier-preserving base query and a governance-aware companion query. The views are fused with bounded distinct-path reciprocal-rank fusion (base weight 1.2, governance weight 1.0, at most 80 candidates per view) so ownership/architecture/contract evidence can be added without replacing ordinary `find()` behavior. `CodeMap.task_query_views(task)` exposes the derived views for audit/debugging; `CodeMap.formulate_task_query(task)` returns the governance-aware view.

Task formulation uses only the supplied task text and derived document-frequency statistics from the candidate-visible repository. It never reads answer keys, grader evidence, git history, prior agent state, or execution authority. `find()` and `context()` semantics are unchanged.

## 0.10.21 — deterministic resumable benchmark shards

Hashmarks can now execute known bounded benchmark/test surfaces as deterministic, resumable shards instead of first attempting a monolithic run and discovering the outer execution timeout. The installed CLI exposes a resume-first protocol:

```bash
hashmarks benchmark shards plan \
  --total 147 \
  --shard-size 20 \
  --run-identity sha256:<candidate-plus-inputs> \
  --output-dir .hashmarks/benchmarks/qa-run \
  --warmup-json '["python","qa_worker.py","--warm"]' \
  -- python qa_worker.py --start {start} --end {end} --output {output}

hashmarks benchmark shards warm --output-dir .hashmarks/benchmarks/qa-run
hashmarks benchmark shards next --output-dir .hashmarks/benchmarks/qa-run
hashmarks benchmark shards status --output-dir .hashmarks/benchmarks/qa-run
hashmarks benchmark shards merge --output-dir .hashmarks/benchmarks/qa-run
```

The plan is immutable. Warm-up is explicit and sealed. `next` executes exactly one pending shard, validates row count and unique IDs, then atomically seals the shard with its SHA-256 and manifest identity. Failed or incomplete shards remain pending. `merge` refuses incomplete or duplicate coverage and only publishes an aggregate when every planned row is represented exactly once. `run_identity` binds the plan to the exact candidate/benchmark input identity so results are not silently resumed across changed bytes.

This orchestration layer does not enter the Identity hot path, alter CodeMap ranking, or change benchmark semantics. It only makes long-running verification surfaces predictable and resumable under bounded execution environments.

## 0.10.20 — evidence-family task retrieval

Hashmarks task retrieval now keeps the established rare-term and governance views and adds a third, bounded evidence-family view only when candidate-visible task wording implies a generic repository evidence family. Families cover common repository concepts such as privacy/security, observability, local/offline operation, CI/CD and release, lock/provenance, dependency materialization, browser preflight, read-only observers, snapshot/workspace isolation, network retries, and resource capacity. The view never names project-specific files and does not grant authority or visibility. `find_task()` deduplicates identical views and caps evidence-family fetch depth below the established base/governance fetch depth.

On the retained blind 147-question Oh-Goon QA evidence-localization benchmark, the exact candidate improves any expected-evidence hit from 78.91% to 80.95%, micro expected-file recall from 41.99% to 43.61%, mean question recall from 51.83% to 53.14%, and reduces no-hit questions from 31 to 28. This is retrieval telemetry only, not semantic correctness or certification scoring.

## 0.10.22 — scoped ownership evidence preservation

`CodeMap.find_task()` now preserves one scoped `AGENTS.md` authority only for ambiguous HYBRID task retrieval when the governance view already discovered that file, the fused top results localized inside its subtree, and no README/AGENTS authority is already present. This is a bounded fusion-preservation rule, not new discovery: high-confidence routes such as RELATIONSHIP are never overridden. The blind QA gate recovered Q15 and Q31 with zero previously-hit question losses.

## 0.10.23 — conceptual scoped README preservation + blind benchmark integrity

`find_task()` now preserves one already-discovered deep scoped `README.md` for conceptual tasks when fusion has already localized at least two non-authority top-10 results inside that README's governed subtree. The candidate must already be present in the governance view's first 20 distinct paths; Hashmarks performs no extra scan or path discovery. High-confidence non-conceptual routes remain untouched.

This phase also re-establishes the external Oh-Goon QA benchmark on a physically blind candidate corpus: `docs/certification/answers/` is absent from the indexed repository view. The release benchmark binds exact Hashmarks bytes, blind-corpus identity, retrieval protocol, and grading input, and reports paired parent-vs-candidate wins/losses under one frozen protocol. Historical benchmark artifacts are retained rather than silently rewritten when an integrity issue is found.


## 0.10.24 — graph-backed evidence adjacency

Hashmarks now exposes `CodeMap.task_graph_adjacency(task)` as an additive, one-hop navigation surface for spawned-agent evidence discovery. Canonical `find_task()` ranking is unchanged. Adjacency starts only from canonical task hits, follows mechanically indexed static/native file relations, applies task-affine identifier admission and low-fanout symbol resolution, and returns compact provenance (`seed_path`, `seed_rank`, relation, confidence). A small global list is complemented by at most three candidates per seed so high-degree graph hubs cannot erase locally useful evidence.

On the physically blind Oh-Goon QA corpus, canonical top-20 retrieval remains exactly 147/147 path-for-path identical to 0.10.23 with zero losses. The new graph lane independently exposes expected evidence for 4 of the 25 previously blind questions (Q70, Q72, Q74, Q82). Coincidental same-name call edges such as generic `main`, `get`, `close`, or `start` are deliberately rejected when they lack task affinity or have broad definition fan-out.


## 0.10.25 — multi-surface change-impact navigation

`CodeMap.change_impact()` projects already-proven reverse dependency impact into bounded implementation, contract, verification, build/config, orientation, and other repository surfaces. The API is additive and advisory: it does not alter `find()` or `find_task()` ranking, does not infer fuzzy relationships, and includes depth plus provenance for each reported path.


## 0.10.26 — scoped authority hierarchy

`CodeMap.scoped_authority()` resolves the indexed `AGENTS.md` / `AGENTS.override.md` chain that mechanically applies to an explicit repository path or to bounded `find_task()` target seeds. Root authority is broad, deeper scopes are more specific, and a local override wins at the same scope. The result is a compact path/precedence map only: Hashmarks does not infer authority from README/docs, does not parse repository instructions into permissions, and does not alter canonical retrieval ranking.


## 0.10.27 — retrieval provenance / explainability

`CodeMap.explain_task_retrieval()` exposes the bounded task-query views, per-view distinct-path rank, weighted-RRF contribution, final rank/score, and bounded preservation reason for canonical task retrieval. The surface is observational only and does not alter `find()` or `find_task()` ranking. Graph adjacency, change impact, and scoped authority retain their existing explicit provenance surfaces rather than being fused into a new score.


## 0.10.28 — task-query latency closure

`CodeMap.find_task()` now keeps a small in-process cache keyed by CodeMap generation, task text, and limit. Additive surfaces that compose canonical task retrieval reuse the exact selected result instead of replaying the same bounded query lanes. The cache is never persistent authority: any generation change forces normal recomputation, and first-query ranking semantics are unchanged.


## 0.10.29 — benchmark protocol authority closure

Retained agent-suite metrics now bind comparability to a canonical `benchmark_protocol_identity`: exact retrieval API, budget/limit, ordered repositories, each candidate-visible workspace fingerprint, each corpus SHA-256, and task count. Reports may be compared as the same protocol only when this identity matches.


## 0.10.30 — native paired A/B benchmark

`scripts/compare_agent_suites.py` compares two protocol-identical retained agent-suite reports task-by-task. It refuses mismatched benchmark protocol identities or task sets, binds both input report bytes by SHA-256, reports per-task and aggregate deltas, and can gate zero recall losses / zero fallback regressions. Candidate implementation and benchmark repository inputs are intentionally separate identities.


## 0.10.31 — adaptive evidence budget

`CodeMap.task_context_plan()` derives a bounded task-specific evidence budget/disclosure plan from the canonical query route and candidate-visible governance/evidence cues. `task_context()` executes that plan, while existing `context()` defaults and explicit caller budgets remain unchanged.


## 0.10.32 — cross-layer relationship intelligence

`CodeMap.task_relationships()` composes existing mechanically grounded evidence into
a bounded worker-facing relationship map. Canonical task hits remain primary.
Trusted one-hop code-graph adjacency, proven reverse change-impact surfaces, and
mechanically scoped AGENTS authority are emitted as separate typed relationship
layers with provenance. Missing impact roots are reported explicitly rather than
replaced by fuzzy graph guesses. This surface is advisory and has no ranking effect.


## 0.10.33 — retrieval stability testing

`CodeMap.retrieval_stability()` replays canonical `find_task()` within one CodeMap generation while bypassing only the generation-bound task-result cache. It fingerprints the complete ranked path/kind/score projection, reports the first divergent rank when instability exists, restores pre-existing cache state, and has no ranking effect. Stability is measured; retrieval is never modified to satisfy the gate.


## v0.10.34 fresh multi-repo corpus

Hashmarks carries a deterministic fresh benchmark family (`hashmarks-v0.10.34-fresh-corpus-a`) that materializes three disjoint repositories and 18 independently defined localization tasks across Python service, TypeScript UI, and release/contract automation shapes. Fixture identity is computed only from declared source bytes and corpus bytes; generated `.hashmarks`, VCS, virtualenv, and dependency state cannot affect corpus identity. The existing agent-suite protocol separately binds retrieval parameters, workspace fingerprints, corpus hashes, and task counts. The fresh benchmark is additive QA evidence and does not alter retrieval or ranking.

## 0.10.35 — answer-blind worker proof

`make metrics-blind-worker-ab` materializes a deterministic challenge from the fresh
multi-repository corpus, injects plausible documentation decoys, and launches two
separate subprocess workers per repository. Worker inputs contain only task IDs and
queries; expected files and symbols stay in a hidden grader corpus until both worker
outputs are frozen. The portable lexical/grep worker provides a no-CodeMap baseline;
the Hashmarks worker uses canonical `CodeMap.find_task()`. The retained artifact
reports top-1/top-5/top-20 localization side-by-side and preserves every individual
failure for inspection instead of collapsing the result into a single success score.

### Worker entry-point projection

`CodeMap.task_entry_points(task)` is an additive worker-facing projection over the
canonical `find_task()` result. It groups already-selected hits into mechanically
typed roles (`authority`, `contract`, `config_build`, `verification`,
`implementation`, `orientation`) and emits bounded recommendations while retaining
each path's canonical rank. It performs no new discovery and has no ranking effect.
The blind worker benchmark measures this projection separately from canonical
retrieval so improvements cannot be mistaken for a changed search ranking.

## 0.10.36 — ambiguity-visible worker evidence

`CodeMap.task_entry_points()` now reports an explicit `ambiguity` block when the
same task text contains multiple repository-role cues that are all supported by
already-retrieved canonical evidence. The projection does not choose a new winner
or change `find_task()` ranking; it exposes the competing bounded role entry points
so a worker can inspect both instead of treating one top-1 guess as certain. This
phase is driven by the retained v0.10.35 blind-worker misses (`AGENTS` + tests and
Vite test-environment configuration), not by a goal of forcing the fixture to 100%.

The blind-worker gate also spawns a separate ambiguity-reviewer subprocess. The reviewer
receives only the public task text and repository bytes; it never sees worker-A output or
hidden expected files/symbols. Grading happens after both processes exit, so the report can
measure whether reviewer warnings predict real worker misses without leaking the answers.

### v0.10.37 — uncertainty changes worker behavior

`make metrics-worker-behavior-ab` runs two answer-blind subprocess policies over the retained fresh multi-repo challenge. The direct worker edits its first `task_entry_points()` recommendation. The uncertainty-gated worker performs the same retrieval but, when Hashmarks reports competing explicit roles, it defers the edit and emits `inspect-competing-evidence` with the public alternatives. Hidden expected files/symbols remain grader-only until both worker outputs are frozen. The benchmark reports correct immediate edits, unsafe wrong first edits, and inspection cost separately; abstention is never counted as a correct edit. Canonical `find_task()` ranking and discovery are unchanged.


### v0.10.38 — inspection effectiveness
Ambiguity remains advisory and canonical retrieval is unchanged. The answer-blind worker inspection benchmark compares defer-only behavior with inspect-then-resolve behavior. Resolution may use only public task text and worker-visible competing evidence; hidden expected files/symbols remain grader-only. Same-path role ambiguity collapses safely, explicit public surface/role cues may resolve a competing candidate, and unresolved/tied evidence remains deferred.

### Multi-step worker decision proof (v0.10.39)
`make metrics-worker-multistep-ab` runs answer-blind subprocess workers through orientation, ambiguity inspection, edit-target selection, and verification-target selection. Hidden grading expectations are opened only after worker outputs are frozen. The benchmark reports unsafe edits, recovery from a wrong first hypothesis, verification-target correctness, and actual selected evidence bytes with a deterministic bytes/4 token approximation. It does not change canonical `find_task()` ranking.

### Failed-verification recovery proof (v0.10.40)

`make metrics-worker-failed-verification-ab` measures recovery after a controlled,
plausible wrong edit receives a failed verification signal. The grader alone may
use hidden expected files to select the first canonical top-N path that is known
wrong. Workers receive only task text, the failed edit path, the verification
surface, and a generic `failed` outcome. The benchmark compares repeating the
failed edit, fresh canonical re-search, and evidence-guided recovery that excludes
only the path carrying direct negative verification evidence. Canonical
`find_task()` ranking is not changed by this phase.


### v0.10.41 — native agent-economics baseline
The agent-economics harness freezes public task inputs and reports cold setup separately from warm per-task archaeology. The native baseline measures repository scan files/bytes, selected evidence files/bytes, deterministic bytes/4 token proxy, first-edit correctness, verification correctness, and candidate-search effort. It is benchmark evidence only and does not alter canonical retrieval.


### v0.10.42 — paired current-Hashmarks economics
Runs the exact v0.10.41 agent-economics protocol in paired mode: native archaeology and current Hashmarks receive the same public tasks and repositories. Cold Hashmarks sync is reported independently from warm task cost. The phase changes no retrieval algorithm; it exists to establish whether current Hashmarks already reduces agent archaeology enough to justify further retrieval work.


### v0.10.43 — fielded BM25 negative-result gate
An experimental file-level fielded BM25 lane tests code-aware tokens with weights symbol 5, signature 4, path 3, imports 2, body 1. It is benchmark-only and has no canonical ranking authority. On the retained 18-task economics challenge, current Hashmarks scores 16/18 correct first edits while BM25 and the naive BM25 override fusion score 12/18. Promotion is therefore explicitly rejected; canonical retrieval remains unchanged.


### v0.10.44 — structure-constrained BM25 admission gate
BM25 is restricted to paths already admitted by current Hashmarks task-entry evidence. It still falls from 16/18 current-Hashmarks first-edit correctness to 12/18. The existing public-task ambiguity resolver reaches 18/18 without BM25. BM25 incremental gain is -4, so promotion remains rejected.


### v0.10.45 — retrieval residual admission gate
The fresh answer-blind corpus has 16/18 correct first edits but 18/18 expected evidence in top-5 and top-20. The only residual class is two role/authority ambiguities. There are zero discovery/deep-ranking misses, so n-gram and embedding indexes are not admitted. A selective ambiguity scout is admitted because it targets the observed residual directly.


### v0.10.46 — selective ambiguity scout economics
A separate answer-blind scout subprocess is invoked only for task-entry ambiguity. On 18 tasks, no-scout correctness is 16/18; selective scout reaches 18/18 with 3/18 scout tasks (two real corrections plus one benign false-positive ambiguity), while always-scout would invoke 18/18. The scout receives only public task text, first path, ambiguity flag and competing evidence; hidden expected files/symbols remain grader-only. This is a deterministic proxy for Codex subagent economics, not an LLM quality claim.

### v0.10.47 — real Codex Agent Economics harness

Hashmarks now ships a headless Codex A/B/C runner for the actual economics experiment. It launches a fresh independent `codex exec` process for each `(repository, task, lane)` pair so workers do not inherit a parent conversation. The paired lanes are `native`, `hashmarks`, and `selective`; all receive identical public task text, model/reasoning settings, sandbox mode, and structured output schema. Hidden expected edit/verification answers remain grader-only until every final result is frozen.

Run `make codex-agent-economics-preflight` first. A full run requires an authenticated Codex CLI on the host. `codex exec --json` events, stderr, prompt, final structured message, command line, wall time, and any visible token counters are retained per worker. Hashmarks never fabricates missing Codex token counters: zero means unavailable in the event stream.

The harness deliberately uses independent `codex exec` workers instead of root-thread `spawn_agent` so task delivery, model settings, and per-worker traces remain externally auditable. v0.10.48 extends this with a real ambiguity-only scout worker.

### v0.10.48 — real ambiguity-only Codex scout orchestration

The real Codex economics harness can now pay for a second model only when `task_entry_points().ambiguity.ambiguous` is true. The scout runs as a separate clean `codex exec` process, sees only the public task plus worker-visible competing candidate paths, is restricted to selecting one of those candidates, and freezes its structured recommendation before the main worker runs. Main-worker and scout token/time counters are summed, so the extra model can never be hidden from the economics result.

This deliberately avoids recursive Codex subagent spawning: the harness owns both independent processes and can audit their exact prompts, model/reasoning settings, traces, and costs. A non-candidate scout output is rejected fail-closed.

### v0.10.49 — Codex model-tier economics matrix and rollout usage recovery

The real-agent lab can now compare arbitrary `NAME:MODEL:EFFORT:STRATEGY` variants across `native`, `hashmarks`, and `selective-real`. The matrix reports verified solutions (correct edit target **and** verification target), verified rate, visible total tokens, tokens per verified solution, wall time per verified solution, and Pareto dominance when token telemetry exists. No dollar price is invented; subscription/API economics can be layered on later from real pricing data.

`codex_rollout_usage.py` recovers the Codex thread id from each headless JSONL stream and can locate the matching `~/.codex/sessions` rollout to recover token counters when `codex exec --json` omits them. This is important because the matrix must not declare one lane cheaper merely because its token fields were absent from stdout.

A recommended external matrix is:

```text
cheap/native
cheap/hashmarks
cheap/selective-real
strong/native
```

Use `--plan-only` first to verify the requested model names and run size without spending agent turns. Actual execution remains fail-closed on Codex preflight.

### v0.10.50 — sanitized swarm / exact-symbol anchoring
Real-repository swarm testing exposed two issues hidden by the earlier retained corpus: SECRET benchmark answers were mounted inside the worker repository, and natural-language task terms could drown an exact class/function token. v0.10.50 adds bounded exact-symbol anchoring to canonical `find_task()` and requires sanitized worker workspaces for agent-economics evidence. Hashmarks should be shared as a warm daemon/MCP service across agents rather than initialized independently per child.

#### Swarm evidence
`process_swarm_real_repo_v2.py` runs isolated answer-blind process workers against a sanitized real repository and freezes one JSON trace per worker before grading. v0.10.50's authoritative Hashmarks self-corpus run uses 19 tasks x 4 strategies = 76 workers. It is a process-worker benchmark, not an LLM-agent claim; its artifacts are intended to be replayed by the real Codex harness from v0.10.47-v0.10.49.

## Agent action routing and sanitized swarm proof (v0.10.51)

`CodeMap.task_action_map()` is an additive worker projection over canonical `find_task()` evidence. It assigns already-retrieved paths to `edit`, `verify`, `contract`, `inspect`, and `related` roles while preserving canonical rank and provenance. Test files are verification surfaces even when they are also source files; benchmark/external corpus files are inspection-only; config/build surfaces become edit candidates only for strong direct configuration cues.

The bundled `scripts/agent_evaluation/sanitized_agent_swarm.py` enforces PUBLIC/EVIDENCE/SECRET separation, refuses an in-repository `benchmarks/agent_tasks.json` answer key, freezes worker traces before opening SECRET, and shares one warm CodeMap across the swarm. On the sanitized 19-task retained real-repo corpus the action map selects 19/19 expected edit targets, finds verification surfaces for 19/19, has expected evidence in top-5 for 19/19, and carries the full expected set in top-20 for 18/19.

## Shared warm CodeMap service (v0.10.52)

`hashmarks.codemap.service` exposes one long-lived CodeMap over a local Unix socket. Stateless workers use `CodeMapServiceClient` for `find_task()` and `task_action_map()` instead of creating independent indexes. One server thread owns CodeMap/SQLite state; concurrent clients queue at the socket boundary. The retained 19-task sanitized swarm stress proof used eight concurrent clients, performed exactly one sync, selected 19/19 expected edit targets, found 19/19 verification targets, and completed the batch in under one second on the qualification host.

> **Current boundary correction:** v0.10.53/v0.10.54/v0.10.65/v0.10.83 below are historical release descriptions, not feature-admission guidance. Failed-edit memory, recovery policy, scout/delegation policy, and agent work-session state are now classified as legacy boundary debt by `docs/reference/PRODUCT_BOUNDARY.md`. Do not expand these surfaces or cite them as precedent for new Hashmarks features.

## Accumulated negative evidence (v0.10.53) — historical boundary debt

`task_action_map(..., failed_edit_targets=[...])` carries worker-local failed hypotheses without changing canonical retrieval. Failed targets stay visible with the `disproven` role but cannot be selected again as edit targets. The scope is exact-path-only and the worker must resend its accumulated failures; the shared CodeMap service does not turn one agent's failed hypothesis into global repository truth. On the sanitized 19-task corpus, one- and two-failure replays repeated a disproven target 0 times, preserved canonical evidence 19/19, produced a replacement after the first failure 19/19, and still produced a third candidate for 18/19 tasks after two distinct failures.

## Decision packet and scout admission (v0.10.54) — historical boundary debt

`task_decision_packet()` compresses worker-visible action evidence into edit/verify/contract plus a scout gate. A scout is admitted only for no safe edit, missing verification, unresolved first-pass action ambiguity, or a failed-hypothesis recovery whose next edit candidate has fallen below canonical rank 5. On the sanitized 19-task corpus the baseline admits 0 scouts while retaining 19/19 correct edits. After deliberately invalidating every first edit, only 5/19 recoveries admit a scout; 14/19 remain single-agent because their replacement candidate is still shallow and typed.

## Agent work traces and scoring (v0.10.55)

`scripts/agent_evaluation/score_agent_work.py` grades the execution loop rather than retrieval recall alone. It records first/final edit correctness, wrong edit attempts, repeated disproven targets, duplicate reads, scout calls, verification outcomes, evidence/model tokens, wall time, and cost per verified solution when exact usage is available. Verification selected is not verification passed: the sanitized 19-task process-worker baseline scores 80/100 with 19/19 correct edit decisions but 0 verified solutions because its verification events are explicitly `not-run`.

## Mechanical verification planning (v0.10.57)

`verification_plan()` converts a known verification surface into bounded argv when Hashmarks can identify the runner mechanically. Python/pytest plans use exact test node IDs when symbol metadata is available; unsupported runners fail closed instead of guessing shell commands. On the sanitized 19-task corpus, 19/19 plans were available, all 19 were node-scoped pytest commands, and all 19 generated commands executed successfully with zero timeouts on the clean qualification tree. This validates the command plan itself, not a hypothetical patch.

## Role-preserving worker context budget (v0.10.61)

`task_decision_packet(..., token_budget=N)` now carries a deterministic `work_context` whose mandatory skeleton is allocated before discretionary evidence. Edit and verification anchors, plus a contract anchor when one exists, cannot be displaced by related/inspection material merely because the total budget grows. Pathologically small budgets fail closed with `safe=false` and explicit `missing_roles`; they never pretend that an incomplete worker packet is sufficient.

The allocator preserves canonical action-map order and does not introduce a new retrieval ranker. Its permanent monotonicity contract is: for budgets `B1 < B2`, mandatory items admitted at `B1` remain admitted at `B2`. The regression sweep covers 128, 192, 256, 384, 512, 640, 768, 1024, 1280, 1536, and 1800 tokens.

## Evidence density and minimum sufficient context (v0.10.62)

Worker context now reports supplied bytes, useful role bytes, duplicate evidence bytes, useful-byte ratio, and tokens per safe packet. `work_context_budget_sweep()` evaluates a deterministic ascending budget set and reports the smallest safe budget while simultaneously checking the mandatory-role monotonicity invariant. This is measurement only: it does not change `find_task()` ranking or add a retrieval subsystem, and callers can keep a conservative production default until a sanitized real-repository corpus proves a smaller default is safe.

## Worker packet generation and freshness identity (v0.10.63)

Every decision packet now carries a content-addressed identity block binding repository namespace, CodeMap generation, optional identity-daemon generation/freshness state, task identity, context digest, verification-plan digest, negative-evidence digest, and a derived decision generation. A packet from an earlier repository or decision state is therefore distinguishable instead of being silently reusable. Git repositories use the HEAD tree identity as the repository namespace; non-Git workspaces use a stable canonical-path namespace while CodeMap generation remains the change boundary. This adds identity and invalidation evidence only; it does not force a full map rebuild.

## Post-edit incremental refresh (v0.10.64)

`refresh_after_change(task, changed_paths, ...)` is the external-harness handoff after an edit. The harness still owns source modification; Hashmarks receives only repository-relative changed paths, runs the existing incremental `sync(paths=...)` path, and returns a newly generation-bound decision packet plus refresh economics. This makes post-edit work proportional to the reported change set instead of rebuilding the repository map, while preserving the hard boundary that Hashmarks does not perform the edit itself.

## Failed-verification recovery evidence (v0.10.65) — historical boundary debt

`AgentWorkSession.summary()` now reports recovery attempts, verification count, failed verifications, cumulative decision-context tokens, success after failure, and repeated disproven targets. The session still does not perform an implementation retry itself: the external worker asks for the next packet after a failed verification. Hashmarks' run-local negative evidence guarantees the exact disproven edit path is excluded from the next action proposal while canonical repository ranking remains unchanged.

### Harness-neutral economics boundary (v0.10.71)

Real-agent economics are computed from normalized harness traces, not runner-specific result shapes. The worker-visible trace is frozen first; SECRET grading joins only by task identity afterward. Missing model-token or wall-time evidence remains unavailable rather than being estimated. The primary comparison remains verified-solution rate and cost per verified solution. Hashmarks does not launch the model or own the solution loop.

### Portable real-agent experiment import (v0.10.72)

Experiment lanes declare harness, model, strategy and reasoning effort as public metadata. Externally executed native JSONL is imported through a thin harness adapter into the common agent-event trace schema; the native-event hash and normalized trace identity make the import reproducible. Unsupported harnesses fail closed. SECRET contents are never embedded in the experiment manifest; grading remains a later authority-side join.

### Fail-closed experiment coverage (v0.10.73)

A real-agent economics matrix is only complete when every declared lane has exactly one imported run for every declared task. Missing lane/task pairs, duplicate runs, unexpected lanes/tasks, and unsupported bundle schemas keep the coverage ledger non-terminal. Downstream economics certification must call `require_complete_coverage` before claiming a completed comparison.

### Authority-side experiment report (v0.10.74)

A completed economics report is assembled only after exact lane/task coverage passes and the SECRET grader presents exactly the declared task set. Imported traces are then joined to boolean verified-solution outcomes and summarized with the same harness-neutral token/time metrics and Pareto comparison. The emitted report exposes outcomes, not expected-file or expected-symbol answer keys.

### Tamper-evident experiment certificate (v0.10.75)

A completed real-agent experiment can now be sealed into a deterministic certificate binding the public manifest identity, every normalized trace identity, every native-event SHA-256, the coverage ledger identity, the SECRET authority identity, and the final report identity. The certificate contains only identities and outcomes metadata—not SECRET answers. Recomputing the certificate detects changes to any bound input.


### Shared-path mandatory role coverage (v0.10.76)

Worker context budgeting now treats one repository path as capable of satisfying multiple mandatory evidence roles. When the same path is both the edit authority and a contract surface, the packet retains one deduplicated anchor with explicit `covered_roles` instead of falsely reporting the secondary role as missing. This preserves evidence density while preventing false `safe=false` results.

### Typed recovery evidence (v0.10.83) — historical boundary debt

A failed verification no longer automatically means that the selected edit target was wrong. Hashmarks now separates a **failed attempt/hypothesis** from an explicitly **disproven edit target**. `task_recovery_brief()` keeps the first-stage packet compact and expands only typed negative evidence plus the next edit/verification action. The full decision packet remains available for diagnostics but is not dumped into the agent context by default.

This matters for coding agents because a correct file can still receive an incorrect patch. Retiring that file after any failed test causes the harness to steer the agent away from the actual owner. Callers should mark `target_disproven=True` only when repository or execution evidence proves that the target itself is wrong.

### Typed ownership relation graph (v0.10.84)

Hashmarks can now project the already-indexed import/call facts as a bounded,
cycle-safe ownership relation graph. The graph is task-directed evidence, not a
second repository authority: imports and calls nominate candidates, while active
reachability plus verification origin, task locality, or call evidence is needed
before a candidate is selected as the edit owner.

`CodeMap.ownership_relation_graph(task, start_path, max_depth=2)` returns typed
nodes/edges, candidate corroboration, cycle evidence, the selected candidate when
corroborated, and the exact `owner_path` used by the projection. Exact import
module resolution constrains short call-symbol matches so unreachable duplicate
symbols do not enter the active path. Traversal is bounded and cuts already-visited
nodes rather than recursively following cycles.

The Stage-1 `task_decision_brief()` now includes the compact owner path when
structural ownership was resolved, for example test -> route -> implementation.
The external agent still owns reasoning, edits, shell execution, and verification;
Hashmarks only supplies repository evidence and the bounded action projection.

### v0.11.13 cold-start safety / repository-understanding economics candidate

Real-world Oh-Goon indexing exposed a cold-start scaling failure before task evaluation. The candidate now exposes a read-only index preflight (measured files/bytes/language/surface mix), durable `BUILDING`/`COMPLETE` CodeMap identity, and a post-sync economics certificate with cache state, elapsed/throughput evidence, lexical rows, workspace-map amplification, bounded persistence writes, and per-surface lexical cost. Worker decision packets carry the selected edit/verification evidence surfaces and fail closed when the persisted CodeMap generation is incomplete.

The instrumentation is intentionally not an observability platform. Hashmarks emits repository-intelligence facts; it does not retain longitudinal telemetry, render dashboards/heatmaps, choose deadlines, retry work, resume execution, schedule processes, or certify runs. Low-value lexical surfaces are measured before any exclusion/demotion decision.

### v0.11.13 real-world evidence-value / lexical-surface calibration candidate

`benchmarks/codemap_surface_calibration.py` compares a frozen real-repository task corpus against benchmark-only copies of a completed CodeMap. Current experiment lanes are full line-level lexical evidence, expensive-surface file-membership projection (one representative line per path/token), and an expensive-surface cap of four positions per path/token. The tool reports exact edit/verification outcomes, expected scout/discrimination controls, false-safe outcomes, selected evidence-surface contribution, decision latency, lexical rows, and map bytes. It never changes the production index and carries no timeout/retry/execution policy.

On the retained 48-task Oh-Goon real-world corpus, the full map selected 42 exact edit owners; five misses were already fail-closed/ambiguous and one deliberately underspecified `observer` task exposed a baseline false-safe that should require discrimination. Both experimental expensive-surface variants preserved the same decision outcomes. File-membership projection reduced lexical rows from 1,439,966 to 1,035,883 (-28.1%); cap-4 reduced them to 1,128,088 (-21.7%). These results justify further measurement but do **not** authorize a production representation change while the baseline ambiguity residual and broader cross-repository evidence remain open.

Real repository churn on the same completed Oh-Goon map remained bounded and correct in this environment: warm full recheck ~1.33 s with zero writes, one-file change ~0.32 s, twenty-file change ~0.62 s, rename/delete membership updated correctly, an injected incomplete generation failed closed, and an ordinary full sync restored `COMPLETE` in ~0.92 s. A second real shape—the Hashmarks repository itself at 250 indexable files / ~2.33 MB—measured ~6.48 s cold and ~0.17 s warm. These are repository-intelligence measurements, not execution deadlines.

### Bounded decision calibration and weak-anchor safety

Hashmarks calibration can evaluate large frozen task corpora as identity-bound groups instead of one monolithic command. Decision consumers use the typed `hashmarks.task-decision-packet.v2` contract, and generic contract/behavior requests that lack a task-specific repository anchor fail closed rather than manufacturing a unique edit owner. Pure repository-path classification is memoized in-process to remove repeated decision-work cost; this is an implementation optimization only and does not add execution timeout/retry/resume authority to Hashmarks.

### v0.11.13 decision hot-loop / evidence-read amplification candidate

The current candidate continues the real Oh-Goon 48-task calibration work by measuring physical CodeMap reads rather than accepting wall-clock noise as the only performance signal. Generation-bound decision sessions now reuse stable file rows, exact symbols, reverse references, graph edges, and module identities; known import-source paths are bulk-preloaded before qualified verification resolution, and exact Python module fallback identities are resolved with one bounded multi-module read instead of one SQL query per imported symbol. Ordinary per-test dynamic module re-execution is structurally guarded so process-local production caches are not defeated by test helpers.

On the retained full-evidence Oh-Goon corpus the clean six-group result remains 42/47 exact edit owners, 2/3 graded verification selections, 0 false-safe decisions, and 18 scouts, while clean decision time is ~26.38 s. Across all 48 tasks only 28 direct `file_row` reads remain and Python module resolution uses 41 bulk module reads with zero individual `module_paths` reads. The benchmark-only membership and cap-4 lexical variants again preserve the exact same correctness result (~20.45 s and ~20.11 s in this run); production lexical representation remains unchanged pending broader independent-repository promotion evidence.

A proposed multi-view lexical SQL CTE was measured and rejected: on the real CodeMap it reduced query count but increased work relative to separate indexed reads. Retaining this negative result is intentional so future optimization follows measured total cost rather than a "fewer queries is always faster" assumption.

Persistent-candidate validation is now intentionally cheaper than canonical promotion. Source-only candidates run bounded source test rings, source compileall, one deterministic source ZIP, and focused tests from an independent extraction. Independent archive rebuild byte-identity and the broader artifact/install matrix are reserved for canonical promotion or any phase that changes the packaging transform itself.


## v0.11.19 verification ownership authority-link closure

`hashmarks.verification-ownership.v2` binds a nominated verification surface to the selected edit authority only when bounded structural reverse-reference evidence proves the relationship. Direct references and bounded indirect references may create a verification link; task wording, namespace overlap, or lexical nomination alone may not. The graph reuses the existing authority/ownership view and remains repository evidence only. Hashmarks does not execute tests, certify results, schedule work, or acquire runtime authority.

### Strict Ruff complexity debt

Hashmarks pins a strict Python complexity/size policy (`C901`, `PLR0911`-`PLR0916`) in `pyproject.toml`. `make lint` is the uncompromised zero-debt end-state. Existing historical debt is tracked in `ruff-debt-baseline.json`; `make lint-debt-gate` fails if any file increases its debt or if a new file introduces debt. `make dev-check` uses that non-regression gate while the historical debt is burned down. Do not close debt with `noqa`, per-file ignores, relaxed thresholds, or by moving complexity to another file. Refactors must preserve behavior and monotonically reduce the ledger until `make lint` is green, at which point the baseline can be deleted and `dev-check` can switch to strict Ruff directly.

## v0.11.21 DEVELOPMENT AW — evidence-context identity closure

The compact agent-start projection now carries `provenance.context_identity`, a domain-separated identity over the existing decision-authority receipt plus repository identity, CodeMap generation, selected source revision, explicit freshness state, and native Hashmarks producer implementation identity. It is budget-independent and changes when repository/revision/freshness authority changes. This composes existing Hashmarks repository evidence only; it does not create execution, scheduling, retry, or certification authority.

## v0.11.21 DEVELOPMENT AX — native evidence-context conformance

Evidence-context canonicalization is now a native Hashmarks contract in `hashmarks.evidence_context`. `evidence_context_identity()` creates the producer-owned opaque identity and `validate_evidence_context()` verifies it. Consumers therefore do not need to copy Hashmarks hashing/canonicalization rules. Tampered authority, revision, freshness, or producer identity fails closed. This follows the same producer-creates/consumer-validates boundary used by verification-selection identity.

### Development HM-16 — producer-identity hot-path economics
The no-argument native producer implementation identity is now memoized for the lifetime of the imported installation. This removes repeated full-package hashing from evidence-context packet construction while preserving explicit package-root recomputation for artifact/conformance drift checks. Identity semantics and all repository evidence are unchanged; this is a measured repository-intelligence hot-path optimization only.


## Performance qualification filesystem

`make test-profile` warns under WSL `/mnt/<drive>`. Correctness remains valid there, but comparable performance/economics baselines must use a native Linux filesystem path such as `/home/...`.
