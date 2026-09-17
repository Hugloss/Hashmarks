# MUST-STEAL / impact status — 0.10.18

## Proven fast/safe core

- [x] content-addressed SHA-256 file identity
- [x] real-directory Merkle identity
- [x] incremental synthetic Merkle trie for explicit manifests
- [x] persistent file digest reuse
- [x] batched SQLite reads/writes
- [x] dirty-path invalidation
- [x] equality cutoff
- [x] long-lived daemon continuity
- [x] native Linux/WSL inotify watcher
- [x] `UNKNOWN` safe fallback
- [x] generation-bound reconciliation
- [x] stable-read TOCTOU protection
- [x] WSL-safe, length-bounded runtime socket placement
- [x] request-time native inotify barrier
- [x] CAS + action cache safety
- [x] strong verification with identical canonical identity

## Developer-flexibility closure in 0.4.0

- [x] small public `Identity` façade
- [x] `auto` / `local` / `daemon` modes
- [x] safe local fallback instead of daemon-required CLI
- [x] explicit local observer modes: reconcile / watcher / manual
- [x] typed `File`, `Directory`, `Glob` input specs
- [x] `Snapshot` + `Snapshot.diff()`
- [x] `StepSnapshot` + component-level cache-key diff
- [x] schema/version metadata
- [x] stats/counters
- [x] doctor command
- [x] registered huge-manifest handle protocol with bounded chunk upload
- [x] automatic registered-manifest reuse from `Identity.snapshot_manifest()`
- [x] pluggable CAS/action-cache Protocol boundaries
- [x] daemon benchmark supports `--manifest files`
- [x] existing-repository benchmark harness

## Deliberately deferred until adoption demands it

- [ ] Git change-journal restart accelerator
- [ ] persistent OS journal across daemon restarts
- [ ] multi-workspace daemon
- [ ] native macOS/Windows watcher implementations (portable watcher remains available)
- [ ] REAPI protobuf encoder/backend
- [ ] remote CAS/action-cache implementations
- [ ] `.hashmarksignore` / Gitignore-compatible parser
- [ ] automatic bounded cache GC policy
- [ ] alternative digest algorithms

These are no longer performance blockers. They should earn their complexity through a concrete integration or benchmark requirement.


## Generic Impact foundation in 0.5.0

- [x] generic `WorkUnit` / `WorkIdentity` model
- [x] `AFFECTED` / `VERIFIED_UNAFFECTED` / `UNKNOWN` decision contract
- [x] previous PASS is the only reusable result status
- [x] complete-vs-partial evidence is explicit and enforced
- [x] workspace-scoped persistent impact-result store
- [x] generic transitive `DependencyGraph` with explanation paths
- [x] universal TOML declared-input adapter for any repo/tool
- [x] generic observed/native dependency JSON interchange format
- [x] conservative Python static-import adapter
- [x] conservative Node/JS/TS relative-import adapter
- [x] adapter discovery prunes `.venv`, `node_modules`, caches and build outputs before traversal
- [x] `hashmarks impact detect`
- [x] `hashmarks impact assess`
- [x] `hashmarks impact record`
- [x] `hashmarks impact run` executes only AFFECTED + UNKNOWN work and persists PASS identities
- [x] `Identity.impact_engine()` / `Identity.impact()` public integration

## Next impact adapters / evidence sources

- [x] Coverage JSON-context observed-dependency bridge (pytest-testmon direct bridge remains below)
- [x] Vitest native test-file discovery (`vitest list --filesOnly`); module-graph/related-test bridge remains below
- [x] Nx native project/test bridge
- [x] Pants native target/test bridge
- [x] Go `go list` package/test bridge
- [x] Rust Cargo metadata/test-target bridge
- [x] C/C++ compiler depfile bridge (partial evidence)
- [x] Maven/Gradle module/project + test-task bridge
- [x] declared cross-ecosystem project links / shared-input composition
- [ ] richer result-cache metadata and reusable output/result attachments

These should use native ecosystem authorities where available instead of duplicating their resolver semantics inside Hashmarks.


## Native evidence + developer bootstrap in 0.6.0

