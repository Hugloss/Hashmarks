# Test Runtime Economics

## CA-01 — real-repository prefix proof

The native duration baseline reported 873 tests in 1564.03 seconds. The slowest test was
`test_real_repository_find_task_prefix_is_stable_through_agent_surface` at 211.22 seconds.

Classification: **test-proof scope defect**, not evidence that `find_task()` itself requires a production cache.
The asserted contract is prefix stability across limits 5/10/20. Repository scale and the exact Hashmarks
repository bytes are not inputs to that invariant. The old test paid for a cold full-repository CodeMap sync
on every suite run and then deleted the state.

CA-01 replaces that proof with a bounded representative 30-file repository while preserving the public
`CodeMap.sync()` -> `find_task()` agent-surface path and the exact prefix assertions. This keeps a real
index/sync/ranking proof but removes unrelated repository-scale work from release-correctness qualification.

Measured in the qualification environment, the focused test completes in 0.32s (0.23s call). A retained native baseline was 211.22s. These timings are not hardware-comparable; they establish that the new proof
is bounded by construction.

A retained WSL run used `/mnt/c/...`. Cross-filesystem metadata and small-file I/O can amplify
repository-wide scans substantially. CA must therefore distinguish test-proof duplication from product
runtime economics before adding caches or changing repository semantics.

Do not use runtime alone as a correctness gate. Preserve at least one appropriately scoped real repository
or scale qualification where scale itself is the contract under test.
