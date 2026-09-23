# Getting started with Hashmarks repository intelligence

Hashmarks provides local repository intelligence, codebase search for coding agents, repository context, change-impact evidence, and an optional read-only MCP server for coding agents. This guide covers the current repository-intelligence workflow from installation through CLI, Python, and MCP usage.

## Requirements

- Python 3.11 or newer
- Linux or WSL is recommended for watcher/daemon behavior and performance qualification

Hashmarks has no required third-party runtime dependency. Git and `uv` are development/qualification tools, not requirements for the core installed package.

## Install and try Hashmarks

```bash
pip install hashmarks
```

Check the installed CLI against a repository:

```bash
hashmarks --workspace . doctor --mode local
```

Build the repository map:

```bash
hashmarks --workspace . map sync
hashmarks --workspace . map status
```

The CodeMap is derived state. It can be rebuilt from repository bytes and supported repository metadata.

## Orient before reading source

```bash
hashmarks --workspace . orient
```

Use orientation and outlines before loading implementation bodies when possible:

```bash
hashmarks --workspace . find "repository ownership"
hashmarks --workspace . outline hashmarks/codemap/engine.py
hashmarks --workspace . refs CodeMap
hashmarks --workspace . affected hashmarks/codemap/engine.py
```

This progressive pattern is useful for agents, IDE integrations, and humans because it keeps repository evidence bounded.

## Python API

```python
from pathlib import Path

from hashmarks import CodeMap

with CodeMap(Path(".")) as codemap:
    codemap.sync()
    capsule = codemap.orient()
    hits = codemap.find_task("where is cache invalidation owned?", limit=10)

print(capsule)
for hit in hits:
    print(hit.path, hit.kind, hit.score)
```

For canonical content identity:

```python
from hashmarks import File, RepositoryIdentity

with RepositoryIdentity(".", mode="local") as identity:
    snapshot = identity.snapshot(File("pyproject.toml"))
    print(snapshot.hash)
```

## Long-lived local map maintenance

On Linux/WSL:

```bash
hashmarks --workspace . map watch
```

A watcher is an accelerator. If Hashmarks cannot prove observation continuity, evidence becomes unknown/stale and must be reconciled before stronger authority is issued.

## Cleaning state

Inspect before cleaning:

```bash
hashmarks --workspace . map status
```

Clean workspace CodeMap state:

```bash
hashmarks --workspace . map clean
```

Shared content-addressed artifacts can be useful across Git worktrees. Do not assume a developer's shared cache is empty when writing tests; isolate cache/state roots explicitly when isolation is part of the test contract.

## Develop and qualify from source

A source checkout uses `uv` and Git for the repository-owned development/qualification workflow:

```bash
make init
uv run hashmarks --workspace . doctor --mode local
make dev-check
```

For full native release qualification:

```bash
make test-profile
```

For bounded/resumable testing:

```bash
make test-shard-plan
make test-shard TEST_SHARD=0
```

## Next reading

- [`reference/ARCHITECTURE.md`](reference/ARCHITECTURE.md) — system layers and authority model
- [`maintainers/CODEMAP.md`](maintainers/CODEMAP.md) — where CodeMap behavior is implemented and how common requests flow through the code
- [`reference/PRODUCT_BOUNDARY.md`](reference/PRODUCT_BOUNDARY.md) — what belongs in Hashmarks
- [`reference/INVARIANTS.md`](reference/INVARIANTS.md) — fail-closed semantic guarantees
- [`integration/OH_GOON_INTEGRATION.md`](integration/OH_GOON_INTEGRATION.md) — evidence handoff to execution/certification systems

## Local MCP server for coding agents

Hashmarks can act as a local, read-only Model Context Protocol (MCP) server for coding agents. Install the optional MCP support:

```bash
pip install "hashmarks[mcp]"
```

For normal agent use, put the Hashmarks MCP registration in the **target repository** and start your coding-agent host from that repository. The host launches `hashmarks --workspace . mcp` as a stdio child process; you do not need to keep a separate Hashmarks server running.

Claude Code and Pi with `pi-mcp-adapter` can use a project-local `.mcp.json`; Codex uses `.codex/config.toml`; OpenCode uses `opencode.json`. See [`integration/MCP.md`](integration/MCP.md) for copy-ready host configuration and the five-tool contract. MCP is a read-only repository-intelligence transport; the external agent retains editing, execution, git, reasoning, and orchestration.

To inspect the server manually, run:

```bash
hashmarks --workspace . mcp
```

The process waits for MCP JSON-RPC on stdin. Stop it with `Ctrl+C`; normal host integrations launch it automatically.
