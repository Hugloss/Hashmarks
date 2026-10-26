# Public API and stability policy

Hashmarks is pre-1.0, but public releases still need an explicit contract so implementation history does not accidentally become API.

## What is public

The component rewrite in
[`CANONICAL_COMPONENT_REWRITE_PLAN.md`](../plans/CANONICAL_COMPONENT_REWRITE_PLAN.md)
is an explicitly breaking Python contract revision. Migrated operations move to
their named components and their flat root methods are removed without aliases.
First-party callers migrate with each owner; a partially migrated development
tree is not a released dual API. Serialized evidence meaning, independent source
oracles, freshness and authority do not change merely because a Python call moves.

Qualification handoffs remain owned by `hashmarks.qualification_units`.
`validate_native_qualification_repository_binding(root, handoff)` re-proves the
current repository content, selected membership, classification and producer
identities after validating the retained envelope. The existing development
command `python -m scripts.qualification_handoff --root PATH --validate FILE`
exposes that check with validation-only authority. The former `promotion_receipt`
API and `scripts.promotion_gate` command are removed without compatibility
aliases. Ruff requirements/configuration belong to `pyproject.toml`; tool
execution receipts, release decisions and certification remain external.

`CodeMap.files` is already a read-only `RepositoryFiles` reference. The component
can be constructed without CodeMap or storage, canonicalizes its workspace and
explicit policy path once, and retains lexical member/symlink admission rules.
The old private admission facade methods are removed.

Index operations now use `CodeMap.index.sync()`, `.preflight()`, `.clean()` and
`.watch_forever()`. The old flat root operations and private ingestion methods
are removed. `RepositoryIndex` can be constructed from Files, borrowed stores,
the observation source and a range producer without CodeMap or upper evidence
owners. The optional `CodeMap(..., range_provider=...)` construction argument
injects the narrow `SourceRangeProvider` contract; producer replacement is no
longer performed by changing a root field after construction.

Read sessions now use `CodeMap.reads.session()` and yield an immutable
`ReadScope`, rather than the facade. Diagnostics and counters use
`CodeMap.reads.diagnostics()` and `.stats()`. Root session/query-cache helpers are
removed. Generation drift still fails closed; task freshness preparation belongs
to task entry points rather than a method-name dispatcher inside the read owner.
Opt-in diagnostic producer keys include the concrete component's module and
qualified class name followed by the method name. Source and Bindings `observe`
calls therefore remain separate measurements. These labels and timings describe
runtime diagnostics only and carry no repository or execution authority.

Source operations use `CodeMap.source.outline()`, `.symbol()`, `.read()`, `.grep()`,
`.observe()`, `.range_receipt()`, `.ecmascript()`, `.scoped_occurrences()` and
`.scoped_literals()`. The source component
owns qualified member/range reads and returns detached public outline symbols.
Its instruction-scope primitive consumes explicit paths. Query-based instruction
seed selection remains Context composition, above Source and retrieval.

Indexed JavaScript/TypeScript/Go/Rust declaration and import positions use physical
LF source lines, matching canonical Source observations. Unicode separators
inside source strings or comments do not shift those positions, including
advisory outlines when native ranges are unavailable. Symbol body reads use the
same physical lines, retaining Unicode contents and the existing CRLF display
normalization.
Lexical match positions and grep context use this physical-line contract across
all indexed languages. Parser derivation identities invalidate retained lexical
artifacts when their line partition changes.

`CodeMap.source.range_receipt()` is a supported direct Python operation with
schema `hashmarks.source-range-receipt.v1`. It preserves original bytes in an
explicit zero-based half-open range and binds them to the canonical full-member
revision. CLI/MCP expose the existing source-observation operation's `range` mode;
the flat service-client method is `source_range_receipt(...)`. All use the same
native receipt. See [Exact source byte-range receipts](SOURCE_RANGE_RECEIPTS.md).

`CodeMap.source.ecmascript()` is the supported bounded JavaScript/TypeScript
syntax observation. It uses the configured native Source parser and canonical
member read for import/export aliases, bindings, object destructuring,
assignments, property accesses, and calls. Exact byte ranges and lexical scopes
do not establish semantic alias closure or runtime call targets. Unsupported
parsers and bounded/incomplete evidence retain explicit unknown qualifications.
Its schema is `hashmarks.ecmascript-source-observation.v1`; CLI/MCP use the
`ecmascript` source-observation mode and the service client exposes
`source_ecmascript(...)`. See [ECMAScript source observations](ECMASCRIPT_SOURCE_OBSERVATIONS.md).

