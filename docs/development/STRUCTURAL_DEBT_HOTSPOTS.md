# Structural Debt Hotspot Closure

## Purpose

This branch is limited to structural-debt reduction in three production CodeMap hotspots. It must improve maintainability without changing Hashmarks authority, retrieval semantics, public payloads, freshness behavior, ambiguity policy, or product scope.

Branch base: `main` at `5a95266bf34383b7e42c2da14d6f67a1df144c88`.

Measured starting debt from `ruff-debt-baseline.json`:

| File | Starting excess |
| --- | ---: |
| `hashmarks/codemap/task_action_projection.py` | 294 |
| `hashmarks/codemap/change_impact.py` | 202 |
| `hashmarks/codemap/import_resolution.py` | 194 |

The branch goal is to drive these three files as close to zero structural excess as can be safely proven, preferably to zero. Repository-wide debt outside these three files is out of scope for this branch.

## Hard rules

1. Work one bounded refactor at a time: small change -> focused behavior/adversarial proof -> CI proof -> exact debt measurement -> baseline ratchet -> next change.
2. Do not stack a second production refactor on an unqualified commit.
3. If a refactor exposes weak understanding or insufficient coverage, stop the refactor and strengthen behavior/adversarial tests while the code is still in its known shape. Resume only after those tests are green.
4. Never reduce debt by adding `# noqa`, per-file ignores, broad exception swallowing, higher Ruff thresholds, weaker tests, or a total-only debt allowance.
5. Do not hand-wave a lower aggregate. `ruff-debt-baseline.json` remains a per-file downward-only authority and is regenerated/ratcheted only from measured state.
6. Preserve Hashmarks' product boundary: repository intelligence only. Do not add orchestration, execution, repair selection, test execution, scheduling, or agent-control responsibility.
7. Prefer cohesive state objects and responsibility extraction over trivial one-line helper proliferation. A split must represent a real ownership boundary.
8. Preserve externally visible schemas, deterministic ordering, bounds, cache identity, provenance, freshness, ambiguity, and fail-closed behavior unless a separately justified product change is explicitly approved.
9. Do not mix unrelated test-value cleanup, documentation cleanup, dependency work, or performance experiments into this campaign.

## Phase 0 - Freeze the behavioral authority

Before changing each hotspot, identify and run its existing focused proof surface. Add tests only where a concrete invariant is not already protected. Tests must assert behavior/authority, not implementation spelling.

Common gates for every production step:

- `make ruff`
- focused pytest owners for the changed responsibility
- `make lint-debt-gate`
- `make compile`
- normal CI on the exact commit

After a production refactor qualifies, measure the exact structural-debt delta. Ratchet the baseline in a separate commit and qualify that commit before the next production refactor.

## Phase 1 - `import_resolution.py` (194)

Do this first. Its authority is comparatively narrow and its adversarial tests are already strong, which makes it the safest place to establish the refactoring pattern for the larger files.

### Invariants to freeze

- Import ambiguity is evidence of uncertainty, never a reason to select an arbitrary owner.
- Python top-level binding authority remains syntax-sensitive and scope-sensitive.
- A dynamic, ambiguous, cyclic, or depth-bounded re-export chain remains unresolved/fail-closed.
- The re-export walk remains explicitly bounded to eight hops.
- Multiple module owners never collapse into deterministic Python ownership by path ordering.
- `from x import *` is authoritative only when the exported name can be proved from static `__all__` or the existing symbol evidence rules.
- Relative Python import candidate order and fallback semantics remain unchanged.
- JavaScript/TypeScript resolution remains exact workspace-relative resolution with the same suffix/index candidate order.
- Go resolution remains module-bound and package-local; no broad repository guessing is introduced.

### Existing proof owners

Use at least:

- `tests/test_import_identity_normalization.py`
- `tests/test_import_ownership.py`
- `tests/test_import_resolution_responsibility.py`
- `tests/test_reexport_binding_authority.py`
- `tests/test_src_layout_import_authority.py`
- `tests/test_ownership_import_path_session_reuse.py`
- `tests/test_polyglot_owner_resolution.py`
- relevant exception-boundary tests

If cycle handling, dynamic `__all__`, multiple re-export ambiguity, or the eight-hop bound is not directly exercised, add the missing behavior test before moving that logic.

### Refactor sequence

#### 1.1 Isolate Python binding analysis

Extract cohesive internal helpers/state for top-level binding analysis instead of keeping assignment/import/re-export classification intertwined with traversal. The owner remains import resolution; this is not a new authority layer.

Target responsibilities:

- direct local binding recognition;
- direct/star re-export target collection;
- duplicate/ambiguous re-export detection;
- static `__all__` interpretation.

Prefer small typed result objects where they eliminate repeated tuples/flags and make `unknown`/`ambiguous` explicit.

#### 1.2 Remove nested `__all__` parser complexity

Move static-name parsing out of `_python_star_export_authority()` into a pure helper. Keep every current fail-closed condition: unsupported mutation, dynamic values, invalid call form, delete, and unresolved owner.

#### 1.3 Replace the nested re-export walk with explicit traversal state

