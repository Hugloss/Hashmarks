# Hashmarks Evidence Strengthening Master Plan

Status: development master plan; not normative product authority  
Authority base: Hashmarks `main` at `1e5cdfec0e65bcc79f453c61c9a1b54cc38d7f53`  
Supersedes: PR #27 planning branch based on pre-PR #28 main  
Scope: strengthen Hashmarks' repository-evidence and bounded evidence-correlation model without transferring agent, execution, observability-backend, package-manager, deployment, or certification authority into Hashmarks.

## Product test

Hashmarks answers:

> What is observable about this repository, how do we know it, how current and complete is the observation, what corresponds to it, and what changed?

Hashmarks does not answer:

> What should the consumer do next?

A capability is admitted only when its result can be expressed as repository evidence, qualified external-evidence correspondence, provenance, completeness, freshness, uncertainty, identity, or delta. If making the result true requires reasoning, execution, workflow history, remote discovery, runtime control, diagnosis, recommendation, or a decision about what should happen next, that responsibility remains outside Hashmarks.

External evidence may enrich Hashmarks' understanding of repository correspondence. Hashmarks does not acquire ownership of the system that produced the evidence.

## Qualified baseline inherited from PR #28

The plan starts after the large-evidence dogfood closure already merged into current main. Do not reimplement these capabilities:

- exact typed `module` locator;
- normalized packet-level repository-evidence bindings;
- request-local reuse of repeated locator resolution;
- shared 1 MiB core/MCP request and packet budgets;
- fail-closed packet-size enforcement;
- max 256 anchors;
- legal MCP round-trip of previous correlation;
- large-stream rule: producer parses/recover/aggregates; Hashmarks correlates bounded structured anchors;
- real Splunk-style dogfood proving repeated module observations and traceback locators;
- external modules remain unresolved unless repository evidence or independently qualified ownership evidence proves correspondence.

PR #27 remains historical planning evidence. Its useful EC requirements are incorporated here, but its pre-#28 branch is not merge authority.

# Master cross-domain rules

## M1 — Evidence admission matrix

Before adding a semantic owner, record:

- repository fact represented;
- concrete real-world defect/use-case admitting it;
- existing owner(s);
- missing fact;
- canonical owner;
- repository-derived vs external observation;
- persistence class;
- freshness owner;
- completeness owner;
- identity owner;
- delta/comparability owner;
- sensitivity/redaction handling;
- public/API/MCP exposure decision;
- explicit non-goals.

Useful-to-an-agent is not sufficient product admission.

## M2 — Existing-owner-first

A new domain does not imply a new module, schema, table, public method, or MCP tool. Extend an existing owner when it already owns the fact. Two writers for the same semantic fact are an architecture defect.

## M3 — Evidence state classes

Exactly distinguish:

1. canonical repository inputs;
2. reconstructible derived/index state;
3. qualified external observations, request-scoped by default;
4. consumer/workflow history, forbidden as Hashmarks authority.

Persistence of class 3 requires separate admission. Class 4 never becomes repository authority.

## M4 — Shared evidence axes, typed domain facts

Every evidence domain must define identity, authority/origin, scope/definition, freshness, completeness, provenance, ambiguity, bounds/truncation, observation identity, delta/comparability, persistence, and sensitivity.

Do not create one generic evidence object that erases typed domain semantics.

## M5 — Four independent operational axes

Trust, completeness, producer/query cost, and returned response size are separate. A small result may have been expensive; a trusted producer may still be incomplete; a complete external sample may still have incomplete repository projection.

## M6 — Negative evidence

Absence may be stated only for an explicitly declared scope for which every relevant producer and Hashmarks projection completeness axis is complete. Partial evidence may prove observed presence but never global absence.

## M7 — Comparability before delta

Before reporting a semantic delta distinguish:

- same question/different observation;
- definition changed;
- scope changed;
- producer semantics changed;
- not comparable.

A changed question must never masquerade as repository change.

## M8 — Identity governance

Every new identity domain defines:

- domain separator/version;
- canonical serialization;
- ordering;
- normalization;
- included/excluded fields;
- duplicate handling;
- missing-vs-null semantics.

Equivalent ordering must not alter semantic identity. Arbitrary metadata cannot strengthen repository identity.

## M9 — External producer provenance is not trust authority

Record producer identity/version/schema/collection mode/scope/completeness/truncation/redaction where available. Never translate `producer=X` into truth strength.

