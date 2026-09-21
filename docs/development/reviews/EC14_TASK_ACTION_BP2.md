# EC-14 Task-Action BP2 Review

## Exact qualified candidate

Post-edit main: `0dc17e96ffab5cfdb4339aaab772c559123bd54b`.

Changed source blob: `e14c39c54b90e8657a28939f224a7066333b8623`.

The bounded edit extracted local structural-owner ambiguity evidence acquisition into a responsibility-named internal stage.

## Executable qualification

GitHub CI run **618** completed successfully on the exact candidate. The successful matrix includes repository-evidence diagnostics, fast validation, workspace-authority diagnostics, pre-commit, release qualification, Python 3.11/3.12/3.13/3.14 tests, MCP minimum/latest supported lines, consumer wheel artifact, and qualification convergence.

This supplies behavior/repository qualification for the candidate. The BP1 direct-test source was not modified by the production PR.

## Fresh debt measurement

The exact post-edit `ruff-debt-baseline.json` still records:

- `task_action_projection.py`: **189 excess**
- debt-bearing functions: **4**
- rule findings: **16**
- repository total excess: **2,472**

The production file grew from 816 to **823 lines**.

Therefore the extraction is behavior-preserving according to CI, but it did **not** reduce the repository's measured structural debt. It must not be counted as a debt-reduction closure.

## Locality interpretation

The new helper has one in-module caller and one responsibility, but caller count is review evidence only. Because no independently persisted complete pre/post structural-locality receipt was produced for this edit, EC-14 must not claim locality improvement from this change.

## Decision

**STOP THIS REFACTOR CHAIN.**

Do not stack more helper extraction merely because the selected file remains the largest current debt item. The first qualified edit demonstrated that decomposition at this seam moves code without reducing the measured debt authority.

The edit may remain because it names a coherent stage and CI qualified its behavior, but it is not promotion evidence for further mechanical splitting.

## Next authority

Restart from exact fresh main and remeasure current debt/responsibility before selecting another production change. If `task_action_projection.py` is selected again, the next proposal must target an exact Ruff-bearing function/control-flow cause and show a plausible reduction in its measured rule values before editing. Do not use file size, recent edit history, or this helper as selection authority.
