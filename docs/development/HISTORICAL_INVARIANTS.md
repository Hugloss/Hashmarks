# Historical Hashmarks invariant ledger

**Status: non-normative development history.** This file preserves the pre-public invariant ledger, including historical execution-cache, agent-evaluation, Codex/scout, recovery, and benchmark contracts. It exists for engineering archaeology only. It must not be used to admit product features or override the current product profile.

Current authority lives in:

- [`../reference/PRODUCT_BOUNDARY.md`](../reference/PRODUCT_BOUNDARY.md)
- [`../reference/INVARIANTS.md`](../reference/INVARIANTS.md)
- [`../reference/ARCHITECTURE.md`](../reference/ARCHITECTURE.md)

---

# Hashmarks invariants

**Status: normative.** These invariants define current Hashmarks correctness and authority guarantees. Version-tagged sections retained below record when an invariant family was introduced; they do not override the current product profile in [`PRODUCT_BOUNDARY.md`](../reference/PRODUCT_BOUNDARY.md). Historical development context belongs under `docs/development/`.

## Canonical identity

**I1. Bytes, not metadata, define file identity.** `mtime`, `ctime`, inode and watcher events are accelerators only.

**I2. Directory and declared-input identity are compositional Merkle identities.** A changed leaf changes only its affected ancestors.

**I3. Strong verification and fast observation produce the same canonical identity.** `verify=True` changes proof strength, never digest semantics.

**I4. Identity domains are versioned.** File, directory, manifest, input-root, step and snapshot schemas must not be silently reinterpreted.

## Path authority

**P1. Host/control paths are canonicalized once.** Workspace/state/CAS/database/runtime roots are realpath-canonical and CWD-stable.

**P2. Workspace identity paths are lexical, relative and cannot contain parent escapes.** Final symlink leaves are not resolved into targets.

**P3. Internal Hashmarks state can never participate in source identity.** Mandatory exclusions and traversal ignores are separate concepts.

**P4. Unix runtime sockets never depend on mounted workspace filesystem support.** Runtime IPC is placed on a local runtime filesystem with bounded AF_UNIX path length.

## Observation safety

**O1. Watchers are observation accelerators, never identity authorities.**

**O2. A new/lost/overflowed observer is `UNKNOWN`.** Hot identity cannot be trusted until reconciliation succeeds.

**O3. Reconciliation is generation-bound.** Filesystem changes that arrive during reconciliation prevent a stale transition to `CLEAN`.

**O4. Stable file reads are `stat -> hash -> stat`.** Moving bytes are retried and never cached under stale metadata.

**O5. Native Linux daemon/local watcher reads establish a request-time barrier.** Already-queued inotify events are drained into `ChangeTracker` before hot state is trusted.

**O6. A watcher backend without a request-time barrier must degrade to `UNKNOWN` reconciliation.** It may not silently return hot cached identity.

## Public API safety

**A1. `Identity(mode="auto")` may change acceleration mode, never identity semantics.** Daemon failure safely falls back to local reconciliation.

**A2. `Identity(mode="daemon")` fails when the daemon is unavailable or semantically incompatible.** Explicit requirements are never silently weakened.

**A5. Daemon compatibility is semantic, not just transport-level.** A client requires the expected protocol, semantics identifier and mandatory safety capabilities before it may trust daemon-maintained hot state. An older daemon cannot inherit newer watcher-safety guarantees by sharing a protocol number.

**A3. Long-lived local observation is explicit.** Default `local_observer="reconcile"` cannot return stale hot state. `watcher` requires a barrier. `manual` is expert opt-in and the caller owns `record_changes()`.

**A4. Typed input specs mean what they say.** `File` rejects real directories; `Directory` rejects files/symlink leaves; `Glob` requires glob syntax.

## Huge manifests

**M1. Explicit manifests are fingerprinted once and maintained as an incremental synthetic Merkle trie.**

**M2. Huge daemon manifests are registered once and referenced by a small fingerprint handle.** Hot requests never resend the entire path list.

**M3. Registered manifests are daemon-ephemeral accelerators.** Losing a daemon loses the handle, not canonical identity; clients re-register from the canonical `InputManifest`.

**M4. Registered-manifest memory is bounded and reference-owned.** Clients release handles on clean close, identical handles are ref-counted, total retained paths/handles are capped, and request chunks are byte-bounded as well as count-bounded.

## Cache/storage

**C1. Action-cache results are valid only while referenced CAS blobs exist and verify when requested.** Dangling/corrupt results become misses.

**C2. Pluggable storage cannot redefine identity.** CAS/action-cache backend protocols are below the canonical identity boundary.

**C3. Persisted directory nodes are disabled by default until a safe freshness read-side provides measured value.**

## Impact safety

**K1. UNKNOWN means run.** Missing, partial, stale, or untrusted dependency evidence can never justify skipping work.

**K2. Only an unchanged complete WorkIdentity may reuse a previous PASS.** FAIL, ERROR, UNKNOWN, missing baseline, changed work definition, or changed relevant inputs all remain runnable.

**K3. Static adapters are evidence providers, not skip authorities.** Python/Node static import graphs are partial by default: they may prove `AFFECTED`, but unchanged work remains `UNKNOWN` until complete declared/native/observed evidence exists.

**K4. Completeness is a claim, not authority.** Declared work defaults to partial. `complete=true` only makes a work unit eligible for reuse; a separate trusted runner policy must authorize that evidence source.

**K5. Producer names are not trust credentials.** Generic repo-controlled observed JSON is never trust-eligible by default. A native/observed integration must be created through an explicitly trust-eligible channel and separately allowlisted by runner policy before its `complete=true` claim can authorize a skip.

**K6. Complete evidence cannot be empty.** A complete dependency claim with zero inputs is rejected rather than interpreted as "nothing can affect this work."

**K7. Impact storage is workspace-scoped and below identity authority.** Sharing a physical state directory cannot make results from workspace A reusable in workspace B.

**K8. Adapters do not redefine canonical identity.** They supply relevant input sets and dependency evidence; Hashmarks still computes canonical WorkIdentity from the resolved bytes and work definition.

**K9. Adapter discovery must prune known dependency/cache trees before traversal.** Filtering after recursively walking `.venv` or `node_modules` is not an acceptable hot-path implementation.

**K10. Execution-start errors overwrite reusable state.** Missing commands, invalid working directories and OS launch failures record `ERROR`; an older PASS may not survive a failed attempt as reusable evidence.

**K11. Dependency completeness and execution completeness are separate claims.** Command-bearing work cannot reuse PASS unless both are trusted. Hashmarks automatically fingerprints the resolved executable authority, but external package/runtime completeness is never inferred from executable bytes alone.

**K12. Assessment and execution use the same executable authority.** `impact run` executes the resolved path whose bytes were included in WorkIdentity; it does not re-resolve `PATH` after assessment.

**K13. PASS promotion is post-run identity-bound.** A zero exit code is promoted only after re-evaluating WorkIdentity. If inputs or execution authority changed while the command ran, the result is stale and cannot become reusable evidence.

**K14. Artifact work proves outputs as well as inputs.** `reuse=artifact` requires declared outputs, records their identity with PASS, and reruns when outputs are missing or changed. `reuse=never` can never skip side-effect work.

**K15. Evidence schemas are type-strict at trust boundaries.** A JSON string such as `"false"` is not a boolean completeness claim and must be rejected, never truth-coerced.

**K16. Duplicate adapters merge evidence conservatively.** Evidence is accumulated rather than silently discarded; disagreements about command, working directory, environment, toolchain or reuse semantics remove skip authority instead of guessing.

**K17. Evidence authority is not command-execution authority.** Auto-discovered repo-controlled config/observed documents may contribute dependency evidence without gaining permission to choose a process command. Standalone execution requires an eligible adapter command or explicit caller opt-in.


## Bootstrap / metrics ownership

**B1. Make is a convenience router, not a dependency authority.** `make bootstrap` delegates to locked uv and must not create a second dependency-resolution model.

**B2. Core bootstrap is registry-free.** A checkout with uv and the retained lock can install/run Hashmarks core and daemon offline. Test-only tooling may still be supplied explicitly with `uv --with`.

**B3. Metrics are observations, never identity inputs.** Baselines are written under mandatory-excluded `.hashmarks` state and cannot change canonical source identity.

**B4. Heavy scale is explicit.** The normal metrics target must stay quick enough for routine development; 100k/500k profiles require named targets or explicit file counts.

## Native impact evidence

**N1. Prefer native discovery without transferring identity authority.** Pytest/Vitest may define the test set they know how to collect, while Hashmarks still owns WorkIdentity and safe reuse decisions.