`_resolve_import_owner_evidence()` currently owns leaves, visited nodes, unresolved state, recursion, depth, binding interpretation, and owner expansion in one closure. Replace this with a cohesive traversal state/result and a bounded traversal helper.

The traversal must retain:

- `(facade_path, exported_name)` cycle identity;
- the eight-hop ceiling;
- exact unresolved propagation;
- one unique qualified leaf as the only successful qualified owner;
- bounded target/owner fan-out;
- Python fail-closed behavior when top-level binding cannot be proved.

Do not convert uncertainty into empty-success semantics.

#### 1.4 Simplify language dispatch/candidate construction only where useful

After Python authority is qualified, reduce remaining branch/local debt in Python, JS/TS, Go, and dispatch functions. Do not force a shared abstraction across languages when their resolution semantics differ.

### Phase exit

- all focused import/re-export/polyglot tests green;
- exact behavior and ordering unchanged;
- `import_resolution.py` debt is materially lower, ideally zero;
- no structural-debt increase in any other production file;
- baseline ratcheted to measured state in a separate qualified commit.

## Phase 2 - `change_impact.py` (202)

Do this second. The largest structural smell is not just function size: `_change_impact_surface_state()` returns collections plus three nested functions, making state mutation and authority boundaries implicit.

### Invariants to freeze

- `task_change_impact()` remains repository evidence only; it never selects repairs, executes verification, judges a patch, or schedules work.
- caller-reported paths remain the only post-change sync scope.
- declared-project topology refresh/rebind behavior remains freshness-bound and provider-specific.
- impact surfaces remain bounded by depth, per-surface count, and project-impact count.
- duplicate `(role, path)` entries remain suppressed deterministically.
- adding verification metadata to an existing row preserves the selected-row semantics.
- owner-chain reuse remains generation/task/bounds scoped inside decision sessions.
- owner-chain reconstruction remains fail-soft only for the currently allowed ownership-graph failures.
- project impact ordering/provenance remains deterministic.
- compact and verbose project-impact encodings remain semantically equivalent.
- public payload keeps `authority: advisory`, `owner: external`, and `completeness: not-claimed`.

### Existing proof owners

Use at least:

- `tests/test_task_change_impact.py`
- `tests/test_change_impact_owner_chain_reuse.py`
- `tests/test_large_repo_reverse_impact.py`
- `tests/test_post_change_delta.py`
- `tests/test_post_change_refresh.py`
- relevant project-impact/freshness tests

Before moving state, ensure there is direct coverage for bounds, duplicate surface insertion, verification metadata promotion, compact/verbose project impact, and decision-session owner-chain reuse.

### Refactor sequence

#### 2.1 Introduce explicit surface accumulation state

Replace the large tuple containing `surfaces`, project collections, and nested `roles`/`visible`/`add` functions with a cohesive internal state object that owns only accumulation mechanics.

Candidate responsibilities:

- classify a path into impact roles;
- check evidence visibility through the existing session boundary;
- perform bounded deterministic surface insertion;
- merge verification metadata into an already-admitted row;
- hold project roots/depths/edges and impacted-project sets.

Do not make the state object a second CodeMap or pass unrestricted repository authority into it. Repository reads should remain explicit through the owning mixin/session boundary.

#### 2.2 Separate project-fragment accumulation

Extract the project-dependent/provenance merge from the changed-path loop into one responsibility. Preserve minimum depth, edge identity `(from, to, kind, producer)`, and existing limits.

#### 2.3 Separate owner-chain impact application

Keep `_change_impact_owner_chain()` cache identity and reconstruction semantics intact, but move the later "changed path intersects owner chain -> add preceding owner path" projection out of the public method.

#### 2.4 Separate verification-impact projection

Isolate the condition that promotes the selected verification path into the verification surface when changed code intersects the task owner chain. Preserve the exact verification-plan metadata fields and availability semantics.

#### 2.5 Make the public method an orchestration boundary

`task_change_impact()` should read as a short sequence:

validate/normalize -> ensure/sync -> refresh declared project evidence -> acquire task-action authority -> accumulate reverse/project impact -> apply owner-chain impact -> apply verification impact -> project public payload.

Move public result construction into a cohesive projection helper only if it reduces complexity without hiding authority decisions.

### Phase exit

- all focused change-impact and freshness tests green;
- exact bounds, ordering, cache identity, and public schema preserved;
- `change_impact.py` debt materially lower, ideally zero;
- baseline ratcheted downward from measured state in a separate qualified commit.

## Phase 3 - `task_action_projection.py` (294)

Do this last. It has the highest debt and the broadest decision surface. The file encodes retrieval-preserving projection, explicit surface selection, structural ownership, verification relevance, ambiguity, stale-evidence rejection, public payload construction, and decision-session caching. It must not be split mechanically.

### Invariants to freeze

