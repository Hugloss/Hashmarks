# Hashmarks architecture

Hashmarks is a repository observer and repository-intelligence system with a strict separation between **canonical identity**, **derived repository intelligence**, **consumer reasoning**, and **execution/certification**.

## Architectural goal

Repeated repository archaeology should become incremental and reusable without allowing caches, agent history, or execution state to become repository truth.

The core observer question Hashmarks answers is:

> What is observable about the current repository, what changed, how complete and fresh is that evidence, and what provenance supports it?

## Layers

### 1. Canonical identity

Canonical identity is content-derived. Files, directories, manifests, repositories, and declared repository inputs are represented by deterministic identities over their authoritative inputs.

Filesystem metadata and watchers may avoid unnecessary work, but they do not define content identity.

### 2. Observation and freshness

Observation tracks whether previously derived evidence can still be trusted against current repository state.

The important distinction is between:

- **proven** — continuity/currentness has been positively established for the required authority surface;
- **stale** — a relevant change is known to invalidate the evidence;
- **unknown** — currentness cannot be proven and stronger authority must fail closed.

Unknown must never be silently promoted to fresh.

### 3. Derived CodeMap

CodeMap indexes repository structure and relationships such as:

- paths and repository domains;
- symbols and structural ranges;
- imports, references, calls, and dependency edges;
- projects/packages and declared relationships;
- ownership and qualified identity;
- reverse impact and related tests;
- repository ambiguity and competing candidates;
- cross-artifact declaration correspondence, exact evidence, qualified absence, and disagreement;
- verification relevance.

CodeMap is reconstructible derived state. It may be cached and incrementally maintained, but its semantic result may not exceed a fresh reconciled view of the same repository.

### Repository analysis scope

The admitted repository boundary is also the default analysis boundary. Repository-owned imports, references, manifests, lockfiles, and dependency declarations may create edges to external packages, but those edges do not recursively admit the dependency implementation.

```text
admitted repository bytes / metadata
        │
        ├── repository-owned structure and relationships ──► Hashmarks analysis
        │
        └── external dependency edge ──────────────────────► bounded reference only
                                                              no implicit source descent
```

Hashmarks therefore does not recursively inspect virtual environments, `site-packages`, `node_modules`, package-manager caches, SDK/runtime installations, or unrelated dependency source trees merely because repository code imports them. Explicitly admitted vendored source or a third-party project deliberately selected as the target repository is different: it is repository-owned input for that analysis request.

External package source may still be used by Hashmarks' development/qualification harnesses as a bounded real-code corpus. Such characterization must produce generic analyzer semantics or **NO_CHANGE**; package-specific investigation is not a product responsibility.

### 4. Consumer-facing projections

Hashmarks exposes bounded projections rather than forcing consumers to load the repository wholesale. Examples include orientation capsules, search hits, outlines, impact reports, ownership graphs, evidence contexts, and verification relevance.

A projection can rank or nominate repository evidence. It does not decide the consumer's patch, workflow, retry strategy, or delegation policy.

### 5. External solution and execution planes

Consumers own reasoning and solution behavior. Execution systems own execution and certification.

```text
Hashmarks repository evidence
          │
          ├──────────────► coding agent / IDE / human
          │                    reasoning, editing, choices
          │
          └──────────────► Oh-Goon / CI / runner
                               admission, execution, certification
```

The normative feature-admission contract is [`PRODUCT_BOUNDARY.md`](PRODUCT_BOUNDARY.md).

### Product release awareness and installation handoff

Release awareness is a narrow product-distribution lifecycle surface, not repository intelligence and not general execution authority.

> **Hashmarks may discover update availability. It never owns updating itself.**

An eligible interactive CLI invocation may periodically read public GitHub latest-release metadata. That request is bounded, credential-free, contains no repository-derived information, and is independent of workspace, CodeMap, semantic identity, MCP, or repository evidence. Its small timestamp/latest-version cache is disposable product-local state in the user cache directory; it never lives under `.hashmarks/`, never enters repository identity, and never becomes historical observation state.

