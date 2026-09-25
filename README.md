# Hashmarks — Repository intelligence and a local MCP server for coding agents

**Give AI coding agents a fast, local map of a codebase before they start reading everything.**

Hashmarks is **local repository intelligence** and a read-only **Model Context Protocol (MCP) server for coding agents**. It provides **codebase search for agents**, repository context, code navigation, symbols and references, code ownership, dependency relationships, **change impact analysis**, freshness, and verification evidence from the repository itself.

Use Hashmarks with **Claude Code, Codex, OpenCode, Pi**, other stdio MCP clients, developer tools, CI, or directly from the CLI and Python API. Hashmarks runs locally, does not call models, and does not edit files or execute shell commands.

> **Hashmarks understands the repository. Your agent still decides what to do.**

**Works with:** Claude Code · Codex · OpenCode · Pi · stdio MCP clients
**Use it as:** CLI · Python library · local MCP server

Install from PyPI: `pip install hashmarks`

## Why Hashmarks

Coding agents repeatedly spend context and tool calls rediscovering the same codebase. Hashmarks keeps useful repository knowledge available as bounded, freshness-aware evidence.

- **Codebase search for coding agents.** Find relevant paths, symbols, references, imports, tests, and task-local evidence without scanning the whole repository.
- **Repository context before source reads.** Start with languages, projects, repository areas, ownership, and structural outlines before opening implementation bodies.
- **Change impact analysis.** See reverse dependencies, affected files/projects, and structurally related tests before or after a change.
- **Code navigation and ownership.** Trace symbols, references, imports, callers, project boundaries, and likely implementation owners.
- **Freshness-aware evidence.** Distinguish current, stale, and unknown repository evidence instead of silently serving an old index as truth.
- **Observer-aware deltas.** Keep repository change separate from observer-capability change, and compare stable evidence identities instead of treating every newly visible fact as a repository edit.
- **Repository evidence bindings.** Bind opaque consumer IDs to exact line ranges or whole repository members, then compare direct/member/dependency/relationship evidence without transferring consumer policy into Hashmarks.
- **Evidence correlation.** Map bounded runtime/derived observations such as tracebacks, CI failures, resolver output, or dependency-tree evidence back to canonical repository truth while preserving ambiguity, completeness, and source equivalence.
- **Cross-artifact declarations.** Represent explicitly correlated declarations of the same conceptual repository fact across files and formats, preserving exact evidence, freshness, ambiguity, qualified absence, and disagreement without choosing which declaration should win.
- **Local and read-only for agent consumers.** Hashmarks maintains disposable derived state, while editing, execution, git, planning, and model decisions stay with the caller.

## Quick start

Run it inside any repository:

```bash
hashmarks --workspace . map sync
hashmarks --workspace . orient
hashmarks --workspace . find "where is cache invalidation implemented?"
hashmarks --workspace . affected path/to/file.py
```

Useful repository-intelligence commands:

```bash
hashmarks --workspace . outline path/to/file.py
hashmarks --workspace . refs SymbolName
hashmarks --workspace . tests SymbolName
hashmarks --workspace . structural-locality path/to/file.py::qualified_symbol
hashmarks --workspace . map status
hashmarks --workspace . map findings
```

Hashmarks has no required third-party runtime dependencies. Its CodeMap is derived local state and can be rebuilt from repository bytes and supported repository metadata.

## MCP server for coding agents

Install the optional MCP support:

```bash
pip install "hashmarks[mcp]"
```

Hashmarks exposes one local, read-only **stdio MCP server** with a focused repository-intelligence tool catalog:

| MCP tool | What it gives the coding agent |
| --- | --- |
| `repository_context` | compact repository orientation, languages, projects, generation and freshness |
| `find` | bounded codebase search across paths and symbols |
| `task_evidence` | role-separated retrieval, ownership, ambiguity, verification, freshness and next-read evidence |
| `change_impact` | structural impact for changed or candidate paths |
| `correlate_evidence` | bounded external/derived observations correlated to canonical repository evidence |
| `dependency_codemap` | producer-neutral dependency observations and factual dependency queries |
| `repository_declarations` | cross-file/format declarations with exact evidence, ambiguity, qualified absence, and disagreement |
| `post_change` | refreshed evidence and deltas after the caller changes files |

You normally **do not start Hashmarks MCP by hand**. Put the MCP configuration in the **target project** you want the agent to analyze. The agent host starts `hashmarks --workspace . mcp` as a stdio child process.

