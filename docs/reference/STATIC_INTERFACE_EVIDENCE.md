# Explicit Python interface syntax evidence

The read-only `StaticPythonInterfaceDeclarations` provider is a narrowly scoped
example of borrowing GitNexus's API-route and tool-map **facts** without taking
ownership of a process graph, a framework runtime or agent tool selection.

It does **not** alter the 14-tool MCP catalog or run automatically. It is an
explicitly selected trusted provider for Hashmarks' existing
`CodeMap.discover_repository_declarations` operation.

```python
from hashmarks import CodeMap
from hashmarks.codemap.static_python_interface_declarations import (
    StaticPythonInterfaceDeclarations,
)

provider = StaticPythonInterfaceDeclarations(
    paths=("src/api.py", "src/mcp_tools.py"),
    route_objects=("app", "router"),
    tool_objects=("mcp",),
)
with CodeMap(".") as codemap:
    codemap.sync()
    observation = codemap.discover_repository_declarations([provider])
```

## Exactly what is observed

The producer parses **only explicitly selected, admitted Python source files**.
It recognizes top-level function and async-function decorators with a statically
named receiver: `@app.get("/path")`, `@router.post("/path")`,
`@mcp.tool(name="tool_name")`, and related supported static forms.
Only a literal route string or a literal explicit tool-name argument is
recorded as such. A dynamic argument remains
`argument_state=dynamic-or-unsupported`. A bare tool decorator has
`argument_state=not-supplied`; no default name is inferred.
Keyword expansion (`**options`) and unsupported positional tool arguments also
remain dynamic/unsupported when no supported explicit argument is observable.
An explicit literal beside an expansion describes that syntax only, not the
framework's eventual argument binding or registration.

Each observation carries its exact source span, canonical bound member
revision via existing repository evidence bindings, directly observed
handler syntax, a provider-owned normalized value, semantic subject/role
identities, and consumer-owned interpretation.

**Syntax is not runtime registration.** The provider cannot prove that the
decorated function was called, that `app` is a particular framework object,
that the route or tool was registered, that its consumer exists, or that a
handler is reachable. Consequently:
- `correspondence.state=unresolved`;
- `coverage.state=incomplete`;
- `absence.state=unknown` unless independent existing authority qualifies it;
- no risk, repair, missing-handler, broken-shape or execution conclusion is made.

Provider discovery is bounded to 32 explicit paths, 128 groups, and 262,144
source characters per selected file, all admitted/read through the existing
repository declaration provider context. Unselected modules, nested or dynamic
registration, imported framework aliases, class methods, synthesized/parametric
routes and unsupported decorators are **not** negative findings. A missing
selected member does not establish missing routes. An invalid AST or provider
violation fails before publishing an authoritative declaration observation.

The core does not need to understand API routing or MCP tools; `concept` and
`scope` remain provider namespaced and opaque. This provider must not become
an ambiently loaded plugin, a second parser/index generation, or an MCP
execution surface.

## Opt-in backend handler inputs (B15–B19)

`StaticPythonInterfaceDeclarations(paths=(...), include_input_contract_syntax=True)`
now attaches `static_input_syntax` to the same selected, directly observed
top-level decorated functions. This opt-in is independent of
`include_literal_shape_syntax`; the default packet is unchanged.
The same **one** `handler_input_syntax` AST owner is used by
`change_impact(changed_line_spans=...)` in its already revision-bound,
uniquely indexed Python decorator associations as `handler_input_context`.

- **B15:** record up to 16 parameters in signature order with explicit
  positional-only, positional-or-keyword, variadic-positional, keyword-only
  and variadic-keyword kinds, individual source coordinates and a qualified
  signature source range. Additional parameters fail the selected provider
  before publication; a changed-line request locally reports unresolved
  rather than a fabricated empty signature.
- **B16:** retain bounded `ast.unparse` annotation *syntax* (maximum 192
  characters), an independently bounded return annotation, and explicit
  `not-supplied`, `over-bound` or `dynamic-or-unsupported` states.
  Neither a `Payload` annotation nor a `dict[str, int]` return annotation
  proves Pydantic validation or the actual runtime response shape.
- **B17:** distinguish absent defaults, literal **types without literal
  values**, and direct call syntax such as `Depends(auth)`,
  `Query(1, ge=0)`, `Header(default=None)`, or `Field(...)`.
  The call's direct callee/first argument name, counts, up to eight keyword
  *names* and expansion uncertainty remain syntax facts only. No default
  expression is executed, and literal default values are not transmitted.
- **B18:** `Annotated[Type, Depends(...)]` metadata captures at most four
  direct source expressions and explicit omission counts. Calling a
  function `Depends` is not proof that the framework bound it to a
  dependency, nor that the dependency is registered, reachable or invoked.
