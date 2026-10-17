# Python filesystem lifecycle evidence

Hashmarks observes filesystem checks and subsequent operations through source
references. It does not establish runtime object identity, namespace exclusivity,
protection sufficiency, exploitability, or execution permission.

## Existing surfaces

```python
from hashmarks import CodeMap, validate_repository_intelligence_evidence

with CodeMap(".") as codemap:
    codemap.index.sync()
    findings = codemap.repository_findings(["src/cleanup.py"])
    observation = findings["resource_lifecycle"]
    checked = validate_repository_intelligence_evidence(observation)
```

`hashmarks map findings`, the CodeMap service, and the existing
`repository_findings` MCP tool carry the same additive `resource_lifecycle`
section. Lifecycle findings have category `resource-lifecycle`, code
`python-filesystem-check-use`, and advisory severity. They have no actionability
or safety verdict. Existing unrelated finding behavior remains unchanged.

`structural_locality` includes lifecycle observations within its selected symbols
and traversal bounds. `task_evidence` includes related lifecycle evidence after a
Python edit owner is resolved; it does not change that owner, candidate ranking,
or verification selection. Its initial projection accounts for omission of the
related section and refers back to the full packet.

The nested schema is
`hashmarks.python-filesystem-lifecycle-observation.v1`. Its types and semantic
validator have one owner. No new MCP tool or execution backend is introduced.

## Packet meaning

The packet retains repository identity, generation, nullable canonical staleness,
producer implementation/rule identity, requested scope, contributing member
revisions, bounds, operations, relationships, unresolved observations, accounting,
and a deterministic observation identity.

Operations retain API identity, source path/symbol/range/column, member revision,
operand role, a source-reference identity, descriptor-relative arguments,
lexical context managers, and qualified call-site forwarding evidence.

A relationship states `same-source-reference`. Its runtime identity remains
`unverified`. It retains conditional failure language, environmental unknowns,
positive namespace-mutator evidence, and structurally relevant verification
paths. Relevant tests do not establish coverage, test execution, or sufficiency.

References are local symbolic source bindings. Equal references do not assert
equal inodes, stable directory entries, live descriptors, or exclusive ownership.
Distinct helper/factory invocations retain separate call-site identity.

The observation identity binds the complete packet, including qualifications and
omissions. It is not a signature authenticating an external producer. Consumer
validation checks the schema and internal evidence contract; the consuming system
still owns trust and admission of a producer/artifact/repository binding.

## Supported source evidence

The initial producer recognizes qualified `os.stat`, `lstat`, `fstat`, selected
`os.path` checks, `rmdir`, `unlink`/`remove`, `rename`/`replace`, and selected
namespace mutators. It also recognizes selected methods on a statically tracked
`pathlib.Path` construction. Imports, `as` aliases, relative repository helpers,
and explicit re-export bindings use canonical CodeMap resolution. Re-export
qualification stops after eight hops.

Simple operand assignments and supported parameter/return forwarding preserve
source references. A resolved call target alone never establishes argument flow.
The producer checks supported signatures and keeps dynamic, decorated, variadic,
cyclic, asynchronous, and ambiguous forwarding unresolved. It never imports the
target repository or recursively inspects dependency implementations.

Straight-line statements, separate `if` branches, and lexical context-manager
extent are observed. Unsupported exception/loop/short-circuit shapes are
qualified; operation locations may remain available without an invented
check/use sequence across them. This is not complete Python execution or heap
analysis, and the producer does not prove execution feasibility.

Source-visible API rebinding and lexical shadowing withhold qualified API
observations. Production modules are not excluded merely because their basename
resembles a test.

## Descriptor and namespace qualifications

Supplying `dir_fd` does not prove a stable child binding or descriptor lifetime.
For an unresolved path expression the packet reports conditional relative-path
interpretation. An absolute POSIX path ignores the directory descriptor. A
relative path can contain additional components or `..`; its classification does
not establish a single protected child name or confinement.

The packet distinguishes `fstat` descriptor inspection, `stat`'s path/descriptor
operand capability, and name/path selection by later operations. Rename source
and destination operands remain separate.

All context-manager evidence is `lexical-context-only`. A lock enclosing the
operations does not suppress the candidate or establish protection from another
process. Runtime namespace ownership and protection remain unverified.

## Completeness, freshness, and visibility

`complete-within-supported-scope` describes only the supported static observation
scope. It never means complete concurrency analysis or absence of risk.
`negative_evidence_admissible` is always false. Empty results, limited traversal,
unsupported syntax, parse/read failures, and omitted candidates cannot establish
absence of a check, mutator, protection, or relevant test.

Files are admitted through existing repository policy. AST snapshots come from
`read_python_ast` and must match canonical repository-member bytes. Cache metadata
is acceleration/drift detection only; it does not supply source identity.
Contributing files are checked again for drift before packet completion. Stale
or unqualified material never becomes current through presentation or correlation.
Denied supporting implementations are not followed or disclosed in diagnostics.

Defaults are eight call hops, 64 calls per symbol, 256 reference candidates,
256 distinct symbols per anchor, 10,000 discovery paths, and 256 returned
relationships. Structural-locality projections additionally respect their own
selected graph and bounds. Exhaustion is explicit; result projection occurs
after qualification. Supporting and requested paths have distinct accounting.
The call budget accumulates across repeated helper contexts within each anchor;
entering the same helper again does not replenish its budget.

Observation state is request-local. Reopening CodeMap reconstructs current
evidence from current admitted source. No lifecycle graph, safety policy,
historical packet hydration, or runtime progress store is maintained.

## External native evidence

Use `correlate_evidence` with an external observation's exact path/range and
`member_revision` or `span_identity`. Matching source identity proves source
correspondence only. Runtime outcome and environmental conditions remain external
claims; Hashmarks does not infer causation or certify protection.

The deterministic native regression coordinates a separate process after its
check, replaces the child entry, releases deletion, and distinguishes the
original from the replacement. The test harness owns execution, synchronization,
deadlock protection, cleanup, and result assertions. The source observation and
external behavioral result are independently qualified.

## Ownership note

```text
Observed repository fact/evidence:
Python filesystem operations, source references, bounded forwarding,
lexical protection constructs, and positive verification/mutator evidence.
Authority source:
Current admitted bytes, canonical CodeMap relationships and source revisions.
Completeness/freshness behavior:
Explicit supported scope, source equivalence, uncertainty and bound accounting.
Existing Hashmarks owner extended:
CodeMap ownership/concurrency composition and existing evidence surfaces.
Consumer/execution responsibility explicitly not acquired:
Safety sufficiency, exploitability, investigation strategy, execution,
remediation, admission and certification.
Decision: SPLIT
```
