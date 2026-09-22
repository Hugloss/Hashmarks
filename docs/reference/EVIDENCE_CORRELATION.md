# Evidence correlation

**Status: public repository-intelligence contract.**

The governing rule is:

> **Hashmarks establishes repository truth and correlates evidence to it. The consuming agent decides what the evidence means and what action to take.**

Evidence correlation lets a consumer submit bounded, structured observations and ask Hashmarks where those observations correspond to the current repository. Hashmarks preserves the distinction between external claims and canonical repository evidence. Correlation never becomes causation, diagnosis, recommendation, execution, or certification authority.

Interpretation and action remain consumer-owned. Hashmarks reports correspondence, provenance, uncertainty, qualified source equivalence, and repository deltas; it does not decide what those observations mean for the consumer's next step.

## Evidence classes

Hashmarks may correlate several classes of evidence without collapsing their authority.

### Repository-native evidence

Repository-owned bytes and metadata are observed through existing Hashmarks repository authorities. Examples include:

- source files and tests;
- `uv.lock`, `pyproject.toml`, `package-lock.json`, and other admitted manifests or lockfiles;
- build/configuration files;
- repository-owned generated metadata that is explicitly admitted.

These inputs are repository evidence, not external claims.

### Externally derived evidence

A consumer may supply bounded observations produced outside Hashmarks, for example:

- `uv tree` or resolver diagnostics;
- SBOM or vulnerability-scanner findings;
- compiler/linter diagnostics;
- coverage output;
- CI result metadata.

Their fields remain caller claims until correlated with repository evidence.

### Runtime-observed evidence

The same correlation primitive accepts bounded runtime observations such as:

- traceback frames;
- application log anchors;
- Sentry/OpenTelemetry observations;
- profiler samples;
- failing-test locations.

Hashmarks does not ingest or retain the producing log stream. A parser, observability system, or agent extracts structured anchors and supplies only the bounded observations needed for repository correlation.

## Public Python surface

Use `CodeMap.correlate_evidence(...)`:

~~~python
from hashmarks import CodeMap

bundles = [
    {
        "bundle_id": "failure:1",
        "producer": {"kind": "traceback"},
        "completeness": "complete",
        "anchors": [
            {
                "anchor_id": "frame:0",
                "path": "/app/src/worker.py",
                "line": 81,
                "symbol": "process_output_data",
                "metadata": {"handling_ident": "opaque-value"},
            }
        ],
    }
]

with CodeMap(".") as codemap:
    codemap.sync()
    packet = codemap.correlate_evidence(
        bundles,
        path_mappings=[{"external_prefix": "/app", "repository_prefix": ""}],
    )
~~~

Schema: **`hashmarks.evidence-correlation.v1`**.

The result contains the original claims, resolution state, canonical repository evidence from the existing repository-evidence-binding authority, source-equivalence state, completeness, provenance-bearing repository identities, and an overall correlation identity.

## Anchor contract

Each anchor has a caller-controlled opaque `anchor_id` and at least one repository locator:

- `path` — repository-relative, or an absolute external path requiring an explicit mapping;
- `line` — one-based line, valid with an exact `path` or exact `module`;
- `symbol` — a symbol name, qualname, or exact `path::qualname` identifier;
- `module` — an exact dotted module identity resolved only through the existing indexed repository module owner.

Optional `metadata` is opaque JSON-compatible correlation material. Hashmarks does not interpret fields such as `commit`, `revision`, `version`, request IDs, timestamps, topic/partition values, or application correlation IDs unless a separate typed Hashmarks contract explicitly assigns semantics to them.

Bundle and anchor container order is presentation-only. Canonical correlation packets sort bundles by `bundle_id` and anchors within each bundle by `anchor_id`; reordering the same evidence set must not change `correlation_identity`. Any producer ordering that is itself evidence must be represented explicitly in bounded metadata or provenance rather than inferred from list position.

Two qualified identity claims are currently recognized:

- `member_revision` — the exact lowercase SHA-256 member revision used by repository evidence;
- `span_identity` — an exact `sha256:<digest>` line-span identity.

These typed claims may establish source equivalence. Arbitrary similarly named metadata cannot.

## Resolution states

Hashmarks resolves evidence conservatively. Relevant outcomes include:

- `resolved-unique`;
- `resolved-ambiguous`;
- `unresolved`;
- `claim-conflict`.

A path can resolve even when no containing symbol exists. Symbol-only evidence may resolve to multiple candidates. Exact module evidence may resolve only to admitted repository members; an external dependency module therefore remains unresolved unless the repository itself owns that module. Conflicting path/module or line/symbol claims remain conflicts rather than allowing one hint to silently override the other.

