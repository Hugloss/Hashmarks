# HM297 external-library characterization lesson

**Status:** historical development record — non-normative. Current authority is `docs/reference/PRODUCT_BOUNDARY.md` and `docs/reference/INVARIANTS.md`.

## What happened

HM297 used real installed package source from projects including Pydantic, pytest, Starlette, AnyIO, HTTPX, FastAPI, HTTPCore, Uvicorn, Click, Cryptography, and PyYAML as bounded development characterization corpora. That experiment was useful: it exposed a **generic** concurrency-analyzer precision defect around definite function-local mappings and context/run-scoped state. HM297 repaired that generic rule without adding package-name suppressions.

After the generic repair, a tempting next step was to continue investigating remaining named findings such as Starlette context behavior, Pydantic alias behavior, and pytest cache behavior simply to determine whether the top-level finding count could be made smaller.

That continuation is now explicitly rejected.

## Lesson

> **Do not chase remaining findings in external libraries.**

Hashmarks analyzes the admitted repository, not the dependency ecosystem surrounding it. Third-party source can be useful as a bounded real-code test corpus, but it must not become an open-ended investigation queue. An import/reference edge does not transfer analysis ownership to the dependency implementation.

The correct development pattern is:

```text
real external code exposes a possible issue
        ↓
ask whether the behavior is a generic Hashmarks defect
        ↓
if yes: reduce to neutral semantics + minimal regression fixture
        ↓
fix the generic analyzer and re-check representative repositories
        ↓
stop

if no generic defect is proven:
NO_CHANGE
```

The rejected pattern is:

```text
Pydantic finding → investigate Pydantic
Starlette finding → investigate Starlette
pytest finding    → investigate pytest
next dependency  → continue indefinitely
```

That path would make Hashmarks slower to develop, encourage package-specific suppression logic, and gradually turn repository intelligence into dependency-ecosystem archaeology.

## Historical findings are not backlog

The remaining Starlette, Pydantic, pytest, HTTPCore, or other named-package observations from HM297 remain valuable historical evidence. They document what the analyzer saw and prevent future teams from repeating the same characterization blindly.

They are **not active roadmap items**. Do not reopen them merely to reduce a count. Reopen product work only when repository-owned evidence or a bounded independent corpus proves a generic correctness, freshness, ambiguity, provenance, or scope defect in Hashmarks itself.

## Permanent rule created from the lesson

HM298 promotes the lesson into current repository governance:

- `PRODUCT_BOUNDARY.md` defines the repository/dependency analysis scope;
- `AGENTS.md` tells coding agents not to chase named dependencies;
- contributor guidance requires explicit repository analysis scope;
- `ARCHITECTURE.md` shows external dependency edges stopping at the admitted repository boundary;
- `INVARIANTS.md` freezes the rule as PB8/PB9;
- boundary tests prevent silent documentation drift.

This file remains historical explanation only. It does not replace those normative documents.
