# Backend E2E campaign

**Development sequencing:** the active
[canonical component rewrite](../plans/CANONICAL_COMPONENT_REWRITE_PLAN.md)
comes first, with breaking Python APIs and explicit owners. Implementation is
in progress under the user's explicit instruction.
This broad campaign is retained as follow-on research qualification; its
unchanged all-capability requirements do not gate each owner-sized repair.

This is Hashmarks development qualification, not product execution or
certification authority. The target is independently supported 5/5 evidence
for all twenty backend capabilities. Current corpus membership is not a claim
that those capabilities have passed.

The active successor corpus is
`benchmarks/repository_evaluation/manifests/backend-campaign-v2/campaign.json`:
89 workflow entries, 59 distinct upstream problems, eight suites. The selected-call
catalog contributes twelve capability-specific views of existing problems across
three repositories. Its source oracles and witness membership are supplied;
independent review and full qualification remain open. Current gaps and exact
repair evidence are maintained in [the remaining plan](BACKEND_E2E_REMAINING_PLAN.md).

## Historical baseline membership

The frozen campaign is
`benchmarks/repository_evaluation/manifests/backend-campaign-v1/campaign.json`.
It binds the three existing suites and their source-oracle digests. The shared
active schemas are `hashmarks.backend-evidence-campaign.v4` and
`hashmarks.backend-evidence-matrix.v5`; older reports are historical evidence.
The directory name identifies the frozen source corpus, not the active report
schema version. The shared
matrix owns the unchanged minima: twelve distinct genuine problems and three
repositories per capability. Formats and repeated variants do not add breadth.

| Capabilities | Existing catalog | Problems | Repositories |
| --- | --- | ---: | ---: |
| 1, 3, 5, 6, 7, 17 | backend-v1 | 12 | 3 |
| 10 | backend-model-v1 | 12 | 3 |
| 12 | backend-async-v1 | 12 | 4 |
| 2, 4, 8, 9, 11, 13, 14, 15, 16, 18, 19, 20 | No admitted campaign suite yet | 0 | 0 |

Separate debugging, dependency, heldout and native captures do not automatically
fill those rows. Their precise problems, semantic oracles and transport proof
must be admitted before they contribute.

## Observation contracts

### Bounded call-collection presentation ownership note

Observed repository evidence: the node, direct-call and unresolved/external-call
collections already admitted by Structural Locality. Authority source: the
existing CodeMap packet, with exact native collection references and member
counts. Freshness/completeness behavior: preserve every member and qualifier
within the producer's existing bounds; empty collections do not establish
repository or runtime absence. Existing owner extended: evidence presentation.
Consumer/execution responsibility not acquired: runtime dispatch, path inference,
edit selection, test execution or sufficiency. Decision: OBSERVER.

### Candidate verification disclosure ownership note

Observed repository fact/evidence: bounded test references and task matches around
already retrieved source declarations while task behavior ownership is unresolved.
Authority source: existing indexed declaration, qualified-import and verification
reference owners; exact source/test revisions accompany the correspondence.
Completeness/freshness behavior: three source locators and eight returned test
candidates at most; stale or denied sources are excluded; omitted/unknown evidence
does not establish absence. A parent class is a lexical declaration subject only.
Existing Hashmarks owner extended: task evidence and verification candidate disclosure.
Consumer/execution responsibility explicitly not acquired: edit or verification
selection, behavior ownership, test execution, coverage and sufficiency.
Decision: OBSERVER.

### Lexical enclosing declarations ownership note

Observed repository fact/evidence: exact indexed function declarations enclosing
a retrieved nested function, with source spans and revision binding.
Authority source: existing CodeMap symbol parent and span records.
Completeness/freshness behavior: visible current indexed sources only; four
enclosing function declarations at most; unresolved parents and bounds remain
explicit; no negative evidence is derived.
Existing Hashmarks owner extended: task-local indexed declaration disclosure.
Consumer/execution responsibility explicitly not acquired: behavior ownership,
runtime execution, repair selection, and verification sufficiency.
Decision: OBSERVER.

Each workflow retains both stages, full/default and explicit initial profiles,
API packets, actual CLI/MCP responses, byte/token measurements and source delta.
Required observations use failure-preserving three-state composition:
known false dominates missing; missing is incomplete; an empty set is not proof.
Initial compact/text replies have a hard 4,000-token ceiling, counting the entire
actual CLI or MCP reply. Initial MCP carries one native v2 packet plus its
readable projection. Recall is a separate measurement. Every capability now
requires presentation preservation, rather than only capability 17.

