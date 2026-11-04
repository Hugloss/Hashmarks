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

from hashmarks import CodeMap
from hashmarks.adapters import npm_lock_dependency_observation

workspace = Path("/path/to/repository")
with CodeMap(workspace) as repository:
    repository.index.sync()
    member, lock_bytes = repository.source.member(
        "package-lock.json", include_bytes=True
    )
    if member["state"] != "known-present" or lock_bytes is None:
        raise ValueError("package-lock.json is not available as admitted source")
    snapshot = npm_lock_dependency_observation(
        lock=lock_bytes,
        repository_inputs=[
            {
                "path": member["path"],
                "member_revision": member["member_revision"],
            }
        ],
    )
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

Source returns the admitted bytes and their matching member revision together.
Preserve that revision in `repository_inputs` so the producer can recheck the
exact captured artifact through the same source authority.

The input to `projection()` is an already-qualified v3 observation, including its
original repository binding and identities. Use existing adapters and
`dependencies.observe()` to obtain it. Requalification accepts the complete
retained projection; it does not create a fresh observation from old claims.

Package selectors require exact `ecosystem` and `name` and optionally exact
`version`, a typed `version_predicate`, and declared `context`. Exact `version`
and `version_predicate` are mutually exclusive. Package-name matching is
ecosystem-qualified: PyPI queries and component names use native
`packaging.utils.canonicalize_name`, while npm, scoped npm and other opaque
ecosystem names retain exact spelling. This changes query matching only;
declared component names, component IDs and selection IDs remain unchanged.
`MLFlow` matches `mlflow`; `ML_Flow` matches `ml-flow`, not `mlflow`.
`@scope/ml_flow` remains distinct from `@scope/ml-flow` in npm.
Unknown contexts and unknown selector fields are rejected.
Requests normalize, sort and deduplicate selectors and repository-relative paths.

The public `hashmarks.dependency_package_query_identity(ecosystem, name)` call
returns the original requested spelling, canonical query name, semantic rule and
native engine/version provenance without reading a repository or registry. Each
projected package retains the same `package_identity` evidence alongside its
original selector. **OBSERVER:** this is package-coordinate correspondence over
declared dependency facts; it grants no installation, resolution or execution
authority. Query equivalence never merges distinct retained component IDs or
strengthens bounded matches into uniqueness.

Retained requalification checks name semantics as well as version-predicate
semantics before source work. A packet missing that evidence, or one whose
native name engine/semantics changed, requires a fresh projection; it is not
silently reinterpreted with the new matching rule.

Python consumers use the existing `uv_lock_dependency_observation()` adapter,
including explicitly supplied `METADATA` and `RECORD` when module ownership is
needed. The projection reuses those same qualified observations and
`dependencies.consumers()`; it does not introduce a parallel Python path.

## Ecosystem-qualified version predicates

For an already-qualified Python dependency observation, select a predicate with
the same public projection call:

```python
filtered = repository.dependencies.projection(
    observation,
    packages=[
        {
            "ecosystem": "pypi",
            "name": "example-package",
            "version_predicate": {
                "dialect": "pep440",
                "expression": ">=1.2,<2",
                "prereleases": False,
            },
        }
    ],
    limit=10,
)
```

Python/`pypi` uses PyPA `packaging`'s `SpecifierSet` and `Version` semantics.
The `pep440` predicate has an explicit `prereleases` boolean, defaulting to
`False`; set it to `True` when prereleases belong in the selected predicate.
Epochs, post-releases, local versions and compatible-release operators retain
those library semantics. JavaScript/`npm` uses the separate `npm-semver` dialect
and the selected `node-semver` library's `Range.test`; its native prerelease rules apply and a
`prereleases` field is invalid. An empty expression uses the selected library's
unrestricted-range syntax under that dialect's prerelease rules.

The npm interpreter uses a qualified Node-compatible port profile: version and
endpoint text is at most 256 characters, while numeric version components and
numeric prerelease identifiers are at most JavaScript's safe integer limit
(`2**53 - 1`). Native Node can accept larger numeric prerelease identifiers;
those inputs remain unclassified here because their comparison is outside the
qualified port profile. Versions with extra numeric release components and
other out-of-profile inputs also remain unclassified. The producer does not
repair unsupported port arithmetic with a separate comparator.

Every package candidate is classified before result bounds. `matches` contains
bounded matching selections and `match_count` counts all observed matches.
The package's `version_predicate` packet retains the exact expression, dialect,
ecosystem, prerelease policy, interpreter contract and library version in its
`predicate_identity`. It reports full `match`, `nonmatch` and `unclassified`
counts, bounded per-selection classifications and their raw versions, omitted
selection count and disclosure truncation. A matching version beyond the first
page of nonmatching versions is therefore still returned in `matches`.

Unknown ecosystems, mismatched dialects, unsupported syntax and versions that
the selected library cannot interpret remain `unclassified`. Invalid request
types or undeclared fields are rejected. Raw observed version strings are
preserved. The predicate's selection-scope completeness and its classification
availability remain separate from projection truncation and source currentness.
Its `negative_evidence` is always `not-admissible`.

Package `contexts` and `current_inventory` use the complete package-presence
candidate set before predicate filtering. A version nonmatch does not turn a
present package into an absent one. Source consumers cover only the returned
matching nodes; the full counts retain unclassified and omitted selections.
Overall consumer scope remains incomplete.

Requalification checks the retained predicate and engine evidence before reading
current Source inputs and verifies the same interpretation after projecting
the selections. A changed library version or interpretation contract requires
a fresh projection. Source-input drift keeps the original selected versions
as historical facts while current membership and consumer qualification retain
their normal stale/unknown behavior.

### Observer ownership

Observed repository fact/evidence: whether each supplied dependency selection's
version satisfies an explicit ecosystem-qualified predicate.
Authority source: qualified v3 selection/context facts and established native
library semantics, bound by the predicate's content identity.
Completeness/freshness behavior: classify the declared package universe before
projection; preserve source correspondence, unclassified versions and omissions.
Existing Hashmarks owner extended: dependency package queries and retained
projection/requalification; the pure predicate interpreter owns no inventory.
Consumer/execution responsibility: advisory choice, severity, remediation, Fleet
population, admission and execution remain external.
Decision: **OBSERVER**.

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
