# Changelog

## 0.18.0 — Locked qualification authority and documentation cleanup

- Make the committed `uv.lock` the exact repository development/qualification resolution authority while `pyproject.toml` remains dependency-intent authority; normal setup, CI, MCP development registrations, pre-commit, and release qualification consume the lock with frozen uv operations.
- Bind release qualification provenance directly to the exact `uv.lock` bytes and remove the old gitignored/local-lock compatibility model rather than preserving a parallel dependency representation.
- Remove internal HM phase chronology, handoffs, historical receipts, superseded plans, and pre-public agent-loop archaeology from the maintained documentation tree; Git and merged pull requests remain the historical record.
- Remove committed copies of generated agent-evaluation fixtures/results and the phase-era HM285 measurement-authority checklist; canonical synthetic fixtures now have one owner in evaluation code and are materialized per run, while semantic tests protect behavior and Git/PR history preserves old snapshots.
- Make evaluation protocol/fixture family identifiers semantic and package-version-neutral instead of embedding obsolete `v0.10.x` release numbers in current benchmark identities.
- Remove remaining RCR/guardrail chronology, closed refactor receipts, and obsolete pre-public/v0.11 compatibility wording from maintained contributor policy while preserving the current responsibility-first and authority-boundary rules.
- Remove remaining unpublished/pre-public anecdotes and standalone historical-evidence appendices from current API/integration/invariant/onboarding docs; current semantic contracts stay explicit while Git/release history remains the archaeology source.
- Replace transitional migration/containment policy with a current boundary-violation rule: out-of-profile surfaces are defects to reject, split, narrow, or remove rather than responsibilities to preserve.
- Repair the final dangling repository-local documentation link left by the hard docs cleanup and add a regression that requires live Markdown link targets to exist.
- Make `docs/README.md` the single complete catalog for the live documentation tree, remove the redundant nested maintainer index, and require every maintained docs page to be indexed exactly once.
- Replace the internal-agent oracle-separation source-text preservation test with behavioral proof that the worker ledger rejects secret input and the grader refuses unsealed traces before producing oracle-derived results.
- Replace the refactoring-policy archaeology blacklist with positive regression proof for the current measured-product-value, no-parallel-phase-history, single-spelling, and responsibility-decision contract.
- Mark every documented Make command as a phony command target; four evaluation targets could previously be shadowed by same-named filesystem entries, and a derived regression now keeps documented commands both defined and phony.
- Replace the broad-search SQL source-text preservation test with direct `search_candidates` behavior proof for name/signature/path recall, deterministic ordering, and repeatability without freezing a specific SQL implementation.
- Finish the hard test cleanup by replacing CLI delegation source-text assertions with parser/execution behavior proof, relying on the existing MCP server/surface error-boundary regression instead of transport-SDK substring checks, and removing regressions whose only purpose was to preserve the absence of already-deleted compatibility/history artifacts.
- Consolidate the ownership-intelligence adversarial regression corpus into one canonical test module and remove the phase-numbered phase2/phase3 files without dropping any of their 13 scenarios.
- Keep only current product/reference, integration, maintainer, and qualification documentation in the live tree, and keep the changelog limited to public release history.

## 0.17.0 — External evidence correlation and real-data qualification

- Add a bounded producer-side Splunk CSV dogfood adapter under evaluation tooling, preserving exact source identity, parser health, multiline records, traceback path/line/symbol evidence, repeated-event identity, bounded aggregation, and explicit completeness/truncation without turning Hashmarks into a log-ingestion platform.
- Harden external-evidence correlation so bundle/anchor container order is presentation-only: anchors are canonically ordered by `anchor_id`, while any semantically meaningful producer ordering must be carried explicitly in metadata or provenance.
- Preserve and correlate recovered runtime traceback evidence through explicit path mappings, while keeping interpretation and causation external to Hashmarks.
- Restore the native-vs-Hashmarks context-economics JSON-to-CSV projection on current main with stricter input-schema validation, duplicate identity rejection, explicit UTF-8 handling, and output digests.
- Qualify the release against the retained masked Splunk export and keep the resulting dogfood evidence and focused regressions in-repository without committing the masked payload itself.

## 0.16.0 — Authority non-interference and evidence qualification

- Separate repository authority proof from bounded retrieval and presentation so limits, candidate truncation, compact projections, persistent reopen, and MCP projection cannot manufacture or erase ownership authority.
- Preserve caller-reported changed evidence explicitly, including missing or excluded paths, and extend canonical source evidence coverage to CSS, SCSS, Sass, and Less.
- Separate finding observations from interpretation and counter-evidence so contradictory evidence can change actionability without erasing the underlying observation.
- Continue release qualification with fresh downstream Oh-Goon dogfood, mutation/adversarial proof, ranking/retention measurement, and economics before final 0.16.0 closure.

## 0.15.0 — Repository authority and agent evidence closure

- Add public repository evidence bindings for opaque consumer IDs over exact physical line ranges and whole repository members, with stable definition/observation identities, declared dependency and relationship evidence, binding deltas, per-binding change coverage, explicit bounds, context-policy isolation, and fail-closed stable-read/member-revision checks. These remain repository intelligence only; consumer execution/certification policy stays external.
- Normalize the serialized freshness state axis to `current | stale | unknown` across current pre-1.0 evidence projections. Proof strength such as `proven` is kept separate from freshness state, and `invalidated` remains a delta consequence rather than a second freshness spelling.
- Add a canonical semantic-owner/state reference plus CI architecture guards so new CodeMap mixins, member-observation semantics, and freshness/delta projections cannot silently create undocumented parallel owners.
- Split CI into independent cheap/static, workspace-authority, and evidence-binding diagnostics while allowing full matrices to continue after unrelated diagnostic failures; add one final qualification-convergence gate and cancel stale PR runs instead of duplicating push+PR work.

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
- Qualification tooling uses minimum-supported versions rather than narrow patch/minor pins: pytest `>=8.4`, Ruff `>=0.12`, and uv `>=0.10.0`; newer versions are accepted unless qualification proves a concrete incompatibility.
- The software license and final repository URLs are release-owner decisions and are intentionally not invented by the build metadata.

- Development performance/maintainability: incremental stale-row reconciliation now collapses redundant requested prefixes and uses binary-search entry into sorted discovered paths instead of rescanning every discovered path for every request prefix. Added a CodeMap maintainer guide that maps implementation ownership and common request flows for developers who already understand the product boundary but not the internal mixin/module topology.
