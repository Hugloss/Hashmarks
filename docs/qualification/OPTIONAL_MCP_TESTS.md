# Optional MCP test execution follow-up

This test-only repair starts at `5cd5706763b7192d8c89cdfc3a01de5525d28010`.
The validated code/test files match commit
`50cdc103fc811e52b70d955d18e4f9bb037c1792`; this report records the resulting
qualification separately.
The earlier annotation import repair allowed collection without MCP, but normal
pytest execution only enforced capability markers in constrained-host mode.
Four SDK-dependent transport cases therefore attempted to import absent MCP.
The economics CLI test also assumed a historical count of seven excluded members.

The shared pytest capability owner now qualifies `host_mcp_sdk` in both normal
and constrained runs. Missing SDK cases skip with an explicit reason; installed
SDK cases execute and expose transport failures. Other normal-host prerequisites
retain their prior behavior. Additional constrained-host exclusions remain scoped
to that mode. The old constrained-only helper has no remaining callers or alias.

Mixed CLI/MCP checks apply the marker only to their MCP parameter. Both source
invalidation and literal-argument CLI cases remain runnable without the SDK.
A subprocess regression makes MCP unavailable on an SDK-equipped development
host and executes the actual reported cases: two CLI cases must pass, four SDK
cases must skip. Before the capability repair it reproduced all four import
failures; after repair it passes. The original collection regression remains.

The economics CLI check verifies non-empty excluded membership, category
accounting and total membership conservation. It no longer fixes an exact count
that changes when repository tests are added. Production classification, capture
helpers, dependency declarations, the committed lock and CI installation choices
are unchanged.

| Final validation | Result |
| --- | --- |
| Full Python 3.11.15 test-only environment, SDK absent | **4,229 passed, 21 skipped, zero failures/errors**, 549.24 seconds |
| Reported transport cases, economics and capability regressions, SDK present | **33 passed**, zero skips/failures/errors |
| Same focused selection, Python 3.14.7 test-only environment, SDK absent | **29 passed, 4 SDK cases skipped**, zero failures/errors |
| Source hygiene, formatting, Ruff and size/complexity gate | PASS |
| Focused ty and Pyright for the new capability regression and economics CLI test | PASS; not a full-project typing claim |

The full run emitted one warning because a native fixture's `record_property`
metadata uses pytest's default `xunit2` output. It was not a test failure. Skipped
cases remain unqualified capabilities; SDK functionality is established separately
by the SDK-present transport checks. No full SDK-present suite, live producer,
release certification or performance improvement is claimed. Interpreter patch
versions differ from the reported CI runner's 3.11.17; exact local versions are
recorded with the receipts.

Raw JUnit, exact invocations, skip reasons, environment and changed-test hashes
are in `dist/ci-followup/qualification.json` and the adjacent files. This directory
is ignored and must accompany a PR/CI handoff separately. The previous ownership
repair reports and archives retain their own historical scope.