Native publication uses `CodeMap.native.import_scip()` and `.enrich_projects()`.
`CodeMap.native.status()` reports native evidence qualification. Repository
relationship queries use `CodeMap.relationships.projects()`, `.deps()`, `.refs()`,
`.affected()` and `.tests()`. Both components can be constructed independently
from their explicit lower repository inputs. Their retired root operations are
removed; reverse-cache validity stays with Relationships and native publication
uses the existing store transaction and generation.

Independent construction derives redundant authority inputs from their owner:
`DecisionScope(index)`, `RepositorySource(index, reads)`,
`RepositoryImports(source)`, `RepositoryNativeEvidence(source)`,
`RepositorySearch(native)`, `RepositoryVerification(imports)`,
`RepositoryCorrelation(bindings)` and `RepositoryRelationships(imports, native)`.
Source rejects a read scope belonging to another Index, and Index reuses the
store's canonical workspace binding. Multi-owner compositions require the same
read-scope authority. Independent, internally consistent readers of one shared
durable store remain supported; their read scopes cannot be mixed in one packet.

Structural operations use `CodeMap.structure.search()` and `.locality()`, with
their existing evidence schemas and bounds. The old root methods are removed.
Pure packet comparisons are imported from their defining modules:
`hashmarks.codemap.structural_locality_delta.structural_locality_delta` and
`hashmarks.codemap.semantic_relationship_delta.semantic_relationship_delta`.
Their former package-level callable aliases are removed because Python submodule
imports overwrite same-named package attributes. The defining imports preserve
function identity across import orders without loading the live components.

Native call-site evidence keeps producer item-range qualification independent
from `declaration_context`. The latter reports lexical containment in one
uniquely indexed declaration only when the index and current member revision
agree. It preserves the producer's raw range and any `outside-caller-item`
state. Lexical containment establishes neither runtime caller identity nor
dispatch, reachability or negative evidence. Position/range validation is owned
by the pure relationship model and shared by the live source resolver and LSP
adapters.

Retrieval uses `CodeMap.search.find()`, `.packet()`, `.find_task()`,
`.task_query_views()`, `.formulate_task_query()` and `.query_route()`. Retrieval
diagnostics use `.retrieval_stability()` and `.explain_retrieval()` on the same
Search owner. Context uses `CodeMap.context.build()`, `.orient()`, `.task()`,
`.task_plan()`, `.work()`, `.budget_sweep()` and `.instruction_scope()`. The old
root methods and query/context cache fields are removed. Normalized find routes
travel with their evidence; presentation does not classify the query again.

Ownership uses `CodeMap.ownership.findings()`, `.repository_graph()`, `.relations()`,
`.import_findings()`, `.cache_findings()`, `.cache_invalidation_graph()` and
`.concurrency_findings()`. Task views use `CodeMap.tasks.action_map()`,
`.entry_points()`, `.graph_adjacency()`, `.relationships()`,
`.verification_relevance()`, `.verification_ownership_graph()` and
`.explain_verification_selection()`. Their old flat root methods are removed.
Direct verification uses `CodeMap.verification.for_owner(VerificationRequest)`
inside the request's exact active read scope; `.plan()` describes a supplied test
surface. Task convenience views share the normalized observation rather than
calling back from Verification to Tasks. Candidate-local test observations retain
their own source basis and cannot overwrite task-owner-bound reference facts.

Verification prioritizes canonically classified test paths inside the existing
reverse-reference window. Other paths fill its remaining capacity; preference
does not filter the repository scope or increase the 1,024-row evidence bound.
The extra lookahead row still detects truncation. Reference caches bind their
generation, short target and exact preference set, so a different ordering cannot
reuse an incompatible prefix. Import/re-export identity, shadowing, freshness
and completeness still qualify every claimed direct relationship.

