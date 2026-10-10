# Post-#415 repository evidence checkpoint ledger

**Original baseline:** merged #415 (`f4c18cfb05891505cbf8b8377b729ff03cb9abca`); follow-on work now builds on merged #416 (`c7a2b05986410c4e9ac8ceb6a4d4ed8c20d18f70`). This is a follow-on to the historical single-PR
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

## H06 follow-on checkpoint bundle

| Checkpoint | Classification | Implementation / proof boundary |
| --- | --- | --- |
| H06a | EXTEND_EXISTING_OWNER | Explicit caller-supplied LSP `textDocument/hover` capture, existing source-binding and generation authority; zero relationship claims |
| H06b | REGRESSION | Bounded modern/legacy hover forms, nullable/error states, strict unknown/dynamic semantics, malformed and oversized capture rejection |
| H06c | REGRESSION | Rehashed packet forgery cannot assert relationship edges, trusted semantics or negative evidence from hover |
| H06d | PRESENTATION/DOCS | Existing native/presentation parity, documentation and source-revision contract; no new MCP method or agent-harness behavior |

H06 document-symbol captures remain conditional: their different request shape
and scope cannot be forced into cursor-bound relationship queries without an
explicit non-edge ownership plan.

## Open conditional checkpoints

- **H04:** changed-line → symbol/relationship claims require a direct
  revision-bound source/range oracle and a demonstrated gap in existing
  repository delta/change-impact/structural-locality. No inferred impact.
- **H06 remaining:** document-symbol or other LSP observations require exact
  producer scopes and protocol validation; do not force symbol lists into the
  hover/relationship edge owner.
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