**N2. Native does not imply complete.** Collection/listing/static graph/coverage contexts remain partial unless the evidence source explicitly proves and declares complete dependency coverage.

**N3. Coverage contexts are observed code evidence, not hermeticity proof.** They may prove a code dependency was exercised; they do not by themselves prove absence of data-file, subprocess, service, plugin or environment dependencies.

**R1. Branding never rewrites canonical identity bytes.** The public project/package is Hashmarks, but pre-rename `fastidentity.*` cryptographic domain and protocol/schema identifiers remain frozen compatibility identifiers. `.hashmarks` is the canonical state directory and both `.hashmarks` and legacy `.fastidentity` are mandatory identity exclusions.


## CodeMap / agent-context safety

**G1. Identity is authoritative; CodeMap is derived.** Identity/daemon modules must not import CodeMap. Parsing, indexing, ranking and context construction may never participate in canonical identity or hot identity latency.

**G2. CodeMap generations are separate from Identity generations.** A map may lag source identity. When continuity can be proven, the map records the observation generation it reconciled against; otherwise freshness is explicitly unknown.

**G3. CodeMap full reconciliation is generation-bound when daemon observation is available.** The observer barrier is sampled before and after indexing; a moving/UNKNOWN generation cannot be promoted as fresh map evidence.

**G4. Exact-path reads self-refresh.** `outline`/`source` revalidate the requested file digest before using stored ranges. Changed ranges are never used blindly against newer source.

**G5. Source symlinks are never followed by CodeMap.** A workspace symlink cannot cause agent indexing to read bytes outside the workspace. File-to-symlink transitions remove the old map row.

**G6. Parse artifacts are content-addressed derived data.** Reuse keys include content digest, language, parser/version and CodeMap schema. Any change to parser output semantics requires a parser/version change.

**G7. Shared artifacts may cross Git worktrees; workspace graph state may not.** Worktree reuse is allowed only for path-independent parsed artifacts. Path/module resolution, generations, policy and reverse-dependency state remain workspace scoped.

**G8. Index authority and evidence visibility are separate authorities.** `index=false` forbids derived indexing. `visibility=deny` forbids evidence disclosure. `visibility=outline` may expose structure/relationships but not source bodies or lexical implementation matches.

**G9. Agent context uses progressive disclosure.** Prefer existence/orientation, outline, relationships and exact symbol ranges before whole-file reads. A context builder must honor its explicit token budget.

**G10. Retrieval may abstain.** Insufficient relevance evidence returns an abstention/fallback recommendation rather than guessed source context. Token reduction must never be optimized by knowingly lowering required retrieval recall.

**G11. Exploration traces are internal.** Search/ranking work may be extensive inside CodeMap, but the agent-facing ContextPack contains selected evidence and reasons, not the raw exploration trace.

**G12. Lexical grep rechecks current source before disclosure.** Persistent occurrence indexes narrow candidates only. Returned source lines come from the current workspace and require SOURCE visibility.

**G13. Huge/non-source/generated inputs may participate in Identity without participating in CodeMap.** Identity scope and agent-index admission are intentionally different concerns.

**G14. CodeMap watcher is a separate derived-state process.** Its parsing callbacks cannot execute inside the Identity daemon. Watcher overflow/loss causes CodeMap reconciliation rather than stale-clean state.


**G15. Native CodeMap providers are explicit derived-lane work.** Nx, Pants, TypeScript, Go, Cargo, Maven, Gradle, SCIP and structural-search tooling may run during explicit enrichment/import/query operations, never inside Identity or the identity daemon hot path.

**G16. Native evidence is freshness-bound.** Evidence derived from a source generation or manifest set stops participating automatically when that generation/manifests change. Cached stale rows are not current authority.

**G17. Request-time ranking must remain bounded/local.** A CodeMap query may use maintained/local graph expansion and cheap centrality signals, but must not perform an unbounded whole-repository ranking pass that turns lookup latency into graph-size latency.

**G18. Native project/test evidence remains partial unless separately proven complete.** A native build graph can prove affected work and improve localization; it cannot by itself authorize reuse of a previous PASS. Impact completeness and trust policy remain separate authorities.

**G19. Native selection is positive-only evidence.** pytest-testmon, Vitest/Vite, or any future selector may add reasons to run work; omission from a selector never proves a test or work unit reusable. Reuse remains governed by WorkIdentity, completeness, trust, and result-promotion rules.

**G20. Pyright Type Server is a derived read-only resolver, not execution authority.** TSP requests are explicit CodeMap enrichment, snapshot-bound, version-checked, workspace-confined, and freshness-bound to CodeMap/config state. Server-directed LSP requests receive only minimal read-only client replies; workspace edits are rejected. Pyright evidence cannot enter Identity or skip authority.


**G21. Retrieval release gates are multi-repository.** A ranking/index change may not be accepted solely because it improves Hashmarks-on-Hashmarks retrieval; retained external repository corpora must preserve required file/symbol recall and fallback-search bounds.

**G22. Request-time search cost must be indexed/bounded.** Lexical candidate narrowing and caller expansion must use maintained indexes or bounded local work; repeated whole-table suffix scans or whole-repository ranking are release regressions.

**G23. Token reduction is subordinate to independently graded correctness.** Estimated source/context ratios are advisory. Public model-token claims require matched baseline/Hashmarks experiment identities, exact model-input-token provenance, and separate grader verdicts proving task success and patch correctness. Agent self-attestation cannot authorize a claim.

**G24. Structural parser duplicates are normalized before persistence.** Parser/provider output may contain repeated logical symbols, but workspace CodeMap persistence must deterministically canonicalize them rather than fail or silently vary by insertion order.


**G25. Hashmarks is repository intelligence, not the coding-agent solution loop.** Hashmarks may derive and expose bounded repository evidence, ownership/impact relationships, provenance, freshness, invalidation, and verification relevance/selection evidence. External agents/harnesses retain solution reasoning, planning, edits, arbitrary task-tool execution, verification execution, recovery strategy, orchestration, model/context management, git/worktree lifecycle, and final solution behavior. Agent-facing features that would transfer those authorities into Hashmarks are architecture regressions.

**G26. Verification command scope must not erase verification-surface provenance.** When a mechanically recognized verification command is broader than the selected task-local test/contract surface, consumer-facing evidence must preserve the selected repository-relative verification path separately. Hashmarks may expose that authority but must not execute it on behalf of the consumer.

**G27. Configuration source projection is post-selection, lexical, bounded, and fail-closed.** Hashmarks may expose an exact TOML/JSON/YAML key or section range only from the configuration path already selected by repository authority, and only when task wording mechanically supports one unique structural key/section. This projection must not select another owner, infer a desired value, edit configuration, or execute the solution. Ambiguous, invalid, unsupported, denied, or over-budget ranges remain explicit `next_read` evidence rather than guessed source.

**G28. Task-evidence provenance is derived, revision-bound, and freshness-honest.** Consumer-facing provenance may explain only the already-selected edit authority; it cannot rerank or nominate ownership. The selected source revision is the canonical Hashmarks file-content digest, not filesystem metadata. Freshness is tri-state: `proven` only when a generation-bound continuity authority proves no intervening change, `stale` when a continuity/generation boundary changed, and `unknown` when continuity is unproven. A recent sync timestamp must never be relabeled as proven freshness.

**G29. Post-change evidence delta is incremental invalidation, not autonomous recovery.** The external consumer owns the change and reports changed repository paths plus the exact prior task-evidence packet. Hashmarks may reconcile only those paths, compare revision/generation and existing edit/verification/owner/provenance authorities, and return reusable versus invalidated evidence. Unchanged source bodies and commands must not be replayed merely to restate continuity. Hashmarks must not judge the patch, execute verification, choose recovery strategy, or perform a follow-up edit.

**G30. Changed-code impact remains bounded repository evidence, not a follow-up plan.** After caller-reported edits, Hashmarks may compose the existing reverse/project impact surface with an already-proven task ownership path and selected verification authority to expose affected implementation/contract/test paths. Every row must retain provenance, denied paths must remain undisclosed, and verification relevance may expose runner/scope metadata but must not replay commands merely for impact reporting. Hashmarks must not choose which affected path to edit, decide which tests to run, execute verification, prioritize follow-up work, or infer a recovery strategy.

**G31. Changed-impact relation reconstruction may corroborate but never replace admitted authority.** If task admission directly selects an edit owner and therefore retains no owner path, changed-impact may reconstruct the existing bounded ownership relation graph from the already-selected verification surface. The reconstructed graph is usable only when it terminates at the current admitted edit path; disagreement must be ignored and cannot rerank or replace the edit authority. A unique visible same-package Go source sibling may nominate the graph entry exactly as in existing ownership traversal, but it is not ownership truth.

