# Hashmarks HM28-R — Reference Index Freshness Reuse Closure

## Parent authority

Exact parent SHA-256: `9ca4bb097092101bd18045c9f562ae97928f8a5fe2e7e904b6ca407326d1aabd`.

## Decision

NO CHANGE; existing freshness-bound AST/reference reuse is the correct authority boundary.

## Evidence

- The reference index is already keyed by exact filesystem identity and the underlying Python AST snapshot is freshness-bound.
- No cross-generation or final-decision cache is introduced. Existing cache ownership preserves mutation visibility while amortizing repeated unchanged AST/index work.
- The residual is first-touch per-candidate projection, not repeated parsing of one unchanged candidate within the same semantic operation.

## Qualification

- focused affected ring: **57/57 PASS**
- compileall: **PASS**
- scale selection correctness: **4/4**
- unsafe regressions: **0**
- 501-surface action sample: **293.26 ms**
