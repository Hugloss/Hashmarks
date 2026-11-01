# Dependency projection and retained evidence requalification

`CodeMap.dependencies.projection()` is the supported direct Python producer API
for a bounded package and source-consumer projection. Its companion
`CodeMap.dependencies.requalify()` rechecks a caller-retained projection through
the same dependency and Source owners. Both return
`hashmarks.dependency-projection.v1`, registered as `dependency_projection`.

The projection keeps package identity, versions, contexts, relationships,
module-ownership ambiguity, source correspondence, completeness, provenance and
admissible scoped absence together. A consumer does not need to join internal
tables, inspect the CodeMap store or implement freshness rules. Retention,
admission, execution and certification remain external.

## Public calls

```python
from pathlib import Path

from hashmarks import CodeMap, hash_bytes
from hashmarks.adapters import npm_lock_dependency_observation

workspace = Path("/path/to/repository")
# The caller captures the artifact and claims the exact captured byte revision.
lock_bytes = (workspace / "package-lock.json").read_bytes()
snapshot = npm_lock_dependency_observation(
    lock=lock_bytes,
    repository_inputs=[
        {
            "path": "package-lock.json",
            "member_revision": hash_bytes(lock_bytes).hash,
        }
    ],
)

with CodeMap(workspace) as repository:
    repository.index.sync()
    observation = repository.dependencies.observe(snapshot)
    retained = repository.dependencies.projection(
        observation,
        packages=[{"ecosystem": "npm", "name": "example-package"}],
        source_paths=["src/bridge.ts"],
        limit=100,
        max_depth=8,
    )
    current = repository.dependencies.requalify(retained)
```

The input to `projection()` is an already-qualified v3 observation, including its
original repository binding and identities. Use existing adapters and
`dependencies.observe()` to obtain it. Requalification accepts the complete
retained projection; it does not create a fresh observation from old claims.

Package selectors require exact `ecosystem` and `name` and optionally exact
`version` and declared `context`. Names use the adapter's normalized component
identity; the core does not guess import names or apply ecosystem-specific
name normalization. Unknown contexts and unknown selector fields are rejected.
Requests normalize, sort and deduplicate selectors and repository-relative paths.

Python consumers use the existing `uv_lock_dependency_observation()` adapter,
including explicitly supplied `METADATA` and `RECORD` when module ownership is
needed. The projection reuses those same qualified observations and
`dependencies.consumers()`; it does not introduce a parallel Python path.

## Packet and independent authorities

| Field | Meaning |
| --- | --- |
| `request` | Canonical selectors, explicit source paths and result/depth bounds. |
| `observation` | The complete original qualified v3 packet, unchanged. |
| `derivation` | Existing derivation-authority packet, or `null` when the producer supplied no adapter semantic-contract token. A missing token is not inferred from producer kind. |
| `assessment` | Existing scoped dependency-input and inventory assessment, unchanged. |
| `packages` | Exact component/selection matches, incident relationships, module owners, ambiguity, contextual inventory coverage and current-input qualification. |
| `source_scope` | Original source-member baseline, current native Source observations and explicit member correspondence. |
| `consumer_evidence` | Existing canonical consumer observation, or an explicit unavailable/not-requested/no-matching-selection state and reason. |
| `repository` | Original and current identity/generation bindings, with their equality reported separately. |
| `projection_identity` | Deterministic content identity of this complete projection. It is an integrity check, not a signature or producer authentication. |

Every package match preserves the native component and concrete selection,
including version, selection source, marker and contexts. Nested inventory,
incident relationships and module-ownership rows preserve their evidence-source
references. All declared module owners remain visible even when only one is a
requested selection. Multiple versions, selections and contexts are reported
before result bounds; one returned row does not establish uniqueness.

Each package's `contexts` describes membership in the **retained declared resolved
inventory**. These historical facts do not become current merely because the
packet is well formed. `current_inventory` separately reports current membership
only when the canonical assessment establishes available inputs, current retained
input revisions and proven correspondence with the producer's original claims.
Without that proof, current membership stays `unknown` and negative evidence stays
`not-admissible`.

An absent package is admissible only within its declared inventory context when
the retained inventory coverage is complete and untruncated and the current input
qualification succeeds. Complete graph coverage cannot fill missing inventory
coverage. An empty bounded match list never proves absence. Inventory membership
does not prove that a package is currently installed, importable or executable.
The overall packet always has `negative_evidence: not-admissible`; qualified
absence belongs to the individual inventory context.

Aggregate projection `completeness` stays `incomplete`. Complete inventory
coverage does not establish complete graph, module-ownership or consumer
coverage, including when no source paths were requested. Each canonical domain
retains its own completeness qualification in every presentation format.

Exact scoped input correspondence and whole-repository identity are independent.
For example, an unrelated Git commit may change the repository identity while the
explicit lockfile bytes remain unchanged. Scoped inventory correspondence can
remain current in that case. Current source-consumer and downstream graph joins
require the original exact repository identity and CodeMap generation, current
dependency-input correspondence, and available matching retained source members.
A stale graph binding cannot be repaired by matching lockfile bytes alone.

