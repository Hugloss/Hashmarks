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