Debugging correspondence uses frozen `debug_frame_units` and per-unit
`debug_frame_observations`, not one boolean per problem. Each observation has
`unit_id` and `correspondence` (true, false or null). Frame identities are local
to the repository and genuine problem; variants and transports cannot add units.
Missing reviewed units remain incomplete even if a summary boolean says true.
Recall fails when its best possible result cannot reach the threshold, otherwise
missing units remain incomplete. JSON oracle comparisons distinguish boolean,
integer and floating-point values recursively.

An optional stage-specific `owner_oracle` describes `scope` (`file` or `symbol`),
`resolution` (`unique`, `ambiguous` or `unknown`) and `candidates`. Symbol
candidates require path, qualified name and exact start/end lines bound to an
independent source label. A legacy path label alone cannot qualify an exact
symbol assertion. `initial_checks` must be independently frozen; their absence
is not a successful initial-evidence measurement.

Workflow v2 `transitions` entries carry `kind`, `before_path` and `after_path`.
Additions have a null before endpoint; deletions have a null after endpoint;
modifications keep the same path with changed bytes; renames explicitly nominate
different paths. `changed_paths`, when provided, must equal the endpoint union.
Sources remain immutable; workflow copies are disposable.

Native preparation includes all labelled files and only genuinely reviewed
optional verifiers. Explicit `native_observations` may nominate stage-specific
`language` and `paths`. Python and TypeScript specimens use their respective
installed producers. Native v4 reports retain source identities, observation
artifact hashes and capture artifact hashes. Their scope remains source binding
and native transport; they cannot prove an execution path or verifier recall.
Reports require every target's API/CLI/MCP and definition-token artifacts plus
exact target membership. Aggregation recomputes native gates from those bytes;
a supplied passing summary is not qualification proof. Disposable stage source
membership comes from the union of nominated files in the actual pinned trees,
not from the producer's selected capture files. An unchanged file can have a
matching source binding while its old capture remains generation-stale; neither
dimension strengthens the other.

## Remaining implementation tickets

### Remaining-work checkpoint

The prior 22-file repair is committed at `70283d2`. The retained four-workflow
report at `.hashmarks/backend-e2e/implementation-20261013/v4-class-scope/summary.json`
is FAIL: cancellation passes its current gates; sender and metadata expose their
changed methods but exceed the initial response limit, and sender, metadata and
logging omit the reviewed verifier candidates. Initial MCP compact/text maxima
are 5,167/4,994 tokens for sender and 4,774/4,397 for metadata.

The current three catalogs have no independently frozen display checks or
capability-proof membership. Their 36 entries include repeated upstream problems,
which do not contribute additional breadth. The missing twelve capability rows
still require genuine admitted corpora. No current capability rating is implied.

The implementation order is: retain the baseline; repair initial size; repair
verification disclosure; finish source-reviewed oracles; extend all-family
witnesses/regrading; retain aggregate input rejections; qualify genuine
add/delete/rename and fresh native captures; admit missing corpora; repair their
generic omissions; clear full Ty/Pyright; then freeze and qualify final economics,
bounded regression batches and independent artifacts. The final gate includes
full typing, not only typing of changed files.

Local measurements and logs belong under `.hashmarks/backend-e2e/remaining-work/`.
Historical reports remain unchanged. A renderer-only replay is an iteration
measurement and must be followed by actual API/CLI/official-MCP acquisition.

Initial transport compresses semantic JSON directly using bounded zlib/base64
when smaller; the v1 string table remains the uncompressed fallback. Decoders also
accept historical compressed string tables. The semantic packet identity
is computed from the unchanged decoded facts, never compression bytes. Decoders
retain uncompressed v1 support and reject invalid sizes, truncated streams and
trailing/concatenated data. Payloads above the compression allocation bound use
the existing uncompressed representation without losing valid packet capacity.
Readable declaration tables factor only JSON-identical qualifiers and common
paths/prefixes. Table rows retain native order and future fields; shared metadata
never makes boolean false equivalent to numeric zero.

