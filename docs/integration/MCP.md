# Hashmarks MCP server for coding agents

Hashmarks exposes an optional **local, read-only stdio Model Context Protocol (MCP) server** for coding agents and developer tools, including Claude Code, Codex, OpenCode, and Pi through an MCP adapter. It gives MCP clients bounded codebase search, repository context, ownership and verification evidence, and change impact analysis from the same local repository-intelligence layer. MCP is only a transport adapter over existing Hashmarks repository intelligence; it does not add planning, editing, shell execution, git ownership, retries, model routing, or workflow orchestration.

## Install

For end users on Linux x86_64 (including WSL2), install the self-contained CLI + MCP runtime:

```bash
curl -fsSL https://github.com/Hugloss/Hashmarks/releases/latest/download/install.sh | sh
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

After registration, Hashmarks asks OpenCode for its **effective** configuration in the current repository. The result reports `effective_registration` as:

- `active` when OpenCode resolves the installed Hashmarks executable with the expected workspace-bound MCP command;
- `shadowed` when a higher-precedence project configuration resolves a different `mcp.hashmarks` command;
- `unverified` when OpenCode accepted registration but its effective configuration could not be inspected.

A `shadowed` result is diagnostic, not a request for Hashmarks to rewrite the project. Hashmarks never becomes an OpenCode configuration manager: the project owns its local OpenCode file, OpenCode owns precedence and effective configuration, and Hashmarks only reports that the installed registration is not the active command.

## Run

From a repository:

```bash
hashmarks --workspace . mcp
```

One server process binds one canonical workspace. Start another process for another repository. The first repository-intelligence tool call may build or reconcile the CodeMap; MCP discovery itself does not pre-index the repository.

### ChatGPT through Secure MCP Tunnel

ChatGPT does not connect directly to a local stdio MCP process. OpenAI Secure MCP Tunnel can own the remote transport while launching Hashmarks through its existing local stdio command, so Hashmarks does **not** need a second HTTP server or public ingress.

First qualify the exact local executable/workspace handoff without creating a tunnel or storing credentials:

```bash
make init
make mcp-chatgpt-handoff \
  CHATGPT_MCP_WORKSPACE=/absolute/path/to/repository
```

For a standalone Hashmarks binary rather than this source checkout, override the executable and disable source-root binding explicitly:

```bash
make mcp-chatgpt-handoff \
  CHATGPT_MCP_HASHMARKS=/absolute/path/to/hashmarks \
  CHATGPT_MCP_WORKSPACE=/absolute/path/to/repository \
  CHATGPT_MCP_SOURCE_ROOT=
```

The default receipt is `dist/chatgpt-secure-mcp-tunnel-handoff.json`. It binds:

- the canonical workspace;
- the exact Hashmarks executable path, SHA-256, and version;
- for source-managed handoffs, the actual imported Hashmarks source root and canonical repository content identity;
- the exact stdio `mcp_command_argv` and shell-safe `mcp_command`;
- the negotiated MCP protocol/server identity/version and server instructions, with CLI and MCP versions required to agree;
- the exact eight-tool read-only catalog and annotations;
- explicit authority that Secure MCP Tunnel, ChatGPT configuration, and credentials remain external.

To hand that already-qualified stdio command to OpenAI's tunnel client, create/select a tunnel in the OpenAI Platform first, then keep the runtime API key outside Hashmarks and run the OpenAI-owned client. For example:

```bash
mcp_command="$(
  uv run --frozen --no-sync python -c \
    'import json; print(json.load(open("dist/chatgpt-secure-mcp-tunnel-handoff.json"))["mcp_command"])'
)"

export CONTROL_PLANE_API_KEY='...'

tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile hashmarks-chatgpt \
  --tunnel-id '<tunnel_id>' \
  --mcp-command "$mcp_command"

tunnel-client doctor --profile hashmarks-chatgpt --explain
tunnel-client run --profile hashmarks-chatgpt
```

Use the latest OpenAI `tunnel-client` release and the current Secure MCP Tunnel documentation rather than pinning tunnel-client behavior in Hashmarks. Hashmarks never receives or stores the control-plane API key or tunnel ID.

When the target ChatGPT workspace has developer-mode custom-app access, create the app using **Tunnel** and select the OpenAI-managed tunnel. Review the discovered Hashmarks tools before model calls. The tunnel/app/workspace permissions remain OpenAI/organization authority; a successful local Hashmarks handoff does not imply that ChatGPT access has been granted.

For routing benchmarking, do not count a missing Hashmarks app as a tool-selection loss. First capture the host-visible catalog and qualify it with the agentsCookbook host-neutral gate:

```bash
../agentsCookbook/benchmark tool-routing-catalog \
  --catalog host-tools.json \
  --subject hashmarks
