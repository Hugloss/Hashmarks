# Evidence Correlation Hardening and Observability Interop Plan

Status: development continuation plan  
Authority base: Hashmarks `main` at `2fc360347de081bc1eefd4745798adb4d4e4b01d`  
Scope: harden the public `hashmarks.evidence-correlation.v1` contract introduced by PR #26 without moving log ingestion, diagnosis, execution, recovery, or agent workflow authority into Hashmarks.

## Governing split

Hashmarks establishes repository truth and correlates bounded evidence to it. The consuming agent decides what the evidence means and what action to take.

Observability systems and their MCP servers may fetch or query runtime evidence. Hashmarks must not become another observability backend, log-search engine, root-cause engine, incident manager, or execution motor.

The target architecture is:

```text
Grafana / Loki / Datadog / Sentry / CloudWatch / Splunk / Azure Monitor /
Honeycomb / OTel collector / test runner / compiler / scanner
        |
        | bounded structured external evidence
        v
Hashmarks evidence correlation
        |
        | repository correspondence + provenance + uncertainty + deltas
        v
consumer / coding agent
        |
        | interpretation, diagnosis, edit, execution, certification
        v
external consumer authority
```

## External patterns reviewed

The plan intentionally borrows implementation lessons from observability MCPs without borrowing their product authority.

- Grafana MCP: explicit log-result limits, limit+1 truncation detection, compact output, time-range and bytes-scanned query guardrails, enforced stream scopes, and explicit caution around PII in tool arguments/results.
  - https://github.com/grafana/mcp-grafana
- Sentry MCP: explicit security boundaries, skill/resource scoping, prompt-injection awareness, and treatment of event/runtime data as untrusted external input.
  - https://github.com/getsentry/sentry-mcp
- Datadog MCP: logs/metrics/traces/incidents remain source-system responsibilities exposed to agents.
  - https://github.com/datadog-labs/mcp-server
- Azure MCP / Azure Monitor: query time ranges, resource/workspace scope, result limits, and backend query limits remain explicit.
  - https://github.com/Azure/azure-mcp
- Honeycomb MCP: environment, dataset, and time range are first-class query scope.
  - https://github.com/honeycombio/honeycomb-mcp
- MCP 2026-07-28 release candidate: MCP Logging is deprecated in favor of stderr for stdio and OpenTelemetry for structured server observability.
  - https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/

These projects are evidence-source or observability-query systems. Hashmarks remains a deterministic repository observer and correlation layer.

## Permanent non-goals

Do not add any of the following to Hashmarks core:

- raw log ingestion, retention, tailing, indexing, or search;
- Splunk SPL, Loki LogQL, CloudWatch Logs Insights, DQL, NRQL, KQL, Honeycomb query execution, or source credentials;
- incident diagnosis, root-cause conclusions, repair recommendations, retry/recovery policy, or action selection;
- package installation, shell/process execution, network fetches, or secret access driven by external evidence;
- persistent incident history or agent memory;
- producer-specific parsing that is better owned by the evidence source/adapter;
- a second repository freshness, identity, completeness, relationship, or delta authority;
- a heuristic prompt-injection classifier that claims external text is safe.

## Mandatory cross-phase invariants

Every phase below must preserve these rules.

### I1. External text is data, never instruction authority

Runtime messages, exception text, breadcrumbs, annotations, compiler messages, scanner descriptions, CI output, and producer metadata may be attacker-controlled. Hashmarks may preserve and identify them, but it must never interpret instruction-looking text as commands, policies, fixes, or repository authority.

### I2. Trust, completeness, cost, and output size are separate axes

Do not collapse these facts:

- whether evidence content is trusted or externally controlled;
- whether the producer claims the observation scope is complete;
- whether Hashmarks repository observation is complete;
- whether candidate/relationship bounds were exhausted;
- how expensive the producer query was;
- how much result data Hashmarks returns.

A small response can come from an expensive query. A complete producer sample can still have incomplete repository correlation. A large response can still be fully bounded.

### I3. No hidden truncation