### Claude Code MCP server

Create `.mcp.json` in the target project:

```json
{
  "mcpServers": {
    "hashmarks": {
      "command": "hashmarks",
      "args": ["--workspace", ".", "mcp"]
    }
  }
}
```

Then start Claude Code from that project directory.

### Codex MCP server

Create `.codex/config.toml` in the target project:

```toml
[mcp_servers.hashmarks]
command = "hashmarks"
args = ["--workspace", ".", "mcp"]
cwd = "."
enabled = true
```

Then start Codex from that project directory.

### OpenCode MCP server

Add Hashmarks to `opencode.json` in the target project:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "hashmarks": {
      "type": "local",
      "command": ["hashmarks", "--workspace", ".", "mcp"],
      "cwd": ".",
      "enabled": true
    }
  }
}
```

Then start OpenCode from that project directory.

### Pi MCP server

Pi uses MCP through `pi-mcp-adapter`:

```bash
pi install npm:pi-mcp-adapter
```

Copy the same `.mcp.json` shown for Claude Code into the **target project**, then start Pi there:

```bash
cd /path/to/your/project
pi
```

Pi starts Hashmarks automatically through the adapter. Do not leave a separate Hashmarks MCP process running in another repository.

For the complete tool schemas, freshness behavior, concurrency guarantees, and host qualification details, see [Hashmarks MCP server for coding agents](docs/integration/MCP.md).

## What Hashmarks provides

| Area | Capability |
| --- | --- |
| Repository map | Incremental CodeMap over paths, symbols, imports, references, calls, projects, and tests |
| Codebase search | Task-oriented retrieval, lexical search, structural outlines, exact symbol/source views |
| Repository context | Languages, projects, areas, ownership, generation, freshness, and bounded orientation |
| Code navigation | Symbols, references, imports, callers, projects, repository areas and bounded source views |
| Code ownership | Repository ownership, import ownership, cache ownership, verification ownership, qualified identity |
| Change impact analysis | Reverse impact, affected files/projects, structurally related tests, post-change evidence |
| Freshness | Generation-bound observations, invalidation, stale/unknown/current evidence semantics |
| Verification evidence | Bounded verification relevance and repository-bound verification descriptions |
| Structural locality | Exact-symbol call/caller closure, forwarding shape, context/file fan-out, verifier paths, ambiguity and pre/post structural deltas without refactor policy |
| Content identity | Canonical file, directory, manifest, and repository identities |
| Interchange | Strict producer/consumer contracts, provenance, validation, and conformance surfaces |
| Evidence bindings | Opaque consumer bindings to exact line/member evidence, declared dependencies, relationship evidence, deltas, and change coverage |\n| Evidence correlation | Request-scoped external/derived anchors correlated to repository paths, symbols, source equivalence, relationships, and before/after deltas |
| Repository declarations | Explicitly correlated conceptual declarations distributed across files/formats, with exact evidence, normalized equality/difference, ambiguity, coverage-qualified absence, identity, and factual deltas |

Built-in lightweight structural parsing covers Python, JavaScript/TypeScript, Go, and Rust. Optional Tree-sitter range enrichment can add precise symbol ranges for additional languages when available. Native/project evidence can also be imported from supported adapters and SCIP.

If you provide `--state-dir`, durable CodeMap state is bound to the canonical workspace that first claims it. Hashmarks rejects reuse of the same explicit state directory by another repository before serving repository evidence.

## Common workflows

### Codebase search for coding agents

Use task-oriented search when an agent needs to locate implementation before opening source files:

```bash
hashmarks --workspace . find "where is cache invalidation implemented?"
hashmarks --workspace . refs CacheOwner
```

Hashmarks combines repository paths, symbols, references, and structural evidence so the caller can narrow the next read instead of scanning the entire codebase.

### Repository context for a large codebase

Start with a compact repository map before loading implementation bodies into context:

```bash
hashmarks --workspace . orient
hashmarks --workspace . map status
```

This is useful for large repositories where a coding agent needs to understand projects, languages, areas, and freshness before deciding what source to inspect.

### Change impact analysis before editing

Ask what depends on a file and which tests are structurally relevant:

```bash
hashmarks --workspace . affected path/to/file.py
hashmarks --workspace . tests SymbolName
```

Hashmarks reports repository-derived impact and verification evidence. The external agent or developer still decides what to edit and what to execute.

### Fresh repository evidence after changes

After files change, sync the derived CodeMap and query the new generation:

```bash
hashmarks --workspace . map sync
hashmarks --workspace . find "what changed around this behavior?"
```

MCP clients can use `post_change` for the same repository-intelligence refresh without giving Hashmarks file-editing or execution authority.

## Python API

### Repository intelligence with `CodeMap`

```python
from pathlib import Path

