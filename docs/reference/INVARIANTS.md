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

**G25. Hashmarks is repository intelligence, not the coding-agent solution loop, repository mutation engine, or historical archive.** Hashmarks may derive and expose bounded repository evidence, ownership/impact relationships, provenance, freshness, invalidation, verification relevance/selection evidence, immutable observations retained for an active bounded work window, and semantic deltas between caller-selected repository authorities. External agents/harnesses retain solution reasoning, planning, edits, arbitrary task-tool execution, verification execution, recovery strategy, orchestration, model/context management, git/worktree lifecycle, branch creation/management, merge/rebase/cherry-pick and conflict-resolution semantics, rollback/revert/reset/checkout, ref/worktree mutation, and final solution behavior. Hashmarks may observe those repository states but must never perform or own those transitions. It must not crawl/pre-index Git history or retain an unbounded observation timeline; bounded historical observations are evictable working-set evidence, and older authorities must be supplied or reconstructed by the caller/Git when needed. Agent-facing features that would transfer those authorities into Hashmarks are architecture regressions.

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

**G46. Cross-artifact declaration correspondence is explicit and scope-bound.** Core may compare provider-normalized declarations only inside one explicitly scoped conceptual group. Similar names, filenames, values, locality, or model inference cannot manufacture correspondence.

**G47. Declaration comparison never becomes source-of-truth precedence.** Canonical equality may establish equivalence and canonical inequality may establish difference for resolved declarations in one group, but Hashmarks never chooses a winning declaration, treats majority agreement as authority, or invents a global declaration ranking.

**G48. Declaration absence requires qualified semantic coverage.** An unseen expected declaration becomes authoritative absence only when declared coverage is complete and explicitly non-truncated for the relevant scope. Incomplete, truncated, or unknown coverage preserves absence as unknown.

**G49. Declaration semantics and repository evidence retain separate authority.** Producer normalization, semantic values, correspondence, expected membership, and coverage remain provider claims unless a separate Hashmarks authority establishes them. Exact member/span identity, repository freshness, and repository presence remain owned by canonical repository-evidence authorities. A provider-resolved value may participate in declaration equivalence/difference only when all exact cited repository evidence is currently `known-present`; absent, unsupported, or unknown evidence must fail closed to ambiguity.

**G50. Declaration deltas are factual and tamper-detecting.** Previous declaration observations must validate their Hashmarks-issued observation identity before comparison. Deltas may report changed definitions, values, provider observations/provenance, correspondence, coverage, equivalence/difference, or absence, but never whether a change is correct or desirable. Exact repository-evidence and observer deltas remain owned by the existing repository-evidence-binding delta authority.

**G51. Declaration provider discovery is explicit, deterministic, and bounded composition.** Hashmarks runs only caller-selected provider objects, canonicalizes provider order, requires unique provider names, bounds distinct repository inputs and path enumerations per provider, and records provider provenance separately from nested declaration evidence. Provider semantic inputs used for declaration evidence must be read through the Hashmarks-owned provider context and remain revision-equivalent through qualification. Dynamic path discovery must use the context's admitted repository-file enumeration, sharing the repository discovery policy/pruning/symlink owner without requiring CodeMap parser support for the file format; the public provider context does not expose a raw repository filesystem path. Ambient entry-point discovery, repository-supplied code loading, and hidden default providers are not authority.

**G52. Provider detection and semantic absence are different facts.** `not-detected` means only that one selected provider did not apply. A detected provider failure must fail the discovery call closed; neither state may be converted into declaration absence. Negative declaration evidence still requires the nested complete, untruncated coverage contract.

**G53. Provider execution does not cross the MCP boundary.** MCP may transport already normalized declaration claims into the read-only declaration qualification surface, but it must not dynamically import or execute arbitrary Python declaration providers.

**G54. Provider path enumeration is repository observation, not ambient filesystem access.** Provider enumeration uses the shared repository admission/pruning/symlink discovery owner, is bounded, is recorded in provider observation identity, and is revalidated during qualification. Admitted files may be enumerated even when CodeMap has no parser for their format, but enumeration alone does not certify their contents or semantics: declarations still require revision-bound exact repository evidence reads. Enumeration must not grant providers an opaque raw workspace path or expose denied, internal, pruned, or symlink-descended material.

