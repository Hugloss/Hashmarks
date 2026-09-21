# Responsibility-First Refactoring and Complexity Policy

## Purpose

Hashmarks does not refactor to minimize lines of code. Large LOC, Ruff debt, branch counts, long functions, wide APIs, repeated edits, and difficult tests are **signals to investigate**. The objective is lower accidental complexity with stronger cohesion, ownership clarity, discoverability, deterministic behavior, and repository-intelligence boundaries.

This policy is the mandatory gate before any "reduce the biggest files", naming cleanup, or complexity-debt phase.

## Product boundary first

Hashmarks owns repository intelligence: repository identity, relationships, ownership/impact evidence, retrieval, evidence packets and receipts, evidence freshness, repository qualification, consumer conformance, and evidence economics. It does not own process execution, admission, sandbox/runtime authority, retries/resume orchestration, certification, release promotion, or the coding-agent solution loop.

A refactor must never move an external-harness or Oh-Goon responsibility into Hashmarks merely because doing so makes local code easier to organize. Interoperability transfers information, never authority. This follows the permanent evidence-versus-authority split: Hashmarks describes repository truth; execution systems decide what may run.

## Investigation signals

Use several signals together. No single metric proves that a split is needed.

### Function/control-flow signals

Measure at least:
- function length;
- cyclomatic/branch complexity (Ruff `C901`, `PLR0912` and the local AST branch proxy);
- returns, statements, locals and arguments (`PLR0911`, `PLR0915`, `PLR0914`, `PLR0913`);
- nesting and compound boolean conditions;
- mutable/shared state touched;
- number of independent invariants coordinated by one function.

`uv run --offline python scripts/ruff_debt.py` is the repository-wide complexity inventory. Ruff debt is diagnostic and a ratchet; historical Ruff-zero is not itself a promotion objective.

### File/responsibility signals

Inspect:
- number of domain concepts owned;
- public API/schema surface;
- internal dependency graph;
- external dependencies;
- state/cache ownership;
- frequency of unrelated changes landing in the same file;
- testing difficulty and fixture breadth;
- whether a blind maintainer can predict the owner from the filename.

### Runtime/economics signals

Where relevant, measure repeated scans, N+1 queries, parsing, sorting, set construction, serialization, cache misses, persistence amplification, and cold/warm/incremental economics. Performance evidence may motivate internal refactoring, but must not hide evidence or change authority semantics.

## Mandatory classification

Every reviewed candidate ends with exactly one decision:

**KEEP COHESIVE** — one coherent responsibility; do not split for LOC.

**REFACTOR INTERNALLY** — ownership is cohesive, but functions/control flow are too complex. Extract responsibility-named internal stages while retaining one module owner.

**EXTRACT RESPONSIBILITY** — a stable, independently understandable responsibility has its own natural owner and one-way dependency boundary.

**DECOMPOSE MULTIPLE RESPONSIBILITIES** — the file owns multiple genuine domain responsibilities that should have separate owners.

## Extraction acceptance gate

For every module extraction record:
1. responsibility extracted;
2. proposed responsibility-based filename;
3. why the name reveals ownership;
4. responsibility remaining in the original module;
5. dependency direction;
6. measured complexity/discoverability improvement;
7. public API/schema/identity/serialization/exception contracts preserved;
8. state/cache authority after the split.

Reject an extraction that creates forwarding-only modules, `*_helpers`, `*_utils`, `*_core`, `*_impl`, `*_internal`, numbered fragments, circular dependencies, duplicated caches/state, awkward parameter plumbing, or scatters one invariant.

## Internal-refactor acceptance gate

Internal helpers/stages must be named for the responsibility they perform, not their historical position in a long function. The orchestration function should read as the domain workflow. Complexity must actually fall rather than merely move into an unnamed helper.

It is acceptable for a file to become longer when explicit stages make ownership and invariants clearer. LOC is not the optimization target.

## Contract preservation

Unless a phase explicitly changes a contract, preserve:
- public imports and call signatures;
- serialized schema names and fields;
- deterministic identities and ordering;
- repository/evidence freshness semantics;
- exception/fail-closed behavior;
- cache ownership and invalidation rules;
- qualification behavior;
- Hashmarks' repository-intelligence-only product boundary.

Compatibility aliases may preserve v0.11 public names, but new internal names should converge on responsibility-owned vocabulary.

## Qualification protocol

Two evidence gates are now mandatory before a complexity owner can close:

- **Exact direct-test ownership:** the selected production owner must have at least one confirmed direct owning test or an explicit unresolved ownership item. Exact first-party static re-exports may establish ownership only when the symbol resolves unambiguously to one defining source; naming similarity or facade adjacency is not authority.
- **Complete structural-locality evidence:** behavior preservation plus lower Ruff debt is insufficient when new internal structure is introduced. Pre/post locality must be comparable and complete; unresolved repository call targets keep the phase open rather than being waived. Every introduced helper/stage must bind an independent responsibility value, and observed caller count <= 1 remains review evidence only, never proof of global single-use.
  A bounded observer reporting `call-limit-reached`, `reference-limit-reached`, or an equivalent truncation state is incomplete measurement, not semantic ambiguity and not locality success. Raise the explicit bound within the supported limit and rerun the same scope; do not shrink navigation depth merely to make the receipt pass.