Hashmarks does not perform basename guessing, nearest-symbol guessing, hidden prefix stripping, or other fuzzy repairs that would strengthen a weak external claim.

## Explicit path mappings

Absolute runtime/container paths require an explicit mapping:

~~~json
{
  "external_prefix": "/app",
  "repository_prefix": ""
}
~~~

Mappings are bounded declarations. They cannot contain `..`, cannot redefine the repository root, and cannot escape it. Repository-relative claims need no mapping.

Path mapping establishes only a locator correspondence. It does not prove that the observed runtime bytes equal the current repository bytes.

## Source equivalence

Correlation and source equivalence are separate axes.

`source_equivalence.state` is:

- **`proven`** — every supplied qualified source identity comparable with the resolved repository evidence matches;
- **`mismatch`** — at least one comparable qualified identity differs;
- **`unknown`** — the external observation did not provide enough qualified identity evidence.

A current repository observation therefore never implies that an older runtime failure was produced by the same bytes.

## Completeness

Each bundle declares `complete | incomplete | unknown`, an explicit caller-owned `scope` object, and `truncation = complete | truncated | unknown`. Hashmarks preserves those declarations and never infers that a supplied sample contains every runtime or derived observation.

A bundle may declare `completeness=complete` only when it also declares `truncation=complete`. This means only that the caller claims the supplied observations are complete for the declared scope; it does not make the producer authoritative about repository truth. Packet output marks producer/completeness authority as caller-claimed.

Negative external evidence is admissible only within declared scopes when every supplied bundle is complete and explicitly non-truncated. An incomplete, truncated, or unknown bundle may prove that an observation was supplied, but it cannot prove absence. Scope and truncation are part of the evidence-definition identity, so changing a time window, source selection, sampling boundary, or truncation state cannot masquerade as the same observation definition.

Bounds are fail-closed. Oversized bundle counts, anchor counts, path mappings, identifiers, scope metadata, or anchor metadata are rejected rather than silently truncated into stronger evidence.

The correlation request and emitted correlation packet each have one core-owned encoded JSON budget of **1 MiB**. MCP reuses these exact limits and must not add a stricter transport-only evidence budget. The emitted packet includes its active bounds. When independent relationship evidence would exceed the packet budget, Hashmarks fails closed and the consumer must reduce relationship bounds or split the external evidence set.

Repeated observations that resolve to the same repository evidence share one canonical repository-evidence binding. Anchors retain their individual external claims and opaque metadata, but the full canonical repository evidence is emitted once at packet scope and anchors reference it by binding identity. Repeated locator resolution is request-local reused work; it does not create persistent state or a new evidence authority.

## Request-scoped external evidence

External evidence is **request-scoped and not persisted** by the correlation contract. Hashmarks may continue to use its normal disposable repository-intelligence caches, but it does not acquire ownership of production logs, traces, incident history, agent memory, or observability storage.

## Before/after correlation

A consumer may supply a previous correlation packet:

~~~python
after = codemap.correlate_evidence(
    bundles,
    previous_correlation=before,
)
~~~

The result includes a **`hashmarks.evidence-correlation-delta.v1`** packet. Repository change classification is delegated to the existing repository-evidence-binding delta authority.

A supplied previous packet is treated as untrusted serialized evidence. Hashmarks validates its schema and recomputes the packet's `correlation_identity` over the authoritative packet content before it may participate in a delta. Missing, malformed, or content-mismatched identities fail closed; changing nested repository evidence while retaining the old identity is rejected. A derived `delta_from_previous` field is excluded from the base packet identity because it describes comparison history rather than the correlation observation itself.

This supports dependency/toolchain upgrade investigations without adding causal reasoning to Hashmarks. For example:

1. repository state A contains one `uv.lock`;
2. a dependency upgrade changes `uv.lock` and related repository bytes;
3. tests fail and an external runner supplies structured failure/traceback anchors;
4. Hashmarks correlates those anchors to repository truth and reports repository evidence deltas;
5. the consuming agent decides whether the dependency change caused the failure and what repair is appropriate.

Hashmarks may report that the lockfile changed, a traceback resolves to a repository symbol, tests are structurally related, and qualified runtime source identity matches or does not match. It must not conclude that a particular dependency caused the regression merely because those observations correlate.

## MCP

The same primitive is exposed through the read-only `correlate_evidence` MCP tool. MCP is only a bounded transport adapter and reuses the core correlation request/packet budgets; parsing raw Splunk exports, JSONL streams, Sentry payloads, OpenTelemetry streams, or other producer-specific formats remains outside Hashmarks core.

