# Standalone consumer integration

Hashmarks supplies canonical repository observations that an embedding tool can
consume through a thin adapter. This guide covers the observation gaps identified
by the 0.30 integration review. The additions are documented under Unreleased
until included in a published package.

## Ownership and public entry points

| Consumer need | Hashmarks entry point and owner | Authority kept by the consumer or native tool |
| --- | --- | --- |
| Selected-input digest, manifest, inventory, and byte counts | `RepositoryIdentity.observe_inputs(...)`; Identity | Choosing the input scope and interpreting changes |
| Source-bound native test membership | `codemap.verification.observe_membership(report)`; Verification borrowing Source, Bindings, and Correlation | Native collection, selector meaning, execution, scheduling, retries, and results |
| Make targets and authored shell invocation syntax | Explicit `MakeShellDeclarations`; Declarations provider context | Make/shell expansion, effective command behavior, and execution |
| Python/uv manifest declarations | Explicit `PythonUvManifestDeclarations`; Declarations provider context | Package resolution and effective uv workspace membership |
| Original contiguous source bytes and a range identity | `codemap.source.range_receipt(...)`; Source | Selecting the range, interpreting bytes, and editing |
| JavaScript/TypeScript aliases, property accesses, and call syntax | `codemap.source.ecmascript(...)`; Source and its configured native parser | Semantic alias closure, imported implementations, runtime targets, and execution |
| Hashmarks verification contract validation | `validate_native_consumer_bundle(...)`; existing public consumer validator | Trust/admission policy and execution-result authority |

Each result carries the facts its existing owner can establish. A source-bound
declaration is an observation of authored syntax. A native membership observation
preserves an external producer's claim. Neither becomes a statement that a command
ran, a dependency resolved, or a verification result passed.

## Package and import contract

