# Structural locality evidence

Hashmarks can project fresh, bounded structural-locality facts for one exact repository symbol:

```bash
hashmarks --workspace . structural-locality path/to/file.py::qualified_symbol
```

The projection is repository evidence, not refactor policy. It is intended for external coding agents, review systems, and tools that need to compare the cost of understanding a structural edit without allowing Hashmarks to decide whether the edit is desirable.

## What the packet owns

A `hashmarks.structural-locality.v1` packet binds:

- the exact `path::qualname` target;
- the synchronized repository fingerprint;
- the exact target source identity;
- the measurement configuration identity;
- bounded reachable symbols and static call edges;
- exact observed caller evidence when the indexed target resolves unambiguously; this is a conservative lower bound, not a proof that no aliased or dynamically bound callers exist;
- unresolved call/caller candidates when exact resolution is not possible;
- syntactic forwarding-only classification where Hashmarks has a supported parser;
- file fan-out, symbol count, navigation depth, context-line closure and cross-file reach;
- structurally related verifier paths;
- freshness, bounds, provider version and one evidence identity.

Hashmarks does **not** infer that a helper is a good abstraction, that a wrapper is justified, that a responsibility should be split, or that the caller should edit anything.

## Fresh measurement

The CLI/API performs an explicit CodeMap sync by default before producing the packet. The packet therefore records `freshness.state = "current"` with basis `explicit-sync`.

The Python API may request `refresh=False` for diagnostic use. Such a packet retains the ordinary observer freshness state and may be `unknown` or `stale`. Consumers that need architectural authority should fail closed on non-current evidence.

## Ambiguity

Structural-locality evidence deliberately prefers incompleteness to a false exact edge.

For a static call such as `helper(...)`, Hashmarks resolves the target only when the indexed repository evidence identifies one unambiguous symbol. If two repository symbols can satisfy the same short identity, the edge is emitted in `unresolved_calls` with candidate symbol IDs and is **not** counted as exact reuse, exact ownership, or exact navigation closure.

The same rule applies to caller evidence. A candidate caller that cannot be proven to target the selected symbol remains unresolved. `exact_caller_count` is therefore safe as positive evidence (for example, two exact callers prove at least two callers) but must not be interpreted as global caller-set completeness or as proof that a symbol is single-use.

## Forwarding-only syntax

For supported Python symbols, Hashmarks reports whether the function body is syntactically just one call/return-call after an optional docstring. This is a structural observation only.

A forwarding-only function may still be required by an external compatibility or protocol contract. Whether that cost is justified belongs to the consumer.

## Delta

Two packets measured with the same target and measurement configuration can be compared with:

```bash
hashmarks structural-locality-delta --before before.json --after after.json
```

The `hashmarks.structural-locality-delta.v1` result reports:

- introduced and removed symbol IDs;
- dimension deltas;
- verifier-path additions/removals;
- exact before/after evidence and repository identities;
- comparability/incomparability reasons.

It intentionally contains no architectural score, recommendation, winner, edit instruction, or merge authority.

## Consumer split

The intended ownership boundary is:

```text
repository bytes
    |
    v
Hashmarks structural-locality facts
    |
    +--> external refactor methodology / agent economics
    |
    +--> repository-owned semantic contracts
```

Hashmarks owns what is structurally observable. A consumer such as agentsCookbook may combine those facts with repository-owned semantic evidence to decide whether new helpers, wrappers, shims, adapters, or modules actually earn their existence.