For large logs or exports, the external parser should recover/validate the producer format, preserve parser diagnostics in its own provenance, mark incomplete or recovered samples accordingly, and submit bounded structured anchors. Hashmarks correlates those anchors; it does not become the CSV/log parser or retain the source stream.

For high-volume streams, consumers should aggregate repeated events into **unique repository locators** before correlation when event identity itself is not needed for repository truth. Occurrence counts, time windows, representative event IDs, and similar summary fields remain opaque consumer metadata. Hashmarks may also reuse repeated locators within one request, but its anchor/count bounds remain a repository-intelligence economics guard rather than a log-retention mechanism. Consumers should split independent locator sets only after aggregation; separate correlation packets do not imply that Hashmarks owns cross-chunk incident state.

## Permanent boundary

Evidence correlation must not add:

- log ingestion, monitoring, search, or retention;
- incident/root-cause diagnosis;
- causal conclusions;
- repair recommendations;
- retry/recovery policy;
- test or process execution;
- agent workflow/history;
- certification or result authority.

The permanent split remains:

> **Hashmarks establishes repository truth and correlates evidence to it. The consuming agent decides what the evidence means and what action to take.**


## Temporal and source provenance

A bundle may carry bounded JSON-compatible `provenance` describing external observation facts such as event time, observation time, collection time, source service, or source placement. Hashmarks preserves these values as caller-claimed external provenance; it does not translate them into repository freshness.

Repository freshness remains independently established by repository evidence owners. A recent external timestamp cannot make stale or mismatched repository evidence current, and a repository revision cannot prove when an external event occurred.

Provenance participates in evidence-definition identity. Changing the external observation window/time/source question therefore changes the definition rather than masquerading as repository change.

## Delta comparability

Evidence-correlation delta is authoritative only when `evidence_definition_identity` is preserved. A preserved definition emits `comparability=comparable` and may include repository evidence delta. A changed definition emits `comparability=not-comparable` and suppresses repository evidence delta rather than presenting changes from two different questions as repository change.

This is deliberately non-causal: comparable correspondence changes still do not establish incident identity, culprit, root cause, or repair action.


## Locator portability and source equivalence

External absolute paths are correspondence claims, not repository identities. Explicit path mappings translate container, Linux, Windows, or WSL-style producer paths into repository-relative candidates; the longest matching prefix wins deterministically. Mappings remain confined to repository-relative paths and cannot escape through `..`.

Path translation proves only where to ask the repository owners for evidence. Source equivalence remains `unknown` unless an external anchor supplies an independently comparable typed identity. The admitted typed bases are repository `member_revision` and `span_identity`; exact agreement produces `proven`, any admitted disagreement produces `mismatch`, and absence of a comparable typed claim remains `unknown`.

Opaque commit labels, image digests, package versions, timestamps, and arbitrary metadata never strengthen source equivalence merely because their text resembles a repository identity.


## Compactness, MCP, and producer neutrality

Evidence correlation is already a bounded normalized projection rather than a retained copy of producer payloads. Repeated anchors reuse normalized repository-evidence bindings, and packet/request byte ceilings fail closed instead of silently dropping arrays, strings, provenance, completeness, truncation, or source-equivalence facts. A separate lossy `compact` mode is therefore not admitted: it would create a second representation whose authority would need to remain synchronized with the canonical packet.

The MCP surface exposes the same correlation owner and the same request/packet bounds. Evidence payloads are product inputs and outputs, not operational telemetry. Hashmarks does not emit those payloads as OpenTelemetry/logging data by default, persist them as an event store, or acquire producer query credentials.

Producer kind is descriptive provenance, not a dispatch authority. Normalized pytest, Ruff/type/compiler, coverage, dependency, SBOM/scanner, Splunk/Loki/CloudWatch/Sentry-style, and OpenTelemetry-style observations use the same bounded correlation contract. Producer-specific collection, parsing, retry, retention, diagnosis, and remediation remain outside Hashmarks.


## Cross-bundle correspondence

When independently normalized anchors from different bundles resolve uniquely to the same repository member or symbol, the canonical packet may expose `same-repository-target` correspondence. This is repository correspondence only. It does not establish that the observations belong to the same incident, share a cause, identify a culprit, or imply a repair.

Ambiguous and unresolved anchors do not participate in same-target correspondence. Correspondence is part of canonical packet identity, so post-issuance mutation is detected by the existing correlation packet integrity owner.

Final qualification includes deterministic replay and bounded projection at 1, 10, 100, and the maximum 256 anchors, alongside the existing ambiguity, conflict, truncation, oversized-packet, malicious/opaque metadata, source-equivalence, path-mapping, and tamper regressions.