- [x] thin `make bootstrap` over locked/offline uv
- [x] `make start` / `make stop` / `make doctor` convenience targets
- [x] quick reproducible `make metrics` baseline
- [x] timestamped + `latest.json` metrics artifacts under excluded state
- [x] explicit 100k and 500k metrics targets
- [x] real-repository + directory/files + daemon + Impact timing bundle
- [x] repository-local pytest native test discovery when available
- [x] repository-local Vitest `list --filesOnly` discovery when available
- [x] Coverage.py JSON-context observed dependency adapter
- [x] native discovery remains partial unless completeness is explicitly asserted

## Still next for Impact precision

- [x] pytest-testmon positive-only selector through public CLI; private `.testmondata` is never parsed
- [x] Vitest/Vite native static-module selector + CodeMap file-edge producer; remains positive-only/partial
- [x] Nx native project/test bridge
- [x] Pants native target/test bridge
- [x] Go `go list` package/test bridge
- [x] Rust Cargo metadata/test-target bridge
- [x] C/C++ compiler depfile bridge (partial evidence)
- [x] Maven/Gradle module/project + test-task bridge
- [x] declared cross-ecosystem project links / shared-input composition

The preferred pattern remains: use native ecosystem authorities to produce evidence; do not clone their resolvers inside Hashmarks.

## Impact authority closure in 0.6.1

- [x] declared work defaults to partial evidence
- [x] `complete=true` is an explicit assertion rather than implicit authority
- [x] separate `ImpactTrustPolicy` owns skip authority
- [x] declared config requires explicit runner `--trust-declared-config`
- [x] generic observed JSON is not trust-eligible by default
- [x] trusted producer name cannot be spoofed through repo JSON alone
- [x] trusted native integrations require both a trust-eligible channel and producer allowlist
- [x] complete evidence with zero inputs is rejected
- [x] missing command / working directory / OS spawn failure records `ERROR`
- [x] no-work discovery emits an explicit warning

This closes the remaining P0 reuse-authority ambiguity. Future adapters may improve precision, but they must enter through the same policy boundary.


## Execution & result authority closure in 0.6.2

- [x] daemon protocol bumped for incompatible safety semantics
- [x] daemon status advertises semantics + mandatory capabilities
- [x] auto mode rejects incompatible daemon hot state and safely falls back local
- [x] exact resolved command executable is fingerprinted into WorkIdentity
- [x] shebang interpreter bytes are fingerprinted when available
- [x] impact execution uses the same resolved executable authority that was assessed
- [x] dependency completeness and execution/toolchain completeness are separate trusted claims
- [x] post-run WorkIdentity verification before PASS promotion
- [x] mid-run input/tool change produces stale result instead of reusable PASS
- [x] explicit validation / artifact / never reuse policies
- [x] artifact PASS stores output identity and reruns on missing/changed outputs
- [x] strict observed-evidence boolean parsing (`"false"` cannot become true)
- [x] duplicate adapter evidence is merged conservatively instead of first-one-wins
- [x] native pytest/Vitest discovery command authority is reused for execution where available
- [x] registered manifest handles are ref-counted and bounded
- [x] manifest registration is byte-bounded as well as path-count-bounded
- [x] `hashmarks version` / `__version__` integration surface
- [x] auto-discovered repo commands require separate execution permission
- [x] stdlib build backend now produces both wheel and sdist offline
- [x] wheel/sdist install validated with isolated offline uv

After this closure, foundation correctness work should stop unless a concrete integration reproduces a new invalid reuse. The next work should be ecosystem adapters and Oh-Goon integration.


## CodeMap / agent-efficiency foundation in 0.7.0

- [x] hard import/performance firewall: Identity never imports CodeMap
- [x] separate `.hashmarks/codemap.sqlite3` workspace graph state
- [x] content-addressed parsed-artifact cache keyed by file digest + parser/version + language
- [x] Git-worktree artifact reuse without sharing workspace graph authority
- [x] Python stdlib-AST symbols, signatures, ranges, imports and static call evidence
- [x] advisory JS/TS, Go and Rust outlines/import evidence with lexical provenance
- [x] path-only + lexical indexing fallback for additional common source languages
- [x] persistent lexical grep accelerator that rereads candidate lines before disclosure
- [x] `orient`, `find`, `grep`, `outline`, `symbol`, `deps`, `refs`, `affected`, `tests`, `source`, `context`
- [x] progressive L0/L1/L2/L3 disclosure and explicit source token budgets
- [x] context abstention on insufficient retrieval confidence
- [x] token-cost metadata for files, outlines, signatures and symbol bodies
- [x] task-conditioned lexical ranking plus bounded graph-neighbor expansion
- [x] reverse static dependency graph for related/affected tests
- [x] separate CodeMap watcher with changed-path/subtree incremental reindexing
- [x] CodeMap watcher continuity/heartbeat independent of Identity daemon
- [x] daemon observer-barrier sampling for generation-bound CodeMap reconciliation
- [x] source symlink non-following / file-to-symlink removal safety
- [x] separate index-vs-agent visibility policy with default secret-like path denial
- [x] outline-only policy cannot disclose source bodies or lexical grep matches
- [x] explicit workspace/shared CodeMap cleanup
- [x] synthetic agent-efficiency metrics: cold/hot sync, one-file reindex, find/context latency, target recall and estimated context ratio

