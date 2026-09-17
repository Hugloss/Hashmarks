# Qualification tool compatibility

Hashmarks uses **minimum supported tool versions**, not narrow patch/minor compatibility pins.

The policy is deliberately developer-friendly:

- declare the oldest tool version we intentionally support;
- accept newer releases by default;
- let CI and qualification expose real semantic breakage;
- add an upper bound only when there is concrete evidence that a newer release is incompatible.

`uv.lock` is local, generated dependency-resolution state and is intentionally gitignored. Release qualification records the observed environment; the local lockfile is not release source identity.

## pytest

Minimum supported version:

```text
pytest >=8.4
```

The project-owned `test` dependency group carries that lower bound. CI exercises the minimum 8.4 line and also resolves the newest available pytest satisfying `>=8.4`. If a future pytest release breaks Hashmarks, CI should expose the incompatibility and we can then decide whether to adapt Hashmarks or introduce a justified upper bound.

Pytest is a qualification dependency, not a Hashmarks runtime dependency.

## Ruff

Minimum supported version:

```text
Ruff >=0.12
```

Hashmarks does **not inherit Ruff's default rule selection**. `[tool.ruff.lint].select` declares the complete rule contract explicitly, so upgrading Ruff does not silently opt Hashmarks into a different default lint policy. CI exercises both the minimum Ruff line and the newest available Ruff satisfying `>=0.12`.

Ruff remains externally prepared diagnostic tooling. It is not a runtime dependency and its PASS result is not canonical promotion authority. External evidence records the exact Ruff version that actually produced it, but that concrete version only needs to satisfy the minimum contract.

## uv

Minimum supported version:

```text
uv >=0.10.0
```

The requirement is declared using uv's native `[tool.uv].required-version` setting. `make lock`, `make init`, and normal uv commands therefore work with 0.10.0 or any newer compatible uv. There is no Hashmarks-specific exact lock-generator patch pin.

`make init` may create or refresh a local `uv.lock` as uv resolves the declared dependency constraints. That lockfile is useful local prepared state for frozen/offline follow-up commands, but it is not committed, packaged, or treated as release identity.

## Boundary examples

The current admission edges are intentional and regression-tested:

```text
uv 0.9.99   -> rejected
uv 0.10.0   -> accepted
uv 0.12.13  -> accepted
uv 0.13.x+  -> accepted unless qualification proves a real incompatibility

pytest <8.4 -> rejected
pytest 8.4+ -> accepted, including 10.x+ unless incompatibility is proven

Ruff <0.12  -> rejected
Ruff 0.12+  -> accepted, including 0.17+ and 1.x+ unless incompatibility is proven
```

Concrete versions selected inside CI matrix jobs are deterministic test inputs, not contributor admission pins. Exact versions recorded in receipts are provenance, not policy. Current contributor documentation must not instruct developers to install a side-by-side tool merely to reproduce an observed patch version.

## Compatibility policy

Before raising a minimum tool version or adding an upper bound:

- identify a concrete semantic or security reason;
- prefer fixing Hashmarks to work with newer tooling when practical;
- keep implicit/default behavior explicit where tool upgrades can change semantics;
- exercise the minimum and current/latest supported tool lines in CI;
- avoid exact patch pins unless byte-identical tool behavior is itself part of the product contract.

A version number should not become developer friction without evidence that the restriction protects a real Hashmarks invariant.