Automatic update awareness is excluded from MCP, daemon, CI, and non-interactive invocations and is hard-disabled by `HASHMARKS_NO_UPDATE_CHECK=1`. Network failure, malformed metadata, cache corruption, rate limiting, or GitHub unavailability cannot change repository semantics or prevent the requested repository command from running.

Installation mutation remains deliberately narrower than update awareness. The canonical standalone distribution may, after an explicit interactive **Upgrade now** selection, replace the running process with the existing checksum-verifying standalone installer. The skip path does not resolve shell, PowerShell, curl, or other installer prerequisites; those requirements are resolved once, when the approved standalone handoff actually starts. The displayed standalone command is also the execution payload: release version and install target are not re-encoded through a second Hashmarks-owned channel. Python-package and source installations are externally managed: Hashmarks reports update availability and points the user back to the native mechanism that already owns that installation, but it does not determine whether that mechanism is uv, pip, pipx, Git, or something else. It does not reconstruct package-manager filesystem layouts, inspect package-manager receipts, preflight manager support, or certify installation ownership.

This does **not** admit a general command runner, package resolver, updater backend hierarchy, repository process execution, release promotion, or workflow engine. The product lifecycle may discover one public release fact and hand an explicitly approved standalone self-update to the existing standalone installer; repository/task execution remains external.

## Authority model

Hashmarks distinguishes several kinds of authority that must not be conflated:

- **content identity authority** — exact repository/input bytes and deterministic composition;
- **repository-evidence authority** — structure/ownership/impact claims derived from repository evidence;
- **freshness authority** — whether evidence is current enough for the claim being made;
- **selection authority** — deterministic repository-derived membership or relevance selection;
- **execution authority** — permission and mechanics to launch work; external to Hashmarks;
- **result/certification authority** — whether an execution result is accepted/certified; external to Hashmarks.

Interoperability can transfer evidence between layers but does not transfer ownership of authority.

### Authority precedence is non-strengthening, not a global score

Authority domains compose in a safe direction rather than through one universal rank:

```text
repository bytes / explicit repository metadata
          │
          ▼
qualified observation + freshness/provenance
          │
          ▼
qualified derived repository relationships/providers
          │
          ▼
findings / rankings / selections
          │
          ▼
bounded consumer projections

consumer/model interpretation stays outside repository authority
```

The diagram is not a total ordering across unrelated evidence kinds. Each evidence family keeps its existing qualification semantics. The invariant is that a downstream layer cannot silently make its inputs stronger: stale cannot become fresh, unknown cannot become proven, ambiguity cannot become unique, and a summary cannot override the repository evidence it summarizes. Where no kind-specific authority rule resolves disagreement, Hashmarks exposes the disagreement or remains unresolved.

Cross-artifact declaration correspondence follows the same rule. Providers may normalize producer-native syntax into scoped declaration claims, but provider provenance, correspondence, normalized values, and coverage do not become a global precedence system. Hashmarks binds those claims to exact repository evidence and may report equivalence, difference, ambiguity, or coverage-qualified absence; it never selects the declaration that should win. See [`REPOSITORY_DECLARATIONS.md`](REPOSITORY_DECLARATIONS.md).

### Semantic knowledge graph is a permanent non-goal

Hashmarks may expose bounded repository-derived relationship graphs whose owners already exist in CodeMap—for example imports, calls, references, dependencies, ownership, and explicit repository-declaration correspondence. Those are typed projections over repository evidence.

Hashmarks must **not** generalize semantic identity or correspondence into a repository-wide knowledge graph.

In particular, Hashmarks must not introduce:

- a global semantic node/edge registry spanning unrelated providers or domains;
- persistent semantic edges that outlive the explicit producer-owned claim that created them;
- inferred, transitive, symmetric, inverse, or reachability-derived semantic relationships;
- graph traversal, path search, shortest-path, neighborhood expansion, or transitive-closure APIs over semantic declarations;
- ontology/schema unification that makes opaque provider vocabulary globally meaningful;
- edge weighting, confidence propagation, centrality, ranking, or graph-based winner/precedence selection;
- a graph database, RDF/triple-store-like authority, or graph query layer as a second semantic source of truth.