- `find_task()` remains canonical retrieval authority.
- task-action projection never reranks canonical task evidence and does not manufacture paths outside the permitted existing evidence mechanisms.
- canonical rank and provenance remain preserved in output rows.
- decision-session cache identity remains generation + task + limit + per-role and cached outputs remain deep-copy isolated.
- explicit test/build/config surface selection behavior remains unchanged.
- literal SQL and exact-identifier ownership behavior remains unchanged.
- archive/live-owner discrimination and exact-identifier displacement guards remain fail-closed.
- structural-owner resolution keeps its current task-local and language-specific semantics.
- verification relevance remains an existing authority input, not a new retrieval authority.
- ambiguity flags, reasons, candidate ordering, structural-owner evidence, and verification-origin evidence remain behaviorally identical.
- stale durable owner evidence must never regain safe-to-edit authority; stale edit evidence must clear edit/owner authority and emit `stale-edit-evidence`.
- public schema remains `hashmarks.task-action-map.v1` with the same bounds/ranking/discovery semantics.
- authority-path and recent-authority caches preserve generation/bounds identity and bounded retention behavior.

### Existing proof owners

Use at least:

- `tests/test_task_action_map.py`
- `tests/test_task_action_brief.py`
- `tests/test_task_action_session_reuse.py`
- `tests/test_task_action_stale_workspace.py`
- `tests/test_exact_identifier_owner_preservation.py`
- `tests/test_structural_owner_resolution.py`
- `tests/test_qualified_identity.py`
- `tests/test_omitted_alnum_task_locality.py`
- `tests/test_config_surface_authority.py`
- `tests/test_ambiguity_quality.py`
- `tests/test_ownership_decision_contract.py`

Because this phase is high risk, add characterization tests before refactoring any branch whose result cannot already be predicted from these owners.

### Refactor sequence

#### 3.1 Separate cache/input context from projection

Extract the decision-session cache lookup/store mechanics and the reusable task-action input context (hits, cues, cue words, strong cue sets, rows, projection/discrimination inputs) only where the grouping is cohesive. Do not hide `find_task()` behind a new retrieval abstraction.

#### 3.2 Make surface-selection state explicit

Replace dictionary-shaped internal phase handoffs where practical with typed internal state representing:

- edit / verify / contract;
- explicit-surface ambiguity;
- explicit-edit selection;
- verification anchors;
- literal-reference owner;
- localized-config state;
- explicit-config request.

This state is internal representation only. Do not change public dictionaries or serialized schema.

#### 3.3 Make structural-owner resolution state explicit

`_task_action_resolve_structural_owner()` currently repeats large dictionary returns across early exits and owns several independent decisions. Introduce one cohesive owner-resolution state/result so early exits return one typed shape.

Then isolate, one at a time:

- literal task-path filtering;
- exact-identifier candidate/displacement logic;
- owner-start selection;
- resolved-owner admission/guard logic.

Every extraction gets focused behavior proof before proceeding.

#### 3.4 Make ambiguity composition explicit

`_task_action_projection_ambiguity_state()` should remain discrimination-only. Reduce its locals/branching by grouping already-computed ambiguity facts into a typed internal evidence/state object, then compose global ambiguity + reason from that object.

Do not merge distinct ambiguity reasons merely to satisfy Ruff. The existing reasons are externally meaningful diagnostics.

#### 3.5 Reduce `task_action_map()` to phase orchestration

The public method should visibly retain this authority order:

validate/cache -> canonical retrieval -> row/projection preparation -> initial surface selection -> discrimination/owner resolution -> contract promotion -> verification relevance -> ambiguity -> stale-evidence fail-closed check -> public payload -> authority caches -> session cache.

The goal is not the fewest lines; the goal is one obvious owner for every phase with fewer locals, statements, branches, and implicit dictionary contracts.

#### 3.6 Consider a file split only after the phase boundaries are proven

Do not begin by moving hundreds of lines into new modules. Once typed state boundaries and focused tests are green, evaluate whether surface selection, owner projection, or ambiguity composition is a genuinely independent internal module.

If moving code across modules causes unclear ownership, import cycles, hidden access to CodeMap internals, or test regressions, stop the split. Keep the improved responsibilities in the existing file and strengthen the boundary instead.

### Phase exit

- complete focused task-action/owner/ambiguity/staleness suite green;
- canonical retrieval, public schema, cache identity, deterministic ordering, and fail-closed semantics unchanged;
- `task_action_projection.py` debt materially lower, preferably zero;
- baseline ratcheted downward from measured state in a separate qualified commit.

## Campaign completion gate

The branch is ready for review only when all three hotspot phases have individually crossed their proof boundary. At minimum:

1. each production refactor was qualified before the next production refactor began;
2. each baseline update was based on exact measured debt and qualified separately;
3. none of the three files exceeds its previous qualified debt at any point;
4. no unrelated production file gained structural debt;
5. focused behavior/adversarial suites are green;
6. full CI is green on the exact branch head;
7. no suppressions, threshold increases, authority weakening, or public-contract drift were used to obtain the reduction.

Preferred final state for this branch:

- `hashmarks/codemap/import_resolution.py`: 0 excess
- `hashmarks/codemap/change_impact.py`: 0 excess
- `hashmarks/codemap/task_action_projection.py`: 0 excess

If one file cannot safely reach zero in this branch, stop at the last qualified downward ratchet and document the remaining concrete ownership problem rather than forcing a cosmetic split.