Task packets and briefs now use `CodeMap.tasks.evidence()`, `.action_brief()`,
`.decision_packet()`, `.decision_brief()` and `.decision_brief_budget_sweep()`.
The task component borrows Context and reuses its scoped task observation across
all projections. Its Source comes from the supplied Search owner, rather than a
second independently supplied source argument. Flat root packet methods and
their inherited implementation paths are removed.

Task declaration hints retain unique normalized word families, qualified-name
order and the original locator's fields when context hints coincide. These
ordering observations do not replace canonical Search ranking or edit authority.
Advisory verification disclosure keeps the exact declaration and its observed
parent class as distinct subjects with independent source bases. Three source
locators can contribute up to six subjects; returned candidates remain bounded
at eight. Reference/namespace authority remains independent from lexical
declaration and filename similarity, and selected edit/test surfaces do not
change merely because additional candidate evidence is disclosed.

Changed-path operations use `CodeMap.changes.impact()`, `.task_impact()`,
`.task_delta()`, `.refresh()`, `.refresh_brief()`, `.refresh_delta()`, `.brief()`,
`.freshness_map()`, `.snapshot()`, `.delta()` and `.external_observation_freshness()`.
Changes owns its read-scope-bound snapshot and impact reuse. A composed response
rejects a publication change after its qualified input rather than mixing
generations. Post-change before revisions are captured in one read scope. A
source-drift recomputation retains those original values and re-observes only
the current endpoint through `CodeMap.reads.observe()`. Member reconciliation
checks and returns the exact Index publication; another writer invalidates that
binding. Repeated source changes retain a typed failure and the existing bounded
CLI/MCP recomputation contract. Pure diagnostic functions are imported from `diagnostic_observation`
and `diagnostic_source_revision`; their root class aliases are removed.

Aggregate operations use `CodeMap.cross_repository.packet()`,
`CodeMap.economics.receipt()` and `CodeMap.views.profile()`, `.query()` and
`.status()`. Profile formatting is a pure projection of an explicit snapshot.
Economics compares that same current snapshot without recollecting an endpoint.
Index observations use `CodeMap.index.derived_graph()`, `.status()` and
`.publication_binding()`. Index status has schema `hashmarks.codemap-index-status.v1`
and contains index facts; Views retains the full `hashmarks.codemap-status.v1`
contract with native and watcher qualification. Their old root operations are
removed; `CodeMap` inherits no domain implementation.

`WorktreeOverlay` takes base Index, Search and DecisionScope capabilities followed
by the caller-selected workspace, with keyword `worker_id` and optional immutable
`artifact_db` location. It borrows no base CodeMap or mutable artifact store. Its
local composition root is owned and closed by the overlay. Base generation and
fingerprint drift reject both sync and fused reads until explicit resync.

`CodeMap.verification.relationship_evidence()` retains the supplied elementary
relationship-value contract. The separate graph composer over qualified
owner/test facts is named `.ownership_relationships()`; task convenience views
use it without changing the elementary relationship signature.

Declarations use `CodeMap.declarations.observe()`, `.discover()`, `.operation()`,
`.derivation_authority()` and `.explain()`. `RepositoryDeclarations` borrows
Bindings and derives Source, Files and its read scope from that same binding
owner. Providers are supplied for the current call; previous observations are
comparison inputs and cannot restore provider or correspondence state. The old
root operations are removed.

Dependencies use `CodeMap.dependencies.observe()`, `.codemap()`, `.queries()`,
`.import_correspondence()`, `.correlation()`, `.delta()`, `.derivation_authority()`
and `.explain()`. `RepositoryDependencies` owns the existing internal dependency
observation, correlation, derivation and endpoint-comparison implementations.
It borrows Source, Imports and repository Correlation directly; it has no Tasks
or root dependency. Producer syntax remains in adapters. The old root operations
are removed.

`RepositoryIdentity.observe_directory()` is a local-only contents observation
with native `snapshot("*")` identity and separately named physical materialization
counts. Literal `exclude_paths` constrain both scopes. Producer-owned state is
omitted from both scopes; explicit own-state selections through the ordinary
input/snapshot APIs remain rejected. Its synchronous
`checkpoint` and `progress` callbacks grant no execution authority; callback
exceptions, physical instability, or `max_members` exhaustion prevent a result.
It does not alter the daemon protocol or reinterpret directory member revisions
as child input-root snapshots. See [input observations](INPUT_OBSERVATIONS.md).

