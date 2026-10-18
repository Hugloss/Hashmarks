# Canonical architecture stabilization and trustworthy backend baseline

Status: ACTIVE. The user approved this completion target on 2026-10-18.
This is the active delivery plan. It supersedes the exhaustive completion gates
in `CANONICAL_COMPONENT_REWRITE_PLAN.md`; that document retains implementation
history, design rationale and the later twenty-capability research backlog.

Completion means **stabilization complete**, never backend 5/5 qualified.
The backend matrix, its population minima, review flags and historical results
are unchanged. Missing research evidence remains INCOMPLETE in those reports.

The user also clarified that **6,000 tokens is advisory**, not a hard
stabilization gate. Record complete response costs and defer further compression
to later improvements. Do not start another repair cycle for budget alone.

## Scope and stopping rule

Finish the implemented canonical owners and reproduced generic repairs. Prove
their supported behavior with current configured checks, existing component
contracts and a fixed representative public workflow set. Do not add a corpus,
framework parser, feature or architecture rewrite to improve a score during
this delivery. A new finding is a blocker only when it demonstrates a concrete
correctness failure in an implemented, supported contract exercised by these
checks; unsupported syntax or weak retrieval recall remains an explicit limit.

Hashmarks remains a repository observer. No consumer planning, test execution,
runtime compatibility inference, orchestration or certification responsibility
is added. Development qualification is performed by the external coding agent
using existing repository commands.

The current production candidate is CR-54. Its source-only verifier freshness
repair follows CR-52 source compression and CR-53 alternative test disclosure.
Preserve every original failure and candidate identity. Prepare one final source
artifact after these plan edits, then use its independent extraction for the
remaining checks. Documentation changes alone do not require another production
repair or another broad corpus campaign.

## S1 — Canonical ownership and supported boundary contracts

Required:

- The 23 implemented component owners retain domain operations and caches;
  CodeMap owns composition and resource lifetime.
- Existing retired root APIs remain removed; callers use canonical owners.
- Existing component construction, input binding, lifecycle, shared-store,
  import direction, authority and wrong-owner mutation controls pass.
- Stale evidence, ambiguous ownership, incomplete observations, denied source
  and bounded results cannot silently become fresh, unique or absent.

Use the existing `test_repository_*_component.py`,
`test_component_architecture_contract.py`, `test_component_input_binding.py`
and `test_semantic_ownership_architecture.py` membership in the full test run.
The report names the owner map in `docs/reference/STATE_AND_SEMANTIC_OWNERS.md`.

This is responsibility/boundary qualification. A standalone direct test and
complete native call/caller proof for every private helper are deferred.
Conservative unresolved locality is documented, not converted into exact edges.

## S2 — Current configured quality checks

Run and record the unchanged configured commands on the final source state:

```sh
make agent-preflight
make lock-check
make typecheck
make compile
```

Full Ty and Pyright must pass. Hygiene, formatting, zero new lint debt and
existing file-size limits must pass. Do not add ignores, exclusions, broad Any,
lower severity, altered tool policy or a weakened lock check to obtain green.
Tool installation and process control remain environment/execution concerns.

## S3 — Complete deterministic regression membership

Freeze the existing 64-shard test selection for the final extraction before
running it. The current membership has 3,562 static nodes; recompute its identity
from the final extraction instead of hard-coding that count as policy.

Run all sixteen named batches through the existing developer entrypoints:

```sh
make dev-check-batch DEV_BATCH=0
# Continue batches 1 through 15, or use the existing sequential entrypoint:
make dev-check-tests DEV_BATCH_START=1
```

Record the final source/producer/selection identities, complete batch logs,
selected membership, executed parametrized case counts and any skips. Every
required selected test must execute and pass; no unresolved failure or silently
excluded selected node is allowed. Opt-in live acquisition is a separate scope,
not a passing test inferred from an unexecuted path.

If a batch fails, retain it, repair the demonstrated contract, rerun the affected
tests and that batch, then resume later batches. A host timeout leaves only the
in-flight batch unproven. Completed proof is retained with its actual candidate;
never silently rebind an old result to modified production. Prior CR-53 batches
and the repaired CR-54 batch remain history until the final run qualifies them.

A test-only contract correction does not invalidate every other test. If
production, configuration, evaluator and oracle bytes are identical, prove that
the complete selected node membership and isolation requirements are conserved,
retain completed batches whose test files are unchanged, and rerun every batch
containing the edited test file plus the remaining original frozen membership.
File-size weighting may regroup nodes without changing membership; compare
grouping-independent membership before reuse. Keep original execution identities
and explicit comparability evidence. The external agent executes those fixed
groups; do not add a Hashmarks runner, scheduler or resume store for this work.