**G55. Repository-derived file evidence has one admission authority.** Producer-specific parsers, native tools, project graphs, import-root discovery, and freshness projections may own their semantic interpretation, but they must not create a second filesystem-admission model. Repository files that support derived CodeMap evidence must pass the canonical repository-file admission/visibility owner before they can be parsed into project evidence, persisted as project nodes/edges, or used as manifest freshness authority. A live allow→deny policy change must stop denied derived evidence from participating before a producer refresh can re-establish the remaining admitted graph.

## Product release and update lifecycle

**U1. Update awareness is not repository authority.** Public release metadata, check timestamps, and update prompts are product-lifecycle state only. They must not participate in repository identity, CodeMap generations, semantic observations, evidence history, freshness, or `.hashmarks/` state.

**U2. Automatic release checks are strictly bounded and suppressible.** They may occur only for eligible interactive CLI invocations, at most once per configured check interval. MCP, daemon, CI, and non-interactive invocations perform no automatic release check. `HASHMARKS_NO_UPDATE_CHECK=1` hard-disables automatic update-related network traffic.

**U3. Release checks disclose no repository-derived information.** The public latest-release request must not include workspace paths, repository names/remotes, source, content hashes, observations, semantic identities, MCP payloads, or ambient GitHub credentials. Release discovery must not depend on repository state.

**U4. Automatic update failure is semantically inert.** Offline operation, DNS/TLS failure, GitHub unavailability, rate limiting, malformed release data, cache corruption, or concurrent check suppression cannot fail or alter the requested repository-intelligence command.

**U5. Installation mutation is explicit and narrow.** Hashmarks never silently chooses an upgrade. The canonical standalone distribution may offer an interactive **Upgrade now** handoff to its existing checksum-verifying installer. The **Skip for now** path does not resolve or preflight installer prerequisites; standalone installer requirements are resolved only after explicit upgrade consent. The optional standalone upgrade command is the single resolution of both installation mode and exact execution payload: `None` means the installation remains externally managed, while a command is displayed and transported unchanged. Callers must not separately detect standalone mode and then ask the command builder to decide it again. The exact displayed standalone command carries the selected release/install target once; Hashmarks must not transport the same upgrade inputs again through a parallel environment channel. Non-interactive use never mutates installation state. Python-package/source installations remain externally managed and receive update awareness plus native-tool guidance only.

**U6. Hashmarks never owns updating itself.** Hashmarks may discover that a newer stable release exists. It does not implement a package resolver, package-manager detector, installer backend framework, hidden downloader/updater authority, or continue repository work with mixed old/new code. For installations owned outside the standalone distribution, Hashmarks does not choose or invoke a package manager on the caller's behalf.

**U7. Native package-manager state stays opaque and native.** Hashmarks must not reconstruct uv/pip/pipx filesystem layouts, inspect or certify their receipts/metadata, infer ownership from ambient environment variables or paths, preflight whether their upgrade operation is supported, or mirror their installation state into a second authority. The package manager that installed Hashmarks owns those semantics and its own failures. Hashmarks may show non-authoritative example commands, but the user/native workflow selects and runs the real package-manager operation. Release promotion/publication remains external to the running Hashmarks product.

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

**PB12. Dependency adapters translate producer syntax into producer-neutral semantic authority.** Maven, uv, Gradle, npm, SBOM, and future producer-specific formats terminate at their adapters. Core dependency qualification may use producer-neutral semantic authorities such as selection, resolution graph, resolved inventory, and module ownership, but it must not derive authority from a producer/source-format `kind`, require a package-manager-specific source shape, or duplicate one physical artifact into synthetic sources merely to represent different semantic uses. One evidence source may carry multiple semantic authorities. See `DEPENDENCY_EVIDENCE.md`.

**PB13. Physical-source completeness and semantic coverage are distinct.** A complete, untruncated producer artifact does not imply complete graph, inventory, selection, or module-ownership coverage merely because the source declares that authority. Negative evidence and query completeness require explicit qualified coverage in the relevant semantic domain; source completeness only bounds the cited artifact itself.

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

**G40. Current Ruff complexity debt is zero.** The full configured Ruff check and current complexity/file-size inventory must pass without a historical baseline. Relaxed thresholds, per-file ignores, new suppressions, or moving complexity between files are not debt closure.

**G46. Evidence-context hashing and validation remain producer-owned.** Consumers may compare or store opaque identities but must not silently recreate semantic canonicalization.