## M10 — Sensitive evidence

Hashmarks is not a secret/PII classifier. Prefer producer-side redaction; preserve redaction provenance when useful; never emit full external payloads in operational telemetry by default; never require credentials/tokens for identity; avoid dumping arbitrary external payloads in errors.

## M11 — No causation

Correspondence may say observations resolve to the same repository/dependency surface. It may not say one caused another, identify a culprit, diagnose root cause, recommend a repair, or choose the next action.

## M12 — No hidden truncation

Any Hashmarks bound that can omit valid evidence exposes the omission. Prefer limit+1 where practical to distinguish exact N from at least N+1.

## M13 — Economics are correctness

Qualify input bytes, repository/store reads, elapsed/CPU where practical, memory where practical, relationship expansion, output bytes, and deterministic replay at representative 1/10/100/max bounds. Repeated equivalent semantic requests must not cause avoidable linear repeated repository work.

## M14 — Metamorphic correctness

New evidence owners must test, where applicable:

- input reordering;
- duplicate equivalent observations;
- serialization round-trip;
- cold/warm parity;
- incremental/cold convergence;
- Python/MCP parity;
- bound changes;
- projection reduction;
- stateless replay.

Caching may change cost, never semantics.

## M15 — Adversarial structured input

Reject or safely represent oversized strings, excessive nesting, duplicate IDs, unknown schema versions, malicious Unicode, path escapes, graph bombs, cycles where legal, dangling edges, extreme numeric/time values, fake hash-looking metadata, high-cardinality opaque metadata, and instruction-looking text. Rejection itself must remain bounded.

## M16 — Schema lifecycle

Every public serialized contract has explicit schema identity, validator, canonical fixtures, unknown-field policy, unknown-enum policy, additive-change rules, semantic-version/evolution rules, and client/service/MCP parity where exposed. Do not accumulate compatibility normalization for obsolete unpublished development contracts.

## M17 — Public-surface budget

Internal owner != public CodeMap method != MCP tool. Promotion requires evidence that the responsibility is distinct and the existing public surface cannot expose it cleanly. Do not create one MCP tool per evidence domain.

## M18 — Failure semantics

Public machine-consumed surfaces distinguish invalid input, unsupported schema/producer semantics, ambiguous, unresolved, incomplete, stale/unknown, bound exhausted, not comparable, oversized packet, and repository-changed-during-observation where relevant. Do not force agents to parse unstable prose to recover semantic state.

## M19 — Failure/cancellation safety

Cancelled or failed read-only analysis must not publish half-built derived authority, retain partial external observations, leak transactions, or change later semantic answers.

## M20 — Cold reconstruction oracle

Disposable derived state can be deleted and rebuilt from admitted repository inputs plus explicitly supplied external evidence to produce semantically identical results. Hidden history may change latency, never meaning.

## M21 — Dogfood governance

Use large/private/local real-world corpora for development; minimize every exposed defect into a small neutral committed regression fixture; record the real-world characterization without requiring giant source datasets in ordinary tests.

## M22 — Defect closure

Every reproducible defect follows:

real-world defect -> minimal generic reproducer -> semantic owner -> repair -> focused regression -> decide whether a permanent invariant is justified.

## M23 — No false-authority qualification

For every new owner explicitly test risk of false uniqueness, false freshness, false completeness, false equivalence, false absence, external-claim promotion, correlation-as-causation, and compact output appearing stronger than full evidence.

## M24 — Ecosystem expansion

Generic shapes may be producer-neutral, but semantics are admitted one ecosystem at a time from real dogfood. Python+uv is the first dependency qualification. npm/Cargo/Maven/Go do not gain dependency semantics merely because Hashmarks can index their repositories.

## M25 — Feature lifecycle and rejection

Development evidence -> dogfood -> semantic-owner proof -> adversarial/economics qualification -> explicit public-contract decision.

Reject/remove a capability if it primarily models consumer workflow, cannot establish independent authority, requires execution to become true, creates persistent noisy ambiguity, needs dependency implementation crawling, or costs more than the evidence value justifies.

# MC — Master contract closure

## MC-00 — Normative contract convergence

Audit current `PRODUCT_BOUNDARY.md`, `INVARIANTS.md`, `STATE_AND_SEMANTIC_OWNERS.md`, `API_STABILITY.md`, architecture/reference docs, MCP integration docs, and maintainer responsibility map.

