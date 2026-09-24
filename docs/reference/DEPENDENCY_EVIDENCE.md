# Dependency evidence adapters and producer-neutral authority

**Status: normative dependency-evidence architecture.**

Hashmarks dependency evidence has one direction of travel:

```text
Maven evidence ──> Maven adapter ──┐
                                   │
uv.lock evidence ─> uv adapter ────┼──> general Hashmarks dependency evidence model
                                   │
future Gradle/npm/etc. ────────────┘
```

Package-manager and resolver semantics belong at the adapter edge. The shared dependency model owns only producer-neutral dependency facts, evidence authority, completeness, provenance, identity, delta, and bounded queries.

## The boundary

An adapter may know how Maven, uv, Gradle, npm, Cargo, an SBOM producer, or another resolver represents dependency information. Core dependency qualification must not.

The adapter translates producer-native material into the general `hashmarks.dependency-resolution.v2` contract. After that translation:

- core code must not branch on producer names such as `maven`, `uv`, `gradle`, or `npm`;
- core code must not interpret producer-specific source-format names;
- a producer-specific field must not be added to the shared schema merely because one adapter exposes it;
- a new ecosystem integrates by translating into existing semantic facts or by first extending the general semantic model with a producer-neutral concept.

If a proposed rule can only be explained as "Maven does X" or "uv.lock looks like Y", it belongs in the adapter unless the same rule can be stated independently of that producer.

## Physical source versus semantic authority

A dependency evidence source has two different identities that must not be conflated.

### Source kind

`kind` identifies the physical or logical producer format. It is provenance.

Examples:

- `maven-dependency-tree`;
- `maven-dependency-list`;
- `uv-lock`;
- a future `gradle-resolution-result` or `cyclonedx-sbom`.

Core dependency semantics treat source kind as opaque. Source kind is not permission to establish a fact.

### Authorities

`authorities` declares which general dependency facts the source is qualified to support.

The current semantic authorities are:

- `selection` — concrete selected dependency-node identity;
- `resolution-graph` — roots and dependency relationships;
- `resolved-inventory` — membership in a resolved dependency inventory;
- `module-ownership` — module-to-distribution ownership evidence.

One physical source may carry several authorities. Adapters must not fabricate duplicate source identities merely to satisfy different semantic uses of the same bytes.

For example, one `uv.lock` source can support selection, graph, and resolved-inventory facts. Maven tree and Maven list evidence may remain separate physical sources because they are separate producer artifacts, while the list source can support both resolved inventory and module ownership.

The general invariant is:

> A fact or completeness claim may be no stronger than the cited evidence source's declared semantic authority, completeness, truncation, context, and provenance.

The invariant is **not**:

> A fact of type X must come from source kind Y.

## Semantic facts

The shared model owns these concepts independently of producer syntax:

- logical components;
- concrete selections;
- contexts;
- roots;
- dependency relationships;
- resolved inventory membership;
- contextual module ownership;
- coverage/completeness/truncation;
- repository-input binding;
- observation, definition, and resolution identities;
- factual deltas;
- bounded dependency queries and explicit omissions.

Producer-native coordinates, lockfile source tables, Maven scopes/classifiers, workspace encodings, command output prefixes, and similar details are adapter concerns. They may be normalized into general fields only when the general field has the same meaning.

## Coverage and negative evidence

Coverage `kind` is a semantic domain, not a producer/source format. Supported coverage domains are the domains for which Hashmarks can make scoped completeness and negative-evidence claims.

A coverage claim must:

1. name a supported semantic coverage domain;
2. cite evidence with matching semantic authority;
3. remain within the cited source context;
4. never claim `complete` when any cited source is incomplete or truncated;
5. preserve empty-but-complete observations when emptiness itself is valid negative evidence.

Do not infer negative evidence from the mere existence of a producer artifact. Negative evidence comes from qualified semantic coverage.

## Adapter rules

Every dependency adapter must satisfy all of the following:

1. **Execution-free translation.** Consume already-produced repository/external evidence. Do not invoke the package manager or resolver inside qualification.
2. **No dependency-source archaeology.** Do not recursively inspect installed dependency implementation bytes.
3. **One physical source, one source identity.** Do not duplicate one artifact into fake source identities just to represent several semantic authorities.
4. **Explicit semantic authority.** Declare the general facts each source can support.
5. **Preserve ambiguity.** Do not select one owner, version, workspace member, or target when producer evidence is ambiguous.
6. **Preserve context.** Producer-native contexts are normalized, not collapsed.
7. **Preserve completeness and truncation.** Adapter convenience cannot strengthen incomplete evidence.
8. **No causal inference.** Dependency delta and correlation describe factual change/correspondence, not the cause of a failure.
9. **No producer-specific core rule.** If core needs a new rule, state and test it using neutral terminology before changing an adapter.
10. **Cross-producer parity.** Equivalent semantic facts from different adapters must yield equivalent general query/delta behavior even when provenance differs.

## Current adapters

### Maven

The Maven adapter consumes already-produced dependency-tree JSON and dependency-list text.

- tree evidence is a Maven source format that can support `selection` and `resolution-graph`;
- list evidence is a Maven source format that can support `selection`, `resolved-inventory`, and `module-ownership`;
- Maven-specific parsing, scopes, classifiers, diagnostic prefixes, and module annotations stay inside the adapter.

Core Hashmarks must not require Maven tree/list source kinds.

### uv

The uv adapter consumes committed/provided `uv.lock` bytes.

A single `uv.lock` artifact is one physical source and may support `selection`, `resolution-graph`, and `resolved-inventory`. It must not be split into synthetic graph/inventory sources when the underlying evidence bytes are identical.

uv-specific source mappings, dependency target resolution, markers, and workspace-root interpretation stay inside the adapter.

## Adding another ecosystem

Before adding a Gradle, npm, Cargo, SBOM, or other adapter:

1. identify the producer-native artifacts and their exact provenance;
2. state which existing semantic authorities each artifact can support;
3. translate into the existing general facts;
4. add producer-neutral contract tests first when a genuinely new semantic fact is required;
5. add adapter-specific parsing tests second;
6. add cross-producer behavior tests where another adapter can express the same fact;
7. verify that no core dependency module imports the new adapter or branches on its producer/source kind.

A new adapter is not complete merely because it parses its native format. It is complete when producer-native detail terminates at the adapter boundary and the resulting observation behaves like any other producer of the same semantic facts.

## Regression expectations

Meaningful defects at this boundary require semantic regressions. Especially protect:

- source-format kind remaining opaque to core authority;
- one source carrying multiple semantic authorities;
- fact-to-authority validation;
- coverage-to-authority validation;
- context isolation;
- ambiguity preservation;
- completeness/truncation non-strengthening;
- cross-producer query and delta parity.

Do not add tests whose only purpose is checking adapter names, filenames, or version strings. Tests should prove observable dependency-evidence behavior or an authority invariant.
