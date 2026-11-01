# Hashmarks CI: relevant development checks and full qualification

Hashmarks remains a repository observer. **This workflow consumes its existing
repository-intelligence evidence**, but it does not add a product test runner,
verification policy engine, or new execution path. Native pytest still executes
tests; GitHub Actions and the local developer retain execution/result authority.

## Two cadences, plus independent release authority

| Check | Trigger | Coverage | Status |
| --- | --- | --- | --- |
| Relevant verification | Pull requests, merge queue, main pushes | Locked dependencies, compile, Ruff, typing, selected pytest, real installed wheel/sdist and MCP SDK smoke | `Qualification convergence` status (can be required by ruleset) |
| Full qualification | Every day at 02:23 UTC, or manual dispatch | Existing full Python 3.11–3.14 matrix, MCP compatibility/stress, source qualification, standalone Linux/Windows, publication aggregation | Daily diagnostic, not a PR-green claim |
| Publish qualification | Existing reviewed release request/explicit dispatch | Independently qualifies exact release source and published bytes | Release authority; unchanged |

**The daily run can detect a regression after merge.** Do not claim that a green
PR performed full regression. Release publication must independently test its
exact source, even if the daily run previously passed.

## Developer usage

- `make test-fast`: inspect local staged, unstaged, and untracked changes and run
  selected native pytest tests. With a clean checkout it compares to `HEAD^`.
- `make test-fast CI_BASE_REF=origin/main`: inspect the full current branch delta.
- `make test`: execute the complete native suite explicitly.
- `make test-profile`: obtain pytest duration diagnostics for further optimization.

The selection plan is JSON, bound to base SHA, effective checkout SHA, changed
paths and a deterministic plan digest. CI preserves it as a run artifact. A
`focused` plan is an **admission to run a subset**, not a completed verification
receipt; pytest and the final required status establish the actual result.

## Fail-closed selection

The developer consumer first inspects the exact Git delta. Test-only changes
select the changed tests plus mandatory baseline tests. Documentation-only
changes run the baseline tests. For Python source changes under `hashmarks/`
or `scripts/`, CodeMap is queried for existing verification ownership; test
nominations are validated from the live workspace. Only complete, untruncated,
non-stale, non-ambiguous source-qualified links may reduce pytest membership.

Any missing, truncated, stale, ambiguous or unqualified relevance, absent
verifier, unexpected file, unusual Git operation, changed shared test harness,
CI policy, dependency manifest or lock selects the **entire native test suite**.
Selection failures may never silently result in zero tests or a successful
partial result. The original `make test` remains the same authority.

When the change broadens shared behavioral impact beyond observable links, the
full suite is intentionally the safe answer. Optimize real producers, fixtures
and qualification before weakening a fallback. The nightly workflow is not
permission to claim unverified test coverage in a PR.

## Follow-up optimization

Profile the expensive backend workflow fixtures and benchmark specimens. Split
fast deterministic contract tests from authentic transport/corpus integrations,
without replacing independent end-to-end correctness evidence with mocks. Keep
each real integration counterpart in daily and exact-release qualification.
Improve the relevance observer where uncertainty causes unnecessary full-suite
fallback; do not bypass completeness or invent repository negative evidence.

## CI migration and required check

The check name **`Qualification convergence`** is preserved so existing branch
protection can retain one mandatory PR status. The complete historical
qualification jobs move to the daily workflow, whose convergence job is named
`Nightly qualification convergence` to avoid an ambiguous required status.
The independent `publish.yml` source-bound release qualification remains.
Check repository rulesets after merging, especially any requirements naming
removed *individual* legacy CI jobs. Do not weaken those rules until the
replacement check is observed on a real PR and on the merge queue.

The active `main` ruleset observed during this PR has no required-status rule;
configure `Qualification convergence` as required separately after this PR passes.