### Next CodeMap precision work (not hot-path blockers)

- [x] optional Tree-sitter range provider for robust polyglot symbol/body ranges
- [x] SCIP import adapter for native definitions/references across languages
- [x] native TypeScript compiler resolver for tsconfig-aware file edges (full Vite graph remains below)
- [x] Pyright Type Server native Python import resolver (SCIP remains preferred for richer references)
- [x] project/package graph adapters for npm/Nx/Pants/Go/Cargo/Maven/Gradle
- [x] optional ast-grep structural-search adapter with Hashmarks disclosure policy
- [ ] persistent indexed-search backend evaluation (simple local index vs Zoekt-like design) only if current lexical index benchmarks justify it
- [x] retained real-agent localization corpus tracking first-hit, file/symbol recall, fallback search and context budget
- [ ] optional semantic embeddings/summaries only after deterministic retrieval metrics establish need

CodeMap should become more precise by adding evidence providers, not by moving parsing into the Identity lane.


## CodeMap precision providers in 0.8.0

- [x] optional Tree-sitter range enrichment without adding a hot/runtime dependency
- [x] SCIP definitions/references import through official JSON boundary
- [x] repository-local TypeScript compiler resolution including tsconfig aliases
- [x] optional ast-grep structural search with agent-content policy enforcement
- [x] explicit `map enrich` boundary; native build tools never run on Identity or ordinary map sync
- [x] Nx native project graph + conservative test WorkUnits
- [x] Pants native target graph + conservative test WorkUnits
- [x] npm workspace/package graph
- [x] Go package graph + test-package WorkUnits
- [x] Cargo workspace/crate graph + test WorkUnits
- [x] Maven reactor/module graph + test WorkUnits
- [x] Gradle one-shot native project/dependency/task report + test WorkUnits
- [x] compiler depfile Impact bridge, intentionally partial
- [x] native evidence freshness snapshots; stale SCIP/TS/project evidence is ignored
- [x] outline/signature-first context packing before implementation bodies
- [x] retained real-task retrieval gate: 100% file/symbol recall and 0% fallback search on the current six-task corpus
- [x] rejected request-time whole-repo PageRank after measured latency regression; cheap local graph expansion retained

### Still deliberately open

- [ ] direct pytest-testmon bridge through a stable/exported evidence boundary
- [ ] full Vitest/Vite module/runtime-dependency producer beyond TypeScript resolution
- [x] Pyright Type Server import resolver via published TSP; SCIP remains preferred for definitions/references
- [x] declared cross-ecosystem project links / shared-input composition across provider graphs
- [ ] persistent Zoekt-like indexed-search evaluation only if current lexical index becomes the bottleneck
- [ ] semantic embeddings/summaries only after deterministic retrieval metrics justify them

These are precision/adoption phases, not Identity hot-path blockers.


## Native selection + Python precision in 0.9.0

- [x] selection is a separate positive-only authority from Impact reuse decisions
- [x] pytest-testmon selection through its public CLI; private `.testmondata` schema remains untouched
- [x] Vitest/Vite static module graph selector without running tests
- [x] Vite-resolved file edges can enrich CodeMap and are generation-bound
- [x] explicit `.hashmarks-project-links.toml` composes backend/frontend/shared-contract graphs
- [x] Pyright Type Server resolver through published JSON-RPC/LSP/TSP boundary
- [x] TSP `0.4.x` compatibility check and snapshot-bound `resolveImport` requests
- [x] stale TSP snapshots retry once on `ServerCancelled` (`-32802`)
- [x] Pyright resolutions outside the workspace are rejected
- [x] server→client LSP requests receive minimal read-only replies so TSP sessions cannot deadlock
- [x] Pyright native edges are CodeMap-generation/config-manifest freshness-bound
- [x] retained agent corpus expanded to 19 localization tasks
- [x] current retained gate: 100% expected-file recall, 100% expected-symbol recall, 0% fallback search under 1,200-token budget
- [x] stronger global test-file demotion was measured and rejected because it reduced recall / reintroduced fallback search