**G32. Exact import-resolution performance must remain index-local and semantics-preserving.** When a language resolver already has a bounded set of mechanically valid candidate paths, it must use keyed/scoped repository-index lookups rather than materializing the complete file map per candidate edge. Performance optimization must not broaden fuzzy matching, change admitted ownership, weaken visibility policy, omit evidence, or transfer planning/orchestration authority into Hashmarks.

**G33. Declared cross-repository impact is provenance-bearing evidence, never coordination.** Hashmarks may project bounded dependent-project chains only from fresh native/manifest project edges that already exist in the repository graph. When a caller-reported changed path invalidates the declarative `declared-project-links` snapshot, Hashmarks may recollect only that existing declarative provider to bind its topology to current bytes. It must not discover undeclared repositories, schedule downstream work, choose edits/tests, delegate agents, route models, execute verification, or orchestrate repositories.

**PB1. Consumer workflow history is never repository authority.** State whose truth comes from what a consumer attempted, decided, executed, observed at runtime, or plans to do next cannot silently become Hashmarks repository authority. Consumer experience may trigger a new repository query; only repository-derived observation may strengthen repository truth.

**PB2. Equal repository state must not depend on hidden prior consumer workflow.** For equal repository state, query, visibility/policy, and explicit neutral repository-evidence inputs, Hashmarks semantic authority must be invariant to prior consumer workflow. Cache history may change latency and cost, never meaning or authority.

**PB3. Repository evidence may describe choices; consumer policy remains external.** Hashmarks may expose ranked candidates, ambiguity, discriminating evidence, likely repair surfaces, and verification relevance when mechanically grounded in repository evidence. Choosing what action to take, how to sequence actions, whether to delegate, or how to respond to previous outcomes remains consumer policy.

**PB4. Repository relevance and runtime outcome authority are separate.** Hashmarks may derive repository-bound verification relevance, membership, commands/descriptions, and provenance. Execution, runtime outcomes, retries/resume, environment recovery, and certification remain external even when Hashmarks selected or described the work.

**PB5. Historical boundary debt is not feature precedent.** Existing production or experimental surfaces that cross the product profile must be contained or migrated, not used to justify new responsibilities. New capability admission is governed by `docs/reference/PRODUCT_BOUNDARY.md`, regardless of existing names or compatibility surfaces.

**PB6. Hashmarks must never become the agent or the execution motor.** Hashmarks may serve coding agents and execution systems, including Oh-Goon, but service does not transfer ownership. Agent reasoning, memory, edits, delegation, workflow, and recovery remain consumer-owned. Admission, sandboxing, process lifecycle, timeout/retry/resume, runtime environment, result authority, certification, release promotion, and execution-history authority remain execution-layer owned. A proposal that moves either responsibility class into Hashmarks is an architecture regression unless it is split down to a neutral repository-derived evidence primitive.

**PB7. Interoperability transfers evidence, never authority.** Hashmarks may emit repository-bound identities, selections, provenance, relevance, ambiguity, and validation contracts that other systems consume. It must not infer from that interoperability that it should own the consumer's decisions or the execution system's control plane. Product names, benchmark wins, convenience, and existing compatibility surfaces do not override this rule.

## Real-agent evidence authority

- Estimated localization/context tokens are diagnostic only and can never authorize a model-token savings claim.
- A real model-token reduction claim requires complete baseline/Hashmarks pairs with exact model-input token counts.
- Missing pairs, duplicate task/mode traces, unsuccessful tasks, or incorrect patches make the claim ineligible.
- Aggregate token reduction is computed from aggregate paired token counts, never an unweighted mean of per-task percentages.

## Agent measurement authority

- Agent traces describe navigation/tool activity; they do not own correctness or claim-grade token accounting.
- Strict real-agent comparisons require independent `hashmarks.agent-verdict.v1` correctness evidence and independent `hashmarks.agent-model-usage.v1` provider usage evidence keyed to the exact task/mode/run.
- Embedded/self-reported trace token counts are advisory only and cannot authorize a strict token-reduction claim.
- Duplicate or mismatched verdict/usage evidence fails closed.
- Token reduction remains subordinate to non-regressing task success and patch correctness.

## Real-agent experiment authority

- Claim-grade real-agent evidence must be enumerated by a canonical `hashmarks.agent-experiment.v1` manifest; ad-hoc file discovery cannot authorize a public result.
- Every expected task must have exactly one baseline and one Hashmarks run. Run IDs and task/mode slots are unique.
- The manifest binds repository identity, task revision, model/config identity, and runner identity to each trace. Identity drift fails closed.
- Independent correctness verdicts are bound to the SHA-256 of the exact retained subject patch/output bytes they grade. A verdict cannot be reused for different output bytes.
- In strict raw-evidence mode, grader/provider `evidence_digest` values must equal the SHA-256 of retained raw evidence bytes inside the experiment directory.
- Experiment-relative evidence paths are workspace-confined; absolute paths and `..` escape are invalid.
- An experiment report identifies its exact manifest bytes by SHA-256.


## Experiment-set claim authority

- A valid single experiment does not automatically authorize a broad/public token-saving claim.
- `hashmarks.agent-experiment-set.v1` binds each included experiment manifest to its exact SHA-256 and revalidates that experiment before aggregation.
- Model identity, model-config identity, task-policy identity, and any declared runner/grader/provider/benchmark-protocol identity must remain identical across a set; drift fails closed.
- Experiment IDs, manifest bytes, run IDs, and unique `(repository_identity, task_id, task_revision)` task identities cannot be reused to pad an aggregate.
- Aggregate model-input-token reduction is computed from total exact provider-authoritative baseline and Hashmarks tokens across eligible experiments, never by averaging experiment percentages.
- Broad/public breadth eligibility has fixed minimums of 3 experiments, 3 distinct repositories, and 30 unique tasks. A caller cannot lower those floors through manifest data or CLI options.
- Breadth eligibility is not statistical-significance authority and does not generalize beyond the exact model/config/task-policy/benchmark identities retained by the set.


## Replication authority (0.10.6)
- Repeated experiments MUST declare an explicit replication group under experiment-set v2.
- Replication MUST NOT increase repository/task breadth counts.
- Statistical eligibility requires the configured minimum repeats for every declared group and at least two retained experiments.
- Confidence intervals are deterministic and descriptive over exact retained experiments only; they MUST NOT be represented as population/generalization proof.
- Experiment-set v1 semantics remain frozen and backward compatible.


## Retrieval regret authority (0.10.7)
- Useful/required retrieval evidence MUST be defined outside the agent trace by a separately identified evidence authority.
- Trace and required-evidence task revision and repository identity MUST match exactly.
- Missing required evidence MUST remain explicit and MUST NOT be converted into zero regret.
- Retrieval-regret metrics are observational optimization evidence; they do not independently authorize token-saving or correctness claims.
- The observatory MUST NOT enter Identity/daemon hot paths or change CodeMap ranking semantics.


## Derived intelligence graph (0.10.8)
- A derived node identity MUST represent its semantic value, not the identities of the inputs used to compute it.
- Upstream dependencies and consumed input identities MUST be retained separately from the derived value identity.
- Body-only source changes MAY preserve higher-level semantic identities such as the symbol surface.
- Derived graph recording MUST NOT change CodeMap retrieval/ranking behavior in 0.10.8.
- Existing workspace databases MUST backfill missing derived nodes on sync rather than trusting absence as freshness.


## Semantic invalidation shields (0.10.9)
- A semantic shield exists only when a derived value identity is unchanged despite changed consumed input identities.
- Unchanged higher-level semantic identity MUST be eligible to stop future derived invalidation propagation.
- Shielding MUST NOT suppress required line/range/source-index refresh.
- Sync MUST report changed, preserved and shielded surface counts for measurement.


## Worktree base/overlay reuse (0.10.10)
- A base snapshot MUST be keyed by the exact Git tree identity and repository common-dir namespace.
- Snapshot reuse MUST be CodeMap-only and MUST NOT enter canonical Identity authority.
- Any path Git reports staged, unstaged, deleted, renamed, copied or untracked MUST remain an overlay and MUST NOT reuse base file evidence.
- Failure to prove Git overlay state MUST disable base-snapshot reuse.
- Shared snapshot entries MUST still bind language, visibility, file digest and a present content-addressed parsed artifact.
- Hashmarks-owned state MUST NOT count as repository overlay.


