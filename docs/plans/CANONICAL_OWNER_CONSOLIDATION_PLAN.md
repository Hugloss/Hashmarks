# Canonical owner consolidation: architecture first

**Status: superseded implementation handoff.** The current plan is
[Canonical component rewrite](CANONICAL_COMPONENT_REWRITE_PLAN.md), including
the user-authorized breaking Python API migration and removal of compatibility
paths. The user has authorized implementation of the component rewrite.

The source-binding, cache-owner, source-read, manifest-admission and metadata
repairs described below have since been implemented and qualified on a repaired
parent. An independent `RepositoryFiles` component has also been started and has
focused proof. The package TODO labels and architecture decisions below describe
the earlier bounded plan; they are not the current worktree status. Use the new
plan's starting-point table before making changes. **Scope:** Hashmarks only.

## 1. Objective and a finishable next milestone

Consolidate the existing architecture so a developer can change one canonical
responsibility, verify its contract, and finish that subgoal without first
completing every backend research catalog. Preserve supported public behavior
and make source, state, cache, and consumer boundaries discoverable.

The immediate milestone is **CO-01 through CO-07**, followed by the selected
integration closure in CO-08. CO-00 is delivered with this plan. Complete one
package at a time and preserve its evidence under its exact candidate identity.
Do not claim that a completed package proves the whole architecture correct.

The twenty-capability 5/5 campaign becomes a later research/qualification track.
Its existing definitions and reports remain intact. Do not change
`backend_matrix.py` minima, thresholds, review flags, required witnesses, or
failed expectations to manufacture a pass. No capability is currently
established at 5/5. Completing this architecture milestone is a different,
explicitly smaller claim; it does not grant a clean release or all-capability
rating.

Full-project typing cleanup is an independent backlog, worked in owner-sized
batches. Last retained full measurements were 2,069 Ty diagnostics and 2,041
Pyright errors. Those historical numbers are not a fresh measurement of future
candidates. No checker configuration, severity, exclusions, unchecked casts, or
blanket `Any` may be changed to hide the debt.

### What stays mandatory for every package

- Exact source/revision binding and non-strengthening evidence authority.
- Existing admission, visibility, freshness, ambiguity and completeness rules.
- Focused positive and adversarial behavior checks for the changed contract.
- No newly introduced typing defects in changed code or its public types.
- Existing public signatures, schemas, operation identity and error semantics,
  unless a separately justified change explicitly revises that contract.
- No execution, workflow, scheduling, certification, Git lifecycle, global
  semantic graph, or consumer-policy responsibility in product code.

### What is not a prerequisite for each local package

Do not add seven missing catalogs, acquire every native producer, rerun all
89 campaign entries, rebuild wheel/sdist installations, or clear all unrelated
typing errors before closing one internal owner repair. Run the proof required
by that repair. Broader integration and release proof retain their own scope.

Architecture cannot produce missing independent oracles or genuine problems.
The later research track still needs those; do not promise that refactoring
alone will deliver broad 5/5 evidence.

## 2. Read first and preserve one authority map

Read these existing references before implementation:

1. `AGENTS.md` and `docs/reference/PRODUCT_BOUNDARY.md`.
2. `docs/reference/STATE_AND_SEMANTIC_OWNERS.md`, especially Cross-owner operations.
3. `docs/maintainers/CODEMAP.md` for real implementation/test entry points.
4. `docs/maintainers/RESPONSIBILITY_REFACTORING.md` for preservation/locality proof.
5. `docs/reference/ARCHITECTURE.md`, `INVARIANTS.md`, and `API_STABILITY.md`.

The state/semantic owner reference remains normative. The maintainer guide is
navigation. This file schedules implementation; it is not a new owner registry.
The supplied canonical-ownership specification is input to this review, not a
second product constitution. Existing diagnostic/member/declaration work in
`docs/plans/HM_OBS_REPOSITORY_EVIDENCE_OWNER_CENSUS.md` is historical evidence;
reuse its existing owners rather than repeat its implementation.

## 3. Source-grounded review and decisions

Review date: 2026-10-17. The worktree was already modified before this review.
The reviewed paths include CodeMap construction/MRO, ingestion and stable
reads, member observation, graph-cache writers, import-root/policy refresh,
task-owner/verification composition, operation/transport ownership, existing
architecture tests, and the backend acquisition/regrading boundary.

