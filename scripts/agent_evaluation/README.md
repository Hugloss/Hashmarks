# External-agent evaluation tooling

This directory contains **development and measurement infrastructure**, not Hashmarks product runtime.

The tools here may launch or model external coding agents, benchmark worker behavior, grade retained traces, compare retrieval strategies, or measure evidence economics. They exist to evaluate Hashmarks repository intelligence. They do **not** define product authority and are not installed as part of the `hashmarks` Python package.

Key rules:

- Hashmarks production code must not import this package.
- A benchmark result is evidence about Hashmarks, not automatic admission for a new product feature.
- Cross-repository dogfood and parity probes belong here as measurement infrastructure; they do not become Hashmarks acceptance authority.
- Agent workflow, attempt history, recovery, delegation, model routing, edits, and verification execution remain external responsibilities.
- New production behavior discovered through these experiments must pass `docs/reference/PRODUCT_BOUNDARY.md` before implementation.
- Invoke executable evaluation modules from the repository root with `python -m scripts.agent_evaluation.<module>` (normally through `make evaluation-help` targets), so package ownership and imports remain explicit.
- Evaluation schema versions describe serialized contracts; evaluation family identifiers describe semantic protocols/fixtures and must not be coupled to the Hashmarks package version.

Current product contracts live under `docs/reference/`. Superseded benchmark contracts and development experiments remain recoverable from Git and merged pull requests rather than a parallel historical-document tree.