## Query routing (0.10.11)
- Query intent classification MUST be deterministic and inspectable.
- A strong route MAY prune retrieval work only when the retained hybrid recall floor remains available through lexical/path indexes.
- Ambiguous queries MUST retain full hybrid retrieval.
- Routing MUST NOT weaken the strict multi-repository recall/fallback gates.
- Query routing remains outside Identity/daemon authority and latency.


## Progressive context protocol (0.10.12)
- Context disclosure MUST use one shared CodeMap generation and retrieval evidence base; levels MUST NOT become parallel indexes or freshness authorities.
- `orient` MAY disclose ranked candidate identities only and MUST NOT read source bodies.
- `outline` MAY disclose signatures/outlines only and MUST NOT read source bodies.
- `evidence` MAY add bounded relationship/dependency signatures and MUST NOT read source bodies.
- `source` is the only context level that MAY upgrade visible symbols to exact source ranges.
- Agent visibility and token-budget boundaries remain authoritative at every disclosure level.
- Unknown disclosure levels MUST fail closed rather than silently escalating to source.
- The pre-0.10.12 `context()` behavior remains available as the default `source` disclosure for compatibility.


## Candidate / rerank pipeline (0.10.13)
- Broad candidate generation MUST remain cheap, deterministic and index-backed.
- Small candidate sets MUST reach the full reranker without truncation.
- Large candidate sets MAY be bounded before full reranking only through a deterministic, path-diverse preselection stage.
- Exact identifier/path evidence and explicit relationship boosts MUST remain eligible for the bounded rerank set.
- The retained multi-repository recall/fallback gate remains the authority for accepting any candidate-bound change.
- A future semantic/model reranker MAY attach only at the bounded rerank stage; it MUST NOT scan the whole repository or become Identity authority.


## Context CAS (0.10.14)
- Context cache keys MUST bind exact workspace fingerprint, CodeMap generation, query, budget, limit, disclosure, policy identity, retrieval protocol and ranked hit evidence.
- Cached payload bytes MUST be content-addressed and rehashed on read; a mapping row alone is never sufficient authority.
- Freshness/generation/warning metadata MUST be rebuilt for the current request and MUST NOT be replayed from cached payload bytes.
- Exact source-range payloads MUST NOT be cached or reused unless filesystem freshness is positively proven.
- Structural payloads MAY be reused when freshness is unknown but MUST NOT be reused when staleness is positively known.
- Context CAS is disposable derived state under CodeMap and MUST NOT enter canonical Identity or execution authority.


## Multi-agent single-flight retrieval (0.10.15)
- Single-flight keys MUST contain only immutable repository/retrieval request identity; agent prompts beyond the exact query, session history and mutable agent state MUST NOT be shared.
- In-flight entries MUST disappear when computation completes; persistent reuse belongs only to the separately verified Context CAS.
- Followers MUST receive only the immutable final result or exception from the leader computation.
- Equivalent concurrent `find` requests MAY share one in-process computation.
- Structural context MAY share an in-process computation when freshness is not positively stale.
- Exact source context MUST require positive filesystem freshness before sharing; unknown or stale source requests run independently.
- Single-flight remains CodeMap-local and MUST NOT enter canonical Identity, execution or grading authority.
- Python annotation relationships MAY add `return-type`, `parameter-type`, `inherits` and `attribute-type` edges, but they remain derived structural evidence and never become execution or grading authority.
- Type-relation expansion MUST be anchored in exact query-name symbols, resolve local symbols through bounded indexed lookup, and protect only a bounded number of directly related hits.
- Parser semantics changes that alter structural evidence MUST change the parser identity so stale parsed artifacts cannot be reused as if they had the new semantics.
- Edge relationship lookup on large repositories MUST remain indexed by path/source; richer semantic graphs may not reintroduce whole-edge-table scans into query latency.


## Real-agent trace intake / regret triage (0.10.16)
- Runner-specific tool names MUST NOT be guessed; every raw tool MUST be explicitly mapped to a canonical navigation kind or explicitly ignored.
- The normalization-policy identity MUST be derived from the exact canonical tool mapping.
- Raw runner-log bytes MUST remain SHA-256 bound to the normalized trace.
- Runner event sequence MUST be strictly monotonic before normalization.
- Repository paths in raw logs and required-evidence manifests MUST reject absolute or parent-escaping paths before normalization.
- Regret MUST distinguish first-required-evidence latency from all-required-evidence latency.
- Repeated-query/read token estimates and irrelevant-read token estimates are overlapping observational opportunities and MUST NOT be added together as a savings claim.
- Regret suites MUST byte-bind every member trace and evidence manifest and reject duplicate task/mode runs.
- Normalization and regret triage remain outside Identity, execution, correctness-grading, and provider-token authority.


## Crash-safe runner journal (0.10.17)
- Journal initialization MUST be create-only; an existing non-empty journal MUST NOT be reused as a new run.
- Each observed wrapper event MUST have an explicit non-negative sequence and MUST be written create-only so duplicate sequence evidence cannot overwrite prior bytes.
- Finalization MUST require a contiguous sequence from zero; a missing event MUST fail closed rather than silently shorten the trace.
- Final raw logs MUST be validated through the same explicit tool-map/path normalization authority introduced in 0.10.16.
- Optional event start/finish nanoseconds MUST be non-negative and finish MUST be >= start.
- Timing-derived regret is observational only and MUST NOT become provider-token, grader-correctness, Identity, or execution authority.
- The journal MUST remain runner-neutral; it MUST NOT infer Codex/Pi tool semantics or intercept execution implicitly.

## Repository control-surface retrieval (0.10.18)

- Repository domains are derived retrieval metadata only; they never grant visibility, freshness, correctness, or execution authority.
- Control-surface ranking is intent-scoped. Queries with no explicit domain signal retain ordinary source/test behavior.
- Domain matching may boost/reserve already discovered evidence, but may not create a parallel unbounded repository search universe.
- Bounded docs/scripts remain subject to the same size, visibility, freshness, and source-policy checks as other CodeMap files.
- The legacy multi-repository recall/fallback gate remains release authority for general retrieval regressions.

## Task-query formulation / multi-view retrieval

- Full-task query formulation is derived/advisory CodeMap intelligence only.
- Inputs are limited to candidate-visible task text plus derived repository lexical statistics.
- SECRET grading authority, expected evidence, model identity/history, and execution state are forbidden inputs.
- `find_task()` must remain additive to `find()`; ordinary `find()` ranking is not rewritten by task-query policy.
- Multi-view work is bounded to at most 80 candidates per view and fusion is path-diverse.
- Governance vocabulary may add ownership/architecture/contract/control-surface evidence but may not grant visibility, freshness, correctness, or execution authority.

## Evidence-family retrieval invariants (0.10.20)

- Evidence-family expansion is derived only from candidate-visible task wording.
- Evidence-family vocabulary is repository-generic and never hard-codes benchmark file names or hidden answers.
- Base rare-term and governance retrieval remain separate, preserved views; the evidence-family view may add candidates but cannot replace them.
- Identical query views are deduplicated before retrieval.
- Evidence-family fetch depth is bounded below the ordinary base/governance task fetch depth.
- Repository-domain/evidence-family metadata never grants read visibility, execution authority, identity authority, or grading authority.
- Identity and daemon hot paths never import or execute task-query formulation.


## Benchmark shard authority (0.10.21)

- Known bounded benchmark/test workloads may be split before execution; timeout discovery is not a prerequisite for sharding.
- Shard boundaries are deterministic from `total` and `shard_size`.
- A shard is reusable only when its data file and seal both validate against the immutable manifest identity.
- `run_identity` is part of that manifest and must bind the exact candidate plus benchmark inputs used by the caller.
- Planned warm-up is explicit, separately sealed, and required before any shard executes.
- Incomplete/failed shards are never sealed and therefore remain pending.
- Aggregate publication requires every planned shard, exactly the planned total row count, and globally unique row IDs.
- Benchmark sharding is orchestration only: it cannot enter Identity authority or change retrieval/grading semantics.

## Scoped ownership evidence preservation (0.10.22)

- `find_task()` may reserve at most one scoped `AGENTS.md` already returned by the governance view.
- Reservation is permitted only when the base task route is HYBRID/ambiguous.
- Reservation is forbidden when fused results already contain a README/AGENTS authority.
- Reservation never creates a new candidate, scans unrelated control files, or changes `find()` semantics.
- High-confidence routes such as RELATIONSHIP must not be displaced by ownership preservation.
- Promotion requires at least one recovered blind-QA miss and zero losses among previously-hit questions.

## Conceptual scoped README preservation / blind benchmark integrity (0.10.23)

