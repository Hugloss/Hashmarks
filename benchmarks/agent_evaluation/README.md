# Agent-evaluation fixtures

This directory contains **development measurement infrastructure**, not installed Hashmarks product state.

Hashmarks is repository intelligence. Synthetic repositories, corpora, packets, and worker outputs are used to measure how external consumers behave with and without Hashmarks evidence. They do not define runtime APIs, agent workflow authority, execution policy, or compatibility obligations.

Canonical synthetic fixture inputs are owned by the evaluation code that materializes them into a caller-supplied run directory. Generated blind inputs, packets, worker outputs, and result files are not committed as parallel repository state. Real-world retained qualification evidence, when exact external provenance matters, belongs in the repository-quality evidence surface rather than in a generated fixture mirror.

New product behavior must still pass the product-admission contract in `docs/reference/PRODUCT_BOUNDARY.md`; benchmark wins do not authorize moving consumer workflow into Hashmarks.
