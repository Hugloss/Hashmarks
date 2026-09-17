# Junior-developer documentation audit

## Scope

Review why a developer can understand the Hashmarks product boundary yet still struggle to understand the implementation. The audit compares the current landing page, architecture/reference docs, `AGENTS.md`, historical-development index, `CodeMap` composition, and the `hashmarks/codemap` module surface.

## Finding 1 — conceptual architecture stopped before code ownership

`docs/reference/ARCHITECTURE.md` correctly explains canonical identity, observation/freshness, derived CodeMap, projections, and external execution. It does **not** map those layers to implementation modules or tell a maintainer where a behavior is produced.

Impact: a junior knows the conceptual layer but still has to grep through dozens of similarly related modules.

Closure: current maintainer documentation now maps responsibilities in `docs/maintainers/CODEMAP.md`.

## Finding 2 — `engine.py` composition is not a call graph

`CodeMap` is assembled from many mixins. The MRO is a composition mechanism, not a readable request flow. A new developer can easily assume mixin order describes runtime flow or start adding logic to `engine.py` because it is the visible class.

Impact: ownership mistakes and unnecessary centralization pressure.

Closure: the maintainer guide states that `engine.py` owns wiring/shared state and provides explicit traces for `sync()`, ownership, imports, and verification.

## Finding 3 — close names encode different responsibilities

Examples include:

- `import_resolution.py` versus `import_ownership.py`;
- `evidence_freshness.py` versus `freshness_map.py`;
- `ownership_analysis.py` versus `ownership_graph.py`;
- evidence producers versus consumer-facing projection modules.

These distinctions are architecturally intentional, but public docs did not explain them at implementation level.

Impact: a junior may merge responsibilities or call the wrong producer because filenames look interchangeable.

Closure: responsibility map and “things easy to misunderstand” section added.

## Finding 4 — current and historical docs were separated, but current maintainer docs had no home

`docs/development/README.md` correctly declares the development tree historical/non-normative. Before this closure there was no separate current maintainer-documentation lane.

Impact: implementation guidance either had to live in product contracts, which would bloat them, or in a directory explicitly described as historical.

Closure: added `docs/maintainers/README.md` and `docs/maintainers/CODEMAP.md`; `docs/development/` remains historical evidence only.

## Finding 5 — `AGENTS.md` is a guardrail ledger, not onboarding

`AGENTS.md` is dense by design: it records product-boundary and architecture guardrails accumulated over many phases. It is valuable for an experienced contributor/agent deciding whether a change is admissible, but it is a poor first implementation map.

Impact: a junior can read hundreds of lines of prohibitions without learning the shortest path to the code that owns a bug.

Decision: do not simplify away those guardrails. Route maintainers to the implementation map first, then use `AGENTS.md` as the change-admission checklist.

## Finding 6 — module count makes filename-order reading ineffective

`hashmarks/codemap/` contains dozens of modules. Reading alphabetically or reading every file before making a change is neither efficient nor a reliable way to infer authority.

Closure: the maintainer guide teaches a producer → evidence/store → consumer reading strategy and instructs maintainers to begin from a public method plus focused tests.

## Acceptance criteria

A new maintainer should be able to answer, without reading the whole package:

1. where `CodeMap.sync()` discovery/stale-removal behavior lives;
2. why import identity and import-ownership diagnostics are different;
3. where repository ownership evidence is composed versus selected/projected;
4. what `decision_session.py` may cache;
5. which directories contain current contracts, current maintainer guidance, and historical evidence;
6. where to begin debugging an indexing, ownership, import-resolution, or verification issue.

This audit does not claim every internal algorithm is simple. Its purpose is to make responsibility and entry points discoverable before a developer reads the implementation details.
