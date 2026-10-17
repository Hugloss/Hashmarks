# Backend E2E qualification

The current architecture handoff is the active
[canonical component rewrite](../plans/CANONICAL_COMPONENT_REWRITE_PLAN.md),
with breaking Python APIs and explicit owners. Implementation is in progress under the user’s explicit instruction.
The broader qualification definition below remains intact for later research;
it is not the completion criterion for every bounded architecture subgoal.

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
`hashmarks.task-evidence-initial.v2`: the same admitted owner, selected verifier,
provenance, freshness and uncertainty, canonical first-three locators and bounded
declaration supplements, all already-bounded verification alternatives, and the
separate weak task matches. It retains exact source locations while omitting the
source body, ancillary locator/ranking detail and related sections. Every
collection reduction and omitted section is recorded in `initial_projection`.
The v2 wire packet compresses semantic JSON directly as `json+zlib`, with base64
data and an exact decoded-byte count. Compressing the former string-table
intermediate added overhead on the genuine corpus. Decoders retain both earlier
`json-string-table.v1` and `json-string-table.v1+zlib` formats. The uncompressed
string table remains the fallback for small or over-bound packets; JSON numbers,
booleans, nulls and array order retain their types and meaning. Decoder allocation
is bounded to 1 MiB for compressed encodings. Duplicate JSON keys, truncated,
concatenated or trailing compressed data and identity mismatches fail closed. Use
`decode_initial_packet` before interpreting data. Its semantic identity is
verified against the decoded view. Presentation references use the explicit
`decoded-initial-data` namespace. Initial MCP responses deliver the native packet
once in `structuredContent`, with the readable projection in text content.
Default full MCP responses retain their JSON mirror.

Initial compact/text rendering factors identical declaration qualifications and
common source locators into scope tables. Compact uses structured rows; text
retains its readable tables. Rows preserve declaration
order, exact ranges, future fields and field absence. All already-bounded initial
verification alternatives are displayed; a second five-row presentation cap does
not hide a relevant test. Unresolved task ownership may expose fresh test candidates
around three retrieved source declarations, with qualified reference or explicitly
weak source-identifier/task matches. Those candidates do not change edit/verification
selection or establish coverage, sufficiency, runtime behavior or repository absence.
The full packet and projection have distinct identities. Re-observing the full
mode may observe changed source, so consumers must compare the supplied full
packet identity before treating an expansion as the same observation.

In initial mode, weak matches use lossless `columns-rows.v1` encoding: the
`matches_encoding.columns` names each value in a `matches` row. Counts,
visibility, ordering and all match-scope/authority qualifiers are retained.
Unexpected row fields retain the original object encoding. The full mode
continues to return object rows.

Verification candidates use `columns-rows-with-extras.v1`. Common columns are
named once; each row also carries an extras object for fields that are not
present in every candidate. Decoding preserves missing versus null values and
rejects extras that overwrite a declared column. No bounded alternative is
removed merely because another verifier was selected.

Initial text now displays ownership status, freshness, ambiguity, source
locators and bounded verification candidates with native source pointers.
Qualification details remain in the native packet. Text rendering is stable
across JSON key ordering; display omissions do not establish absence.

The v2 backend matrix separates the hard `initial_size` gate from the
`initial_evidence` recall measurement. The workflow runner explicitly captures
default/full and initial responses at both revisions. Missing required proof
remains incomplete, while any known hard failure dominates missing proof.
Legacy oracles without independently declared initial checks or owner scope
cannot qualify those missing measurements.

The workflow v2 contract additionally supports explicit `modify`, `add`,
`delete` and `rename` transitions. Legacy v1 manifests remain readable as
modification workflows. Renames are caller-nominated, never inferred semantic
equivalence. Every transition endpoint is confined to its admitted source root.

See [the campaign contract](BACKEND_E2E_CAMPAIGN.md) for the read-only aggregate
entrypoint, current membership and remaining qualification requirements.

Initial class declaration lists use the same lossless encoding, with
`declarations_encoding.columns` naming `path`, `symbol`, `start_line`, and
`end_line`. The class scope, revision, generation, bounds, omission counts and
authority qualifiers are retained as object fields. Future declaration fields
keep object rows so encoding cannot discard newly admitted source facts.

The `backend-model-v1/source-oracles.json` source baseline reviews three genuine
FastAPI, Litestar and SQLModel problems. Both revisions bind exact upstream
commits, full repository-content identities and independently reviewed source
range hashes. Its expectations distinguish direct annotations, initializer
syntax and base expressions from runtime validation and inherited fields.
The remaining acquired model problems are not admitted by this baseline.

`source-oracles-expanded.json` separately reviews seven genuine problems across
the same three repositories, including inherited datetime declarations,
nullable/default distinctions and a changed class-variable annotation. The
shared `backend-model-v1/suite.json` and `grader.json` admit those seven source
transitions, with task and declaration observations graded together. Their
production paths are explicit caller input; these cases do not measure
answer-blind owner recall. The annotation-only case records verification
correspondence as unknown rather than manufacturing an existing test oracle.
Seven cases remain below the required twelve-problem capability breadth.