Compact initial verification groups also factor identical locator qualifiers
into `group.locator_qualifiers`. A reader reconstructs each locator as
`{**group.get("locator_qualifiers", {}), **finding["details"]}`. Path, source
references and any differing qualifiers remain on the individual finding.
This preserves all admitted alternatives while avoiding repeated qualification
fields; it does not change verification selection or ownership authority.

### Current implementation measurements on 2026-10-13

The fresh four-workflow CLI measurement at
`.hashmarks/backend-e2e/remaining-work/four-workflow-cli-03/summary.json`
retains the required methods and reviewed test candidates at both revisions.
Maximum actual initial compact/text sizes are 2,732/2,516 tokens for
cancellation, 3,752/3,502 for sender, 3,691/3,435 for metadata and 3,184/2,832
for logging. This report is INCOMPLETE because MCP was deliberately omitted;
these measurements do not establish the complete transport gate or 5/5.

The focused source ring passed 221 tests (four MCP tests excluded), and the
separate official-MCP/presentation ring passed 51 tests. These are bounded
iteration checks. The subsequent Ruff cleanup commit introduced a watcher-test
syntax error, callback parameter mismatches and missing annotation imports.
Their repair passes 21 focused tests and full collection (3,916 tests).

Task-evidence composition now narrows each nested mapping from one observation
and records precise types for collection/token fields owned by existing packet
producers. The production owner passes both Ty and Pyright; its focused public
surface ring passes 92 tests. This is an internal typing repair, with no new
observer responsibility or changed authority/selection rules. Full project Ty
still reports 4,203 diagnostics and Pyright 6,595 errors and eight warnings.
Neither full typing gate is green.

Fresh acquisition after that typing repair is retained at
`.hashmarks/backend-e2e/remaining-work/four-workflow-public-typed-01/summary.json`.
All four workflows pass every current workflow gate at both revisions through
API, CLI and official MCP. Maximum actual initial MCP compact/text sizes are
2,822/2,280 tokens for cancellation, 3,952/3,267 for sender, 3,876/3,197 for
metadata and 3,320/2,595 for logging. The report remains INCOMPLETE because four
passing workflows do not close the twelve-problem corpus or independent
capability-proof requirements.

Fresh native qualification at
`.hashmarks/backend-e2e/remaining-work/native-fresh-01/qualification/summary.json`
passes all twelve existing backend workflows, including both source bindings,
definition tokens, stale reopen checks and CLI/MCP. Its scope is nominated SCIP
specimens; it does not establish composed backend sufficiency or 5/5. Installed
producer and runtime identities are recorded as temporary QA provenance.
The broader fresh native ring's initial run passed 59 tests and had 33 LSP
fixture setup errors from a missing TypeScript runtime. That run remains failed;
after installing the prerequisite, the complete fresh ring passed all 92 tests.
Its log is
`.hashmarks/backend-e2e/remaining-work/semantic-evidence-live-repaired.log`.
This is fresh uv/Maven/SCIP/LSP production, not committed-capture replay.

Two actual SQLAlchemy runtime specimens are retained under
`.hashmarks/backend-e2e/remaining-work/runtime-fresh-01/`. Logging reproduces an
AttributeError before the change and a usable connection afterward. Aggregate
strings reproduces the unintended TypeError before the change and the expected
unsupported-dialect CompileError afterward. Repository stack frames are retained
without asserting causal diagnosis or broad debugging qualification.

The existing twelve base problems, model catalog and async catalog still lack
complete independently reviewed display/adversarial proof membership. The
twelve missing capability catalogs, remaining witness families, fresh native
producer runs, full bounded regression batches, comparable economics and final
artifact qualification remain required. Historical measurements and the first
independent source artifact do not qualify later modified source bytes.

### Owned-file native-query repair on 2026-10-14

The first broader regression pass completed batches 0–3 and failed batch 4:
native request-local claims were omitted when the admitted owner was a file
without a symbol locator. The repair keeps file ownership unchanged and uses
the existing source resolver to qualify the producer's explicit query within
that file. Matching snapshot bytes, admitted/current source, a unique indexed
declaration and an unambiguous declaration-token cursor are required. Keyword
or body positions, stale snapshots, other files, repeated tokens and multiple
subjects remain unqualified. Query cursors may lie inside a unique token;
result-endpoint token rules retain their existing stricter behavior.