Existing genuine dependency/native capture replay tests are part of regression
proof. Run focused fresh native captures only if native producer integration
changes during stabilization. Broad fresh native population acquisition is
deferred; do not claim it was performed.

## S4 — Fixed representative genuine public workflows

Use exactly these existing `backend-data-v1` workflows on the final extraction:

| Workflow | Supported behavior under qualification |
| --- | --- |
| `fastapi-iterable-serialization-options` | Exact source/call disclosure, source qualification and the reproduced large initial-response case |
| `litestar-dtodata-renamed-instance` | Separately bound cross-file source/call facts and explicit runtime uncertainty |
| `faststream-keyed-none-tombstone` | Source/call facts plus the independently source-reviewed after-test declaration, without selecting or executing that test |

Use the existing backend runner and pinned source map. Do not edit task wording,
oracles, source membership or bounds to make a result pass. Observe both revisions
through API, real CLI and official MCP, including default/initial profiles and
every required format. Facts, authority, revision,
freshness, CLI/MCP and presentation gates must pass. Record complete initial
compact/text response costs against the advisory 6,000-token target; exceeding
it is a documented improvement opportunity, not a blocker. Missing authority,
freshness or required facts cannot be compensated by smaller output.

The existing backend evaluator may still return `initial_size: false` or an
aggregate FAIL under its recorded size policy. Preserve that result verbatim;
the stabilization report distinguishes the user's advisory budget from required
correctness gates. Do not relabel a historical backend qualification as PASS or
change its matrix score to make this milestone look better.

Pure regrading must verify exact receipts, retained artifact hashes, source
bindings and the independently frozen required source/call/test witnesses for
these three workflows. Required units must be present and PASS. Preserve the
before-test unknown and ineligible owner/initial-recall metrics; this does not
claim independent semantic compatibility or broad answer sufficiency.

Existing regression tests supply controlled stale/edit/reopen, ambiguous owner,
wrong source/revision, missing evidence and presentation-preservation adversaries.
The selected-verifier freshness regression must retain the original selected
test and report `stale` after unsignaled source change; optional enrichment must
not refresh away that evidence. Direct source readers still reject in-scope drift.

Do not run the other nine data cases or the larger campaign again merely because
this fixed set passes. Existing complete twelve-case CR-52 proof is preserved
under its original identity and is not relabeled as final-candidate evidence.

## S5 — Source artifact and independent extraction

Create one deterministic source ZIP including current new files and modes.
Verify its manifest hashes and the extracted package's actual import origin and
producer identity. Execute S3/S4 from that extraction using the configured tools.
Run one source compile check. The final working production, test, configuration
and oracle bytes must still match those qualified inputs at handoff.

Independent rebuild byte identity, isolated wheel/sdist installation and full
distribution promotion proof are deferred until a release or packaging-transform
change. Stabilization is a source deliverable, not a release certification.

## S6 — Handoff and completion

Write `docs/qualification/STABILIZATION_REPORT.md` with one evidence row per
S1–S5 requirement, exact candidate identities, commands/results and retained
limitations. The report must distinguish:

- architecture stabilization and tested responsibility boundaries;
- current regression/typing/public-source baseline;
- incomplete twenty-capability research qualification.

The active target is complete only when S1–S5 pass on the final source candidate,
the report is current, and no required correctness failure remains. The report
may then say **stabilization complete**. It must continue to say that broad
backend 5/5 qualification is **INCOMPLETE**.

## Deferred, nonblocking research and release work

Retain these in `docs/qualification/BACKEND_E2E_REMAINING_PLAN.md`:

- Missing dependency/build, cross-service, additional native and economics
  populations; remaining debugging breadth.
- Full handler/model/config/data and other capability semantic/test/adversarial
  review, independent oracles, unseen holdouts and complete witness populations.
- The existing twelve-problem/three-repository minima, owner/debug/initial-recall
  targets and all twenty capability rows reaching 5/5 on one future candidate.
- Exhaustive introduced/private-stage baseline/direct-test correspondence and
  complete qualified native/source locality for every measured scope.
- Broad cold/warm/incremental/rename/delete/recovery economics with noise controls.
- All-campaign fresh native acquisition, final unseen heldout qualification and
  independent release rebuild/wheel/sdist proof.

Resume this work only as a separately requested capability/release increment.
Do not reduce scores, flip review flags or amend evaluator minima to disguise
deferred work. The smaller delivery scope changes the finish line, not evidence.