`RepositoryIdentity.observe_inputs()` is the supported selected-input
identity/inventory operation. It returns the immutable `InputObservation`,
`InputMember`, and `InputCounts` types, exported from `hashmarks`, and preserves
the existing `Snapshot` digest domain. Recursive member counts and regular-file
byte totals describe the same observation as the digest; `Snapshot.digest.size`
retains its established identity meaning. Local, auto, and daemon modes are
supported; the CLI command is `observe-inputs`. A method-specific daemon
capability admits the new operation without invalidating older v3 snapshot
clients. Auto mode falls back only for an unavailable daemon or missing
capability; malformed and oversized replies are protocol errors. See
[Selected-input observations](INPUT_OBSERVATIONS.md).

The supported Python API is:

1. names exported by `hashmarks.__all__`, including the lazily exposed `CodeMap`;
2. behavior documented in the root `README.md`, `docs/GETTING_STARTED.md`, and current files under `docs/reference/`;
3. CLI commands documented in the current README/getting-started documentation, including the optional local `hashmarks mcp` stdio surface;
4. explicitly versioned producer/consumer schemas whose validators are part of the documented repository-evidence contract.

Consumer-facing producer binding is also part of the supported top-level Python API: `native_producer_implementation_identity()` returns the exact loaded Hashmarks producer implementation identity, and `validate_native_consumer_bundle()` validates Hashmarks-issued verification-selection evidence against its producer-owned contract. Consumers should import these names from `hashmarks`, not from implementation submodules; the identity remains opaque and Hashmarks-owned, while execution/result/certification authority remains external.

For a valid envelope/contract bundle, `normalized` is a detached
`NativeVerificationSelectionProjection`; that type and its
`NativeVerificationMember` rows are supported top-level imports. The projection
retains typed producer metadata, repository/source/generation/freshness fields,
exact members, opaque membership/selection/provenance/contract identities,
evidence hashes, and repository-only/external-layout authority declarations.
Invalid bundles return no normalized projection. Consumers bind this validated
representation to their admitted source and execution policy rather than
reparsing the original envelope or reproducing producer validation.

`validate_repository_intelligence_evidence()` is the supported consumer validator for current repository-intelligence evidence contracts used across decision, context, impact, verification, ownership, action-map, repository snapshot/delta, and external diagnostic/freshness surfaces. Hashmarks owns current schema recognition and producer-semantic validation. Obsolete development schema names are rejected rather than preserved as compatibility aliases. The returned `normalized` value is a compact, validated projection, not a lossless copy of its input. For diagnostic deltas it declares `projection_coverage: "projection-only"` and lists unprojected source pointers in `unprojected_sections`; consumers needing those facts must retain the original packet, whose identity is included in the normalized result. The projection may bind repository identity, generation, freshness, and the loaded producer implementation identity, but execution, result, retry, scheduling, and certification authority remain external.

Bindings use `CodeMap.bindings.observe()`, `.delta()` and `.coverage()`. The independent `RepositoryBindings` component borrows Source and its read scope; it has no Tasks, packet or root dependency. Their current schemas are `hashmarks.repository-evidence-bindings.v1`, `hashmarks.repository-evidence-binding-delta.v1`, and `hashmarks.repository-evidence-coverage.v1`; see [`REPOSITORY_EVIDENCE_BINDINGS.md`](REPOSITORY_EVIDENCE_BINDINGS.md). Flat root binding operations are removed.

Correlation uses `CodeMap.correlation.observe()` and `.delta()` on an independent `RepositoryCorrelation` component borrowing Source and Bindings. Their schemas are `hashmarks.evidence-correlation.v2` and `hashmarks.evidence-correlation-delta.v2`; see [`EVIDENCE_CORRELATION.md`](EVIDENCE_CORRELATION.md). Flat root correlation operations are removed. Correlation remains a projection over existing repository evidence authorities and does not grant causal or action authority. Pure retained-packet integrity checks do not construct live repository services.

