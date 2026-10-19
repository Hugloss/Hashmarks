# Selected Python and uv manifest declarations

**Status: public explicit declaration provider.**

`PythonUvManifestDeclarations` observes authored Python/uv declarations from
explicitly selected `pyproject.toml` files. The result preserves manifest origins
and declaration scopes using the existing
[repository declaration contract](REPOSITORY_DECLARATIONS.md).
The [dependency evidence owner](DEPENDENCY_EVIDENCE.md) continues to qualify
resolved selections and graphs supplied by dependency adapters.

## Public Python usage

```python
from hashmarks.codemap import CodeMap, PythonUvManifestDeclarations

with CodeMap(".") as repository:
    repository.index.sync()
    declarations = repository.declarations.discover(
        [
            PythonUvManifestDeclarations(
                paths=(
                    "pyproject.toml",
                    "packages/demo/pyproject.toml",
                )
            )
        ]
    )
```

Every selected manifest is read through the revision-bound provider context.
The provider does not scan the repository for additional manifests. Explicitly
selected manifests remain observable even when their directory does not match
a selected workspace declaration.

The result is `hashmarks.repository-declaration-discovery.v1`. Each group scope
contains `manifest_path`, `project_directory` and an exact `toml_key` array. A
declaration's normalized `binding_id` points to its evidence under
`declarations.repository_evidence.bindings`. Manifest evidence uses existing
whole-member bindings with exact member revisions. TOML key origins do not
pretend to be inferred physical line spans.

## Supported declarations

| Authored source | Preserved facts |
| --- | --- |
| `[project]` | Static name, version and `requires-python` strings; the explicit dynamic metadata list |
| `[project.scripts]` | Each script name and literal target string, separately attributable to its manifest |
| `project.dependencies` | Every raw requirement and its ordinal, including duplicates and marker text |
| `[project.optional-dependencies]` | Requirements in each distinct extra |
| `[dependency-groups]` | Direct requirements and `include-group` declarations, including missing or cyclic references |
| `[build-system]` | Authored requirements, backend and backend paths |
| `[tool.uv.sources]` | Named source alternatives, markers and authored source attributes; unsupported keys are listed |
| `tool.uv.dev-dependencies` | Direct authored legacy development requirements in their own scope |
| `[tool.uv.workspace]` | Member/exclude patterns and qualified matches against selected present candidate manifests |

Requirements are preserved as authored strings. The provider does not parse
them into a second normalized dependency representation, evaluate markers,
select versions or judge satisfaction. Two manifests declaring the same
package retain two attributable declarations. Group includes are direct
references only: the provider reports whether the exact target key is present
in that manifest's parsed group table, but does not recursively flatten groups,
normalize group-name equivalence, choose ordering or interpret cycles as an
effective dependency set.

Dynamic metadata values, script importability, installed launcher behavior,
build-backend execution and effective uv source selection remain unestablished.
The provider validates its supported field shapes; it does not certify native
packaging validity. Unknown source keys remain visible rather than acquiring
native interpretation.

## Workspace candidates and native membership

Static matching reuses the existing uv workspace candidate predicate, now
shared with import-root discovery through `hashmarks.codemap.uv_workspace`.
It uses the existing normalization and `fnmatchcase` predicate against the
candidate's project-directory path relative to the declaring manifest. The
declaring project is included; explicit exclusions override member-pattern
matches for other candidates. This is the existing Hashmarks candidate-filter
subset, including its wildcard behavior, rather than an implementation of all
native uv glob/discovery semantics.

`static_candidate_matches` contains only nominated, present manifests.
`matches_declared_patterns` is a scoped static predicate, not a statement about
effective workspace membership. If no `members` key was declared, the predicate
is `null` rather than an inferred empty membership. Each workspace group binds
the declaring manifest and all candidate manifests that support its output.
No unobserved path is ruled out by a selected candidate list.

`effective_workspace_membership="not-established"` remains independent of
successful static matches. Native uv retains effective discovery, configuration
and workspace semantics. This provider does not accept a field that upgrades a
declared pattern into native attestation.

## Comparing intent with supplied lock evidence

