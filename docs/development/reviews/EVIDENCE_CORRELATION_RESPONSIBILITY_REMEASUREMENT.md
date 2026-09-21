# Evidence Correlation Responsibility Remeasurement

## Authority

Exact post-EC-12 main: `e65f28aa7d630a802dbe2b1f60cf5addf29beb4e`.

This is the EC-13 responsibility remeasurement. It is a development review, not a new semantic authority.

## Fresh measurement

| Signal | Current evidence |
| --- | --- |
| Production owner | `hashmarks/codemap/evidence_correlation.py` |
| Production lines | 1,433 |
| Focused test lines | 1,293 |
| Production line ceiling | 1,600 |
| Ruff structural-debt baseline entry | none |
| Public CodeMap entry | `correlate_evidence` |
| Public delta entry | `evidence_correlation_delta` |
| MCP entry | one `correlate_evidence` surface reusing the same owner |
| Persistence | request-scoped; no event-store authority |
| Packet identity | one canonical packet identity owner |
| Repository evidence | delegated to existing repository-evidence owners |
| Path translation | bounded explicit mapping inside correlation admission |
| Source equivalence | typed member/span identity comparison only |
| Cross-bundle relation | repository-target correspondence only; no cause/incident inference |

The current Ruff debt baseline contains no `evidence_correlation.py` finding. At 1,433 lines the file is below the repository's 1,600-line production ceiling. Size is therefore an investigation signal, not an active structural-debt violation.

## Responsibility inventory

The module coordinates one semantic responsibility: **bounded external-evidence correspondence to current repository evidence**.

Its internal stages are:

1. validate and normalize external claims, bounds, producer/scope/provenance and explicit path mappings;
2. resolve path/module/symbol/line claims through existing repository owners;
3. bind resolved references to canonical repository evidence;
4. compare only admitted typed source identities;
5. derive scoped completeness and definition identity;
6. expose same-repository-target cross-bundle correspondence without incident or causation inference;
7. issue and validate one canonical correlation packet identity;
8. compare only definition-compatible packets.

These stages are coupled by the same request bounds, packet identity, ambiguity rules and fail-closed semantics. None currently demonstrates an independent public or persistence owner.

## Classification

**KEEP COHESIVE.**

No module extraction is justified by the fresh evidence.

A split now would primarily move private stages across files and create additional navigation/parameter plumbing around the same packet identity and bounds. It would not establish a distinct semantic owner. In particular, do not extract generic `locator_helpers`, `correlation_utils`, `packet_core`, producer adapters, or a second source-equivalence owner.

Internal extraction remains admissible later only if a fresh complexity measurement identifies a concrete function/control-flow problem or a stage gains independently reusable semantics.

## Contract preservation

EC-00 through EC-12 now form the frozen evidence-correlation qualification surface:

- external observations remain claims;
- repository identity/freshness comes from repository evidence owners;
- completeness/truncation is explicit and bounded;
- arbitrary producer metadata never proves source equivalence;
- path mappings translate claims but do not establish identity;
- deltas require comparable definitions;
- producer kind does not dispatch collection/execution;
- same-target correspondence never implies same cause or incident;
- canonical packets fail closed on size and identity tampering.

## EC-14 handoff

Do not carry `evidence_correlation.py` forward as a predetermined cleanup target.

Restart general cleanup from the exact then-current `main`, run the repository's fresh debt/responsibility measurement, and let that measurement select the next candidate. Historical hotspots and this file's recent edit frequency are evidence only, never merge authority.
