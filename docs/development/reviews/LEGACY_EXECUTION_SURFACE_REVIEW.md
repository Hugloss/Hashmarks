# Legacy execution surface responsibility review

## Decision

**KEEP AS VERSIONED COMPATIBILITY / DO NOT EXPAND.**

The historical `IdentityEngine`, `ActionCache`, `ActionResult`, `ExecutionCache`, `ExecutionIdentity`, and `resolve_execution_identity` APIs are not simply poorly named repository-evidence concepts. Inspection shows that they fingerprint executable/interpreter bytes, retain resolved PATH state, persist step exit/stdout/stderr/output results, compose those results with CAS blobs, and expose an engine-level execution cache. Renaming these surfaces to `Evidence*` would make ownership less truthful, not more truthful.

They predate the current Hashmarks product boundary. Hashmarks' modern CodeMap implementation owns repository evidence and verification selection; Oh-Goon owns admission, physical execution, runtime authority, retry/resume, and certification.

## Responsibility classification

| Surface | Classification | Why |
| --- | --- | --- |
| `ActionResult` | KEEP COMPATIBILITY | Represents exit/stdout/stderr/output result data, not repository evidence. |
| `ActionCache` | KEEP COMPATIBILITY | Persists `StepIdentity -> ActionResult`; real runtime-result reuse. |
| `ExecutionCache` | KEEP COMPATIBILITY | Composes action results with CAS and validates referenced blobs. |
| `ExecutionIdentity` | KEEP COMPATIBILITY | Fingerprints selected executable/interpreter/PATH state. |
| `resolve_execution_identity()` | KEEP COMPATIBILITY | Resolves executable authority from command/environment. |
| `IdentityEngine.execution_cache` | KEEP COMPATIBILITY | Exposes the historical runtime-result cache through the legacy facade. |

## Boundary rule

1. Do not cosmetically rename these to repository/evidence terminology.
2. Do not add new CodeMap or repository-intelligence dependencies on them.
3. Do not add scheduling, process launch, timeout, retry, resume, sandbox, admission, or certification behavior here.
4. Preserve v0.11 public imports and behavior until an explicit versioned retirement decision.
5. A future incompatible release may either remove these APIs or isolate them in an explicitly legacy compatibility package, but that is a product/API decision rather than naming cleanup.

## Blind-maintainer result

The word `execution` is useful here because it exposes the historical boundary mismatch. Hiding it would make blind maintenance more dangerous. The correct present-day discoverability improvement is to mark the subsystem as compatibility-only and prevent modern repository-intelligence code from depending on it.