from hashmarks import CodeMap

workspace = Path(".").resolve()

with CodeMap(workspace) as codemap:
    codemap.sync()

    print(codemap.orient())

    for hit in codemap.find_task(
        "where is repository freshness decided?",
        limit=5,
    ):
        print(hit.path, hit.score)

    print(codemap.affected("hashmarks/codemap/engine.py"))
```

### Repository evidence bindings

```python
from hashmarks import CodeMap

with CodeMap(".") as codemap:
    codemap.sync()
    before = codemap.repository_evidence_bindings(
        [
            {
                "binding_id": "consumer:contract-a",
                "evidence": [
                    {"path": "src/owner.py", "start_line": 10, "end_line": 14},
                    {"scope": "member", "path": "uv.lock"},
                ],
            }
        ],
        dependency_paths={"consumer:contract-a": ["pyproject.toml"]},
    )
```

Bindings are read-only repository intelligence: the ID is opaque, exact line/member evidence remains separate from containing-member/dependency/relationship change, and Hashmarks does not decide what the consumer should execute. See [Repository evidence bindings](docs/reference/REPOSITORY_EVIDENCE_BINDINGS.md).

### Cross-artifact repository declarations

`CodeMap.repository_declarations(...)` binds provider-normalized declaration claims to exact current repository evidence and reports equivalence, difference, ambiguity, and coverage-qualified absence. Semantic extraction/correspondence remain provider claims; Hashmarks does not choose a winning declaration. See [Repository declarations](docs/reference/REPOSITORY_DECLARATIONS.md).

### Canonical repository identity with `RepositoryIdentity`

```python
from hashmarks import File, RepositoryIdentity

with RepositoryIdentity(".", mode="local") as identity:
    snapshot = identity.snapshot(File("pyproject.toml"))
    print(snapshot.hash)
```

See [`examples/`](examples/) and the [getting-started guide](docs/GETTING_STARTED.md) for more installed-package examples.

## How Hashmarks works

Hashmarks separates canonical repository identity from derived repository intelligence:

```text
repository bytes / manifests / declared relationships
                    │
                    ▼
          canonical identity + observation
                    │
                    ▼
          derived CodeMap / evidence graph
                    │
                    ▼
       bounded consumer-facing projections
                    │
                    ▼
         agent / IDE / human / CI
