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


### Machine-readable readiness

Hosts and external evaluators can ask Hashmarks to qualify its local MCP surface
without changing host configuration:

```bash
hashmarks --workspace . doctor --mcp
```

The normal doctor payload gains an `mcp` object with schema
`hashmarks.mcp-readiness.v1`. It reports the canonical workspace, stdio launch
arguments, read-only status, server version, tool catalog, and MCP/operation contract
identities. The receipt is explicitly `diagnostic-only` and sets
`consumer_verification_required=true`: a benchmark, coding harness, or host must
still prove which executable it launched, that the process is bound to the intended
workspace, and that the host-visible catalog matches the admitted contract.

This is useful for trial-scoped integrations such as agentsCookbook or Harbor because
they can fail before model work when the Hashmarks runtime is not ready, without
requiring a global Codex/OpenCode/Claude registration.

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
- the complete current fourteen-tool read-only catalog and annotations;
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
| `repository_intelligence_query` | expose existing bounded profiles, snapshots, deltas, freshness, verification explanations, and cross-repository evidence |
| `source_observation` | exact revision-bound source occurrences for one member or an explicit bounded member set |
| `evidence_comparison` | caller-supplied structural-locality, binding, or external diagnostic endpoint comparison, preserving native uncertainty and completeness |
| `structural_locality` | static structural locality, exact callers and unresolved candidates for one symbol |
| `repository_evidence` | exact evidence bindings or explicit changed-path coverage, using existing core producers and native qualification |
| `repository_findings` | existing bounded import, cache, and concurrency repository findings |

### Replacing exploratory native search with repository evidence

A typical coding-agent trace runs `rg` across implementation and test folders,
then `sed` over the resulting files and the Makefile. Hashmarks can reduce
**discovery** calls without taking over exact source reads or command execution:

| Unknown to the agent | Existing Hashmarks MCP evidence | Still consumer-owned |
| --- | --- | --- |
| ZIP writer / implementation owner | `task_evidence` behavior localization, candidate vs qualified owner, source range / exact next-read | Inspect and edit the selected body |
| Where `ZipInfo` occurs in known paths | `source_observation` scoped literal occurrences | Broader regex search if literal evidence is insufficient |
| Which tests verify the localized behavior | `task_evidence` selected verification evidence and provenance | Inspect tests, decide and run the test command |
| The already-known `Makefile` recipe | Direct read is appropriate; Hashmarks makes no Make execution claim | Read the relevant lines and execute validation |

Example MCP requests (the returned paths are illustrative, **not** claimed
owner/verification results for this checkout):

```json
{"task":"Locate source ZIP creation and related verification tests","presentation":"compact"}
```

Pass that object to `task_evidence`. After it returns explicit paths, a scoped
literal request to `source_observation` can be:

```json
{
  "paths": ["hashmarks/archive.py", "tests/test_archive.py"],
  "literal": "ZipInfo",
  "result_mode": "scope",
  "presentation": "compact"
}
```

The paths above are examples only. The `scope` mode accepts at most 32 explicit
paths and exactly one literal string per call; it never expands those paths to
another repository scan. It is **case-sensitive literal**, not regex.
`source_observation` also supports `result_mode="literals"` with 1–8
distinct case-sensitive literal strings across up to 32 explicit paths. The MCP `literal` input accepts an array of exact strings only in
`literals` mode, and retains its existing single-string shape in other modes. One canonical stable read per member yields exact
per-literal observed and (when qualified) total counts with independently
qualified scoped absence. It is not regex or a repository-wide search.

`source_observation` returns the native revision-bound source packet alongside
its optional presentation. Compact projection shows occurrence hits before
the member inventory; omitted rows are counted and do not prove absence.
A member-only or stale result cannot silently imply repository-wide completeness.

The `task_evidence` presentation also shows independently referenced owner,
source, verifier, verification-plan and ambiguity-discrimination rows. Owner
candidates and suggested discrimination reads remain producer claims, and the
verification plan is evidence, not a command performed by Hashmarks.
The native packet is preserved, and its freshness, proof-scope completeness and
negative-evidence limits remain authoritative.

