# Hashmarks naming ownership audit — BH

Rule: a name should reveal which product owns the concept even when surrounding code is absent.
Large LOC is a review signal, not extraction proof. Renames below are responsibility changes in navigation only; no serialized schema or semantic identity is rewritten.

## N1/N2 inventory and ownership classification

| Current/legacy surface | Owner | Decision | Responsibility-correct direction |
|---|---|---|---|
| `hashmarks.codemap.verification` | HASHMARKS | rename internal module | `evidence_verification` |
| `hashmarks.codemap.agent_packet` | HASHMARKS | rename internal module | `evidence_packet` |
| `hashmarks.codemap.decision_packet` | HASHMARKS | rename internal module | `evidence_decision_packet` |
| `hashmarks.codemap.context_planning` | HASHMARKS | rename internal module | `repository_context` |
| `hashmarks.codemap.store` | HASHMARKS | rename internal module | `repository_index_store` |
| `hashmarks.codemap.task_action` | HASHMARKS | rename internal module | `repository_task_action` |
| `_decision_authority_receipt` | HASHMARKS | rename internal symbol | `_decision_evidence_receipt` |
| local `authority_receipt` variables/parameters | HASHMARKS | rename internal symbols | `evidence_receipt` |
| root `Identity` / `IdentityMode` | HASHMARKS, public v0.11 | preserve + additive clarity alias | `RepositoryIdentity` / `RepositoryIdentityMode` |
| serialized `authority_receipt` + `hashmarks.decision-authority-receipt.v1` | HASHMARKS, public v0.11 legacy | KEEP COMPATIBILITY | versioned retirement only; do not silently rewrite |
| `promotion_receipt.py` | HASHMARKS legacy promotion evidence | KEEP COMPATIBILITY | historical external-promotion evidence; HM-07 is no longer active semantic direction |
| `recovery.py` / `task_recovery_*` | HASHMARKS public repository-evidence workflow | REVIEW LATER | avoid cosmetic rename until public compatibility/versioning is planned |

## N3 rename map applied

- `verification.py` → `evidence_verification.py`: owns repository evidence selection/verification, not execution verification.
- `agent_packet.py` → `evidence_packet.py`: owns compact repository evidence projections; `packet` is Hashmarks vocabulary.
- `decision_packet.py` → `evidence_decision_packet.py`: owns repository decision evidence assembly.
- `context_planning.py` → `repository_context.py`: owns repository/dependency/context evidence, not runtime execution context.
- `store.py` → `repository_index_store.py`: owns persisted CodeMap/repository-index state and mutation; query responsibility remains separately in `store_queries.py` for now and is a later naming-review candidate.
- `task_action.py` → `repository_task_action.py`: owns repository-derived edit/verification action nomination, not runtime action execution.
- `_decision_authority_receipt` → `_decision_evidence_receipt`: internal ownership terminology corrected while the v0.11 serialized field/schema remains frozen.

## N4 reserved vocabulary

Hashmarks preferred: `evidence`, `repository`, `CodeMap`, `impact`, `repository qualification`, `qualified repository identity`, `evidence packet`, `evidence receipt`, `evidence freshness`, `repository projection`, `consumer conformance`.

Oh-Goon-reserved for new authority semantics: `authority`, `admission`, `execution`, `certification`, `sandbox`, `supply`, `execution generation`, `authority receipt`, `release promotion`, `Game Tape`.

## N5 blind-maintainer review

PASS for the six renamed internal modules: each filename now states evidence/repository responsibility without requiring knowledge of the old `engine.py` decomposition history.

DEFERRED rather than cosmetically changed: stable v0.11 public `Identity`, serialized `authority_receipt`, and public recovery surfaces. These require compatibility/versioning work; silently changing them would violate the contract-preservation rule.

## Responsibility review decisions

- `evidence_verification.py`: **KEEP COHESIVE** for this naming phase. Large, but one repository-verification responsibility; complexity review remains separate.
- `evidence_packet.py`: **KEEP COHESIVE** for this naming phase. Evidence projection responsibility is clear.
- `repository_context.py`: **KEEP COHESIVE**. Repository context/dependency projection is one responsibility.
- `repository_index_store.py`: **REFACTOR INTERNALLY** later if mutation/schema control-flow remains complex; query ownership is already separated.
- `repository_task_action.py`: **REFACTOR INTERNALLY** later around large decision functions; do not split solely for LOC.

No new execution/admission/certification authority was introduced.

## Additional boundary-sensitive legacy names discovered

The inventory also found `ExecutionIdentity`, `ExecutionCache`, `ActionResult`, `ActionCache`, `resolve_execution_identity`, and execution-oriented fields in the older generic impact/identity layer. These are **not** being cosmetically renamed in BH. Their behavior may represent older public contracts, and the naming review cannot truthfully decide whether they should become repository/evidence names or be retired/moved without a responsibility/boundary review of that subsystem. Decision: **REVIEW BOUNDARY BEFORE RENAME**. A blind `Execution*` → `Evidence*` replacement would hide a possible architectural ownership problem rather than fix it.

Likewise, existing CodeMap schemas/fields containing `authority` (`hashmarks.decision-authority*.v1`, `hashmarks.authority-ownership-graph.v3`, scoped-authority payloads) are frozen compatibility surfaces in v0.11. New internal names should use evidence/ownership vocabulary, but schema retirement requires an explicit versioned compatibility plan.
