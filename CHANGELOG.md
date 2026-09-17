# Changelog

## Unreleased — Public release / multi-host MCP hardening

- Rework the public GitHub/PyPI landing surface for launch discovery: the README now leads with repository intelligence, codebase search for coding agents, repository context, local MCP usage, change impact, and copy-ready Claude Code/Codex/OpenCode/Pi configuration; package metadata and public docs use the same search-facing vocabulary without competitor/comparison framing or keyword stuffing.
- Bind every durable CodeMap state directory to exactly one canonical workspace. Reusing one explicit external `--state-dir` across different repositories now fails closed before any query/write instead of leaking or replacing another repository's evidence; `map clean` preserves that binding.
- Move bounded repository-race retry (`BUILDING`, decision-generation changes, unstable file sampling) into one transport-neutral owner shared by MCP and the public repository CLI. CLI queries now retry those known races centrally and return one-line caller errors if the bounded budget is exhausted instead of leaking tracebacks from leaf commands.
- Centralize SQLite first-open concurrency policy (`busy_timeout`, WAL, synchronous mode) so simultaneous cold-start processes wait for journal initialization rather than failing with `database is locked`.
- Tighten release publication verification so the publish directory must contain exactly the expected wheel and sdist, with no unbound extra entries, and translate release-contract CLI validation errors once at the script boundary.
- Make public onboarding install-first: README and Getting Started now lead with `pip install hashmarks` and the installed `hashmarks` CLI, while `make init` / `uv run` are explicitly source-development workflows.
- Lock the PyPI sdist to an intentional public-source surface: package sources, current public docs, examples, README/changelog/license/build metadata only. Repository-only tests, benchmarks, qualification scripts, `AGENTS.md`, Makefile, and `docs/development/` archaeology are no longer shipped accidentally.
- Add an exact sdist-member policy and prove that an extracted sdist rebuilds the direct wheel byte-identically. Installed-artifact smoke now exercises the real generated `hashmarks` console script plus `doctor`, `map sync`, `orient`, and `find` from a disposable repository.
- Qualify the declared pytest floor at `pytest==8.4.0` in CI and run installed wheel/sdist artifact qualification on every advertised Python 3.11–3.14 job, not only the Python 3.14 release environment.
- Add capability-aware constrained-host diagnostics for restricted CI/container environments: `HASHMARKS_CONSTRAINED_HOST=1 make test` reuses deterministic repository-owned shards, disables unrelated host pytest plugins, explicitly gates missing MCP SDK/installed-console/Git capabilities, excludes external-DNS/certification/slow/scale work, and reports `HOSTED-DIAGNOSTIC-PASSED` without ever becoming native release authority.
- Add bounded `test-diagnostic-batch` / `test-diagnostic-shard` targets and an AND-only `DIAGNOSTIC_EXTRA_MARKER` so short-lived hosted environments can make systematic progress without bypassing mandatory safety exclusions.
- Keep OpenCode, Claude Code, Codex, and Pi integration project-local: `opencode.json`, shared `.mcp.json`, and `.codex/config.toml`; host status separates registration, discovery, project trust/adapter readiness, and real-call evidence without requiring a global Hashmarks registration.
- Harden MCP calls for simultaneous host processes by boundedly retrying only known transient repository races (`BUILDING`, decision-generation changes, and files changing while hashed). Every retry recomputes from current durable state; unrelated failures still fail immediately and there is no stale-result fallback.
- Add strict host-status parsing and source/config/host-bound real-call receipts so misleading host output or stale historical evidence cannot produce a false PASS.
- Add exact-wheel real-call qualification harnesses for OpenCode, Claude Code, Codex, and Pi, while keeping those external-host/model checks outside the normal OSS test dependency surface.
- Add a bounded multi-process/live-mutation regression to the normal `make test` suite, plus a heavier `make mcp-concurrency-stress` release gate.
- Keep MCP transport errors at one boundary: `HashmarksMcpSurface` remains SDK-independent and raises `McpSurfaceError`; `mcp_server.py` translates that domain error to the SDK's `ToolError` once for every registered tool, preserving model-readable validation messages without transport-specific try/except blocks in repository methods.
- Centralize repository read serialization/retry behind one `_read()` owner on the MCP surface, preserving the existing bounded transient-race policy without duplicating lock/retry scaffolding across tools.
- Exercise the installed `hashmarks` console script in normal OSS tests against isolated temporary repositories/state, asserting the actual `doctor` and CodeMap schemas instead of weakening assertions when daemon state is absent.
- Move live OpenCode/Claude/Codex/Pi host qualification executables under `scripts/host_qualification/` so release harnesses do not leak into the product script root.
- Centralize expected CLI failure translation: repository commands delegate to one repository-CLI boundary and the top-level CLI converts caller-visible failures to process exits once, instead of repeating `try/except -> SystemExit` in leaf handlers.
- Centralize daemon and warm-CodeMap JSON request exception serialization behind one local IPC request boundary, so both services share one decode/dispatch/error policy.
- Remove a no-op catch-and-immediate-reraise block from manifest registration and add architecture tests that forbid new leaf CLI exception wrappers, no-op rethrows, and unreviewed broad `Exception`/`BaseException` catches outside explicit rollback/cleanup/provider/transport boundaries.

