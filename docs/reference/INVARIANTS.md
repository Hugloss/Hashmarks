# Hashmarks invariants

**Status: normative.** These are the current public correctness, freshness, ownership, and authority guarantees for Hashmarks.

The product-admission constitution in [`PRODUCT_BOUNDARY.md`](PRODUCT_BOUNDARY.md) overrides historical implementation precedent.

## Canonical identity

**I1. Bytes, not metadata, define file identity.** `mtime`, `ctime`, inode values, watcher events, and cache state are accelerators only.

**I2. Directory, manifest, repository-input, and snapshot identity are deterministic compositions of their authoritative inputs.** Changing an authoritative leaf changes the affected composed identity.

**I3. Strong verification and fast observation produce the same canonical identity.** Stronger observation changes proof strength, never digest semantics.

**I4. Identity domains are versioned and must not be silently reinterpreted.** Repository/content identity must never absorb consumer workflow, process execution, or certification state.

**I5. Persisted filesystem metadata is exact accelerator state, never identity authority.** Device, inode, size, and nanosecond timestamps must round-trip without signed-64 truncation or floating-point coercion before they may justify digest reuse. Ordinary rows keep signed-64 values in SQLite INTEGER columns with no overflow payload; a row containing any wider value stores one canonical decimal BLOB sidecar and only bind-safe INTEGER placeholders. The local file-digest database is disposable derived state with no backward-compatibility promise: incompatible table shape is rebuilt and malformed overflow rows are evicted/rehashed. Repository bytes and content digests remain canonical identity.

## Path and workspace authority

**P1. Host/control paths are canonicalized once.** Workspace, state, CAS, database, and runtime roots are CWD-stable.

**P2. Repository identity paths are lexical, repository-relative, and cannot escape through parent traversal.**

**P3. Internal Hashmarks state never participates in repository source identity.** Mandatory exclusions and traversal ignores remain explicit.

**P4. Workspace confinement applies to repository reads and derived evidence.** A repository symlink or malformed relative path must not make Hashmarks read arbitrary bytes outside the admitted workspace.

## Observation and freshness

**O1. Watchers are observation accelerators, never identity authorities.**

**O2. New, lost, overflowed, incomplete, or otherwise unproven observation is `unknown`, not fresh.**

**O3. Reconciliation is generation-bound.** A changing repository cannot be promoted to clean/fresh evidence from a stale reconciliation cut.

**O4. Stable file reads validate the file around hashing/reading.** Moving bytes are retried or fail closed rather than being cached under stale metadata.

**O5. Request-time observation barriers must be real.** If a watcher backend cannot establish the required barrier, Hashmarks degrades to reconciliation/unknown rather than claiming hot freshness.

**O6. Freshness is evidence-specific.** A recent timestamp, successful cache lookup, or previous query cannot substitute for repository continuity proof.

**O7. Serialized freshness has one state vocabulary.** Current public repository-evidence projections use exactly `current`, `stale`, or `unknown` for freshness state. Proof strength such as `proven` is separate provenance; invalidation is a delta consequence, not an alternate freshness-state spelling.

## Public API and daemon safety

**A1. Local/daemon acceleration may change cost, never semantics.** Automatic fallback must preserve the same repository truth.

**A2. Explicit daemon requirements fail closed when the daemon is unavailable or semantically incompatible.**

**A3. Daemon compatibility is semantic, not merely transport-level.** Protocol, semantics identity, and mandatory safety capabilities must match before daemon-maintained hot state is trusted.

**A4. Typed repository inputs mean what they say.** File, directory, glob, manifest, and repository-relative path inputs are validated rather than truth-coerced.

**A5. Public client/service parity is part of the contract.** A public repository-intelligence client method must have a matching validated service operation.

**A6. APIs have one current supported spelling.** Obsolete Python/CodeMap names, compatibility aliases, and development-evaluation readers are removed rather than preserved. Changes to supported public contracts must be explicit and release-documented; daemon protocol validation may reject an incompatible peer rather than adapt or normalize it.

## Manifests, caches, and derived state

**M1. Large explicit manifests are represented by deterministic identities and bounded incremental structures rather than resent/rehashed without bound.**

**M2. Shared immutable content-addressed artifacts may be reused only when their identity proves equivalence.**

**M3. Mutable graph/index/generation/policy state remains scoped to the workspace authority that owns it.** Worktree or repository reuse must not leak mutable authority across workspaces.