### Still deliberately open after 0.9.0

- [ ] complete pytest-testmon/coverage dependency export only if a stable public evidence boundary is available
- [ ] richer Python symbol/reference provider only if SCIP/LSP evidence measurably improves the agent corpus
- [ ] larger cross-repository agent benchmark with real coding success and actual model-token accounting
- [ ] persistent Zoekt-like search only if the current lexical index becomes a measured bottleneck
- [ ] semantic embeddings/summaries only after deterministic retrieval stops meeting recall/budget targets

Identity remains frozen: none of these providers may be imported or executed by the Identity hot path.


## Multi-repository agent evaluation closure in 0.10.0

- [x] retained localization gate expanded beyond self-retrieval to Hashmarks + real Oh-Goon
- [x] 39-task strict suite: 100% expected-file recall, 100% expected-symbol recall, 0% fallback search
- [x] query-latency measurements and release thresholds added to the multi-repo suite
- [x] duplicate `(path, qualname)` parser candidates are canonicalized before SQLite persistence
- [x] small control files (`Makefile`, project manifests/config) are searchable without indexing noisy lockfiles
- [x] lexical token index narrows symbol/file candidates before ranking
- [x] identifier splitting supports snake_case/CamelCase query terms
- [x] caller expansion uses an indexed short-target field instead of repeated global suffix scans
- [x] request scoring tokenizes the task once rather than once per candidate
- [x] JS/TS `const` bindings are included in advisory structural maps
- [x] file-level lexical coverage lets symbol-less control files compete in ranking
- [x] `find` reserves bounded path diversity so one file cannot crowd out another required file
- [x] backward-compatible `hashmarks.agent-trace.v1` plus hardened `hashmarks.agent-trace.v2` experiment identity, exact-token provenance, and independent `hashmarks.agent-verdict.v1` grading
- [x] strict token-accounting authority moved out of the trace into independent `hashmarks.agent-model-usage.v1` provider evidence; self-reported trace token counts are advisory only
- [x] `hashmarks.agent-experiment-set.v1` byte-binds multiple experiments, rejects identity/evidence reuse, aggregates exact provider tokens, and separates controlled-result eligibility from fixed-floor broad/public breadth eligibility
- [x] canonical `hashmarks.agent-experiment.v1` manifest closes experiment completeness/identity authority, exact graded-subject SHA-256 binding, raw grader/provider evidence digest binding, and path confinement
- [x] source-estimated token reduction remains advisory; correctness/patch success stays a separate gate

### Still deliberately open after 0.10.11

- [ ] collect paired real Codex/Pi baseline-vs-Hashmarks traces with exact model-input tokens
- [ ] collect enough genuine external experiments to satisfy the fixed 3-experiment / 3-repository / 30-unique-task broad-claim breadth gate; eligibility still does not imply statistical significance
- [ ] persistent Zoekt-like backend only if larger repos make the current local indexes a measured bottleneck
- [ ] semantic embeddings/summaries only if deterministic map/search cannot maintain recall under budget
- [ ] broader external corpora/repositories beyond the current Hashmarks + Oh-Goon gate

Identity remains frozen: v0.10 retrieval/index changes stay entirely in CodeMap/benchmark lanes.

- [x] replication/statistical authority separates repeated-run variance from corpus breadth and labels bootstrap intervals as exact-set descriptive evidence only

- [x] real-agent retrieval-regret observatory: independent required-evidence authority, first-evidence delay, duplicate search/read waste, irrelevant-read token waste, no ranking change

- [x] Salsa/DICE-style derived intelligence graph with semantic-value identities separated from consumed input identities; no retrieval-semantic change

- [x] Salsa/DICE-style semantic invalidation shields: unchanged derived value stops propagation, while source-line storage still refreshes

- [x] Zoekt-style worktree/base reuse: exact Git-tree base snapshot + local dirty overlay, shared content-addressed artifacts, fail-closed overlay proof