| Item | Evidence and consequence | Responsibility decision |
| --- | --- | --- |
| F1: parsed bytes can differ from the artifact revision | `indexing_lifecycle.py::_sync_index_discovered` hashes a batch; `_parse_or_reuse` later calls `Path.read_text` and assigns the earlier digest. A controlled write between those operations published `replacement_owner` under the digest of `original_owner`. Restoring the original bytes still reused the wrong symbols, and public `outline()` returned them. | **REFACTOR INTERNALLY**, CO-01. Keep lifecycle/parser owners; bind bytes at their boundary. |
| F2: relationship-cache invalidation crosses owner internals | `_reverse_file_graph_cache` is initialized in `engine.py`, read/populated in `evidence_graph.py`, and directly cleared in both graph enrichment and `indexing_lifecycle.py::sync`. | **REFACTOR INTERNALLY**, CO-02. Relationship evidence owns cache validity; indexing signals its publication through an owner operation. |
| F3: navigation contains conflicting copies | `CODEMAP.md` had two responsibility maps, a broken repeated title, and obsolete `delta_*` implementation names in its second copy. | **REFACTOR INTERNALLY**, CO-00; corrected as documentation. |
| Mixin rewrite has no demonstrated basis | Runtime MRO inspection covered 52 classes and 1,057 non-dunder method/descriptor names, with zero duplicate effective definitions. | **KEEP COHESIVE**. Retain composition; add a focused collision regression in CO-07. |
| Import roots/policy have construction and refresh phases | Engine initializes roots/policy; lifecycle refreshes from packaging/admission authority. Multiple assignments alone do not prove competing semantic owners. | **KEEP COHESIVE** pending the finite boundary checks in CO-03. Do not introduce a new root-discovery or policy service. |
| Ranking, task-owner selection and proof are separate stages | Task retrieval supplies candidates; task-action composition may refine a candidate; `ownership_decision.py` supplies authority proof. `evidence_packet.py` already projects separate retrieval/ownership/verification fields. | **KEEP COHESIVE** unless CO-04 proves a concrete redecision. A method named projection is not by itself a violation. |
| Repeated validation can be correct | Operation registry, service wire validation, domain semantics and consumer conformance protect different trust boundaries. | **KEEP COHESIVE**, CO-06 conformance. Consolidate only a reproduced duplicate semantic rule. |

The source-interleaving reproduction is retained locally in
`.hashmarks/architecture-review-20261017/{reproduce.py,review-evidence.json}`.
Its public response retained `stale: null`; the proven defect is wrong
source/artifact binding, not proof that all freshness states became current.
The baseline architecture ring passed **138 tests**. That ring did not detect F1.
Historical candidate qualification separately passed 936 focused tests; it does
not establish current whole-project or all-capability qualification.

This was a bounded review. Dynamic attribute access, all mutations through
aliases, every non-CodeMap owner, and every possible semantic dependency were
not exhaustively resolved. No repository-wide absence-of-duplicates or
absence-of-cycles claim is made.

## 4. Intended dependency boundaries

```text
Python / CLI / MCP / local service
                  |
       existing domain operations
                  |
  task/action composition and evidence packets
       /           |             \
 retrieval    owner qualification  verification relevance
       \           |             /
      qualified relationships and indexed queries
                  |
       admission / member observation / freshness
                  |
       stable bytes / digest / owned mechanisms

Indexing separately coordinates admission -> stable bytes -> parsing
-> atomic store publication. Member observation may request reconciliation.
It must not create an indexing -> member-observer -> indexing cycle.
```

This is a responsibility sketch, not a new dispatcher or a required call order.
Type-only imports and mixin inheritance do not prove semantic cycles. Follow
the actual operation and state effects when reviewing an apparent cycle.

An operation contract is an existing typed function/method plus its behavioral
tests. For each boundary changed, record: owner; input types and bounds;
revision/freshness preconditions; output and qualification; effects; callers;
dependencies; errors; preserved invariants; replaceable mechanism; direct tests.
Extend existing types. Do not create interface classes for every private method.

## 5. Ordered subgoals