- **Behavior-preservation closure:** BP1 freezes exact pre-edit source identity, direct owning test bytes, behavior boundaries, and the broader repository gate. BP2 must replay unchanged frozen test bytes against the complete changed/new production source set, bind the same post-edit repository identity used by locality evidence, execute the declared broader gate on that state, and combine the preservation receipt with comparable pre/post analyzer measurements. Lower Ruff debt alone never closes a phase.
  Verification must use the repository-owned test materialization needed by the exercised runtime surface. A dependency-only environment is not equivalent when tests require installed entry points, console scripts, generated artifacts, or other project-owned runtime bytes; mirror the repository CI/setup contract instead of skipping those tests.

For each phase:
1. freeze the exact parent artifact identity;
2. record pre-change complexity metrics for the selected owner;
3. make one bounded responsibility change;
4. run focused semantic tests for the owner;
5. run the Ruff debt inventory/ratchet as diagnostic evidence;
6. run source compileall;
7. build the candidate deterministically;
8. test the exact extracted candidate with the same focused ring;
9. rebuild independently and compare bytes when producing a persistent checkpoint;
10. persist an audit describing classification, before/after metrics, contracts, tests, and next measured target.

Host/controller timeout is **INCOMPLETE**, not product failure. Use bounded qualification shards; do not rerun already proven work solely because a later host window expired.

## Blind-maintainer navigation review

After each refactor ask:
- Can an engineer with no historical context find the owner from the bug/concept?
- Is the filename more informative than the source filename plus a suffix?
- Are related invariants still close enough to understand together?
- Did complexity fall, or only move?
- Did we create tiny modules that make navigation worse?
- Could this name be confused with Oh-Goon execution authority?

## Hashmarks refactoring phases from BN

Starting authority: exact DEVELOPMENT BN. These phases are ordered by measured complexity, not file length.

### RCR-01 — Indexing lifecycle orchestration
Review `hashmarks/codemap/indexing_lifecycle.py::sync` (BN: 212 lines / ~30 AST branch nodes; Ruff `C901=55`, `PLR0912=30`, `PLR0914=61`, `PLR0915=129`). Decision: **REFACTOR INTERNALLY**. Keep indexing lifecycle cohesive; extract responsibility-named stages for persistence/indexing and later preparation/finalization only when each reduces orchestration complexity without transferring state authority.

### RCR-02 — Index discovery and surface classification
Review `_discover`, `_discover_subtree`, and `_index_surface_for_path` together. Determine whether discovery policy is one cohesive indexing-admission responsibility or whether surface classification is an independently reusable repository-evidence concept. Do not extract based on function count.

### RCR-03 — Change-impact evidence projection
Review `change_impact.py`, especially `_change_impact_surface_state`, `_change_impact_owner_chain`, and `task_agent_change_impact`. Preserve the rule that Hashmarks reports impact evidence; it does not execute recovery or verification.

### RCR-04 — Evidence decision packet
Review `evidence_decision_packet.py::task_decision_packet`. Prefer internal responsibility stages before any module split. Preserve packet schemas and deterministic selection semantics.

### RCR-05 — Evidence packet construction
Review branch-heavy `evidence_packet.py` functions. The module is presumptively cohesive; extract only a genuine separately named evidence responsibility, never `packet_helpers`.

### RCR-06 — Evidence graph resolution
Review import/re-export resolution and file-graph construction. Keep qualified identity and freshness authority centralized unless a stable resolver owner is demonstrably independent.

### RCR-07 — CLI command-family ownership
`cli.py` is the known **DECOMPOSE MULTIPLE RESPONSIBILITIES** candidate. Split only by stable command families with discoverable names and preserved CLI behavior, not `cli_partN`.

### RCR-08 — Re-inventory and stop condition
Re-run the full complexity inventory. Continue only where measured complexity plus responsibility review identifies a real problem. A large cohesive file with bounded functions is not unfinished work.

## Governing rule

**Large LOC is a signal to investigate, not proof that a file should be split. Split by responsibility and ownership; reduce complexity where complexity actually exists; name modules so a future engineer can find the correct owner; and never trade Hashmarks' repository-intelligence boundary for a cleaner local shape.**

## Execution status after BO

- RCR-01: CLOSED in BO — indexing lifecycle orchestration internally decomposed.
- RCR-02: REVIEWED / KEEP COHESIVE — no extraction justified.
- RCR-03: REVIEWED — BN internal decomposition remains sufficient; no churn.
- RCR-04: CLOSED in BO — evidence decision packet internally decomposed.
- RCR-05: CLOSED in BP — evidence packet construction remains cohesive; selected-row/verification projection and current source-range rebinding are explicit internal responsibilities.
- RCR-06: CLOSED in BP — import resolution remains evidence-graph owned; language-specific resolver stages make identity semantics discoverable without creating a second resolver owner.
- RCR-07: NEXT — CLI command-family ownership review.
- RCR-08: follows RCR-07 — re-inventory and explicit stop/continue decision.