## HM311 — Prepublic Compatibility Debt Closure

- Remove backward-compatibility machinery from current pre-public surfaces instead of preserving historical local state or aliases. `WorkspaceMapStore` now accepts only the current generated CodeMap table shape and discards/rebuilds incompatible local SQLite state; legacy lexical conversion and `ALTER TABLE` backfills are removed.
- Collapse public Python/CodeMap naming to one current surface: `RepositoryIdentity` / `RepositoryIdentityMode`, `repository_ownership_graph()`, `repository_instruction_scope()`, and `repository_instruction_file_rows()`. Remove the historical Merkle `ignore_names` knob, deprecated helper aliases, the unused daemon-socket `state_dir` signature, and the external-qualification receipt validator shim.
- Retire development-only v1 agent trace/experiment-set readers and the compatibility-manifest helper; current evaluation consumes v2 contracts only. Rename the serialized decision evidence surface from historical `authority_receipt` / decision-authority receipt vocabulary to `evidence_receipt` / `hashmarks.decision-evidence-receipt.v1`. Current daemon protocol validation remains because rejecting mixed incompatible runtimes is a safety fence, not backward-compatibility support.

## HM310 — Filesystem Metadata Persistence Portability Closure

- Reproduce a real filesystem portability failure where valid `st_ino` and other stat-derived integers outside SQLite's signed-64 INTEGER domain raise `OverflowError` while persisting file-digest cache metadata. Repository bytes remain valid; the failure is confined to the incremental reuse cache.
- Keep ordinary signed-64 metadata in the existing INTEGER fast path and add one nullable `overflow_metadata` BLOB sidecar for rows containing any wider stat integer. Overflow rows encode all five stat integers canonically in decimal ASCII while bind-safe INTEGER placeholders prevent SQLite numeric coercion; ordinary rows pay no arbitrary-width decode cost.
- Treat the file-digest database as disposable derived cache state, not a backward-compatible persistence API: the current table shape is authoritative, incompatible cache shape is rebuilt, malformed overflow rows are evicted/rehashed, and no schema-version or migration subsystem is introduced. `executable` remains constrained INTEGER. No repository identity, freshness, query, ownership, MCP, or execution semantics change.

## HM309 — Concrete Configuration Surface Authority Closure

- Reproduce a same-locality authority collision where a real configuration surface such as `policy.toml`, `policy.yaml`, `policy.yml`, or `policy.json` is present in bounded evidence but a same-stem `policy.py` contract/source helper wins the action projection solely from retrieval score, even when the task explicitly names the concrete configuration surface.
- Within an already-active local configuration projection, prefer mechanically classified `CONFIG`/`BUILD`/`PLAN` surfaces over contract-only source rows. When multiple concrete configuration surfaces are local, require a unique existing task-specificity advantage before selecting one; otherwise preserve the prior fail-conservative fallback rather than inventing uniqueness.
- Preserve generic contract behavior and repositories with no concrete configuration surface. This checkpoint adds no instruction-prose interpretation, new authority store, planner semantics, execution behavior, or public packet schema.

## HM308 — Repository-Backed Omitted Identifier Locality Closure

- Reproduce a dense-sibling task-locality failure where explicit lowercase letter+digit identifiers such as `flare041` can be absent from normal bounded task query views, allowing generic sibling evidence to displace the requested namespace even while the decision remains marked safe.
- Recover only omitted explicit letter+digit tokens that are proven by existing indexed repository evidence. Probe deterministically in bounded groups, preserve at most two proven identifiers, and keep normal query views, ordinary retrieval limits, freshness authority, and public packet schemas unchanged.
- Permit one additional exact local component hit only for configuration/policy tasks, where characterization proved the local verification test can otherwise be the third task-local hit. Generic version/protocol-like tokens without repository evidence are ignored.
- Preserve existing ambiguity semantics: multiple proven task-local owners remain discrimination-required rather than being collapsed into false uniqueness. No planner, executor, workflow, confidence score, MCP-specific semantics, new index, or second authority is added.