Correct weaker/stale wording. In particular, no normative text may imply Hashmarks decides what "should probably change"; Hashmarks may expose owners, affected surfaces, ambiguity, verification relevance, and correspondence, while the consumer chooses the change.

Exit: normative documents agree with the product-admission constitution.

## MC-01 — Existing semantic-owner coverage map

Inventory existing owners before new code, including configuration evidence, verification evidence, repository delta, project graph, import resolution, cross-repository evidence, producer provenance, repository evidence bindings, and evidence correlation.

Exit: every proposed fact has exactly one intended semantic owner and no parallel authority is planned.

## MC-02 — Evidence-domain admission matrix

Commit the admission template from M1 and apply it to dependency/distribution evidence. Candidate future domains are listed but explicitly not admitted.

Exit: dependency evidence is admitted by a concrete dogfood defect; future domains remain candidates.

## MC-03 — Shared identity/persistence/comparability rules

Document M3-M9 as reusable contract rules without introducing a generic evidence super-schema.

Exit: new owners reuse canonical vocabulary rather than inventing parallel freshness/completeness/delta state.

## MC-04 — Schema and machine-failure contract

Freeze schema lifecycle, validation, failure semantics, and Python/service/MCP parity rules.

Exit: public evidence cannot silently reinterpret incompatible input.

## MC-05 — Universal qualification harness/rules

Establish reusable metamorphic, adversarial, economics, cold/warm/incremental, and installed-artifact qualification requirements.

Exit: subsequent domains have a common quality bar.

# EC — Evidence correlation hardening

## EC-00 — Post-PR #28 v1 contract freeze

Freeze canonical fixtures for path, line, range where currently supported, symbol, module, ambiguity, conflicts, path mappings, source equivalence, completeness, normalized repository bindings, bounds, and previous-correlation round-trip.

Exit: hardening cannot silently reinterpret the published post-#28 v1 packet.

## EC-01 — Previous-correlation integrity

Fully validate inbound previous packets: schema, identities, allowed vocabulary, authority constants, unique IDs, path mappings, canonical repository bindings, source equivalence, completeness, bounds, and correlation/evidence-definition identities.

Exit: one-field tampering cannot produce authoritative delta.

## EC-02 — Untrusted external-evidence boundary

External messages/metadata are data, never instruction authority. Preserve producer-neutral origin/trust/redaction provenance without classifying arbitrary text as safe.

Exit: prompt-injection-looking evidence cannot acquire action authority.

## EC-03 — Scoped completeness and truncation

Represent explicit external observation scope, selection/query identity, time scope where applicable, requested/returned bounds, producer pagination/truncation, producer completeness, and Hashmarks projection completeness independently.

Exit: bounded samples cannot masquerade as global absence.

## EC-04 — Temporal/source provenance

Preserve event/observation/collection timing and source placement as external provenance, separate from repository freshness.

## EC-05 — Correlation delta comparability

Report correspondence changes only after definition/scope comparability. Distinguish repository change from changed question.

## EC-06 — Locator/range/path portability

Qualify Linux/container/Windows/WSL mappings, overlapping prefixes, confinement, ranges, and claim conflicts without creating a second path/range authority.

## EC-07 — Qualified source equivalence

Strengthen source equivalence only through independently comparable Hashmarks identity owners. Arbitrary commit/image/version labels remain claims.

## EC-08 — Compact bounded projection

Preserve authority-relevant identity/provenance/completeness/truncation/equivalence under compact output. Never silently truncate arrays or strings.

## EC-09 — MCP/OTel conformance

Keep product evidence separate from operational telemetry. Stdio diagnostics use stderr; structured operational telemetry, if present, follows current MCP/OpenTelemetry direction and excludes evidence payloads by default.

## EC-10 — Producer-neutral dogfood

Dogfood externally normalized pytest, Ruff/type/compiler, coverage, dependency, SBOM/scanner, Splunk/Loki/CloudWatch/Sentry-style, and OTel-style evidence without adding producer query clients to Hashmarks.

## EC-11 — Cross-bundle repository correspondence

Allow "same repository target/symbol" and disagreement facts; forbid "same cause/incident" conclusions.

## EC-12 — Final adversarial/economics matrix