- [x] typed deterministic query intent routing prunes unnecessary search expansion while ambiguous queries retain hybrid recall


## Progressive context / dynamic disclosure closure in 0.10.12
- [x] explicit `orient -> outline -> evidence -> source` context protocol
- [x] every level projects the same find result / CodeMap generation rather than creating parallel truth
- [x] lower three levels mechanically cannot read source bodies
- [x] source remains visibility-checked and token-budgeted
- [x] response advertises the next disclosure level for deterministic escalation
- [x] legacy `context()` callers retain source-level behavior by default
- [ ] use real agent traces to learn when escalation was unnecessary before changing the default agent policy


## Candidate / rerank pipeline closure in 0.10.13
- [x] explicit broad-candidate -> bounded-rerank stage boundary
- [x] no truncation for normal/small candidate sets
- [x] deterministic path-diverse preselection for unusually broad candidate sets
- [x] exact/relation evidence survives stage-one priority
- [x] future semantic/model reranker has a bounded insertion point
- [ ] add a learned/semantic reranker only if real retrieval-regret traces justify it


## Context CAS closure in 0.10.14
- [x] context action identity binds repository/search/policy/protocol inputs
- [x] derived context payload stored in verified content-addressed bytes
- [x] response exposes action hash + result digest
- [x] dynamic freshness metadata is never replayed from cache
- [x] source-range caching requires positive filesystem freshness
- [x] cache stays derived/disposable outside Identity authority
- [ ] share in-flight equivalent context computations across concurrent agents (0.10.15)


## Multi-agent shared retrieval closure in 0.10.15
- [x] exact-key in-process single-flight primitive
- [x] concurrent equivalent `find` calls share work
- [x] concurrent equivalent structural-context calls share work
- [x] followers receive only immutable final result/exception
- [x] in-flight state disappears after completion; persistent reuse stays in Context CAS
- [x] source-level sharing requires positive freshness proof
- [x] no agent history/session state crosses the sharing boundary
- [x] Python return/parameter/base/attribute annotations become bounded CodeMap relationship evidence
- [x] exact-name semantic seeds can protect at most two directly related local type hits from lexical crowding
- [x] parser identity bumped for the richer relationship semantics
- [x] composite path/source edge indexes keep the expanded graph inside retained latency gates


## Real-agent intake / regret triage closure in 0.10.16
- [x] runner-neutral raw tool-log schema with explicit tool mapping
- [x] no heuristic tool-name guessing; unknown tools fail closed
- [x] exact normalization-policy identity derived from tool map
- [x] exact raw-runner-log SHA-256 retained in normalized trace
- [x] repository-relative path escape hardening in raw logs and retrieval evidence
- [x] regret-to-first and regret-to-all-required-evidence metrics
- [x] repeated-query/read estimated-token attribution
- [x] exact-byte-bound multi-run regret triage suite
- [x] overlapping opportunity categories explicitly non-additive/non-claim
- [ ] ingest genuine Codex/Pi runner logs and use the ranked triage output to choose the next retrieval behavior change


## Crash-safe runner capture closure in 0.10.17
- [x] create-only per-run capture journal
- [x] atomic immutable per-sequence event files
- [x] duplicate sequence overwrite impossible
- [x] finalization requires contiguous 0..N sequence
- [x] final output reuses 0.10.16 explicit normalization authority
- [x] optional monotonic start/finish timing preserved and validated
- [x] regret reports timing to first/all required evidence when available
- [x] no runner interception or tool-name guessing
- [ ] wire an actual Oh-Goon/Codex/Pi wrapper to emit genuine journal events and use resulting regret-suite triage to choose the next retrieval optimization

## Repository control-surface intelligence closure in 0.10.18

**MUST-STEAL implemented:** typed context domains + intent-scoped retrieval from Sourcegraph/Augment/GitHub-style repository control surfaces, adapted to Hashmarks ownership rules. The accepted mechanism indexes bounded docs/scripts and gives explicit ownership/architecture/build/plan/config/script/contract/doc queries bounded domain-aware ranking. A wider domain-candidate injection was measured and rejected after it reduced blind QA recall.

## 0.10.19 evidence-driven task-query layer — DONE

