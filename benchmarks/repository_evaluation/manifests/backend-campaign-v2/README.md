# Backend campaign successor

This successor preserves the existing 36 pinned catalog entries and their source
labels while their independent oracles and witness membership are completed.
The original campaign and its manifests remain unchanged historical definitions.

The three suite IDs are `backend-core-v2`, `backend-model-v2` and
`backend-async-v2`. Their source IDs still refer to the original exact archives;
materializing a second copy is unnecessary when the content identities match.
Use a suite-specific source map for acquisition and the complete combined source
map for aggregation.

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