The relationship count scope explicitly says `owned-file-query`; it does not
claim a uniquely established symbol owner. Captures remain request-local and
previous packets remain comparison input. No inferred, transitive or persistent
semantic relationships are introduced.

```text
Observed fact: Producer-nominated declaration/relationship claims within an
  already admitted owner file, with exact source-byte/token correspondence.
Authority source: Existing ownership qualification and relationship source resolver.
Completeness/freshness: Existing capture/source bounds and uncertainty; unresolved
  nominations are accounted for, never promoted to absence or unique ownership.
Existing owner extended: Task evidence and native relationship projection.
Consumer/execution responsibility not acquired: Edit decisions, runtime compatibility,
  graph traversal, verification execution or certification.
Decision: OBSERVER
```

Initial compact/text views retain these records using lossless native value
references for JSON-identical duplicate evidence/bindings. A compact finding's
`details` contains `record`, `value_refs` and `value_ref_base`; the text line
`Producer relationships:` carries the same wrapper. Restore each destination
JSON pointer from decoded native data at `value_ref_base + source_pointer`.
Pointers use ordinary JSON-pointer escaping. Different/future fields and
boolean/numeric distinctions are retained. Qualification contexts are removed
only when their values are already identically present in that record.

Independent readers reconstruct every original value, including escaped future
keys, Unicode and differing qualifications. The controlled public-transport
regression at `.hashmarks/backend-e2e/remaining-work/semantic-wire-current/`
measures actual CLI compact/text at 3,610/3,627 tokens and official MCP at
3,796/3,391. This controlled case does not add genuine corpus breadth.

The earlier four-workflow, native, live-ring and source-artifact measurements
precede this production repair. They remain historical; affected qualification
must be repeated on the new observer bytes. Full typing, missing corpora and
the independent capability-proof requirements still prevent a 5/5 claim.

### Regression and typing checkpoint on 2026-10-14

The repaired candidate's focused source/native/presentation ring passes 143
tests, including the independent reader for the initial relationship view.
The remaining deterministic development batches 12–15 pass, completing the
bounded regression sequence. Earlier failing batch attempts remain retained;
their repaired batches and the affected MCP catalog/fixture checks pass. These
are source regression results, not twenty-capability qualification.

The full configured typing measurements at
`.hashmarks/backend-e2e/remaining-work/typing-current-ty.log` and
`typing-current-pyright.log` remain red: Ty reports 4,695 diagnostics and Pyright
4,837 errors with zero warnings. Static re-exports now describe the existing
lazy public imports to type checkers without changing runtime loading. More
precise types expose previously obscured errors; counts from older type runs
are historical measurements, not a green baseline.

The modified observation/presentation owners and the new tests pass scoped Ty.
The expanded scoped Pyright run also includes the MCP contract owner and exposes
three errors there: selector defaults include `None`, SDK model lists need a
covariant read-only sequence parameter, and the server surface is attached
dynamically. Repair these at their existing owners, then remeasure both tools;
do not hide them with ignores, blanket `Any`, exclusions or narrower project
configuration. The broader full-project typing backlog remains required.

Fresh four-workflow and twelve-specimen native captures are being acquired
against stable current observer/evaluator bytes. Only completed, identity-bound
reports may replace the historical qualification results above. A later
production repair invalidates their current-candidate status again.

### Responsibility and authority repairs on 2026-10-14

Classification: **EXTRACT RESPONSIBILITY** for task presentation, bounded task
retrieval supplements and verifier correspondence; **KEEP COHESIVE** for the
canonical indexing lifecycle/store. The measured reasons are the required
quality gate's three oversized owners, their distinct observation contracts,
and reproduced typing/authority failures. This is a bounded repair, not a new
refactoring queue or an extraction requirement based on LOC alone.

| Responsibility | Current owner | Contract retained |
| --- | --- | --- |
| Default/initial task presentation | `hashmarks/evidence_presentation_task.py` | Existing producer facts, order, references, uncertainty and omissions |
| Bounded task retrieval supplements | `hashmarks/codemap/task_evidence_retrieval.py` | Existing ranking/bounds; no edit or verification selection authority |
| Existing verifier/edit-authority correspondence | `hashmarks/codemap/verification_ownership.py` | Existing CodeMap links; no inferred semantic graph or execution authority |
| Stable indexing/persistence and measured store counts | Existing lifecycle/store owners | Existing source admission, freshness and persistence rules |