Whenever Hashmarks applies a bound that can omit otherwise valid results, the packet must say so. Prefer limit+1 observation where practical so the producer can distinguish "exactly N" from "at least N+1" without silently truncating.

### I4. No negative claim from incomplete scope

A bounded or partial sample may prove observed presence, but it cannot prove absence outside its declared and completely observed scope.

### I5. Definition/configuration change is not repository change

Changed path mappings, evidence scope, time window, source selection, relationship limits, projection mode, or output budget must never masquerade as code/repository change.

### I6. External provenance does not become repository truth

A field named `commit`, `version`, `image`, `revision`, `environment`, or similar remains a caller claim unless an existing Hashmarks authority can independently compare it.

### I7. Stateless replay

External evidence remains request-scoped. Previous correlation packets are supplied explicitly and validated. No hidden incident/session history may affect the answer.

### I8. Output must remain bounded and inspectably incomplete

Compact/budgeted output may omit opaque payload details, but authority-relevant identities, truncation state, provenance, and completeness must remain visible.

### I9. Operational telemetry is not product evidence

If the MCP server itself emits OpenTelemetry, that telemetry describes Hashmarks server operation. It does not become repository evidence or external correlation evidence unless explicitly reintroduced as an ordinary external claim.

---

# Ordered implementation phases

## EC-00 — Public Contract and Schema Evolution Gate — P0

Purpose: freeze what PR #26 published before hardening semantics underneath consumers.

Work:

- capture canonical v1 conformance fixtures for:
  - path-only anchor;
  - line anchor;
  - qualified symbol anchor;
  - ambiguous symbol anchor;
  - conflicting line+symbol anchor;
  - explicit path mapping;
  - source equivalence `proven | mismatch | unknown`;
  - complete/incomplete/unknown bundle declarations;
  - previous-correlation delta;
- document which fields are stable v1 contract and which are implementation detail;
- define the compatibility rule:
  - additive fields that do not strengthen old claims may remain v1;
  - changed meaning of `complete`, `proven`, resolution, or delta comparability requires either an explicit compatibility field or schema evolution;
- add serialization round-trip/conformance tests.

Exit:

- exact v1 fixtures are committed;
- hardening work cannot silently reinterpret an old packet.

## EC-01 — Correlation Packet Integrity Closure — P0

Purpose: make previous/inbound correlation packets as fail-closed as other Hashmarks public evidence.

Work:

- replace schema-only previous-packet validation with full validation;
- recompute and verify `correlation_identity`;
- reconstruct the evidence definition from public fields and verify `evidence_definition_identity`;
- validate:
  - allowed top-level fields;
  - authority constants;
  - bundle and anchor identity uniqueness;
  - path mappings;
  - correlation resolution vocabulary;
  - candidate completeness;
  - source-equivalence state/basis shape;
  - completeness shape;
  - nested repository-evidence packet validity/identity;
- reject malformed or contradictory packets before repository delta comparison;
- add tamper tests for one-field modifications to:
  - claims;
  - producer metadata;
  - completeness;
  - path mappings;
  - candidate state;
  - repository evidence;
  - source equivalence;
  - evidence-definition identity;
  - correlation identity.

Exit:

- no tampered `previous_correlation` can produce an authoritative delta.

## EC-02 — Untrusted External Evidence Boundary — P0

Purpose: make the runtime-evidence trust boundary machine-visible without moving security policy into Hashmarks.

Borrow:

- Sentry's explicit treatment of runtime/event data as untrusted external input;
- Grafana's recognition that observability text can carry prompt-injection payloads.

Work:

- add producer-neutral trust provenance to external evidence, for example:
  - `origin_authority = caller-claim`;
  - `content_trust = untrusted-external-data`;
- preserve opaque external text exactly enough for evidence identity while ensuring rendered/MCP output keeps it structurally inside data fields;
- keep server-generated correlation metadata distinct from external payload;
- do not emit natural-language remediation/action guidance from external evidence;
- document that redaction/sanitization is producer/adapter responsibility;
- allow a producer to declare that content was redacted and bind that declaration into the evidence definition;
- add regressions where external text contains:
  - fake system/developer instructions;
  - shell/package-install commands;
  - URLs;
  - markdown code blocks;
  - "Resolution:"/"Fix:" text;
  and prove correlation output treats all of it only as opaque evidence.

