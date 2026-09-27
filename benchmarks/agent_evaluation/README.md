# Agent-evaluation fixtures

This directory contains **development measurement infrastructure**, not installed Hashmarks product state.

Hashmarks is repository intelligence. Synthetic repositories, corpora, packets, and worker outputs are used to measure how external consumers behave with and without Hashmarks evidence. They do not define runtime APIs, agent workflow authority, execution policy, or compatibility obligations.

Canonical synthetic fixture inputs are owned by the evaluation code that materializes them into a caller-supplied run directory. Generated blind inputs, packets, worker outputs, and result files are not committed as parallel repository state. Real-world retained qualification evidence, when exact external provenance matters, belongs in the repository-quality evidence surface rather than in a generated fixture mirror.

New product behavior must still pass the product-admission contract in `docs/reference/PRODUCT_BOUNDARY.md`; benchmark wins do not authorize moving consumer workflow into Hashmarks.


## Native Codex and OpenCode benchmark

`make benchmark` runs one pinned localization task through six conditions: native
OpenCode and native Codex, each with bare, Hashmarks MCP, and Enola MCP access.
`make benchmark BENCHMARK=matrix` runs all three matrix tasks (18 trials).
`make benchmark BENCHMARK=cycle` runs an adapted TypeScript cycle task three
times per condition (18 trials). `make benchmark-show` lists definitions without
running agents; `make benchmark-report` reads verified results. Set
`BENCH_AGENT=opencode-native` or `BENCH_AGENT=codex-native` to run one native CLI.
The experiments and runner live in the adjacent `agentsCookbook` checkout;
set `AGENTS_COOKBOOK=/path/to/checkout` if it is elsewhere. Set `BENCH_ROOT`
to change the local result/cache/work directory. `BENCH_PYTHON` selects the
Python interpreter for agentsCookbook; use one outside Hashmarks' `.venv` if
that environment is active.

The run uses your installed native CLI model/provider/auth settings. Check that
`codex` and `opencode` already work interactively. Native Codex requires a
`model` in your `~/.codex/config.toml`, and native OpenCode requires a configured
model. The benchmark does not set a model or create MCP registrations.

Register `hashmarks` and `enola` as stdio MCP servers in both host CLIs. The
Hashmarks server command must resolve to this checkout's `.venv/bin/hashmarks`
through `PATH`; use `hashmarks --workspace . mcp` from the trial working directory.
The Enola server should use `enola` with no args, so it observes the trial working
directory. For Codex, the global `~/.codex/config.toml` can contain:

```toml
[mcp_servers.hashmarks]
command = "hashmarks"
args = ["--workspace", ".", "mcp"]
cwd = "."

[mcp_servers.enola]
command = "enola"
args = []
cwd = "."
```

Keep your existing Codex model and authentication fields; this is only an MCP
example. Configure the same command/args/cwd in your native OpenCode MCP config.
The runner verifies workspace binding and the selected executable, and marks a
trial `INCOMPLETE` if a registration is stale or absent. `codex mcp list --json`
and `opencode mcp list` are useful host checks. Enola hooks are excluded; only
MCP access varies between subject arms.

The earlier `codex-agent-economics` evaluation remains available through its
separate Make targets. The native matrix compares subject assistance within each
agent/model configuration; its scores do not certify either product. The adapted
cycle task separately counts behavior success and module dependency cycles. See the suite
READMEs in `agentsCookbook/benchmarks/suites/repository-intelligence/` for exact
pinned source and oracle semantics.
