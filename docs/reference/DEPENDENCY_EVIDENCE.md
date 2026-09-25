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

The adapter translates producer-native material into the general `hashmarks.dependency-resolution.v3` contract. After that translation:

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

Source completeness and semantic coverage are separate axes. Source completeness says whether the supplied producer artifact/observation itself is complete and untruncated within its declared context. Coverage says whether a specific semantic domain is exhaustive. A physically complete source may therefore support incomplete `module-ownership` coverage, and carrying an authority never by itself makes that authority complete.

Semantic authorities are producer/caller declarations inside an external observation. Core qualification checks that facts and coverage do not exceed those declarations; it does not infer authority from `kind` or independently certify the external producer. Repository truth remains governed by the normal Hashmarks correlation and repository-evidence boundaries.

`producer_digest` is an adapter-computed or caller-supplied byte fingerprint; core does not independently verify arbitrary external bytes. It does not establish physical artifact identity: two distinct artifacts can have identical bytes. Core enforces unique `source_id` values within an observation, while each adapter is responsible for assigning one source identity to each supplied artifact and reusing that identity across all of its semantic authorities.

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

`scope` is an opaque JSON map of semantic conditions under which the same resolution question is asked. It may be empty. Adapters must keep producer format, evidence names, and ecosystem labels out of `scope`; those belong in `producer`, source `kind`, or other provenance fields. Core hashes the canonical map without interpreting its keys. A change to a semantic condition, such as an interpreter constraint, changes the definition.

`definition_identity` covers semantic scope, contexts, and roots without evidence references. `resolution_identity` covers that definition and the semantic components, selections, inventory, and relationships. `observation_identity` also binds producer metadata, physical evidence sources, coverage, module ownership, repository inputs, and repository binding. Changing only the producer therefore preserves resolution comparability while changing the observation identity. Delta remains factual and does not certify either producer.

Qualified observations expose `root_evidence` separately from semantic `roots`, so consumers can revalidate the evidence references bound by `observation_identity`. Public dependency queries, deltas, correspondence, and correlation revalidate normalized structure and content identities before using a supplied packet. This detects alteration or inconsistent reuse; because the hashes are not signatures, it does not authenticate the external producer or turn caller-declared authority into repository truth.

The v3 snapshot surface is fail-closed: unknown top-level and typed fact/source/coverage fields are rejected rather than silently normalized away. A v3 relationship has `kind: dependency`; other kinds are rejected, including when a supplied observation is replayed through queries or delta. Dependency-correlation request and row mappings are fail-closed for the same reason; caller metadata that is not part of the correlation contract is not silently discarded. `producer` metadata and semantic `scope` remain intentionally opaque JSON maps. Pure observation queries/deltas may be replayed from a structurally valid packet, but correspondence/correlation that combines dependency evidence with live repository intelligence requires the packet's repository identity and CodeMap generation to match the current CodeMap.

## Coverage and negative evidence

Coverage `kind` is a semantic domain, not a producer/source format. The current coverage domains are `selection`, `resolution-graph`, `resolved-inventory`, and `module-ownership`.

`selection` coverage owns exhaustiveness of selected-node/context membership and therefore bounds `contexts` query completeness. Graph coverage owns graph traversal/absence, inventory coverage owns inventory membership/absence, and module-ownership coverage owns module-owner absence. One domain must not stand in for another merely because a current producer emits them together.

Dependency query requests are fail-closed for unknown fields while preserving the documented shared request shape used across operations. Supplied query identifiers must be strings and bounds must be integers, not coercible text, floats, or booleans. Graph traversal never crosses declared context boundaries: an observation with multiple contexts requires an explicit context. Within one context, marker-qualified relationships and edges incident to marker-qualified selections remain facts but are not flattened into unconditional node topology. Traversal follows unconditional edges only and reports reachable conditional edges as `conditional-edge` omissions; a query starting from a marker-qualified selection reports `conditional-selection` unless it asks for the trivial zero-length identity path. Such omissions make the result incomplete and prevent authoritative negative evidence. Relationship multiplicity by marker/effective scope remains in the observation and delta, while unconditional node-topology traversal collapses duplicate source-target edges.

A missing component ID is admissible absence only when selection coverage is complete in every declared context. An explicit module-ownership row with no owners retains `state: unresolved` to describe link cardinality; it supports an absent-owner query result only when both that row and the relevant module-ownership coverage are complete. Incomplete or unknown rows do not become negative evidence because another source declared complete coverage.

A coverage claim must:

1. name a supported semantic coverage domain;
2. cite evidence with matching semantic authority;
3. remain within the cited source context;
4. never claim `complete` when any cited source is incomplete or truncated;
5. preserve empty-but-complete observations when emptiness itself is valid negative evidence.