Qualify 1/10/100/256 anchors, exact/ambiguous/unresolved/conflicting locators, relationships, maximum metadata/mappings, producer and Hashmarks truncation, tampered packets, malicious text, compact/full output, store reads, memory where practical, and replay identity.

## EC-13 — Responsibility remeasurement

After semantics stabilize, freshly measure `evidence_correlation.py` responsibility/complexity, coverage, locality, callers, and reuse. Split only when a distinct semantic owner is proven.

## EC-14 — Fresh responsibility-first cleanup

Restart general cleanup from exact fresh main and fresh debt measurement. Historical structural-locality work remains evidence, never predetermined merge authority.

# DE — Typed dependency/distribution evidence

## DE governing model

Keep four distinct layers:

1. declared dependency intent in repository manifests;
2. repository lock state as canonical repository bytes;
3. external structured resolution graph observation;
4. external installed/import-module ownership observation.

None automatically proves another.

Hashmarks does not run uv, install packages, mutate environments, fetch dependency source, crawl site-packages, resolve dependencies, recommend upgrades, or diagnose failures.

`uv.lock` remains repository identity/change evidence. Structured resolver semantics should preferentially arrive through a supported external producer contract such as externally generated `uv workspace metadata`, not by treating an unstable lockfile format as Hashmarks' permanent semantic API.

## DE-00 — Dependency semantic-owner contract

Apply the admission matrix. Define the new owner as dependency-resolution correspondence only and specify its handoffs with `project_graph.py`, import resolution, repository member identity, and evidence correlation.

Workspace/local projects retain repository-project identity even when they also appear as resolution nodes.

## DE-01 — Producer-neutral resolution snapshot

Define a versioned neutral snapshot for roots, nodes, dependency edges, markers, extras/groups, conflicts, distribution raw/canonical name, version, source, and opaque producer node identity.

Rules:

- normalized distribution name is not a graph key;
- multiple versions/sources/marker variants may coexist;
- cycles are legal;
- malformed/dangling graph structure fails closed;
- producer schema/version is explicit;
- preview producer formats are adapters, not copied wholesale into Hashmarks public semantics.

## DE-02 — Resolution scope identity and comparability

Make selected workspace/script/member roots, groups, extras, Python/platform marker scope, conflicts, and semantics-affecting producer options part of resolution definition identity.

Changed selection/platform/marker semantics => scope-changed/not-comparable, not package delta.

## DE-03 — Repository-input binding

Correlate external resolution snapshots to claimed repository inputs such as `pyproject.toml`, `uv.lock`, workspace manifests, or admitted lock artifacts.

A producer claim that it came from a lockfile does not prove current-byte equivalence. Only independently comparable revisions/digests may produce proven/mismatch; otherwise unknown.

Track repository byte delta independently from selected resolution semantic delta.

## DE-04 — Module/distribution ownership observation

Distribution names and import module/package names are separate namespaces. No fuzzy/name-convention inference such as `PIL -> Pillow`, `yaml -> PyYAML`, or underscore/hyphen rewriting may prove ownership.

Accept independently produced module ownership evidence with its own scope/completeness/provenance. Namespace packages may remain ambiguous or map to several distributions.

Hashmarks never runs environment synchronization to obtain this evidence.

## DE-05 — Repository import/dependency correspondence

Reuse existing indexed repository import identity. Correlate proven/ambiguous module ownership to dependency resolution nodes.

Allowed facts include repository path imports module X; qualified observation maps X to distribution node Y; node Y changed between comparable resolutions.

Causation remains not inferred.

## DE-06 — Dependency-resolution delta

For comparable scopes report independently:

- node/distribution added/removed;
- version changed;
- source changed;
- dependency edge changed;
- marker changed;
- selected root/group/extra changed where represented as definition change;
- direct/transitive classification relative to selected root changed;
- module ownership evidence changed.

Do not turn dependency delta into upgrade recommendation.

## DE-07 — Evidence-correlation composition

Only after DE-00..06 stabilize, let evidence correlation consume dependency-owner projections. Do not implement package semantics inside `evidence_correlation.py`.

Do not automatically add a new MCP tool. First prove existing correlation/query surfaces cannot expose the evidence cleanly.

## DE-08 — Real dependency-upgrade dogfood

Use real before/after Python+uv upgrade evidence, including a case equivalent to the prior cryptography-class issue:

repository inputs + resolution A -> changed repository/lock + resolution B + externally reported test/traceback -> Hashmarks correspondence/delta.

