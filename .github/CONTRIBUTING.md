# Contributing to Hashmarks

Thank you for improving Hashmarks. The most important contributor rule is that **product ownership is decided before implementation**.

## Before proposing a feature

Read [`docs/reference/PRODUCT_BOUNDARY.md`](../docs/reference/PRODUCT_BOUNDARY.md).

Every new capability must be classified before coding as one of:

- an in-profile repository-intelligence defect;
- an in-profile optimization;
- a missing repository-intelligence primitive;
- consumer/runtime behavior that belongs outside Hashmarks;
- existing boundary debt to contain/remove;
- measurement-only infrastructure.

A useful idea is not automatically a Hashmarks feature. Hashmarks must not become the coding agent's solution loop or an Oh-Goon-style execution/certification engine.

### Evidence authority precedence

New providers and projections must preserve the non-strengthening rule: a derived/cached/presentation layer cannot make its source evidence fresher, more proven, or less ambiguous than the qualified repository evidence supports. There is no universal confidence score; use the existing evidence-kind authority and preserve unknown/ambiguity when it does not uniquely resolve the claim.

### External-library scope

**Do not chase remaining findings in external libraries.** The default analysis boundary is the admitted repository-owned material. Imports and dependency metadata may be represented as repository evidence, but they do not authorize recursive inspection of dependency implementations. Do not investigate `site-packages`, `node_modules`, virtual environments, package-manager caches, SDK/runtime trees, or unrelated dependency checkouts merely because the repository references them.

An external library may be used as a bounded development/qualification corpus to expose a generic Hashmarks defect. If that happens, reduce the issue to neutral repository semantics and regression coverage. Do not add library-name suppressions, do not keep studying the named package to make counts smaller, and do not turn historical external-library findings into backlog items. If no generic repository-intelligence defect is demonstrated, record **NO_CHANGE**.

For a genuinely new product capability, document:

```text
Product purpose:
Repository source of authority:
Neutral inputs:
New persistent/cached state:
Semantic cold/reconciled oracle:
Why Hashmarks is the correct owner:
What remains owned by the consumer/execution layer:
Why existing repository-intelligence primitives are insufficient:
Repository analysis scope (repository-owned only; explain any explicit exception):
Boundary decision: ADMIT / SPLIT / REJECT
```

## Development setup

```bash
make init
```

Run the normal bounded development check:

```bash
make dev-check
```

Useful targeted checks:

```bash
make compile
make test
make test-shard-plan
make test-shard TEST_SHARD=0
```

For native full-suite qualification:

```bash
make test-profile
```

Restricted CI/container hosts may run capability-aware diagnostics without weakening native qualification:

```bash
HASHMARKS_CONSTRAINED_HOST=1 make test
make test-diagnostic-batch DIAGNOSTIC_BATCH=0 DIAGNOSTIC_BATCH_LIMIT=8
```

Hosted diagnostics never mutate the native release contract. They exclude external-DNS, certification, slow, and scale markers; skip only explicitly unavailable capabilities such as the optional MCP SDK, installed console script, or Git executable; disable unrelated host pytest-plugin autoload; and fail on every runnable test failure. `HOSTED-DIAGNOSTIC-PASSED` is diagnostic evidence only, never promotion authority.

## Testing principles

- Prefer production-shaped tests over mocks when authority/freshness semantics are under test.
- Keep tests isolated from the developer's persistent cache unless shared-cache behavior is the contract being tested.
- Incremental/cached behavior should be compared against a fresh reconciled/cold oracle for semantic authority.
- Unknown or incomplete evidence should fail closed rather than being coerced into stronger authority.
- Benchmarks measure behavior; they do not automatically authorize product expansion.

## Documentation

Current/normative documentation lives under `docs/reference/`, `docs/integration/`, and `docs/qualification/`. Historical phase evidence belongs under `docs/development/` and must not become current product authority.

If a change alters a public contract, update the relevant normative documentation and its invariant tests in the same change.

## Pull requests

A focused pull request should explain:

1. the problem and why it belongs in Hashmarks;
2. the authority/invariant affected;
3. the smallest implementation that fixes it;
4. the tests or measurements that prove the change;
5. any compatibility or migration impact.

Avoid unrelated refactors in the same change unless they are required to make ownership clearer.

## Qualification-tool compatibility

The compatibility envelope for pytest and Ruff is documented in [`docs/qualification/TOOL_COMPATIBILITY.md`](../docs/qualification/TOOL_COMPATIBILITY.md). Widening a range requires boundary-version proof; it must not be done as an incidental dependency update.