## HM307 — Repository Authority Resurrection and Live Policy Drift Closure

- Independent crash/drift characterization reproduced three cold-vs-live repository-intelligence gaps: exact delete→recreate owners were not rediscovered, file→symlink→file owners were not recovered after safe symlink retirement, and an already-open CodeMap could keep using a construction-time context-policy snapshot after the policy changed.
- Preserve only stale task-local paths already exposed by canonical preflight as bounded in-memory resurrection tombstones. Absent/symlink paths remain non-authoritative and cause no repeated repository scan; exact regular-file return performs one admitted path-scoped reconciliation.
- Re-read the exact repository context-policy authority at query/sync boundaries. Semantic policy changes force one normal full reconciliation so both newly denied and newly admitted paths converge to cold-map truth; invalid live policy fails closed before persisted repository evidence is returned.
- Make `derived_graph(path)` use existing readiness and exact-path currentness authority, closing direct diagnostic leakage after unsignaled source or policy drift. No new database, watcher, polling loop, topology subsystem, confidence score, MCP semantics, or execution/agent authority is added.

## HM306 — Structured Query Freshness Projection Closure

- Independent drift characterization proved that, after an unsignaled source rewrite without an active observer, `status()` correctly reported unknown continuity while `symbol()` could still return the old persisted symbol without any freshness/currentness field.
- Propagate the existing `generation`, `identity_generation`, and tri-state `stale` authority into structured persisted-query projections including symbols, dependencies/references, project/structural views, affected/tests, repository instruction scope, and change-impact.
- Preserve `stale = null` as explicit unknown when continuity cannot be proven; do not convert unknown into fresh and do not force a full repository rescan on every query.
- Keep exact-path/source surfaces free to revalidate the requested path directly. No new index, database, daemon, score, recovery loop, or dependency analysis is added.

## HM305 — Evidence Authority Precedence Contract Closure

- Consolidate Hashmarks' existing authority rules into one explicit non-strengthening contract: downstream indexes, providers, findings, rankings, selections, summaries, and consumer projections may not silently strengthen or redefine the repository evidence they depend on.
- Keep content identity, freshness/provenance, qualified provider evidence, repository relationships, selection, and projections as distinct authority domains rather than inventing a universal confidence score or total ordering.
- Require stale/unknown/incomplete/ambiguous evidence to remain conservative unless an existing kind-specific authority rule proves a stronger state; unresolved provider disagreement stays unresolved instead of being settled by convenience.
- Keep human/model-generated interpretation and consumer outcomes outside repository authority. No runtime ranking, persistence, provider, schema, or query semantics change in this checkpoint.

## HM304 — Interrupted Query Readiness Closure

- Stress testing a real 50k-file cold sync killed after 5,024 persisted rows proved that ordinary repository-intelligence queries could read the partially materialized durable map while `sync.build_state` remained `BUILDING`. Exact early symbols were returned, late symbols were absent, and unrelated early files could fill the result set without any completeness marker.
- Normal query and direct action surfaces now fail closed with an explicit incomplete-generation error until `sync()` restores `COMPLETE`; this includes find/grep/symbol/outline/impact/findings and direct task-action use.
- Keep the full task decision packet as the explicit safety-reporting exception: it may describe an incomplete generation only to emit `codemap_complete=false`, stale/unsafe context, and `codemap-generation-incomplete` discrimination. Its preflight does not consume partial retrieval evidence.
- Preserve `status`, index preflight, and explicit `sync()` recovery while incomplete. No automatic retry/recovery, execution authority, dependency inspection, or new persistent state is added.

## HM303 — Persisted Analysis-Scope Convergence Closure

- Retire historical persisted repository rows that no longer satisfy the shared analysis-scope contract before global/store-backed queries can return them.
- Bind one lightweight conformance identity to the scope contract inputs: pruned path segments, repository context-policy fingerprint, and internal state path. Stable queries reuse that identity and do not rescan persisted paths.
- Reconcile scope once on contract/policy changes and on direct sync entry, preserving query economics while allowing pre-HM303 `.venv`, `node_modules`, or context-denied rows to converge out of the map.
- Keep the durable workspace fingerprint consistent when scope reconciliation removes rows, while preserving repository-owned lexical neighbors and all current admitted evidence.
- Add no dependency inspection, package-specific suppression, scanner, external-library roadmap, workflow, agent behavior, or execution authority.

## HM302 — Explicit Query Currentness Scope Conformance Closure

