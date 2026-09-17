# Hashmarks HM25-R — Replay / Residual Projection Economics

## Parent authority

Exact HM24 REUSE: `26b1a4583241d9b20955606ee79892256cd0c5479f300e44c6ddf7b28b48065a`.

This phase does not descend from historical HM25/HM26. Those checkpoints were used only as measured design evidence.

## Remeasurement and admission

The exact HM24 REUSE scale probe remained linear with verification candidate count. The 501-test case measured 330.54 ms in the baseline run. The historical verification-reference and repository-config projection ideas were therefore reimplemented on the exact HM24 REUSE parent, not patch-replayed.

After the combined replay, the same probe selected the same correct verifier on all four scale cases, reported zero unsafe regressions, and the 501-test case measured 303.44 ms in this run. Timing is empirical and noisy; semantic equivalence and call-elimination boundaries are the admission authority, not a single wall-clock sample.

## Change

1. Verification AST/reference traversal now uses a freshness-bound derived reference index keyed by absolute path plus the file stat identity. A changed source identity cannot reuse the prior index. Final verification selection, candidate membership, ownership decisions, filesystem visibility, and repository generation are not cached.
2. Python verification-candidate projection samples whether pytest is declared once for that candidate projection and passes that observation into Python plan construction. A later decision samples repository config again. Non-Python verification planning remains unchanged.

## Qualification in this runtime

Focused changed ring: **50/50 PASS**. `compileall`: **PASS**. A monolithic full-suite attempt was interrupted by the outer execution window after progress and without a reported assertion failure; therefore this handoff does **not** falsely claim full-suite qualification. Durable resume remains an external/Oh-Goon responsibility, not Hashmarks product state.

## Next phase

**HM26-R — Residual Candidate/Store/Classification/Ranking Economics.** Reprofile candidate-path membership, `symbols_for_paths_many()` / SQLite store work, repository-path classification, ranking/sorting/top-N, and remaining cross-root ownership overlap. Admit a source change only for a currently demonstrated material cost.