The canonical presentation builder still owns reference escaping, counts and
omission accounting. Task presentation imports its type only; the runtime
dependency goes from the generic presentation entry to the task renderer.
Existing CodeMap mixins inherit each extracted implementation once, with no
forwarding compatibility implementations or additional state/cache owners.
The architecture test's canonical verifier location was updated to the new
implementation owner; its core response-validation requirement is unchanged.

Sixteen retained before/after default/initial packets yield 48 exactly matching
public structured/compact/text projections before and after the extraction.
This comparison retains JSON type distinctions and is recorded in
`task-presentation-refactor-comparison.json`. It proves projection preservation
for those packets, not fresh acquisition or additional genuine corpus breadth.
The presentation/native ring passes 144 tests; the affected ownership/task
contract ring passes 177 tests after correcting the architecture-test location.
The configured size/complexity gate now reports zero rule findings and zero
oversized production files. The indexing repair passes 100 focused regressions.

Negative-evidence review reproduced a separate generic defect through the
public API: without an admitted edit owner, the verifier graph reported
`unowned=true` and `ambiguous=false`, although the underlying observation had
no eligible verifier scope. The repaired summary preserves `null` for unknown
states, derives ambiguity from the observed candidate population before display
bounds, and carries `verification_qualification` from the existing relevance
owner. Qualified empty observations still admit absence; observed positive
candidates remain visible. Boolean counts cannot impersonate integer counts.
Actual API/CLI evidence is retained in `verifier-negative-after.json`; 143
affected tests pass, including bounded, hidden-alternative and unknown cases.
Further inspection of the large-reference probe reproduced a lower-layer
lookahead defect: the semantic reader requested 1,025 rows to detect its 1,024
reference bound, but both the store and generation-bound session clipped the
request to 1,024. The actual indexed fixture contains 1,031 reference rows and
was reported complete. The shared reference-query ceiling now admits the
lookahead row for global and qualified-suffix reads. Semantic consumers retain
their existing 1,024 bounds and qualify truncation themselves. Actual-source
regressions cover an exactly full, complete window, an overfull window and
expansion of a smaller cached prefix. The repaired fixture reports incomplete
scope, denied negative evidence and unknown verifier ownership; its retained
evidence is `reference-lookahead-after.json`. This controlled fixture adds no
genuine corpus breadth. Captures preceding this repair remain historical.

The MCP contract, indexing/store, extracted presentation/retrieval/correspondence
owners pass scoped Ty/Pyright. This does not make every modified owner green:
the retained verification-relevance implementation still has typing debt.
The full configured measurements in `typing-final-observer-ty.log` and
`typing-final-observer-pyright.log` remain red at **4,649 diagnostics** and
**4,786 errors, zero warnings**, respectively. No typing scope, threshold,
ignore or dependency configuration was weakened.

Fresh acquisition for this observer passes all twelve nominated native
specimens at `native-final-observer/qualification/summary.json`. The fresh
uv/Maven/SCIP/LSP and transport ring passes 92 tests in
`semantic-evidence-live-final-observer.log`. Four-workflow composed acquisition
and the final deterministic batch sequence must finish before their results
are admitted. None of these bounded results closes the twenty-capability 5/5
requirements below.

After the reference lookahead repair, fresh acquisition at
`four-workflow-reference-candidate/summary.json` passes every current workflow
gate for cancellation, sender, metadata and logging at both revisions through
API, CLI and official MCP. Its aggregate status is **INCOMPLETE**, because four
passing workflows do not supply the full corpus or independent capability
proofs. The contemporaneous twelve-specimen native report at
`native-reference-candidate/qualification/summary.json` is PASS with no missing
workflows, and `semantic-evidence-live-reference-candidate.log` records 92 fresh
producer/transport tests passing. Full configured typing remains red at 4,649
Ty diagnostics and 4,786 Pyright errors, with zero Pyright warnings. The
size/complexity gate passes with no oversized files or rule findings. The
all sixteen reference-candidate development batches pass in
`dev-batches-reference-candidate.log`. Earlier partial/failed attempts remain
historical and are not substituted for this completed sequence.

Maximum current initial compact/text estimated-token counts across both
revisions are:

| Workflow | CLI compact/text | MCP compact/text |
| --- | --- | --- |
| Cancellation | 2,730 / 2,514 | 2,820 / 2,278 |
| Sender | 3,754 / 3,504 | 3,952 / 3,267 |
| Metadata | 3,687 / 3,431 | 3,873 / 3,194 |
| Logging | 3,184 / 2,831 | 3,320 / 2,595 |

These are actual consumer-visible transport measurements using the existing
estimator. They do not substitute for unseen workflow/format proof or an
independently frozen essential-fact population.

### Earlier implementation checkpoint

The three existing catalogs now use workflow v2. All 36 workflows validate
against their pinned trees, including two genuine model-fixture additions.
Python symbol labels also validate qualified declaration names against cached
AST snapshots; a matching range digest alone no longer qualifies a wrong name.

The twelve base tasks now have behavior descriptions without the expected
owner's exact method name. Their original explicit-target descriptions remain
as metadata. File-owner and changed-symbol oracles were reviewed from pinned
source diffs. Review records explicitly retain pending test-correspondence,
display and capability-adversarial work; they are not complete review claims.

Shared task grading now has artifact/source-bound fact witnesses. Ordinary
aggregation recomputes task, initial, stale, delta, boundary and declaration
gates, verifies API witnesses, and checks response/size metadata against actual
consumer-visible bytes. Native regrading performs that wire check too.
Capability qualification requires reviewed positive and adversarial witness
membership; tags alone cannot establish 5/5. Recall qualification also requires
explicit eligibility and representative eligible populations.

Native transition observations now include every prior target, with explicit
transition membership. Fresh-capture preflight checks all selected destinations
before acquisition. Non-ASCII token prefixes remain incomplete until their
producer coordinate encoding is qualified, rather than being graded as a
false definition-token contradiction.

The genuine blind cancellation workflow exposed a retrieved nested helper
whose enclosing method was absent. Bounded indexed enclosing declarations now
retain that exact source locator without granting ownership/runtime authority.
The repaired workflow passed every current gate through API, CLI and official
MCP; its initial MCP compact/text replies measured 3,141/2,534 tokens at both
revisions.

The complete twelve-problem run at
`.hashmarks/backend-e2e/implementation-20261013/base-blind-twelve/summary.json`
reported FAIL: one workflow passed every current gate, while eleven retained
retrieval, changed-symbol or verification omissions. This is an iteration
measurement, not final-candidate qualification. Later grading/validation edits
require a new identity-bound measurement. Do not change expected facts to match
these omissions. A source fact already carried in a qualified class-declaration
record is admissible at that location; it need not be duplicated as a top-level
retrieval row.

Latest focused regression ring: 136 tests passed. A separate official MCP and
presentation ring passed 40 tests before the final grading edits. Ruff,
compilation and scoped typechecks passed. Full project typing, fresh acquisition,
all missing capability catalogs, complete witness coverage, final bounded
batches and artifact qualification remain unfinished.

The repair and disclosure foundation is implemented, but this campaign is not
5/5. Complete these dependencies before making that claim:

1. Freeze independently reviewed owner, essential-initial, display and authority
   oracles for each existing genuine workflow; migrate active workflow contracts
   to v2. Explicit-target variants do not count as blind-owner recall.
2. Finish source-bound gate witnesses and shared pure regrading for all claim
   families. Bind every admitted test, callee, diagnostic frame and declaration
   source revision, not only the candidate owner file.
3. Qualify every prior native target across unchanged/modified/deleted and
   capture-scope transitions. Separate fresh acquisition from replay. Missing
   producers or unsupported token encodings are incomplete, not passing proof.
4. Add independently admitted genuine corpora for the twelve missing capability
   rows above, including real failures, contracts, messaging, transactions,
   dependency/build transitions and declared cross-repository boundaries.
5. Repair each demonstrated source/verification omission generically through its
   existing observer owner; do not put oracle names or framework exceptions in
   production ranking or analysis.
6. Freeze comparable cold/warm/incremental/churn economics after correctness
   repairs, then measure five paired samples and same-version noise controls.
7. Requalify all twenty rows, all stages/profiles/formats/transports, genuine
   native/dependency rings, heldout owners, bounded development batches and the
   final independent source artifact. Preserve FAIL and INCOMPLETE until that
   exact evidence exists.