- Make `_ensure_path_current()` enforce the same shared repository-analysis admission predicate used by targeted discovery, findings, and verification planning before any digest/parse/index work occurs.
- Prevent explicit query surfaces such as `outline()` and path-qualified `source()` from reading or admitting `.venv`, `node_modules`, other pruned runtime/dependency paths, or context-policy `index = false` files merely because the caller names them directly.
- Retire historical persisted rows when an explicitly queried path is now outside admitted analysis scope, so pre-closure dependency evidence cannot remain queryable.
- Preserve segment-aware repository-owned lexical neighbors such as `src/node_modules_adapter.py` and normal explicit-currentness behavior for admitted source.
- Add no dependency inspection, package-specific suppression, new scanner, cache, index, workflow, agent behavior, or execution authority.

## HM301 — Explicit Verification Scope Conformance Closure

- Make `verification_plan()` obey the same admitted repository-analysis scope as CodeMap discovery and repository findings.
- Prevent pruned dependency/runtime paths and context-policy `index = false` paths from receiving runnable verification recommendations merely because their lexical path looks like a test.
- Centralize the existing internal/pruned/context-policy admission rule as one CodeMap path predicate reused by targeted discovery, explicit findings, and verification planning.
- Preserve verification planning for repository-owned tests and segment-aware lexical neighbors. No dependency inspection, package-specific rule, runner execution, or new state is added.

## HM300 — Findings Admission-Scope Conformance Closure

- Make explicit ownership-analysis and `map findings --path` requests obey the same admitted repository-analysis scope as CodeMap indexing.
- Prevent pruned dependency/runtime paths such as `.venv` and `node_modules` from being read directly by import/cache/findings analyzers merely because a caller supplied an explicit Python path.
- Preserve context-policy indexing denial as analysis denial for these explicit ownership surfaces, closing the same bypass for repository-declared excluded material.
- Keep path rejection segment-aware so repository-owned lexical neighbors such as `src/node_modules_adapter.py` remain analyzable.
- Add direct no-read regression proof plus unified `repository_findings` and context-policy coverage. No package-specific suppressions, dependency crawler, new analyzer, or new persistent state is added.

## HM299 — Incremental Dependency-Scope Conformance Closure

- Make targeted/incremental CodeMap discovery enforce the same segment-aware dependency/runtime prune boundary as full repository discovery.
- Prevent explicit or watcher-driven syncs beneath `.venv`, `venv`, `node_modules`, build/runtime/cache trees, and other existing prune roots from admitting dependency implementation files into repository evidence.
- Keep pruning segment-aware so repository-owned names such as `src/node_modules_adapter.py` remain valid source.
- Reuse the same prune predicate when targeted `pyproject.toml` changes refresh Python import roots, eliminating a second dependency-scope path.
- Add public CodeMap regression coverage for cold-vs-incremental equivalence and cleanup of historical rows previously admitted beneath pruned dependency roots. No new analyzer, cache, index, dependency crawler, or external-library special case is added.

## HM298 — External-Library Scope Guardrail Closure

- Make the repository/dependency analysis boundary explicit: **do not chase remaining findings in external libraries** merely to reduce finding counts.
- Define imports, references, lockfiles, package declarations, and dependency edges as bounded repository evidence that do not recursively admit external dependency implementations.
- Prohibit dependency-driven descent into virtual environments, `site-packages`, `node_modules`, package-manager caches, SDK/runtime trees, and unrelated dependency checkouts unless that source is explicitly admitted as repository-owned input.
- Preserve external packages as bounded development/qualification corpora for discovering **generic** analyzer defects, while requiring neutral regression semantics or `NO_CHANGE` instead of package-specific suppressions.
- Record the HM297 Starlette/Pydantic/pytest characterization lesson under `docs/development/reviews/` so those named observations remain historical evidence rather than active roadmap work.
- Add anti-drift documentation tests for the normative boundary, agent guidance, contributor guidance, architecture placement, and PB8/PB9 invariants. No production analyzer/runtime behavior changes.

## HM297 — Scoped/Local Concurrency Precision Closure

- Stop promoting definite function-local fresh mappings (`{}`, `dict()`, `list()`, `set()`, and comprehensions) as shared-owner read/modify/write risks while retaining parameter/aliased-owner nominations.
- Treat module-level `ContextVar` and `RunVar` owners as context/run-scoped state rather than generic durable shared owners, including subscripted constructors such as `RunVar[T](...)`.
- Preserve real positive controls: parameter-owned `store.get` → `store.set/update`, visible transaction guards, same-descriptor `os.read` → `os.write`, pytest persistent cache evidence, and import/custom-loader findings.
- Real-code characterization across HTTPX, FastAPI, Pydantic, pytest, Starlette, Uvicorn, AnyIO, HTTPCore, Click, Cryptography, and PyYAML reduces top-level findings from 21 to 8 (61.9%) without suppressing the retained positive controls.
- Incremental rename/edit acceptance proves findings move to the current path and disappear when the underlying evidence is removed; top-level finding evidence remains exact drill-down material for the dedicated analyzers.