Exit:

- external evidence cannot acquire instruction or action authority through formatting/content.

## EC-03 — Scoped Completeness, Truncation, and Selection Provenance — P0

Purpose: make `complete` meaningful only relative to a declared bounded observation scope.

Borrow:

- Grafana limit+1 truncation detection;
- Azure/Honeycomb explicit source/time/query scope.

Add a producer-neutral observation-scope envelope capable of representing:

- source kind/provider;
- environment/account/region/cluster/dataset/log-group/service identifiers as bounded opaque scope;
- time window;
- source-side selection/filter identity or opaque query identity;
- requested result bound;
- returned item count;
- source-reported pagination/truncation/partial-result state;
- producer-declared completeness.

Rules:

- `complete` means complete only for the exact declared external scope;
- empty evidence is useful negative evidence only when a non-empty explicit scope is declared complete;
- candidate truncation and repository relationship-bound exhaustion remain independent;
- when Hashmarks itself applies a candidate/result bound, observe one additional candidate where practical and emit:
  - exact complete;
  - bounded/more-exists;
  rather than guessing;
- do not infer producer completeness from returned count alone.

Exit:

- no plausible-looking bounded sample can be mistaken for global absence evidence.

## EC-04 — Temporal and Source Provenance — P0/P1

Purpose: preserve event/query timing and source placement without conflating them with repository freshness.

Add typed optional fields for:

- event time;
- producer observation/query start and end;
- observation collection time;
- timezone/offset;
- source scope identifiers;
- producer identity/version where useful.

Rules:

- external event/observation time is provenance, not Hashmarks freshness;
- current repository observation never proves historical runtime bytes were the same;
- timestamps must be normalized/validated but remain caller claims unless independently proven;
- source scope changes are definition changes.

Exit:

- two observations from different time windows or environments cannot be accidentally treated as directly comparable.

## EC-05 — Correlation Delta Authority Closure — P0/P1

Purpose: make deltas describe Hashmarks-owned correspondence changes, not only underlying repository-binding changes.

Add bounded per-anchor change facts for:

- `unresolved -> resolved-unique`;
- unique <-> ambiguous;
- repository path/symbol correspondence change;
- candidate set/completeness change;
- source equivalence `unknown | proven | mismatch` transitions;
- external-scope/completeness changes;
- repository-evidence changes.

Add explicit comparability:

- `comparable`;
- `definition-changed`;
- `scope-changed`;
- `not-comparable` where required.

Rules:

- changed evidence definition must never silently yield a like-for-like correspondence delta;
- causation remains `not-inferred`;
- interpretation remains consumer-owned.

Exit:

- consumers can distinguish "repository changed" from "we asked a different question."

## EC-06 — Locator, Range, and Path Portability Hardening — P1

Purpose: support real diagnostics without creating a second range/path authority.

Work:

- support bounded line ranges only through existing repository-evidence binding range semantics;
- test:
  - Linux absolute paths;
  - container-prefix mappings;
  - Windows drive paths and case/normalization behavior;
  - WSL-style source/runtime mappings;
  - UNC-like inputs where supported/rejected;
  - overlapping path mappings;
  - longest-prefix selection;
  - repository-root mapping;
  - `..` and escape attempts;
  - symlink/confinement interaction;
- retain claim-conflict semantics when line/range/symbol disagree.

Exit:

- common runtime/build path shapes map deterministically or fail explicitly.

## EC-07 — Qualified Source Equivalence Expansion — P1

Purpose: strengthen byte/source comparison only where Hashmarks already has independent identity authority.

Work:

- retain current qualified `member_revision` and `span_identity`;
- investigate whether a repository-level identity can be admitted without trusting arbitrary commit-looking metadata;
- add producer/source identity only when there is a canonical comparison owner;
- preserve mismatch rather than repairing/guessing older runtime source identity.

