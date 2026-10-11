# Backend E2E qualification

The target is defensible **5/5 Local E2E evidence for all twenty backend
capabilities**. Expected value is a separate audit judgment. A coverage rating
is never inferred from an average score or from the size of the test suite.

This work extends `scripts.repository_evaluation` with revision workflows,
separate source-fact oracles, retained public responses and coverage accounting.
It is development measurement only. Hashmarks product APIs do not import this
evaluator, judge task sufficiency, execute verification, choose patches, manage
Git state, or certify results.

## Frozen source corpus

The initial `benchmarks/repository_evaluation/manifests/backend-v1/suite.json`
contains twelve genuine upstream source transitions across aiokafka, SQLAlchemy
and FastStream. Each before/after tree has an exact Git commit and a frozen
repository content identity. The
separate `backend-v1/grader.json`
contains independently source-grounded declaration ranges, raw range hashes,
expected verification paths and exact post-change revision checks. Oracles are
never supplied to product observation calls.

The corpus deliberately admits these projects as qualification targets. It does
not authorize following their imports into dependency implementations or adding
package-specific analysis rules.

| Repository | Genuine source transitions |
| --- | --- |
| aiokafka | Fetch cancellation, sender node failure, metadata futures, stable-offset parsing |
| SQLAlchemy | Failed async transaction start, logging-token reset, repeated pickle criteria, aggregate string compilation |
| FastStream | Middleware entry failure, concurrent subscriber shutdown, queue lifetime, partial pull batches |

The first twelve workflows address owner localization, changed declaration and
test correspondence, verification relevance, freshness, initial evidence and
presentation. They **do not qualify** runtime debugging, handler/model/config
contracts, concurrency semantics, message delivery, transaction outcomes,
dependency changes, service compatibility or performance. Real task context
does not establish those additional capabilities by itself.

## Local entrypoints

Obtain read-only local checkouts containing the exact commits named by the suite.
Extract the selected trees without checking out or modifying those repositories:

```sh
uv run --frozen --no-sync python -m scripts.repository_evaluation.materialize_backend \
  --repository aiokafka=/path/to/aiokafka \
  --repository sqlalchemy=/path/to/sqlalchemy \
  --repository faststream=/path/to/faststream \
  --output-dir .hashmarks/backend-e2e/sources

make backend-evidence-dogfood
```

`BACKEND_SOURCES` overrides the source-directory mapping file;
`BACKEND_OUTPUT` overrides the report directory. The ordinary initialization and
test environment still consume the committed uv lock. The official MCP SDK and
installed Hashmarks console script are required for MCP capture.

For a bounded investigation, select a named workflow:

```sh
uv run --frozen --no-sync python -m scripts.repository_evaluation.run_backend \
  --sources-file .hashmarks/backend-e2e/sources/sources.json \
  --workflow aiokafka-metadata-future \
  --output-dir .hashmarks/backend-e2e/investigation
```

`--transport cli` or `--transport mcp` permits a partial measurement. Omitted
transport proof remains unknown and cannot produce a passing full qualification.
Use a new output directory after changing the observer, evaluator, corpus or
grader. Existing receipts fail closed on identity drift instead of silently
reinterpreting old results.

The existing producer rings remain separate, executable evidence:

```sh
make dependency-dogfood
make semantic-evidence-dogfood
make semantic-evidence-live
```

A passing existing live producer ring is useful evidence. It does not
automatically qualify every newly composed backend packet.

The backend corpus also has a separate explicit-target native specimen ring:

```sh
make backend-native-live
make backend-native-dogfood BACKEND_NATIVE_CAPTURES=.hashmarks/backend-e2e/native-live/captures
```

Install `scip-python` and the official `scip` decoder before running the live
command. Each live acquisition requires a new capture directory; set
`BACKEND_NATIVE_LIVE_CAPTURES` and `BACKEND_NATIVE_LIVE_OUTPUT` for another run.
The replay target accepts `BACKEND_NATIVE_CAPTURES` and `BACKEND_NATIVE_OUTPUT`.
Both commands use the exact source mapping in `BACKEND_SOURCES`.

This ring deliberately selects the changed declaration and independently
identified verifier file as explicit specimens. It checks capture bytes,
configuration identity, exact source revisions, current native definition
binding, stale evidence after reopening on changed source, and real CLI/MCP
projection conformance. Unobserved relationship kinds remain unknown. Its report
does not qualify owner recall, verifier recall, initial sufficiency or complete
repository coverage, and cannot grant a capability 5/5. Initial task queries
remain independent of these oracle-selected capture inputs.

## What a workflow records

Each workflow copies caller-supplied sources into a disposable workspace. It
observes the before revision through the API, real CLI and official MCP client,
replaces the copy with the genuine after revision, observes invalidated source
bindings before rebuilding, captures the post-change delta, and re-observes the
after revision. Original source trees remain untouched.