## HM296 — Concurrency Owner-Binding Precision Closure

- Bind low-level `os.read` / `os.write` concurrency evidence to the file-descriptor argument rather than treating the `os` module namespace as the durable owner.
- Do not nominate a read/write race when a function copies from one descriptor to a different descriptor; retain nomination when the same descriptor is read then written.
- Preserve existing method-owner behavior (`store.get` → `store.set`, `path.read_text` → `path.write_text`) and `import os as ...` aliases.
- Real Oh-Goon acceptance removes only the false `source_fd` → `destination_fd` advisory while preserving both import/module-identity findings.

## HM295 — Repository Findings Projection

- Add one `hashmarks map findings` entry point that projects high-signal repository-analysis findings from existing import-identity, cache-ownership, and static concurrency analyzers.
- Keep the projection evidence-only: no new scanner, reasoning engine, remediation, execution, certification, persistent state, cache, index, or agent/orchestration authority.
- Preserve lower-signal analyzer output for dedicated drill-down commands instead of promoting every cache nomination into a top-level finding.
- Expose the same normalized `hashmarks.repository-findings.v1` projection through `CodeMap` and the warm CodeMap service.
- Validate the surface against the real Oh-Goon 1267.0.883 WIP, where one command surfaces the high-confidence duplicate-module-identity finding without manual analyzer composition.

## HM289 — Retrieval Ordering Contract Closure

- Make capped broad fallback retrieval deterministic by ordering symbol candidates by repository path, source line, and qualified name, and file candidates by repository path.
- Preserve the existing leading-wildcard LIKE recall surface and avoid adding indexes, caches, persisted state, DTOs, or execution/orchestration behavior.
- Add same-content ABA regression proof at both the direct broad-candidate surface and public `find()` surface so SQLite row history cannot change the visible capped subset.
- Treat deterministic ordering as an explicit correctness contract, not as a transparent performance optimization; retain HM286 measurement authority for any performance claim.

## HM285 — Reference-backed Test-shaped Source Ownership + Evaluation Stability

- Recover exact edit authority for a path classified as both test and source only when an existing non-test source import resolves uniquely back to that exact implementation path; filename shape alone grants no authority.
- Fail closed for unqualified plain method names when canonical evidence already contains multiple live exact source definitions, preventing lexical order from manufacturing uniqueness.
- Add a 107-case answer-blind exact-symbol corpus with wording metamorphs, path-qualified tasks, explicit false-safe/false-unique gates, and retrieval-to-action failure-stage evidence.
- Make repository-evaluation correctness runs deterministically shardable with isolated CodeMap state and strict identity-bound merge semantics.
- Separate performance profiling from correctness runs with warmups, repeated samples, median/p95/MAD, semantic fingerprints, and same-version noise-floor comparison.
- Carry forward the separately measured HM284 ownership import-path reuse and constant-time build-state existence probe; the reported-file freshness fast path remains rejected.

## HM284 — Generation-bound Ownership Import-path Reuse Closure

- Reuse exact ownership import-path resolutions only inside one explicit generation-bound `decision_session()`, keyed by generation + source path + import target; store immutable tuples and return fresh lists.
- Preserve import-resolution, visibility, repository identity, freshness, ranking, and execution authority; clear reuse at every session boundary and bypass it outside sessions.
- Replace `_sync_begin_build()`'s repository-wide `stats()["files"]` count with the already-existing constant-time `has_files()` readiness probe; no sync or freshness work is skipped.
- Reject the historical reported-file freshness fast path on this parent after remeasurement showed no end-to-end gain.

## HM283 — Exact Identifier Ownership Preservation Closure

- Prevent uniquely proven exact class/method/function ownership already present in canonical task evidence from being silently displaced by weaker structural-owner continuation.
- Fail closed when multiple active source paths expose the same exact identifier; keep generic structural ownership, literal-path authority, verification-role separation, and comment-only lexical evidence behavior unchanged.
- Add reusable `scripts/repository_evaluation/` tooling with public case manifests separated from grader expectations, exact repository/producer-bound research receipts, clean-vs-resumed timing classification, and semantic A/B comparison.
- Keep generated experiment runs, receipts, snapshots, and evidence capsules outside Git under ignored `.hashmarks/` state or external durable archives.
- Document the stale-reconciliation handoff from `indexing_lifecycle._sync_remove_stale_paths` to the segment-safe `repository_index_store.paths_under()` query primitive.

