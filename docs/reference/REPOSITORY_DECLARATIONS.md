# Repository declarations and cross-artifact correspondence

**Status: public repository-intelligence contract.**

Hashmarks can represent multiple declarations of the same conceptual repository fact, including declarations distributed across files and formats, while preserving each declaration's exact repository evidence, identity, freshness, ambiguity, provenance, and relationship to the others.

The governing boundary is:

> **Hashmarks reports equivalence, disagreement, absence, and ambiguity; it does not choose which declaration should win.**

This capability is intentionally not a universal service/configuration ontology. Hashmarks core does not define concepts such as \`service.owner\`, \`service.lifecycle\`, \`runtime.python\`, or organization-specific source-of-truth precedence.

## Why this exists

Repositories frequently express one conceptual fact on several surfaces:

- intent in a manifest and a concrete value in a lock/configuration artifact;
- runtime compatibility in build, container, and CI configuration;
- component identity repeated across packaging and deployment metadata;
- ownership or membership declarations distributed across repository metadata;
- generated and source declarations that refer to the same conceptual value.

Ordinary path or key search can locate those files but cannot safely state whether the declarations are comparable, equivalent, different, absent, or ambiguous.

Repository declarations provide the producer-neutral evidence contract for that problem.

## Authority split

The declaration provider owns:

- producer-specific parsing;
- semantic extraction;
- normalization of comparable values;
- provenance for each declaration;
- the claim, with explicit provenance/basis, that declarations correspond to the same conceptual fact;
- the semantic namespace and scope in which that conceptual identity is meaningful;
- coverage claims, coverage provenance, and expected declaration membership.

Hashmarks core owns:

- exact repository evidence binding;
- content-derived member/span identity;
- repository freshness;
- deterministic declaration/group identities;
- exact equality/difference over provider-normalized values;
- ambiguity preservation;
- coverage-qualified negative evidence;
- bounded request handling;
- factual before/after deltas.

The consumer owns:

- source-of-truth precedence;
- deciding which declaration is correct;
- repair choice;
- edits;
- policy or workflow decisions.

Provider claims do not become repository truth merely because Hashmarks carries them. Public packets therefore mark semantic values, correspondence, and coverage as provider-claimed while repository evidence remains governed by the existing repository-evidence authority.

## No universal schema

A declaration group has a non-empty \`semantic_namespace\`, a non-empty opaque \`concept\` object, and an opaque semantic \`scope\`.

The namespace prevents unrelated producers from accidentally sharing semantic identity merely because their opaque concept/scope JSON happens to match. Direct \`repository_declarations()\` callers supply the namespace explicitly. Provider discovery binds it to the registered provider name and rejects provider attempts to override it.

Core does not interpret the namespace, concept, or scope. Declaration producer metadata, correspondence basis, and coverage provenance are required to be non-empty objects so semantic claims cannot silently lose the provenance that made them meaningful.

For example, a provider may use:

~~~json
{
  "semantic_namespace": "example-runtime-provider",
  "concept": {
    "kind": "runtime-compatibility",
    "identity": "python"
  },
  "scope": {
    "environment": "application"
  }
}
~~~

Another provider may use completely different fields. Those names do not become Hashmarks vocabulary.

The invariant is:

> Producer-specific semantics terminate at the provider boundary. Core operates on an explicit semantic namespace, declared correspondence, scope, normalized values, evidence, provenance, completeness, freshness, ambiguity, identity, and delta.

Equal \`concept + scope\` under different semantic namespaces is **not** semantic equivalence. Cross-provider correspondence requires an explicit producer that owns that correspondence; Hashmarks core never manufactures it from matching opaque JSON.

## Scope prevents false disagreement

Two values that look different are not necessarily contradictory.

For example, an application requirement, a CI test version, and a build-image version may describe different semantic scopes. Hashmarks must not flatten them into one disagreement merely because they mention Python.

A provider must place non-comparable declarations in different groups/scopes. Group scope participates in \`group_definition_identity\`.

Hashmarks compares values only inside one explicitly scoped declaration group.

## Correspondence is explicit

Hashmarks core never decides that two declarations concern the same conceptual fact because:

- their field names are similar;
- their file names are conventional;
- their values look alike;
- they occur near one another;
- a model inferred semantic similarity.

\`correspondence.state\` is one of:

- \`declared\` — the provider declares the supplied members comparable in this group;
- \`ambiguous\` — correspondence is not unique;
- \`unresolved\` — correspondence cannot currently be established.

Ambiguous or unresolved correspondence never becomes equivalence or disagreement in core.

## Values and comparison

Each declaration has:

- a stable request-local \`declaration_id\`;
- exact repository \`evidence\`;
- non-empty opaque producer provenance;
- \`value_state = resolved | ambiguous | unresolved\`;
- a normalized \`value\` or bounded \`candidate_values\` when applicable.

An ambiguous declaration requires at least two **distinct** normalized candidate values. Candidate alternatives are canonically ordered, so presentation order cannot change declaration observation identity.

For uniquely declared correspondence:

- any declaration whose exact repository evidence is not \`known-present\` => \`ambiguous\`;
- fewer than two evidence-qualified resolved declarations => \`comparison.state = insufficient\`;
- all normalized values equal => \`equivalent\`;
- two or more normalized values differ => \`differing\`;
- any unresolved/ambiguous provider value => \`ambiguous\`.

Equality is canonical JSON equality over the provider-normalized value. Core does not add version-range, alias, compatibility, language, or organization-specific equivalence rules.

No majority rule exists. Two declarations agreeing and one differing does not make the majority authoritative.

## Exact repository evidence

Every declaration requires at least one exact repository-evidence reference:

~~~json
{
  "path": "pyproject.toml",
  "start_line": 3,
  "end_line": 3
}
~~~

or a whole admitted repository member:

~~~json
{
  "scope": "member",
  "path": "generated/metadata.json"
}
~~~

The existing repository-evidence-binding authority supplies member revisions, span identities, visibility, freshness, and current repository identity.

Each projected declaration also carries an `evidence_state`. A provider may claim a resolved normalized value, but that value participates in equivalence/difference only when **all cited exact evidence is `known-present`**. Known-absent, unsupported, or otherwise unqualified repository evidence makes the group comparison ambiguous rather than allowing a stale provider claim to manufacture equivalence or disagreement.

A provider value is therefore bound to exact current repository evidence without pretending that core independently parsed or certified the provider's semantic interpretation.

## Absence requires coverage

Failure to discover a declaration is not authoritative absence.

A group may provide:

- \`coverage.state = complete | incomplete | unknown\`;
- \`coverage.truncation = complete | truncated | unknown\`;
- explicit \`expected_declaration_ids\`;
- coverage scope and provenance.

Only \`complete + complete\` coverage can turn an unseen expected declaration into:

~~~text
absence.state = known-absent
~~~

When every explicitly expected declaration is observed with current evidence, the state is \`known-present\`. The result also exposes any current \`unexpected_declaration_ids\` when explicit expected membership was declared, without deciding whether those extra declarations are erroneous. Incomplete or truncated coverage reports \`unknown\` and preserves unseen expected IDs separately. If no expected membership is declared, absence is also \`unknown\` rather than inventing an expectation.

Hashmarks does not invent expectations such as "every deployment must contain file X." Expected declaration membership is provider evidence.

## Distributed declarations

File boundaries are not semantic boundaries.

One declaration group may bind declarations from:

- several files;
- several repository areas;
- different producer formats;
- several ranges in the same physical file.

Conversely, multiple declarations in one file are not automatically the same conceptual fact.

A physical source may support several semantic declarations without acquiring several physical identities. Exact evidence remains owned by canonical repository evidence.

## Identity and delta

The contract separates **semantic subject**, optional **semantic declaration role**, exact **declaration definition**, and **observation** identity.

`semantic_subject_identity` identifies the declared conceptual subject from `semantic_namespace + concept + scope`. It deliberately does **not** bind `group_id`, declaration membership, file path, line/range location, normalized value, coverage, or current repository evidence. Therefore the same namespaced subject keeps the same subject identity when a declaration moves or when a caller uses a different request-local group label. A namespace, scope, or concept change produces a different subject identity.

The namespace is identity scoping, not ontology. Two independent providers that emit byte-for-byte equal opaque concept/scope objects still receive different subject identities because discovery binds each group to its own provider namespace. A provider cannot spoof another discovery namespace.

A semantic namespace names a semantic contract, not a provider build. Provider implementation/provenance/version may change without changing subject identity when the provider is still making the same namespaced concept/scope claim. If an integration changes what that claim means, it must change the namespace, concept, or scope rather than silently reusing the old subject identity.

A declaration may optionally supply a non-empty opaque `semantic_role` object. When present, Hashmarks derives `semantic_declaration_identity` from the already-issued `semantic_subject_identity + semantic_role`. The role is provider vocabulary scoped inside that subject; it is not a global role taxonomy. Request-local `declaration_id`, value, producer metadata, repository path/range, and evidence state do not define this semantic declaration identity. When no role is supplied, Hashmarks deliberately creates no child semantic identity.

These identities are correlation evidence, not ontology authority. Hashmarks does not interpret the opaque concept or semantic role, infer correspondence or child roles, select a winner, or promote either identity into a universal metadata schema. Every projected declaration carries its group's `semantic_subject_identity`; declarations with an explicit role additionally carry `semantic_declaration_identity`, so consumers can correlate provider-declared roles separately from exact declaration provenance.

Deterministic semantic identity is also **not an existence timeline**. A role-tagged declaration may be present in one explicit observation, absent in the next because complete coverage proves its request-local declaration missing, and later reappear with the same `semantic_declaration_identity` when the provider emits the same role again. That later identity match does not fill the gap between endpoints or prove the declaration continuously existed. Hashmarks stores no tombstone or resurrection record and does not search repository history to connect the endpoints. The current endpoint's absence remains owned by provider coverage; its exact evidence remains owned by repository-evidence bindings; any older packet used for comparison is caller-supplied bounded evidence.

The remaining identities keep their existing, narrower jobs:

\`group_definition_identity\` binds:

- group ID;
- \`semantic_subject_identity\` (which already binds semantic namespace, opaque concept, and semantic scope);
- coverage scope and expected declaration membership;
- the declaration definition identities in the group.

\`group_observation_identity\` additionally binds:

- correspondence state/basis;
- coverage/provenance;
- declarations and normalized values;
- exact repository-evidence observations;
- comparison and absence result.

Each declaration likewise has definition and observation identities. A declaration definition binds the group ID, the already-issued \`semantic_subject_identity\`, its optional derived \`semantic_declaration_identity\`, its request-local declaration ID, and the existing repository-evidence binding definition. Moving a declaration to a different file/range therefore cannot masquerade as the same exact declaration definition, even when an explicit semantic role proves that the conceptual child remains the same. Subject and role canonicalization still have one owner inside the declaration domain.

A previous packet is revalidated before delta. Mutation under an old identity is rejected.

The factual delta reports:

- added/removed groups;
- whether the provider-declared semantic subject changed for a stable group ID (`semantic_subject_changed`);
- a `semantic_subjects` projection that correlates unique namespaced subjects even when request-local group IDs change;
- optional nested `semantic_declarations` correlation for declarations that explicitly provide a semantic role, including request-local declaration-label change plus value/producer/evidence-qualification transitions;
- added/removed semantic subjects or semantic declaration roles and explicit ambiguity when one identity maps to multiple candidates at either endpoint;
- added/removed declarations;
- declaration/group definition changes;
- normalized value changes;
- observation/provenance changes;
- correspondence changes;
- coverage changes;
- comparison/absence changes.

Exact repository/observer change is not reimplemented here. Declaration delta
composes the existing repository-evidence-binding delta authority, which keeps
repository evidence and observer-capability change distinct.

A delta does not say whether any change is correct or desirable.

Subject-level delta is intentionally conservative. It correlates endpoints only when one `semantic_subject_identity` maps to exactly one group in both observations. Duplicate subject groups produce `semantic_subjects.ambiguous` with the competing group IDs; Hashmarks does not pick one by order, similarity, declaration count, or value. A request-local `group_id` change therefore does **not** authorize pairing ordinary request-local `declaration_id` values. Child correlation across group/declaration-label changes exists only for declarations whose producer explicitly supplied `semantic_role`; the derived `semantic_declaration_identity` must itself be unique at both endpoints. Duplicate roles remain `semantic_declarations.ambiguous`, and untagged declarations remain unpaired. A role change is removal plus addition, never an inferred rename. Group-level comparison/absence/correspondence/coverage transitions may still be compared for a uniquely identified subject. Semantic-role correlation does not strengthen coverage or negative evidence: `coverage.expected_declaration_ids` remains the provider's request-local absence authority. Exact member/span/locator change remains owned by the nested repository-evidence binding delta.

A subject identity is intentionally **not** a branch, commit, ref, snapshot lineage, or retained history node. Hashmarks compares caller-supplied/current observations; Git and the caller remain the owners of repository history and mutation.

### Authority-transition separation

Declaration change reporting keeps definition, observation, repository evidence, and provider interpretation separate:

- moving otherwise equivalent declaration evidence to a different repository file or range changes the declaration/binding **definition** because the exact evidence locator is part of authority; it does not manufacture a normalized-value change;
- deleting or restoring evidence at the same declared locator preserves the declaration definition while changing its **observation**, evidence qualification, comparison, and—when complete coverage authorizes it—absence result;
- changing declaration producer provenance with the same normalized value and exact evidence changes declaration **observation** only; it does not change semantic definition or repository evidence;
- changing correspondence state/basis or its provenance changes the **group observation** and is reported through `correspondence_changed`; correspondence provenance is not smuggled into declaration values or repository evidence;
- canonical repository-evidence binding delta remains the owner of member/span/locator transitions underneath these declaration-level facts.

These axes are intentionally independent. A source move, source disappearance, provider version change, or correspondence-basis change must not be collapsed into a generic semantic-value change merely because the group observation identity changed.

## Derivation authority and explanation

`CodeMap.repository_declaration_derivation_authority(observation)` is a pure
read-only projection over one already-qualified declaration packet. It returns
schema `hashmarks.repository-declaration-derivation.v1` and reuses, rather than
redefines:

- the packet observation identity;
- group and declaration definition/observation identities plus optional semantic declaration-role identity;
- exact repository-evidence binding definition/observation identities;
- the canonical repository-evidence binding packet identity;
- provider provenance and evidence qualification state;
- repository and observer authority already present in the declaration packet.

The derivation projection includes exact bound repository evidence for each
declaration so a consumer can trace a declaration observation back to the member
or span evidence that supported it. Its deterministic `derivation_identity`
binds that existing authority graph; it does not create a new repository
generation, declaration identity family, evidence store, or provenance graph.

`CodeMap.repository_declaration_explain(observation)` returns schema
`hashmarks.repository-declaration-explain.v1`. It provides a compact semantic
summary of group comparison/absence outcomes and declaration counts together
with the full declaration derivation projection.

Both operations are endpoint-local. They validate the supplied packet and its
nested declaration/group/binding identities without requiring the packet to
match current repository state. A caller may therefore retain an explicit
observation during a bounded agent work window and explain it after the live
repository advances. Hashmarks does not search Git, reconstruct old repository
state, or retain a historical timeline.

### Why this remains typed

Dependency evidence and repository declarations now both prove the same general
architectural pattern:

```text
explicit observation
  -> domain definition/observation identities
  -> exact supporting evidence authority
  -> deterministic derivation projection
  -> pure explanation