Do not:

- trust arbitrary git SHA, image tag, package version, branch, build ID, or deployment label by naming convention.

Exit:

- source equivalence never becomes stronger than independently comparable identity evidence.

## EC-08 — Bounded Output, Compact Projection, and Sensitive Metadata Controls — P1

Purpose: keep the public/MCP surface economical and safe at maximum accepted input bounds.

Borrow:

- Grafana compact log output;
- explicit separation of bytes scanned from bytes returned;
- avoidance of sensitive/high-cardinality values in operational telemetry.

Work:

- define response budget/projection modes;
- preserve authority-relevant fields under compact output:
  - identities;
  - resolution;
  - provenance;
  - completeness/truncation;
  - source equivalence;
  - repository references;
- permit omission of bulky opaque metadata only with an explicit omission state;
- never silently cut arrays/strings;
- add maximum-size tests for:
  - 256 anchors;
  - ambiguous candidate sets;
  - relationships enabled;
  - metadata at accepted bounds;
- document that Hashmarks is not a PII detector/redactor; producer-side redaction is preferred and its declaration can be preserved.

Exit:

- worst-case accepted requests have predictable bounded output or explicit refusal/compact behavior.

## EC-09 — MCP and OpenTelemetry Conformance — P1

Purpose: align transport behavior with current MCP direction without mixing operational telemetry into product semantics.

Work:

- keep stdio tool results deterministic and stateless;
- use stderr for ordinary stdio diagnostics;
- if structured server telemetry is added, use OpenTelemetry;
- do not build new product semantics on deprecated MCP Logging;
- never include full evidence payload/tool arguments in OTel by default;
- keep high-cardinality/sensitive source identifiers out of metric labels;
- if trace context propagation is supported, preserve it as operational transport context only.

Exit:

- MCP operational observability cannot strengthen or mutate repository evidence.

## EC-10 — Producer-Neutral Real-World Dogfood — P1

Purpose: prove the abstraction using real evidence classes without embedding producer-specific clients.

Dogfood normalized evidence derived externally from:

- pytest failure/traceback;
- Ruff diagnostic;
- mypy/compiler diagnostic;
- coverage miss;
- `uv tree` or dependency resolver output;
- `uv.lock` change;
- SBOM/vulnerability scanner finding;
- Loki/Grafana-style log query result;
- Splunk-style result;
- CloudWatch-style result;
- Sentry-style issue/event/traceback;
- OpenTelemetry trace/span anchor.

For every producer class verify:

- explicit scope;
- explicit completeness/truncation;
- trust provenance;
- bounded metadata;
- deterministic repository correlation;
- no producer-specific query execution in Hashmarks;
- no causation/repair authority.

Exit:

- multiple real producers map through one neutral contract.

## EC-11 — Cross-Bundle Correspondence — P1/P2

Purpose: expose useful repository facts across independent observations without inventing runtime causation.

Add optional derived correspondence facts such as:

- several anchors resolve to the same repository member;
- several anchors resolve to the same exact symbol/range;
- independent bundles disagree on qualified source equivalence;
- one bundle is incomplete while another independently observes the same repository location.

Rules:

- "same repository target" is allowed;
- "same cause", "same incident", "regression caused by", or "fix this" are not Hashmarks conclusions.

Exit:

- correlation can compactly show repository convergence across sources while staying non-causal.

## EC-12 — Adversarial, Bound, and Economics Qualification — P1

Purpose: prevent the new contract from becoming correct-but-expensive or correct-only on happy paths.

Qualification matrix:

- anchors: 1 / 10 / 100 / 256;
- relationships off/on;
- exact/ambiguous/unresolved/conflicting anchors;
- maximum metadata;
- maximum path mappings;
- overlapping mappings;
- complete/incomplete/unknown producer scope;
- source-side pagination/truncation;
- Hashmarks-side candidate bound exhaustion;
- tampered previous packets;
- reordered bundles;
- malicious/instruction-looking external text;
- compact/full output.