## HM282 - Indexed persisted-prefix reconciliation closure

- Replace repeated `file_map.path LIKE 'prefix/%'` descendant scans with an exact-path plus primary-key range query over normalized `/`-separated repository paths.
- Preserve exact/descendant stale-removal semantics while making large incremental path batches scale with the requested ranges instead of rescanning the full persisted path map per prefix.
- Add segment-boundary regression coverage proving `src` cannot capture lexical neighbors such as `src0` or `src2`, including Unicode descendant paths.

## HM280 - Generation-bound change-impact owner-chain reuse closure

- Reuse only the exact owner-chain derivation shared by repeated `task_change_impact()` compositions inside one explicit decision session.
- Key reuse by repository generation, task, and the exact task-action `limit`/`per_role` bounds; clear it at session boundaries and deep-copy cached values.
- Preserve `task_change_impact()` currentness authority: every call still runs its bounded path sync and declared-project freshness refresh before consulting owner-chain reuse.
- Add diagnostics hit/miss counters and regression coverage for sync preservation, exact-bound misses, mutation isolation, and cross-session recomputation.

## HM277 - Generation-bound snapshot composition reuse closure

- reuse one exact repository-intelligence snapshot across profile, economics, delta, and repeated snapshot surfaces inside one explicit generation-bound decision session;
- key reuse by CodeMap generation, task, exact changed-path sequence, and all snapshot bounds, with no cross-session or persistent cache;
- deep-copy cached snapshots on reuse so caller mutation cannot become shared evidence authority;
- preserve byte-identical snapshot/profile/economics/delta outputs while eliminating repeated higher-level snapshot composition.

## HM276 - Discovery metadata reuse closure

- carry each admitted file's discovery-time size in an immutable internal discovery record;
- make index preflight consume that already-observed size instead of re-statting every discovered file;
- preserve later digest/unstable-file freshness checks and add regression coverage proving preflight performs no filesystem stat calls;
- document the discovery → preflight metadata ownership boundary for maintainers.

## HM275 - Incremental stale-prefix and maintainer documentation closure

- collapse duplicate/descendant requested prefixes for incremental stale-row reconciliation and use sorted range entry rather than rescanning the whole discovered set per prefix;
- add regression coverage for segment-safe prefix collapse, exact stale-row equivalence, and overlapping incremental requests;
- add the current `docs/maintainers/` lane with a CodeMap responsibility map and common request traces so implementation navigation is not inferred from mixin order or historical handoffs;
- keep `docs/development/` explicitly historical/non-normative.

## HM274 - Ownership composition reuse closure

- reuse one request-local repository-row snapshot across composed ownership analyses instead of repeatedly materializing `all_file_rows()`;
- reuse import/cache producer evidence only when argument scope is identical, preserving repository-wide cache-owner resolution for scoped invalidation requests;
- keep reuse local to one ownership composition request with no persistent cache, freshness authority, schema, protocol, or product-surface changes;
- add regression coverage proving a composed ownership graph materializes repository rows once while retaining scoped evidence behavior.

## HM273 - Import resolution responsibility closure

- extract repository import/re-export identity resolution from `evidence_graph.py` into dedicated `import_resolution.py` ownership;
- keep `ownership_graph.py` as a consumer of resolved import identity rather than merging producer and ownership-ranking authority;
- keep dynamic-loader ownership diagnostics in `import_ownership.py` separate because they diagnose `sys.modules` bypass patterns rather than resolve repository import identity;
- add a responsibility boundary test preventing resolver ownership from drifting back into graph traversal or ownership ranking.

## HM272 - Evidence freshness responsibility closure

- extract evidence snapshot/manifest freshness and freshness-status semantics from `evidence_graph.py` into dedicated `evidence_freshness.py` ownership;
- keep import/re-export resolution, graph traversal, SCIP import, and project enrichment semantics unchanged;
- add a responsibility boundary test preventing freshness ownership from drifting back into graph traversal.

## HM271 — Configuration Evidence Responsibility Closure

- Extract task-local TOML/JSON/YAML evidence projection from `evidence_packet.py` into the dedicated `ConfigurationEvidenceMixin` owner.
- Preserve the existing fail-closed config evidence contract and packet output unchanged; this is a responsibility consolidation, not a feature.
- Add a boundary test ensuring config parser/scorer methods cannot drift back into packet assembly ownership.


Hashmarks follows a public `0.x` contract: user-visible changes are recorded here, while detailed engineering history remains under `docs/development/` in the full source repository and is intentionally not shipped in the PyPI sdist.

## 0.14.0 — Repository-scope authority and precision closure

### Repository-analysis scope

