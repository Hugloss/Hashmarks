# Source-bound verification membership

**Status: current direct-Python contract, added after the 0.30.0 baseline.**

`CodeMap.verification.observe_membership(report)` observes the repository inputs
named by a supplied verification selection or native collection report. It keeps
the reported membership and collector claims separate from Hashmarks' source
observations. It does not discover tests, invoke a collector, or prove that a
reported selector names a test that a native tool would collect.

## Observer ownership note

```text
Observed repository fact/evidence: correspondence between a supplied flat membership report and explicitly nominated repository member revisions.
Authority source: existing Source/Bindings/Correlation observations; membership, collector provenance, status, scope and completeness remain caller claims.
Completeness/freshness behavior: missing revision claims and unavailable source remain unknown; source equivalence, repository freshness and claimed collection completeness stay separate.
Existing Hashmarks owner extended: Verification membership, borrowing Source, Bindings and Correlation through their existing read scope.
Consumer/execution responsibility explicitly not acquired: native collection, collector authenticity, execution, partitioning, admission, results and certification.
Decision: OBSERVER
```

## Public Python surface

~~~python
from hashmarks import CodeMap, validate_native_consumer_bundle

# supplied_report is produced or normalized by the external consumer.
with CodeMap(repository_path) as codemap:
    codemap.index.sync()
    observation = codemap.verification.observe_membership(supplied_report)

validated = validate_native_consumer_bundle(observation)
assert validated["valid"], validated["reasons"]
~~~

The supported observation schema is
`hashmarks.verification-membership-observation.v1`. This initial handoff is a
direct Python API. Service, CLI and MCP do not acquire it automatically.

The existing `validate_native_consumer_bundle(envelope, contract, ...)` call
continues to validate its existing verification-selection envelope and downstream
contract. The new single-observation form does not take a legacy contract or a
Hashmarks own-qualification handoff. The public creation and validation path does
not load Hashmarks own-test shard or qualification configuration.

## Supplied report

The input is a strict JSON-portable object with exactly these fields:

~~~json
{
  "schema": "hashmarks.verification-membership-report.v1",
  "selection_kind": "native-collected",
  "producer": {"name": "example-collector", "version": "1"},
  "provenance": {"report_id": "externally-retained-report:1"},
  "scope": {"paths": ["tests/test_example.py"]},
  "status": "succeeded",
  "completeness": "complete",
  "truncation": "complete",
  "members": [
    {"path": "tests/test_example.py", "test_symbol": "TestGroup::test_case[a::b]"}
  ],
  "inputs": [
    {"path": "tests/test_example.py", "member_revision": null},
    {"path": "pyproject.toml", "member_revision": null}
  ]
}
~~~

The null revisions in this example deliberately supply no historical source
proof. Even if both paths are present, their source equivalence remains unknown.

| Field | Contract |
| --- | --- |
| `selection_kind` | `native-collected` or `caller-selected`. This is an explicit claim about the input, not a Hashmarks attestation that collection occurred. |
| `producer` | Nonempty opaque producer metadata. It is separate from the observation's Hashmarks producer identity. |
| `provenance` | Opaque report provenance supplied by the consumer. It is not authenticated by Hashmarks. |
| `scope` | Opaque claimed collection/selection scope, including any relevant consumer-normalized selection context. A `complete` claim requires a nonempty scope. |
| `status` | Claimed `succeeded`, `failed` or `unknown`. Hashmarks does not sense a process or establish this status. |
| `completeness` | Claimed `complete`, `incomplete` or `unknown`. `complete` requires claimed success and complete truncation. |
| `truncation` | Claimed `complete`, `truncated` or `unknown`. |
| `members` | An array of `{path, test_symbol?}` rows, or null when membership is unavailable. An explicit empty array is different from null. Claimed success requires an array. |
| `inputs` | Explicit `{path, member_revision?}` source/configuration claims. Omitted or null revisions remain unknown. |

All paths are normalized repository-relative member paths. A member may name a
whole file by omitting `test_symbol` or using null. A nonblank symbol retains its
complete native selector, including class segments and parametrized values
containing `::`; Hashmarks does not split or reinterpret that selector as syntax.
Leading/trailing whitespace follows the existing member constructor's
normalization. Duplicate normalized members and duplicate input paths are rejected.
Members and inputs are ordered canonically; caller mutation after the call cannot
change the issued observation.

The report is bounded to 10,000 members and 1 MiB of encoded strict JSON. The union
of selected paths and nominated input paths is bounded to 256 unique members;
producer, provenance and scope objects each have an 8 KiB bound. Existing
Correlation request/packet bounds also apply. Oversized input is rejected rather
than silently truncated. The complete observation has a 4 MiB bound.