It exposed a generic observer defect: model declarations nested inside a
function or conditional were skipped. The selected-source observer now retains
those declarations by their exact class line. `include_class_fields=True`
additionally exposes ordinary annotated classes as
`python-annotated-class-syntax`, with direct field origins and base-expression
syntax. It does not infer a model role or resolve inherited/runtime fields.
The default continues to omit ordinary classes without recognized model-base
syntax. These source observations still require full revision, native and
actual CLI/MCP workflow qualification before capability promotion.

The public `repository_declarations` discovery mode now exposes this same
selected-source provider through CLI and official MCP, including its tracked
inputs and nested declaration bindings. Observation/explain remain caller-claim
projections. Discovery uses the existing current-source validation and rejects
mixed raw/source inputs; comparison packets cannot restore unselected providers.

The existing backend workflow runner also accepts optional
`declaration_observations` for both revisions. These contain only public
discovery inputs, separate from the grader's `declaration_oracles` source IDs,
range hashes and fact checks. Admission requires independently labeled source
for every nominated path. API and actual CLI/MCP declaration observations are
retained under the same stable repository snapshot and receipt identity as the
task packet. Their facts, authority, revision and transport results compose into
the common gates: any failure remains a failure, and omitted transport proof
remains incomplete. Nominated source disclosure does not establish answer-blind
owner recall or verification sufficiency.

```text
Observed repository fact/evidence: Direct class annotations and base expressions,
  including declarations nested in caller-selected source members.
Authority source: Existing declaration provider and canonical member bindings.
Completeness/freshness behavior: Existing file/group/field bounds, exact source
  revisions, incomplete semantic coverage and no negative-evidence authority.
Existing Hashmarks owner extended: Static Python backend declaration observer.
Consumer/execution responsibility explicitly not acquired: Model inference,
  runtime inheritance/validation, compatibility judgments or test execution.
Decision: OBSERVER
```

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
and exception-handler/async-for syntax, with exact UTF-8 source columns. Bare
awaited identifiers and context identifiers remain visible independently of
callee syntax. The shared Python
AST cache supplies one qualified tree to body and decorator observers; canonical
member bytes and the existing read-after-observation revision check remain the
authority. Oversized, unstable or unavailable parses stay unresolved. Nested
def/class/lambda subtrees are outside the declared body scope. Site truncation,
omitted functions and unsupported callee expressions remain explicit.
Nested functions selected by the reported line are observed as separate indexed
declarations; their sites never become sites of the enclosing function.

These observations can show `cancel`, `ack`, `commit` or `rollback` spelling in
source. They do not establish the receiver's API identity, actual execution,
message acknowledgement, transaction effects or task ownership. Call syntax is
not an exact caller-to-callee edge.

Task retrieval also discloses at most sixteen directly declared methods of the
first class within its canonical first three locators. Exact indexed class and
member ranges qualify lexical containment; nested classes, inherited methods
and similarly named classes do not expand that scope. The member list carries
its current source revision, index generation, bounds and omission counts.
Retrieval order, ownership and verification selection remain unchanged.
Runtime membership and negative evidence remain unestablished.

```text
Observed repository fact/evidence: Bounded direct indexed method declarations
  within an already retrieved class's exact source range.
Authority source: Existing CodeMap symbol/file index and current member digest.
Completeness/freshness behavior: Index-scoped counts and explicit omissions;
  force-checked source binding before and after disclosure, no runtime absence.
Existing Hashmarks owner extended: Task-local repository retrieval disclosure.
Consumer/execution responsibility explicitly not acquired: Choosing a method
  to edit, establishing runtime membership or reranking ownership/verification.
Decision: OBSERVER
```

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

The separate `backend-v1/function-boundaries.grader.json` records reviewed source
sites, exact declaration ranges, literal-line hashes and required uncertainty.
Its scoped-record checks require a site within the same named declaration;
matching a declaration in one record and a call in another cannot satisfy them.
The explicit source specimen pass retained twenty-four before/after observations
and 192 CLI/MCP format captures across the twelve pinned problems. This proves
that source syntax contract only. It does not add runtime semantics, invalidate
the separate revision/native gates or qualify twelve async problems.

The additional `backend-async-v1` corpus contains twelve distinct upstream
async-resource problems across aiokafka, SQLAlchemy, FastStream and Litestar.
It includes listener lifecycle and subscription-lock changes, with pinned
before/after archives and independently hashed declarations and literal sites.
Some problems change synchronous methods that manage async resources; the
corpus does not claim twelve async function declarations or runtime task proof.

Its `boundary_observations` inputs nominate source spans separately from the
`function_boundary_oracles` grader. The existing backend workflow observes
those spans before and after the genuine source transition, checks current
member revisions, rejects stale members on reopening, and grades all four
actual CLI/MCP formats. A failed syntax check also fails the common facts gate;
successful owner/revision measurements cannot compensate for it. Admission
rejects nonexistent paths named as existing verification files.

