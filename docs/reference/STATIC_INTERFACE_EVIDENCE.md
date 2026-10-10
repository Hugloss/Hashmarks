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

## Qualification

Focused regressions:
- `tests/test_competitor_scip_metadata.py`
- `tests/test_static_python_interface_declarations.py`

The full required Python 3.11/3.14, schema, MCP/CLI, source admission, release
and formatting rings remain required before the consolidated PR is ready.
No regression benchmark improvement is claimed until measured in agentsCookbook.
