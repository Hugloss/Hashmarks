# Test runtime economics

Test runtime is a qualification cost signal, not product authority.

## Scope the proof to the invariant

A correctness test should use the smallest repository shape that still exercises the contract it claims to prove. Do not pay for a full-repository scan when repository scale is not part of the invariant.

Keep scale and real-repository qualification where scale, filesystem behavior, process interaction, or integration is itself the contract under test. A bounded unit or behavioral regression does not replace those distinct proofs.

## Classify slowness before changing product code

When a test is slow, distinguish:

- product runtime cost;
- test-proof duplication or oversized fixtures;
- environment/filesystem effects;
- process or external-service cost;
- intentional scale/empirical qualification.

Do not add caches, weaken freshness, reduce evidence, or change authority semantics merely to make a test faster.

## Preserve evidence

When replacing an unnecessarily expensive proof, keep the same public/behavioral path and assertions that establish the invariant. Record focused regressions for defects, and keep performance observations separate from correctness promotion.

Runtime measurements should identify enough environment and execution mode to make comparisons meaningful. Hardware-dependent timings are diagnostic evidence, not universal thresholds.

## Derived-authority explicit-packet economics

Use `make metrics-derived-authority` when evaluating whether explain/endpoint-comparison work needs any bounded retention. The command writes one diagnostic receipt under `.hashmarks/metrics/` containing both a controlled fixture and the existing genuine uv/Maven dependency dogfood corpus. The benchmark module owns the normal measurement profile (controlled iterations, scale, real-producer iterations, and fixture root); the Make target only selects the stable `derived-authority-economics-latest.json` receipt path.

The receipt is **runtime diagnostics only**. It is not repository evidence, release authority, or a performance threshold. The controlled section records packet sizes, explain/delta timings, transient allocation peaks, repository re-observation calls, and persistent-state byte growth. The real-producer section separately records adapter artifact bytes and parse cost, qualification cost, explicit endpoint/explain/delta sizes and timings, adapter semantic identity, and dependency change axes.

Repeated explicit-packet explain/delta fails if it touches repository-member observation again, changes persistent-state size, or becomes nondeterministic. Adapter parsing is measured separately because it belongs at the producer/caller edge. A slow producer adapter does not justify a Hashmarks history layer.

Do not infer that a cache is useful merely because an explain packet is larger than its observation or because one machine reports a particular latency. Retention requires material repeated cost in genuine workflows after explicit packets are reused. A future cache must remain bounded, evictable, reconstructible, and irrelevant to semantic correctness.

Current derived-authority qualification completed with two consecutive real uv/Maven passes and did not admit a retention layer. The explicit-packet design is therefore the current baseline. This does not claim that every future workload will have negligible cost; it means no measured evidence in this program justified making server-side history part of Hashmarks.

## Reuse genuine artifacts for read-only proofs

If several tests inspect the same immutable reference workflow, capture it once
with the actual repository observer and native backend runner. Only read-only
aggregators and retained-evidence graders share the capture; tests that inject
invalid in-memory claims deep-copy the outcome before mutation. Tests that alter
source files, evidence bytes, transport behavior, or receipt history continue
using isolated inputs and directories.

This is a **pytest fixture-cost optimization**, never a Hashmarks runtime cache,
new result authority, or a replacement for genuine CLI/MCP end-to-end checks.

## Share real CLI transport captures while isolating corruptions

A separate module-scoped fixture may capture one real CLI workflow for multiple
retained-result grading checks. It must collect all native presentation formats,
not forge packets or replace the subprocess implementation. A consumer that
changes an in-memory outcome deep-copies it. A consumer that corrupts a captured
JSON file copies the evidence tree into a per-test directory first.

Parametrized tamper tests may likewise copy one genuine source-bound API capture,
suite, and grader into per-test directories before modifying them. A positive
admission test must establish that the copied, unmodified evidence still binds
to its source and submitted report. Campaign manifests stay next to their
matching copied suite; no test corrupts the shared fixture.

Tests that explicitly prove capture freshness, receipt reuse, transport behavior,
or source mutation still acquire independent real witnesses.

## Avoid duplicate native acquisitions in read-only aggregation tests

For multi-workflow aggregation, capture one real, source-bound set of backend
workflow reports with ordinary `run_backend()` and share that unchanged evidence
across independent read-only qualification and order-invariance checks.
A separate genuine duplicate workflow capture remains necessary to establish
overlapping membership. Tests that deliberately corrupt a report still use
isolated evidence and never mutate the shared capture.

A native-packet handoff test which constructs explicit packets and replaces the
native verifier only needs a valid two-workflow corpus; it must not perform
unused real backend acquisitions. True native capture and transport semantics
remain covered by the separate genuine backend workflow tests. This is a
pytest-fixture optimization, not a product cache, test runner, or substitute for
nightly and exact-source release verification.
