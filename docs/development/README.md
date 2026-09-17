# Historical development record

This directory contains development evidence: phase handoffs, benchmark receipts, audits, reviews, status ledgers, and historical documentation snapshots.

These files are useful for archaeology and for understanding why current contracts exist, but they are **not normative product documentation**.

When historical text conflicts with current documentation, use this precedence order:

1. `docs/reference/PRODUCT_BOUNDARY.md`
2. `docs/reference/INVARIANTS.md`
3. current integration/reference documentation
4. root `README.md` / `AGENTS.md`
5. historical development records

Key archives:

- [`HISTORICAL_RELEASE_NOTES.md`](HISTORICAL_RELEASE_NOTES.md) — the former long-form root README/release chronology.
- [`HISTORICAL_OH_GOON_INTEGRATION_NOTES.md`](HISTORICAL_OH_GOON_INTEGRATION_NOTES.md) — version-by-version integration history superseded by the current integration contract.
- [`HISTORICAL_INVARIANTS.md`](HISTORICAL_INVARIANTS.md) — preserved pre-public invariant ledger, including superseded execution/agent-evaluation contracts.
- `handoffs/` — historical continuation checkpoints.
- `evidence/` — measurement and qualification receipts.
- `audits/` / `reviews/` — bounded development investigations.
- `status/` — historical status ledgers.

Launch/release operations:

- [`LAUNCH_DISCOVERY.md`](LAUNCH_DISCOVERY.md) — GitHub/PyPI/MCP Registry discovery language, repository topics, and launch metadata checklist.
- [`PUBLISHING_CHECKLIST.md`](PUBLISHING_CHECKLIST.md) — release-publication checklist and external promotion requirements.