- Scoped README preservation is permitted only for CONCEPTUAL base routes.
- The README must already be present in the governance view's first 20 distinct paths; the preservation lane may not discover or scan for new files.
- The README parent must be a deep scope (at least three path components).
- At least two non-README/non-AGENTS results in the fused top 10 must already localize beneath that exact parent scope.
- At most one scoped README may replace the final result slot; all higher-ranked fused evidence remains unchanged.
- High-confidence relationship/path/config/test/identifier/structural routes remain untouched by this rule.
- External QA candidate workspaces MUST physically exclude SECRET answer material before CodeMap sync.
- Benchmark reports MUST record a candidate-visible corpus identity and MUST NOT compare parent/candidate results produced under different retrieval protocols or corpus visibility boundaries.
- Historical benchmark evidence is immutable; discovering a benchmark-integrity defect requires a new paired baseline rather than rewriting old evidence.


## Graph-backed evidence adjacency (0.10.24)

- `find_task()` remains the canonical locator; graph adjacency is additive and may not rewrite or displace primary retrieval.
- Every adjacency candidate is one hop from an already-selected canonical task seed. No recursive graph walk is permitted in this phase.
- Static symbolic edges require task-affine identifier overlap and are rejected when a target spelling resolves to more than four distinct repository paths.
- Native file edges are consumed only through their existing freshness authority.
- Expansion is bounded by seed count, per-seed edge count, global result count, and per-seed result count.
- Every returned adjacency candidate carries seed/relation/confidence provenance.
- A missing trustworthy graph path is preferable to a coincidental same-name relation.
- Identity and daemon hot paths do not consume CodeMap graph adjacency.


## Multi-surface change-impact navigation (0.10.25)

- Change-impact navigation consumes only paths already proven reachable by the existing reverse file graph and retained project graph.
- It MUST NOT create fuzzy or LLM-generated dependency edges.
- Results are bounded by traversal depth and per-surface capacity.
- Every surfaced file carries relationship depth and provenance.
- The projection is advisory navigation only and MUST NOT become execution, ownership, or test-selection authority.
- `find()` and `find_task()` ranking semantics remain unchanged.


## Scoped repository authority hierarchy (0.10.26)

- Scoped authority discovery is mechanical path hierarchy, not semantic retrieval: only indexed `AGENTS.md` and `AGENTS.override.md` surfaces participate.
- Root authority applies repository-wide; nested authority applies only beneath its exact directory subtree.
- Deeper scope is more specific; `AGENTS.override.md` wins over `AGENTS.md` at the same scope.
- README, architecture, contract, policy, and other documentation may be retrieved as evidence but MUST NOT be promoted into scoped authority by this API.
- Task-based scope inference may use canonical `find_task()` only to identify candidate target paths; it may not change ranking.
- The API reports authority paths, scopes, precedence, visibility, and applicability only. It MUST NOT parse instructions into execution permissions or become an orchestration authority.
- `find()` and `find_task()` results must remain path-for-path unchanged by scoped-authority queries.


## Retrieval provenance / explainability (0.10.27)

- Explainability is observational: canonical retrieval bytes/order must not depend on explanation requests.
- Every selected task path may report the exact task-query lane, distinct-path rank, lane weight, and weighted-RRF contribution that discovered it.
- Bounded post-fusion preservation is labeled separately from ordinary RRF selection.
- Provenance must not invent semantic relationships, agent intent, or authority.
- Existing graph adjacency, change-impact, and scoped-authority provenance remain separate authorities and are not collapsed into a synthetic global score.


## Task-query latency closure (0.10.28)

- Canonical `find_task()` results may be reused only within the same CodeMap generation and exact task/limit key.
- A CodeMap generation change MUST force task retrieval recomputation.
- The task-result cache is bounded, in-process execution state only; it is not persisted and cannot become evidence authority.
- Cache reuse MUST preserve byte-for-path-equivalent selected results and MUST NOT change first-query ranking semantics.
- Promotion requires exact blind-QA invariance and the existing ordinary retrieval latency/recall firewalls.


## Benchmark protocol authority (0.10.29)

- Benchmark comparability MUST be bound to canonical protocol bytes, not filenames or caller convention.
- The protocol identity binds retrieval API, budget, limit, ordered repository workspace fingerprints, corpus SHA-256 identities, and task counts.
- Any change to those fields MUST change the protocol identity.
- Timing/result data are observations and MUST NOT participate in protocol identity.


## Native paired A/B benchmark (0.10.30)

- A/B reports MUST have identical `benchmark_protocol_identity` and identical canonical protocol payloads.
- The paired task set MUST match exactly by repository name + task ID.
- Baseline and candidate report bytes MUST be SHA-256 bound in the comparison artifact.
- Implementation identity is not benchmark-input identity; both implementations must execute against the same fixed benchmark repositories/corpora for a strict paired claim.
- Recall losses and fallback regressions MUST be explicit paired outcomes, never hidden by aggregate averages.


## Adaptive evidence budget (0.10.31)

- Adaptive budgeting is opt-in through `task_context_plan()` / `task_context()`; existing `context()` semantics remain unchanged.
- Plans may use only deterministic route classification and candidate-visible task cues.
- Budgets are bounded by explicit min/max limits and explicit caller overrides take precedence.
- Adaptive planning MUST NOT change `find_task()` ranking or create new evidence authority.


## Retrieval stability testing (0.10.33)

`CodeMap.retrieval_stability()` replays canonical `find_task()` within one CodeMap generation while bypassing only the generation-bound task-result cache. It fingerprints the complete ranked path/kind/score projection, reports the first divergent rank when instability exists, restores pre-existing cache state, and has no ranking effect. Stability is measured; retrieval is never modified to satisfy the gate.


## v0.10.34 fresh multi-repo corpus

Hashmarks carries a deterministic fresh benchmark family (`hashmarks-v0.10.34-fresh-corpus-a`) that materializes three disjoint repositories and 18 independently defined localization tasks across Python service, TypeScript UI, and release/contract automation shapes. Fixture identity is computed only from declared source bytes and corpus bytes; generated `.hashmarks`, VCS, virtualenv, and dependency state cannot affect corpus identity. The existing agent-suite protocol separately binds retrieval parameters, workspace fingerprints, corpus hashes, and task counts. The fresh benchmark is additive QA evidence and does not alter retrieval or ranking.


### v0.10.38 — inspection effectiveness
Ambiguity remains advisory and canonical retrieval is unchanged. The answer-blind worker inspection benchmark compares defer-only behavior with inspect-then-resolve behavior. Resolution may use only public task text and worker-visible competing evidence; hidden expected files/symbols remain grader-only. Same-path role ambiguity collapses safely, explicit public surface/role cues may resolve a competing candidate, and unresolved/tied evidence remains deferred.

## v0.10.39 multi-step worker proof
- Multi-step worker policy is observational benchmark logic, not retrieval authority.
- Workers receive only public task id/query; expected edit and verification targets remain grader-only.
- Ambiguity recovery may inspect competing worker-visible evidence but must not consume hidden answers.
- Verification discovery is a separate retrieval step; success is scored independently from edit-target success.
- Evidence cost is reported, never used to mutate canonical ranking.

## v0.10.40 failed-verification recovery — historical benchmark invariants

- Controlled wrong-edit injection is grader authority only.
- Recovery workers never receive `expected_files` or `expected_symbols`.
- The **benchmark worker/harness** may remember a failed edit while evaluating consumer recovery; that memory is not repository authority and does not admit failed-edit state into modern Hashmarks product APIs.
- Evidence-guided benchmark recovery must not convert one failed edit into a different wrong edit merely to claim progress.
- This benchmark is additive QA evidence, has no canonical ranking effect, and must be interpreted under `PRODUCT_BOUNDARY.md`.


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

## v0.10.47 real Codex economics
- A Codex economics result is real only when produced by an actual `codex` executable; deterministic fake binaries are test fixtures only.
- Every lane runs as a fresh independent `codex exec` process with the same task/model/reasoning/sandbox contract.
- Worker prompts contain only public task fields. Expected files/symbols/verification remain grader-only.
- Missing token telemetry is recorded as unavailable/zero and is never estimated as Codex usage.
- All prompts, commands, JSONL events, stderr hashes, final structured results, and wall time are retained per run.

## v0.10.48 real selective scout
- Scout spawn is permitted only when worker-visible Hashmarks ambiguity is true.
- Scout receives no grader answer and may choose only among the supplied ambiguity candidates.
- Scout output outside that candidate set is rejected, never normalized into a plausible answer.
- Scout and main worker run as separate fresh `codex exec` processes; total economics sums both.
- No recursive child-agent delegation is required for the benchmark.