All four presentation formats are captured. The evaluator checks oracle facts
on the actual returned packets and checks presentation conformance against each
transport's own native packet. It retains the exact consumer-visible response,
UTF-8 byte count and the existing byte-based token estimate. Compact/text must
fit within 4,000 estimated tokens; the MCP measurement includes both text and
structured content when both are delivered.

Task evidence now supports an explicit `initial` result mode:

```sh
hashmarks task-evidence 'Describe the repository question' --result-mode initial
```

The API and MCP accept `result_mode="initial"` as well. The default remains the
full `hashmarks.task-evidence.v5` packet. The initial mode returns
`hashmarks.task-evidence-initial.v1`: the same admitted owner, selected verifier,
provenance, freshness and uncertainty, canonical first-three locators and bounded
declaration supplements, one selected/canonical relevance record, and the
separate weak task matches. It retains exact source locations while omitting the
source body, ancillary locator/ranking detail and related sections. Every
collection reduction and omitted section is recorded in `initial_projection`.
The full packet and projection have distinct identities. Re-observing the full
mode may observe changed source, so consumers must compare the supplied full
packet identity before treating an expansion as the same observation.

For this new mode, presentation metadata accounts for undisplayed sections
without duplicating the bounded native facts as display findings. Public
envelopes retain those facts in `result`; a standalone presentation projection is
metadata only. This does not change the existing full-mode rendering contract.
The new mode is a candidate for the initial-response target, not proof that the
4,000-token target has been achieved. Transport measurements and source-fact
qualification still determine that result; existing gates have not been weakened.

Source ranges and revisions are checked against the admitted source trees.
Changed symbols are checked as exact path/symbol/range records, so independent
matches from different declarations cannot manufacture a correspondence.
An oracle may name alternative public record locations for the same positive
source fact, such as a retrieval symbol or an ownership candidate's qualified
name. Every alternative retains the complete expected path and source range;
alternatives are forbidden for authority checks.
Bounded or missing observations cannot satisfy an exclusion check. Source
invalidation must preserve unknown/not-admissible negative evidence.

Receipts bind corpus, oracle, observer, evaluator and transport selection.
Receipt result bytes and retained observation files are revalidated before
reuse. Implementation drift during observation invalidates the measurement.
Receipt reuse preserves evidence only; it does not establish clean-run timing,
execution progress, retry policy or certification.

## Coverage accounting

Every completed report contains all twenty capability rows. A 5/5 row requires at
least twelve distinct upstream problems across at least three repositories,
complete required evidence and passing capability-specific checks. Rewordings,
formats and adversarial variants of the same problem do not increase breadth.
Missing workflows, transport captures or required native proof remain
`INCOMPLETE`. A known hard violation remains `FAIL` even if other work is missing.

Owner top-three recall must reach 95%; supported debugging correspondence and
initial evidence targets must reach 90%. Authority, source binding, freshness
and required transport facts have zero tolerance for violations. A missing fact
cannot be compensated by a better result on another capability.

The report is reproducible repository-intelligence measurement, not an automatic
release promotion or certification decision. Representative coverage and
independent oracle review remain necessary before promoting these targets to
release gates.

## Implementation sequence and current boundaries

| Bundle | Required outcome | Current state |
| --- | --- | --- |
| R01 | Frozen genuine problems, source oracles, public-surface revision runner, all-twenty report | Initial twelve-workflow corpus and runner implemented; full qualification pending |
| R02 | Exact owner/direct path observations with unresolved missing edges | Repaired arbitrary first-symbol projection, incomplete-graph candidate displacement and hidden explicitly named method locators; broader direct-path corpus pending |
| R03 | Genuine failure frames, changed symbols and independently known verifier correspondence | Exact revision/range grading, qualified indirect/alias references and weak lexical test scouts implemented; failure corpus and further relevance proof pending |
| R04 | Genuine handler/model/config/data/service declaration cases | Pending; no runtime compatibility inference is admitted |
| R05 | Async/message/transaction syntax and source ownership observations | Current-source/index-bound function syntax implemented for caller-reported changed spans; genuine transport qualification and broader cases pending |
| R06 | Required facts visible within the initial response ceiling | Whole-response size measured; compact/text CLI whitespace removed without changing facts; duplicated payloads still exceed the ceiling |
| R07 | Dependency/native/language qualification and comparable indexing economics | Explicit backend SCIP capture/source/reopen/transport runner implemented; composed packet, language and economics qualification pending |
| R08 | Complete reviewed matrix and final bounded regression qualification | Pending; no 5/5 completion claim |

The next repairs must follow observed gaps in these genuine workflows. Exact
relationship segments remain bounded claims under their existing producers;
there is no inferred path completion or global semantic graph. Test relevance
remains repository evidence and never becomes coverage or sufficiency authority.