- Make repository-owned material the default analysis authority across cold discovery, incremental/targeted sync, explicit findings, explicit query currentness, verification planning, and persisted query state.
- Treat imports, package declarations, lockfiles, and dependency references as bounded repository evidence rather than permission to recursively inspect dependency implementations.
- Exclude pruned dependency/runtime trees such as `.venv` and `node_modules` consistently across discovery and explicit-path surfaces while preserving segment-safe repository-owned lexical neighbors.
- Reconcile historical persisted rows against the current analysis-scope contract so stale out-of-scope evidence cannot survive upgrades or context-policy changes.

### Findings and ownership precision

- Reduce concurrency-risk over-nomination by distinguishing definitely fresh function-local owners and scoped state owners from shared mutable state without package-specific suppression.
- Preserve conservative ambiguity for caller-derived or otherwise unresolved owners rather than reducing finding counts by special-casing third-party libraries.
- Strengthen exact identifier ownership, import/re-export identity, test-shaped source ownership, and generation-bound composition reuse while retaining fail-closed uniqueness semantics.

### Evidence economics and durability

- Reuse repository-intelligence snapshots, ownership/import resolutions, task action composition, and owner-chain derivations only inside explicit generation-bound decision sessions.
- Add durable measurement/evaluation receipts and repository-analysis findings surfaces without turning Hashmarks into an agent harness, execution engine, or workflow orchestrator.
- Keep persisted freshness, provenance, repository identity, verification relevance, and analysis-scope reconciliation bound to authoritative repository generations.

### Product boundary

- Explicitly freeze the rule: **do not chase remaining findings in external libraries**. External code may be used as bounded development/qualification corpora only to expose generic Hashmarks defects that can be reduced to neutral repository-analysis semantics and regression fixtures.
- Keep reasoning, planning, editing, tool execution, recovery, git/worktree lifecycle, model routing, and orchestration outside Hashmarks.

## 0.13.0 — Initial public release

- Developer dependency locks are local gitignored uv state; release source identity is not coupled to `uv.lock`.
- The stdlib build backend propagates owner-supplied PEP 639 license metadata/license files and `[project.urls]` into wheel/sdist publication metadata.

### Repository intelligence

- Added a compact, identity-bound change-intelligence brief for explicit change sets, projecting changed revisions/symbols, bounded impact, ownership, verification relevance, freshness, and cross-project provenance without execution authority.
- Added deterministic verification-selection explanations and bounded non-selection (`why_not`) evidence using stable producer reason classes rather than generated prose.
- Added a derived Evidence Freshness Map that reuses existing generation/revision/provenance authority to report current, invalidated, unknown, and dependency-bound repository evidence without creating a second freshness store.
- Added a semantic Repository Delta Intelligence projection between admitted change-intelligence generations, emitting only changed repository facts while preserving exact producer identities and adding no historical state store.
- Added compact, standard, and audit evidence profiles as deterministic density projections over one authoritative repository-intelligence snapshot identity; profiles are derived-only and add no duplicate repository truth.
- Added a bounded cross-repository evidence packet that composes admitted project-impact provenance, affected ownership/verification relevance, dependency freshness, and explicit unresolved evidence without cloning, orchestration, or execution authority.
- Added a thin Repository Intelligence Query Surface that consolidates F1–F6 access behind one deterministic facade while delegating unchanged producer semantics and adding no duplicate repository truth.
- Added a deterministic Intelligence Economics Receipt that measures serialized profile/delta evidence economics and bounded evidence coverage from Hashmarks-owned producer facts only; it explicitly excludes agent runtime, model-token, tool-call, execution, billing, scheduling, retry, and certification authority.
- Consolidated the CodeMap service protocol so F1–F8 repository-intelligence products are remotely exposed only through the Repository Intelligence Query Surface; direct `CodeMap` producer methods remain authoritative local composition surfaces.
- Renamed the older wall-time/cache query measurement helper to repository query runtime diagnostics, keeping diagnostic runtime measurements semantically separate from the deterministic Intelligence Economics Receipt.
- Canonical file, directory, manifest, snapshot, and repository identities.
- Incremental `CodeMap` for repository paths, symbols, imports, references, calls, projects, tests, ownership, and reverse impact.
- Bounded orientation, outline, task retrieval, exact source, dependency/reference, affected-path, and verification-relevance views.
- Generation-bound freshness, observation, invalidation, and fail-closed reconciliation semantics.
- Content-addressed structural artifact reuse across compatible Git worktrees while mutable workspace state remains isolated.
- Strict producer/consumer evidence contracts, provenance, conformance, and qualification receipts.

### Public-contract cleanup before publication

