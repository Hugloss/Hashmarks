# Selected-input identity and inventory

`RepositoryIdentity.observe_inputs()` returns canonical selected-input identity,
recursive member revisions, and regular-file counts from one reconciled
observation. A consumer can retain that result without assembling its own
authoritative inventory or interpreting `Snapshot.digest.size` as file bytes.

This API is part of the unreleased selected-input handoff change. It is not
present in the published Hashmarks 0.30.0 package.

## Ownership

Observed repository fact/evidence: the members, kinds, content revisions, and
regular-file byte counts of a caller-selected live filesystem scope.

Authority source: the existing Identity input resolver, canonical Merkle node
encoding, FileDigestStore, and filesystem observation machinery.

Completeness/freshness behavior: a successful result is complete for its recorded
resolved scope. Scope drift, unstable selected members, unsupported entries,
unreadable content, or a member-bound failure prevent a complete result. Freshness
uses the existing observer state and generation; it is not a promise that the
filesystem will remain unchanged after the call.

Existing Hashmarks owner extended: Identity and filesystem observation.

Consumer/execution responsibility explicitly not acquired: selecting the scope,
freezing or copying bytes, creating archives, locks, publication, Run admission,
and execution remain consumer responsibilities.

Decision: **OBSERVER**.

## Public use

Use an installed Hashmarks build that contains this API. The
[runnable example](../../examples/input_observation.py) uses only the public
Identity API and the Python standard library. Running it without arguments creates
a neutral temporary repository, observes a selected file before and after a
change, compares the public snapshots, and shows an explicitly empty selection:

```bash
uv run --frozen python examples/input_observation.py
```

Pass a workspace and input paths to observe your own scope without modifying its
source files:

```bash
uv run --frozen python examples/input_observation.py /work/project src pyproject.toml
```

The empty example describes only its selected scope; it does not establish that
the repository has no other files.

```python
from hashmarks import Directory, File, RepositoryIdentity

with RepositoryIdentity("/work/project", mode="local") as identity:
    observation = identity.observe_inputs(
        Directory("src"),
        File("pyproject.toml"),
        exclude=("src/generated", "src/local.env"),
    )

receipt = observation.as_dict()
selected_digest = observation.snapshot.hash
actual_file_bytes = observation.counts.regular_file_bytes
selected_paths = tuple(member.path for member in observation.members)
```

The signature is:

```python
observe_inputs(
    *inputs,
    exclude=(),
    require_matches=True,
    verify=False,
    max_members=100_000,
) -> InputObservation
```

Inputs and exclusions accept the existing string, `Path`, `File`, `Directory`,
and `Glob` forms. Paths are workspace relative and follow the same canonical path
rules as `snapshot()`. The caller may supply an explicit `state_dir`; Hashmarks'
own state files remain excluded by the existing storage owner.

## Scope and canonical identity

The existing input resolver produces one authoritative set of selected roots and
exclusions inside the existing reconciliation. The same set controls both the
Merkle traversal and member inventory. At the end, Hashmarks invokes that resolver
again only to validate that the set has not changed. A different include or
exclusion match raises `UnstableObservationError`; it does not replace the scope,
merge results, or return an apparently current partial inventory.

Equivalent reordered or overlapping selections are canonicalized by
`InputManifest`. A selected real directory covers its descendants. The inventory
contains physical selected paths; synthetic parent nodes used to encode a
manifest are not extra directory members.

Exclusion rules have these meanings:

| Rule | Meaning |
| --- | --- |
| Literal path | Excludes that path and its descendants, including when the path is absent at initial resolution. |
| Glob | Uses the existing glob resolver to record explicit excluded paths. A changed match set during observation is unstable. |
| Redundant nested exclusion | Collapses into the selected excluded ancestor. |
| Excluded selected root | Removes that root from the effective input manifest. |
| Excluded child beneath a selected directory | Removes the child from both that directory's identity and its member inventory. |

Use literal directory exclusions for generated subtrees whose membership can
change. Exclusion globs are recorded as their resolved paths, not retained as an
unbounded live matching policy.

Existing traversal policy remains in effect. Names such as `.git` and
`__pycache__` are ignored while walking a selected directory, while explicitly
selecting an otherwise ignored root retains existing Identity behavior.
Hashmarks' mandatory exclusions, including `.hashmarks` and its owned state
paths, remain excluded. Explicitly selecting a mandatory-excluded path raises
the existing identity error. The observation records these policies alongside
the caller's exclusions.

