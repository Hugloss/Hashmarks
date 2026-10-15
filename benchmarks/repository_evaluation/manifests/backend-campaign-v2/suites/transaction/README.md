# Genuine transaction and persistence qualification corpus

Twelve distinct upstream changes are pinned across three explicitly admitted
repositories: four each from SQLAlchemy, databases and Litestar. Twenty-four exact
Git archives pass `load_corpus`. Source declarations, nominated direct calls,
revision hashes and exact existing/new test ranges were selected from source and
upstream diffs before measuring these workflows with Hashmarks.

| Workflow | Upstream change | Source and test basis |
| --- | --- | --- |
| sqlalchemy-failed-begin-state | `d29277af2b8046e9ac98ea0ddcf254fe2abc758e` | `_start_transaction` tracks a transaction only in the success branch; new failed-BEGIN recovery test |
| sqlalchemy-bulk-begin-flushing | `4914050a66d0dcb7ec1e5df5a8810fb0c08f25ce` | `_bulk_save_mappings` moves begin into try/finally; pending-rollback regression checks flushing cleanup |
| sqlalchemy-prepare-failure-rollback | `30d75f9a30beab059b6ce93d2c200fd8944d0eb9` | `_prepare_impl` adds an expected-state context around rollback; injected prepare-failure regression |
| sqlalchemy-prepared-commit-xid | `08cef20f4a2bfbeda61abfe6caee975190f0794c` | `do_commit_twophase` replaces SQL interpolation with text/bindparam syntax; existing two-phase commit/rollback tests |
| databases-transaction-context-isolation | `cc3246a7e18c838a880576a59e24e1e18bceb249` | `Database.transaction` nominates a root connection context; added parallel-transaction test |
| databases-commit-clears-backend | `25fa29515d4b6387db482734c564152a1034fbe6` | `Transaction.commit` clears the backend after connection exit; concurrent task/transaction tests |
| databases-acquire-cancellation-counter | `c8171e2f4cda988b78a7ec5c1073623f93afdd3b` | `Connection.__aenter__` broadens Exception to BaseException; queries-after-error adds cancellation |
| databases-disconnect-local-state | `e3e7fa0ec37b4279763faf1449f9cecdae3b71df` | `Database.disconnect` replaces task-local connection state; existing explicit connect/disconnect tests, no dedicated new regression |
| litestar-update-session-merge | `c0a98e51ee09efb15f5892e6143d0a6fa5fd7cd9` | `update` retrieves the identifier then merges; mocked session test asserts merge/flush/expunge and no commit |
| litestar-update-fetched-values | `c148231a9c24357436b03245d0891a88823d7826` | `update` refreshes between flush and expunge; new fetched-value timestamp regression |
| litestar-repository-auto-commit | `55ce3a64886475c4243409d8d76758f68d437483` | `upsert` gains an explicit flush-or-commit helper; lazy-load test disables refresh and commits explicitly |
| litestar-delete-many-chunking | `12f2e0263d03427f9ad602cb8ec797896035341d` | `delete_many` gains configurable chunk sizing; existing/new mocked deletion tests retain flush/no-commit assertions |

Full upstream URLs, parent/after commits, exact archive content identities,
declaration ranges, test ranges and raw range hashes are in `suite.json` and
`grader.json`. The failed-BEGIN problem is also present in the core corpus; its
membership here has separate transaction-syntax source assertions. Reusing it
across capabilities does not create another distinct global problem.

The catalog declares 2,043 exact boundary witness contexts across revisions,
API, actual CLI and official MCP formats. It requires fresh native acquisition.
`source_labels` nominate native declarations; `task_source_labels` additionally
bind production context and the independently selected verifier declaration.
New after tests are never expected in the before revision. Only explicitly
selected production source files enter native captures; imported dependency
implementations are outside the observation scope.

These checks qualify direct source syntax and existing verifier candidates.
They do not establish runtime callee identity, execution ordering, transaction
success, isolation, database compatibility, complete test coverage or sufficient
verification. The historical parallel-transaction patch was subsequently
reverted; recording its source is not an endorsement of its runtime correctness.
Existing test source is not a new execution receipt. The ordinary before tests
for a newly added failure regression remain contextual evidence, with their
limits stated in each review basis.

Every capability-14 proof remains `reviewed: false`. Complete independent review
must still cover success/else assignments, try/finally state cleanup, commit and
rollback branch conditions, connection release scopes, helper bodies, chunk
selection, essential initial display facts and genuine runtime witnesses where
required. In particular, a helper named `_flush_or_commit` does not prove a
commit, and a call to `refresh` does not prove a fetched value was returned.
Passing the narrower source-call checks cannot promote this review flag or
establish 5/5.

Source-only reserved holdouts are SQLAlchemy
`295013ba17895cb925bef042b9ad70c80f1d19b0` (event-hook failure handling), databases
`9795187928083bb2cdf119284160c649e80ca27b` (SQLite connection/query-parameter handling) and Litestar `bb4cb71e9ab2b149d84faa9874464327864099b1`
(repository existence filters). They are excluded from development membership
and have not been measured as these qualification tasks. Resolve full archive
identities and independently admit exact holdout tasks/oracles before use.

Materialize with the existing QA entrypoint:

```sh
uv run --frozen --no-sync --group test python -m scripts.repository_evaluation.materialize_backend \
  --suite benchmarks/repository_evaluation/manifests/backend-campaign-v2/suites/transaction/suite.json \
  --repository sqlalchemy=/path/to/sqlalchemy \
  --repository databases=/path/to/databases \
  --repository litestar=/path/to/litestar \
  --output-dir .hashmarks/backend-e2e/transaction-sources
```
