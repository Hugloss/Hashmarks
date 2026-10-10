# Consolidated competitor-evidence implementation (single Hashmarks PR)

**Base:** `main@ae3450cf54a420b1dc5a0e39271b485b09aefc46` (merged #414).
**Scope:** read-only, reproducible repository intelligence. No new harness, graph engine, agent memory, editor, LSP process, execution system, or second CodeMap authority.

## Admission baseline

Before writing each capability, compare the exact existing CodeMap producer, operation, presentation, and tests. Classify as `ALREADY_PRESENT`, `EXTEND_EXISTING_OWNER`, `PROVIDER_ONLY`, `MEASUREMENT_ONLY`, or `REJECT`. An apparently missing field does **not** justify a new public tool or semantic owner. All code changes, docs and QA live in **this one PR**; use separate commits and focused test rings to keep failures attributable.

| ID | Source inspiration | Gap / action | Admission | Canonical owner | Proof |
| --- | --- | --- | --- | --- | --- |
| H01 | Serena / Sourcegraph | Bounded source-backed symbol signature and producer documentation metadata | EXTEND_EXISTING_OWNER | SCIP/native evidence and source observation | Exact attribution, bounded metadata, stale/denied isolation |
| H02 | Serena | Adjacent source context for known symbols | ALREADY_PRESENT (source match/line anchors); prove before extending | `source_observation` | No second read, accurate line/clip anchors |
| H03 | GitNexus | Direct relationship context by kind/direction, never inferred reachability | ALREADY PRESENT (#409-#414); regression/composition audit | `structural_locality` | Incoming/outgoing and unresolved kept separate |
| H04 | GitNexus | Changed-line to symbol/relationship factual mapping | EXTEND EXISTING OWNER only if oracle exposes a gap | Repository delta, change impact, binding coverage | No phantom moves/removals or causal impact |
| H05 | Sourcegraph | Bounded SCIP occurrence role and symbol documentation capture | EXTEND_EXISTING_OWNER | SCIP adapter/native producer snapshot | No synthesized reference coverage, omission accounting |
| H06 | OpenCode | Additional LSP producer observations (hover/symbols) | PROVIDER_ONLY / conditional | Native supplied evidence, not LSP runtime | Strict protocol inputs and source equivalence |
| H07 | GitNexus route_map | Static, directly declared API route/handler facts | PROVIDER_ONLY | `repository_declarations` + bindings | Explicit format/provenance, no dynamic-route absence |
| H08 | GitNexus tool_map | MCP/RPC declaration/handler observations | PROVIDER_ONLY | `repository_declarations` + bindings | Exact handler bindings, no guessed dispatch |
| H09 | GitNexus shape_check | Producer-normalized response shape/consumer access correspondence | PROVIDER_ONLY | `repository_declarations` | Incomplete/dynamic shape never becomes a confirmed mismatch |
| H10 | GitNexus api_impact | Route-scoped direct fact view using existing declarations/bindings | EXTEND EXISTING PROJECTION only if necessary | declaration + impact | No severity/risk recommendations or inferred call chain |
| H11 | GitNexus process grouping | Explicit entry-point process-membership capture | CONDITIONAL; no inferred process graph | Relationship provider | Direct, bounded producer claims only |
| H12 | Aider | Task-relevant evidence ordering | MEASUREMENT BEFORE CODE | Existing bounded retrieval | Rare-owner recall and false certainty must not regress |
| H13 | Aider | Full serialized-response budget accounting | MEASUREMENT BEFORE NEW TRANSPORT | Evidence presentation | Real host-visible tokens; omission/parity audited |
| H14 | Hermes | Semantic tool discoverability/description differentiation | EXISTING MCP AUTHORITY, conditional changes | MCP operation contract | Exact native catalog/projection identity |
| H15 | Serena | Bounded pure projection across already-observed facts | CONDITIONAL, no user code eval | Evidence presentation | Identity, source refs, completeness, no added semantics |
| H16 | Sourcegraph | Precision vs heuristic candidate authority separation | REGRESSION AUDIT | Native evidence / task evidence | No rank-to-owner authority promotion |

## Integrated acceptance gates

1. **Single semantic owner:** reuse existing CodeMap evidence and existing 14-tool MCP catalog. No second generation, local content identity, cached history, parser-level precedence, or graph truth score.
2. **Source binding:** every factual location is repository-admitted, visibility checked, source-revision bound, and revalidated. Imported producer claims remain producer claims even when locators correspond.
3. **Independent uncertainty:** preserve freshness, availability, completeness, candidate ambiguity, truncation, negative-evidence admissibility, and producer-vs-repository authority separately.
4. **No false negative:** empty/partial/unsupported/provider-missed data never proves reference, declaration, field, route or tool absence.
5. **Compatibility:** existing API/CLI/MCP defaults, input schemas, output modes, operation identities, and old generated data are preserved or deliberately migrated through their canonical owner.
6. **Conformance:** native, compact, structured and text presentations preserve semantic facts; verify using existing conformance validator. Do not claim token savings from row caps while the native payload remains in the envelope.
7. **Regression:** every implemented defect or new admitted contract gets positive, absent, ambiguous, stale, denied, truncated, changed-source, and deterministic replay tests where applicable. Cold/warm equivalence for persisted native claims.
8. **Performance:** frozen corpus tests for bounded cost, rare-owner retrieval, relevant evidence loss, and measured actual response bytes/tokens.
9. **Agent effectiveness:** agentsCookbook (external) measures exposed, invoked, returned, model-visible, demonstrably used and paired success. Hashmarks never asserts model visibility or agent comprehension.
10. **Validation:** uv-managed locked environment; focused tests, formatting/Ruff, full test suite and release qualification on the exact final PR head. An unrun check is NOT PASS.

## Work order within this PR

- **A: Source/semantic precision (H01, H03-H06, H16).** Start by proving metadata gap; add strictly bounded native producer observations, regression and documentation.
- **B: Cross-artifact direct contracts (H07-H11).** Only explicitly selected trusted providers. Start with one representative static route/tool corpus and preserve the declaration-provider input authority. An unsupported framework is unknown.
- **C: Delivery quality (H12-H15).** Frozen format and routing experiments first; only code changes with measured correctness/usefulness, no new formatter/index by default.
- **D: Integration qualification.** Ensure parity, native transports, coverage, compatibility, source admission, CIs; summarize any deferred conditional item honestly in PR.

## Explicit rejects

No GitNexus-style Cypher, knowledge-graph paths/clustering, taint decisions, inferred transitive API reachability, security/risk scoring, workflow planning, shell/tool execution, agent memory, model-scheduling, LSP server lifecycle, editor writes, Git history owner, unsafe dependency crawling, or copying PolyForm Noncommercial/GPL application code.

The design borrows **public semantic ideas and contract behavior** rather than importing third-party implementations. Dependency licenses must be checked before any source reuse.
