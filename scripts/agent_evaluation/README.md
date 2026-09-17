# External-agent evaluation tooling

This directory contains **development and measurement infrastructure**, not Hashmarks product runtime.

The tools here may launch or model external coding agents, benchmark worker behavior, grade retained traces, compare retrieval strategies, or measure evidence economics. They exist to evaluate Hashmarks repository intelligence. They do **not** define product authority and are not installed as part of the `hashmarks` Python package.

Key rules:

- Hashmarks production code must not import this package.
- A benchmark result is evidence about Hashmarks, not automatic admission for a new product feature.
- Agent workflow, attempt history, recovery, delegation, model routing, edits, and verification execution remain external responsibilities.
- New production behavior discovered through these experiments must pass `docs/reference/PRODUCT_BOUNDARY.md` before implementation.
- Invoke executable evaluation modules from the repository root with `python -m scripts.agent_evaluation.<module>` (normally through `make evaluation-help` targets), so package ownership and imports remain explicit.

Historical benchmark contracts belong under `docs/development/`; current product contracts live under `docs/reference/`.
