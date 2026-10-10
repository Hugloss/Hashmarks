# Post-#415 repository evidence checkpoint ledger

**Baseline:** `main@f4c18cfb05891505cbf8b8377b729ff03cb9abca`,
the merged #415 result. This is a follow-on to the historical single-PR
H01–H16 admission plan, not a claim that every conditional item in that
historical plan shipped.

## Current cohesive implementation bundle

| Checkpoint | Classification | Implementation / proof boundary |
| --- | --- | --- |
| H09a | EXTEND_EXISTING_OWNER | Explicitly selected Python route/tool handler literal dictionary-return syntax, each return site separately anchored to canonical repository evidence; dynamic/unpacking stays unknown |
| H09b | EXTEND_EXISTING_OWNER | Handler-local `name["key"]` access syntax, with source location and syntactic receiver; no owner alias analysis or producer-consumer matching |
| H10a | ALREADY_PRESENT + SOURCE EVIDENCE | Existing route-to-handler decorator declaration is the only scoped association; body-syntax observations live on that declaration, not an inferred call graph or impact classification |
| H16a | REGRESSION | Default unchanged; denied, stale, oversized, nested, unknown and replay cases cannot imply complete coverage or compatible API shape |

The additional handler capture is **opt-in** and uses the
`StaticPythonInterfaceDeclarations` provider, already bound by CodeMap's
repository-declaration discovery. There is no new MCP tool, index, service,
cache, LSP process or historical authority.

## Open conditional checkpoints

- **H04:** changed-line → symbol/relationship claims require a direct
  revision-bound source/range oracle and a demonstrated gap in existing
  repository delta/change-impact/structural-locality. No inferred impact.
- **H06:** LSP hover/symbol captures require explicit protocol validation,
  source equivalence, and an existing-owned non-edge observation form. The
  current LSP relationship adapter must not turn hover or symbol lists into
  semantic relationship edges.
- **H09 (remaining):** a future explicit provider may attest normalized
  producer/consumer field correspondence; without attributable evidence no
  mismatch, breaking-change or absence judgment is admitted.
- **H10 (remaining):** route-local direct evidence composition may be added
  only with qualified endpoints; no transitive downstream API impact.
- **H11:** process membership is provider-only and has no current proved
  direct producer corpus. Do not infer a process graph from static naming.
- **H12/H14/H15:** compare real retrieval, catalog and projection measurements
  in agentsCookbook/host trials before changing ranking, tools, presentation
  or transport. Preserve rare-owner recall and exact model-visible attribution.

## Qualification gates for this follow-up

1. Exact default discovery identity and output remains unchanged without opt-in.
2. Both literal and unresolved sites are preserved without inferring complete
   response/consumer coverage or runtime contract compatibility.
3. Literal facts require current, admitted, source-bound evidence. Denied and
   changed inputs fail closed; malformed boolean and site overflow reject.
4. Native declaration deltas and existing evidence presentation remain sourced
   from their existing semantic owners.
5. Python 3.11/3.14, Ruff/formatting, full MCP, wheel and release qualification
   must be checked on the exact PR head. An unrun gate is **not** PASS.