**M4. Cache hits may change latency and storage cost, never repository meaning.** Eviction may force recomputation but may not weaken or strengthen semantic authority.

**C1. Persisted derived/index state is reconstructible evidence, not canonical source authority.**

**C2. Storage backends cannot redefine canonical identity or evidence semantics.**

**C3. Corrupt, dangling, schema-incompatible, or freshness-invalid cached evidence fails closed to recomputation/unknown.**

**C4. Generated CodeMap databases have one current shape.** Workspace CodeMap SQLite state is disposable derived evidence. If its table shape is not the current shape, discard/rebuild it; do not migrate historical lexical/index columns, copy legacy rows, or add schema-specific backward readers.

## CodeMap repository intelligence

**G1. Canonical identity is authoritative; CodeMap is derived.** Parsing, indexing, ranking, enrichment, and context construction never participate in canonical identity.

**G2. CodeMap generations are distinct from identity/observation generations.** A map may lag the repository; freshness must say so.

**G3. Full reconciliation is generation-bound when observation authority is available.** Moving or unknown generations cannot be promoted as fresh map evidence.

**G4. Exact-path reads revalidate the requested source before using stored structural ranges.**

**G5. Source symlinks are not followed outside the workspace.** File-to-symlink and membership transitions invalidate the old row.

**G6. Parse artifacts are content-addressed derived data.** Reuse keys bind content, language/parser semantics, and CodeMap schema.

**G7. Index authority and evidence visibility are separate.** Indexing permission does not imply permission to disclose source bodies.

**G8. Consumer-facing repository evidence uses bounded progressive disclosure.** Orientation, structure, relationships, and exact ranges are preferred over unnecessary whole-file materialization.

**G9. Retrieval may abstain.** Insufficient evidence remains ambiguity/unknown rather than a guessed owner or fabricated confidence.

**G10. Persistent lexical/reference indexes narrow candidates only.** Disclosed source evidence is rechecked against the current workspace and visibility policy.

**G11. Identity scope and CodeMap admission are intentionally different.** Large/generated/non-source inputs may affect identity without becoming retrieval surfaces.

**G12. Native providers and external enrichers are explicit derived-lane work.** They may enrich repository evidence but never enter the canonical identity hot path or acquire execution authority.

**G13. Native/imported evidence is freshness-bound.** When its repository/config/manifest authority changes, stale rows stop participating as current evidence.

**G14. Request-time ranking and graph expansion remain bounded/index-local.** Performance work may reduce cost but not weaken ownership, visibility, provenance, or fail-closed semantics.

**G15. Retrieval/index changes are accepted only with correctness evidence.** Reduced token count, lower latency, or smaller indexes do not justify new false-safe ownership or verification decisions.

**G16. Parser/provider duplicates are normalized deterministically before persistence.** Insertion order must not create semantic variation.

**G17. Qualified ownership is evidence-based and ambiguity-preserving.** Aliases, re-exports, nested projects, import roots, and dynamic-loading patterns may strengthen ownership only when mechanically proven; unresolved identity stays unresolved.

**G18. Reverse impact and verification relevance are repository relationships, not commands to execute.** Selection/relevance evidence may be consumed externally without transferring runtime authority.

## Consumer and execution boundary

**G25. Hashmarks is repository intelligence, not the coding-agent solution loop.** Hashmarks may derive and expose bounded repository evidence, ownership/impact relationships, provenance, freshness, invalidation, and verification relevance/selection evidence. External agents/harnesses retain solution reasoning, planning, edits, arbitrary task-tool execution, verification execution, recovery strategy, orchestration, model/context management, git/worktree lifecycle, and final solution behavior. Agent-facing features that would transfer those authorities into Hashmarks are architecture regressions.

**G26. Verification scope must preserve repository-surface provenance.** Hashmarks may expose repository-relative verification relevance, runner/scope metadata, or mechanically derived verification descriptions; it must not execute verification for the consumer.

**G27. Configuration/source projection is post-selection, bounded, and fail-closed.** Projection may expose exact evidence from an already-selected repository authority but cannot infer the desired edit or execute it. When an active local configuration projection has mechanically proven concrete `CONFIG`/`BUILD`/`PLAN` surfaces, a same-locality contract-only source row cannot displace a concrete configuration surface by retrieval score alone. Multiple concrete configuration surfaces require a unique existing task-specificity advantage before one is selected; unresolved ties preserve the existing fail-conservative fallback.

