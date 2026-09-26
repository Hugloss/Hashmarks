# Agent-evaluation fixtures

This directory contains **development measurement infrastructure**, not installed Hashmarks product state.

Hashmarks is repository intelligence. Synthetic repositories, corpora, packets, and worker outputs are used to measure how external consumers behave with and without Hashmarks evidence. They do not define runtime APIs, agent workflow authority, execution policy, or compatibility obligations.

Canonical synthetic fixture inputs are owned by the evaluation code that materializes them into a caller-supplied run directory. Generated blind inputs, packets, worker outputs, and result files are not committed as parallel repository state. Real-world retained qualification evidence, when exact external provenance matters, belongs in the repository-quality evidence surface rather than in a generated fixture mirror.

New product behavior must still pass the product-admission contract in `docs/reference/PRODUCT_BOUNDARY.md`; benchmark wins do not authorize moving consumer workflow into Hashmarks.


## One-command launch

Benchmark launch settings live in `benchmarks/benchmark.toml`. The normal local
entrypoint is:

```sh
make benchmark
```

Use `make benchmark BENCHMARK=quick` for a one-task smoke run and
`make benchmark BENCHMARK=chatgpt` in constrained hosted environments that
cannot assume a nested Codex executable. The shell-independent equivalent is
`uv run --frozen python -m scripts.agent_evaluation.benchmark <profile>`.

Use `make benchmark-show BENCHMARK=<profile>` to inspect the exact stored
command without executing it. Profiles only own launch configuration; benchmark
semantics remain in their existing measurement modules.