Require the consumer, not Hashmarks, to decide whether the dependency change caused the failure.

## DE-09 — Dependency adversarial/metamorphic/economics closure

Mandatory cases include:

- direct/transitive dependency;
- transitive-only upgrade;
- add/remove;
- registry/Git/path/editable source change;
- same normalized name with multiple versions;
- marker-specific alternatives;
- extras/groups;
- workspace member vs external distribution;
- cycle;
- dangling edge rejection;
- duplicate/tampered node IDs;
- changed root/group/platform => not comparable;
- stale/mismatched repository input;
- module/distribution name mismatch;
- shared namespace ambiguity;
- no ownership evidence => unknown;
- repository import correspondence;
- failure+dependency delta without causal conclusion;
- incomplete graph cannot prove absence;
- semantic-equivalent reordered graph identity;
- cold/warm/replay parity;
- 1/10/100/max node/edge economics.

# RC — Program closure

## RC-00 — Reconstruction/convergence

Prove cold/warm/incremental semantic parity for all newly persisted derived state. Delete disposable state and reconstruct identical evidence.

## RC-01 — Concurrency/failure/cancellation

Qualify repository mutation during query, rebuild during request, multiple readers, failed/cancelled requests, stale external observation, no leaked BUILDING authority, and deterministic convergence.

## RC-02 — Installed artifact and public contract

Run source and installed-wheel qualification, min/latest supported Python, public import surface, MCP installed-artifact smoke, schema fixtures, docs/package inclusion, and service/client parity.

## RC-03 — Documentation/owner convergence

Update responsibility map, semantic-owner table, architecture/reference docs, API stability surface where public, and permanent invariants only for truly permanent guarantees.

## RC-04 — Final product-boundary audit

Prove no agent planning, diagnosis, recommendation, editing, execution, retry/recovery, environment management, observability ingestion/search, deployment, certification, or hidden workflow history entered Hashmarks.

## RC-05 — Release-readiness closure

Close only when each admitted domain has one owner, versioned identity, freshness/completeness/persistence/comparability rules, adversarial/economics proof, installed-artifact proof, real dogfood, focused regressions, and no false-authority regressions.

# Candidate future evidence domains — admission required

These are not implementation commitments. Each must pass M1 and be admitted by a concrete missing repository primitive.

- configuration/environment declarations and correspondence;
- public/API/CLI/config/wire contract evidence;
- generated-artifact provenance;
- richer verification/coverage/diagnostic correspondence;
- artifact/source equivalence;
- schema/migration relationships;
- supply-chain/SBOM/scanner correspondence over DE;
- bounded explicitly declared cross-repository correspondence;
- bounded repository history/lineage where factual and non-causal;
- mechanically provable resource/side-effect surfaces.

Permanent red lines:

- no secret/live-environment ownership;
- no generator/test/build execution;
- no release/deployment/certification authority;
- no remote repository discovery/orchestration;
- no vulnerability remediation decision;
- no culprit scoring or historical causality;
- no runtime-behavior prediction from static hints.

# Immediate implementation sequence

1. MC-00/01: converge normative wording and map existing owners.
2. MC-02..05: commit admission/identity/persistence/schema/qualification rails.
3. EC-00/01: freeze post-#28 v1 and close previous-packet integrity.
4. EC-02/03: untrusted evidence + scoped completeness/truncation.
5. DE-00..03: owner, neutral snapshot, scope, repository binding.
6. DE-04..06: module ownership, import correspondence, delta.
7. DE-07..09: correlation composition, real upgrade dogfood, hard qualification.
8. EC-04..12: finish correlation provenance/comparability/portability/economics.
9. EC-13/14: remeasure responsibility and resume fresh cleanup only from evidence.
10. RC-00..05: convergence, failure safety, installed artifact, docs, boundary, release readiness.

Each implementation PR starts from exact current `main`, owns one coherent authority closure, adds focused regressions for exposed defects, and passes repository-owned qualification before merge.

# Completion test

The program is complete when Hashmarks can expose stronger typed repository truth and bounded correspondence while remaining able to say, precisely and cheaply:

- what fact is known;
- which owner establishes it;
- what evidence supports it;
- how fresh/complete/ambiguous it is;
- whether two observations are comparable;
- what changed;
- what is unresolved or not provable;

and still refuses, by architecture rather than convention, to decide what the consumer should do next.