**G28. Task-evidence provenance is derived, revision-bound, and freshness-honest.** A recent sync timestamp, consumer history, or cached response must never be relabeled as proven freshness.

**G29. Post-change evidence delta is incremental invalidation, not autonomous recovery.** The external consumer owns the change and reports changed repository paths plus the exact prior task-evidence packet. Hashmarks may reconcile those paths and return reusable versus invalidated repository evidence. Hashmarks must not judge the patch, execute verification, choose recovery strategy, or perform a follow-up edit.

**G30. Changed-code impact remains bounded repository evidence, not a follow-up plan.** Hashmarks may expose affected implementation/contract/test relationships with provenance; it must not choose the next edit, decide runtime verification policy, or orchestrate follow-up work.

**G31. Reconstructed ownership/impact relations may corroborate but never replace admitted authority without proof.** Disagreement remains ambiguous rather than being resolved by convenience or ordering.

**G32. Exact import-resolution optimization must remain semantics-preserving.** Keyed/index-local lookup may replace repeated global work only when ownership and visibility semantics are unchanged.

**G33. Declared cross-repository impact is provenance-bearing evidence, never coordination.** Hashmarks may project bounded dependent-project relationships from admitted repository evidence. It must not discover undeclared execution scope, schedule downstream work, route models, delegate agents, execute verification, or orchestrate repositories.

**G34. Dynamic Python module loading is repository ownership evidence, not runtime authority.** CodeMap may report repository-owned dynamic-loading chains and safer mechanically resolved import identities. Hashmarks must not rewrite imports, execute loaders, or claim runtime failure/repair certification from static evidence alone.

**G35. Repository intelligence and execution authority remain separate by constitution.** Hashmarks tells the agent what the repository means, who owns what, what repository evidence indicates risk, what surfaces are affected, and what verification is relevant. The consumer decides what should change. Oh-Goon decides whether execution is admitted, runs it safely, manages processes/timeouts/recovery, and certifies the result.

**G36. Static cache-invalidation ownership remains repository evidence only.** Exact local/import identity may establish an invalidation relationship; same-name lexical coincidence may not. Hashmarks never executes invalidators or owns runtime cache lifecycle.

**G37. Composed ownership/invalidation edges require exact repository evidence.** Shadowed, duplicated, cyclic, or unresolved identities remain ambiguous.

**G38. Static concurrency-risk evidence is nomination-only.** Lexical/read-modify-write evidence does not prove runtime concurrency, prescribe synchronization, or transfer scheduling/process authority.

**G39. Verification ownership links require structural repository evidence.** Lexical/task wording and locality may nominate a verifier but cannot by themselves prove coverage or execution authority.

**G41. Structured repository-query projections are freshness-honest.** Query responses that expose persisted repository relationships or symbols must carry the current CodeMap generation, identity generation, and tri-state stale authority when they do not independently prove exact-path currentness. Unknown continuity remains `stale = null`; projections must not omit that uncertainty and thereby appear stronger than `status()` authority. Exact source/path reads may instead revalidate the requested path directly.

**G42. Repository context policy is live admission authority, not a process-construction snapshot.** Repository-evidence query and sync boundaries must revalidate the exact configured policy authority. A semantic policy change reconciles both removal and discovery so allow→deny and deny→allow converge to the same admitted map as a cold build; invalid policy fails closed before persisted repository evidence is returned.

**G43. Path resurrection never converts a tombstone into current authority.** Bounded task-local history may remember an exact stale path solely so an unsignaled delete→recreate or file→symlink→file transition can be rechecked. Missing and symlink paths remain non-authoritative and must not trigger repeated repository polling; an exact regular-file return is admitted only after current path-scoped reconciliation.

**G44. Omitted task identifiers require repository-backed locality proof.** An explicit lowercase letter+digit token omitted by normal bounded task-query formulation may strengthen task-local retrieval only when existing indexed repository evidence proves that token. Recovery stays bounded, does not rewrite public query views or widen ordinary retrieval limits, ignores unproven version/protocol-like tokens, and must preserve multi-owner ambiguity rather than manufacture uniqueness.

