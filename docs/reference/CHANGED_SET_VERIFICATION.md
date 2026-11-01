# Changed-set verification evidence

**Status: supported public Python producer contract.**

`CodeMap.verification.changed_set(...)` returns
`hashmarks.changed-set-verification.v1`. It composes existing repository
verification, source, import, project and correlation owners into one bounded
result. A consumer does not need to reconstruct verification relationships
from low-level graph edges.

```python
from hashmarks import CodeMap

with CodeMap(".", state_dir=".hashmarks") as repository:
    repository.index.sync()
    evidence = repository.verification.changed_set(
        ["src/catalog/total.py", "tests/conftest.py"],
        limit=100,
    )
```

Changed paths are caller-supplied repository-relative paths. The operation
normalizes, deduplicates and sorts them; it does not inspect Git, select a
change, run a test or decide whether the evidence is sufficient. There is no
new root alias, CLI command or MCP tool for this component operation.

## Result and authority

| Field | Meaning |
| --- | --- |
| `changes` | Per-path canonical source observation, source-qualified role, project/workspace context, existing relevance and explanation, qualified relationships, optional asset observations and consumer-scope qualifications. |
| `targets` | Deduplicated logical verification targets, their canonical command-free nominations, stable member identities and context. An unavailable nomination retains its reason and supplies no membership. |
| `membership` | Existing `hashmarks.verification-membership.v1` identity for exactly the returned, available logical targets; `null` when none qualify. This is not native collected membership or a complete set of consumers. |
| `collection` | Optional unchanged observation of a caller-supplied native collection report, through `observe_membership()`. |
| `correlation` | Optional unchanged canonical runtime/diagnostic correlation packet, through `RepositoryCorrelation.observe()`. |
| `repository`, `freshness` | Existing repository/source/generation binding and the canonical `current`, `stale`, or `unknown` freshness vocabulary. |
| `completeness`, `truncated`, `bounds` | Consumer coverage and projection qualifications, including omitted reference candidates and omitted targets. |
| `evidence_identity` | Deterministic identity over this exact projection and its nested evidence. No observation history or execution state is stored. |

The changed-file contract nominates whole logical file targets, retaining the
nomination's test-file/package/project scope. It does not guess one function
from a whole-file change or flatten a test class into an invalid node selector.
The existing standalone `nomination(path, symbol=...)` operation remains
available for explicit supported node requests.

`execution_authority`, `result_authority` and `certification_authority` are
`external`. The result contains no canonical argv, working directory, batch
layout, worker selection, timeout, retry or scheduling decision. Legacy advisory
`plan()` is not consulted by this operation or by its relevance candidates;
candidate availability uses source-qualified nominations, not installed tools.

Shared indexed relevance keeps its caller's selected binding intact. Optional
availability remains unqualified when current source or metadata cannot support
a nomination; it does not refresh away the existing task evidence staleness
signal. The changed-set producer owns reconciliation of its observed source
contributors and then obtains strict current target nominations.

## Relationships and support scope

Ordinary source relationships reuse the existing bounded reference owner.
Direct references and one-intermediate indirect references retain their
qualified import identity, reference strength and supporting source revisions.
Re-export facades and intermediate import declarations are retained from the
same import walk, not rediscovered by another graph. Syntax-qualified test
helpers can be intermediate source consumers; they are not themselves promoted
to test membership merely because their path is under `tests/`.

A changed verifier has an explicit `changed-verifier` relationship to itself.
Python verifier roles require source declarations in a canonical test domain;
test helpers, factories and data remain support. Native polyglot test-file
classification uses the existing syntax provider and repository test domains.
Missing capability, malformed source and denied evidence remain unknown.

Qualified `conftest.py` and pytest configuration may expose
`pytest-conftest-scope` / `pytest-configuration-scope` applicability relationships
to indexed Python verifiers beneath their directory. These are **related
structural applicability**, not proof that every test consumes a particular
fixture. Fixture overrides, plugins, dynamic fixture lookup, generated tests,
runner collection and runtime configuration selection are not inferred. The
packet preserves unknown consumer coverage and observed unsupported features.
Ordinary imported factories/helpers reuse import evidence; structurally proven
repository file reads reuse the existing literal-read owner.

## Repository assets

For an observed asset, `changes[i]["asset"]` describes its content kind,
repository roles and supported references from other repository members.
Content metadata comes from the existing Source observer. Consumer candidates
reuse the maintained repository index and supporting members are bound to their
canonical source revisions; this does not add another repository walk, index or
persistent asset graph.

Refresh the existing index with `repository.index.sync()` before a new
observation when files may have been added. Opening a retained CodeMap alone
does not rediscover new consumers. The changed-set operation rechecks its
known supporting members; it does not introduce an implicit repository scan
to turn an old candidate inventory into complete consumer coverage.

Qualified consumer relationships remain distinct from literal occurrences that
have not been established as a read or link. A reference from a Markdown document,
an application file and a test fixture have different repository roles. A
documentation directory or image extension does not establish that an asset has
only documentation consumers. The evidence preserves unknown dynamic consumers,
unsupported reference forms and projection bounds.