The documented dependency-resolution observation/query surface uses `hashmarks.dependency-resolution.v3` and `hashmarks.dependency-resolution-delta.v3`; derivation and explanation use `hashmarks.dependency-resolution-derivation.v1` and `hashmarks.dependency-resolution-explain.v1`, and dependency evidence correlation uses `hashmarks.dependency-evidence-correlation.v2`; see [`DEPENDENCY_EVIDENCE.md`](DEPENDENCY_EVIDENCE.md). V3 makes semantic evidence authority explicit, keeps producer/source-format `kind` opaque, and binds producer provenance to observation identity rather than semantic definition identity. Dependency endpoint delta compares caller-supplied qualified endpoints directly and reports repository identity, repository generation, semantic, adapter, producer, physical-evidence, coverage, and ownership change axes independently. Repository identity change is evidence reported by the comparison, not a reason to reconstruct or search repository history. Earlier development shapes are not compatibility aliases or accepted readers.

The documented `CodeMap.declarations.observe()` surface is supported Python API. Its schemas are `hashmarks.repository-declarations.v1` and `hashmarks.repository-declarations-delta.v1`; declaration derivation and explanation use `hashmarks.repository-declaration-derivation.v1` and `hashmarks.repository-declaration-explain.v1`; see [`REPOSITORY_DECLARATIONS.md`](REPOSITORY_DECLARATIONS.md). Semantic extraction, normalized values, correspondence, roles, and coverage remain provider claims; the repository-evidence binding, identity, freshness, ambiguity, qualified-absence, factual-delta, derivation, and explanation behavior is the Hashmarks contract. Direct declaration groups require a non-empty `semantic_namespace`; discovery binds that namespace to provider name. Groups/declarations expose deterministic `semantic_subject_identity` over `semantic_namespace + concept + scope`. A declaration may additionally provide a non-empty opaque `semantic_role`, producing `semantic_declaration_identity` over the subject identity plus that role; without a role no child semantic identity exists. Both semantic identities remain separate from exact declaration-definition and observation identity. Declaration delta exposes ambiguity-preserving `semantic_subjects` endpoint correlation and nested `semantic_declarations` only for explicitly role-tagged children.

The local read-only MCP tools `dependency_codemap` and `repository_declarations` preserve their existing default observation responses. Both accept bounded `result_mode` projection: dependency supports `observation | explain | compare`, while declarations support `observation | explain | discovery`. Dependency `compare` requires an explicit caller-supplied `previous_observation` and returns the existing `hashmarks.dependency-resolution-delta.v3` schema; explain modes return the existing typed explain schemas. These are transport projections only: no server-side observation history is retained and no parallel CLI explain/compare command is part of the contract.

The documented `RepositoryDeclarationProvider`, `RepositoryDeclarationProviderContext`, `RepositoryDeclarationProviderResult`, `RepositoryDeclarationProviderError`, and `CodeMap.declarations.discover()` surface is also supported Python API. The provider context exposes bounded admitted-path enumeration via `paths(prefix)`, plus revision-bound `exists`, `read_bytes`, and `read_text`; it intentionally does not expose a raw repository filesystem path. Discovery uses the `hashmarks.repository-declaration-discovery.v1` and `hashmarks.repository-declaration-discovery-delta.v1` wrapper schemas. Providers are explicitly supplied Python objects; ambient entry-point loading and arbitrary provider execution inside MCP are not part of the public contract.

`CodeMap.tasks.evidence()` is the supported role-separated task-evidence API. Its default schema is `hashmarks.task-evidence.v5`: bounded retrieval, explicit-target evidence, ownership, verification, related evidence, freshness and provenance are distinct authority domains. Initial responses use `hashmarks.task-evidence-initial.v2` and retain the same facts through the initial packet codec; presentation bounds do not establish repository absence or ownership uniqueness.

`CodeMap.verification.observe_membership(report)` is a supported direct Python
operation for `hashmarks.verification-membership-report.v1` inputs. It returns
`hashmarks.verification-membership-observation.v1`, preserving native producer
claims, exact selectors, explicit empty/unavailable membership, and source
correspondence through the existing Source/Bindings/Correlation owners.
`validate_native_consumer_bundle(observation)` validates this retained packet;
the existing two-argument envelope/contract path remains supported. Pure retained
validation does not observe the current filesystem. CLI `verification-membership`,
MCP `repository_evidence` membership mode, and the flat service method
`verification_membership(report)` preserve the native observation and its caller
claims. Native collection and execution remain external. See
[Verification membership handoff](VERIFICATION_MEMBERSHIP_HANDOFF.md).