**G45. Task evidence separates retrieval, ownership, verification, and freshness authority.** Bounded retrieval order is relevance evidence only and cannot establish implementation ownership. Exact target/owner evidence may resolve outside the bounded retrieval rows through maintained repository indexes. Freshness is independent: current evidence may remain ambiguous or unresolved, and an ownership result may never be labeled safe merely because its evidence is current.

## Product-boundary constitution

Hashmarks is a repository observer that exposes repository intelligence, not an autonomous coding agent, policy engine, or execution engine.

**PB1. Consumer workflow history is never repository authority.** What a consumer attempted, decided, executed, observed at runtime, or plans next cannot silently become repository truth.

**PB2. Equal repository state must not depend on hidden prior consumer workflow.** Cache history may change latency and cost, never semantic authority.

**PB3. Repository evidence may describe choices; consumer policy remains external.** Ranking, ambiguity, discriminating evidence, candidate repository-surface nomination, and verification relevance do not transfer final action authority.

**PB4. Repository relevance and runtime outcome authority are separate.** Execution, retries/resume, environment recovery, runtime outcomes, and certification remain external.

**PB5. Implementation presence is not feature precedent.** Existing code cannot justify expanding product responsibility; any production surface outside the product profile is a defect to narrow or remove.

**PB6. Hashmarks must never become the agent or the execution motor.** Hashmarks may serve coding agents and execution systems, including Oh-Goon, but service does not transfer ownership. Agent reasoning, memory, edits, delegation, workflow, and recovery remain consumer-owned. Admission, sandboxing, process lifecycle, timeout/retry/resume, runtime environment, result authority, certification, release promotion, and execution-history authority remain execution-layer owned. A proposal that moves either responsibility class into Hashmarks is an architecture regression unless it is split down to a neutral repository-derived evidence primitive.

**PB7. Interoperability transfers evidence, never authority.** Hashmarks may emit repository-bound identities, selections, provenance, relevance, ambiguity, and validation contracts that other systems consume. It must not infer from that interoperability that it should own the consumer's decisions or the execution system's control plane.

**PB8. Repository ownership does not transit through dependencies.** The default Hashmarks analysis authority stops at admitted repository-owned material. Imports, references, manifests, lockfiles, package declarations, and dependency edges may describe relationships to external packages, but they do not implicitly admit external dependency implementation bytes. Hashmarks must not recursively analyze virtual environments, `site-packages`, `node_modules`, package-manager caches, SDK/runtime trees, or unrelated dependency checkouts merely because the repository depends on them.

**PB9. External-library characterization is qualification evidence, not backlog.** Third-party repositories/libraries may be used as bounded real-code corpora to expose generic repository-analysis defects. A named external-library finding becomes product work only when it demonstrates a generic Hashmarks correctness/freshness/ambiguity defect. Otherwise it remains historical characterization and the product decision is **NO_CHANGE**. Package-name suppression tables or library-specific behavior added merely to reduce finding counts are architecture regressions.

**PB10. Derived evidence may never silently strengthen its authority source.** Hashmarks has distinct authority domains rather than one universal confidence order. Cached/indexed/provider/reconstructed evidence, findings, rankings, selections, compact packets, overviews, and other consumer projections must remain bounded by the repository bytes/metadata, provenance, freshness, visibility, and kind-specific qualification rules that support them. They may not convert `STALE`, `UNKNOWN`, `INCOMPLETE`, `AMBIGUOUS`, or unresolved evidence into stronger truth. When no existing authority rule proves a unique resolution, preserve ambiguity/unknown. Human/model interpretation and consumer outcomes never become repository facts without corresponding repository-derived evidence.

**PB11. External observations are correlation inputs, not repository authority.** Runtime logs, tracebacks, CI/test failures, resolver/dependency-tree output, profiler/compiler/scanner findings, and similar consumer-supplied observations remain typed or opaque claims unless an existing Hashmarks authority independently proves the corresponding repository fact. Correlation may expose matching repository evidence and deltas, but the consumer owns interpretation, causal conclusions, and action.

## Evidence, interchange, and consumer conformance

**E1. Hashmarks-produced evidence identities bind the exact authority-relevant fields they claim to represent.** Consumers compare or validate producer-owned identities; they do not recreate hidden canonicalization rules.

**E2. Public evidence validation is fail-closed and allowlist-based.** Unknown fields, malformed scalars, non-finite values, mismatched producer/repository identity, or inconsistent membership cannot gain authority by being rehashed.