**G47. Producer-identity caching may optimize immutable installed bytes only.** Explicit package-root inspection remains capable of detecting supplied-byte changes.

**G49. Contract-surface consolidation is descriptive, never semantic rewriting.** Compatibility metadata cannot silently convert one public semantic contract into another.

**G51. Names expose responsibility and product ownership.** Public/cross-module names must make repository/evidence responsibility clear enough that they cannot reasonably be mistaken for agent workflow or execution/certification permission.

**G54. The CLI facade does not acquire adjacent authority.** Moving parser/handler ownership cannot transfer execution, benchmark orchestration, or certification responsibility into repository intelligence.

**G65. Exception translation has one owner per boundary.** Repository/domain code raises domain errors; the repository CLI adapter and top-level CLI translate caller-visible failures once, the MCP server translates `McpSurfaceError` to the SDK transport error once, and local daemon/CodeMap IPC handlers share one request/error serialization boundary. Broad catches remain local only where rollback, cleanup, optional-provider isolation, single-flight propagation, or a transport request envelope requires them. Catch-and-immediate-reraise blocks are forbidden.

**G66. Repository-intelligence state families have one semantic owner.** A new projection or schema must reuse the existing repository observation, generation, member revision, freshness, completeness, relationship, and delta authorities when they already define the fact. A new CodeMap mixin or public state word may not silently become a second owner merely because a consumer needs a different projection shape.

**G67. Repository evidence bindings are projections, not a second change authority.** Binding definitions may be consumer-declared and opaque, but observed member/range identities, relationships, freshness, completeness, and change facts remain bound to the canonical Hashmarks owners. Definition/configuration change must remain distinguishable from repository content or relationship change.

**G68. Evidence correlation preserves claims without acquiring interpretation authority.** Bounded external or derived observations may be correlated to canonical repository evidence only through existing repository observation, identity, freshness, completeness, relationship, and delta owners. Path/symbol correspondence and qualified source equivalence may be reported; arbitrary metadata cannot strengthen repository truth. Correlation must not become causation, diagnosis, recommendation, execution, recovery, certification, or persistent consumer/runtime history.

**G69. Semantic-subject identity is explicitly namespaced, location-independent, and read-only.** Repository declarations derive semantic-subject identity from an explicit semantic namespace plus the opaque concept and semantic scope. Direct callers supply the namespace; provider discovery binds it to the selected provider name and rejects provider namespace overrides. Request-local group labels, declaration membership, exact file/range locators, values, coverage, and current evidence do not define that subject identity. Equal opaque concept/scope under different namespaces is not equivalence, even when semantic roles, normalized values, request-local labels, and exact repository evidence also match. Replacing one provider namespace with another is semantic removal plus addition, never an inferred rename, alias, or provider migration. Provider implementation/provenance/version is not semantic identity while the provider name, concept, and scope remain the same; changing semantic scope changes subject identity and any derived role identities. Declaration/evidence and observation identities remain separate. Subject identity may support correlation and endpoint comparison, but it must never become branch/ref identity, repository-history ownership, source-of-truth precedence, or permission for Hashmarks to mutate repository state.

**G70. Semantic-subject delta preserves multiplicity and child-identity ambiguity.** A subject identity may correlate endpoint groups only when exactly one group with that identity exists in each observation. Duplicate subject identities remain explicit ambiguity; order, value agreement, declaration count, file locality, or model similarity may not select a pairing. A changed request-local group ID does not authorize pairing ordinary request-local declaration IDs across endpoints. Exact repository member/span/locator change remains owned by canonical repository-evidence delta.

**G71. Semantic declaration identity is explicit, optional, subject-scoped, and never strengthens absence.** A provider may opt one declaration into cross-label correlation only by supplying a non-empty opaque `semantic_role`; Hashmarks derives `semantic_declaration_identity` from the already-issued subject identity plus that role. It must not infer roles from declaration IDs, paths, values, producer metadata, repository similarity, or models. Role identities correlate only when unique at both endpoints; multiplicity remains ambiguity and a role change is removal plus addition. Duplicate roles may not be collapsed by declaration order, apparent source specificity, majority, matching values, agreement with another declaration, or producer metadata. If a native format has precedence semantics, the provider must resolve and expose that claim explicitly; core does not reconstruct native precedence. Untagged declarations remain request-local. Role identity does not alter `coverage.expected_declaration_ids`, prove negative evidence, select precedence, or own repository-locator change.