```

The domain semantics are materially different. Dependency derivation has adapter
semantic contracts and external physical-source authorities. Declaration
derivation has provider-claimed semantic values/correspondence plus canonical
repository-evidence bindings. Hashmarks therefore does **not** introduce a
universal provenance schema or require declaration providers to manufacture
dependency concepts such as `adapter_semantics`.

The shared rule is architectural rather than polymorphic:

> **Derived results must be traceable to their existing domain authority without
> erasing or inventing domain semantics.**

## Python API

~~~python
from hashmarks import CodeMap

groups = [
    {
        "group_id": "python-runtime",
        "semantic_namespace": "example-runtime-provider",
        "concept": {"kind": "runtime-compatibility", "identity": "python"},
        "scope": {"environment": "application"},
        "correspondence": {
            "state": "declared",
            "basis": {"provider": "example"},
        },
        "declarations": [
            {
                "declaration_id": "project-intent",
                "semantic_role": {"kind": "project-intent"},
                "value_state": "resolved",
                "value": ">=3.12",
                "producer": {"kind": "example-project-metadata"},
                "evidence": [
                    {
                        "path": "pyproject.toml",
                        "start_line": 3,
                        "end_line": 3,
                    }
                ],
            },
            {
                "declaration_id": "container-runtime",
                "semantic_role": {"kind": "container-runtime"},
                "value_state": "resolved",
                "value": "3.11",
                "producer": {"kind": "example-container-config"},
                "evidence": [
                    {
                        "path": "Dockerfile",
                        "start_line": 1,
                        "end_line": 1,
                    }
                ],
            },
        ],
        "coverage": {
            "state": "complete",
            "truncation": "complete",
            "expected_declaration_ids": [
                "project-intent",
                "container-runtime",
            ],
            "scope": {},
            "provenance": {"provider": "example"},
        },
    }
]

with CodeMap(".") as codemap:
    codemap.sync()
    packet = codemap.repository_declarations(groups)
~~~

The same request-scoped primitive is exposed by the read-only MCP \`repository_declarations\` tool.

The MCP tool keeps \`result_mode="observation"\` as the default, returning the existing \`hashmarks.repository-declarations.v1\` packet. Opt-in \`result_mode="explain"\` returns \`hashmarks.repository-declaration-explain.v1\` by delegating to the typed declaration explanation owner. \`previous_observation\` remains valid only with observation mode, preserving the existing declaration-delta contract. MCP does not promote declaration compare beyond the repository-evidence binding authority that currently governs it, and it retains no historical declaration timeline.

## Explicit provider discovery

Hashmarks also exposes a Python-side provider SPI for integrations that need to
**discover** declaration groups rather than construct them directly:

~~~python
from hashmarks import (
    CodeMap,
    RepositoryDeclarationProviderContext,
    RepositoryDeclarationProviderResult,
)


class MyProvider:
    name = "my-repository-metadata"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return context.exists("metadata.example")

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        text = context.read_text("metadata.example")
        groups = tuple(normalize_my_format(text))
        return RepositoryDeclarationProviderResult(
            groups=groups,
            provenance={"provider": self.name, "version": "1"},
        )


with CodeMap(".") as codemap:
    codemap.sync()
    packet = codemap.discover_repository_declarations([MyProvider()])
~~~

Discovery is deliberately **explicit composition**, not ambient plugin loading.
Hashmarks does not scan Python entry points, import arbitrary repository code, or
guess providers from similar filenames or keys. Callers select the provider
objects that are allowed to run.

The provider SPI is a **trusted in-process extension boundary**, not a sandbox.
The provider contract is read-only and Hashmarks itself performs no repository
mutation, but arbitrary Python provider code is not sandboxed. Callers are
responsible for selecting providers they trust. The discovery packet reports
this distinction explicitly instead of treating provider purity as mechanically
proven.

Provider semantic inputs are freshness-bound through
`RepositoryDeclarationProviderContext`. Declaration evidence paths must have
been consumed through `read_bytes` / `read_text`; Hashmarks records the exact
member revisions observed by the provider and revalidates those inputs across
declaration qualification. If a provider input changes during discovery, the
call fails closed instead of pairing a stale normalized value with newer
repository evidence.

Dynamic file discovery uses `context.paths(prefix)`, which enumerates admitted
repository files through the same policy/pruning/symlink-safe discovery owner
used by CodeMap indexing, **without requiring the file format itself to be
indexable by CodeMap**. The public provider context does **not** expose the raw
repository filesystem path. Enumeration queries and their exact result sets are
recorded in provider observation state and revalidated around declaration
qualification, so a completeness decision cannot quietly depend on an
untracked directory snapshot. Enumeration is fail-closed and bounded: at most
32 distinct prefix queries and 256 distinct enumerated paths per provider.

Provider discovery has separate wrapper schemas:

- \`hashmarks.repository-declaration-discovery.v1\`
- \`hashmarks.repository-declaration-discovery-delta.v1\`

The wrapper records deterministic provider observation state and provenance, then
contains the ordinary \`hashmarks.repository-declarations.v1\` packet. This keeps
provider execution/discovery provenance separate from declaration semantics and
canonical repository evidence.

For collected groups, discovery also binds \`semantic_namespace\` to the selected provider's registered \`name\`. Provider-returned groups must not supply or override that field. This prevents two independent providers with coincidentally equal opaque \`concept + scope\` objects from collapsing into one semantic subject. If cross-provider semantic correspondence is desired, it must be modeled explicitly by a provider/integration that owns that correspondence rather than inferred by core.

Providers may optionally emit declaration-level `semantic_role` objects inside those groups. Discovery passes them through the same canonical declaration contract; it does not invent, normalize, alias, require, or separately index roles. The derived `semantic_declaration_identity` therefore remains scoped by the provider-bound semantic subject and is independent of provider wrapper provenance/version, request-local group/declaration labels, and exact evidence location. If a provider changes what one of its opaque roles means, it must change the role object and accept removal-plus-addition semantics rather than hiding the change behind an alias or migration table.

Role correlation does not promote semantic identity into repository-evidence binding identity. If a provider changes request-local group/declaration labels, the generated binding IDs may also change; canonical repository-evidence delta then reports those bindings conservatively as removed and added rather than guessing continuity from semantic roles. The caller already holds the explicit endpoint packets and can follow each role-tagged declaration to its endpoint-local `binding_id` and exact evidence. Discovery does not add a cross-binding alias, move heuristic, or second locator-delta owner.

Provider states have narrow meaning:

- \`collected\` means the explicitly selected provider detected the workspace and
  returned claims that passed the provider-envelope checks;
- \`not-detected\` means that provider did not apply to this workspace.

\`not-detected\` is **not** proof that a conceptual declaration is absent. Only
the nested declaration coverage contract can establish negative evidence.

A detected provider exception fails the whole discovery call. Hashmarks does not
return a partial discovery packet that could make missing provider output look
like semantic absence.

Provider warnings are observable discovery provenance. If a warning undermines
the provider's ability to enumerate a declaration group, the provider must
downgrade that group's \`coverage.state\` / \`coverage.truncation\`; warnings do
not give Hashmarks permission to invent completeness.

### Provider-transition separation

Discovery transitions keep wrapper execution evidence separate from nested declaration authority:

- `not-detected -> collected` and `collected -> not-detected` are provider-state transitions; they add or remove the provider's nested declaration groups, but `not-detected` itself never becomes a semantic absence claim;
- changing only provider warnings/provenance changes the discovery wrapper observation while leaving the nested declaration packet unchanged;
- when a warning genuinely means enumeration is incomplete, the provider must explicitly downgrade declaration coverage; the nested declaration delta then owns the resulting coverage/absence change;
- moving a provider-selected source path changes provider inputs/enumerations and the nested declaration/binding definition, while an unchanged normalized value remains an unchanged value;
- provider helper-input or enumeration changes that do not change qualified declarations remain wrapper-only observation changes.

Hashmarks therefore does not infer declaration semantics from provider lifecycle, warning text, helper-input churn, or path-enumeration churn. Providers express semantic consequences through ordinary declaration groups, exact evidence, and coverage claims.

Provider order is canonicalized, provider names must be unique, provider
metadata is bounded, and each provider may content/existence-observe at most
**256 distinct repository input paths** through the Hashmarks context. Path
enumeration is separately bounded to **32 prefix queries** and **256 distinct
enumerated paths**. The whole discovery packet is also bounded. Provider
provenance/input/enumeration changes are reported separately from nested
declaration/repository change.

The MCP server does **not** execute arbitrary Python declaration providers.
External producer adapters may run in their own integration boundary and pass
normalized groups to the existing read-only \`repository_declarations\` MCP tool.
This preserves the MCP execution boundary while reusing the same qualification
contract.

Direct declaration requests and packets remain bounded to **1 MiB encoded JSON**.
Discovery wrappers are separately bounded and fail closed; Hashmarks never
silently truncates a declaration set into stronger evidence.

## Non-goals

This contract does not:

- define a Backstage, Helm, service-catalog, or organization-specific model;
- search for conventions merely because a named integration uses them;
- choose an authoritative declaration;
- encode source-of-truth precedence;
- generate missing metadata;
- translate descriptions;
- repair files;
- infer semantic correspondence or semantic declaration roles with an LLM;
- ambiently discover/load Python provider plugins;
- execute arbitrary declaration providers inside MCP;
- use majority voting;
- claim absence without qualified coverage;
- expand repository analysis into external dependency source.

Producer integrations should be admitted only when they expose a reusable repository-intelligence primitive or translate their native syntax into this producer-neutral contract.