No canonical hash domain or existing snapshot identity changes. Without
exclusions, an equivalent `observe_inputs()` call produces exactly the digest of
`snapshot()`. With exclusions, native directory and manifest node encodings apply
to the filtered scope. Filtered directory or manifest nodes never enter the
unfiltered caches; file revisions still come from the existing FileDigestStore.

`observation.manifest` and `snapshot.manifest_fingerprint` identify the resolved
selected roots. Retain the complete `InputObservation` when transporting the
scope: those existing manifest fields do not encode nested exclusions or walk
policy. Calling `snapshot_manifest(observation.manifest)` alone applies the
ordinary snapshot policy, so it does not replay a filtered observation.

## Members, revisions, and counts

`InputObservation`, `InputMember`, and `InputCounts` are immutable public value
objects. Member ordering follows canonical byte ordering of relative paths.

| Member kind | Revision and other facts | Count semantics |
| --- | --- | --- |
| Regular file | Existing canonical file revision, byte length, and executable bit. A content revision alone does not include the path or executable bit. | One file and its full byte length. Binary and non-indexable files are included. |
| Real directory | Native directory revision for its selected children. Empty selected directories remain members. | One directory and zero regular-file bytes. |
| Symlink | Existing canonical symlink revision and the literal target spelling. The target is not followed, including a dangling target. | One symlink and zero regular-file bytes. |

Hardlinks count once per selected path, including each path's file bytes. The
inventory reports the selected namespace, not unique physical storage usage.
Zero-byte files still count as files. Synthetic manifest parents do not count as
physical directories.

`InputCounts` exposes `file_count`, `directory_count`, `symlink_count`,
`regular_file_bytes`, and the derived `entry_count`. These counts use the same
members and native file digests that produce the selected-input digest.
`Snapshot.digest.size` retains its established Merkle-encoding size. Use
`counts.regular_file_bytes` for the sum of regular-file bytes.

An empty input sequence, a fully excluded scope, or an unmatched selection with
`require_matches=False` returns the existing empty selected-input identity and
zero counts. Its `completeness="complete"` concerns that explicit empty scope;
it is not evidence that the repository contains no files.

## Coherence, errors, and freshness

Member metadata is captured before the native file digest read. After identity
construction and scope validation, the capture checks the selected members and
their containing directory identities. A relevant content, membership, kind,
or ancestor change prevents the digest from being paired with an earlier count.
The existing reconciliation also rejects or retries changing observer
generations. Changes confined to an excluded path do not become selected
identity or member evidence.

The default read validates file metadata and can reuse existing native content
digests. `verify=True` additionally forces file-byte hashing through the same
FileDigestStore. Neither mode freezes the filesystem or reserves paths for a
later consumer copy.

Failures return no `InputObservation`:

- Missing required inputs raise the existing missing-input error.
- A changed scope or unstable capture raises `UnstableObservationError`; native
  unstable file reads keep their existing FileDigestStore error behavior.
- Permission and other filesystem read errors propagate.
- FIFO, socket, device, and other unsupported selected kinds raise `ValueError`
  before being treated as readable file content.
- A selected path with a symlink or non-directory ancestor is unsupported. A
  symlink leaf remains supported without following its target.
- Exceeding `max_members` raises `ValueError`; a truncated inventory is never
  returned as complete. The bound counts real directories and symlinks as well
  as files and must be a positive integer.

The versioned dictionary has schema `hashmarks.input-observation.v1`, the existing
snapshot envelope, explicit scope, members, counts, completeness, and freshness.
`authority="repository-evidence-only"` and `execution_effect="none"` describe the
handoff. Freshness is the existing `current`, `stale`, or `unknown` vocabulary,
qualified by the snapshot's observer generation. Consumer workflow decisions do
not become Hashmarks evidence.

## Transport and authority support

| Requested authority or mode | Support |
| --- | --- |
| `RepositoryIdentity(..., mode="local")` | Supported for live filesystem inputs. Existing `reconcile`, `watcher`, and explicit `manual` observer choices retain their documented roles. The inventory itself traverses the selected scope on each call. |
| `mode="auto"` | `observe_inputs()` raises `NotImplementedError`, including when no daemon is running. Use an explicit local identity object for this API. |
| `mode="daemon"` | Inventory transport is not implemented. The constructor retains its existing required-daemon check; an available daemon does not enable this method. |
| Git commit, ref, or tree selection | Not implemented by this method. There are no `ref` or `revision` parameters, and path strings are not interpreted as Git selectors. |

A caller may point a local Identity object at a filesystem checkout that the
caller and Git already materialized. Git history observation and checkout
lifecycle remain separate authorities. This method does not import CodeMap or
substitute CodeMap's index admission set for the requested Identity scope.