**G72. Semantic identity reappearance is not historical continuity.** The same deterministic subject or semantic-declaration identity may appear in later caller-supplied observations after being absent from an intermediate endpoint. That proves only that the later provider claim uses the same admitted semantic identity inputs. It does not prove continuous existence, resurrect a missing declaration, create a tombstone, infer a move, or authorize Hashmarks to retain/search a timeline. Endpoint absence remains coverage-owned, exact physical evidence remains repository-evidence-owned, and any earlier observation used for comparison remains caller-supplied bounded evidence.

**G73. Declaration uncertainty axes remain orthogonal.** Provider value ambiguity, provider-declared correspondence ambiguity, repository-evidence qualification, and coverage/absence uncertainty describe different facts and must remain independently reportable. One uncertainty axis must not strengthen, resolve, or replace another: ambiguous candidate values do not become disagreement, incomplete or truncated coverage does not become known absence, missing evidence does not select a value, and agreement among remaining declarations never creates precedence. Hashmarks reports the simultaneous states and leaves interpretation to the consumer rather than introducing a combined uncertainty score, winner, or new semantic owner.

**G74. Cross-provider correspondence is a producer-owned claim, not identity union.** Independent provider namespaces keep independent semantic subject and role identities even when another explicit provider reads both evidence sets and declares them comparable. The correspondence provider owns a separate namespaced subject, correspondence basis, normalized values, coverage, and exact bindings for its claim. Its equivalence, disagreement, ambiguity, addition, or removal must not rewrite source-provider identities, source coverage, source bindings, or infer cross-namespace aliases, ontology equivalence, precedence, or migration. Hashmarks compares only inside the explicit correspondence group and preserves the underlying provider claims independently.

**G75. Hashmarks is not a semantic knowledge graph.** Repository-declaration identity and correspondence remain bounded producer-owned facts, not nodes/edges in a global semantic graph. Hashmarks must not persist semantic edges independently of their producer claims; infer transitive, symmetric, inverse, reachability, or path-derived relationships; perform semantic graph traversal or transitive closure; unify opaque provider vocabularies into a global ontology; or introduce graph-derived confidence, centrality, ranking, precedence, or winner semantics. Explicit A↔B plus explicit B↔C does not authorize inferred A↔C. Likewise, explicit A↔B, B↔C, and C↔A do not create a connected component, equivalence class, global consensus, majority authority, or cycle-level winner. Any aggregate multi-party comparison must be owned and evidenced by another explicit producer claim. Existing CodeMap relationship graphs remain bounded repository-derived projections under their current owners and do not authorize a general semantic graph owner.

**G76. Correspondence provenance is not referential integrity.** Opaque names such as provider identifiers inside correspondence basis/provenance are descriptive metadata owned by the producer claim, not foreign keys into other provider observations. Removing a named source provider must not cascade-delete, invalidate, or rewrite an independently explicit correspondence claim whose own repository evidence remains qualified; adding or restoring a source provider must not auto-bind or rewire that correspondence. Core does not enforce provider-existence constraints, cascade semantics, identity joins, or relationship rewrites from provenance names. If referential semantics matter, the correspondence producer must express and evidence them explicitly inside its own claim.

**G77. Previous declaration observations are comparison inputs, never semantic storage.** Repository-declaration and correspondence packets remain `derived-not-persisted`. A caller-supplied `previous_observation` may influence only the factual delta returned by that explicit call; it must not seed, restore, cache, replay, or otherwise persist semantic subjects, role identities, correspondence groups, relationship edges, provider observations, or graph state inside CodeMap. Reopening CodeMap against the same durable state directory must reconstruct current declaration state only from the currently selected providers and current qualified repository evidence. Replaying an older packet may reproduce a comparison against that packet, but a later call without it must be identical to the same current-provider observation as if the replay never occurred.

### MCP transport boundary

The MCP adapter is a read-only transport projection over one workspace-bound CodeMap. It may serialize refresh and query access, validate/bound consumer inputs, and translate tool errors, but it must not own repository freshness, planning, editing, execution, git, retries, model routing, or workflow orchestration. One MCP server binds one canonical workspace. Tool calls must never expose evidence from a CodeMap generation whose durable build state is `BUILDING`.
