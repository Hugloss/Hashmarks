# Responsibility-First Refactoring and Complexity Policy

## Purpose

Hashmarks does not refactor to minimize lines of code. Large LOC, Ruff debt, branch counts, long functions, wide APIs, repeated edits, and difficult tests are **signals to investigate**. The objective is lower accidental complexity with stronger cohesion, ownership clarity, discoverability, deterministic behavior, and repository-intelligence boundaries.

This policy is the mandatory gate before any "reduce the biggest files", naming cleanup, or complexity-debt effort.

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

`make lint-debt` is the repository-wide current complexity and production-size gate. It requires zero findings; it does not compare against historical measurements or grant promotion authority.

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

Unless a refactor explicitly changes a contract, preserve:
- public imports and call signatures;
- serialized schema names and fields;
- deterministic identities and ordering;
- repository/evidence freshness semantics;
- exception/fail-closed behavior;
- cache ownership and invalidation rules;
- qualification behavior;
- Hashmarks' repository-intelligence-only product boundary.

Compatibility is not a reason to preserve obsolete internal spellings. Preserve supported public contracts unless the change explicitly revises them; do not add aliases merely to keep retired internal names alive.

## Qualification protocol

Two evidence gates are now mandatory before a complexity owner can close:

- **Exact direct-test ownership:** the selected production owner must have at least one confirmed direct owning test or an explicit unresolved ownership item. Exact first-party static re-exports may establish ownership only when the symbol resolves unambiguously to one defining source; naming similarity or facade adjacency is not authority.
- **Complete structural-locality evidence:** behavior preservation plus lower Ruff debt is insufficient when new internal structure is introduced. Pre/post locality must be comparable and complete; unresolved repository call targets keep the phase open rather than being waived. Every introduced helper/stage must bind an independent responsibility value, and observed caller count <= 1 remains review evidence only, never proof of global single-use.
  A bounded observer reporting `call-limit-reached`, `reference-limit-reached`, or an equivalent truncation state is incomplete measurement, not semantic ambiguity and not locality success. Raise the explicit bound within the supported limit and rerun the same scope; do not shrink navigation depth merely to make the receipt pass.
- **Behavior-preservation closure:** BP1 freezes exact pre-edit source identity, direct owning test bytes, behavior boundaries, and the broader repository gate. BP2 must replay unchanged frozen test bytes against the complete changed/new production source set, bind the same post-edit repository identity used by locality evidence, execute the declared broader gate on that state, and combine the preservation receipt with comparable pre/post analyzer measurements. Lower Ruff debt alone never closes the work.
  Verification must use the repository-owned test materialization needed by the exercised runtime surface. A dependency-only environment is not equivalent when tests require installed entry points, console scripts, generated artifacts, or other project-owned runtime bytes; mirror the repository CI/setup contract instead of skipping those tests.

For each bounded refactor:
1. freeze the exact parent artifact identity;
2. record pre-change complexity metrics for the selected owner;
3. make one bounded responsibility change;
4. run focused semantic tests for the owner;
5. run the current Ruff and file-size gates as diagnostic evidence;
6. run source compileall;
7. build the candidate deterministically;
8. test the exact extracted candidate with the same focused ring;
9. rebuild independently and compare bytes when producing a persistent checkpoint;
10. record the classification, before/after metrics, contracts, tests, and any unresolved measured target in the change/PR evidence; do not create a parallel phase-history document.

Host/controller timeout is **INCOMPLETE**, not product failure. Use bounded qualification shards; do not rerun already proven work solely because a later host window expired.

## Blind-maintainer navigation review

After each refactor ask:
- Can an engineer with no historical context find the owner from the bug/concept?
- Is the filename more informative than the source filename plus a suffix?
- Are related invariants still close enough to understand together?
- Did complexity fall, or only move?
- Did we create tiny modules that make navigation worse?
- Could this name be confused with Oh-Goon execution authority?

## Governing rule

**Large LOC is a signal to investigate, not proof that a file should be split. Split by responsibility and ownership; reduce complexity where complexity actually exists; name modules so a future engineer can find the correct owner; and never trade Hashmarks' repository-intelligence boundary for a cleaner local shape.**