Measured blind-QA misses justified a bounded task-query layer rather than another global ranking heuristic. Hashmarks now preserves a rare-term base view, derives a governance-aware view from candidate-visible task wording, and fuses them at distinct-path level. A prior authority-companion ranking experiment that did not beat 0.10.18 was rejected and is not canonical.

## 0.10.20 evidence-family retrieval — DONE

- Generic evidence-family task-query view: DONE.
- Candidate-visible cue derivation only: DONE.
- Project-specific filename/SECRET-answer coupling: FORBIDDEN.
- Base + governance view preservation: DONE.
- Identical-view deduplication: DONE.
- Bounded evidence fetch: DONE.
- Blind external QA improvement with general retrieval non-regression: REQUIRED FOR PROMOTION.


## 0.10.21 — proactive bounded verification

**MUST-STEAL principle:** do not run a known large verification surface monolithically when deterministic chunking can make completion and resume explicit. Hashmarks now provides immutable shard plans, explicit warm-up, one-shard `next`, atomic seals, completeness-gated merge, and run-identity binding. This turns timeout avoidance into a reusable execution primitive instead of agent-specific retry behavior.

## 0.10.22 — specialist evidence without specialist crowd-out

Adopted: preserve already-discovered scoped ownership authority only when ambiguous fusion would otherwise erase it. Rejected: broader README/AGENTS reservation and relationship-route override, because both displaced previously-correct evidence in blind QA.

## 0.10.23 — specific authority beats broad authority only after localization proof

Adopted: preserve an already-discovered deep scoped README when a conceptual task has already localized multiple concrete results inside that README's subtree. The rule is deliberately post-localization and changes no search universe. Also adopted: benchmark candidate visibility must be physically blind; SECRET answer files may grade after retrieval but may never participate in candidate indexing or ranking.


## 0.10.24 — bounded graph navigation, not graph-shaped ranking magic

**MUST STEAL:** coding agents benefit from a map of trustworthy next places to inspect, not an unbounded dependency dump. Hashmarks therefore keeps primary retrieval stable and projects a bounded one-hop evidence map from already-relevant seeds. Relationship provenance stays visible, high-degree/generic-name edges are quarantined, and the worker can progressively disclose source only after choosing a promising adjacent identity.


## 0.10.25 — change impact as a worker navigation map

Adopted: turn already-proven reverse dependency impact into a small role-indexed repository map so an agent can see implementation, contracts, verification, build/config, and orientation surfaces after a change. Rejected: a second impact engine, fuzzy semantic blast-radius inference, and any ranking override of canonical task retrieval.


## 0.10.26 — Codex-style scoped repository authority without context duplication

Adopted: mechanical root-to-leaf repository instruction scoping, including local `AGENTS.override.md`, as a separate navigation/authority surface. Rejected: treating README/docs as authority, inheriting parent conversation state, or letting authority resolution rewrite retrieval ranking.


## 0.10.27 — explain selection, do not create another ranker

Adopted: expose deterministic retrieval provenance from the exact bounded lanes already used by canonical task retrieval. Rejected: an explanation-only reranker or synthetic cross-surface score, because observability must not become a second retrieval authority.


## 0.10.28 — cache the canonical answer, not another interpretation

Adopted: generation-bound reuse of the exact canonical task-retrieval result across additive CodeMap surfaces. Rejected: persistent task-result state, approximate-query cache keys, and any latency shortcut that changes ranking or bypasses freshness.


## 0.10.29 — benchmark configuration is authority, results are observations

Adopted: content-addressed benchmark protocol identity that separates fixed comparison conditions from measured results. Rejected: trusting report names, mutable paths, or aggregate metrics as proof two runs used the same protocol.


## 0.10.30 — pair by fixed inputs, vary only the implementation

Adopted: native task-level paired comparison guarded by protocol identity. Rejected: comparing two convenient metric files whose corpus/workspace inputs drifted, or accepting aggregate score similarity as proof of zero regressions.


## 0.10.31 — spend context where task shape justifies it

Adopted: bounded route-aware evidence budgets as an opt-in worker projection. Rejected: hidden global token-budget changes, model-generated budget decisions, and using benchmark outcomes as runtime policy.


## 0.10.33 — deterministic retrieval stability gate

`CodeMap.retrieval_stability()` replays canonical `find_task()` within one CodeMap generation while bypassing only the generation-bound task-result cache. It fingerprints the complete ranked path/kind/score projection, reports the first divergent rank when instability exists, restores pre-existing cache state, and has no ranking effect. Stability is measured; retrieval is never modified to satisfy the gate.