## v0.10.49 model-tier economics
- Verified solution requires both correct first edit target and correct verification target.
- Tokens per verified solution is emitted only when real Codex token telemetry is available.
- Missing stdout usage may be recovered from the exact thread rollout; it is never approximated from prompt bytes.
- Pareto dominance compares only variants with actual token telemetry.
- Model names/reasoning efforts are explicit experiment inputs, never silently substituted.

## v0.10.50 sanitized agent economics
- SECRET benchmark answers must live outside the worker-visible repository.
- Worker traces freeze before SECRET grading.
- Exact identifier-shaped task tokens may preserve an already-indexed exact symbol path; generic natural-language tokens may not.
- Agent swarms should share one warm Hashmarks service; per-child index initialization is diagnostic only, not the preferred deployment model.

### v0.10.51 agent-action invariants

- Canonical retrieval authority remains `find_task()`; `task_action_map()` never discovers or reranks paths.
- A test-domain path is verification evidence and cannot simultaneously become the implementation edit target merely because it is source code.
- Benchmark/external corpus files are inspection evidence, never edit authority.
- Config/build paths become edit candidates only from strong direct config cues; generic task words do not grant edit authority.
- Agent-economics SECRET answers must live outside the worker repository and are opened only after traces freeze.

### v0.10.52 shared-agent authority invariants

- One CodeMap service process owns one warm CodeMap for a workspace.
- Agent clients are stateless and never become repository-index authorities.
- The service is single-owner for SQLite/CodeMap state; concurrency is admitted at the socket queue, not by concurrent database writers.
- Service status exposes sync/request counts so duplicate initialization is observable.
- `task_action_map()` results over IPC preserve the same canonical ranking/action semantics as in-process CodeMap.

### v0.10.53 negative-evidence compatibility invariants — historical boundary debt

These invariants document the retained historical surface; they do **not** admit failed-attempt memory as a modern Hashmarks responsibility.

- Canonical `find_task()` repository evidence must remain independent of caller attempt history.
- Any retained failed-target compatibility input must remain request-local and must never become shared/global repository truth.
- New features must not depend on failed-target state; the external agent/harness owns failed attempts and retry memory.
- Repository-native negative evidence (absence, ambiguity, staleness, unresolved ownership) remains valid when mechanically derived from repository state.

### v0.10.54 scout-admission compatibility invariants — historical boundary debt

- Historical `scout` fields may remain for compatibility but are not a modern orchestration authority.
- Hashmarks may expose ambiguity, candidates, and discriminating repository evidence.
- Deciding whether to create another agent/process, choosing its model, and managing its context/lifecycle belongs to the external agent/harness.
- New APIs must prefer repository-intelligence terminology over scout/delegation policy.

### v0.10.55 work-score invariants

- Selecting a verification surface is not equivalent to passing verification.
- A verified solution requires the final expected edit target and a passed verification event bound to that edit.
- Repeated disproven edits, wrong edits, duplicate reads, and unnecessary scout calls remain separately observable; aggregate score never hides them.
- Missing exact model usage produces null cost-per-verified-solution rather than an estimate.

### v0.10.56 verification-plan invariants

- Verification plans are argv arrays plus working directory, never shell snippets.
- Unsupported test ecosystems return unavailable rather than guessed commands.
- When an exact pytest test symbol is known, the plan targets the node ID instead of the entire test file.
- Passing a verification plan on the unchanged tree proves the plan is runnable; it does not prove a patch that was never applied.

## v0.11.5 provenance-compression invariants

- Compact project-impact encoding is a lossless transport representation over already-admitted project provenance; it must not discover, rank, infer, or remove project authority.
- Every compact packet must expand back to the verbose project-impact roots, affected-project depths, admitted edges, producer/kind provenance, completeness counters, and optional confidence without semantic loss.
- Project provenance bounds are independent of bounded file-surface limits. Truncation must remain explicit through `reported_affected`, `total_affected`, and `complete`; compression must never disguise truncation as completeness.
- Verbose encoding remains the compatibility default. Compact encoding is opt-in through the Python API, CLI, and service contract until downstream compatibility evidence justifies any default change.
- Provenance compression is repository-evidence transport only. It does not add semantic retrieval, planning, command execution, timeout/retry behavior, scheduling, or environment recovery.
## v0.11.8 verification-relevance invariants

- Verification relevance is a bounded repository-evidence projection around an already-selected edit owner; it must not alter canonical `find_task()` ranking or nominate a different edit owner.
- Reverse-reference evidence may promote a test surface only when the reference is indexed, worker-visible, test-domain evidence and the candidate has non-generic namespace locality to the selected edit owner.
- A verification override must be uniquely stronger on evidence dimensions independent of canonical rank; ties and weak evidence remain conservative rather than guessing.
- Candidate discovery is explicitly bounded by edit-symbol and per-symbol reverse-reference limits, and returned candidate evidence is separately bounded.
- Verification relevance may expose a mechanically derived test symbol and whether an existing verification plan is available, but selecting a test is not proof of sufficiency and Hashmarks must not execute the plan.
- SECRET expected verification paths are grader-only; the selector uses PUBLIC task text plus deterministic repository indexes only.



## v0.11.9 repository-work-selection envelope invariants

- `hashmarks.test-shards.v3` remains the shard-membership contract; v0.11.9 does not introduce a new membership algorithm merely to carry downstream provenance.
- `hashmarks.repository-work-selection.v1` binds the exact inner v3 plan to canonical repository content identity, exact selection-input identity, Hashmarks producer version/algorithm/implementation identity, and optional externally supplied release-artifact SHA-256 provenance.
- A repository-content change invalidates the outer envelope even when deterministic shard membership is unchanged. A change to test-selection inputs must also invalidate the selection-input identity and, when membership/weights change, the inner plan identity.
- `isolated_process` is a Hashmarks-described execution requirement attached to immutable membership. It does not grant Hashmarks process-launch, timeout, retry, concurrency, scheduling, or recovery authority.
- The envelope must contain no execution-policy fields such as argv, deadline/timeout, retry counts/delays, worker/concurrency settings, schedule, machine placement, process state, or environment-recovery instructions.
- Producer artifact identity is optional evidence and must be explicit `sha256:<64 hex>` when supplied; absence must remain visible rather than being replaced by the locally installed version.
- Consumers may reject an envelope whose repository identity, producer provenance, inner plan identity, or schema does not match their admitted policy. Hashmarks does not decide that admission policy.

## v0.11.10 consumer-conformance and membership-conservation invariants

- `hashmarks.test-shards.v3` and `hashmarks.repository-work-selection.v1` remain unchanged wire contracts; v0.11.10 adds strict validation and derived membership identity rather than silently extending either schema.
- Strict conformance is allowlist-based. Missing or unexpected fields in the envelope, producer, repository binding, authority declaration, selection, or shard rows fail closed even when a caller recomputes the unkeyed packet identity.
- The authority declaration is frozen: Hashmarks owns repository-content identity, deterministic test membership, process-isolation requirements, and selection-plan identity; the execution layer owns process launch, deadline, retry/resume, concurrency, scheduling, environment recovery, and result authority.
- `hashmarks.test-shard-membership.v1` hashes the sorted exact test-node set independently of shard grouping/order. External execution refinement may preserve this identity by regrouping the same nodes, but omission or duplication must fail/change membership identity.
- Process-isolation requirements are selection evidence. A v3 plan may not add arbitrary isolated shards or omit isolation for a producer-declared process-sensitive node and still pass conformance.
- `validate_work_selection_repository_binding()` may re-prove repository content, selection inputs, and deterministic selection from current bytes. This remains repository-evidence validation only; it must not launch tests, choose timeout budgets, retry work, schedule jobs, or certify results.
- Producer artifact identity remains provenance, not a cryptographic signature. Downstream trust/admission of that provenance belongs to the execution/certification layer.



## v0.11.11 B2 authority-discrimination invariants

- Multiple distinctive task-local verification origins that independently resolve to different live implementation owners are unresolved authority evidence; Hashmarks must preserve the ambiguity and require discrimination rather than silently selecting the first-ranked owner.
- Multiple task-local verification origins that converge on the same implementation owner remain resolved and must not be blocked merely because several tests exist.
- Explicit configuration/policy tasks may use a verification-backed active implementation owner only as a namespace-locality anchor for nearby config/contract evidence; that source path does not become configuration authority.
- Bounded indirect verification relevance is limited to edit symbol → source/entry-point → test reference evidence with explicit fanout limits. It is nomination evidence, not verification execution or result authority.
- `checks/**/*_spec.py` is a verification domain only under the strong checks-directory plus Python-spec naming convention; arbitrary helper files under `checks/` are not tests.
- Semantic/vector nomination remains unadmitted by B2 because the observed failures were authority discrimination and bounded relation gaps, not unresolved semantic recall.