`MakeShellDeclarations` and `PythonUvManifestDeclarations`, imported from
`hashmarks.codemap`, are supported first-party declaration providers. Consumers
select their exact paths and invoke `CodeMap.declarations.discover(...)`; the
registered `make_shell` and `python_uv_manifest_paths` source-selection adapters
also support CLI/MCP/service declaration discovery. The CLI offers exact
`--make-path`, `--shell-path`, and `--python-uv-manifest-path` selectors, or one
`--source-selection-json` file. The flat service method is
`repository_declarations(..., result_mode="discovery", source_selection=...)`.
Provider output remains
bounded authored syntax with qualified coverage and unresolved native semantics.
See [Make/shell evidence](MAKE_SHELL_EVIDENCE.md) and
[Python/uv manifest evidence](PYTHON_UV_MANIFEST_EVIDENCE.md).

CodeMap service clients require canonical replies to be JSON objects with the
expected operation schema. The existing service route definitions supply the
semantic operation and response key. Malformed objects, other operation schemas
and arrays of key/value pairs are rejected with `RuntimeError`. Unknown fields
and literal null/boolean/numeric values are preserved. Internal `find_task` replies
require an array of objects and retain its order; an empty bounded array carries
no repository-negative authority. Service handlers also reject non-object replies
before serialization.

`from hashmarks.codemap import CodeMapServiceClient` is the documented
Python service-client import. The service client retains flat transport methods,
including `sync()` and `task_evidence(...)`; named component families belong to
direct `CodeMap` instances. The service client connects to a separately managed
service and does not promise parity with every direct Python operation. The
[standalone consumer guide](../integration/STANDALONE_CONSUMERS.md) lists the
transport scope of the added observation APIs.

The current task-action, task-evidence, initial-envelope, and post-change response shapes are declared once in `hashmarks.codemap.task_evidence_types`. These `TypedDict` contracts preserve ordinary dictionary/JSON responses; they describe field structure, not repository authority. Default and initial calls have distinct return types. Nullable evidence remains nullable and conditional fields remain optional. Ownership hops and bounded graph projections share `hashmarks.codemap.ownership_relation_types`; trace and authority records are owned by `hashmarks.ownership_decision`. Service-client responses use these same shapes and validate their required fields and nested structure at the JSON boundary, preserving additional producer evidence. MCP Python calls retain the default/initial return distinction. Available and unavailable verification plans have separate typed shapes.

The semantic initial view has its own `InitialTaskEvidenceProjection` contract, including encoded collections and omission accounting; it is not a complete default packet. `read_initial_projection()` reads this view after the lossless initial codec decodes it. The codec itself also supports opaque extension JSON and does not qualify repository authority.

`PreviousTaskEvidence` accepts a current typed default packet or an ordinary dictionary loaded from JSON. Read-only mappings are rejected, and packet identity/context validation still runs before synchronization. `task_post_change_delta()` accepts only the current default task-evidence schema; older development packets are rejected before synchronization.

For natural-language tasks, `retrieval.results` may end with at most two `retrieval_supplement: "bounded-natural-language"` rows. These use the same search-hit fields as canonical rows, but their `score_basis` is `natural-identifier-phrase-relevance`; their scores are not comparable with canonical relevance scores. The requested result limit remains a hard cap. When supplements displace canonical rows, `retrieval.canonical_omitted_results` reports the exact number displaced and `retrieval.ordering` is `canonical-then-bounded-natural-language`. Supplements carry no ownership or verification authority.

`CodeMap.tasks.verification_ownership_graph()` and `hashmarks map verification-ownership` expose existing edit-authority links and bounded verifier candidates through `hashmarks.verification-ownership.v2`. `verification_qualification` retains the underlying relevance observation's authority, completeness, truncation, candidate count and bounds when supplied. Summary `unowned` and `ambiguous` values may be `null` when their observation scope is unknown or incomplete. Empty returned candidates alone cannot establish absence; a hidden, observed second candidate cannot disappear from ambiguity merely because the displayed candidate limit is smaller. These summaries describe repository observations, not verification sufficiency or execution permission.