## Read-only aggregation

Run each suite through the existing entrypoints. `BACKEND_SUITE` selects the
suite without duplicating Make targets. Use distinct output directories for
different candidate identities.

```sh
make backend-evidence-dogfood \
  BACKEND_SUITE=benchmarks/repository_evaluation/manifests/backend-model-v1/suite.json \
  BACKEND_SOURCES=/absolute/path/to/model-sources.json \
  BACKEND_OUTPUT=/absolute/path/to/model-report
```

Supply a sources JSON mapping campaign source IDs to exact extracted trees.
Supply a reports JSON keyed by campaign suite IDs:

```json
{
  "backend-v1": {
    "workflow_report": "/absolute/path/to/workflow/summary.json",
    "native_report": "/absolute/path/to/native/summary.json",
    "capture_root": "/absolute/path/to/native-captures"
  }
}
```

Missing suite reports remain incomplete. Optional native report fields are
required when native proof is supplied. The aggregator validates current
observer/evaluator identity, pinned source/oracle identity, completed receipts,
retained artifact bytes and native acquisition/binding scope. Historical v1
native reports cannot provide the newly required v2 artifact proof.

```sh
uv run --frozen python -m scripts.repository_evaluation.aggregate_backend \
  --campaign benchmarks/repository_evaluation/manifests/backend-campaign-v1/campaign.json \
  --sources-file /absolute/path/to/campaign-sources.json \
  --reports-file /absolute/path/to/reports.json \
  --output-dir .hashmarks/backend-e2e/campaign/aggregate
```

The command emits `summary.json` and `summary.md`. It only reads admitted
measurements; it never launches producers or selected work. Exit zero requires
the complete campaign to pass. Rejected or incompatible inputs cannot qualify.
Each selected input is retained as ADMITTED, MISSING or REJECTED, with its digest
and reason when available. Rejected reports make the aggregate FAIL while valid
unrelated reports remain visible. Missing required inputs remain INCOMPLETE;
optional native replay omission does not imply acquisition or binding proof.
Frozen campaign/source/oracle admission still fails closed before report grading.

Task, boundary and declaration fact witnesses retain each captured context.
Delta witnesses bind reviewed before/after source revisions separately, even when
both endpoints use the same repository path. Shared regrading recomputes these
witnesses from artifacts rather than trusting their supplied summaries. Debugging,
native, dependency, service, authority/freshness and economics witness families
still need their complete reviewed membership before all twenty rows can qualify.

## Remaining work before 5/5

The successor definitions and detailed implementation handoff are available in
[`BACKEND_E2E_REMAINING_PLAN.md`](BACKEND_E2E_REMAINING_PLAN.md). The original
campaign below remains historical; the successor initially retains its 36
entries without asserting new independent review or capability qualification.

The following tickets remain the implementation handoff. Complete a ticket's
named evidence contract before changing its status; a focused pass or additional
capability tag cannot substitute for its missing proof.

