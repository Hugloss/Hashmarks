# Qualification tool compatibility

Hashmarks uses minimum-compatible dependency declarations rather than exact development-tool pins. Exact versions belong in resolved environments and qualification evidence, not in contributor policy.

`uv.lock` is local, generated dependency-resolution state and is intentionally gitignored. Release qualification records the observed environment; the local lockfile is not release source identity.

## pytest

Minimum supported version:

```text
pytest >=8.4
```

The project-owned `test` dependency group carries that lower bound. Pytest is a qualification dependency, not a Hashmarks runtime dependency. Qualification verifies that the prepared test environment satisfies the declared minimum before running the suite.

## Ruff

Ruff is deliberately **not** a compatibility matrix.

The project-owned `lint` dependency group declares Ruff and `[tool.ruff]` in `pyproject.toml` is the single lint configuration. Local pre-commit hooks and CI invoke that same project Ruff configuration. Hashmarks does not maintain separate minimum/latest Ruff test lanes and does not test Ruff versions merely to prove that a tooling range exists.

Run the canonical Ruff check with:

```bash
make ruff
```

The everyday Ruff rule set is intentionally baseline-clean and focused on deterministic editing hygiene. Historical structural complexity debt is a separate concern owned by:

```bash
make lint-debt
```

That debt check is repository analysis implemented by `scripts/ruff_debt.py`; it is not Ruff-version compatibility testing.

## uv

Minimum supported version:

```text
uv >=0.10.0
```

The requirement is declared using uv's native `[tool.uv].required-version` setting. `make lock`, `make init`, and normal uv commands therefore work with 0.10.0 or any newer compatible uv. There is no Hashmarks-specific exact lock-generator patch pin.

`make init` may create or refresh a local `uv.lock` as uv resolves the declared dependency constraints. That lockfile is useful local prepared state for frozen/offline follow-up commands, but it is not committed, packaged, or treated as release identity.

## Policy

Tool-version policy should protect a real Hashmarks invariant, not create synthetic qualification work. Raise a minimum or add an upper bound only for a concrete semantic, security, or platform reason. Prefer one project-owned configuration and ordinary product tests over duplicated compatibility lanes.