The structural repairs are existing observer defect repairs: a file relationship
does not prove its first declaration, and an incomplete graph cannot displace a
source candidate or redirect verification while competing relationships remain
unobserved. Incomplete candidate evidence is retained for discrimination.
Explicit qualified declaration locators compose the existing symbol/import
identity resolver into bounded retrieval supplements. These supplements cannot
change edit or verification selection, prove uniqueness, or grant ownership.

Verification output can additionally expose bounded task-lexical test scouts
from the existing repository index. New scouts carry
`candidate_origin=bounded-task-lexical-only`, retain false direct/indirect
reference claims, and cannot change the previously selected verification
surface. The search uses repository test-domain and visibility qualification;
test-shaped production filenames do not become test surfaces. Reaching the
lexical bound remains explicit incomplete evidence. A matching word never proves
that a test exercises the changed symbol or is sufficient verification.

Task packets also retain a separate `verification.relevance.task_matches`
observation, including when owner discrimination suppresses owner-bound reference
relevance. It records up to sixteen visible test paths from the first sixty-four
indexed lexical matches, their matched-term counts, index generation and explicit
search/projection bounds. Source binding is indexed and not revalidated by this
projection. It never establishes an edit-to-test relationship, changes the
selected verifier, or admits negative evidence. The qualification oracle and
release gates are unchanged; finding a known verifier in these weak observations
is additional retrieval evidence, not a passing correspondence claim.

```text
Observed repository fact/evidence: Bounded indexed task-term matches in test files.
Authority source: Existing CodeMap lexical index; no exact test relationship.
Completeness/freshness behavior: Explicit bounds and index generation; source
  binding is not revalidated; negative evidence is never admitted.
Existing Hashmarks owner extended: Task evidence and its presentation projection.
Consumer/execution responsibility explicitly not acquired: Choosing/running
  verification, recommendations, ownership and test-sufficiency decisions.
Decision: OBSERVER
```

Caller-reported changed-line evidence now includes bounded
`function_boundary_syntax` for Python functions whose exact declaration ranges
match the current canonical symbol index. It exposes await/call/with/async-with
and exception-handler syntax, with exact UTF-8 source columns. The shared Python
AST cache supplies one qualified tree to body and decorator observers; canonical
member bytes and the existing read-after-observation revision check remain the
authority. Oversized, unstable or unavailable parses stay unresolved. Nested
def/class/lambda subtrees are outside the declared body scope. Site truncation,
omitted functions and unsupported callee expressions remain explicit.

These observations can show `cancel`, `ack`, `commit` or `rollback` spelling in
source. They do not establish the receiver's API identity, actual execution,
message acknowledgement, transaction effects or task ownership. Call syntax is
not an exact caller-to-callee edge.

```text
Observed repository fact/evidence: Direct function-body syntax and source sites.
Authority source: Canonical current member bytes, shared Python AST parser and
  exact indexed declaration-range/name correspondence.
Completeness/freshness behavior: Explicit lexical scope, byte/function/site
  bounds, omission counts, unresolved reads and existing revision closure;
  negative evidence is not admitted.
Existing Hashmarks owner extended: Caller-reported changed-line evidence.
Consumer/execution responsibility explicitly not acquired: Runtime API/task/
  message/transaction ownership, execution order, diagnosis and verification.
Decision: OBSERVER
```

## Measured implementation checkpoint

The twelve-workflow API/CLI/MCP rerun under protocol
`sha256:77cab0911ec2a53211eb2557bf442b22e9f8c596d11daa4074f106abb082966b`
exposed the exact changed declaration in all twenty-four before/after
observations. All twelve workflows passed owner-path top-three recall, owner
authority, candidate revision binding and deliberately invalidated source
binding checks. Three workflows exposed every required declaration/test fact;
nine still missed an independently identified verification path in at least one
revision. None met the whole-response compact/text ceiling.

These measurements bind the implementation captured by that protocol. Later
source changes require fresh measurement; this checkpoint is not current
release authority and does not promote any capability to 5/5. The initial
corpus still leaves fourteen capability families without dedicated workflows.

The explicit-target native specimen ring subsequently passed all twelve genuine
workflows across the same three repositories. It regenerated twenty-four SCIP
captures and checked exact declaration tokens, before/after member revisions,
stale evidence after reopening, API output, and all four CLI/MCP formats.
An incoming subclass implementation claim remains a separate producer record;
the number of related records is never used as a declaration-uniqueness oracle.
This checkpoint proves the named specimen contract only. It does not change the
initial task-query scores or qualify any missing backend capability.
Its observer identity is
`sha256:2857d4b8b70fe4f76b19a221a1cf2d4b41ce619eb85c006d05d7df7b97a2bc33`;
its evaluator identity is
`sha256:abd8c5d6c1ebaee896b631156c31d39047783ae71acbe2600d86a0799c6b597e`.
Subsequent product changes require remeasurement before using this history as
current qualification.