| Package | Deliverable | Depends on | Initial state |
| --- | --- | --- | --- |
| CO-00 | One current navigation map and explicit existing owner contracts | Source review | Delivered in this planning change |
| CO-01 | Bytes parsed and artifact revision cannot diverge | CO-00 | TODO; reproduced correctness defect |
| CO-02 | Relationship owner controls reverse-cache invalidation | CO-01 | TODO; confirmed cross-owner write |
| CO-03 | Admission, policy, import-root and source-read handoffs are explicit | CO-01, CO-02 | TODO; bounded investigation with conditional repairs |
| CO-04 | Retrieval, task-owner and verifier handoffs preserve their distinct authority | CO-03 | TODO; prove existing behavior before changing it |
| CO-05 | Repair the metadata retrieval defect in the proper owner | CO-04 | TODO; retain the genuine failing case |
| CO-06 | Existing providers, validators and transports conform to their owner contracts | CO-04; rerun after CO-05 | TODO; preserve existing mechanisms |
| CO-07 | Meaningful ownership regressions are enforced by existing tests | CO-01 through CO-06 | TODO; no governance framework |
| CO-08 | Selected integration closure and explicit follow-on backlog | CO-07 | TODO; no automatic all-capability claim |

### CO-00: documentation and discoverability

Delivered: remove the repeated guide preface/map while retaining unique
declaration/task entries and request flows; replace retired module names; link
the normative cross-owner contracts; add owner/test navigation. Clarify that
engine initialization does not own every cache's meaning.

Acceptance: one responsibility-map heading; every direct CodeMap mixin remains
discoverable; referenced files/operations exist; publication/architecture tests
pass. This is documentation completion, not implementation of later packages.

### CO-01: stable ingestion and artifact recovery

**Owner:** `IndexingLifecycleMixin`; mechanisms remain
`FileDigestStore.read_bytes_stable`, `parsers.parse_source` and ArtifactStore.
**Classification:** REFACTOR INTERNALLY. No new production responsibility.

1. Freeze exact pre-edit source, direct owning test bytes and relevant artifact
   identity. Reproduce F1 before repairing it. Add
   `tests/test_codemap_source_revision_binding.py` with a deterministic hook
   after batch hashing and before parsing; use no sleep or probabilistic race.
2. Preserve the normal warm artifact-reuse path. On a parse miss, obtain raw
   bytes and their actual digest through the existing stable-read primitive.
   Decode the same bytes with the existing UTF-8 replacement behavior. Never
   label a later independent `read_text` with a previous digest.
3. When the observed digest differs from the earlier lookup digest, derive the
   artifact key from the observed digest and check/reuse that exact artifact.
   Parse/store only under the observed digest. Update the index using that
   artifact's revision. A moving/unavailable file must follow the existing
   explicit failure/skip contract; never publish mixed evidence.
4. Inspect **all callers** of `_parse_or_reuse`, including full/targeted sync and
   `_refresh_path_current`. Keep publication with the existing store transaction.
   Do not route ingestion through `_repository_member_observation`, which can
   itself request index refresh.
5. Close recovery of already-poisoned derived artifacts. The current internal
   cache-key domain is `hashmarks.codemap-artifact.v1` in `artifact_key_for`.
   Advance that internal key namespace for revision-bound ingestion and ensure
   the new expected key forces existing file rows to reparse/rebind. Preserve
   public `CODEMAP_SCHEMA`, content identity and parser capability semantics.
   Inspect `python_ast.artifact_key` and `parse_source` normalization so a direct
   parser path cannot reintroduce an old reusable key. Do not add old-key aliases
   or a migration reader for disposable derived state.
6. Add the adversarial matrix: write between hash/read; return to old bytes;
   same durable state reopened; two workspaces sharing ArtifactStore; source
   deletion/unavailability; stable unchanged file; and a TypeScript path proving
   this is ingestion behavior rather than a Python-only special case.
7. Assert through public `outline`/`source` where applicable: symbol/range facts
   correspond to their issued digest; restored original bytes yield the
   original declaration; an old poisoned row/artifact cannot survive recovery.
   Also prove unchanged warm files still reuse artifacts.

**Done:** the pre-repair reproduction fails, all post-repair cases pass, existing
direct test bytes still pass, publication/admission regressions stay green, and
the documented artifact recovery works without deleting canonical input.

### CO-02: relationship-owned cache lifecycle

**Owner:** `EvidenceGraphMixin`. **Classification:** REFACTOR INTERNALLY.