## Source consumers and retained members

`source_paths` selects the explicit scope to observe; supplying a path does not
claim it imports a package. Every nominated path is observed and rechecked,
including paths that contribute no returned row or are hidden by output bounds.
Initial native member facts become `source_scope.retained_members`. Requalification
preserves that baseline and the original dependency packet. It compares current
native members without overwriting an older revision or filling an originally
unknown observation with a later claim of historical presence.

`source_scope.correspondence` reports `matched`, `mismatch` or `unknown`. Unknown
or unavailable native source stays unknown. For example, Source may report an
indexed member-revision mismatch as `unknown`; the projection does not turn that
into a successful current observation. Matching known-absent members describe
that member fact but do not enable a consumer join.

`consumer_evidence.selection_scope` is `returned-package-matches`. At most 64
distinct returned selection IDs are passed to the existing consumer operation;
additional IDs have an explicit omission count. Package-result omissions remain
independently visible. Its `context_scope` is
`all-declared-contexts-for-selected-nodes`: source imports are observed against all
declared ownership contexts of those node IDs. A package selector's `context`
does not narrow the canonical consumer's `observed_contexts`.

The nested `hashmarks.dependency-consumers.v1` packet keeps native source revisions,
syntax provenance, metadata-owner ambiguity, type-only/deferred qualifiers and
existing bounded advisory downstream relationships. Supported source/ownership
profiles are Python/`pypi` and JavaScript or TypeScript/`npm`. Known selections from
other ecosystems retain explicit unsupported capability; an unknown node ID is
invalid. Consumer completeness remains incomplete and consumer absence is never
admissible from this explicit source scope.

Retained input and source qualification observes current admission without
indexing or reconstructing repository history. Without a complete existing
CodeMap publication, a current consumer join reports `codemap-not-ready`; an
unreconciled analysis-scope change reports `codemap-scope-stale`. Eligible current
joins reuse the existing consumer query's normal read-scope admission, and the
projection rejects any publication drift. No projection is persisted by
Hashmarks. The caller can retain or discard packets as part of its own bounded
working set.

## npm lock and static import profile

`hashmarks.adapters.npm_lock_dependency_observation()` accepts caller-supplied
`package-lock.json` bytes with `lockfileVersion` 2 or 3 and a native `packages`
object. It translates supported lock-recorded external package locations into existing v3
components, selections, resolved inventory and positive namespace ownership.
The explicit component `name` preserves aliases separately from the installation
namespace. Different native installation locations remain distinct selections;
the adapter does not choose the nearest location for a source importer.

The adapter retains one captured `lock` context and physical-artifact digest.
Lock-recorded locations do not prove that those packages are physically installed.
Platform/optional/development markers and native source/location metadata remain
qualified producer claims. Linked packages, workspace/non-install locations and
local sources are omitted with explicit locations and reasons under
`producer.unsupported`, and reduce selection/inventory completeness. Dependency
edges, roots, hoisting, workspace visibility, subpath exports and runtime loader
behavior are not reconstructed. Module-ownership coverage is always incomplete.

Native ECMAScript Source facts cover static imports, side-effect imports and
re-exports, preserving exact byte ranges, syntax contexts and type-only status.
The supported suffixes include `.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.mts`
and `.cts`. The consumer profile recognizes bare and scoped package namespaces
from those facts. Relative paths, builtins, URLs and package-private `#` specifiers
do not become external package ownership. Dynamic import/`require`, TypeScript
path mappings, workspace resolution and runtime execution remain unobserved.
Positive npm namespace correspondence is candidate ownership evidence, not proof
that a runtime import resolves successfully.

## Bounds, integrity and publication

- At most 64 package selectors and 64 explicit source paths; paths are at most
  4096 characters before normalization.
- `limit` is 1–256 for package matches and each nested collection and for consumer
  rows. `max_depth` is 1–12 for the existing downstream relationship operation.
- Source consumers observe at most 1 MiB per member. Dependency input assessment
  retains its existing 8 MiB member budget.
- A qualified dependency observation and a complete projection each have a
  4 MiB serialized envelope limit. Large projections must use smaller scopes or
  limits; retained evidence is not silently dropped to fit.
- npm input is at most 4 MiB and 1000 native package descriptors; existing v3
  qualification also enforces its own raw-snapshot and semantic collection bounds.

Requalification verifies envelope shape, content identity, canonical request,
original v3 integrity and retained member shape before reading current source.
All derived package, assessment and consumer fields are recomputed through their
owners; previous computed claims are not accepted as current authority. Input,
source or repository-generation drift during the observation fails closed.
Unchanged inputs and qualifications produce an unchanged projection identity.

Structured, compact and text evidence presentations reuse the same canonical
packet and preserve its qualifications. This direct Python API does not add a
CLI/MCP command or service route.

Ownership note: the observed facts are retained qualified dependency claims and
current native source correspondence. The existing dependency, Source, Imports
and Relationships owners remain authoritative. There is no new resolver, graph,
history store, admission policy or executor. Decision: **OBSERVER**.
