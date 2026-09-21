# EC-16 CodeMap Watch Lifecycle Ownership Closure

## Fresh authority

Exact starting `main`: `8223ad2ddcbd75a27041e869dc8f59af42f508a8`.

This phase starts after EC-15 merged and re-reads the resulting main bytes. On those bytes:
- `hashmarks/codemap/evidence_verification.py` is below the 1,600-line production ceiling;
- `hashmarks/codemap/indexing_lifecycle.py` is **1,663 fetched lines** and is the remaining oversized production file.

The last qualified exact Ruff inventory remains **1,513 excess / 128 functions / 245 findings**. EC-16 does not claim a Ruff-debt reduction; it addresses the remaining structural line-ceiling violation.

## Responsibility review

`indexing_lifecycle.py` contained one separable foreground orchestration responsibility in `watch_forever()`.

That method does not implement:
- watcher backends — owned by `hashmarks/watcher.py`;
- observation continuity state — owned by `hashmarks/observation.py`;
- repository discovery/sync/reconciliation — owned by `indexing_lifecycle.py`;
- freshness semantics — owned by existing freshness/query surfaces.

It composes those authorities into the foreground CodeMap watcher lifecycle:
1. start observer before the initial full sync;
2. publish watcher process/state/heartbeat metadata;
3. reconcile initial UNKNOWN observation state;
4. force a full sync if watcher continuity becomes UNKNOWN;
5. stop the observer and publish stopped state on exit.

## Pre-edit contract freeze

Before moving production bytes, EC-16 adds `tests/test_index_watch_lifecycle.py` with direct owner-independent regressions for:
- observer start before initial sync, initial synchronization, and clean stopped metadata;
- UNKNOWN observation state forcing a second full reconciliation.

The tests resolve `CodeMap.watch_forever.__module__` dynamically, so they test the public CodeMap lifecycle rather than hardcoding the old module owner.

Test-freeze commit: `b47188dcc8f7839df787268f08b5a0c3f50ad430`.

The existing Linux subprocess regression `test_codemap_watcher_keeps_map_hot_without_identity_daemon` remains unchanged and continues to qualify real watcher integration.

## Bounded edit

The existing `watch_forever()` implementation is moved intact into:
`hashmarks/codemap/index_watch.py` as `IndexWatchMixin`.

`CodeMap.watch_forever()` remains the same public method through CodeMap mixin composition. No compatibility wrapper, second watcher state model, or alternate reconciliation path is introduced.

Measured source shape after the move:
- `indexing_lifecycle.py`: **1,663 -> 1,580 fetched lines**;
- `index_watch.py`: **98 fetched lines**.

## Preserved boundaries

- watcher backend implementation remains in `hashmarks/watcher.py`;
- `ChangeTracker` / `ObservationState` remain the sole observation-state authority;
- `sync()` remains owned by `IndexingLifecycleMixin`;
- generation/freshness/status methods remain in `IndexingLifecycleMixin`;
- no execution, retry, or recovery semantics are added beyond the existing watcher reconciliation behavior;
- no public schema or state vocabulary changes.

## Qualification rule

Merge only if the exact PR head passes the full repository CI matrix, including the Linux watcher regression, Python 3.11-3.14, release qualification, MCP compatibility, and Qualification convergence.

After merge, remeasure fresh `main`. Only then consider ratcheting the Ruff no-growth baseline or making maintainability debt authoritative.