1. Trace `_file_graph`, `_reverse_file_graph`, project enrichment and all current
   writers of `_reverse_file_graph_cache`. Record dependencies on generation,
   native enrichment and evidence freshness before choosing the cache contract.
2. Keep constructor initialization in the composition root. Put cache
   invalidation behind one relationship-owned operation in `evidence_graph.py`;
   route sync/enrichment invalidation through it. Do not add a cache manager,
   event bus, observer registry, second generation or persistent cache.
3. Do not simply delete sync's reset because the cache has a generation key.
   Preserve no-change sync and same-generation/native-authority behavior until
   the tests prove which inputs can change its result.
4. In a small repository, compare reverse dependencies with a fresh CodeMap
   after import modification, add, delete, rename, enrichment invalidation,
   policy denial and repeated unchanged queries. Cache eviction must not change
   evidence meaning. Preserve current traversal bounds and ambiguity.

**Done:** lifecycle never writes relationship cache internals; one owner defines
cache contents/validity; repeated queries reuse valid work; all transition
results match a fresh admitted view. A named invalidation operation is useful
because it owns a state invariant; do not add forwarding-only layers around it.

### CO-03: close the finite source/admission boundary review

**Owners:** discovery/policy, lifecycle, import identity and member observation.
Default classification is KEEP COHESIVE. Repair only demonstrated violations.

Review exactly these handoffs first:

- `CodeMap.__init__` -> root/policy initialization; `_sync_refresh_python_import_roots`
  -> admitted packaging manifests; import resolution -> current root projection.
- `_refresh_context_policy` / `_reconcile_context_policy_for_query` -> live
  admission; `_iter_admitted_repository_files` -> index/project/provider reads.
- `_repository_member_observation` -> stable bytes and indexed revision;
  declaration provider -> that existing member operation.
- `query_surface._grep_candidate_match`, `_source_current_content` and
  `repository_context._source_slice` -> exact current source and visibility.

1. For each handoff, identify the actual definer, direct callers, state writes,
   error contract and owning tests. A currentness check followed by a raw read
   is a review signal; construct an interleaving before calling it a defect.
2. Preserve construction versus refresh as distinct phases. Keep one existing
   root-derivation implementation and current admitted-manifest discovery; do
   not move repository parsing into the generic digest store.
3. Preserve policy load, semantic-change detection, full admission reconciliation
   and evidence visibility as distinct steps. Test allow->deny and deny->allow,
   invalid policy, hidden root manifest and an admitted non-parser format.
4. Test modifications/deletion/symlink replacement between currentness and read
   for the reviewed public source operations. Reuse stable/member observations
   where a mismatch is reproduced; keep source bytes and ranges revision-bound.
5. Confirm the provider context still has no raw workspace authority and discovery
   still uses the canonical admission traversal.

**Done:** every named handoff has an explicit current contract and behavior
proof, or a named unresolved dependency that keeps this package open. Mark a
proven coherent boundary NO_CHANGE; do not extract modules just to fill a quota.

### CO-04: candidate, owner and verifier contracts

**Owners:** `task_retrieval.py`, existing task-action composition,
`ownership_decision.py`, and `evidence_verification.py`.

1. Trace one public `task_evidence` request through canonical retrieval,
   supplementary disclosure, candidate refinement, final authority proof and
   verification relevance. Record which value is a candidate versus a qualified
   owner. Reuse `TaskActionMap`, `OwnershipAuthority` and existing relevance types.
2. Exercise exact target, unambiguous source owner, two close owners, no owner,
   stale source, unresolved production receiver and unresolved test import.
3. Prove source supplements and presentation bounds cannot rewrite admitted
   edit/verifier authority. Preserve independently observed alternatives and
   omission counts when result limits change.
4. `task_action_projection.py::_task_action_promoted_edit` changes an intermediate
   candidate before `_task_action_ownership_payload_fields` issues proof. Trace
   this full chain before proposing relocation. Move policy only if the actual
   code establishes the same authoritative fact twice; preserve legitimate
   candidate refinement under its existing composition owner.
5. Verification consumes the selected edit surface and qualified reference or
   locality evidence. A weak test candidate remains a weak candidate. It cannot
   prove coverage, sufficient verification, runtime identity, or edit ownership.