Verification relevance distinguishes aggregate reference uncertainty
(`qualified_identity_ambiguous`) from unresolved identity in observed test
references/imports (`verifier_identity_ambiguous`). The latter is an additive,
optional boolean, qualified before output bounds and preserved in task evidence,
initial projections and `verification_qualification`. Integers are not booleans at
the JSON boundary. A missing scoped qualifier retains the aggregate ambiguity
veto in task-owner projection.

An unresolved production receiver call remains disclosed and prevents qualified
verification absence or uniqueness; it does not by itself veto an independently
established edit owner. Unresolved verifier identity still requires owner
discrimination. Aggregate uncertainty continues to prevent verification evidence
from being promoted into decisive owner discrimination. Neither field proves a
dynamic receiver's type, test sufficiency or execution outcome.

Selection traces and ownership authority qualify different facts. A trace may
describe a resolved retrieval selection while its ownership proof remains
incomplete. In that case the authority and task-evidence ownership status are
`unresolved`, `owner_resolved` is false, and the candidate remains visible.
`resolved` ownership requires the admitted owner and completed proof; only that
owner supplies ownership source evidence. Competing-owner ambiguity is evaluated
independently of verification uncertainty, so an unresolved production call cannot
clear an existing conflict. Verification candidates and project-scoped test
commands remain available even when edit ownership is unresolved.

Importable implementation submodules under `hashmarks.*` are **not automatically public** merely because Python allows importing them. Internal helpers, storage classes, parsers, adapters, and mixins may change without compatibility guarantees unless a current public document explicitly promotes them into the contract.

Development material under `scripts/agent_evaluation/`, `benchmarks/agent_evaluation/`, and `tests/` is measurement/evidence infrastructure, not installed product API.

`CodeMap.dependencies.assessment(observation)` is the supported live assessment
of a retained dependency endpoint. Its `hashmarks.dependency-resolution-assessment.v1`
result keeps exact declared-input freshness, external source equivalence,
repository-wide freshness and per-context resolved-inventory qualification separate.
It observes only the declared source inputs through Source, revalidates stability,
and grants no resolver, admission or execution authority. See
[dependency evidence](DEPENDENCY_EVIDENCE.md).

## Pre-1.0 contract evolution

Structural Locality presentation uses collection findings for its bounded node,
edge, unresolved-call and external-call arrays. Their `details` preserve the whole
native array, `source_refs` identify that collection, and `native_item_count`
counts its members. Finding counts for these kinds count collections. The native
Structural Locality response and its authority/bounds retain their existing
contract; see [Structural Locality](STRUCTURAL_LOCALITY.md).

Existing findings, structural-locality and resolved-owner task-evidence surfaces
may carry the additive `resource_lifecycle` observation documented in
[Filesystem lifecycle evidence](FILESYSTEM_LIFECYCLE_EVIDENCE.md). Its nested
`hashmarks.python-filesystem-lifecycle-observation.v1` schema is accepted by
`validate_repository_intelligence_evidence()`. Source-reference relationships,
runtime identity, freshness, semantic coverage, lexical guards and external
claims remain separate; validation never establishes protection or exploitability.
An envelope without this optional family means evidence was not supplied.

For the `0.x` series:

- Hashmarks carries one current documented Python/CLI surface; names outside the supported contract are removed rather than kept as compatibility aliases.
- generated local databases/caches are disposable and may be rebuilt when their current shape changes; no migration/backward-reader obligation exists unless a future explicit requirement introduces one.
- serialized repository-evidence contracts use explicit schema identities and validators; obsolete development/evaluation schema readers are removed instead of normalized.
- implementation details and development evaluation formats are not compatibility commitments.

Current client/daemon protocol checks remain fail-closed safety validation: a mixed incompatible runtime is rejected rather than adapted.

## Authority stability

Compatibility must never weaken Hashmarks' authority model. In particular:

- cached/incremental evidence may not become stronger than current reconciled repository truth;
- compatibility must not turn consumer workflow state into repository authority;
- interoperability may transfer evidence, never execution or solution authority;
- fail-closed freshness and provenance rules take precedence over preserving an obsolete convenience API.

See [`PRODUCT_BOUNDARY.md`](PRODUCT_BOUNDARY.md) and [`INVARIANTS.md`](INVARIANTS.md).

