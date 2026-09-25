# Hashmarks MCP server for coding agents

Hashmarks exposes an optional **local, read-only stdio Model Context Protocol (MCP) server** for coding agents and developer tools, including Claude Code, Codex, OpenCode, and Pi through an MCP adapter. It gives MCP clients bounded codebase search, repository context, ownership and verification evidence, and change impact analysis from the same local repository-intelligence layer. MCP is only a transport adapter over existing Hashmarks repository intelligence; it does not add planning, editing, shell execution, git ownership, retries, model routing, or workflow orchestration.

## Install

For end users on Linux x86_64 (including WSL2), install the self-contained CLI + MCP runtime:

```bash
curl -fsSL https://raw.githubusercontent.com/Hugloss/Hashmarks/main/install.sh | sh
hashmarks --version
```

The installer downloads the matching executable and SHA-256 asset from GitHub Releases, verifies the executable before installing it to `~/.local/bin/hashmarks`, and does not require Python, uv, pip, or PyPI access on the target machine.

Source contributors should not replace the locked development environment with the standalone binary. Use `uv sync --frozen --extra mcp --group test` when developing or qualifying Hashmarks itself.

For OpenCode end users, register Hashmarks from the repository OpenCode should analyze:

```bash
cd /path/to/target/repository
hashmarks install --opencode
opencode mcp list
```

Hashmarks delegates configuration writing to OpenCode's own CLI and registers the exact installed Hashmarks executable with `--workspace . mcp`. This avoids requiring users to know OpenCode's config-file schema.

## Run

From a repository:

```bash
hashmarks --workspace . mcp
```

One server process binds one canonical workspace. Start another process for another repository. The first repository-intelligence tool call may build or reconcile the CodeMap; MCP discovery itself does not pre-index the repository.

## Tool surface

Hashmarks intentionally exposes a small read-only repository-intelligence tool catalog:

| Tool | Purpose |
| --- | --- |
| `repository_context` | compact orientation, generation/freshness, languages, areas, projects |
| `find` | bounded repository path/symbol discovery |
| `task_evidence` | role-separated retrieval, explicit-target, ownership, verification, freshness, ambiguity, and next-read repository evidence |
| `change_impact` | bounded structural impact for caller-reported changed paths |
| `correlate_evidence` | correlate bounded external/derived observations to canonical repository evidence without inferring causation |
| `dependency_codemap` | qualify producer-neutral dependency observations and run bounded factual dependency queries |
| `repository_declarations` | bind explicitly correlated declarations across files/formats to exact repository evidence and report equality/difference, ambiguity, qualified absence, and factual deltas |
| `post_change` | refresh changed paths against a previous `task_evidence` packet and return evidence deltas |

The tools are read-only from the repository consumer's perspective. Hashmarks may update its own disposable derived cache while answering them.

`task_evidence` uses `hashmarks.task-evidence.v2`. Retrieval order is relevance evidence only and carries no ownership authority. Ownership resolution, ambiguity, verification, and freshness are separate fields; current freshness never implies a uniquely resolved owner. The consumer remains responsible for deciding whether and how to act on the evidence.

`correlate_evidence` accepts structured evidence bundles, not raw log streams. Producer-specific parsing/ingestion remains outside the MCP adapter. The tool preserves external claims, ambiguity, completeness, source equivalence, and repository deltas; interpretation and action remain consumer-owned. See [Evidence correlation](../reference/EVIDENCE_CORRELATION.md).

`repository_declarations` accepts producer-normalized declaration groups. Semantic extraction, grouping, normalized values, correspondence, and coverage remain provider claims; Hashmarks binds them to current exact repository evidence and reports canonical equality/difference, ambiguity, coverage-qualified absence, identity, freshness, and factual deltas without selecting a winning declaration. See [Repository declarations](../reference/REPOSITORY_DECLARATIONS.md).

## Freshness and concurrency

The adapter serializes refresh and tool execution inside one MCP server process. Multiple hosts may still spawn independent Hashmarks processes against the same workspace and derived state, so the MCP boundary also boundedly retries only the known transient races that are safe to recompute from scratch: an incomplete `BUILDING` generation, a generation changing during a decision session, or a file changing while it is hashed. Validation failures and unrelated runtime errors are never retried.

Each retry reruns the complete CodeMap operation against current durable state. There is no stale-result fallback, previous-generation serving layer, or second freshness system. CodeMap and repository identity remain authoritative; exhaustion fails closed.

The normal OSS suite includes a bounded version of this multi-process/live-mutation regression, so contributors exercise the concurrency contract with no external agent host installed:

```bash
make test
```

Release qualification then scales the same invariant with:

```bash
make mcp-concurrency-stress
```

The heavier stress runs independent reader processes while source bytes change and requires zero final errors, zero leaked `BUILDING` payloads, and monotonic observed generations. OpenCode/Claude/Codex/Pi executions stay separate because they require external host installations, credentials, and models.

## Project-local host registration

Hashmarks keeps host integration inside the repository. The checked-in development registrations do not require editing a user's global host config. Run `uv sync --frozen --extra mcp --group test` first so the local `uv run --frozen --no-sync hashmarks ...` command is available without rewriting dependency authority.

### OpenCode MCP server configuration