```sh
uv run --frozen --no-sync python -m scripts.repository_evaluation.run_backend \
  --suite benchmarks/repository_evaluation/manifests/backend-async-v1/suite.json \
  --sources-file /path/to/async-sources.json \
  --output-dir .hashmarks/backend-e2e/async-revision

uv run --frozen --no-sync python -m scripts.repository_evaluation.run_backend_native \
  --suite benchmarks/repository_evaluation/manifests/backend-async-v1/suite.json \
  --sources-file /path/to/async-sources.json --regenerate \
  --capture-root .hashmarks/backend-e2e/async-native/captures \
  --output-dir .hashmarks/backend-e2e/async-native/qualification
```

The native ring still qualifies explicitly nominated source specimens only.
Neither source nomination nor a passing native specimen report proves that an
initial task response found the needed declaration or test. Those facts,
response economics and unknown runtime boundaries retain separate qualification.

Real debugging acquisitions are also available without a database service:

```sh
uv run --frozen --no-sync python -m scripts.repository_evaluation.capture_backend_failure \
  --sources-file .hashmarks/backend-e2e/sources/sources.json \
  --workflow sqlalchemy-logging-token-reset \
  --output-dir .hashmarks/backend-e2e/runtime-failures/logging-token-reset
```

The second supported specimen is `sqlalchemy-aggregate-strings`. Each runs in a
fresh interpreter against the explicitly selected source package, records actual
exceptions and repository stack frames, and checks source identity before and
after acquisition. Bytecode writes are disabled. Non-repository frames are
counted separately; the full traceback is retained. These are external QA
producer captures, never Hashmarks execution or diagnosis authority. A successful
invocation does not establish repository-negative evidence. Stack-to-source,
symbol and transport qualification remain separate checks, and the debugging
corpus still requires broader genuine problems and repositories.

The existing canonical source member observer is now available through the CLI:

```sh
hashmarks source-observation lib/sqlalchemy/engine/characteristics.py \
  --line 145 --presentation compact
```

This command refreshes the selected member through CodeMap and exposes the same
revision-bound line anchors and context as the API/MCP observer. It does not
execute repository code, interpret a traceback, establish runtime frame identity
or choose a repair. Invalid source lines fail before index state is created.

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

## Annotated decorated methods

The optional computed-field source oracle records a genuine Litestar change
whose new model fixture declares a decorated `status()` method returning
`Optional[Status]`. The earlier fixture does not contain this new declaration;
its existing model field syntax is baseline evidence only. The oracle does not
claim a pre-change computed-field declaration or runtime validation outcome.

Observed repository fact/evidence: direct annotated, decorated methods inside a
selected Python class, their decorator syntax and return annotations.
Authority source: the selected current source member's Python AST and exact
source ranges.
Completeness/freshness behavior: selected-file, incomplete semantic coverage;
24 method and eight decorator bounds fail closed; canonical declaration source
bindings govern freshness. Nested methods and inherited declarations are not
folded into the enclosing class.
Existing Hashmarks owner extended: `StaticPythonBackendDeclarations` and the
canonical repository-declaration provider/binding/presentation surfaces.
Consumer/execution responsibility explicitly not acquired: interpreting a
method as a runtime field, evaluating decorators, validation or serialization.
Decision: OBSERVER.

Method observations retain `runtime_field_role=unknown` and
`runtime_binding=not-established`. Decorator argument values are not copied;
only the existing bounded call syntax is exposed. This source primitive does
not establish method execution, framework identity, or a complete model schema.

## Model declaration corpus checkpoint

`backend-model-v1` now admits twelve genuine changes across FastAPI, Litestar
and SQLModel, with twenty-four exact source trees. The separately reviewed
source oracles cover direct and nested declarations, base expressions,
annotations, direct initializer syntax, nullable defaults, class-variable
annotations, SQL field keyword names and an annotated decorated method.
New after-only fixtures are distinguished from existing before baselines;
those baselines do not establish pre-change declarations of the new models.
An annotation-only change with no reviewed direct test retains an explicitly
unknown verification oracle. Exact qualified names distinguish same-named
classes for native targeting.

The selected-source API ring `model-twelve-source-v2` passed all twenty-four
source observations. The `model-computed-native-v3` specimen regenerated both
native captures and passed exact definition-token, source-binding, stale
reopening, and all four CLI/MCP format checks. Its after specimen targets the
essential `Result.status` method at line 18, rather than another class in the
same file. Removed specimen source is rejected with negative-evidence authority
remaining false; ambiguity in a still-present source remains an error.

The genuine computed-field and item-bound revision workflows passed required
facts, authority, revisions, freshness and CLI/MCP presentation. Initial
response size still fails. The `sa_type` workflow still misses a required
verification path, and the Iterable workflow still misses its required test in
the bounded returned candidates despite recovering more qualified references.
The initial compact/text measurements currently use the default full packet;
they do not certify the separate initial projection. None of these measurements
promotes a capability to 5/5. The wider twenty-capability goal remains incomplete.