6. If a duplicate authority is proven, choose the existing semantic operation
   that survives, account for every caller and error/default/bound difference,
   consolidate once and remove obsolete internal alternatives. A wrapper around
   two surviving decision engines does not close the issue.

**Done:** the named scenarios preserve one final owner proof and distinct
retrieval/verification results. Changed code consumes typed upstream facts rather
than reconstructing them. If existing behavior already satisfies this contract,
close with NO_CHANGE plus the tests; no forced architecture rewrite.

### CO-05: metadata localization as the first genuine repair

**Owner:** existing retrieval/disclosure owner, as established by CO-04.
**Classification:** REFACTOR INTERNALLY if a generic repair is established.

The frozen core task is: "Kafka metadata update notifications complete an
asyncio future using methods that the future does not support."
The independently identified source includes
`aiokafka/cluster.py::ClusterMetadata.failed_update`. Existing initial retrieval
does not surface that owner early enough. Both original and source-neutral
phrasings previously missed it; changing wording alone is not a repair.

1. Freeze the exact task, before/after source, expected facts and bounds. Retain
   the failing current observation before editing retrieval.
2. Diagnose whether the required source is missing from candidate retrieval,
   lost in disclosure, or omitted during projection. Repair that existing owner.
   Do not make a presentation formatter run another search or owner ranker.
3. Add a neutral minimal regression reproducing the missing repository fact.
   Require positive source localization plus a same-name/ambiguous/hidden/stale
   counterexample. No aiokafka/Kafka/framework-specific production rules.
4. Preserve the original oracle. The task's future-kind wording needs separate
   source review: the relevant pinned cluster file imports `concurrent.futures.Future`.
   An oracle correction must be explicit and must not count as a localization win.
5. Re-run both genuine revisions through API, actual CLI and official MCP. Check
   exact methods and relevant-test disclosure, source bindings, omissions and
   authority. Initial complete compact/text replies must remain <=4,000 estimated
   tokens without dropping the required evidence.
6. Run the sender case as a nearby control. A retrieved source claim is not
   runtime receiver/callee proof; do not infer transitive paths from a type
   assertion or build a semantic graph.

**Done:** the unchanged independently expected source facts are visible in the
specified initial bound on both revisions; adjacent authority/size tests pass.
No live Kafka broker is required: this tests Hashmarks observing pinned source.

### CO-06: provider, validation and transport conformance

**Default classification:** KEEP COHESIVE. Existing mechanisms are sufficient.

1. Trace Python API -> domain operation and the equivalent CLI/MCP/service
   adapters for `task_evidence`, `structural_locality`, and repository declarations.
   Compare equivalent admitted inputs; preserve explicit transport-specific bounds.
2. Preserve `operation_contract.py` as operation/mode/schema owner. Domain
   validators own domain semantics; wire validation checks untrusted JSON;
   consumer conformance checks retained evidence; presentation checks projection.
   Reuse those validators, including repeated validation at trust boundaries.
3. Keep the existing service schema/object rejection repair. Test wrong/missing
   schemas, arrays masquerading as objects, malformed hit items, unknown fields,
   false/zero/null, unsupported modes and domain-error translation.
4. For relationship providers, keep producer-specific translation in adapters.
   Qualified import identity stays in its resolver; declaration correspondence
   stays producer-owned. Incomplete native relationships must remain unresolved.
5. Demonstrate mechanism substitution only at existing useful seams: optional
   range enrichment/provider fixtures and store bulk-query conformance. A test
   double must preserve the applicable owner contract; do not implement another
   database/parser backend merely to demonstrate replaceability.
6. Compare native facts, uncertainty and omissions in default/initial and every
   supported presentation format. Preserve JSON literal types and source refs.

**Done:** equivalent requests preserve semantic facts/authority across the
reviewed surfaces and supported mechanism seams. No duplicated schema registry,
new public tool, universal relationship model or removed trust-boundary validation.

### CO-07: focused architecture guardrails

Extend existing tests, primarily `test_semantic_ownership_architecture.py`,
`test_operation_contract.py`, `test_efficiency_architecture.py` and
`test_publication_docs.py`. Do not build a product policy engine.

1. Add a MRO/effective-method check. Verify it catches an intentionally injected
   collision in a controlled test class. Distinguish reviewed explicit overrides
   from accidental shadowing; dunder lifecycle methods are not all duplicates.