The existing public `hashmarks.adapters.uv_lock_dependency_observation` remains
the translation boundary for supported already-produced lock bytes. Observe
the lock through Source, pass the exact nominated repository inputs to that
adapter, and qualify the resulting claim through `repository.dependencies`:

```python
from hashmarks.adapters import uv_lock_dependency_observation

lock_member, lock_bytes = repository.source.member("uv.lock", include_bytes=True)
if lock_member["state"] != "known-present" or lock_bytes is None:
    raise ValueError("selected lock evidence is unavailable")

inputs = [
    {"path": row["path"], "member_revision": row["member_revision"]}
    for provider in declarations["providers"]
    for row in provider["inputs"]
    if row["state"] == "known-present"
]
inputs.append({"path": "uv.lock", "member_revision": lock_member["member_revision"]})
resolved = repository.dependencies.observe(
    uv_lock_dependency_observation(lock=lock_bytes, repository_inputs=inputs)
)
```

These input claims establish repository-source correspondence. They do not
prove that uv ran against those manifests or that the supplied lock satisfies
the authored requirements. Declaration groups retain
`lock_correspondence="unresolved"`; matching names alone never invent semantic
equality between a requirement and a selected version.

Declaration-only and lock-only observations remain independent. Missing or
unsupported lock evidence does not erase successfully observed declarations.
The existing lock adapter retains its root identification, ambiguity and
unsupported-format behavior. The manifest provider neither parses locks nor
misclassifies its declared application project as an external transitive
dependency.

## Freshness, coverage and bounds

A root or member edit changes that input's revision even when lock bytes are
unchanged. Existing Source/discovery qualification rejects stale indexed bytes;
after the caller refreshes the changed paths, `previous_observation` supplies
an explicit comparison endpoint and `delta_from_previous` reports the change.
Comment-only edits can change source observation identity while retaining
equivalent normalized declaration values and semantic subjects.

Bounds are 16 explicitly selected manifests, 262,144 bytes per manifest, 256
entries per supported table/array and the existing 128 group limit. Declaration
packet-size and evidence bounds still apply. Invalid TOML, unsupported required
field shapes, over-bound input, denied source and unstable provider inputs fail
the observation rather than producing partial successful evidence.

Missing selected paths are reported in provenance. An empty parsed manifest or
an all-missing selection can return no declaration groups, with explicit
incomplete scope and `negative_evidence_admissible=false`. Neither can prove
repository-wide absence. Group `value_state="resolved"` refers only to observed
authored syntax; native interpretation and cross-artifact correspondence remain
unestablished or unresolved.

## MCP and consumer example

The registered `repository_declarations` MCP tool accepts:

```json
{
  "groups": [],
  "result_mode": "discovery",
  "source_selection": {
    "python_uv_manifest_paths": [
      "pyproject.toml",
      "packages/demo/pyproject.toml"
    ]
  }
}
```

Direct Python and this registered MCP adapter use the same provider. Dedicated
CLI flags and service-client parity are not claimed by this addition.

The [standalone example](../../examples/python_uv_manifest_declarations.py)
creates a neutral temporary workspace, observes two declaration origins and a
supplied lock, changes a member's script target, and exposes the resulting
mismatch against the previous nominated source inputs. No package installation,
resolution, project imports or entry-point execution occur. Run with the
Hashmarks project environment materialized:

```sh
uv run --frozen --no-sync python examples/python_uv_manifest_declarations.py
```

## Observer ownership note

```text
Observed repository fact/evidence: Selected Python/uv manifest declarations, script targets, dependency origins and nominated static workspace candidate matches.
Authority source: Exact admitted manifest bytes through RepositoryDeclarationProviderContext; resolved evidence remains supplied through the existing uv lock adapter.
Completeness/freshness behavior: Selected supported syntax only; unknown native semantics remain unknown; bounds fail closed; all contributing manifests retain canonical revision bindings and existing deltas.
Existing Hashmarks owner extended: RepositoryDeclarations provider boundary, canonical Source, shared uv workspace candidate predicate and existing Dependencies correspondence.
Consumer/execution responsibility explicitly not acquired: Native package resolution, effective workspace discovery, requirement satisfaction, imports, installation, lock mutation, execution and capability policy.
Decision: OBSERVER
```
