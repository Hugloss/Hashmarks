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
