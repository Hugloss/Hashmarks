# Agent-evaluation fixtures

This directory contains **development measurement infrastructure**, not installed Hashmarks product state.

Hashmarks is repository intelligence. These corpora, packets, worker outputs, and retained fixtures measure how external consumers behave with and without Hashmarks evidence. They do not define runtime APIs, agent workflow authority, execution policy, or compatibility obligations.

`retained/` contains the single repository-owned copy of benchmark inputs/outputs that current tests or research reproduction still consume. Superseded benchmark snapshots belong to Git/PR history rather than parallel retained mirrors. New product behavior must still pass the product-admission contract in `docs/reference/PRODUCT_BOUNDARY.md`; benchmark wins do not authorize moving consumer workflow into Hashmarks.