`opencode.json` contains the project-local `mcp.hashmarks` registration. OpenCode should be started from this repository so it discovers that project config.

### Claude Code MCP server configuration

Claude Code reads the checked-in `.mcp.json` project registration. The same file is also deliberately usable by Pi's MCP adapter, avoiding a second repository-wide MCP registry. Claude Code may require the normal project-MCP approval the first time it sees the shared server.

### Codex MCP server configuration

Codex loads `.codex/config.toml` only after the repository is trusted. `make mcp-host-status` distinguishes this normal bootstrap state as `PROJECT TRUST REQUIRED` instead of reporting a broken registration. Open Codex once in the repository and approve project trust, then rerun the status check.


Codex reads the checked-in `.codex/config.toml` project registration. Hashmarks does not use `codex mcp add` for this repository because that command currently writes user-global configuration; the repository-local TOML keeps the integration scoped to this checkout.

### Pi MCP server configuration

Pi core intentionally ships without a native MCP client. To use Hashmarks MCP with Pi, install the project/user-selected adapter:

```bash
pi install npm:pi-mcp-adapter
```

`pi-mcp-adapter` reads the repository's `.mcp.json`, so no additional Hashmarks-specific Pi config is required. Hashmarks does not vendor or own that third-party adapter.

### Integration status

Inspect all four hosts without modifying their global configuration:

```bash
make mcp-host-status
```

The report separates `PASS`, `PROJECT TRUST REQUIRED`, `NOT INSTALLED`, `NOT REGISTERED`, `FOREIGN CONFIG`, `MISCONFIGURED`, `ADAPTER REQUIRED`, `READY`, `STALE`, `NOT CHECKED`, and `NOT RECORDED`. A registration PASS only proves the project file; host discovery and a real MCP-call receipt are separate facts. Real-call receipts bind to the current source identity, exact checked-in registration SHA-256, and host version, so old evidence cannot silently survive a source/config/host upgrade.

## OpenCode release host qualification

The repository includes a real-host qualification command for maintainers:

```bash
opencode --version
opencode models
OPENCODE_MODEL=<provider/model> make mcp-opencode-check
```

The selected model must support tool calling and already have the provider credentials it needs. The gate does not trust the model's final prose: it runs OpenCode with JSON output and validates emitted `tool_use` events and their structured results. It builds and installs the candidate wheel with the `mcp` extra, creates a disposable repository, writes `opencode.json` inside that repository, verifies the OpenCode server connection, exercises `repository_context`, `find`, `task_evidence`, and `change_impact`, mutates the fixture outside Hashmarks, then resumes the same OpenCode session for `post_change` plus a final `repository_context` generation check.

The qualification registration uses absolute paths for the installed Hashmarks executable and disposable workspace. It does not depend on global OpenCode configuration.

On success the command prints `HASHMARKS OPENCODE MCP HOST GATE: PASS` and persists the canonical receipt plus diagnostic OpenCode JSONL event streams under `dist/`. A missing host or missing native MCP environment is `ENVIRONMENT_BLOCKED`; neither counts as release PASS evidence.

## Claude Code real-call qualification

```bash
CLAUDE_MODEL=<optional-model> make mcp-claude-check
```

The gate builds and installs the exact candidate wheel into an isolated environment, creates a disposable repository with `.mcp.json`, and runs Claude Code in streaming JSON mode. It requires `hashmarks` to be connected in the init event, requires `mcp__hashmarks__repository_context` and `mcp__hashmarks__find` to be present in the model-visible tool catalog, rejects any non-Hashmarks tool use, and validates successful results for both schemas. A host that connects the MCP server but omits the tools from the model-visible catalog is `ENVIRONMENT_BLOCKED`, not a Hashmarks PASS.

## Codex real-call qualification

```bash
CODEX_MODEL=<optional-model> make mcp-codex-check
```

The gate uses a disposable trusted repository and its project-local `.codex/config.toml`, validates Codex `item.completed` events of type `mcp_tool_call`, requires exactly `repository_context` and `find`, and rejects built-in command/file/web execution. The default path keeps Codex in a read-only sandbox. Some Codex versions cancel MCP calls in non-interactive `exec` despite a valid registration; that is recorded as `ENVIRONMENT_BLOCKED` rather than weakening the gate. Maintainers may explicitly opt into `CODEX_HOST_DANGEROUS=1` for the disposable fixture only; the gate never enables that mode implicitly.

## Pi real-call qualification

```bash
pi install npm:pi-mcp-adapter
PI_MODEL=<provider/model> make mcp-pi-check
```

The gate creates a disposable `.mcp.json`, launches Pi in JSON mode with built-in tools disabled and only the adapter's `mcp` proxy enabled, then requires real calls to `hashmarks_repository_context` and `hashmarks_find`. It validates the corresponding Hashmarks schemas and rejects any unexpected Pi tool execution. Adapter metadata/cache readiness alone cannot produce PASS.

## Product boundary

MCP must not add tools for:

- file writing or editing;
- shell/process execution;
- git/worktree lifecycle;
- test execution;
- planning/retries/recovery loops;
- model calls or sampling;
- agent prompts/workflows;
- remote repository tenancy.

Those responsibilities remain with the external consumer. Local stdio is the only supported Hashmarks MCP transport in the initial contract; remote HTTP is a separate future product decision.
