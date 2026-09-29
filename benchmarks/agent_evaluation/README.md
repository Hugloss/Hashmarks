# Agent-evaluation fixtures

This directory contains **development measurement infrastructure**, not installed Hashmarks product state.

Hashmarks is repository intelligence. Synthetic repositories, corpora, packets, and worker outputs are used to measure how external consumers behave with and without Hashmarks evidence. They do not define runtime APIs, agent workflow authority, execution policy, or compatibility obligations.

Canonical synthetic fixture inputs are owned by the evaluation code that materializes them into a caller-supplied run directory. Generated blind inputs, packets, worker outputs, and result files are not committed as parallel repository state. Real-world retained qualification evidence, when exact external provenance matters, belongs in the repository-quality evidence surface rather than in a generated fixture mirror.

New product behavior must still pass the product-admission contract in `docs/reference/PRODUCT_BOUNDARY.md`; benchmark wins do not authorize moving consumer workflow into Hashmarks.


## agentsCookbook-owned native Codex and OpenCode benchmark

### Benchmark ownership

Hashmarks does **not** own or implement this benchmark. Hashmarks is one subject
under test. The benchmark harness, frozen experiment definitions, admission,
execution evidence, independent grading, receipts, and reporting are owned by
the adjacent **agentsCookbook** checkout.

The Hashmarks `make benchmark*` targets are convenience entry points only. They
delegate to agentsCookbook while binding this Hashmarks checkout as the subject
source:

```text
Hashmarks checkout
    make benchmark*
         |
         v
agentsCookbook
    benchmark harness / experiment authority
         |
         +-- bare
         +-- exact admitted Hashmarks executable
         +-- exact admitted Enola executable
```

For native OpenCode trials, agentsCookbook also supplies the temporary
trial-scoped MCP exposure for the selected subject. A Hashmarks/OpenCode
registration in project or user configuration is **not benchmark authority** and
is not required for the OpenCode benchmark. OpenCode remains authoritative for
model, provider, authentication, permissions, and user configuration.

Start from this Hashmarks checkout with the adjacent `agentsCookbook` checkout:

```sh
make init
make benchmark-show
make benchmark-check
make benchmark
make benchmark-report
```

`make benchmark` runs one pinned localization task through six conditions: native
OpenCode and native Codex, each with bare, Hashmarks MCP, and Enola MCP access.
`make benchmark BENCHMARK=matrix` runs all three matrix tasks (18 trials).
`make benchmark BENCHMARK=cycle` runs an adapted TypeScript cycle task three
times per condition (18 trials). `make benchmark-show` lists definitions without
running agents. `make benchmark-check` prepares every selected native arm and
stops before any model call if source, subject, model, MCP binding, or oracle
setup is unavailable. It cannot prove remote model authentication; first confirm
each native CLI works interactively. Set `BENCH_AGENT=opencode-native` or
`BENCH_AGENT=codex-native` to select one native CLI.

The experiments and runner live in the adjacent `agentsCookbook` checkout; set
`AGENTS_COOKBOOK=/path/to/checkout` if it is elsewhere. Each `make benchmark`
invocation creates a fresh local run under `BENCH_ROOT` and prints its path.
`make benchmark-report` reads the latest run for the selected `BENCHMARK` mode,
including its original agent selection. Use `BENCH_RUN=<printed-run-id>` to
resume or report a specific run; resume only with the same model, MCP, and
harness setup. Start a new run after changing them. `BENCH_PARTIAL=1` explicitly
reports verified receipts available so far; a normal report requires every
selected definition. `BENCH_PYTHON` selects the agentsCookbook interpreter,
including when Hashmarks' `.venv` is active.

The run uses your installed native CLI model/provider/auth settings. Check that
`codex` and `opencode` already work interactively. Native Codex requires a
`model` in your `~/.codex/config.toml`, and native OpenCode requires a configured
model. The benchmark never chooses or rewrites either host's model/provider/auth
configuration.

Codex still uses its native MCP registrations. Register `hashmarks` and `enola`
there as stdio MCP servers. The Hashmarks server command must resolve to this
checkout's `.venv/bin/hashmarks` through `PATH`; use
`hashmarks --workspace . mcp` from the trial working directory. The Enola server
should use `enola` with no args, so it observes the trial working directory. For
Codex, the global `~/.codex/config.toml` can contain:

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

Keep your existing Codex model and authentication fields.

Native OpenCode is intentionally different. It does **not** need a pre-existing
Hashmarks or Enola MCP registration for the benchmark. agentsCookbook resolves the
selected subject from the benchmark environment, records the exact executable identity,
and supplies a temporary trial-scoped MCP exposure through OpenCode's native runtime
configuration. OpenCode still owns model/provider/auth/permissions. Any project or
global `mcp.hashmarks` / `mcp.enola` entry is observed but may be shadowed for the
trial; it does not choose the executable under test. End-user
`hashmarks install --opencode` registration is therefore not benchmark authority.

The benchmark puts this checkout's `.venv/bin` first on `PATH` and proves the
selected Hashmarks executable, exposure digest, and workspace binding before agent
work. For OpenCode, a missing subject executable, changed exposure identity, or
unprovable workspace binding yields `INCOMPLETE`; a missing native OpenCode subject
registration does not. For Codex, stale or absent native MCP registration still yields
`INCOMPLETE`. `codex mcp list --json` remains useful for Codex host checks. Enola
hooks are excluded; only MCP access varies between arms.

The earlier `codex-agent-economics` evaluation remains available through its
separate Make targets. The native matrix compares subject assistance within each
agent/model configuration; its scores do not certify either product. The adapted
cycle task separately counts behavior success and module dependency cycles. See the suite
READMEs in `agentsCookbook/benchmarks/suites/repository-intelligence/` for exact
pinned source and oracle semantics.