```

Only a `READY` catalog can support a routing decision. For unknown-path semantic localization, healthy routing chooses `task_evidence` before exploratory native search/read; for an exact known-path inspection, healthy routing chooses native read directly. `ENVIRONMENT_BLOCKED: required-subject-tool-missing` means the host integration is unavailable, not that Hashmarks lost the routing decision.

## Tool surface

Hashmarks intentionally exposes a small read-only repository-intelligence tool catalog:

| Tool | Purpose |
| --- | --- |
| `repository_context` | compact orientation, generation/freshness, languages, areas, projects |
| `find` | bounded exact path/symbol discovery with freshness, completeness, and negative/uniqueness admissibility |
| `task_evidence` | role-separated retrieval, explicit-target, ownership, verification, freshness, ambiguity, and next-read repository evidence |
| `change_impact` | bounded structural impact for caller-reported changed paths |
| `correlate_evidence` | correlate bounded external/derived observations to canonical repository evidence without inferring causation |
| `dependency_codemap` | qualify dependency observations, explain their authority, compare explicit endpoints, or run bounded factual queries |
| `repository_declarations` | bind declarations to exact repository evidence and return the qualified observation or typed explanation |
| `post_change` | refresh changed paths against a previous `task_evidence` packet and return evidence deltas |

The tools are read-only from the repository consumer's perspective. Hashmarks may update its own disposable derived cache while answering them.

### Canonical MCP contract identity

Hashmarks owns one transport-neutral `hashmarks.mcp-contract.v1` manifest. The manifest binds the Hashmarks server name and installed version, the server description and routing instructions, canonical tool order and descriptions, the native MCP input/output schemas, read-only annotations, and each tool's Hashmarks response-schema set. A canonical JSON SHA-256 becomes the `contract_identity`.

The server registration consumes the same contract constants that qualification uses; host gates do not maintain independent copies of tool descriptions or response-schema strings. OpenCode, Codex, Claude Code, Pi, and the ChatGPT Secure MCP Tunnel handoff qualify the exact installed wheel and record a compact summary containing the same contract schema, identity, server version, and canonical tool names. Host-specific spellings such as `hashmarks_find` or `mcp__hashmarks__find` are transport aliases only and never become separate semantic authorities.

Input or output schema drift, tool-order drift, description drift, annotation drift, routing-instruction drift, or installed-version drift therefore changes or rejects the canonical contract before host behavior is accepted. This remains an observation/qualification contract: it does not add another MCP tool, workflow state, host router, or execution authority.

### Machine-classifiable MCP failures

Caller-visible Hashmarks tool failures use one compact `hashmarks.mcp-error.v1` JSON object inside the normal MCP tool-error message. The stable `reason` values are `invalid-request`, `stale-or-foreign-evidence`, `continuity-mismatch`, `unsupported-semantic`, and `transient-race-exhausted`. The payload also keeps the human-readable `message` and states `recovery_authority: consumer-owned`.

The classification is intentionally descriptive rather than prescriptive. Hashmarks labels what failed at its repository-intelligence boundary; it does not decide whether a host should retry, discard evidence, request new evidence, choose another semantic, or abort. In particular, bounded internal retry of known repository races remains an implementation detail. Only when that bounded window is exhausted does the caller receive `transient-race-exhausted`; the caller still owns the next action.

Repository or generation binding mismatches are classified as `stale-or-foreign-evidence`. A previous packet whose continuity identity no longer matches the requested continuation is `continuity-mismatch`. Unsupported evidence semantics are `unsupported-semantic`. Shape, bounds, type, result-mode, and other request-validation failures remain `invalid-request`. These reason codes are part of the canonical MCP contract identity so hosts cannot qualify against an independently drifting error taxonomy.

Tool selection is intentionally phase-specific rather than interchangeable: use `repository_context` for broad orientation, `find` when an exact path/symbol/name is already known, `task_evidence` when a behavior/task needs semantic localization or ownership evidence, and `change_impact` after explicit changed paths exist. `task_evidence` is deliberately stronger than raw text search for that semantic case: one bounded packet separates supporting retrieval from ownership authority, preserves ambiguity, carries source evidence or an exact next-read, selects verification evidence/plan, and reports freshness. These descriptions are exposed through the native MCP catalog so hosts can choose the existing semantic owner without a Hashmarks-owned planner or workflow layer.

`find` uses `hashmarks.mcp-find.v1` and does not let an empty or single bounded result silently become absence or uniqueness authority. It projects the core find engine's bound reasons together with CodeMap generation/freshness and reports observed exact-match cardinality. Exact path claims are scoped to the admitted visible repository path index; exact identifier claims are scoped to the indexed visible symbol surface. Only a current, unbounded exact-query cut can make `negative_evidence` or `uniqueness_evidence` admissible. Natural-language/conceptual retrieval remains bounded retrieval only and cannot prove absence.

The MCP initialization also exposes concise server instructions for hosts that support them. For repository-localization work where the exact owner/path/symbol is not yet known, those instructions tell the coding agent to prefer one bounded `task_evidence` call before broad grep/glob or exploratory reads, then use native reads against the returned evidence. The opposite case is equally important: when a unique exact path is already known and the task is simply to inspect that file, native read is the better tool and Hashmarks should stay out of the way. This is routing guidance rather than workflow ownership: Hashmarks should win semantic reduction, not every repository access, and it does not replace editing, shell, test, or git tools.

`task_evidence` uses `hashmarks.task-evidence.v2`. Retrieval order is relevance evidence only and carries no ownership authority. Ownership resolution, ambiguity, verification, and freshness are separate fields; current freshness never implies a uniquely resolved owner. The consumer remains responsible for deciding whether and how to act on the evidence.

For natural-language localization, the bounded retrieval list can include up to two current, visible symbol supplements after canonical hits. Each supplement has the normal search-hit shape plus `retrieval_supplement` and `score_basis`; its match-count score is not comparable with canonical relevance scores. The result limit remains strict, and `canonical_omitted_results` counts canonical hits displaced by supplements. These rows do not change ownership or verification selection.

`correlate_evidence` accepts structured evidence bundles, not raw log streams. Producer-specific parsing/ingestion remains outside the MCP adapter. The tool preserves external claims, ambiguity, completeness, source equivalence, and repository deltas; interpretation and action remain consumer-owned. See [Evidence correlation](../reference/EVIDENCE_CORRELATION.md).

### Explain and compare modes

The catalog stays small: explainability and endpoint comparison are modes on existing tools, not extra MCP tools.

`dependency_codemap` accepts `result_mode="observation" | "explain" | "compare"`:

- `observation` is the default and preserves the existing `hashmarks.mcp-dependency-codemap.v1` response; bounded dependency queries are available only in this mode;
- `explain` returns the existing typed `hashmarks.dependency-resolution-explain.v1` projection;
- `compare` requires a bounded caller-supplied qualified `previous_observation` and returns `hashmarks.dependency-resolution-delta.v3`.

`repository_declarations` accepts `result_mode="observation" | "explain"`. Observation is the unchanged default response; explain returns `hashmarks.repository-declaration-explain.v1`. Existing `previous_observation` declaration delta behavior remains observation-mode only.

The MCP server never stores a "previous" dependency or declaration observation on behalf of the caller. Compare/explain modes are request-scoped projections over explicit authority supplied or produced in that request. They do not scan Git history, add a session-history cache, or create a new freshness owner.

`repository_declarations` accepts producer-normalized declaration groups. Semantic extraction, grouping, normalized values, correspondence, and coverage remain provider claims; Hashmarks binds them to current exact repository evidence and reports canonical equality/difference, ambiguity, coverage-qualified absence, identity, freshness, and factual deltas without selecting a winning declaration. See [Repository declarations](../reference/REPOSITORY_DECLARATIONS.md).

Python integrations may use the public declaration-provider SPI and `CodeMap.discover_repository_declarations(...)` before transport. MCP intentionally does not dynamically import or execute those Python providers; external adapters pass their normalized groups into `repository_declarations`. A provider detection miss or provider execution failure therefore cannot be hidden inside MCP as declaration absence.

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

`opencode.json` contains the project-local `mcp.hashmarks` registration for **Hashmarks source development**. It intentionally launches the locked checkout through `uv run --frozen --no-sync`; it is not the end-user standalone-binary registration.

Because OpenCode resolves project configuration together with user/global configuration, this development entry can shadow a globally registered standalone Hashmarks executable when OpenCode is started from the Hashmarks checkout. `hashmarks install --opencode` detects and reports that effective shadowing but does not mutate `opencode.json`.

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

### Voluntary OpenCode selection dogfood

The same host qualification script also offers a non-gating diagnostic with six neutral repository tasks. Its disposable commerce repository includes several similarly named implementations and an import-backed checkout owner. It leaves OpenCode's native tools available, asks for no named tool, and records the ordered `tool_use` stream, Hashmarks response schemas, host-reported token data when present, and duration. Each trial uses a fresh disposable repository and session. Run the same runner, model, and repeat count against separately installed baseline and candidate Hashmarks executables:

```bash
uv sync --frozen --extra mcp --group test
python scripts/host_qualification/opencode_mcp_host_gate.py --selection-diagnostic --model provider/model --repeats 3 --hashmarks-executable /absolute/baseline/bin/hashmarks --receipt dist/opencode-selection-baseline.json
python scripts/host_qualification/opencode_mcp_host_gate.py --selection-diagnostic --model provider/model --repeats 3 --hashmarks-executable /absolute/candidate/bin/hashmarks --receipt dist/opencode-selection-candidate.json
```

The receipt binds the prompt manifest, fixture content, runner, executable, installed MCP source, and captured catalog by SHA-256. The catalog comes from an actual OpenCode model request sent to a local non-reasoning endpoint. `--catalog-only` captures that wire catalog without an external model call. The catalog probe does not measure model choice; only completed real-model trials can do that. Provider authentication or connection failure is `ENVIRONMENT_BLOCKED`; timeouts are `INCOMPLETE`, and tool or host failures are `FAIL`. None counts as a selection outcome. Review the JSONL events and source-backed answers before judging use or cost; path mentions and invocation counts alone are not correctness measures. This diagnostic is not a release gate.

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