Source qualification uses the existing bounded `Source.observe()` operation,
currently limited to 1 MiB per member. An oversized source remains unknown with
the existing `source-size-bound` reason; it is not treated as matching or absent.
Bytes are read one member at a time and are not included in this handoff.

## Source revisions and what correspondence proves

`member_revision` is the canonical 64-character lowercase member revision used
by `CodeMap.source.member(path)`. It is not an arbitrary plain file SHA-256, a Git
blob ID, a timestamp, or the repository's `source_identity`. A consumer must
retain or supply the revision that its external report claims to have observed.
The example script uses synthetic supplied reports and records these claims
explicitly; it never runs a native collector.

Every selected member path is observed, including paths without a revision claim.
`inputs` adds nominated configuration, manifests, or other source inputs and
supplies any collection-time member revision claims. No dependency/configuration
closure is inferred. Omitting a configuration input does not prove it irrelevant,
and a complete collector claim does not prove that all relevant inputs were
nominated.

Hashmarks observes nominated members through bounded, byte-backed Source reads,
and passes the exact path/revision claims into the existing Correlation owner
using whole-member Bindings. The `source_members` field retains these canonical
member observations. They must agree with Correlation's member observations for
the combined source-equivalence claim to be proven. Source observations are
revalidated before return; relevant drift fails closed using the existing
unstable-file exception. Admission, visibility, stable reads and generation all
remain Source-owned. Native selectors remain opaque membership
values; they are not sent to the symbol resolver as proof of native test identity.

The observation's `source_equivalence` summarizes **only the explicitly nominated
input union**:

- `proven`: every nominated member is present and uniquely path-bound, and every
  supplied canonical revision matches its qualified member observation;
- `mismatch`: at least one present, qualified member differs from its supplied
  revision claim;
- `unknown`: an input is unavailable/unqualified, a revision claim is missing, or
  the input union is empty, unless an independently qualified mismatch exists.

An indexed revision that no longer agrees with current source is not promoted
into proof. The complete underlying Correlation packet retains per-input
resolution, availability, revision, source-equivalence basis and bindings.

Matching revisions prove equality to the **supplied claims**. They do not prove
which bytes a collector actually read, when collection occurred, which tool
produced a report, that native collection was complete, or that the reported
tests exist under native collection semantics. Report provenance is not a
cryptographic signature. Observing today's source cannot retrospectively fill a
missing collection-time revision.

## Membership and explicit emptiness

For nonempty membership, the observation reuses
`hashmarks.verification-member.v1` and `hashmarks.verification-membership.v1`,
including their existing grouping-independent identities. Changing collection
provenance or source correspondence does not change these member identities.

For `members: []`, the observation contains
`hashmarks.verification-empty-membership.v1`: an empty member array, count zero,
and a deterministic identity in that distinct domain. The existing legacy
membership/envelope validators keep their nonempty contract; the new observation
validator owns this explicit empty result.

For `members: null`, `membership` is null and no member count or membership
identity is invented. A failed collection may retain a partial nonempty list
with incomplete coverage. None of these cases establishes repository-wide test
absence. The observation always declares `repository_absence: not-inferred` and
keeps membership and collection-completeness authority `caller-claimed`.

## Freshness and consumer validation

Repository `freshness` is the existing `current | stale | unknown` binding fact.
It is independent of source equivalence and collector-claimed completeness.
For example, exact source claims can match while overall repository freshness is
unknown. The handoff preserves those facts without manufacturing a fresh result.

`validate_native_consumer_bundle(observation)` performs pure retained-packet
validation. It checks schema/shape, identities, existing Correlation and Bindings
invariants, the exact report-to-correlation claims, membership projection and
external authority boundaries. It does not read the repository or authenticate a
collector. A valid observation can describe stale, mismatched, incomplete or
unknown evidence.

The optional `expected_producer_implementation_identity` checks the issued
Hashmarks identity against the identity the consumer supplies. The optional
`require_fresh=True` additionally requires a recorded `current` repository
observation and `proven` nominated-input equivalence. It never upgrades collector
completeness. These options validate the retained observation's claims, not
present-day currentness. To obtain a new observation, submit the original report
to `observe_membership()` again against the repository authority of interest.

The normalized result includes member rows (null for unavailable membership),
membership/report/observation identities, repository provenance and freshness,
source-equivalence scope, Hashmarks producer metadata, and the preserved report.
The legacy envelope's boolean freshness mapping is unchanged.

## Standalone example

Run the self-contained example with the supported Hashmarks package installed:

```sh
uv run --frozen --no-sync python examples/verification_membership.py
```

The example creates a neutral temporary repository and supplied report, observes
matching and changed source, and demonstrates incomplete and explicit empty
membership. It uses public Hashmarks APIs and runs no collector or tests.

Source observation and retained validation can ship independently of the
selected-input inventory API. No OH-Goon installation, paths, configuration,
execution, or code changes are required.
