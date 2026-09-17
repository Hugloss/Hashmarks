# HM52-R — Documentation Ownership / Repository Surface Closure

## Parent authority

Exact parent: HM51-R — Ten-Phase Proof-Gated Closure.
Parent ZIP SHA-256: `0f74445fb0a9f43f37ed19be1a15f3ecd0aae5690b68c2099c3036ec13af0049`.

## Why this phase was admitted

The exact HM51-R root contained 31 Markdown files: conventional entry points plus 27 phase handoffs and several responsibility-specific documents. This was direct repository-surface evidence that historical development artifacts had accumulated at the root and obscured ownership/navigation.

## Change

Documentation is now classified by responsibility rather than filename prefix:

- root: only `README.md` and `AGENTS.md`;
- `docs/reference/`: normative invariants and compatibility classifications;
- `docs/integration/`: external product-boundary contracts;
- `docs/qualification/`: qualification/test-economics material;
- `docs/development/handoffs/`: phase continuation handoffs;
- `docs/development/audits/`: bounded audits;
- `docs/development/reviews/`: historical/current development reviews;
- `docs/development/status/`: historical status ledgers.

`docs/README.md` is the navigation authority. Source-distribution membership now owns the `docs/` tree rather than a small list of root Markdown files. Tests and references were updated to the responsibility-owned paths.

## Regression authority

`test_repository_root_markdown_is_limited_to_entry_points` prevents phase/status/audit Markdown from accumulating at repository root again.

## Qualification in ChatGPT environment

- affected + product/build ring: 66/66 PASS;
- source `compileall`: PASS;
- deterministic ZIP rebuild is required before persistence.

This is repository hygiene/discoverability work only. No repository-intelligence semantics, ranking, freshness, execution authority, or public data contract was intentionally changed.