Measure:

- elapsed time;
- output bytes/tokens;
- relationship expansion cost;
- memory where practical;
- determinism/replay identity.

Exit:

- explicit budgets/ratchets exist for the public correlation path.

## EC-13 — Responsibility and Complexity Re-evaluation — P1

Purpose: decide structure from evidence after semantics stabilize.

Current `evidence_correlation.py` size is an investigation signal only.

Freshly measure:

- Ruff responsibility/complexity debt;
- exact test ownership;
- line/branch coverage;
- structural locality;
- callers/reuse of introduced helpers.

Inspect likely responsibility families:

- request validation;
- locator/path/symbol resolution;
- external scope/provenance;
- source equivalence;
- repository-evidence attachment;
- packet identity/validation;
- delta projection.

Do not split solely to reduce LOC/Ruff. A new owner must earn an independently evidenced semantic boundary.

Exit:

- keep cohesive authority or perform a BP1/BP2/locality-gated decomposition.

## EC-14 — Resume Fresh Responsibility-First Cleanup — after correlation closure

The old `responsibility-first-cleanup-20260921` branch is not merge authority.

Rules:

- start from fresh current `main`;
- remeasure current debt;
- let the measurement select the next target;
- if `structural_locality.py` is selected again, replay the earlier characterization/refactor evidence on fresh bytes rather than merging the diverged branch;
- otherwise keep the old branch as historical evidence only;
- remove all temporary measurement workflows before merge.

Dependency:

- agentsCookbook PR #54 provides the fail-closed locality bound behavior needed by the earlier structural-locality closure and must be independently qualified/merged before relying on it as main authority.

---

# Required regression inventory

Before the correlation hardening series is considered closed, tests must cover at least:

1. tampered prior packet rejected;
2. tampered nested repository evidence rejected;
3. duplicate bundle/anchor IDs rejected;
4. source scope change reported as definition/scope change;
5. time window change does not masquerade as repository change;
6. producer says complete but source reports truncated -> not complete;
7. Hashmarks candidate bound exhausted -> not exact negative evidence;
8. exact-limit vs limit+1 behavior distinguishes no-more vs more-exists;
9. ambiguous symbol remains ambiguous;
10. line/symbol disagreement remains claim-conflict;
11. source equivalence mismatch remains mismatch;
12. arbitrary commit-like metadata remains opaque;
13. instruction-looking log text remains untrusted data;
14. redaction declaration changes evidence definition identity;
15. compact output exposes omissions/truncation;
16. MCP previous-correlation replay is stateless and deterministic;
17. OpenTelemetry/server diagnostics never enter correlation packets;
18. cross-bundle same-symbol correspondence does not infer causation;
19. path mapping cannot escape repository confinement;
20. maximum accepted request either returns within explicit budget or fails explicitly.

# Merge strategy

Prefer small authority-closing PRs in this order:

1. EC-00 + EC-01
2. EC-02 + EC-03
3. EC-04 + EC-05
4. EC-06 + EC-07
5. EC-08 + EC-09
6. EC-10 + EC-11
7. EC-12
8. EC-13 if measurement justifies structural edits
9. EC-14 fresh cleanup continuation

Each PR must:

- start from exact current `main`;
- add focused regressions for every reproducible defect exposed;
- keep Hashmarks non-causal/non-executing;
- preserve current semantic owners rather than create parallel state;
- run the full repository-owned qualification gates before merge.

# Completion definition

The evidence-correlation program is closed only when:

- inbound and previous packets are integrity-validated;
- external content has an explicit untrusted-data boundary;
- producer scope/completeness/truncation are explicit;
- time/source provenance is separate from repository freshness;
- deltas distinguish repository change from question/scope change;
- source equivalence remains independently qualified;
- output and economics are bounded;
- MCP behavior is stateless and current-spec aligned;
- real observability/test/compiler/scanner evidence dogfoods one neutral contract;
- no log backend/query/diagnosis/execution authority has leaked into Hashmarks;
- any later structural cleanup is selected by fresh evidence rather than carried forward.
