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
        path_mappings=[
            {"external_prefix": "/app", "repository_prefix": ""}
        ],
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

Each bundle declares `complete | incomplete | unknown`. Hashmarks preserves that declaration and never infers that a supplied sample contains every runtime or derived observation.

Bounds are fail-closed. Oversized bundle counts, anchor counts, path mappings, identifiers, or metadata are rejected rather than silently truncated into stronger evidence.

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