| Ticket | Current state | Next concrete implementation and proof |
| --- | --- | --- |
| T00 — Baseline | Retained | Preserve failed and incomplete reports; bind each new report to actual observer/evaluator and source bytes. Do not overwrite earlier measurements. |
| T01 — Initial size | Four-workflow proof; broader population open | Finish the current reference-candidate capture, then run all 36 catalog entries through initial API/CLI/MCP. Require compact/text to retain essential facts and stay within the 4,000 estimated-token limit at both revisions. Any repaired population must be acquired again. |
| T02 — Verifier disclosure | Four reviewed workflows pass; authority repairs added | Check all existing reviewed verifier paths through the public initial reply. Keep candidates separate from edit/verification selection; preserve bounded scope, source revision and unknown relationships. Retain the real-index lookahead regressions. |
| T03 — Independent oracles | Open | For every catalog entry, review the pinned source/change and existing tests without using candidate output as the oracle. Freeze owner scope, eligible ambiguity, essential initial facts, default/initial display checks and positive/adversarial capability witness membership. Bind facts to exact source ranges/revisions. Do not supply oracle hints to product calls. |
| T04 — All-family witnesses | Partial | Reuse `FactObservation`, canonical witness identity and pure regrading. Task, declaration, boundary and delta witnesses exist. Add artifact/source-bound witnesses for authority, freshness, native claims, runtime-frame correspondence, dependencies, nominated services and economics. Live grading and retained-artifact regrading must use the same semantic owner; changed bytes or missing source bindings cannot preserve PASS. |
| T05 — Aggregate input accounting | Implemented regression ring; final admission open | Aggregate every expected input with ADMITTED/REJECTED/MISSING status, exact digest and regrading. Exercise malformed, unknown-suite, changed-artifact and omitted-required-input cases. Known failure dominates missing proof; required missing work stays INCOMPLETE. Retain valid inputs alongside rejection reasons. |
| T06 — Genuine transitions/native acquisition | Existing native specimens pass; expanded coverage open | Admit genuine add/delete/rename tasks and independently label unchanged versus deliberately invalidated source bindings. Preflight every required producer before any acquisition. Fresh captures and offline replay are separate evidence; qualifying a nominated native specimen does not qualify composed task sufficiency. |
| T07 — Missing catalogs | Open | Build the twelve missing capability catalogs listed below, each with at least twelve distinct upstream problems across three admitted repositories. Reuse a problem across capabilities only when each capability has independently reviewed evidence; variants/transports do not add breadth. Freeze eligibility before measurement. |
| T08 — Generic observer gaps | Active repair queue | Run the frozen problems first, retain omissions/false claims, repair the existing observer owner, and add a minimal neutral regression. Re-run the same public workflow and adjacent adversaries. Keep external dependency implementations and consumer reasoning/execution outside the investigation. |
| T09 — Full typing | Red | Repair bounded owner groups using precise producer result types and consumer narrowing. Start with retained verification relevance and session/query typing debt, then qualification owners and test fixtures. Run scoped Ty/Pyright and affected behavior tests per group; periodically remeasure the unchanged full configuration. No blanket `Any`, ignores, exclusions or weakened tool policy. |
| T10 — Final qualification | Open | Complete fresh public/native acquisition, all named regression batches, comparable cold/warm/incremental measurements with a same-version noise control, and independent heldout evaluation. Build one deterministic source ZIP with modes/untracked source included and smoke-test its independent extraction. Broader rebuild/wheel/sdist proof belongs to final promotion. Full configured quality/typing and all twenty independent capability rows must pass. |

T07 still needs capabilities **2, 4, 8, 9, 11, 13, 14, 15, 16, 18, 19 and 20**.
Their minimum targets are directly evidenced call segments, real failure frames,
handlers, producer/consumer data, DI/configuration, messaging, transactions,
dependency changes, independently versioned nominated services, additional
native evidence, Python/TypeScript backend behavior and comparable economics.
Existing capability labels alone do not qualify any of these rows.

For T09, first reproduce each owner's current diagnostics from the full logs.
Inspect the value's producer before adding its type; do not cast external
unvalidated input into certainty. Preserve runtime/source decisions while
repairing types. A parser that actually returns a list must not be declared a
set merely to silence a checker. Once an owner passes scoped checks, run its
existing behavioral/authority ring before proceeding to another owner. The
remaining full-project diagnostic count is a failing gate, never a suppression
baseline or a rating.

1. Review explicit owner scopes and essential initial facts for existing cases.
2. Finish scoped authority checks for every exact relationship family and freeze
   eligibility for blind owner, debugging-frame and initial-recall measurements.
3. Qualify genuine add/delete/rename workflows, beyond controlled regressions.
4. Extend native qualification to every nominated required target and prove
   unchanged bindings separately from deliberate invalidation adversaries.
5. Admit runtime-debugging, dependency, language and economics measurements under
   matching identities and scopes; do not substitute SCIP binding proof for them.
6. Reduce actual initial MCP size without losing admitted verifier alternatives,
   source facts, uncertainty or omission accounting. Readable text alone does
   not close the size requirement.
7. Repair reproduced generic verification misses using qualified identity and
   locality rather than oracle hints or larger retrieval bounds.
8. Complete the twelve missing capability catalogs with twelve genuine problems
   across three repositories each, reviewed independently of candidate output.
9. Run current fresh native captures, all CLI/MCP formats, comparable economics
   controls and the complete campaign aggregate.
10. Complete configured lint/type checks, deterministic bounded regression
    batches and the repository's final artifact qualification.

Do not mark this campaign complete while any required proof is missing or any
hard authority, freshness, presentation or initial-size violation remains.