2. Protect the relationship cache write boundary, allowing composition-root
   initialization. Resolve direct AST attribute assignments, including annotated
   assignments, rather than string-matching formatted source. State the static
   checker's limits; it cannot prove all alias/dynamic mutation absent.
3. Protect canonical admission, schema and member-observation operations with
   the existing structural architecture tests. Add a forbidden relative-import
   example if dependency direction enforcement changes; resolve full module names.
4. Use the existing live behavior tests to protect freshness, invalidation and
   projections. Do not replace those with documentation-string assertions.
5. Check owner dependency direction only for the reviewed operation chains. A
   resolved forbidden runtime dependency fails; dynamic/unresolved calls require
   review. Do not call an incomplete static inventory a complete acyclic graph.
6. Keep one navigation map; verify referenced symbols/modules and all direct
   mixin navigation entries. Avoid freezing private helper choreography.

**Done:** each guard catches its deliberately broken counterpart and passes
the repaired real implementation. All introduced checks enforce a demonstrated
ownership rule and are covered by behavior proof where static analysis is partial.

### CO-08: close this milestone and stop

1. Freeze the integrated production candidate and selected test membership.
   Run the package-owned tests and bounded integration ring below. Preserve
   failures; an interrupted batch remains INCOMPLETE.
2. Use the existing per-workflow receipt mechanism in `benchmarks/research_receipts.py`.
   Reuse only exact matching source/observer/evaluator/input identities. Changed
   producer bytes require new current observations; never relabel old results.
   Do not add a dependency-hash authority to avoid current identity checks.
3. Acquire the selected metadata/sender workflows once on the integrated
   candidate. Regrade retained bytes through the existing pure grader; missing,
   changed or wrongly bound artifacts must fail/incomplete as appropriate.
   The global matrix may remain INCOMPLETE because its population is broader.
4. Measure the modified ingestion/cache operations on equivalent small-repository
   cold, warm and incremental inputs. Preserve read/parse/query counts and exact
   results. Use repeated same-version controls for timing claims. No full new
   performance catalog is required unless claiming capability-20 qualification.
5. At a persistent source checkpoint, use the existing candidate-validation tier:
   compile configured source, make one deterministic source ZIP, and run focused
   import/behavior smoke from an independent extraction. Reserve independent
   byte-identical rebuild/wheel/sdist qualification for promotion or a packaging
   transform change, as AGENTS.md requires. Do not change packaging here.
6. Report each completed package, current contracts, tests and remaining defects.
   A scoped checker pass is scoped. Refresh full typing only when reporting a
   new full total. Whole-project release checks must still pass before claiming
   a clean release; they are not part of a single local repair's rating.

**Done:** CO-01 through CO-07 have their declared evidence; integrated selected
workflows and extraction smoke pass on the bound candidate; no confirmed defect
in this selected scope is hidden as deferred. Stop expanding the architecture
initiative. Schedule a new goal for broader qualification or another owner.

## 6. Executable validation entry points

Use the committed lock. `make init` is needed only if the environment is not
materialized. If the home cache is unwritable, use disposable task cache paths.
These commands describe development QA; no process execution moves into product.

```bash
make agent-finish

# Existing architecture/navigation baseline: 138 tests at review time.
uv run --frozen --offline --no-sync --group test python -m pytest -q \
  tests/test_semantic_ownership_architecture.py \
  tests/test_operation_contract.py \
  tests/test_efficiency_architecture.py \
  tests/test_public_api_contract.py \
  tests/test_refactoring_policy_boundary.py \
  tests/test_publication_docs.py \
  tests/test_repository_file_admission_convergence.py

# Ingestion/publication ring; include the new CO-01 file after creating it.
uv run --frozen --offline --no-sync --group test python -m pytest -q \
  tests/test_codemap_source_revision_binding.py \
  tests/test_codemap.py \
  tests/test_codemap_publication_authority.py \
  tests/test_codemap_enrichment_publication_authority.py \
  tests/test_context_policy.py \
  tests/test_repository_evidence_bindings.py

# Task authority and public presentation ring.
uv run --frozen --offline --no-sync --group test python -m pytest -q \
  tests/test_task_action_map.py \
  tests/test_task_evidence.py \
  tests/test_task_evidence_candidate_verification.py \
  tests/test_task_evidence_declaration_context.py \
  tests/test_decision_evidence_adversarial.py \
  tests/test_verification_reference_fallback.py \
  tests/test_task_evidence_initial.py \
  tests/test_evidence_presentation_contract.py \
  tests/test_codemap_service_client_protocol.py

make compile
make agent-preflight
```