- Removed unpublished agent-loop, failed-attempt/recovery/session, generic work-execution, execution-result-cache, and execution-step identity surfaces from the installed product contract.
- Moved external-agent evaluation harnesses and retained corpora to development/benchmark infrastructure rather than installed APIs.
- Defined explicit product-boundary, API-stability, tool-compatibility, and GitHub contribution contracts.
- Added deterministic package builds, installed wheel/sdist smoke qualification, and CI compatibility matrices.

### Release notes

- Python `>=3.11` is supported by the package metadata; CI is intended to qualify Python 3.11–3.14 on Linux.
- Qualification tooling uses minimum-supported versions rather than narrow patch/minor pins: pytest `>=8.4`, Ruff `>=0.12`, and uv `>=0.10.0`; newer versions are accepted unless qualification proves a concrete incompatibility. See [`docs/qualification/TOOL_COMPATIBILITY.md`](docs/qualification/TOOL_COMPATIBILITY.md).
- The software license and final repository URLs are release-owner decisions and are intentionally not invented by the build metadata.

- Development performance/maintainability: incremental stale-row reconciliation now collapses redundant requested prefixes and uses binary-search entry into sorted discovered paths instead of rescanning every discovered path for every request prefix. Added a CodeMap maintainer guide that maps implementation ownership and common request flows for developers who already understand the product boundary but not the internal mixin/module topology.

## HM278 - Generation-bound task-action composition reuse

- Reuse exact `task_action_map(task, limit, per_role)` projections only inside one explicit generation-bound `decision_session()`.
- Cache identity includes generation, task, limit, and per-role bounds; entries are cleared at session start/end and deep-copied across the cache boundary.
- Preserve existing authority/freshness side effects on the first computation in each session; no persistent/global cache, schema, service, or ranking change.
- Add focused regression coverage for exact-key reuse, bound misses, mutation isolation, and cross-session recomputation.

## HM279 - Decision-session composition diagnostics

- Add opt-in `CodeMap.decision_session(diagnostics=True)` runtime diagnostics for high-level repository-intelligence composition.
- The bounded `hashmarks.decision-session-diagnostics.v1` receipt reports producer call hierarchy, inclusive/exclusive time, semantic request identities, duplicate calls, existing cache hit/miss counters, and store-read counters.
- Diagnostics are request-local, derived, non-persisted, capped at 256 spans, and have no repository-evidence or execution authority.
- No OpenTelemetry/exporter/persistent metrics ownership is introduced; ordinary sessions remain uninstrumented.

## HM280 - Generation-bound change-impact owner-chain reuse

- Reuse only the expensive `_change_impact_owner_chain()` derivation inside one explicit decision session.
- Preserve `task_change_impact()` path sync and declared-project freshness refresh on every call; reuse never becomes freshness authority.
- Key reuse by generation, task, and task-action bounds, deep-copy cache values, and keep all reuse process-local/disposable.

## HM281 - Producer implementation provenance inspector

- Add a non-authoritative `producer_implementation_provenance()` projection over the exact package inputs already used by producer implementation identity.
- Expose only package-relative Python paths, byte counts, and SHA-256 content digests so same-version byte drift and same-content renames are diagnosable without exposing source bytes or host-private paths.
- Keep producer implementation identity producer-owned and opaque; the provenance projection is derived diagnostics, not a second identity authority or consumer-side canonicalization contract.

## Unreleased

### Launch discovery and public README closure

- Rework the README first screen around the product users actually search for: local repository intelligence, a read-only MCP server for coding agents, codebase search, code navigation, ownership, change impact analysis, freshness, and verification evidence.
- Move maintainer-only MCP qualification detail out of the launch path and link to the dedicated MCP integration guide instead.
- Add copy-ready project-local setup examples for Claude Code, Codex, OpenCode, and Pi, explicitly showing that the configuration belongs in the target repository and that the host launches the stdio server.
- Align PyPI description/keywords and search-facing documentation titles with the same canonical product language without competitor comparisons or keyword stuffing.
- Keep public repository URLs unset until the final GitHub location exists; launch metadata must never invent canonical links.


- Remove stale pre-license README guidance so the public release surface consistently identifies Apache-2.0 before release promotion. Add regression coverage preventing the contradictory pre-license wording from returning.
- Add an optional local stdio MCP adapter (`hashmarks[mcp]`, `hashmarks --workspace . mcp`) with five bounded read-only repository-intelligence tools. MCP remains a transport projection over existing CodeMap evidence and serializes refresh/read access so incomplete BUILDING generations are never exposed to clients.
- License Hashmarks under Apache License 2.0 and project the SPDX/license file into package metadata.