Typed finding presentations and conservative assertion semantics are specified in
[Agent-native evidence](../reference/AGENT_NATIVE_EVIDENCE.md). These projections
are not action recommendations and do not promote partial or producer-claimed
observations into repository-wide truth.

Every tool accepts optional `presentation`: `none`, `structured`, `compact`, or
`text`. The default remains `compact` for `repository_intelligence_query` and
`none` for the other tools. `none` preserves the native response. Other formats
use `hashmarks.evidence-presentation-envelope.v1` with the intact native `result`
and a `hashmarks.evidence-presentation.v1` projection. The query tool keeps its
existing query envelope with a sibling presentation. Native response modes and
schemas remain separately advertised; display bounds never establish absence,
completeness, or unique ownership. See the presentation contract above for exact
row caps, source references, qualification metadata, and omission accounting.

The tools are read-only from the repository consumer's perspective. Hashmarks may update its own disposable derived cache while answering them.

### Canonical operation schema authority

Hashmarks resolves semantic response identity before any transport is involved:

```text
(operation, mode)
        ↓
one canonical operation contract
        ↓
exact schema + version
        ↓
core emits it
        ↓
MCP / CLI / API / adapters project it
        ↓
each exposed boundary validates the exact mapping
```

`hashmarks.operation-contract.v1` is the single owner of the exposed operation-to-schema mapping. Core producers consume that mapping; transports do not repeat schema/version strings. A transport may rename a tool for host integration, but it may not mint a different semantic response schema. The `find` CLI and MCP tool therefore both project the same core-owned `hashmarks.find.v2` packet, and dependency observation uses transport-neutral `hashmarks.dependency-codemap.v1`.

Changing an exposed schema/version means changing the operation contract first. The operation-contract identity then changes, the MCP contract incorporates that identity, core output follows the mapping, and boundary validation rejects any producer or adapter that still emits the old schema. CLI handlers for repository context, find, task evidence, change impact, and post-change all validate through the same operation contract before printing; MCP validates independently at its own transport boundary. The warm CodeMap service owns one complete route registry: every route is explicitly classified as either `canonical-semantic` or `internal-service`, so absence from a semantic side table never implicitly means "internal." The semantic routes `task_evidence`, `task_change_impact`, and `task_post_change_delta` are transport aliases for the registered `task_evidence`, `change_impact`, and `post_change` operations: registration is checked before semantic work and the returned packet is checked against the canonical schema before the service publishes it. Internal service routes are forbidden from carrying semantic operation metadata.

Public semantic exposure is admitted through the same owner. MCP tool contracts fail construction when their operation is not registered, every semantic CodeMap CLI projection validates through `_print_operation(...)`, and every semantic warm-service route carries an explicit canonical operation plus response key. Service routes that remain `internal-service` are limited to control/raw transport behavior and may not silently stand in for an unregistered semantic packet. Public transport modules must not mint versioned `hashmarks.*.vN` semantic schemas locally. A future CLI, service, API, or adapter must therefore register the operation contract first and project that registered response rather than introducing a transport-local schema identity.

Registered fixed-mode core operations also self-prove their final packet before any transport receives it. The original repository context, find, task evidence, change impact, evidence correlation, and post-change producers keep their direct proof calls; the broader CodeMap query, ownership, verification, decision, repository-intelligence, refresh, structural-locality, and context producers use the explicit `@operation_response(...)` boundary decorator. The decorator is proof, not a second schema selector: producers obtain schema identity from `operation_schema(...)`, while service, CLI, and MCP retain independent convergence checks over the same canonical mapping. The regression suite also classifies every CodeMap CLI handler as either canonical semantic projection or an explicit non-semantic control/raw path, so using plain printing is no longer an implicit escape from operation admission.

### Canonical MCP contract identity

Hashmarks owns one transport-neutral `hashmarks.mcp-contract.v1` manifest. The manifest binds the Hashmarks server name and installed version, the server description and routing instructions, canonical tool order and descriptions, the native MCP input/output schemas, read-only annotations, and each tool's Hashmarks response-schema set. A canonical JSON SHA-256 becomes the `contract_identity`.