## v0.11.13 qualified import-identity invariants

- Same short symbol names MUST NOT establish verification authority when concrete import/module identity can be qualified.
- Python relative imports, `as` aliases, package re-exports, and name-scoped star re-exports may contribute qualified owner identity only through bounded syntax/index evidence.
- Qualified re-export traversal is bounded to eight import hops. Cycles, multiple concrete leaves, multiple module-path owners, or a frontier continuing beyond the bound MUST remain unresolved; Hashmarks must require discrimination/scouting rather than fall back to stale short-name authority.
- A star re-export is expanded only for the specific symbol currently being qualified; it MUST NOT become an unbounded namespace import or general symbol-discovery mechanism.
- Multiple live editable owners carrying the same task anchor behind an archive/legacy hit are unresolved authority evidence. The archive hit MUST NOT win merely because stale verification surfaces rank first.
- These rules change repository-evidence qualification only. They MUST NOT execute verification, decide retries/recovery, schedule work, or acquire certification authority.
- A Python module named `test_*.py` under an application source tree (`src/`, `lib/`, or `app/`) remains production source unless its repository path independently establishes test ownership. Filename shape alone MUST NOT convert production code into verification authority.
- Test files may become edit authority only when the task explicitly asks to add/change/fix/strengthen test or regression behavior; generic mentions of tests remain verification-only.
- CamelCase and snake_case forms of the same identifier may establish the same bounded task anchor. Generic contract/policy/authority vocabulary MUST NOT displace a stronger identifier owner without explicit repository evidence.
- Multiple close editable identifier owners without decisive structural or qualified verification evidence MUST remain unresolved and require discrimination.
- Explicit pytest shard/batch tuning may nominate a uniquely evidenced build/config surface, but Hashmarks MUST NOT decide the execution-layer shard size, timeout, retries, concurrency, or process lifecycle.

## v0.11.12 compact worker authority-receipt invariants

- Compact worker projections MUST NOT become a second ranking or ownership authority; they project the canonical action map only.
- Full decision evidence remains available for audit/recovery and MUST NOT be discarded merely to reduce model-visible context.
- `hashmarks.decision-authority-receipt.v1` is independent of worker token budget and MUST be identical across full packet, decision brief, action brief, and agent start when repository generation, task, selected action authority, negative evidence, and verification authority are unchanged.
- Repository/task/decision-authority changes MUST change the authority identity.
- The receipt MUST remain compact: it references authority provenance and MUST NOT inline verification-relevance or work-context bodies.
- This is repository-evidence provenance only; it is not execution admission, result authority, or a cryptographic signature from a trusted third party.

## v0.11.13 repository-understanding economics invariants

- A CodeMap sync MUST publish durable `BUILDING` state before repository materialization and MUST publish `COMPLETE` only after fingerprint/generation finalization.
- Query paths MUST NOT silently convert an interrupted `BUILDING` generation into fresh authority. Worker decision packets MUST mark incomplete CodeMap identity stale/unsafe and require discrimination.
- Index preflight MAY report directly measured repository shape (files, bytes, languages, evidence surfaces, work class) but MUST NOT invent lexical-row estimates, deadlines, retry policy, worker counts, or scheduling policy.
- Index economics MAY report cold/warm/incremental state, elapsed time, throughput, lexical occurrences, persistence bytes/amplification, bounded persistence chunk size, and per-surface evidence cost.
- Per-surface accounting is measurement evidence only. Generated files, lockfiles, OpenAPI, translations, snapshots, fixtures, docs, tests, config, or source MUST NOT be excluded or demoted merely because they are expensive; a correctness/evidence-contribution experiment is required first.
- Bounded SQLite persistence transactions are repository-index storage mechanics only. They MUST NOT become execution shards, retries, resume/checkpoint orchestration, timeout management, process control, or certification authority.
- Longitudinal storage, dashboards, heatmaps, alert thresholds, fleet comparisons, and operational run policy remain outside Hashmarks.

## v0.11.13 real-world evidence-value calibration invariants

- Lexical-surface optimization MUST be evaluated on a frozen task corpus before production indexing authority changes.
- Benchmark-only lexical variants MUST operate on copies of a completed CodeMap and MUST NOT alter canonical runtime indexing behavior.
- The primary safety gate is zero new false-safe decisions. Exact-owner, exact-verification, scout/discrimination, decision latency, lexical rows, and persisted bytes MUST be reported separately rather than collapsed into one score.
- Underspecified tasks MAY declare `expected_scout=true`; a confident owner on such a task is a false-safe outcome.
- A lower lexical-row count or faster query is not sufficient evidence for promotion when correctness evidence is incomplete.
- Real repository churn QA MUST cover warm recheck, one-file change, bounded many-file change, rename/delete membership, incomplete-generation fail-closed behavior, and ordinary sync recovery.

## Bounded decision calibration contract

- Calibration consumers parse `hashmarks.task-decision-packet.v2` through the typed decision contract; unknown or malformed packet layouts fail closed.
- Multi-task calibration is partitioned by an immutable manifest binding corpus SHA-256, repository identity, CodeMap generation, Hashmarks candidate source identity, scorer schema, representation variant, and deterministic group membership.
- Group results are independently complete evidence. Aggregation rejects mixed identities, duplicate groups, and missing groups; incomplete aggregates remain explicitly incomplete.
- `decision_session()` may cache only generation-stable read-only evidence primitives. It never caches final task decisions and rejects generation changes while active.
- Calibration/session batching is measurement infrastructure, not timeout, retry, resume, scheduling, process-management, or certification authority. Those remain outside Hashmarks.
- Decision-scale measurements are aggregated from identity-matched completed groups rather than requiring one monolithic long-lived process.

## v0.11.13 weak-anchor / repeated-work closure invariants

- Generic behavior/contract wording is not edit authority in a repetitive repository. A contract surface without an identifier-shaped task anchor, a structurally resolved owner, an explicit requested surface, decisive qualified verification, or a rare repository-level lexical anchor MUST remain ambiguous and require discrimination.
- Weak-anchor handling is fail-closed only: it MUST NOT promote a different owner merely because the current best owner is under-anchored.
- Pure repository-path domain classification MAY be memoized in-process because its output depends only on the path string and static classification rules. The cache MUST NOT become persistent repository authority and MUST NOT alter ranking or ownership semantics.
- Performance optimization of `task_action_map` MUST preserve the frozen corpus edit/verification result set except for intentional ambiguity/scout corrections backed by explicit QA.
- Repeated-work optimization remains repository-understanding computation only; timeout decisions, retries, restart/resume, scheduling, process lifecycle, and certification remain outside Hashmarks.

## Bounded calibration durability and hot-loop evidence economics

- Real-world calibration may persist immutable per-task evidence receipts keyed by manifest, repository generation, candidate source identity, scorer schema, group, and task identity. These receipts exist only to avoid recomputing already-completed benchmark evidence after an outer process is terminated.
- Calibration receipt reuse is not runtime retry, resume, scheduling, process management, or execution authority. Resumed timing is marked non-comparable for performance claims when process-local cache/session state differs.
- Query hot paths SHOULD prefer stable keyed or bulk evidence reads over repeated lookup-by-value, N+1 SQLite calls, or N×returned-row Python filtering when semantics are equivalent.
- Pure process-local memoization is permitted for generation-independent normalization/classification functions. Repository-derived caches remain generation-bound and must never cache final authority decisions merely because tasks look similar.

## v0.11.13 decision hot-loop / validation-economics invariants

- Generation-bound decision caches may retain only deterministic repository evidence keyed by the exact CodeMap generation; completed research receipts, not process-local caches, are the cross-process durability authority.
- When a decision phase already knows a bounded set of paths/modules/symbols, it should use bulk keyed reads rather than one SQLite lookup per known identity. This includes file-row preloading for import-source paths and bulk exact module-name resolution.
- A bulk optimization is accepted only when it preserves independent-query semantics. Lower SQL-call count alone is not evidence of improvement: the real Oh-Goon multi-view lexical CTE was rejected because it was slower than separate indexed reads despite fewer physical queries.
- Verification/ownership performance changes must preserve the frozen real-repository correctness gate (no new false-safe decisions); unresolved ownership remains a scout/discrimination result rather than a performance shortcut.
- Candidate validation is tiered. Source-only persistent candidates require bounded source test proof, source compileall, one deterministic ZIP, and focused exact-extraction tests. Independent rebuild byte identity and broader packaging/install proof are canonical/promotion requirements unless packaging/build code changed in the candidate.