```

The canonical identity path does not depend on CodeMap parsing. CodeMap can use richer structural evidence without becoming identity authority. Caches and watchers accelerate work but cannot manufacture freshness.

For the detailed design, see [Architecture](docs/reference/ARCHITECTURE.md) and [Normative invariants](docs/reference/INVARIANTS.md).

## Core architecture

Hashmarks is a repository observer that exposes repository intelligence, not an autonomous coding agent, policy engine, or execution engine. It can tell a consumer what the repository contains, what appears to own a behavior, what may be affected, what evidence is stale or ambiguous, and what verification surfaces are relevant. The consumer remains responsible for reasoning, edits, execution, retries, git/worktrees, and final decisions.

## Non-negotiable agent boundary

The normative contract is [`docs/reference/PRODUCT_BOUNDARY.md`](docs/reference/PRODUCT_BOUNDARY.md).

**Usefulness is not ownership.** A capability does not belong in Hashmarks merely because it would help a coding agent or execution system.

> **Hashmarks owns repository facts, relationships, observations, provenance, completeness, freshness, and deltas. Consumers own reasoning, edits, execution, retries, and final decisions. Hashmarks does not choose the consumer's next action.**

`AGENTS.md` is the contributor/agent-facing guardrail for this boundary. Public consumers do not need Oh-Goon; the important product rule is that Hashmarks transfers repository evidence, never execution authority.

## CLI map

Run `hashmarks --help` for the complete command surface.

| Command | Purpose |
| --- | --- |
| `map sync` | Build/update derived repository intelligence |
| `map status` | Inspect CodeMap generation and freshness |
| `map findings` | Project high-signal actionable repository findings |
| `orient` | Compact repository context/orientation capsule |
| `find QUERY` | Search maintained path/symbol evidence |
| `outline PATH` | Show code structure without loading full bodies |
| `source SYMBOL` | Return exact symbol source under an explicit budget |
| `deps QUERY` / `refs QUERY` | Inspect static dependency/reference evidence |
| `affected PATH` | Reverse change impact from repository relationships |
| `tests QUERY` | Structurally related verification surfaces |
| `structural-locality PATH::QUALNAME` | Fresh bounded structural-locality facts for one exact symbol |
| `structural-locality-delta --before A --after B` | Compare two locality packets without deciding whether the tradeoff is good |
| `task-evidence TASK` | Project bounded retrieval, explicit-target, ownership, verification, freshness, and related repository evidence |
| `change-impact TASK --changed PATH` | Recompute impact and verification relevance from changed paths |
| `post-change TASK --changed PATH --previous-evidence FILE` | Reconcile changed paths and return evidence deltas |
| `doctor` | Show runtime/observer configuration |

## FAQ

### Is Hashmarks an MCP server?

Yes. `pip install "hashmarks[mcp]"` adds the official MCP Python SDK and enables a local read-only stdio MCP server. The same package also works directly as a CLI and Python library.

### Does Hashmarks work with Claude Code, Codex, OpenCode, and Pi?

Yes. Hashmarks provides project-local configuration examples for Claude Code, Codex, OpenCode, and Pi through `pi-mcp-adapter`. Any compatible stdio MCP client can launch `hashmarks --workspace . mcp`.

### Does Hashmarks send my source code to a cloud service?

Hashmarks itself runs locally and does not call a model or remote repository-analysis service. An external coding-agent host may have its own network/model behavior; that is outside Hashmarks.

### Does Hashmarks edit code or run tests?

No. Hashmarks provides repository intelligence and verification relevance. The coding agent, developer, CI system, or execution system owns edits and command execution.

### What is the difference between repository intelligence and ordinary code search?

Search is one part of the product. Hashmarks also tracks structural relationships, ownership, reverse impact, repository freshness, generation-bound evidence, verification relevance, and canonical content identity so consumers can reason about *why* a result matters and whether it is current.

### Can I use one Hashmarks installation with many repositories?

Yes. Install Hashmarks once, then launch it with `--workspace .` from each target repository. Each MCP process binds one canonical workspace, and explicit durable state directories cannot be reused across different repositories.

## Development

For contributors working from a source checkout:

```bash
make init
make dev-check
make mcp-host-status
make mcp-opencode-check
```

The normal OSS test surface does not require an external coding-agent host. `make mcp-host-status` inspects project-local MCP registration/readiness; `make mcp-opencode-check` is the real OpenCode release host gate. Native release qualification and the other real-host MCP gates are documented separately.

See [Contributing](.github/CONTRIBUTING.md) and the [MCP integration guide](docs/integration/MCP.md).

## Documentation

- [Getting started with Hashmarks repository intelligence](docs/GETTING_STARTED.md)
- [Hashmarks MCP server for coding agents](docs/integration/MCP.md)
- [Architecture](docs/reference/ARCHITECTURE.md)
- [Observer and delta model](docs/reference/OBSERVER_DELTA.md)
- [Repository evidence bindings](docs/reference/REPOSITORY_EVIDENCE_BINDINGS.md)
- [Repository declarations](docs/reference/REPOSITORY_DECLARATIONS.md)
- [Evidence correlation](docs/reference/EVIDENCE_CORRELATION.md)
- [Structural locality evidence](docs/reference/STRUCTURAL_LOCALITY.md)
- [Product boundary](docs/reference/PRODUCT_BOUNDARY.md)
- [Normative invariants](docs/reference/INVARIANTS.md)
- [Public API and stability policy](docs/reference/API_STABILITY.md)
- [Changelog](CHANGELOG.md)

## Project status

Current package version: **0.22.0**.

Hashmarks is under active development. Current repository-intelligence contracts are documented explicitly; new integrations should use the supported CLI, Python API, and MCP surfaces rather than historical development experiments.

The repository-owned release workflow builds wheel/sdist once, qualifies those exact bytes, binds them in a release manifest plus SHA-256 checksums, and publishes the same artifact bundle through PyPI Trusted Publishing. External GitHub/PyPI environment approval and Trusted Publisher registration remain release-owner responsibilities.

## Security

Please do not publish sensitive vulnerability details in a public issue. See [`.github/SECURITY.md`](.github/SECURITY.md) for reporting guidance and scope.

## License

Hashmarks is licensed under the [Apache License 2.0](LICENSE).
