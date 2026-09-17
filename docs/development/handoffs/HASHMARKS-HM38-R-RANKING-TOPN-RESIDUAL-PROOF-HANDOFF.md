# Hashmarks HM38-R — Ranking Topn Residual Proof

## Parent authority

Exact parent SHA-256: `b5d5ea09e4432853017ee5af56dd6dcf34d8d9f159f8825bf31f020b71ee3dfa`.

## Decision

**CLOSE-NO-CHANGE** — Keep exact full candidate ranking before bounded output.

## Proof

Candidate score evaluation is about 0.004-0.005 s cumulative. Replacing full semantic ranking with an early top-N shortcut would risk ambiguity/selection semantics for negligible proven benefit.

## Qualification

- focused affected ring: **51/51 PASS**
- compileall: **PASS**
- scale selection correctness: **4/4**
- unsafe regressions: **0**

## Guardrail

No source change is admitted without current-parent measurement or semantic proof. Hashmarks remains repository intelligence; no execution/resume authority is added.