Every cited source must support the claimed fact or coverage domain; one qualified source cannot lend its authority to another source listed in the same row. Complete graph coverage does not require a root: an empty graph and a graph whose producer identifies no root are both valid observations. Absence is admissible only within the separately complete, untruncated coverage domain and declared context.

Dependency negative evidence, ownership, queries, deltas, and correspondence retain `producer_authority: caller-claimed`. Their `qualified-external-observation` authority describes Hashmarks' structural qualification of a caller claim, not independent proof of the producer's truth. MCP and correlation envelopes that combine repository and external evidence label the dependency subprojection explicitly.

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
11. **Semantic IDs cannot smuggle provenance.** Adapter-generated `component_id` and `node_id` values may encode package/component identity, selected version/variant, and other producer-neutral selection semantics, but must not include adapter names, evidence `source_id`, source-format `kind`, producer digests, or other provenance merely to make IDs unique. Two adapters that claim to describe the same ecosystem identity semantics must normalize compatible IDs or explicitly document why their observations are not identity-compatible.

## Current adapters

### Maven

The Maven adapter consumes already-produced dependency-tree JSON and dependency-list text.

- tree evidence is a Maven source format that can support `selection` and `resolution-graph`;
- list evidence is a Maven source format that can support `selection`, `resolved-inventory`, and `module-ownership`;
- Maven tree/list bytes establish positive facts, but do not by themselves prove semantic exhaustiveness because Maven goals support caller-selected filters; complete graph/inventory coverage requires an explicit caller declaration for the supplied context;
- complete list coverage additionally requires a recognized list header and fully parsed content; Maven's `none` marker and a header-only list can describe an empty complete inventory only when that context was explicitly declared complete, while errors, dependency-resolution warnings that negate metadata completeness, or unexplained content do not;
- module-owner absence is admissible only when the list's module annotations establish complete module-ownership coverage;
- Maven-specific parsing, scopes, classifiers, diagnostic prefixes, and module annotations stay inside the adapter.

Core Hashmarks must not require Maven tree/list source kinds.

### uv

The uv adapter consumes committed/provided `uv.lock` bytes.

A single `uv.lock` artifact is one physical source and may support `selection`, `resolution-graph`, and `resolved-inventory`. It must not be split into synthetic graph/inventory sources when the underlying evidence bytes are identical.

The lock's base, optional-extra, and development dependency tables all contribute graph edges. The adapter retains the one lock context and distinguishes grouped edges with `effective_scope` values such as `extra:mcp` and `dev:lint`. An unsupported group shape cannot yield complete graph coverage.

The current adapter admits only uv lock schema version 1 shapes it can model faithfully. Top-level `resolution-markers` are preserved as producer provenance when package selections themselves do not carry fork membership, and marker-qualified relationship facts remain intact. Node-topology queries traverse only unconditional edges; when a reachable node has marker-qualified outgoing/incoming edges, those edges are not flattened into unconditional reachability and the result records a `conditional-edge` omission, making completeness incomplete and preventing negative evidence from becoming admissible. Package-level `resolution-markers` are rejected because selection fork membership is not yet represented by the general model. Declared conflict sets are also rejected rather than flattened because they encode mutually exclusive extras/groups that Hashmarks cannot yet preserve. Top-level `supported-markers` and `required-markers` are normalized into producer-neutral semantic scope (`supported_environments` / `required_environments`) because they change the environment domain or support constraints of the resolution question; changing them therefore changes definition identity even when the selected package facts happen to remain identical.

uv-specific source mappings, dependency target resolution, markers, and workspace-root interpretation stay inside the adapter.

## Adding another ecosystem

Before adding a Gradle, npm, Cargo, SBOM, or other adapter:

1. identify the producer-native artifacts and their exact provenance;
2. state which existing semantic authorities each artifact can support;
3. separate semantic resolution-domain constraints from producer bookkeeping: normalize the former into general `scope`, keep the latter in provenance, and reject producer constructs whose semantics the general model cannot represent;
4. validate producer identity/coordinate field types before normalization; do not turn malformed booleans/numbers into authoritative strings;
5. treat completeness as an authority claim, not a parser side effect: if the producer can emit filtered/subset artifacts whose filters are not encoded in the bytes, require explicit completeness evidence instead of inferring exhaustiveness from syntax;
6. translate into the existing general facts;
7. add producer-neutral contract tests first when a genuinely new semantic fact is required;
8. emit a `relationships` row only for a traversable dependency edge with `kind: dependency`; keep constraints, conflicts, recommendations, diagnostics, and other non-topological producer facts out of graph traversal;
9. add adapter-specific parsing tests second;
10. add cross-producer behavior tests where another adapter can express the same fact;
11. verify that no core dependency module imports the new adapter or branches on its producer/source kind.

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