Install the selected Hashmarks wheel from
[GitHub Releases](https://github.com/Hugloss/Hashmarks/releases) with the native tool
that owns the consuming Python environment. For a reviewed source candidate, that
tool may install the selected checkout or a wheel built from it. Hashmarks does
not manage the consumer's environment, and the standalone CLI/MCP executable is
not the importable Python package. The release workflow does not publish to PyPI.

For example, the published **0.30.0 baseline** can be pinned from its actual wheel
asset in an existing uv-managed consumer project:

```bash
uv add --bounds exact "hashmarks @ https://github.com/Hugloss/Hashmarks/releases/download/v0.30.0/hashmarks-0.30.0-py3-none-any.whl"
uv run --frozen python -c "from hashmarks import RepositoryIdentity"
```

Retain the resulting `pyproject.toml` and `uv.lock` with the consumer project.
**The Unreleased APIs in this guide require a build containing this change; they
are not present in the published 0.30.0 baseline.** To try a reviewed candidate,
run `uv build --wheel --out-dir ../hashmarks-wheels` from that Hashmarks checkout,
then select the exact built wheel from the consumer project, for example:

```bash
uv add --bounds exact /absolute/path/hashmarks-wheels/hashmarks-0.30.0-py3-none-any.whl
```

Use the filename emitted by that build; release preparation owns the next version
number. A later published release can be pinned by its own versioned asset URL.

Use these documented imports:

```python
from hashmarks import (
    CodeMap,
    InputCounts,
    InputMember,
    InputObservation,
    RepositoryIdentity,
    native_producer_implementation_identity,
    validate_native_consumer_bundle,
    validate_repository_intelligence_evidence,
)
from hashmarks.codemap import (
    CodeMapServiceClient,
    MakeShellDeclarations,
    PythonUvManifestDeclarations,
)
```

The provider class imports are explicitly supported here and in the API reference.
Importable parsing, storage, normalization, and validation implementation modules
do not become public APIs by association. Retain Hashmarks' returned identities as
opaque values; downstream code should not recreate the digest algorithm, freshness
rules, membership normalization, or schema validators.

## Transport scope

The direct API and service client have different call shapes. For example,
`codemap.index.sync()` and `codemap.tasks.evidence(task)` are direct component
operations. `client.sync()` and `client.task_evidence(task)` are flat service
methods that connect to an already managed CodeMap service.

| Added capability | Supported surface in this change |
| --- | --- |
| Coherent input observation | `RepositoryIdentity` in local, auto, and daemon modes; CLI `observe-inputs` |
| Native membership observation | Python `verification.observe_membership(report)`; CLI `verification-membership`; MCP `repository_evidence` membership mode; service `verification_membership(report)` |
| Retained membership validation | Public pure Python consumer validator |
| Make/shell and Python/uv declarations | Explicit Python providers; CLI path selectors or source-selection JSON; MCP and service `repository_declarations` discovery mode |
| Exact byte-range receipt | Python `source.range_receipt(...)`; CLI/MCP `source_observation` range mode; service `source_range_receipt(...)` |
| JavaScript/TypeScript syntax | Python `source.ecmascript(...)`; CLI/MCP `source_observation` ecmascript mode; service `source_ecmascript(...)` |

The CLI spells the source command `source-observation`. Identity input observations
use method-specific daemon capability negotiation: auto mode falls back locally
only for an unavailable daemon or missing capability. Malformed or oversized
successful replies remain protocol errors. These observations have no Git-ref,
CodeMap-service, or MCP projection.

Service consumers use `client.sync()` to reconcile the repository when needed;
read methods preserve the native owner's freshness. Explicit selector adapters
construct registered first-party declaration providers for CLI/MCP/service
discovery. Arbitrary supplied Python provider execution is outside these
transport contracts.

## Using the observations together

Choose an explicit input scope and obtain identity, manifest, inventory, and
counts through one `observe_inputs()` call. Use the returned regular-file byte
total for inventory reporting; `Snapshot.digest.size` retains its canonical
identity semantics. A second filesystem count pass would describe a different
observation and can disagree during mutation.

For native test membership, the native collector supplies exact selectors and
the revisions of the inputs it actually observed. Include relevant configuration
or manifest paths as collection inputs. Pass that report unchanged to
`verification.observe_membership()`, then use the public consumer validator on
the retained result. Hashmarks binds every selected member path and the supplied
input revisions. Missing collection-time revision claims remain unknown; reading
today's file cannot prove what an earlier collector saw.

An explicit empty member list, an unavailable member list, incomplete collection,
and a failed collector remain different states. Successful structural validation
does not establish complete collection, fresh source correspondence, or admission
to execute. The consumer evaluates the returned qualifications for its own purpose.

Use declaration providers when the question concerns authored Make/shell or
Python manifest syntax. Keep resolved dependency observations on the existing
dependency adapter path. Static workspace-pattern candidates must not be
relabelled as uv's effective workspace membership, and authored shell text must
not be relabelled as a fully expanded command.

Use `range_receipt()` when exact source bytes are needed. Its byte completeness
applies to that range only. `freshness` remains `current`, `stale`, or `unknown`;
source-equivalence states belong to their separate correspondence contract.

Use `source.ecmascript()` when the question needs source facts such as
`const transport = client`, object destructuring, or `transport.send(...)`.
The optional native syntax capability supplies exact byte ranges and lexical
scope. Dynamic property expressions and call targets remain unresolved. Bounded
facts, unsupported parsers, and incomplete native syntax never establish absence.

## Standalone examples and qualification

The examples under `examples/` use neutral temporary repositories or an explicit
caller-supplied repository. They are ordinary consumers of the documented Python
package and require no Oh-Goon installation, repository, or test archive.

| Contract | Reference | Example |
| --- | --- | --- |
| Input observation | [Selected inputs](../reference/INPUT_OBSERVATIONS.md) | [input_observation.py](../../examples/input_observation.py) |
| Native membership | [Membership handoff](../reference/VERIFICATION_MEMBERSHIP_HANDOFF.md) | [verification_membership.py](../../examples/verification_membership.py) |
| Make/shell syntax | [Make/shell evidence](../reference/MAKE_SHELL_EVIDENCE.md) | [make_shell_declarations.py](../../examples/make_shell_declarations.py) |
| Python manifest syntax | [Python/uv manifests](../reference/PYTHON_UV_MANIFEST_EVIDENCE.md) | [python_uv_manifest_declarations.py](../../examples/python_uv_manifest_declarations.py) |
| Source byte range | [Byte receipts](../reference/SOURCE_RANGE_RECEIPTS.md) | Inline direct-Python example in the reference |
| JavaScript/TypeScript syntax | [ECMAScript source](../reference/ECMASCRIPT_SOURCE_OBSERVATIONS.md) | [ecmascript_source.py](../../examples/ecmascript_source.py) |

Focused tests cover inventory/digest agreement, mutation, exact selectors, empty
and incomplete reports, stale or missing source binding, bounded declaration
coverage, byte-preserving receipts, native ECMAScript syntax, and real transport
round trips. These qualify Hashmarks observation
semantics; they do not claim that an external collector, resolver, or executor has
been integrated or certified.

The admitted JavaScript/TypeScript scope is the syntax gap demonstrated by import
aliases, assigned bindings, destructuring, property accesses, and call sites in
one explicit source member. Existing Source reads and native parsing own that
observation. A resolver graph or runtime interpretation is not part of this scope.

See [Public API and stability](../reference/API_STABILITY.md) for the supported
contract and [Hashmarks ↔ Oh-Goon](OH_GOON_INTEGRATION.md) for the application of
these ownership boundaries to that consumer.
