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

Documentation changes explicitly run the native Markdown-link and publication-
documentation contract tests in addition to the small mandatory baseline.
A documentation-only change does not need a CodeMap query.

The native admission gate first runs a small selector self-test using real
CodeMap on a controlled source-to-verifier repository. A selector regression
fails before the broader native pytest selection begins; it does not replace
that proof.

### Parallel independent checks and full-suite admission

The required PR workflow has two independent jobs on **the same exact checkout**:
the static/artifact gate runs locked dependency checks, compile, Ruff, typing,
release-request validation, genuine wheel/sdist installation and installed MCP
SDK smoke; the native admission gate runs real CodeMap selector regressions,
high-impact early pytest probes, scoped native pytest or SHA-bound full-suite
collection and dispatch evidence. GitHub Actions can start both jobs together
instead of serializing ~40–50 seconds of static checks before shard planning.

Full-suite shards depend only on successful native admission, but **every**
shard, the static/artifact gate, and native admission must succeed before the
existing `Qualification convergence` status becomes green. A failure, skip,
cancel or missing required gate cannot be treated as success. Focused changes
retain the same native test membership; all releases/nightly qualification
stay independent. The concurrency adjustment only moves externally controlled
GitHub Actions steps: Hashmarks does not acquire execution or result authority.

Measure the total run and critical path on successful source and broad CI PRs.
Extra GitHub runner startup can offset the expected gain, so this parallelism
is an observed timing hypothesis, not an automatic performance claim.

For broad/shared verification changes, the consumer also executes a bounded
critical regression cohort **before** the full native pytest suite. The cohort
includes the stale/removed/renamed-verifier provenance regression that escaped
early feedback in PR #481. Newly changed tests are added as early probes
within a fixed limit. These priorities are *explicit development policy*, not
proof that the observer has exhaustively discovered every verifier. They may
not authorize skipping any required tests. They are recorded in the plan
alongside the full-suite membership and exact Git identities.

Both early tests and the PR's normal selected pytest phase use
`--maxfail=1`, stopping after the first failure. A green PR still completes
every selected test. Nightly and release qualification remain unchanged and
continue to report the complete suite's failures.

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
When the optional identity daemon cannot provide a freshness status, the
selector does not turn unknown into fresh: it independently rechecks the exact
source's indexed digest, validates each nominated test's source binding via
Hashmarks's native observer, and rechecks the source digest before admitting
the subset. An explicitly stale graph still selects the full suite.

Any missing, truncated, stale, ambiguous or unqualified relevance, absent
verifier, unexpected file, unusual Git operation, changed shared test harness,
CI policy, dependency manifest or lock selects the **entire native test suite**.
Selection failures may never silently result in zero tests or a successful
partial result. The original `make test` remains the same authority.

When the change broadens shared behavioral impact beyond observable links, the
full suite is intentionally the safe answer. Optimize real producers, fixtures
and qualification before weakening a fallback. The nightly workflow is not
permission to claim unverified test coverage in a PR.

## Exact native full-suite parallelism

For a PR whose selection is `full`, external CI first asks **native pytest**
for every collected node ID, including parametrized cases. The development
handoff partitions those exact IDs across four GitHub-hosted runners, retaining
whole test-file fixture groups where possible. Hashmarks' existing repository
isolation inventory names tests that run in their own independent pytest
process; those node IDs are excluded from ordinary file selectors. The plan
records the candidate Git SHA, native collection identity, every shard's
membership, and a deterministic identity.

Every runner re-collects native pytest before execution and rejects any
mismatch with the artifact. Each actual native pytest process also loads a
collection-only assertion plugin that checks its selected **process-local
collection** against the exact ordinary or singleton membership assigned to
that worker. Drift between the recheck and execution now fails before tests
run. No missing, duplicate or unknown collected item can be accepted as green. GitHub Actions groups workers and starts ordinary
`python -m pytest` executions; Hashmarks has no worker or result authority.
All four runners must pass for `Qualification convergence` to succeed.
If the initial native collection cannot be qualified, the development gate
**falls back to its existing unsharded full pytest**. A later shard membership
mismatch fails closed, never silently downgrading or skipping tests.

Focused source-only and documentation PRs retain the one-runner fast path.
Nightly and exact-release qualification remain independent and unchanged.
The matrix's potential wall-time benefit must be measured rather than assumed.

### Duration-aware distribution

The developer-only shard planner reads one committed duration-prior file,
`scripts/ci_shard_duration_priors.json`, recording real per-test setup, call
and teardown phase-time totals from GitHub Actions run 41326163538. It retains
a small, explicitly labeled historical floor for two files whose first-phase
measurements were lost to an instrumentation test. Values below one second
need no individual override; files without measurements use a conservative
20ms-per-collected-node fallback. Singletons remain in their own native pytest
processes with a separate estimated startup cost. The plan publishes its
estimated per-runner allocation but **does not treat time as coverage evidence**.
The runtime reference is reviewed in Git, not automatically rewritten by CI.

This allocation changes only GitHub Actions worker assignment. Native pytest
still defines all membership, every selected process proves its exact
collection, and the four shards must all pass. Do not use empirical time
weights to skip tests, change completeness, or turn a green subset into release
certification. The existing pytest plugin also emits a small, diagnostic per-file phase-time
receipt from the **actual ordinary pytest execution** (no new collection or
test invocation). The timing unit test uses its own local dictionary, never
clearing already-recorded plugin measurements. GitHub Actions retains these
samples with the run, and the slowest measured modules are printed for review.
This diagnostic output does not enter test selection, exit status, or
certification; only deliberately reviewed and committed prior data affects
the next run's external shard allocation.

Reprofile before changing pinned weights; compare actual
slowest-shard runtime and end-to-end issue-to-merge time with the prior gate.

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
