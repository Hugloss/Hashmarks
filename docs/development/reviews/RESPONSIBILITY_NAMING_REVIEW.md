# Responsibility and naming review

**Status:** historical naming-phase review. For current ownership of the legacy execution-shaped v0.11 APIs, `AGENTS.md` G53/G59 and `docs/development/PREPUBLIC_BOUNDARY_DEBT.md` are normative and supersede unresolved labels retained from this review.

This review gates size reduction and naming cleanup. LOC is evidence to inspect, never an extraction requirement.

## Product vocabulary

Hashmarks **observes repository intelligence**. It owns evidence, repository impact, repository qualification, evidence packets/receipts/freshness, repository projection, ownership evidence, and consumer conformance.

Oh-Goon **admits source and executes it**. Authority, admission, execution, certification, sandbox, supply, execution generation, authority receipts, release promotion, and Game Tape are Oh-Goon vocabulary unless Hashmarks is describing an external boundary or preserving a historical compatibility contract.

At interoperability boundaries, product names must be explicit. Hashmarks produces evidence; a consumer may validate binding/conformance but Hashmarks does not grant execution permission.

## Naming decisions

| Current surface | Decision | Responsibility | Preferred name | Compatibility rule |
| --- | --- | --- | --- | --- |
| `authority_ownership_graph()` | RENAME INTERNALLY / KEEP ALIAS | Repository ownership evidence composed from imports, caches, invalidation and static concurrency signals | `repository_ownership_graph()` | Keep old method and `hashmarks.authority-ownership-graph.v3` schema on v0.11; new code uses repository-owned name. |
| `scoped_authority()` | RENAME INTERNALLY / KEEP ALIAS | Applicable indexed `AGENTS.md` / `AGENTS.override.md` instruction scope and precedence | `repository_instruction_scope()` | Keep old method and serialized schema/fields on v0.11; new code uses responsibility name. |
| `impact.ExecutionIdentity` | HISTORICAL REVIEW RESOLVED | Fingerprint of executable/toolchain bytes used by the legacy impact-run assessment surface | keep v0.11 compatibility name | Final classification: compatibility-only execution model; do not expand modern CodeMap dependence. See `../PREPUBLIC_BOUNDARY_DEBT.md`. |
| `ActionCache` / `ExecutionCache` / `ActionResult` | HISTORICAL REVIEW RESOLVED | Legacy step-result/CAS reuse used by the older engine surface | keep v0.11 compatibility names | Final classification: compatibility-only historical runtime/result models; preserve and contain on v0.11. See `../PREPUBLIC_BOUNDARY_DEBT.md`. |
| `evidence_verification.py` | KEEP COHESIVE | Repository evidence selection and verification-plan recommendation | retained | `verification` is qualified by `evidence`; it does not claim execution/certification. |
| `evidence_packet.py` | KEEP COHESIVE | Agent-facing repository evidence packet construction | retained | Clear Hashmarks ownership vocabulary. |
| `repository_index_store.py` | KEEP COHESIVE / REFACTOR INTERNALLY first | Persistent CodeMap repository index storage | retained | Storage and transaction invariants remain centralized unless a real owner boundary emerges. |

## Large-file responsibility gate

- `cli.py`: **DECOMPOSE MULTIPLE RESPONSIBILITIES** only along stable command-family ownership boundaries; do not create `cli_helpers.py` or numbered CLI fragments.
- `evidence_verification.py`: **REFACTOR INTERNALLY** first. It has one strong repository-verification responsibility; reduce long decision/control-flow methods before splitting.
- `evidence_packet.py`: **KEEP COHESIVE / REFACTOR INTERNALLY**. Packet construction is a meaningful owner; extract only a separately named evidence responsibility.
- `test_shards.py`: **KEEP COHESIVE / REFACTOR INTERNALLY**. Test-shard planning/validation is development qualification tooling, not product execution authority.
- `repository_task_action.py`: **REFACTOR INTERNALLY**. Repository task-action projection is cohesive; reduce complex methods before adding modules.
- `task_retrieval.py`: **REFACTOR INTERNALLY**. Retrieval/ranking is cohesive and must not be fragmented by algorithm step names without an ownership boundary.

## Extraction acceptance checklist

Every extraction must state the responsibility extracted, responsibility-based filename, remaining owner, dependency direction, discoverability improvement, actual complexity reduction, and contracts preserved. Reject splits that add forwarding-only modules, circular dependencies, duplicated state/caches, awkward parameter plumbing, or scatter one invariant.

## Blind-maintainer rule

If a filename, type, or cross-module function could plausibly exist unchanged in both Hashmarks and Oh-Goon, add the domain noun that reveals ownership. Compatibility aliases may preserve old public names, but new internal code must converge on the responsibility-owned vocabulary rather than making both names permanent implementation choices.
