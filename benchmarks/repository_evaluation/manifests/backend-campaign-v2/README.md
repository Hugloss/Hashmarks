# Backend campaign successor

This successor preserves the existing 36 pinned catalog entries and their source
labels while their independent oracles and witness membership are completed.
The original campaign and its manifests remain unchanged historical definitions.

The original three suite IDs are `backend-core-v2`, `backend-model-v2` and
`backend-async-v2`. Their source IDs still refer to the original exact archives;
materializing a second copy is unnecessary when the content identities match.
Use a suite-specific source map for acquisition and the complete combined source
map for aggregation.

`backend-messaging-v2` adds thirteen distinct upstream changes across aiokafka,
aio-pika and FastStream. Its 26 source archives are new nominations, not variants
of the original workflows. See [the messaging source review](suites/messaging/README.md).
`backend-transaction-v2` adds twelve transaction/persistence workflows across
SQLAlchemy, databases and Litestar; one problem overlaps the original corpus.
See [the transaction source review](suites/transaction/README.md).

`backend-language-v2` pairs six existing Python problems with six new TypeScript
problems across Fastify, Hono and NestJS. See
[the language source review](suites/language/README.md). Declaration-only
TypeScript contracts are distinguished from runtime implementations.

The campaign declares 73 entries representing 57 distinct upstream problems
across six suites. Reuse adds no distinct problem. Semantic review, executable
witness membership and observed results still govern qualification.

The model grader now separates `task_source_labels` from native `source_labels`.
Task labels cover production and verification members at both revisions without
silently adding native targets. Validating these bytes does not complete the
independent semantic or capability review.

Aggregation also accepts disjoint `workflow_reports` lists and `native_reports`
lists whose entries contain `native_report` and `capture_root`. Do not mix a list
with the corresponding singular field. Each original report is revalidated;
overlapping workflow outcomes cause a membership rejection rather than precedence.

The directory version identifies this corpus, not the wire schemas. The current
workflow, campaign and matrix schemas remain v2, v4 and v5 respectively.

**No capability is qualified by copying these definitions.** Owner/essential
fact/display review, positive and adversarial capability membership, the missing
catalogs and final qualification remain required. A report must bind the actual
observer/evaluator, these suite/grader digests and all required artifact bytes.

See [the remaining implementation handoff](../../../../docs/qualification/BACKEND_E2E_REMAINING_PLAN.md).
