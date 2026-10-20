# Selected-input identity and inventory

`RepositoryIdentity.observe_inputs()` returns canonical selected-input identity,
recursive member revisions, and regular-file counts from one reconciled
observation. A consumer can retain that result without assembling its own
authoritative inventory or interpreting `Snapshot.digest.size` as file bytes.

This API is introduced in Hashmarks 0.31.0. It is absent from the older
Hashmarks 0.30.0 package.

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

Add `--mode auto` to use a capable running Identity daemon with the existing
local fallback, or `--mode daemon` to require it. The example defaults to local
observation; the no-argument neutral demo remains local.

The empty example describes only its selected scope; it does not establish that
the repository has no other files.

```python
from hashmarks import Directory, File, RepositoryIdentity

with RepositoryIdentity("/work/project", mode="auto") as identity:
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

The CLI projects the same complete observation as JSON:

```bash
hashmarks --workspace /work/project observe-inputs --mode auto \
  --input src --input pyproject.toml \
  --exclude src/generated --exclude src/local.env --verify
```

Repeat `--input` and `--exclude` for additional patterns. Omitting `--input`
requests an explicit empty scope. `--allow-unmatched` maps to
`require_matches=False`; `--max-members` has the same positive-integer bound as
the Python API. CLI paths and globs use the existing string input form. Python
callers can additionally use `File`, `Directory`, and `Glob` assertions.

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

### Local directory materialization observations

`RepositoryIdentity(..., mode="local").observe_directory()` returns a
`DirectoryObservation` from the same Merkle/InputCapture traversal. Its `inputs`
is the ordinary selected-input observation of direct contents (`"*"`), retaining
the native `snapshot("*")` hash domain. `materialization_counts` additionally
counts physical descendants ignored by native hashing, such as nested
`__pycache__` entries. Those counts do not add members to `inputs.members` or
strengthen identity coverage. Symlinks are counted without following targets.
No bytes in an ignored subtree are hashed merely for physical counting.
Producer-owned state paths are omitted from both scopes, including the default
`.hashmarks` directory and an explicitly configured state directory beneath the
workspace. The recorded internal exclusions remain producer-owned scope facts.
Explicit state-path selections through `snapshot()` or `observe_inputs()` retain
the existing rejection policy.

`exclude_paths` contains literal workspace-relative paths, including names with
glob characters; each path and its descendants is omitted from both scopes.
`verify=True` forces native hashing of identity members. `max_members` bounds all
physical counted entries (default 100,000). Unstable physical entries, unsupported
entries, or exhausted bounds prevent a complete result. Physical counts exclude
the workspace root itself, matching the selected direct-contents namespace.

Optional synchronous `checkpoint()` and `progress(InputCounts)` callbacks let a
caller bound its observation and receive physical counting progress. An exception
from either callback aborts the operation without returning a partial result.
Progress is provisional until the final stability checks succeed. This operation
requires explicit local mode and does not change the daemon wire contract.

Observe each child workspace separately when its `snapshot("*")` identity is
required: a parent observation's directory member revision has a different native
hash domain and traversal boundary. Independent calls do not claim one coherent
multi-workspace snapshot; freezing and custody remain consumer responsibilities.

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

These are the local engine's errors. The daemon's existing IPC boundary returns
operation failures as `DaemonProtocolError`, including member limits and source
read failures. An unavailable daemon raises `DaemonUnavailableError`; an
incompatible protocol or missing observation capability raises
`DaemonCompatibilityError`. The CLI renders failures as nonzero errors and
prints no complete observation on failure.

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
| `mode="auto"` | Uses a running compatible daemon that advertises `input-observation.v1`. Falls back to the same local engine only when the daemon is unavailable or incompatible with this operation. |
| `mode="daemon"` | Requires a compatible running daemon and the observation capability. Availability and compatibility errors propagate; there is no local fallback. |
| `IdentityClient.observe_inputs(inputs, ...)` | Direct daemon-only client. It takes an iterable of input specifications and the same observation options. |
| `hashmarks observe-inputs` | CLI projection of the public Identity method, with `local`, `auto`, and `daemon` modes. |
| CodeMap service or MCP | No projection of this Identity operation. These transports do not substitute the CodeMap admission set for selected filesystem inputs. |
| Git commit, ref, or tree selection | Not implemented by this method. There are no `ref` or `revision` parameters, and path strings are not interpreted as Git selectors. |

The daemon adds the `observe_inputs` operation to protocol v3. The
`input-observation.v1` capability is checked for this method; existing snapshot
calls can continue to use an older v3 daemon that supports their baseline
capabilities. The transport retains typed input declarations, so caller-side
kind checks and the canonical engine's scope checks both remain effective.
The request contains the input specifications, exclusions, `require_matches`,
`verify`, and `max_members`. Unsupported fields, including Git selectors, are
rejected rather than silently ignored.

The daemon invokes the same `IdentityEngine.observe_inputs()` owner and sends
the complete observation envelope. Only `snapshot.mode` changes to `"daemon"`;
the recorded scope, member revisions, counts, observer generation, and freshness
travel together. Client decoding checks schema, scalar domains, canonical paths,
manifest fingerprint, member ordering/scope, and count consistency. It preserves
`stale` and `unknown` and does not independently reobserve the filesystem or
authenticate a peer's supplied digest.

The existing daemon response budget is **4 MiB**, including the JSON envelope
and newline. If a complete encoded observation exceeds it, the daemon writes a
small error response instead of any partial observation. `max_members` and the
encoded response budget are separate bounds. Neither a response-budget error
nor a malformed successful reply triggers automatic local fallback. Use an
explicit local API or CLI call when the required complete inventory exceeds the
IPC budget.

A caller may point a local Identity object at a filesystem checkout that the
caller and Git already materialized. Git history observation and checkout
lifecycle remain separate authorities. This method does not import CodeMap or
substitute CodeMap's index admission set for the requested Identity scope.
