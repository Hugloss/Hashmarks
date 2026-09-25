# Getting started with Hashmarks repository intelligence

Hashmarks provides local repository intelligence, codebase search for coding agents, repository context, change-impact evidence, and an optional read-only MCP server for coding agents. This guide covers the current repository-intelligence workflow from installation through CLI, Python, and MCP usage.

## Requirements

For the standalone CLI and MCP server:

- Linux x86_64, including WSL2
- `curl`
- `sha256sum` or `shasum`

Python 3.11 or newer is required only for the Python API and source development. Python, Git, and `uv` are development/qualification tools, not requirements for the standalone CLI or MCP server.

## Install and try Hashmarks

```bash
curl -fsSL https://raw.githubusercontent.com/Hugloss/Hashmarks/main/install.sh | sh
hashmarks --version
```

The installer downloads the current standalone release executable and its SHA-256 asset from GitHub Releases, verifies the executable, smoke-tests the downloaded candidate, and only then atomically replaces `~/.local/bin/hashmarks`. A broken candidate therefore does not destroy an existing working installation.

Check the installed CLI against a repository:

```bash
hashmarks --workspace . doctor --mode local
```

Build the repository map:

```bash
hashmarks --workspace . map sync
hashmarks --workspace . map status
```

The CodeMap is derived state. It can be rebuilt from repository bytes and supported repository metadata. Default repository-local state lives under `.hashmarks/`; Hashmarks makes that directory self-ignored by Git and owner-private where the platform exposes POSIX permissions. A pre-existing default-state symlink is rejected rather than followed.

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

The Python API is an in-process integration surface. When working from the Hashmarks source checkout, materialize the repository-owned environment before using it:

```bash
uv sync --frozen --group test
```

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

The standalone Hashmarks executable already includes the local, read-only Model Context Protocol (MCP) runtime; no second package install is required.

For OpenCode, run this from the **target repository**:

```bash
hashmarks install --opencode
opencode mcp list
```

The registration launches the exact installed Hashmarks executable as `hashmarks --workspace . mcp`. You do not need to keep a separate Hashmarks server running.

Claude Code and Pi with `pi-mcp-adapter` can use a project-local `.mcp.json`; Codex uses `.codex/config.toml`. See [`integration/MCP.md`](integration/MCP.md) for the complete read-only tool contract and host configuration. MCP is a repository-intelligence transport; the external agent retains editing, execution, git, reasoning, and orchestration.

To inspect the server manually, run:

```bash
hashmarks --workspace . mcp
```

The process waits for MCP JSON-RPC on stdin. Stop it with `Ctrl+C`; normal host integrations launch it automatically.