Explicit correspondence remains local to the producer-owned declaration group that states it. If provider A relates A↔B and provider B relates B↔C, Hashmarks does **not** derive A↔C. A separate explicit producer must own and evidence that A↔C claim.

This boundary does not prohibit ordinary repository graphs already owned by CodeMap. It prohibits turning semantic declarations, identities, and cross-provider correspondence into a general-purpose knowledge graph or relationship authority.

### Semantic identity layers

Repository declarations separate four identity questions instead of overloading file location or one universal ID:

\`\`\`text
semantic namespace + provider-declared concept + scope
        │
        ▼
semantic subject identity        what conceptual subject is being described?
        │
        ├── optional opaque semantic_role
        ▼
semantic declaration identity    which provider-declared role inside the subject?
        │
        ├── request-local labels + exact evidence locator/binding
        ▼
declaration definition identity  which exact declaration/evidence definition?
        │
        ├── value + producer/provenance + qualified evidence state
        ▼
observation identity             which exact observed semantic state?
\`\`\`

Semantic subject identity is location-independent but namespace-scoped: core deterministically identifies \`semantic_namespace + concept + scope\` and does not infer a universal ontology. Direct callers provide the namespace; declaration discovery binds it to the selected provider name and rejects provider attempts to override it. Exact path/range location remains declaration provenance. Observation identity remains immutable evidence for an endpoint.

Semantic declaration identity is optional and subject-scoped. Core derives it only from an explicit non-empty provider-declared `semantic_role` plus the already-issued subject identity. It never derives a role from declaration labels, paths, values, producer names, or model similarity. Untagged declarations remain request-local children.

These identities support correlation and factual endpoint comparison only. They are not Hashmarks branches, commits, refs, checkout targets, or retained repository history. Git/caller/native tools continue to own mutation and lifecycle. See [the semantic-identity decision](../maintainers/SEMANTIC_IDENTITY_WITHOUT_REPOSITORY_OWNERSHIP.md).

Subject-level delta is ambiguity-preserving: a semantic identity is correlated across endpoints only when it names exactly one group on each side. Multiple groups with the same subject identity remain ambiguous rather than being paired by group order, lexical similarity, or value agreement.

The same rule applies inside a uniquely correlated subject: semantic declaration roles are paired only when their derived identities are unique at both endpoints. Role identity supports correlation, not coverage, absence, precedence, or repository-locator authority.

## Cache model

Caches are semantic accelerators only.

- Content-addressed artifacts may be shared when their identity proves equivalence.
- Mutable workspace state is scoped to the workspace/observation authority that owns it.
- Cache hits may change cost, never truth.
- Cache eviction may reduce performance or force recomputation, but must not manufacture stronger semantic authority.
- Tests that require isolation must isolate cache/state roots rather than relying on an empty machine-wide cache.

## Worktrees

Git worktrees can reuse immutable content-addressed parse artifacts when file identities match. Dirty/mutable repository state stays worktree-local. The base/reuse optimization must not allow one worktree's mutable evidence to leak into another.

## Parsing and enrichment

Hashmarks keeps the canonical identity path independent from parsing.

Built-in parsers provide useful structure for Python, JavaScript/TypeScript, Go, and Rust. Optional enrichers may add structural ranges, native project graphs, or imported SCIP evidence. Enrichment may improve repository intelligence, but it cannot rewrite canonical bytes or transfer runtime authority into Hashmarks.

## Fail-closed principle

When a claim requires evidence that Hashmarks cannot prove, the result should become conservative rather than guessed. Typical outcomes are ambiguity, unknown freshness, unresolved ownership, or a request for more repository evidence.

The detailed guarantees are maintained in [`INVARIANTS.md`](INVARIANTS.md).


## Policy boundary

Hashmarks has product invariants but is not itself a policy engine. Its product constitution constrains which observations it may own; it does not create runtime governance, recommendation, sufficiency, workflow, or policy-of-policy authority. Architectural enforcement should prefer existing owners, typed evidence, fail-closed semantics, regressions, and deletion of misplaced responsibility over adding governance state.