Candidate discovery intersects indexed lexical tokens from the asset basename.
Within those candidates, the supported positive syntax is a local relative
inline Markdown image/link or an unshadowed, repository-root-qualified literal
`pathlib` read. Unsupported reference syntax and ordinary mentions can remain
`literal-only`; computed paths, dynamic loaders and files outside the maintained
index are not an exhaustively observed consumer set.

The asset packet reports its actual limits: currently 64 candidate members,
64 returned references, 1 MiB per supporting member and 4 MiB of supporting
source bytes. `source_coverage` qualifies the selected source observations, not
the entire repository. A missing, denied, unreadable or oversized candidate
marks that coverage incomplete; candidate, byte and result bounds remain
explicit. Even complete selected-source coverage leaves global consumer
`completeness` unknown.

The asset projection has no `safe_to_skip` or merge decision. Empty or exclusively
documentation-shaped returned references do not prove complete absence of other
consumers. `negative_evidence_admissible` remains false, and incomplete or unknown
coverage cannot be promoted to a repository-wide negative claim. A consumer may
apply its own explicit, bounded documentation policy, but must retain the
producer's qualifications instead of presenting that policy as exhaustive proof.

LFS pointer declarations remain distinct from observed object bytes. Hashmarks
never hydrates missing objects or invokes checkout filters while classifying an
asset. A missing, denied, oversized or stale source remains qualified as such;
it cannot acquire image authority from its filename.

## Workspace context

Each changed path and target carries producer-qualified context. Nominations
observe the nearest relevant Python/frontend manifest and every nearer absent
candidate, so introducing a nearer manifest invalidates retained source
binding. Denied or unreadable metadata cannot be skipped to justify an ancestor.

Python source roots come from Index's existing packaging/workspace interpreter.
Context requalifies ancestor pyproject inputs before projecting them; pyproject
reconciliation reuses canonical index sync and module reprojection. Reopening
the same index preserves unchanged roots and evidence identities.

Manifest location, Python import root and native project identity are different
facts. Native project identity comes only from the existing qualified retained
project evidence. An unobserved/stale project remains unknown, and ambiguous
owners remain ambiguous. Freshly reading `package.json` does not manufacture a
current native project graph. Consumers use these qualifications instead of
inventing project ownership from path prefixes.

## Bounds, uncertainty and freshness

The request accepts at most 256 changed paths and `limit` from 1 to 1000. The
existing reference projection returns at most 16 candidates per changed path;
its other search/depth bounds remain explicit in `relevance`. Shared-support
inspection observes at most 512 indexed candidate paths. Context observes at
most 32 ancestor directories and returns at most 32 projects/source roots.
The final packet is limited to 1 MiB; oversized requests/results fail explicitly.

Reference search completeness, support-scope completeness, context completeness,
returned membership and whole consumer coverage remain distinct. The result
does not claim exhaustive dynamic consumer coverage. Its top-level
`negative_evidence_admissible` is therefore false, including when `targets` is
empty. A bounded result cannot establish that no verification is relevant.
The exact source observer may independently prove that a named file is absent;
that narrower fact does not prove absence of test consumers.

The operation borrows one generation-bound read scope and rechecks observed
supporting members before returning. Source drift restarts through the existing
reconciliation owner; repeated drift fails closed. These are bounded
observations, not an atomic filesystem snapshot or a freshness lease after
return. Retained nominations can be rechecked with
`verification.observe_nomination_source_binding(nomination)`.

## Runtime and collected evidence

Pass `correlation_bundles=` and optional `path_mappings=` using the existing
[evidence correlation contract](EVIDENCE_CORRELATION.md). The nested packet
preserves caller provenance, mappings, source equivalence, ambiguity, bounds and
independent freshness. It does not infer that a change caused a diagnostic.
Omitted runtime input remains `null`, not a complete negative observation.

Pass `collection_report=` using the existing
[membership handoff contract](VERIFICATION_MEMBERSHIP_HANDOFF.md). Supplied
source claims and collector completeness remain external claims. The observer
does not collect tests or substitute current source revisions for revisions an
external collector failed to supply.

The existing evidence-presentation producer renders this packet and delegates
nested source, nomination, collection and correlation facts to their canonical
presenters. Consumers should preserve that producer meaning.

## Observer ownership note

**OBSERVER:** the new fact is source-qualified changed-set verification and
support applicability, needed by consumers that previously had to reassemble
repository graph semantics. `RepositoryVerification` owns the composition and
support interpretation; Source, Imports, Index, Native and Correlation retain
their existing authorities. The state is a request-scoped reconstructible
projection with no new persistent cache or history. Freshness and revision
identity remain Source/read-scope-owned; verification bounds and consumer
coverage remain verification-owned. Repository admission and disclosure apply
before syntax interpretation. The supported Python component method serves
this distinct consumer responsibility; MCP promotion is not part of this change.
Execution, sufficiency, outcomes, certification, Git lifecycle and OH-Goon
workflow policy remain explicit non-goals.

**OBSERVER extension:** content kind, LFS declarations and supported asset
references describe captured repository material. Source owns the byte facts;
the existing verification composition owns their consumer projection. No
OH-Goon filename, documentation exemption, image-decoding policy or execution
decision is part of the reusable producer contract.