- **B19:** declaration provider and changed-line transport are parity-tested
  against the same syntax owner. Cross-file producer/consumer schema matching,
  runtime request validation, dependency resolution and **negative
  evidence** remain respectively `unresolved`, `unknown`,
  `not-established` and `false`.

Source admission, source visibility and the existing second stable revision
read remain mandatory. An outline/denied file never discloses argument,
annotation, or default-call text. The selected provider is still only a
request-local source observer: no framework plugin, source scanner, global
type graph, dependency-injection engine, new MCP tool or durable state.

## Explicit selected-file Python model and environment syntax (B20–B24)

`StaticPythonBackendDeclarations(paths=("src/models.py", "src/settings.py"))`
is a separate **explicitly selected** provider for the existing
`CodeMap.discover_repository_declarations([provider])` authority. It does
not run automatically or add an MCP tool, framework integration, state
store, config interpreter, or global schema index.

- **B20 — Model class declarations.** Direct, top-level
  `class Payload(BaseModel)`, `class Settings(BaseSettings)` and
  simple `receiver.BaseModel` / `receiver.BaseSettings` base *syntax*
  can nominate a bounded model class. This never establishes the runtime
  identity of `BaseModel` or `BaseSettings`; imported and aliased bases
  beyond the supported literal shapes are not inferred.
- **B21 — Field syntax.** Within an observed class, at most 24 directly
  annotated fields retain source lines, identifier, a bounded direct
  annotation, and defaults using the existing shared
  `handler_input_syntax` owner. `Field(default=..., min_length=...)`
  yields direct call/keyword *names*, not a validated Pydantic field or
  a revealed default value. A missing default does **not** prove required.
- **B22 — Environment key reads.** Direct `os.getenv("KEY")`,
  `os.environ.get("KEY")`, and `os.environ["KEY"]` AST forms retain
  exact source sites and literal or dynamic key syntax, plus a directly
  assigned variable name only when the entire right-hand side is the
  expression. Simple lexical spelling does **not** prove `os` resolves
  to Python's standard library or that a particular runtime value is used.
- **B23 — Boundary and bounds.** At most 16 exact selected `.py` paths,
  256 KiB UTF-8 per member, 64 combined declaration groups, and 128
  characters per environment-key literal. Invalid syntax, excessive
  field count or group count, and forbidden source fail closed, without
  a partial authoritative result. Source policy, revisions, and evidence
  binding are owned by the existing provider context.
- **B24 — No invented correspondence.** The two kinds of observations
  can be independently selected with `include_model_fields` and
  `include_environment_reads`. All groups retain
  `correspondence.state=unresolved`, incomplete coverage, unknown
  runtime schema/field requiredness, and negative-evidence inadmissibility.
  Equal spelling across files does not prove that a handler's annotation
  refers to a particular model, nor that configuration sources agree.

Example:

```python
from hashmarks import CodeMap
from hashmarks.codemap.static_python_backend_declarations import (
    StaticPythonBackendDeclarations,
)

with CodeMap(".") as codemap:
    codemap.sync()
    observation = codemap.discover_repository_declarations(
        [StaticPythonBackendDeclarations(paths=("src/models.py", "src/settings.py"))]
    )
```

This is a *descriptive source observation*. It does not replace the
configuration-evidence path selector, dependency CodeMap, or the existing
repository-declaration correspondence authority. Neither Pydantic validation
nor configuration precedence is inferred or executed.

## Source-local environment expression roles and model initializers (B25–B29)

The explicit `StaticPythonBackendDeclarations` producer also qualifies two
small source-local facts that were previously easy to misread:

- **B25 — Access direction, not a runtime value.** Direct
  `os.environ["KEY"]` subscripts now distinguish
  `load-expression-syntax`, `store-target-syntax`, and
  `delete-target-syntax`. An augmented assignment remains a
  `store-target-syntax` observation; it is not a measured read, atomic
  operation, or runtime side-effect report. Direct `os.getenv` and
  `os.environ.get` calls retain `lookup-call-syntax`. A syntactic
  `os` name is not proof of a standard-library object binding.
- **B26 — One exact AST expression.** A directly annotated class field
  whose entire initializer is one supported environment expression
  carries `direct_environment_initializer`. Its
  `state=same-direct-ast-expression` connects the field declaration and
  the *same* observed expression by physical line and column, not by a
  guessed config-key name. The expression is projected through the
  existing `_env_site` syntax owner; no separate parser or index exists.
  `Field(default_factory=lambda: os.getenv("KEY"))`, nested calls,
  aliases and computed expressions do **not** become direct initializers.