The server registration consumes the same canonical tool objects that qualification uses. Each native tool resolves one `McpToolContract`; that object supplies the published tool name and description and owns response validation through its registered operation. The server therefore does not independently re-declare a tool name for registration and then re-type it again for response proof. Host gates likewise do not maintain independent copies of tool descriptions or response-schema strings. OpenCode, Codex, Claude Code, Pi, and the ChatGPT Secure MCP Tunnel handoff qualify the exact installed wheel and record a compact summary containing the same contract schema, identity, server version, and canonical tool names. Host-specific spellings such as `hashmarks_find` or `mcp__hashmarks__find` are transport aliases only and never become separate semantic authorities.

Input or output schema drift, tool-order drift, description drift, annotation drift, routing-instruction drift, or installed-version drift therefore changes or rejects the canonical contract before host behavior is accepted. Successful tool calls are also checked at runtime against the canonical semantic response schema before the MCP boundary publishes them. Fixed-response tools have one default schema; alternate-mode tools derive both the native MCP `result_mode` enum and its default value from the canonical operation contract, then bind each admitted mode to its exact response schema. MCP qualification also checks the observed native input schema against that same mode set and default, including that the defaulted selector remains omittable; schema drift is rejected instead of merely producing a new contract hash. Core dispatch, the MCP surface, native MCP registration, and qualification therefore cannot independently re-type `observation` as the default. An impossible mode is not represented by the wire schema and an `explain` packet cannot satisfy a `compare` call merely because both schemas are known to the same tool. Response-schema drift is an implementation contract violation, not a caller error.

The canonical `post_change` response is `hashmarks.task-post-change-delta.v2`, matching the core post-change projection. This closes the earlier declaration/runtime split where the MCP contract still named the retired v1 response.

This remains an observation/qualification contract: it does not add another MCP tool, workflow state, host router, or execution authority.

### Machine-classifiable MCP failures

Caller-visible Hashmarks tool failures use one compact `hashmarks.mcp-error.v1` JSON object inside the normal MCP tool-error message. The stable `reason` values are `invalid-request`, `stale-or-foreign-evidence`, `continuity-mismatch`, `unsupported-semantic`, and `transient-race-exhausted`. The payload also keeps the human-readable `message` and states `recovery_authority: consumer-owned`.

The classification is intentionally descriptive rather than prescriptive. Hashmarks labels what failed at its repository-intelligence boundary; it does not decide whether a host should retry, discard evidence, request new evidence, choose another semantic, or abort. In particular, bounded internal retry of known repository races remains an implementation detail. Only when that bounded window is exhausted does the caller receive `transient-race-exhausted`; the caller still owns the next action.

Repository or generation binding mismatches are classified as `stale-or-foreign-evidence`. A previous packet whose continuity identity no longer matches the requested continuation is `continuity-mismatch`. Unsupported evidence semantics are `unsupported-semantic`. Shape, bounds, type, result-mode, and other request-validation failures remain `invalid-request`. These reason codes are part of the canonical MCP contract identity so hosts cannot qualify against an independently drifting error taxonomy.

Tool selection is intentionally phase-specific rather than interchangeable: use `repository_context` for broad orientation, `find` when an exact path/symbol/name is already known, `task_evidence` when a behavior/task needs semantic localization or ownership evidence, and `change_impact` after explicit changed paths exist. `task_evidence` is deliberately stronger than raw text search for that semantic case: one bounded packet separates supporting retrieval from ownership authority, preserves ambiguity, carries source evidence or an exact next-read, selects verification evidence/plan, and reports freshness. These descriptions are exposed through the native MCP catalog so hosts can choose the existing semantic owner without a Hashmarks-owned planner or workflow layer.

`find` uses the core-owned `hashmarks.find.v2` packet for every transport. CLI and MCP consume the same packet rather than minting transport-specific schemas. It does not let an empty or single bounded result silently become absence or uniqueness authority; the core packet carries bound reasons together with CodeMap generation/freshness and observed exact-match cardinality. Exact path claims are scoped to the admitted visible repository path index; exact identifier claims are scoped to the indexed visible symbol surface. Only a current, unbounded exact-query cut can make `negative_evidence` or `uniqueness_evidence` admissible. Natural-language/conceptual retrieval remains bounded retrieval only and cannot prove absence.

