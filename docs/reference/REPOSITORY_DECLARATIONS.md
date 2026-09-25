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
- the claim that declarations correspond to the same conceptual fact;
- the semantic scope in which they are comparable;
- coverage claims and expected declaration membership.

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

A declaration group has an opaque \`concept\` object and an opaque semantic \`scope\`.

Core does not interpret either object.

For example, a provider may use:

~~~json
{
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

> Producer-specific semantics terminate at the provider boundary. Core operates on declared correspondence, scope, normalized values, evidence, provenance, completeness, freshness, ambiguity, identity, and delta.

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
- opaque producer provenance;
- \`value_state = resolved | ambiguous | unresolved\`;
- a normalized \`value\` or bounded \`candidate_values\` when applicable.

For uniquely declared correspondence:

- fewer than two resolved declarations => \`comparison.state = insufficient\`;
- all normalized values equal => \`equivalent\`;
- two or more normalized values differ => \`differing\`;
- any unresolved/ambiguous value => \`ambiguous\`.

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
absence.state = present
~~~

Otherwise Hashmarks reports:

~~~text
absence.state = unknown
~~~

and preserves the unseen expected IDs separately.

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

The contract separates definition from observation.

\`group_definition_identity\` binds:

- group ID;
- opaque concept;
- semantic scope;
- expected declaration membership.

\`group_observation_identity\` additionally binds:

- correspondence state/basis;
- coverage/provenance;
- declarations and normalized values;
- exact repository-evidence observations;
- comparison and absence result.

Each declaration likewise has definition and observation identities. A
declaration definition also binds the existing repository-evidence binding
definition, so moving a declaration to a different file/range cannot masquerade
as the same declaration definition.

A previous packet is revalidated before delta. Mutation under an old identity is rejected.

The factual delta reports:

- added/removed groups;
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

## Python API

~~~python
from hashmarks import CodeMap

groups = [
    {
        "group_id": "python-runtime",
        "concept": {"kind": "runtime-compatibility", "identity": "python"},
        "scope": {"environment": "application"},
        "correspondence": {
            "state": "declared",
            "basis": {"provider": "example"},
        },
        "declarations": [
            {
                "declaration_id": "project-intent",
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

## Non-goals

This contract does not:

- define a Backstage, Helm, service-catalog, or organization-specific model;
- search for conventions merely because a named integration uses them;
- choose an authoritative declaration;
- encode source-of-truth precedence;
- generate missing metadata;
- translate descriptions;
- repair files;
- infer semantic correspondence with an LLM;
- use majority voting;
- claim absence without qualified coverage;
- expand repository analysis into external dependency source.

Producer integrations should be admitted only when they expose a reusable repository-intelligence primitive or translate their native syntax into this producer-neutral contract.