- **B27 — Ambiguous arguments stay ambiguous.** If a lookup call
  supplies both positional and named forms of the same argument, that
  argument is `ambiguous-explicit-syntax`, not the first value found.
  Star-argument and double-star expansion keep
  `argument_binding=unresolved-ambiguous-or-expanded` even if a literal
  is visible beside them. Keyword-only `key=` and `default=` forms
  retain their distinct syntactic candidates.
- **B28 — Revision/visibility/privacy.** All expressions inherit the
  exact selected-file source revision and privacy policy from the
  existing declaration provider context. Call default **values** are
  never copied; only existing default kind/callee/keyword-name facts
  remain. Member edit, missing input, denied source, malformed syntax
  and observation replay use existing fail-closed contracts.
- **B29 — No inferred connection.** Identical environment-key literals
  across unrelated sites remain separate facts. These additions do not
  prove runtime `os` binding, assignment execution, Pydantic model
  identity, environment precedence, a default factory's effects,
  consumer compatibility, or an absent dependency. Provider-level
  correspondence stays `unresolved`, coverage `incomplete`, and
  negative evidence inadmissible. The existing model-only/environment-
  only provider switches remain independently usable.

This bundle extends the **same** `StaticPythonBackendDeclarations`
provider; it introduces no new MCP tool, project-wide search, durable
representation, execution runner, graph or automatic linkage. The open
C01–C04 producer/consumer work is separate and not implicitly absorbed.

## Opt-in caller-nominated producer/consumer syntax pairs (C01–C04)

The existing trusted `StaticPythonInterfaceDeclarations` provider can also
observe narrowly selected **potential** source pairs:

```python
provider = StaticPythonInterfaceDeclarations(
    paths=("src/api.py", "src/client.py"),
    consumer_pairs=(
        ("src/api.py", "get_user", "src/client.py", "show_user", "response"),
    ),
)
```

Each nominated pair requires one unique top-level producer function with a
supported syntactic route/tool decorator, one unique top-level consumer
function, and a caller-specified direct receiver identifier. It retains
independently source-bound literal dictionary-return sites and literal
`receiver["field"]` load sites from the existing handler-body AST observer.
Assignment targets, other receivers, nested functions and alias deductions
cannot turn into reads for that nominated receiver.

The nomination is **not** a proof that the client invokes the route, sees that
response, or runs. The pair is intentionally
`correspondence.state=unresolved`, `comparison.state=ambiguous`,
`coverage.state=incomplete`, and `absence.state=unknown`. A consumer
reading `status` when a provider's known return site contains only `name`
is a *difference in directly observed syntax*, not a breaking-API finding.
Dynamic/unobserved branches and external shapes remain unknown.

All input paths must be in the original explicit path set (maximum 32);
there are at most 16 distinct nominations. Missing/duplicated handler
identities are reported as unresolved nominations in provider provenance,
never as absence. Site bounds, visibility admission, index source revisions,
stable file reads, previous-endpoint deltas and provider trust limitations
remain unchanged. Default calls without `consumer_pairs` preserve their
existing packets and identities.

## Native SCIP symbol metadata

SCIP `SymbolInformation.documentation` and occurrence `symbolRoles` are
producer-origin metadata, not independent source facts. The existing SCIP
adapter now retains a deterministic prefix of at most eight documentation
entries and 8,192 characters total (2,048 characters per entry), with separate
omitted-item and clipped-entry counts. Missing documentation is
`documentation_state=not-supplied`; a present empty list is
`documentation_state=supplied` with no entries. Neither proves source
documentation absence.

Occurrence roles retain the original integer bitmask, direct named role flags,
and unrecognized bits. They do not create new reference/implementation graph
edges or prove reference-set completeness. Both fields stay inside the existing
native producer observation and source-equivalence/freshness authority.

Reference reads (`CodeMap.refs`, `CodeMap.deps`, and the corresponding CLI
commands) expose additive `occurrence_metadata` on existing native rows.
Different ranges or masks on the same symbol/line remain separate occurrences;
they are not combined into one mask or extra graph edges. Each row retains a
canonical ordering of at most 128 distinct occurrences and reports received,
retained, duplicate, and omitted counts, plus truncation. Received equals
retained plus duplicates plus omitted. Bounds never qualify negative evidence.
The metadata's `source_binding` uses the existing producer-to-current-source
correspondence owner: matching, different, and unknown remain distinct, including
when an older index is imported again against changed source. Missing metadata
is null, not evidence of zero role flags. Incompatible generated native caches
are discarded through the existing cache schema rule and require reimport.

## Qualification

Focused regressions:
- `tests/test_competitor_scip_metadata.py`
- `tests/test_static_python_interface_declarations.py`

The full required Python 3.11/3.14, schema, MCP/CLI, source admission, release
and formatting rings remain required before the consolidated PR is ready.
No regression benchmark improvement is claimed until measured in agentsCookbook.
