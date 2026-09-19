# Repository evidence bindings

**Status: current public repository-intelligence contract.**

Repository evidence bindings let a consumer give Hashmarks an opaque binding identifier plus explicit repository evidence scopes and receive deterministic, freshness-bound repository facts. Hashmarks does not interpret what the binding means to the consumer and does not decide whether a changed binding requires execution, certification, retry, or any other action.

## Public Python surface

The supported entry point is the exported **CodeMap** class:

~~~python
from hashmarks import CodeMap

bindings = [
    {
        "binding_id": "consumer:contract-a",
        "evidence": [
            {"path": "src/owner.py", "start_line": 10, "end_line": 14},
            {"scope": "member", "path": "uv.lock"},
        ],
    }
]

with CodeMap(".") as codemap:
    codemap.sync()
    packet = codemap.repository_evidence_bindings(
        bindings,
        dependency_paths={
            "consumer:contract-a": ["pyproject.toml"],
        },
    )
~~~

The binding ID is opaque. Hashmarks never derives policy from its spelling.

## Evidence scopes

Two explicit scope forms are supported.

### Exact physical line range

~~~json
{"path": "src/owner.py", "start_line": 10, "end_line": 14}
~~~

Line numbers are one-based and inclusive. Physical lines are split on the LF byte only. CRLF bytes are preserved, a missing final LF is preserved, UTF-8 BOM bytes remain part of the first line, and Unicode separators such as U+2028/U+2029 do not create repository line boundaries.

Text ranges require valid UTF-8 and source-visible repository evidence. A denied or outline-only member cannot be upgraded to raw source evidence through this API.

### Whole repository member

~~~json
{"scope": "member", "path": "uv.lock"}
~~~

Whole-member evidence does not assume text and therefore works for empty, binary, generated, lock, and other repository members. It reports the canonical member revision without creating a fake line locator.

Evidence scopes are explicit. This contract does not perform hidden glob expansion.

## Canonical member observation

Bindings reuse the same repository member observation and stable-read authority as the rest of Hashmarks. A member observation separates:

- member presence;
- indexing state;
- evidence visibility;
- member revision;
- locator state for line evidence;
- content state for line evidence.

A filesystem change that does not match the indexed member revision fails closed as **unknown** rather than producing a generation-bound range identity over mismatched bytes.

Relevant observation states follow the repository-intelligence vocabulary documented in [STATE_AND_SEMANTIC_OWNERS.md](STATE_AND_SEMANTIC_OWNERS.md).

## Binding definition and observation identities

Each binding carries two different identities:

- **binding_definition_identity** — the consumer declaration: binding ID, explicit evidence scopes, declared dependency paths, and relationship observation settings;
- **binding_observation_identity** — repository evidence observed for that definition.

Changing a declaration or relationship bound is definition/observation-configuration change. It is not silently reported as repository content change.

The complete packet uses schema **hashmarks.repository-evidence-bindings.v1** and carries **bindings_identity**, repository identity, source identity, CodeMap generation, identity generation, canonical observer capability identity, and **current | stale | unknown** freshness.

## Declared dependencies

The optional **dependency_paths** mapping declares explicit repository members associated with a binding. Hashmarks reports their member observations and revisions.

These are **declared dependencies**, not inferred semantic dependency closure. The delta schema therefore uses the field **declared_dependencies**.

## Relationship evidence

When **include_relationships=True**, Hashmarks projects bounded indexed repository relationships for the bound evidence paths. Relationship rows reuse canonical relationship evidence identities and provenance.

The relationship projection is explicitly bounded. Changing **relationship_limit_per_path** changes the binding definition/observation configuration; it does not by itself establish a repository relationship change.

Set **include_relationships=False** for the cheaper evidence-only path.

## Binding delta

Compare two binding packets with:

~~~python
delta = codemap.repository_evidence_binding_delta(before, after)
~~~

Schema: **hashmarks.repository-evidence-binding-delta.v1**

The delta keeps independent dimensions separate:

- direct evidence;
- containing member evidence;
- declared dependencies;
- relationship evidence;
- binding definition.

An edit elsewhere in a containing member may therefore produce:

~~~text
direct_evidence.state = preserved
member_evidence.state = changed
~~~

without falsely claiming the bound line range changed.

Relationship facts are compared by their repository relationship evidence identities. Relationship locator movement, observation bounds/configuration, and observer-capability change are reported separately. When observer capability or relationship observation configuration differs, relationship facts are conservatively non-comparable rather than manufactured as repository additions/removals.

## Change coverage and per-binding impact

Use:

~~~python
coverage = codemap.repository_evidence_coverage(
    current_packet,
    changed_paths=["src/owner.py"],
    change_set_complete=True,
    binding_delta=delta,
)
~~~

or supply a typed **RepositoryObservation** with **repository_observation=** when change-set completeness comes from the atomic repository observer.

Schema: **hashmarks.repository-evidence-coverage.v1**

Coverage preserves the source of change-set completeness. Completeness uses its own `complete | incomplete | unknown` axis rather than presence/freshness words:

- **repository-observer** — completeness comes from an atomic Hashmarks repository observation;
- **caller-asserted** — completeness is an explicit caller assertion.

Incomplete change observations never prove that a changed path is outside all declared bindings.

The packet includes **binding_impacts**, keyed by opaque binding ID, with stable repository-evidence reason codes such as:

- **bound-range-content-changed**;
- **bound-member-content-changed**;
- **bound-member-changed**;
- **bound-member-added**;
- **bound-member-removed**;
- **bound-member-observation-state-changed**;
- **bound-locator-changed**;
- **declared-dependency-changed**;
- **declared-dependency-path-changed**;
- **relationship-evidence-changed**;
- **relationship-locator-changed**;
- **relationship-observation-config-changed**;
- **binding-definition-changed**;
- **bound-member-precision-unknown**.

These are evidence classifications. They are not instructions to run, retry, certify, or invalidate consumer work.

## Bounds

The producer rejects requests beyond the current explicit bounds:

- 256 bindings;
- 256 evidence references per binding;
- 512 declared dependency paths per binding;
- 2,048 unique repository paths per request;
- relationship limit per path between 1 and 1,000.

The exact bounds are part of the current pre-1.0 Python contract and may evolve only with the normal public contract/change process.

## Determinism

Where declaration order has no semantic meaning, Hashmarks canonicalizes ordering before identity construction. Duplicate and overlapping evidence declarations remain explicit evidence; they are not silently deduplicated.

## Authority boundary

Repository evidence bindings are read-only repository intelligence.

They may expose repository facts, identities, relationships, freshness, completeness, uncertainty, provenance, and deltas. They do not acquire consumer reasoning, workflow, admission, execution, result, or certification authority.