Task retrieval may include `same_name_declarations`: up to four other indexed
callable declarations with the same spelling in the retrieved callable's file.
The context retains exact source spans, member revision, index generation and
observed/returned/omitted counts. Initial and presented responses preserve these
facts. Same spelling establishes neither runtime identity nor inheritance,
dispatch, ownership or verification selection; no global name graph is created.

Diagnostic queries may also disclose one `bounded-lexical-source-position`
supplement: a current source-visible callable containing query-token conjunctions
after its declaration line. Lookup examines at most eight adjacent query-term
groups (two observed spelling variants per term), thirty-two indexed declarations
and one returned source-position hint. These are disclosure bounds, not semantic
completeness or failure-owner proof. Explicit locators retain precedence and
edit/verification selection remains independently owned.

When there is no diagnostic source-position hint, a natural-language query may
instead disclose one `bounded-declaration-context` callable. Its indexed class
name and signature must add matching identifier terms beyond its own name. The
lookup uses the existing sixty-four-file lexical pool before the twelve-path
shortlist, at most thirty-two distinct query groups and thirty-two declaration
candidates. SQL substring prefixes only prefilter candidates; identifier parts
must qualify the match. Current source or outline visibility is required, and
explicit locators retain precedence. The two-supplement and requested result
bounds are unchanged. A class/signature match establishes neither behavioral
ownership nor runtime identity, test relevance or complete search coverage.

A `bounded-lexical-source-position` locator may carry `direct_call_declarations`, containing up to four
same-file callable targets from at most sixty-four direct indexed calls. The
existing structural-locality resolver must qualify each target; nested callable
calls, shadowed names and transitive targets are excluded. Exact target spans,
call positions, source revision, generation, omissions and unqualified-call counts
remain visible in every format. Runtime invocation remains unestablished and no
negative-evidence authority is granted.

Structural call qualification binds declared members to complete admitted file
scopes and qualified import leaves. A bounded global name bucket cannot erase
an independently qualified positive binding. Unqualified fallback searches keep
their original bounds and uncertainty. Class members use the shared ordered
declaration rule and must match the selected source range; conditional bindings,
rebound receivers and unproven import frontiers remain unresolved. Every examined
import/re-export binding must share the active indexed source generation; drift
requires observation refresh. These are static declaration relationships, not
proof of runtime dispatch or a complete execution path.

Source-candidate test disclosure preserves source namespace locality before task
words in a test directory. Declaration overlap is measured within one indexed
test, rather than combining unrelated names throughout a large module. At least
two words from an already observed source declaration may also retain a matching
test when the task paraphrases that declaration. This spelling overlap stays
source-local lexical disclosure and establishes no reference. A specific
matching test breaks an otherwise equal lexical tie. These are disclosure facts,
never uniqueness or relationship proof. Candidate pools from the first three
source locators share the bounded reply, alongside canonical task candidates.
Scores relative to different sources are not compared to decide that order.
The selected verifier and edit owner remain unchanged.

Initial compact declaration tables bind their scope through the finding's exact
`source_refs[0]` plus the declaration-family key. Table row references append
`/declarations/<i>` in native order. This avoids repeating that pointer inside
each table; the complete native context, qualifiers and row values are retained.
Compact tables expose structured `metadata`, `common`, `prefix`, `columns`,
`extras` and `rows`, avoiding quoted JSON inside text. Text rendering retains its
readable scope tables. The initial wire codec chooses the smaller of `json+zlib`
(Base64) and `json+lzma-base85` for compressible semantic data, and retains the
uncompressed `json-string-table.v1` fallback. This changes wire bytes only;
decoded evidence, source references and semantic packet identity are identical.
Decoders also accept existing `json-string-table.v1+zlib` packets. All compressed
forms have the same 1 MiB decoded-output bound, exact decoded-byte count, stream
closure and semantic identity checks; direct JSON also rejects duplicate keys.
LZMA decoding additionally limits dictionary memory to 16 MiB.

Observed repository fact/evidence: distinct same-named callable declarations in
one selected repository file.
Authority source: existing source-derived CodeMap symbol index and member binding.
Completeness/freshness behavior: current visible source only, bounded disclosure
with explicit omissions, no negative-evidence authority.
Existing Hashmarks owner extended: task evidence lexical declaration disclosure.
Consumer/execution responsibility explicitly not acquired: runtime dispatch,
solution selection, execution and certification.
Decision: OBSERVER.