For the selected genuine workflows, use the existing exact local source map
only after validating every referenced tree against the suite. If unavailable,
materialize those explicitly admitted revisions with the existing corpus tools;
do not substitute installed dependency source or inspect their dependencies.
Use a **new** output directory for every changed candidate:

```bash
uv run --frozen --offline --no-sync --group test python \
  -m scripts.repository_evaluation.run_backend \
  --suite benchmarks/repository_evaluation/manifests/backend-campaign-v2/suites/core/suite.json \
  --sources-file .hashmarks/backend-e2e/explicit-retrieval-20261016/path-intake/core-sources.json \
  --workflow aiokafka-metadata-future \
  --workflow aiokafka-sender-node-failure \
  --output-dir .hashmarks/canonical-owner-integration/CANDIDATE-ID
```

Replace `CANDIDATE-ID` with a new candidate label. Omit `--transport` to acquire
both real transports. Inspect every selected workflow's required gates, facts
and witnesses. Do not treat a global INCOMPLETE result as a local failure or a
global pass; do not ignore a contradicted fact because unrelated gates passed.
Run fresh native acquisition only for packages that change native/parser
interpretation, their binding, or a native surface under qualification.

If a broader deterministic regression ring is required, use
`make dev-check-batch DEV_BATCH=N` with current membership from
`make test-shard-plan`. Resume later batches with
`make dev-check-tests DEV_BATCH_START=N`; reproduce one shard with
`make test-shard TEST_SHARD=N`. Execution stays external. Do not copy a stale
batch count or count partially completed membership as proof.

## 7. Per-package handoff and recovery

Each package's review/PR evidence must identify the exact parent/candidate,
classification, changed responsibility and preserved contracts; direct owning
tests and frozen test bytes; comparable complete locality where structure
changes; diagnostics; and any unresolved input or failing check. Use existing
artifacts/receipts and the change description, not another history database.

For a true extraction, satisfy the eight-item extraction gate in
RESPONSIBILITY_REFACTORING.md before moving code. No `*_helpers`, `*_core`,
numbered fragments, forwarding-only modules or universal managers. For an
internal repair, keep ownership cohesive and measure the relevant maintenance,
correctness or economics improvement; LOC and Ruff counts are not product value.

On failure, preserve the failing candidate/evidence. Correct the same bounded
package and rerun its affected proof; do not silently widen the scope. Revert
only that package's edits with a reviewed patch if necessary, preserving all
pre-existing worktree changes. Product code does not acquire Git recovery.
Disposable artifact/index state may be evicted through its existing owner;
canonical repository input must not be deleted to make tests pass. A new cache
namespace cannot silently reuse receipts from the old candidate.

When the prescribed implementation cannot preserve an invariant, stop that
dependent package, state the concrete missing contract, and obtain semantic
review. Continue independent useful work. A low-context implementer must not
guess away ambiguity, unavailable inputs or dynamic targets.

## 8. Explicit follow-on work

After CO-08, choose a separate next goal. The research backlog retains the
missing handler/data/config/dependency/service/native/economics catalogs,
additional debugging repositories, independent reviews, witness closure,
unseen heldouts, full current-candidate acquisition and final promotion proof.
The full typing backlog also remains explicit. None is marked complete here.

Provider/parser/store rewrites, global dependency-graph tooling, another cache
manager, recursive external-library investigation and arbitrary additional
backend syntax are outside this architecture initiative. A new measured defect
can justify a new bounded owner package later; it cannot silently expand this one.

## 9. Plan contract review

**Verdict:** executable for the stated architecture milestone; production
completion remains unproven. The scope and non-goals, canonical authorities,
ordered packages, concrete files/operations, known defect reproduction,
conditional NO_CHANGE decisions, owning tests, validation tiers, recovery and
follow-on work are explicit. No external repository change or new execution
framework is required. Static review limits are recorded. No unresolved file
destination or architecture-choice question blocks starting CO-01.

This verdict reviews the plan, not the implementation. Do not mark the
architecture consolidation, whole-project typing, release qualification or
twenty-capability campaign complete from this document alone.