The MCP initialization also exposes concise server instructions for hosts that support them. For repository-localization work where the exact owner/path/symbol is not yet known, those instructions tell the coding agent to prefer one bounded `task_evidence` call before broad grep/glob or exploratory reads, then use native reads against the returned evidence. The opposite case is equally important: when a unique exact path is already known and the task is simply to inspect that file, native read is the better tool and Hashmarks should stay out of the way. This is routing guidance rather than workflow ownership: Hashmarks should win semantic reduction, not every repository access, and it does not replace editing, shell, test, or git tools.

`task_evidence` uses `hashmarks.task-evidence.v5`. Retrieval remains relevance evidence only and carries no ownership authority. v3 introduced compact retrieval locators; v4 introduced a non-authoritative `ownership.next_read` for a unique, completely observed task-local structural discriminator. v5 leaves that field empty when no such discriminator exists. A named class scopes a method request but does not itself resolve the method owner; matching indexed members remain retrieval candidates until exact method identity proves ownership. `retrieval.bounds` now reports `canonical_completeness`, `canonical_truncation`, and `bound_reasons` for the executed bounded canonical query. These fields do not prove repository-wide absence. `canonical_omitted_results` still counts presentation displacement separately, and natural-language supplements remain non-authoritative.

For natural-language localization, the bounded retrieval list can include up to two current, visible symbol supplements after canonical hits. Supplements use the same compact locator shape and carry `supplement: bounded-natural-language`; internal supplement scores remain private ranking evidence. The result limit remains strict, and `canonical_omitted_results` counts canonical hits displaced by supplements. These rows do not change ownership or verification selection.

`correlate_evidence` accepts structured evidence bundles, not raw log streams. Producer-specific parsing/ingestion remains outside the MCP adapter. The tool preserves external claims, ambiguity, completeness, source equivalence, and repository deltas; interpretation and action remain consumer-owned. See [Evidence correlation](../reference/EVIDENCE_CORRELATION.md).

### Explain and compare modes

The catalog stays small: explainability and endpoint comparison are modes on existing tools, not extra MCP tools.

`dependency_codemap` accepts `result_mode="observation" | "explain" | "compare"`:

- `observation` is the default and preserves the existing `hashmarks.dependency-codemap.v1` response; bounded dependency queries are available only in this mode;
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

`hashmarks.mcp_launch` is the single semantic owner of the stdio launch tuple used by these registrations and by installed-host qualification. The checked-in `opencode.json`, `.mcp.json`, and `.codex/config.toml` files only project that command into each host's native configuration syntax; host-status tests validate those projections against the canonical source command. Real-host gates and the ChatGPT Secure MCP Tunnel handoff use the same installed-command builder with their resolved executable and workspace paths.

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

The host-gate scripts own their normal host executable, Python selector, receipt path, and safe-mode defaults. The Make targets are thin aliases: they use those script defaults unless you explicitly provide a Make override such as `OPENCODE_MODEL`, `CLAUDE_MODEL`, `CODEX_MODEL`, a host executable override, a Python selector override, or a receipt override. Pi deliberately keeps model selection in Pi's native configuration, so `mcp-pi-check` has no Hashmarks model override.


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
make mcp-pi-check
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

### Caller-supplied reference and call-hierarchy evidence

The existing `structural_locality` relationship result mode accepts
`textDocument/references` and the three LSP call-hierarchy methods through
the same request-local `supplied_observations` contract. This extension
requires no LSP process, additional MCP tool, new persisted index, or default
catalog change. Consult
[qualified relationship observations](../reference/STRUCTURAL_LOCALITY.md)
for the captured protocol shapes and claim/completeness restrictions.

Pure native-to-presentation conformance and portable evidence binding
reacquisition are public Python helpers over existing native packets, not
new MCP operations. Host-model delivery receipts remain outside the server.