**G34. Dynamic Python module loading is repository ownership evidence, not runtime authority.** CodeMap may nominate files lexically and use AST structure to report repository-owned `spec_from_file_location` → `module_from_spec` → `exec_module` chains that can create fresh module objects outside normal `sys.modules` ownership. A uniquely resolved package target may be exposed as a safer normal-import identity. Test/plugin loaders and explicit `sys.modules` registration must remain distinguished from production cache-bypass warnings. Hashmarks never rewrites or executes these imports and never claims runtime failure or repair certification from static evidence alone.

**G35. Repository intelligence and execution authority remain separate by constitution.** Hashmarks tells the agent what the repository means, who owns what, what is risky, what should probably change, and what should verify it. Oh-Goon decides whether execution is admitted, runs it safely, manages processes/timeouts/recovery, and certifies the result. Static ownership, risk, repair-surface nomination, verification relevance, and immutable selection evidence must never be interpreted as runtime admission, process control, retries, recovery, or certification authority.

**G36. Warm service parity and cache invalidation ownership remain repository evidence only.** Every public `CodeMapServiceClient` repository-intelligence method must have a matching validated service dispatch operation; exposing a client method without a service handler is a compatibility defect. `hashmarks.cache-invalidation-ownership.v1` may resolve visible Python invalidation calls to exact cache owners through local/simple-alias/qualified-import evidence, but same-name lexical coincidence is never mutation authority. Unresolved import identity remains unresolved. Hashmarks never executes invalidators, mutates cache state, decides runtime cache lifecycle, or certifies invalidation; those runtime responsibilities remain external.

**G37. Composed invalidation edges require exact repository ownership evidence.** `hashmarks.authority-ownership-graph.v2` may compose `invalidates-cache` edges only from the exact static cache-invalidation resolver. Imported or aliased invalidators require proven module/symbol identity; shadowed locals, duplicate same-named caches, and unresolved imports MUST remain ambiguous. A composed edge is repository evidence, not permission to mutate cache state, runtime lifecycle authority, execution admission, recovery policy, or certification.

**G38. Composed concurrency risk remains nomination-only repository evidence.** `hashmarks.authority-ownership-graph.v3` may attach `contains-concurrency-risk` edges only from the existing bounded static concurrency/RMW analyzer to the exact file containing the nominated sequence. Guarded versus unguarded is lexical evidence only: it MUST NOT be interpreted as proof that concurrent callers exist, proof that a visible guard is sufficient, permission to modify synchronization, runtime locking authority, execution admission, retries/recovery, scheduling, process lifecycle, or certification.



**G39. Verification ownership links require structural repository evidence.** A verification candidate may be linked to an edit authority only through direct or bounded indirect repository reference evidence. Lexical/task wording and namespace locality can nominate or rank a verifier but never prove authority coverage. Verification ownership remains repository evidence only and never grants execution, admission, process-lifecycle, recovery, or certification authority.


## G40. Ruff debt is explicit, monotonic, and cannot be suppressed

The strict `C901` / `PLR0911`-`PLR0916` limits in `pyproject.toml` are the intended zero-debt boundary. Historical violations may exist only while represented by the checked-in `ruff-debt-baseline.json`. Every change MUST pass the debt non-regression gate: no file may increase its measured excess and no new file may introduce debt. `noqa`, per-file ignores, relaxed thresholds, and moving complexity into a different file are not valid debt closure. The baseline is temporary and MUST monotonically shrink until strict `make lint` passes without exceptions.

**G45. Agent-start evidence context is identity-bound, not timestamp-trusted.** The compact start projection binds the existing decision-authority identity to repository identity, CodeMap generation, selected source revision, explicit freshness state, and native Hashmarks producer implementation identity. The context identity adds no execution authority, is independent of model token budget, and changes when revision or freshness authority changes.

**G46. Evidence-context hashing and validation remain producer-owned.** Consumers may compare or store the opaque `context_identity`, but must not recreate its canonicalization. Hashmarks exposes native `evidence_context_identity()` and `validate_evidence_context()` so tampering with authority, revision, freshness, or producer identity fails closed without transferring semantic ownership to a consumer.

**G47. Native producer identity caching may optimize immutable installed bytes only.** The no-argument native producer implementation identity may be memoized because imported package bytes are immutable for that process. Explicit package-root identity remains uncached so artifact/drift inspection observes the supplied bytes. Caching never transfers producer identity authority or suppresses explicit-root change detection.

### G49. Contract-surface consolidation is descriptive, never semantic rewriting

Hashmarks may publish which public schema version is preferred and which legacy versions remain accepted, but it must not silently rewrite one version into another or use compatibility metadata to transfer semantic authority. Legacy acceptance remains explicit in the owning reader/producer. A major-version boundary requires demonstrated incompatible public semantics, not schema-count growth.

### G51 — Names expose responsibility and product ownership

A cross-module Hashmarks name MUST reveal repository/evidence responsibility strongly enough that a blind maintainer does not mistake it for Oh-Goon admission, execution, or certification authority. New Hashmarks-owned concepts MUST NOT use bare authority/admission/execution/certification vocabulary as permission semantics. Structural decomposition is accepted only when the extracted responsibility has a stable conceptual name, coherent ownership, limited coupling, and improved discoverability. Stable v0.11 serialized/public names may remain as explicit compatibility surfaces; compatibility MUST NOT be used to create a second semantic owner or silently rewrite payloads.

## G54 — CLI facade does not own repository-intelligence command families

`hashmarks.cli` remains the executable facade and compatibility entry point. Repository-intelligence command handlers and parser families are owned by `hashmarks.repository_cli`; moving them does not transfer execution, daemon, benchmark, or impact-runtime ownership into repository intelligence.

## Consumer-contract authority invariants

- `validate_native_consumer_bundle()` is the producer-owned validation boundary for the verification-selection envelope plus downstream contract. Consumers MUST NOT reconstruct Hashmarks allowlists, identity hashing, membership normalization, or cross-binding rules.
- Native verification-selection schemas are fail-closed and allowlist-based at the envelope, producer, repository, membership, and member levels. Unknown fields do not acquire authority merely because a caller recomputes an unkeyed identity.
- Consumers that require current repository evidence explicitly request freshness at validation. A stale native bundle may remain structurally valid evidence, but it MUST fail a fresh-evidence requirement.
- Successful consumer validation exposes a small normalized repository-intelligence projection: exact producer implementation identity, repository/source identity, CodeMap/identity generation, stale state, immutable selected members, membership identity, and selection/provenance identity.
- The normalized projection contains no timeout, worker, retry, scheduling, process, result, or certification policy. Hashmarks provenance is repository/evidence provenance only; execution provenance remains external.
- Semantic version is descriptive compatibility metadata and MUST NOT substitute for exact producer implementation identity. Same-version/different-implementation cross-pairs fail when a consumer pins the admitted producer.

## Large-repository reverse-impact scale invariants

- Exact repository paths used for change-impact are path authority, not free-text task queries; one-hop adjacency must seed from the already-proven path rather than lexically re-retrieving unrelated files.
- Python reverse-impact traversal may use indexed bounded reverse import candidates only when it can preserve the existing longest-module-prefix resolution rule. If that proof is unavailable, including authoritative native-file evidence, it falls back to the established full graph.
- Scale optimizations must preserve affected-file semantics; they may not trade completeness or qualified import identity for latency.

## Re-export binding authority invariants

- A facade's local symbol presence alone does not prove local ownership when the same exported name is rebound by a direct top-level re-export. Hashmarks preserves the last directly provable unconditional binding for the local-vs-single-re-export case.
- Multiple direct re-export statements for the same exposed name remain ambiguous repository ownership even if Python runtime statement order would overwrite an earlier binding. Runtime import execution order is not repository ownership authority.
- Missing, cyclic, bounded-out, star/local-conflicted, or otherwise unproven re-export leaves remain unresolved/fail-closed. Deterministic traversal order may not manufacture a unique owner.

## Nested Python project import-root authority

- Explicit Python source-root metadata is scoped to the directory containing the declaring `pyproject.toml`; repository-relative path and import identity remain distinct.
- Full synchronization derives nested-project import roots from the already-discovered repository surface rather than a second repository walk.
- A targeted `pyproject.toml` synchronization refreshes packaging-derived roots so configuration changes or deletions cannot leave stale module identity authority in the same CodeMap service.
- Multiple nested projects exposing the same qualified module identity remain ambiguous; project/path ordering never manufactures unique import ownership.