## v0.10.34 fresh multi-repo corpus

Hashmarks carries a deterministic fresh benchmark family (`hashmarks-v0.10.34-fresh-corpus-a`) that materializes three disjoint repositories and 18 independently defined localization tasks across Python service, TypeScript UI, and release/contract automation shapes. Fixture identity is computed only from declared source bytes and corpus bytes; generated `.hashmarks`, VCS, virtualenv, and dependency state cannot affect corpus identity. The existing agent-suite protocol separately binds retrieval parameters, workspace fingerprints, corpus hashes, and task counts. The fresh benchmark is additive QA evidence and does not alter retrieval or ranking.


### v0.10.38 — inspection effectiveness
Ambiguity remains advisory and canonical retrieval is unchanged. The answer-blind worker inspection benchmark compares defer-only behavior with inspect-then-resolve behavior. Resolution may use only public task text and worker-visible competing evidence; hidden expected files/symbols remain grader-only. Same-path role ambiguity collapses safely, explicit public surface/role cues may resolve a competing candidate, and unresolved/tied evidence remains deferred.

## v0.10.39 — multi-step worker decision proof
MUST-STEAL: measure the whole agent decision sequence, not only retrieval top-1. Preserve separate scores for edit safety, verification quality, recovery, and evidence cost. Do not turn the benchmark policy into an orchestrator or a new ranking authority.

## v0.10.40 — failed-verification recovery proof

**MUST steal:** use explicit negative runtime evidence to invalidate a failed
hypothesis and re-orient through existing repository evidence. **Do not steal:**
retry loops that keep editing the same failed surface, hidden-answer hints, or a
new global ranker designed around benchmark cases.


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

## v0.10.47 — real Codex Agent Economics
**MUST steal:** isolated worker contexts, paired tasks, structured frozen results, explicit model/reasoning controls, token/tool trace retention, and fail-closed distinction between simulated and real Codex runs. **Do not steal:** parent-history fan-out or unbounded recursive subagents for economics measurement.

## v0.10.48 — selective real scout
**MUST steal:** spend a second model only on measured uncertainty, restrict it to competing public evidence, freeze its answer independently, and account for its full cost. This is preferred over always-on retrieval agents.

## v0.10.49 — cost per verified solution
**MUST steal:** compare model tiers on verified outcomes rather than retrieval accuracy alone. The target result is cheap-model + Hashmarks matching or beating strong-model + native at lower measured tokens/time per verified solution.

## v0.10.50 — swarm-discovered fixes
MUST steal from the swarm: benchmark isolation, exact-symbol anchoring, and shared warm retrieval service economics. Do not optimize against leaked in-repo answer keys or treat `task_entry_points()` as a universal edit-target ranker.

## v0.10.51 swarm-derived MUST-STEAL closure

Adopted: separate retrieval from worker action roles. Agents receive explicit edit/verify/contract/inspect/related evidence instead of treating rank-1 as an edit instruction. Adopted: benchmark isolation is executable. Adopted: one warm CodeMap serves the swarm instead of rebuilding repository understanding per child.

## v0.10.52 shared-context closure

Adopted: repository understanding is a shared local service, not duplicated inside each agent. Eight concurrent clients can share one warm authority; request backlog pressure is handled by bounded admission/retry without introducing multiple CodeMap owners.

## v0.10.53 anti-thrashing closure

Adopted: verification failure becomes exact negative evidence. Agents keep failed hypotheses explicitly and Hashmarks prevents repeated edits to disproven targets without suppressing nearby evidence or mutating repository truth.

## v0.10.54 selective-agent closure

Adopted: spawn an extra retrieval/review agent only when the action packet proves it is needed. The retained corpus requires zero scouts normally and five after a forced first-edit failure on every task, avoiding fourteen unnecessary recovery agents.

## v0.10.55 work-quality closure

Adopted: score the whole agent loop, not search recall. Process-only routing earns decision-quality credit but cannot claim verified-solution credit. Real Codex/model traces can use the same frozen SECRET grader and work schema.

## v0.10.56 verification-efficiency closure

Adopted: agents should receive a mechanically scoped verification command together with the edit decision. Exact pytest node selection avoids repeatedly running broad test files and removes another repository/tooling discovery loop from the agent.