**E3. Producer implementation identity and semantic version are different facts.** Version metadata cannot substitute for exact producer identity when a consumer pins an implementation.

**E3a. Producer identity provenance may explain inputs without transferring identity authority.** A diagnostic projection may expose package-relative input paths and content digests so implementation drift is inspectable, but consumers still compare the Hashmarks-issued implementation identity and must not recreate producer canonicalization as an authority source.

**E4. Consumer conformance exposes repository-intelligence evidence only.** Normalized projections contain no timeout, retry, worker scheduling, process state, result authority, or certification policy.

**E5. Freshness requirements are explicit.** Structurally valid stale evidence may remain inspectable but fails a consumer requirement for current repository evidence.

## Scale and repository-language authority

**S1. Exact repository paths used for impact are path authority, not free-text queries.** Impact traversal seeds from the proven path/identity rather than re-retrieving arbitrary lexical matches.

**S2. Scale optimizations preserve semantics.** Bounded reverse indexes, keyed reads, bulk queries, and memoization may reduce work only when they preserve qualified identity, visibility, provenance, and affected-file semantics.

**S3. Re-export and alias binding remain fail-closed.** Multiple plausible leaves, cycles, star/local conflicts, bounded-out traversal, or ambiguous module owners remain unresolved.

**S4. Nested project/import-root metadata is scoped to the declaring project.** Multiple projects exposing the same qualified module remain ambiguous; path ordering cannot manufacture ownership.

## Tooling and release discipline

**G40. Ruff debt is explicit, monotonic, and cannot be suppressed.** Historical complexity debt may exist only while represented by the checked-in baseline. `noqa`, relaxed thresholds, per-file ignores, or moving complexity between files are not debt closure.

**G46. Evidence-context hashing and validation remain producer-owned.** Consumers may compare or store opaque identities but must not silently recreate semantic canonicalization.

**G47. Producer-identity caching may optimize immutable installed bytes only.** Explicit package-root inspection remains capable of detecting supplied-byte changes.

**G49. Contract-surface consolidation is descriptive, never semantic rewriting.** Compatibility metadata cannot silently convert one public semantic contract into another.

**G51. Names expose responsibility and product ownership.** Public/cross-module names must make repository/evidence responsibility clear enough that they cannot reasonably be mistaken for agent workflow or execution/certification permission.

**G54. The CLI facade does not acquire adjacent authority.** Moving parser/handler ownership cannot transfer execution, benchmark orchestration, or certification responsibility into repository intelligence.

**G65. Exception translation has one owner per boundary.** Repository/domain code raises domain errors; the repository CLI adapter and top-level CLI translate caller-visible failures once, the MCP server translates `McpSurfaceError` to the SDK transport error once, and local daemon/CodeMap IPC handlers share one request/error serialization boundary. Broad catches remain local only where rollback, cleanup, optional-provider isolation, single-flight propagation, or a transport request envelope requires them. Catch-and-immediate-reraise blocks are forbidden.

**G66. Repository-intelligence state families have one semantic owner.** A new projection or schema must reuse the existing repository observation, generation, member revision, freshness, completeness, relationship, and delta authorities when they already define the fact. A new CodeMap mixin or public state word may not silently become a second owner merely because a consumer needs a different projection shape.

**G67. Repository evidence bindings are projections, not a second change authority.** Binding definitions may be consumer-declared and opaque, but observed member/range identities, relationships, freshness, completeness, and change facts remain bound to the canonical Hashmarks owners. Definition/configuration change must remain distinguishable from repository content or relationship change.

**G68. Evidence correlation preserves claims without acquiring interpretation authority.** Bounded external or derived observations may be correlated to canonical repository evidence only through existing repository observation, identity, freshness, completeness, relationship, and delta owners. Path/symbol correspondence and qualified source equivalence may be reported; arbitrary metadata cannot strengthen repository truth. Correlation must not become causation, diagnosis, recommendation, execution, recovery, certification, or persistent consumer/runtime history.

### MCP transport boundary

The MCP adapter is a read-only transport projection over one workspace-bound CodeMap. It may serialize refresh and query access, validate/bound consumer inputs, and translate tool errors, but it must not own repository freshness, planning, editing, execution, git, retries, model routing, or workflow orchestration. One MCP server binds one canonical workspace. Tool calls must never expose evidence from a CodeMap generation whose durable build state is `BUILDING`.
