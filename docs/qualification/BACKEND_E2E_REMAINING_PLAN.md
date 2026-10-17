# Backend 5/5 research backlog

## Current development priority: implement the canonical component rewrite

The current implementation handoff is
[Canonical component rewrite](../plans/CANONICAL_COMPONENT_REWRITE_PLAN.md).
The user authorizes a breaking Python API and removal of compatibility paths.
Implementation is in progress under the user's explicit instruction. Earlier
source-binding/cache/source-read/manifest/metadata repairs are implemented.
Files, identity observation access, Index, DecisionScope and Source are
independent components with bounded proof. The remaining domains and broad
qualification are unfinished.
Follow the implementation checkpoint in the component plan and continue CR-02
rather than replaying the captured baseline or already repaired defects.

The broad twenty-capability 5/5 target below is retained as a later research and
qualification track. Its minima, oracles, review requirements, failed evidence
and machine-readable matrix are unchanged. They are not prerequisites for
closing every local architecture subgoal. Owner-sized proof, selected integration
closure, whole-project typing and final release qualification have distinct
scopes; a scoped pass must always name its scope.

The sections below retain prior campaign checkpoints and the full research
backlog. Their historical "current" identities/counts refer to those checkpoints,
not proof of a later candidate. No capability is promoted to 5/5 by this change.

This handoff is Hashmarks development QA. Product code remains a repository
observer; consumers own reasoning and external execution layers own execution
and certification. Follow `docs/reference/PRODUCT_BOUNDARY.md`.

The successor definition is
`benchmarks/repository_evaluation/manifests/backend-campaign-v2/campaign.json`.
It began with 36 entries, 27 distinct upstream problems and eight
capability tags from the original campaign. The messaging intake extends this
to 49 entries and 40 distinct upstream problems. Transaction/persistence intake
extends it to 61 entries and 51 distinct problems across five suites. Language
intake adds twelve entries, six new upstream problems and three new repositories:
the language checkpoint had 73 entries and 57 distinct problems across six suites.
Debugging intake adds four entries, including two new upstream problems. The
debugging checkpoint had 77 entries and 59 distinct problems across seven suites.
Selected-call intake adds twelve capability-specific views of existing problems:
the current campaign has **89 entries / 59 distinct problems / eight suites**.
Its language catalog has six Python and six TypeScript cases over twenty-four
source trees. Copying a suite or reusing a problem adds no distinct evidence.
The original campaign remains historical. The active schemas remain workflow
v2, campaign v4 and matrix v5. Additional capability membership is admitted only
after source review and executable witness proof.

## Research completion contract and retained checkpoints

### Current checkpoint: native service reply validation

**The campaign remains INCOMPLETE. No capability is established at 5/5.**
Current observer is
`sha256:acd5e5c7aa9bd4582a2ffc2a95972fdd8f68cb2255a8c08f91e88a8746761455`;
evaluator remains `81b2085…`. All `0e962bd…`, `31c3938…` and earlier public/native
reports below retain their original identities and are historical after this
production repair.

T09 inspection reproduced a transport correctness defect: canonical clients
accepted wrong/missing schemas and coerced arrays of pairs into repository
objects. `find_task` accepted arrays containing non-object hits, and internal
handlers could return non-object replies. The current repair reuses the existing
`_SERVICE_ROUTES` and operation-schema owner for seventeen canonical clients,
requires object hit rows and handler replies, preserves unknown fields and
literal false/zero/null values, and leaves empty bounded hits without negative
authority. Unix server ownership and byte-writer interfaces are typed without
changing lifecycle, request/response limits, retries or execution policy. This
is an internal repair to the observer's transport boundary.

Evidence lives in `typing-intake/service-boundary-01/` under
`.hashmarks/backend-e2e/explicit-retrieval-20261016/`:

- `frozen-before-tests-02.log`: **7 FAIL / 2 PASS** against the independently
  extracted `0e962bd…` candidate. `baseline-import-origin-02.json` proves the
  exact exercised module and producer identity; the frozen extraction is intact.
- `route-preservation.json`: every rewritten request operation, response key and
  semantic schema agrees with the pre-existing route owner. Request argument
  values and one shallow copy of valid replies are preserved. No registry,
  schema value, authority rule or qualification threshold changed.
- `service-transport-tests-after-01.log`: **93 tests PASS**, including actual
  Unix service, verification, MCP and presentation consumers.
- `hostile-schema-probes-01.log`: **17 additional checks PASS**, covering another
  registered operation's schema on every repaired canonical client.
  `probe-addition-preservation.json` proves the already tested protocol functions,
  fixtures and helpers are unchanged when these probes are added. These are
  controlled protocol regressions, not new genuine corpus problems.
- Scoped Ty/Pyright pass for the service and protocol tests. Existing type ignores
  are removed; the invalid-classification case still reaches native dataclass
  validation through `replace`, retaining its unsupported value.

Fresh full inventories are `full-ty-after-02.log`: **2,069 diagnostics**, and
`full-pyright-after-02.log`: **2,041 errors**. Both full gates remain red.
Structural Locality's earlier typing debt is still open. The next persistent
source candidate is `source-service-boundary-01/`; inspect its manifest and
independent extraction results before treating it as qualified. Final journal
edits may postdate the ZIP.

The remaining work is still T03–T10: missing catalogs, independent semantic
review, exact witness closure, metadata localization, full configured typing,
current public/native acquisition, complete deterministic test membership,
heldouts, comparable economics and final artifacts. Neither protocol hardening
nor green scoped tests substitutes for that work.

### Typing and source-review checkpoint after interruption

The last six test-owner repairs are complete in
`typing-intake/{endpoint-presentation-01,negative-authority-01,correspondence-consumer-01}/`
under `.hashmarks/backend-e2e/explicit-retrieval-20261016/`. The three named
batches pass **22, 13 and 18 tests** respectively, including actual MCP SDK
delivery, declaration authority, qualified negative evidence and consumer
conformance. All six owners pass both checkers. Each batch's `preservation.json`
compares the entire original module AST after erasing checked reads and type
annotations: every original fixture, assertion, parameter and production-call
value is retained. The retrieval spy's obsolete return annotation is corrected
to the actual producer tuple; no replacement API or unchecked cast is added.

Fresh full inventories at
`typing-intake/correspondence-consumer-01/full-{ty,pyright}-after-01.log` report
**2,096 Ty diagnostics / 2,103 Pyright errors**, down from 2,339 / 2,345. Both
full gates remain red. Production/evaluator identities remain `0e962bd…` /
`81b2085…`; the frozen `source-context-explicit-01` ZIP predates these six
test-only repairs as well as later journal edits. Do not claim it contains them.

The historical `31c3938…` SQLAlchemy path batch is now terminal INCOMPLETE:
all four workflows pass all ten gates. Together the three historical repository
batches complete all twelve workflows: eleven pass all ten common gates; the
cancellation-before duplicate failure is preserved and subsequently repaired
under `0e962bd…` as detailed below. These historical reports cannot become current
by merging them with the current cancellation report.

`metadata-task-source-review-02.json` adds source-only caller/constructor evidence
without changing the admitted task. `metadata-task-compare-01/summary.json`
compares original → source-neutral → original API queries against the same
pinned source/index, retaining all original required facts. Both phrasings miss
the same method; the original replay is stable. Removing the unsupported future
kind does not repair localization. Keep the original case, source oracles and
failure; do not treat a wording change as a product repair or a new distinct
problem. Missing catalogs, independent reviews, witness closure, complete typing
and final qualification below remain open.

### Latest implementation checkpoint: 2026-10-17, declaration-context retrieval

**The campaign remains INCOMPLETE. No capability is established at 5/5.**
Current observer:
`sha256:0e962bd7bd543ccbb76af1e6c3588975b4f906444a6b74fa1a0b0649ad061b64`.
Evaluator remains `81b2085…`. This supersedes the observer checkpoint below;
historical reports retain their original identities.

The two SQLAlchemy localization failures below reproduced two generic disclosure
gaps. Their expected files ranked 58th and 18th in the existing lexical pool,
outside its twelve-path shortlist. In addition, a method with no matching word
in its own name was discarded even when its enclosing class and signature
matched. `localization-probe-01/summary.json` and
`declaration-context-probe-01.json` retain the diagnostic measurements.

The repair adds one weak `bounded-declaration-context` hint using the existing
sixty-four-file pool before that shortlist. It examines at most thirty-two
declarations; SQL prefixes are only a prefilter and existing identifier-part rules
qualify the match. Current source/outline visibility is required. Explicit
locators, the two-supplement limit, the requested response bound and independently
owned edit/verifier selection remain unchanged. A matching class does not prove
runtime dispatch or behavioral ownership. Duplicate hints retain the existing
natural-language declaration and its presentation contract.

Evidence under `.hashmarks/backend-e2e/explicit-retrieval-20261016/`:

| Evidence | Result and limit |
| --- | --- |
| `path-intake/context-before-01.log` | Two neutral opaque-method/outline failures reproduced before repair |
| `path-intake/context-adversarial-01.log` | Eight tests PASS: coherent class/signature disclosure, hidden/changed/deleted source, outline policy, explicit precedence, coarse-prefix rejection, hidden-row bounds and repeated task words |
| `path-intake/context-api-01/summary.json` | Both revisions and both API profiles of failed BEGIN and repeated loader pickling retain all frozen task facts under intermediate observer `4b8debd…`; expected source files occur in the first three results, and exact changed methods are direct or declared-member evidence |
| `source-declaration-context-01/extracted-regression-01.log` | Intermediate observer `4b8debd…`: 780 PASS / 1 FAIL. A duplicate context hint changed an existing declaration hint's ordering/tag; the unchanged regression remains preserved |
| `path-intake/context-dedup-after-01.log` | 44 focused disclosure, invalidation, authority and duplicate-hint tests PASS after repair |
| `source-declaration-context-dedup-01/source.zip` | Independent candidate, ZIP SHA-256 `e080885c7039e3d91736a9e1d4b412bfe04d358c888a680b02c1c372d714a05f`, 1,136 members, observer `31c3938…` |
| `source-declaration-context-dedup-01/extracted-regression-01.log` | 781 tests PASS from independent extraction, including actual SDK/IPC, task evidence, structural scopes, public presentation, backend grading/regrading, native LSP and CodeMap regressions |
| `path-intake/context-candidate-diff-01.json` | Path suite/grader bytes and modes unchanged; exact source-member accounting identifies only the two retrieval/query production repairs, one new test and documentation changes |
| `path-intake/native-transport-typing-preservation-01.json` | Entire native transport test module AST identical after erasing imports, annotations and checked JSON-read wrappers. All original fixtures, assertions, parameters and production-call values remain identical |
| `path-intake/native-transport-tests-after-01.log` | All 11 native CLI/official-MCP transport tests PASS after that separate test-only narrowing; scoped Ty/Pyright both pass |

The candidate ZIP predates the native transport test-only narrowing and the
latest documentation. Do not claim it contains those edits. Production and
evaluator identities remain unchanged. Current complete configured inventories
are `full-ty-native-transport-narrowing-01.log`: **2,339 diagnostics**, and
`full-pyright-native-transport-narrowing-01.log`: **2,345 errors** (both in
`path-intake/`). The previous current inventories were 2,382 / 2,391. Neither
full typing gate is green.

The current frozen candidate is `source-context-explicit-01/`; its manifest records
the exact ZIP identity and import/extraction binding. It includes the separate
native transport test typing cleanup. Final journal edits may postdate the ZIP;
always distinguish its manifest from the current worktree.

Acquisition outputs under the preceding `31c3938…` observer are
`path-intake/context-dedup-public-01-{aiokafka,
faststream,sqlalchemy}/`, `context-core-public-01/` for the original metadata and
sender problems, and `context-native-live-01/` with its distinct
`context-native-live-captures-01/` directory. Acquire/inspect terminal summaries
before treating any batch as proof. The aiokafka path batch is complete: all four
workflows pass all ten gates; overall status remains INCOMPLETE. Fresh native
acquisition completes **12 workflows / 24 revisions PASS**. This is selected
source-binding/transport evidence; these path native outcomes have no executable
native fact witnesses and do not close capability-specific witness or native
semantic review. The FastStream path batch is terminal FAIL: three workflows
pass all gates; cancellation-before loses its independently required existing
verifier. The SQLAlchemy batch is still in flight at this checkpoint. The older
`context-public-01/` uses `4b8debd…` and is historical after the duplicate repair.

The cancellation failure proved an additional duplicate: an explicit locator and
a context hint for the same method occupied separate slots, displacing `AckPolicy`
from the first three source candidates and hiding `test_ack_policy.py`. The
neutral explicit/context fixture fails before repair. The current repair also
deduplicates against the already admitted explicit supplements;
`context-explicit-after-02.log` passes 45 affected tests. Both revisions and both
API profiles now pass the unchanged cancellation facts in
`context-explicit-api-02/summary.json`. Current actual-transport qualification is
still required. All `31c3938…` reports remain historical after this repair.

The current core metadata/sender report above is terminal FAIL. Sender passes all
ten gates with maximum complete initial MCP compact size 3,849. Metadata still
misses `ClusterMetadata.failed_update` and its owner file in the first three.
`metadata-baseline-api-01/summary.json` independently reproduces that missing
method under pre-change `db18918…`; it is not introduced by this context repair.
Its smaller response is not an evidence-economics improvement: the required fact
is missing. This is an open localization problem in the original core corpus.

The broad non-diagnostic lexical trial did not repair that genuine case and
introduced two existing declaration regressions (44 PASS / 2 FAIL). It is
rejected. `rejected-nondiagnostic-lexical-01/` retains its exact production/test
bytes, experiment fixture and decision; `lexical-topic-after-01.log` and
`metadata-topic-api-01/summary.json` retain the failures. The original core oracle,
all pre-existing regressions, membership, facts and bounds remain unchanged.
Do not revive this trial or add task/package keywords without a better generic,
source-grounded retrieval explanation and neutral adversarial proof.

Current-candidate qualification now completes:

- `source-context-explicit-01/source.zip`: SHA-256
  `f120a32ef510e9bae0746829dc2de0e79eb145dab73e865111bb2ae638de7724`,
  1,136 members. `import-origin-01.json` proves observer/evaluator imports from
  the independent extraction. `extracted-regression-01.log` passes **793 tests**,
  including the new explicit/context duplicate control and all eleven native
  transport tests. `source-compile-01.log` completes the configured source
  `compileall` scope successfully. This is a focused ring, not full deterministic
  membership or final packaging/promotion proof.
- `path-intake/context-explicit-public-01/summary.json`: the genuine cancellation
  workflow passes all ten gates at both revisions through default/initial API,
  every CLI/MCP format, task variants and source invalidation. Complete initial
  CLI compact replies are 2,687 / 2,725 tokens; MCP compact replies are
  **2,797 / 2,835**. All compact/text replies remain below 4,000. Overall status
  is INCOMPLETE; the test is still a weak candidate, not established coverage.
- `context-current-aggregate-02/summary.json` (under `path-intake/`) purely
  revalidates that current report and its **297 artifact-bound fact witnesses**.
  It admits the valid workflow input and accounts for all 89 expected campaign
  outcomes. Overall and input integrity remain INCOMPLETE for missing proof.
- `context-stale-native-aggregate-02/summary.json` rejects the preceding
  `31c3938…` native report while retaining the current workflow input: FAIL, as
  expected. Older successful native evidence is not promoted to current.
  Report-map attempt 01 used `path` and was rejected as an unknown namespace;
  corrected maps use the authoritative campaign ID **`backend-path-v2`**.
- Fresh configured `full-ty-context-explicit-01.log` /
  `full-pyright-context-explicit-01.log` retain **2,339 diagnostics / 2,345 errors**.
  Both remain red; scoped checks on the two modified production owners and two
  affected test owners pass. Current preflight passes Ruff, hygiene, complexity
  and size gates. Final journal updates postdate the frozen source ZIP.

Source-only investigation also identifies a task-grounding concern:
`metadata-task-source-audit-01.json` records that both pinned metadata revisions
import `Future` from `concurrent.futures` at line 6 and assign
`self._future = Future()` at line 183, while the public task names an asyncio
future. This is a declared-source mismatch requiring oracle review, not runtime
type proof. No dependency implementation was inspected. The original case,
question and all required facts remain unchanged. Review that premise and its
caller boundary before tuning production retrieval against it; a correction
must preserve the original misleading-input case and cannot weaken bounds or
required evidence. Do not infer that the missing method has been repaired.

Economics investigation now has a bounded profiling lead in
`path-intake/localization-profile-01/{summary.json,hot-owners.json,top.txt}`.
One failed-BEGIN API call against an existing saved index makes 87,976,482
profiled calls and takes 35.57 seconds with profiler overhead. Candidate-verifier
collection accounts for 22.37 cumulative seconds; the new declaration-context
lookup accounts for 0.183 seconds. The measured operation parses 496 Python
snapshots and builds 462 reference projections. These cumulative costs overlap
and must not be added. The single run has concurrent qualification activity and
no same-version control: it is characterization, not a performance regression,
speedup or capability-20 qualification. Investigate the verification/import
qualification owners before proposing lexical representation changes or word
matching caches. Preserve references, ambiguity, source binding, candidate bounds
and packet facts. Use T10's comparable cold/warm/incremental samples and controls
before making an economics claim.

Next: finish and retain these exact batches, inspect all failures and sizes,
purely regrade their artifact-bound witnesses, and update the aggregate without
reusing historical observer reports as current proof. All independent capability
reviews remain pending. Campaign population is still 89 entries / 59 distinct
problems / eight suites; debugging still needs eight problems across two more
repositories, and catalogs 8, 9, 11, 15, 16, 18 and 20 remain missing. Complete
T03–T10 below; scoped regression/typing passes do not close those tickets.

### Historical implementation checkpoint: 2026-10-17, selected call scopes and collections

**The campaign remains INCOMPLETE. No capability is established at 5/5.**
This checkpoint supersedes the historical checkpoints below. Current observer:
`sha256:db189183ae2d49a6ff4e01cbc30d50bc03f109890ecf61b56aab878426646b75`.
Current evaluator:
`sha256:81b208502ea966e6363e48c9509d8e8af3f8b0fd77a3007d4c4d0009c3b59a74`.
Historical public/native reports below remain bound to their original identities;
they are not qualification of this candidate.

Catalog 2 now has twelve distinct source-bound problems across aiokafka,
SQLAlchemy and FastStream. Its task inputs, exact direct segments, unresolved
receivers, endpoint labels and structured/compact/text display facts were frozen
from admitted source before the selected-call measurements. It adds no new
distinct campaign problems. All review flags remain false. The 720 required
positive/adversarial witness contexts cover both revisions, API, CLI and MCP,
native and displayed facts. `backend_structural.py` composes the existing public
surface and transport owners; retained-byte regrading and artifact-bound
witnesses use the existing qualification machinery. No product execution or
semantic graph responsibility was added.

Source-first intake reproduced and repaired three generic observer defects:

1. **Nested caller scope:** `edges_from` includes descendants. Structural Locality
   now selects the indexed source's own calls before its per-symbol limit.
   Nested callbacks/methods retain their own caller; no transitive shortcut or
   callback invocation is invented. Three neutral cases failed before repair.
2. **Definition-expression scope:** decorator/default/base calls no longer become
   calls made by the declared body. A genuine SQLAlchemy decorator was previously
   emitted as an exact `_prepare_impl` call at line 1281, before that method's
   body starts at 1284. Three neutral regressions reproduced the defect.
   Parser identity advances from v6 to v7 so persisted artifacts are invalidated.
3. **Qualified lexical scope:** same-named methods and unrelated nested bindings
   no longer hide an independently qualified import call. Actual local function,
   class and closure shadowing remains unresolved. Five of eight neutral cases
   failed before repair, including three false exact import edges. The repair
   reuses `python_exports`' existing scope-aware name-write owner and a qualified
   function index on the same stable AST snapshot. There is no parallel binding
   authority or persistent relationship state. Classification: REFACTOR
   INTERNALLY, motivated by the reproduced binding defects, not file size.

Evidence under `.hashmarks/backend-e2e/explicit-retrieval-20261016/path-intake/`:

| Evidence | Result and qualification limit |
| --- | --- |
| `direct-call-scope-before-01.log` | Three false enclosing-caller associations reproduced |
| `nested-callback-source-oracle-01.json`, `nested-callback-before-01/` | Genuine pinned FastStream shutdown source oracle, frozen before measurement; after-change caller FAIL reproduced |
| `nested-callback-public-after-01/summary.json` | 27 API/CLI/official-MCP observations PASS across both revisions under intermediate observer `82c8201…`; this is lexical caller repair evidence, not current/full capability qualification |
| `decorator-source-oracle-01.json`, `decorator-before-02/` | Source-frozen genuine SQLAlchemy definition-header false exact edge at both revisions |
| `definition-scope-after-01.log` | 110 parser/CodeMap/locality/direct-declaration regressions PASS after the definition-scope repair |
| `parser-migration-01/summary.json` | PASS: unchanged source, same durable state and artifact stores; independent v6 extraction's wrong call lines `[5,6,7]` become `[7]`, one artifact reparsed under v7 |
| `structural-workflow-tests-01.log` | 141 QA/workflow/witness/transport tests PASS before the final qualified-scope repair; includes actual public transports, pure replay, tamper rejection and incomplete-transport controls |
| `api-probe-01-{aiokafka,sqlalchemy,faststream}/summary.json` | All 24 revision observations completed under intermediate observer `f1177c0…`. Native facts and endpoint revision binding pass 20/24; structured display passes 20/24; compact/text pass only 4/24. These failures remain recorded |
| `import-scope-before-01.log`, `import-scope-after-01.log` | Five neutral failures reproduced before qualified-scope repair; 58 affected parser/cache/authority/locality regressions PASS afterward |

The four native failures above concern both revisions of repeated loader
pickling and empty batch publication. They motivated the qualified-scope repair;
current genuine remeasurement is required. Display truncation is still open:
the existing five-row relationship projection hides admitted direct segments
and unresolved next hops. Preserve the frozen facts, native bounds and exact
source references when repairing presentation. Raising scores, deleting adverse
checks, dropping admitted facts or weakening the 4,000-token initial-response
ceiling is not a repair.

The collection-presentation repair is now implemented after that failed probe.
Every already bounded node/call/unresolved/external collection is retained as a
single native-referenced finding, with an explicit member count. Repeated
per-edge presentation metadata is removed. The observation's native traversal
bounds and every admitted field remain intact. Three new neutral checks failed
before repair; all four collection checks pass afterward, including independent
recovery from actual text lines, future qualifiers and strict false/zero values.
The collection counts are documented in `STRUCTURAL_LOCALITY.md` and
`API_STABILITY.md`.

Additional evidence in `path-intake/`:

| Evidence | Result and qualification limit |
| --- | --- |
| `call-scope-public-01/<workflow>/summary.json` | Both revisions of repeated loader pickling and empty batch publication now pass native facts, authority and endpoint binding on API and every real CLI/MCP format under observer `a5f48d0…`. Both reports still fail compact/text display. This proves the lexical-scope repair and preserves the display failure |
| `../source-call-scope-01/extracted-regression-01.log` | 574 tests PASS from an independent extraction under observer `a5f48d0…`, including actual SDK/IPC, parser, source/verification, authority, native LSP, backend workflow/regrading and presentation contracts |
| `collection-oracle-preservation-01.json` | Suite bytes unchanged. Every oracle fact, check ID/predicate, support/authority flag, source label, bound and witness is unchanged; only display record pointers follow the new native collection arrays. Original grader `b5dcfc8…` remains frozen; current grader is `2258f4a…` |
| `collection-format-replay-01/summary.json` | 84 pure format replays conserve every field of all four collections. Historical API bytes retain their original missing facts: 60/72 display checks pass. All 12 replays of the four corrected lexical-scope observations pass their frozen display facts. Projection JSON totals change from 8,351,549 to 7,564,598 bytes. This is historical-byte projection evidence, not current repository or actual transport qualification |
| `locality-projection-contract-01.log` | 24 focused collection/backend/public-transport/presentation tests PASS after the collection repair |

`full-ty-call-scope-01.log` and `full-pyright-call-scope-01.log` report **2,382 Ty
diagnostics / 2,393 Pyright errors** under the preceding call-scope candidate.
Both remain red. These inventories predate the collection projection; fresh
configured inventories and independent extraction/public qualification are next.

The collection candidate was independently frozen as
`source-call-collections-01/source.zip` (ZIP SHA-256
`e928091f8b0a7742210e787a009b3738632a743b2f4d744885bc763d640d045d`,
1,135 members; observer `b8e33d0…`). Its extracted ring completed with
**577 PASS / 1 FAIL**: collection ordering displaced the existing first SCIP
producer-claim finding. The current repair restores that ordering while keeping
all four bounded collections. `scip-collection-order-after-01.log` passes 21
affected discovery, collection and import-scope tests. Preflight passes. This
repair requires a new frozen candidate; preserve the failed candidate's bytes.

That ordering repair is now frozen as
`source-call-collections-scip-01/source.zip`, SHA-256
`84f2d3a6bc6e3930587501adee55f74639506b4426d178e5b42d792259b7dd8f`
(1,135 members, current observer `9ccc6b3…`, evaluator `81b2085…`). Its
`extracted-regression-01.log` completes **578 tests PASS** from independent
extraction, including the restored SCIP-first contract and exact collection
preservation. This is a persistent development candidate, not final release proof.

The subsequent test-only verification-reference typing cleanup passes all four
tests and scoped Ty/Pyright. `verification-fallback-typing-preservation-01.json`
proves the entire module's original fixtures, assertions and production-call
values unchanged after erasing two checked string narrowings. The ZIP predates
this test-only cleanup and the subsequent filename-disclosure production repair.
It is historical; do not claim it contains all latest source/documentation edits.

Full `collections-full-public-01-*` batches use frozen observer `b8e33d0…` and
are historical after that ordering repair. The aiokafka batch is complete: all
four workflows pass all ten gates, including both initial profiles/transports,
sizes and source invalidation; overall status remains INCOMPLETE. All three
repository batches are now terminal: **12 workflows / 24 revisions** complete.
Every nominated structural component passes all five component gates on API,
CLI and MCP. Nine workflows pass all ten common gates. The other three retain
these genuine common task-evidence failures:

- `sqlalchemy-failed-begin`, both revisions: source owner and changed symbol
  missing from task evidence and the first-three owner result. Its nominated
  structural component passes every gate. Repair generic localization at its
  existing owner; do not feed the nominated call target into task ownership or
  rewrite the natural-language task to contain the expected answer.
- `sqlalchemy-pickle-extra-criteria`: the natural-language owner/symbol and
  first-three owner result are missing; its separately nominated structural
  component passes. Preserve this case alongside failed BEGIN when repairing
  generic localization.
- `faststream-ack-cancellation`, after revision: the independently required
  existing verifier is missing. Its structural component passes every gate, and
  the before revision passes the task facts. Inspect the retained verification
  disclosure and indexed source/test evidence; do not drop the after-only
  cancellation test or infer a verified relationship from lexical similarity.

Fresh complete inventories for the collection candidate are
`full-ty-collections-01.log`: **2,382 diagnostics**, and
`full-pyright-collections-01.log`: **2,393 errors**. No full typing gate is green.

The cancellation test was present in the scored candidate pool: 64 candidates,
rank 25, outside the eight returned slots. Its only task matches were
`cancellation` and `py`; generic protocol helpers ranked above it on source-name
overlap. `cancellation-candidates-probe-01/summary.json` records that unchanged
ranking, not a missing repository test or a discovery failure.

The current minimal repair ranks a filename matching the task concern after
exact reference, source filename and namespace precedence, before incidental
source-name overlap. It subtracts the nominated source path/symbol and existing
stopwords from the filename topic match. It changes disclosure only: candidate
limits, canonical edit/verifier selection and relationship authority remain
unchanged. The neutral protocol-helper example fails before repair and passes
afterward; `problem-test-after-01.log` passes 15 related tests, including both
profiles, namespace/reference controls and unchanged canonical selection.
Scoped Ty/Pyright pass. `cancellation-candidates-probe-02/summary.json` retains
64 scored/eight returned candidates and now includes the required test.
`problem-filename-api-01/summary.json` passes the frozen task facts at both source
revisions in default and initial API profiles. Actual current transport/size,
freshness and artifact qualification remain next; do not promote this API probe
to a complete workflow PASS.

The filename-disclosure candidate is independently frozen as
`source-problem-filename-01/source.zip`, SHA-256
`5bb840d834bcc4e1cc039710b9fcd28f33ba6d389c95e2b51ec4b4459fda3b8b`
(1,135 members, observer `db18918…`, evaluator `81b2085…`). Its import-origin
receipt verifies the independent extraction. `extracted-regression-01.log`
completes **583 tests PASS**. This is focused qualification, not the complete
deterministic project membership.

`problem-filename-public-01/summary.json` now completes the genuine cancellation
workflow under that candidate: **all ten gates true** at both revisions, through
default/initial API, all CLI/MCP formats, variants and source invalidation. Overall
status remains INCOMPLETE for wider qualification. Complete initial MCP compact
responses measure **2,869 before / 2,907 after**; all required compact/text
responses are below 4,000 tokens. The former missing test remains a weak
candidate with explicit unestablished relationship authority.

The pure aggregate reader also caught a metadata authoring error: the new path
campaign entry used physical file SHA-256 instead of the established canonical
JSON identities. `campaign-binding-correction-01.json` proves only those two entry
fields changed; every suite/oracle byte, expected fact, bound, witness and other
entry is unchanged. Existing artifacts retain the rejected entry as history.
Correct canonical suite/grader identities are `77955acc…` / `d7500354…`.
`collections-aggregate-02/summary.json` now accepts and regrades all twelve
provided historical `b8e33d0…` reports and preserves FAIL for their three observed
task failures. Overall input integrity remains INCOMPLETE for missing reports;
this is not an aggregate clean-pass claim. The
filename-disclosure ZIP above predates this metadata correction; materialize a
corrected candidate before using its campaign entry for artifact qualification.

The corrected candidate is now
`source-path-qualified-01/source.zip`, SHA-256
`5c94b40234a7f703b0b7cd920d9bd9f1c718ccaa4409e3c367191f6271c1453a`
(1,135 members, same `db18918…` observer and `81b2085…` evaluator).
`path-qualified-code-preservation-01.json` compares every one of the 1,003
production/evaluator/test/tool-configuration members with the 583-test candidate:
all bytes and modes are identical. Only campaign metadata and documentation
changed. `source-path-qualified-01/campaign-admission-01.json` independently loads
all eight frozen suites, source trees and canonical oracle identities: PASS.
These checks close the manifest binding repair, not the remaining qualification.

The latest complete Pyright inventory after the separate typing cleanup is
`full-pyright-after-verification-fallback-01.log`: **2,391 errors**. Full Ty remains
last measured at 2,382 diagnostics. Neither full checker is green.

Current complete configured inventories, including the filename-disclosure
repair, are `full-ty-problem-filename-01.log`: **2,382 diagnostics**, and
`full-pyright-problem-filename-01.log`: **2,391 errors**. Both remain red.

Continue in this order:

1. Campaign metadata and all eight bindings now pass the independent reader;
   cancellation has complete current public proof. Repair the two independently labeled natural-language
   owner failures. Preserve the frozen tasks and oracles. Run all twelve workflows at
   both revisions, default/initial profiles, actual CLI/MCP, all required formats,
   source invalidation and pure witness regrading. The lexical-scope repair has
   genuine public proof; the collection repair still needs current full workflow
   proof. API-only or historical-byte projection probes cannot replace it.
2. Complete catalogs 8, 9, 11, 15, 16, 18 and 20, and eight more debugging
   problems across two additional admitted repositories. Catalog 2's population
   is supplied; its review, display, native, freshness and final qualification
   are not closed. Do not count transports or reused problems as new breadth.
3. Finish independent review and exact witness closure, then current public and
   fresh native qualification for every composed packet. The earlier four
   debugging and sixteen native workflow entries are historical after these
   observer/evaluator changes. Original metadata/sender workflows remain open.
4. Finish T09 full typing and T10 deterministic membership, heldouts, comparable
   cold/warm/incremental economics with a noise control, and final artifact proof.
   The last completed whole-project inventories below still report 2,384 Ty
   diagnostics / 2,395 Pyright errors. They predate this candidate; scoped typing
   is never a substitute for a fresh complete inventory.

### Historical verified checkpoint: 2026-10-17, declaration words

**The four nominated debugging workflows pass every behavioral and transport gate.
The twenty-capability campaign remains INCOMPLETE. No capability is certified 5/5.**

The latest observer is
`sha256:39419ff6240fa082b4a6d0feeaae0b955ed2cbfaba34a8d694c8cdabc66ed662`;
the evaluator is
`sha256:3c36b8cddc21d4b764b2a9d2cc0f9f53b6112348f362abb9c0a41cb693ed3ab2`.
The independently extracted source ZIP is
`.hashmarks/backend-e2e/explicit-retrieval-20261016/source-declaration-words-01/source.zip`,
SHA-256 `60d776feb612cc98b3198fbf884fd7bbc74c86744cca61f42aec2b7e4d6efd6f`.
Its import-origin receipt proves the exercised observer and evaluator came from
that extraction. The working observer/evaluator still match those identities.

All evidence paths in the following table are relative to
`.hashmarks/backend-e2e/explicit-retrieval-20261016/`.

| Evidence | Verified result and limit |
| --- | --- |
| `source-declaration-words-01/extracted-regression-01.log` | 342 affected tests PASS from independent extraction, including actual MCP/IPC, native LSP change regressions, source/test disclosure, codec/presentation and dependency replay |
| `debug-declaration-words-public-01/<workflow>/summary.json` | Logging-token reset, aggregate strings, metadata and annotation diagnostics each pass all ten gates at both source revisions, through API, CLI and official MCP with required formats/variants and stale controls. Overall reports remain INCOMPLETE for wider qualification |
| Same public reports | Relevant existing tests survive both revisions. Every complete initial compact/text CLI/MCP reply meets the unchanged 4,000-token ceiling. Metadata's MCP compact response is **3,890 before / 3,890 after** |
| `debug-declaration-words-native-01/summary.json` | Fresh genuine captures: four nominated debugging workflows / 510 witnesses PASS |
| `language-declaration-words-native-01/summary.json` | Fresh genuine captures: twelve nominated language workflows / 900 witnesses PASS, including the four newly supplied Python native oracles |
| `declaration-words-aggregate-02/summary.json` | Existing pure aggregate reader revalidates all four complete public reports and both complete native reports under matching source/oracle/observer identities. Campaign result is INCOMPLETE; missing work is retained |
| `declaration-words-checkpoint-01.json` | Exact artifact/report identities, all workflow gates and initial transport sizes, native witness counts, typing failures and missing populations |
| `source-word-verifier-before-01.log` / `source-word-verifier-after-02.log` | A generic paraphrased task loses its source-named test before the repair; 22 relevant source/test and authority regressions PASS afterward |
| `duplicate-key-oracle-independence-01.json` | Root and nested duplicate keys are rejected even when a permissive parser would satisfy the semantic identity. Removing only the duplicate-key guard admits those packets; identity checking cannot mask this regression |
| `duplicate-identity-regression-01.log` | 36 codec/profile tests PASS, including the strengthened identity-matching duplicate-key controls |

The sixteen native workflow entries include problems shared between suites. They
do not add sixteen new distinct backend problems or fill missing catalogs. Native
nomination/source-binding PASS does not establish natural-language retrieval,
runtime causality, language parity, independent review or complete capability QA.
The campaign remains **77 entries / 59 distinct genuine problems / seven suites**.

The observer repairs preserve canonical edit/verifier selection and authority.
Source namespace locality, coherent declaration words and balanced disclosure
across observed sources retain relevant tests without making lexical matches
relationships. Direct semantic JSON compression and structured declaration tables
remove encoding/escaping overhead while preserving all admitted facts. Earlier
failed candidates and source-only measurements remain historical below.

Additional test-only typing batches after that ZIP pass their focused tests and
scoped Ty/Pyright: eleven authority-adversarial cases and thirty-nine query-router
cases. Their preservation receipts compare every original fixture and assertion
after removing checked narrowing/annotations. The ZIP predates these two test-only
cleanups and the strengthened duplicate-key test; its production observer and
evaluator are unchanged. Do not claim it is a final shipping artifact.

The latest complete configured inventories are
`full-ty-after-authority-router-01.log`: **2,384 diagnostics**, and
`full-pyright-after-authority-router-01.log`: **2,395 errors**. Both remain red.
Changed owners pass their scoped checks, and current preflight passes formatting,
full Ruff, hygiene, zero complexity and the production size ceiling. Neither
scoped typing nor 342 focused tests closes T09 or T10.

Execute the remaining work in this order:

1. **T07: finish genuine populations.** Catalogs 2, 8, 9, 11, 15, 16, 18 and 20
   remain missing. Debugging still has four of twelve required problems and one
   of three required repositories: admit eight further genuine problems from
   two additional explicitly selected repositories. Follow the source-first
   intake below; do not copy tags, count variants as problems or chase imported
   dependency implementations. Existing cases may support another capability
   only when their actual task and independently expected evidence demonstrate
   that capability's semantics.
2. **T07/T08: finish independent oracles and witnesses.** Keep all review flags
   false until supported review exists. Freeze exact source owners, changed
   symbols, relevant existing tests, positive/adversarial/display facts and
   required witness membership before observing Hashmarks. Native target oracles
   now exist for all twelve language cases, but the other missing semantic
   families and independent reviews remain open.
3. **Qualify each observer repair before widening scope.** First check all known
   supported problems at **both** source revisions in default and initial API
   profiles. The after-only probe previously hid the aggregate-strings regression.
   Then freeze stable bytes and run actual public/native transport qualification.
   API size estimates never replace complete MCP/CLI measurements. Reuse the
   existing owners/runners; do not add execution control, retries or resume state.
4. **T09: finish full typing.** Continue bounded, preserved test/owner repairs;
   no `Any`, casts, ignores, exclusions or assertion/input removal to make counts
   green. Checked mutable views must retain the original dictionaries/lists in
   tamper tests. Variadic fixture helpers that deliberately submit invalid input
   must continue exercising production validation, rather than rejecting it in a
   new test helper. Fresh full Ty and Pyright must both reach zero.
5. **T10: final qualification.** Run every required deterministic test member in
   named complete batches, then unseen heldouts, real cold/warm/incremental
   economics with identical evidence and a same-version noise control, and final
   exact-artifact proof. Other five suites and the historical messaging
   metadata/sender findings still require current qualifying reports; the four
   debugging passes do not clear those tasks. An interrupted batch is incomplete,
   and completed same-candidate batches are not discarded because another window
   expires. Use the repository's existing batch entrypoints below.

Do not raise any capability to 5/5, mark the goal complete, issue a clean-pass
claim or weaken the release gate until populations, independent review, exact
witness closure, full typing and final project validation all pass.

### Historical repair checkpoint: 2026-10-17, base `4dc2527`

The next source-name repair is implemented after the checkpoint below. Frozen
candidate `source-json-tables-01` (ZIP SHA-256
`9bc7035b46ca6e945f113b67dacaf33224b8dad09f6f6603527ccfd34aff8250`;
observer `sha256:5439d9d65b65b47b8455cf3fb8d2a52337c81aea5cc03cde4c06ea74a2cba90c`)
passed 326 independent-extraction tests and fresh native acquisition for all four
debugging workflows / 510 witnesses and all twelve language workflows / 900
witnesses. `json-tables-native-aggregate-01` revalidates those reports and remains
INCOMPLETE for broader qualification. Its full public logging workflow passed
all ten gates. Before-revision metadata MCP compact measured 3,890 tokens, below
the unchanged 4,000 bound. Other full public summaries must be inspected before
claiming their gates complete.

The same candidate still missed aggregate strings' existing test before the
change. The task says `aggregation` / `string`; the existing declaration and test
say `aggregate_strings`. Current disclosure now observes coherent overlap of at
least two words from the retrieved source declaration inside one indexed test.
It does not infer morphology, call relationships, owner or verifier authority.
`source-word-verifier-before-01.log` reproduces the generic failure;
`source-word-verifier-after-02.log` passes 22 relevant tests. All four problems
now pass their frozen facts at both revisions in default and initial API probes
(`source-word-verifier-probe-01`); complete transport qualification remains next.
Preserve the preceding candidate's failure and completed native evidence under
its original identity. The current source-name repair requires a new candidate.

Dependency dogfood typing is also repaired: 15 tests and scoped Ty/Pyright pass;
`dependency-dogfood-typing-preservation-01.json` verifies all original capture
inputs and assertions. The only additional state is an explicit unknown result
before the existing Maven-only branch. Latest full inventories before the final
source-name normalization report **2,481 Ty diagnostics / 2,496 Pyright errors**.
They remain red and do not close T09.

No capability is complete at 5/5. There are still 77 entries / 59 distinct genuine
problems / seven suites, eight missing catalogs (2, 8, 9, 11, 15, 16, 18, 20), and
only four debugging problems from one repository. All independent review flags
remain false. No tasks, thresholds, source identities or problem floors changed.

The source-directory candidate (`sha256:dc6271d73ff91bc6ec160daa83f708933c16e1e9adff3787109966297403c83c`)
completed genuine API/CLI/official-MCP observation at both revisions for all four
debugging workflows. The preserved reports show:

- Logging-token reset and aggregate strings: FAIL. All source-owner, revision,
  freshness, authority and size gates passed, but the relevant existing tests
  disappeared from bounded disclosure.
- Metadata: FAIL only for initial size. Complete MCP compact replies measured
  4,222 before / 4,224 after estimated tokens; CLI measured 3,996 / 3,998.
  Passing an API-only estimate was insufficient transport proof.
- Forward-reference diagnostics: all ten workflow gates passed, overall
  INCOMPLETE for corpus/review qualification.

Those reports remain under `debug-directory-public-02/<workflow>/summary.json`;
they are historical after the following repairs, not current passes.

Current generic repairs:

1. Source namespace locality precedes directory task words in candidate test
   disclosure. The module-wide union of unrelated declaration words no longer
   determines this disclosure score: use the largest overlap in one indexed test
   declaration. A specific matching test only breaks an otherwise equal tie.
   The original module-wide emitted facts and canonical selection remain intact.
2. Preserve each observed source's local candidate order when merging the first
   three source pools. Do not globally compare namespace scores computed against
   different source owners. Canonical task candidates and the selected verifier
   remain represented within the existing eight-path limit. No heuristic gains
   ownership, relationship, completeness or verification-selection authority.
3. Initial packets compress semantic JSON directly as `json+zlib`. Compressing
   the string-table intermediate cost 672–868 extra bytes on the four admitted
   after packets. The existing uncompressed string table and historical compressed
   decoder remain supported; allocation, exact size, trailing/concatenated-stream
   and semantic-identity checks remain. Direct JSON rejects duplicate object keys.
4. Initial compact declaration tables expose structured rows and metadata rather
   than JSON quoted inside text. Text and structured formats retain their facts.
   A stale presentation regression expected an older nested source-reference
   wrapper; it now independently reconstructs every row and qualifier from the
   supported representation and the finding's exact source pointer.

Proof under `.hashmarks/backend-e2e/explicit-retrieval-20261016/`:

| Evidence | Scope and result |
| --- | --- |
| `disclosure-frozen-before-01.log` | Same six neutral cases against independent frozen source-directory extraction: four reproduced failures / two passes |
| `specific-verifier-probe-01`, `-02` | Historical API probes exposing missing test and ordering interactions; retain their failures |
| `specific-verifier-probe-03` | After-only API: all independently frozen source/test/override/helper facts PASS in default and initial profiles for all four problems; precedes the codec/table repair |
| `initial-json-tables-ring-01.log` | 48 current tests PASS, including both compression formats, corrupt/over-bound streams, duplicate keys, exact declaration recovery and disclosure interactions |
| `initial-json-tables-preservation-01.json` | Pure transformation of all eight retained actual MCP replies: decoded native identities and all declaration facts/source references preserved. Metadata compact falls 4,224 → 3,882 after and 4,222 → 3,881 before. This is same-packet comparison, not fresh transport qualification |
| `initial-json-tables-preflight-02.log` | Canonical formatting, complete Ruff, hygiene, zero current complexity and production file-size debt PASS |
| `source-directory-01/source.zip` | Historical source artifact SHA-256 `aa329c5d120074654e11ab185cb43f08f6d94d7d327e742feec8c4525eda215e`; 314 independent-extraction tests PASS |
| `debug-directory-native-closure-01.json` | Revalidated disjoint native batches, all four nominated debugging cases and 510 witnesses PASS on source-directory observer; explicit native binding/invalidation/transport scope only |
| `language-complete-native-closure-01.json` | All twelve nominated language workflows and 900 witnesses PASS on the same historical observer; exact capture, source, artifact and witness regrading. Does not establish language parity, independent review or 5/5 |

Four language cases previously had no executable native target oracle: aiokafka
commit timeout/refresh order and FastStream cancellation/batch nack. Their eight
before/after target oracles now derive from already frozen source labels and exact
member bytes, without reading Hashmarks or native results. The language grader is
`27982182fe9d89a51196d5eb3a0c05cb78963b8cfc49289734351d30cf14be77`;
the campaign binding is updated. Every language case now has a native source
oracle. Independent review remains outstanding; capability 18 has not been filled
by retagging capability 19.

Typing cleanup now covers declaration discovery (55 diagnostics removed, 35 tests
PASS) and CodeMap tests (81 removed, 69 tests PASS), in addition to earlier work.
`declaration-discovery-typing-preservation-01.json` and
`codemap-tests-typing-preservation-01.json` compare the original bodies, providers,
fixture values and assertions after erasing checked narrowing/annotations and
interpreting identical pytest method overrides as their former assignments.
Pytest additionally restores overrides after their tests. No input/assertion
removal, `Any`, cast, ignore or exclusion was introduced by this cleanup.
The latest complete global inventories before the codec change are
`full-ty-after-codemap-01.log`: **2,549 diagnostics**, and
`full-pyright-after-codemap-01.log`: **2,565 errors**. Scoped green checks do not
close T09. Rerun the configured full commands after any further typing repair.

Immediate execution order:

1. Finish scoped Ty/Pyright and current preflight. Compile source once and freeze
   one new source ZIP including all current repairs. Use independent extraction,
   assert actual import origin, and run the affected source, codec, presentation,
   selection and transport regressions there. Do not edit that extraction.
2. From those immutable bytes, qualify each of the four debugging cases at both
   revisions through API, CLI and official MCP, all required profiles, formats,
   variants and stale controls. Use the existing `run_backend` runner, unchanged
   suite/grader and source map. Preserve full response size, every exact witness
   and all failed or incomplete work. Metadata MCP must pass the unchanged 4,000
   bound; restored test facts must survive every transport.
3. Regenerate native captures for the same observer using `run_backend_native`,
   the existing installed qualification tools, and exact source nominations.
   Regrade all 510 debugging witnesses. Keep the completed language 900-witness
   proof bound to its historical observer until properly requalified.
4. Aggregate compatible reports only. Corpus floors, independent review and
   witness-family omissions must remain INCOMPLETE; any hard failure remains
   FAIL. Never convert native source-binding PASS into broad retrieval proof.
5. Continue T07 intake: eight more debugging problems in two additional target
   repositories, eight missing catalogs, independently source-frozen oracles and
   exact positive/adversarial/display witness families. Do not chase dependencies
   or promote historical external-library findings into roadmap tasks.
6. Complete T09 typing, then T10 full deterministic test membership, unseen
   heldouts, economics/noise controls and final exact-artifact qualification.
   Missing, interrupted and partial batches cannot count as clean qualification.

### Historical checkpoint: 2026-10-17, base `1280456`

No capability is complete at 5/5. Corpus breadth is still 77 entries / 59 distinct
problems / seven suites. Eight entire catalogs remain missing: 2, 8, 9, 11, 15,
16, 18 and 20. Debugging still has only four problems in one repository. Every
review flag remains false; no population or oracle was relaxed.

The current repair batch closes three reproduced generic gaps:

1. Diagnostic words were indexed but their containing callable was missed when
   its declaration name did not match the task. `store_queries.py` now joins
   bounded adjacent query-token conjunctions to the closest indexed callable
   after its declaration line. `task_evidence_retrieval.py` admits at most one
   such source-position hint within the existing two-supplement budget. Explicit
   locators, visibility, freshness, ownership and verifier selection are preserved.
   The dense natural-language localization regressions remain unchanged.
2. Verification examined only the first 64 declarations in a candidate test file.
   `evidence_verification.py` now reuses the existing complete per-file session
   symbol reader for the selected path set before bounding the reply. A relevant
   late test is found; an equally matching late declaration preserves ambiguity.
3. The annotation method's new helper was hidden after retrieving the method.
   `direct_call_declarations` reuses the structural-locality resolver for up to
   four qualified same-file targets from 64 direct calls. Nested callable calls,
   shadowed names and transitive targets are excluded. Spans, call positions,
   revisions, generations and omitted/unqualified counts remain visible. Runtime
   invocation, unique ownership and repository-negative evidence remain unknown.

Two subsequent repairs are also implemented:

- Compact declaration tables derive their source scope from the finding's exact
  pointer plus the family key. `compact-scope-preservation-01.json` reconstructs
  the entire former response from the new response and confirms native-packet
  equality, unchanged noncompact formats, and exact source-scope preservation.
  On the same retained metadata API packet, compact size falls from 4,062 to
  3,995 estimated tokens. This is a same-packet measurement, not transport proof.
  No alternate opaque encoding or token-budget increase was introduced.
- Source-candidate verifier disclosure considers existing task words in the test
  directory before whole-module declaration-name overlap. It changes disclosure
  only. A neutral reproduction with twelve broad competing test files now keeps
  the specific test visible. Ambiguous owners stay unresolved; an unrelated
  directory match gains no direct or indirect relationship. The unchanged
  selected verifier and owner are checked in both result profiles.
  `test-directory-regression-03.log`: 29 tests pass. `test-directory-probe-01`
  admits all three metadata source/test facts in default and initial API output;
  initial compact/text estimates are 3,995 / 3,793. Genuine current transport
  qualification is still required before closing this repair.

Frozen artifacts and completed proof, under
`.hashmarks/backend-e2e/explicit-retrieval-20261016/`:

| Evidence | Exact scope and result |
| --- | --- |
| `source-lexical-01/source.zip` | 1,125 members, SHA-256 `9bc671f4022ed8a2a8c75eac51420fa6977616fb86e9b0478ddbaa270f2e36d1`; observer `sha256:b32c447b628e040b51d5e80acfd70b1b2de81b3d5c432d95c87196e42f660587`; independent import-origin proof and 305 affected tests PASS |
| `source-lexical-02/source.zip` | 1,125 members, SHA-256 `24ea3580838918a1e5583bacec674c4abf1c2bb59e55e4b80655d53c2d9cc814`; observer `sha256:70d500b73ad005ba9dcd9907d087b607caf792f15eb618c1d1665ef8e4752284`; independent import-origin proof and 58 affected format/source tests PASS |
| Both artifacts | Evaluator `sha256:3c36b8cddc21d4b764b2a9d2cc0f9f53b6112348f362abb9c0a41cb693ed3ab2`; both precede the latest directory-disclosure repair and adversarial-test typing cleanup |
| `debug-lexical-native-02` / `-03` | Fresh captures and CLI/MCP qualification: four workflows PASS, 120 + 120 + 120 + 150 = 510 witnesses for each exact artifact; not current-observer qualification after the latest repair |
| `debug-lexical-native-01.log` | Prerequisite failure before capture: `scip` and `scip-python` missing from PATH; not a test or evidence PASS. Existing installed qualification tools were added for the later successful runs |
| `debug-lexical-public-01` | On artifact 01, annotation passes all ten workflow gates but overall INCOMPLETE. Metadata remains FAIL for missing verification disclosure and compact size. Authority, revision and freshness remain PASS |
| `debug-lexical-public-02/{contracts,regressions}` | Artifact 02 public qualification; inspect terminal summaries before using. Partial acquisition is never a passing batch |
| `direct-call-oracle-projection-admission-01.json` | Exact helper identity unchanged; additional positive context location only. Both former API profiles still FAIL and ten wrong-identity controls remain FAIL. Debug grader SHA-256 is `99bc23fd8fb9cb6bc651771387395fe580b55faa379f7475d2936ce012a25cf5` |
| `preflight-lexical-03.log` | Formatting, full Ruff, hygiene, zero complexity and production size debt PASS; source compilation also passed before artifact 02 |

Typing work is separate from behavioral qualification. The repository-evidence
binding tests now pass all 70 tests and scoped Ty/Pyright, with all 63 original
test bodies preserved after checked-access expansion. Declaration-discovery
authority adversarial tests now pass seven tests and scoped Ty/Pyright; their
71 Ty diagnostics are removed. `declaration-adversarial-typing-preservation-01.json`
proves the complete original module AST, including 46 functions, all provider
fixtures, inputs and assertions, is identical after erasing checked narrowing.
No `Any`, casts, ignores, exclusions or assertion/input removals were introduced.
The newest complete Ty inventory is `full-ty-after-declaration-adversarial-01.log`:
**2,685 diagnostics remain**. The complete Pyright counterpart reports **2,697
errors**. Both commands remain red. Scoped checks do not close T09.

Next executable batch:

1. Run `make agent-preflight`, scoped Ty/Pyright and the affected source/format
   ring. Freeze the current observer including directory disclosure, compile
   source once, produce one deterministic source ZIP, assert independent import
   origin, and run focused tests from that extraction. Keep earlier artifacts and
   reports historical. Do not acquire evidence from files being edited.
2. Using that extraction, run all four debugging workflows at both revisions
   through API, CLI and official MCP, every required variant/format and stale
   control. Preserve current grader, source identities, tasks, review flags and
   the 4,000-token limit. Record exact failed witnesses; API estimates alone do
   not close size, display or transport gates.
3. Regenerate all four native workflows for the exact observer. Prepend the
   existing `.hashmarks/qualification-tools/bin`,
   `.hashmarks/qualification-tools/node_modules/.bin` and project `.venv/bin`
   to PATH; no tool-version policy or package-specific product rule is needed.
   Expect all 510 actual witnesses, not merely four capture-binding statuses.
4. Aggregate only compatible current reports with the complete campaign source
   map. Expect INCOMPLETE until independent reviews, exact witness membership and
   corpus floors close; preserve FAIL if any hard gate or required fact fails.
5. Admit eight further genuine debugging problems across two additional target
   repositories, using the existing source-first intake and finite runtime QA
   producer. Then finish the eight missing capability catalogs, independent
   positive/adversarial/display oracles and witness families described in T07.
6. Continue T09 typing cleanup using checked narrowing and preservation proof,
   then T10 deterministic full-test membership, unseen heldouts, economics with
   noise controls and final exact-artifact qualification. No 5/5 or clean-pass
   claim is valid before all of those complete.

### Historical same-name checkpoint: 2026-10-16

That repair adds bounded `same_name_declarations` to a retrieved callable:
other same-named callable declarations in that exact file, with source spans,
revision, generation and omission accounting. It establishes no runtime identity,
inheritance, dispatch or owner. The initial codec, contract reader and all
presentations retain it. The first format ring caught and repaired a text omission;
`same-name-declarations-ring-03.log` passes 54 tests. Modified owners pass scoped
Ty/Pyright. This newer repair makes earlier observer qualification historical.
Fresh public/native acquisition and a new artifact are required.

`natural-probe-04` is an API-only after-source probe. All four frozen task facts
now pass in default and initial profiles. The override fact is exposed in the
new declaration context. The original exact path/symbol/span expectation and
direct-locator check are retained, with a second positive source-fact location.
`same-name-oracle-projection-admission-01.json` proves both old API profiles still
FAIL under the extended oracle, and wrong symbol/path/span probes remain FAIL.
An API projection estimate is 3,680 tokens for initial compact and 3,289 for text;
complete real CLI/MCP responses still need qualification.

The following retains the earlier checkpoint; later narrative sections retain earlier
measurements under their original identities. No capability is claimed at 5/5.
Eight entire catalogs remain missing: 2, 8, 9, 11, 15, 16, 18 and 20. The partial
debug catalog has four of twelve required problems and one of three repositories.

Completed observer and QA work:

- Correlation has its JSON CLI surface, owned by repository CLI and delegated to
  `CodeMap.correlate_evidence`. Real API/CLI/official MCP tests cover four formats,
  current and deliberately invalidated revisions, ambiguity and prior packets.
- Runtime observations are integrated into existing corpus admission, workflow
  acquisition, artifact-bound witnesses, pure regrading and frame metrics.
  Runtime capture execution stays in development QA. Empty successful controls
  add no frame or negative-evidence proof. Missing transports yield incomplete
  measurements; contradictions dominate missing information.
- Retained capture grading now rejects a CLI response filed as MCP, duplicate
  formats and context mismatches. Packet and projection grading share one exact
  byte snapshot. The previous implementation could emit a passing MCP witness
  from CLI bytes; the regression now exercises that real authority defect.
- The debug suite has four pinned SQLAlchemy problems and eight source trees:
  logging-token reset, aggregate strings, custom metadata warning and Python
  3.14 forward-reference diagnostics. All forty frame units remain accounted for;
  thirty-nine have independent exact source declarations and the comprehension
  remains unsupported. This source admission is not measured correspondence.
- All four problems now have fresh captures from the checked-in finite producer,
  including Python executable, producer, observer and evaluator identities. The
  producer retains the complete displayed ordinary cause/context chain and
  restores its temporary module registration on success and failure. The Python
  3.14 sample is compiled without inherited future-annotation flags. After the
  forward-reference fix, MappedAnnotationError is intentional; that invocation
  still raises. The former one-off captures remain historical.
- Source-only aggregate-strings review added the new StrSQLCompiler override and
  the actual string-rendering regression to executable task oracles. The base
  signature change, DefaultDialect guard and actual innermost failure frame
  remain separate facts. Native nominations were not silently expanded.
- Natural-language retrieval now admits bounded derived-word lookup alternatives
  and declared scope/signature context. Multiword disclosure hints can appear
  early, while explicit locators retain precedence. Canonical omission counts,
  ambiguity, selected edit and selected verifier authority remain independent.
  No framework names or oracle hints participate in retrieval.

Measured evidence under
`.hashmarks/backend-e2e/explicit-retrieval-20261016/`:

- `runtime-natural-regression-01.log`: 197 passing tests cover the current
  retrieval/action/freshness and runtime/CLI/MCP integration. The earlier
  `runtime-integrated-regression-02.log` records 199 passing tests for runtime workflow,
  source/adversarial admission, byte integrity, pure regrading and existing
  backend/native qualification. A previous run retained an implementation-drift
  failure after a QA edit during acquisition; the stable rerun passed.
- `debug-public-01`: the earlier two-case public run is FAIL. Logging-token reset
  passes its recorded gates; aggregate strings misses essential task source and
  owner evidence. Runtime correlation itself passes across API/CLI/MCP, including
  all deliberately invalidated bindings. Seventeen of eighteen frames have exact
  callable correspondence; the comprehension remains a miss.
- `debug-native-01`: fresh native captures pass the two original cases. This
  proves nominated producer/source/transport binding, not task sufficiency. Both
  two-case reports have older suite/grader identities and are not current
  four-case evidence.
- `debug-native-02` completed four cases, but the two new cases had no frozen
  native fact oracles and emitted zero fact witnesses. Its binding/transport
  PASS is not fact qualification. Nine exact native target oracles were then
  frozen from existing source labels and member bytes, without reading native
  response facts. `debug-native-03` freshly reacquired all four cases and passes
  510 artifact-bound source/definition/stale/CLI/MCP witnesses. Review remains
  pending, and its observer predates the same-name disclosure repair.
- `debug-natural-public-02` is a complete genuine before/after run of aggregate
  strings. Authority, freshness, revision, initial size and owner top-three gates
  pass. One frozen fact fails in both profiles and every surface: the new
  override. Eighteen failing witnesses preserve that omission. Initial
  compact/text responses peak at 3,620 tokens across both transports/revisions.
  Runtime correlation passes; thirteen of fourteen frames have exact callable
  correspondence, and the comprehension remains unsupported. The report is
  historical after the same-name disclosure repair.
- `natural-declaration-ring-07.log`: 33 passing retrieval/verification tests.
  `natural-probe-03`: an API-only genuine after-source probe places the base
  compiler method in the first three findings. Its initial API envelope is 6,813
  bytes (about 1,704 estimated tokens). The new override is still missing. This
  is neither full public transport proof nor a passing workflow; preserve the
  stronger frozen oracle and repair the remaining omission.
- `runtime-chain-ring-02.log`: 23 passing tests for actual cause/context,
  suppressed causes, cycle accounting, source frame identity, native annotation
  semantics, module lifetime and existing runtime witnesses.
- `runtime-captures-02/admission.json`: four problems, eight source trees and
  forty frame units admitted; all prior source declaration identities retained.
  Capability/display/adversarial review flags remain false.
- `full-ty-after-natural-01.log` and its Pyright counterpart: 2,840 Ty diagnostics
  and 2,851 Pyright errors. Modified retrieval, runtime producer and witness
  owners pass scoped checks. Full configured typing remains red; T09 is open.
- `full-ty-after-chain-01.log` and its Pyright counterpart remeasure the
  producer/chain changes: the same 2,840 Ty diagnostics and 2,851 Pyright errors.
- `source-runtime-natural-01/source.zip` has 1,121 members and SHA-256
  `ea68900512eca464f6c6660f662658f90b76f08a571a884b6e9dc1d804f27ee5`.
  An independent extraction verifies import origin and both implementation
  identities, then passes 124 selected tests. It predates the new native target
  oracles and same-name disclosure. Its observer is
  `sha256:12f373399c492162f1c6cdd8d18077d26fb5bc201024966137d74aba33169ddd`;
  evaluator is `sha256:9337980982f182f448098bc8defc4b4d63887b6ca33933c6710c81b33d1471ad`.
- `native-lsp-regression-01.log`: all 33 native LSP change regressions pass.
- `preflight-runtime-natural-02.log` and `compile-runtime-natural-01.log`: Ruff,
  formatting, portable hygiene, zero complexity/file-size debt and source
  compilation pass. These do not substitute for behavioral qualification.

The next debugging work is concrete:

1. Qualify the same-name disclosure against the unchanged source facts and all
   four genuine workflows. Keep the pre-repair public failure and the six
   wrong-identity oracle controls. Reproduce a defect before making another
   observer change; do not add repository-specific retrieval rules.
2. Freeze source, then acquire both revisions through API/CLI/official MCP for
   all four cases and required variants/formats. Measure complete visible initial
   compact/text responses against 4,000 estimated tokens. API estimates and
   historical reports do not satisfy this step.
3. Reacquire fresh native evidence for the current observer and current four-case
   suite. Keep nominated native source scope separate from task-fact scope. Bind
   reports to current suite, grader, observer, evaluator, captures and source.
4. Admit four genuine debugging problems each in databases and Litestar. Freeze
   all source/frame oracles before observing Hashmarks. If a pool is unsupported,
   record the shortage and explicitly admit another repository instead.
5. Complete independent semantic/display/adversarial review and exact required
   witness membership. Count stage-qualified frames once. Transport copies,
   successful controls and repeated runs add no corpus breadth.
6. Continue T03–T10. Complete the eight missing catalogs, witness families, full
   typing, deterministic regression membership, heldouts, economics and artifact
   qualification before any final clean or 5/5 claim.

Preserve these intake distinctions:

- Natural lookup spends two supplement slots on StrCompileDialect and the base
  compiler method. Same-name disclosure now carries the other exact declaration
  as bounded source context. That source observation does not prove dispatch or
  inheritance. Do not convert lexical alternatives into unique edit authority.
- A proposed databases deferred-constraint commit failure was rejected before
  execution: its transaction reset occurs after successful commit/connection
  exit, so a failing commit never reaches the fix in either revision. See
  `runtime-intake/debug-intake-rejected-leads-01.json`. Existing transaction syntax
  evidence remains valid; it does not prove a debugging failure.
- Cancellation specimens need an explicitly supported capture contract.
  `asyncio.CancelledError` is outside `Exception`; an uncaptured cancellation must
  never become a successful empty control. Add a finite QA specimen and a
  decisive producer test before admitting it.

Every one of the twenty rows needs at least twelve distinct genuine problems
across three repositories, independently reviewed positive/adversarial checks,
and every required witness. Formats, variants and repeated runs do not increase
breadth. Cross-capability reuse requires separate reviewed semantic evidence.

Owner top-three recall must reach 95%; reviewed frame correspondence and initial
essential-evidence recall must reach 90% over frozen eligible populations.
False exact authority, stale promotion and presentation losses are hard failures.
Initial CLI/MCP compact/text replies at both revisions must fit 4,000 estimated
tokens, counting actual complete consumer-visible responses. Every deliberately
invalidated source binding must be detected. Missing proof stays INCOMPLETE;
known failure dominates missing. Empty populations never pass.

Full configured Ty, Pyright, Ruff, formatting, hygiene, complexity, deterministic
regressions, heldout evaluation and artifact qualification must pass. Historical
scoped passes cannot replace these checks.

## Successor foundation checkpoint

The successor now has executable task authority checks, transition-bound
freshness witnesses, native packet/definition witnesses and shared retained-byte
regrading. Repository-qualified selectors distinguish identical relative paths
and comparison stages. Native/workflow artifact namespaces remain explicit in
aggregation. Native oracle admission requires both stages and exact target
membership. Invalid boolean, floating-point, negative or textual definition roles
are rejected instead of being promoted to a native definition token.

The two JSON CLI commands are implemented under repository CLI ownership and
covered through actual CLI and official MCP. Query envelopes use their existing
canonical presentation; dependency snapshots remain supplied inputs rather than
instructions to run a dependency tool.

The first complete successor core measurement acquired twelve genuine public
workflows. Five pass every current workflow gate: fetch cancellation, sender node
failure, metadata future, logging-token reset and partial pull batch. Seven retain
owner/symbol/verifier or initial-evidence failures: stable offset, failed begin,
pickle extra criteria, aggregate strings, middleware enter error, subscriber stop
and concurrent queue lifetime. Failed begin also returns initial MCP compact
responses of 4,080/4,082 estimated tokens before/after, exceeding the hard limit.
These are retained repair inputs, not waived cases.

The corresponding fresh native run passes twelve specimens and retains 1,440
source/artifact-bound witnesses. It proves nominated native binding/transport,
not task sufficiency. Core workflow and native inputs were both ADMITTED by the
first aggregate, which remains FAIL. Missing model/async reports and the twelve
missing catalogs remain incomplete. No row is qualified at 5/5.

Measurements are under `.hashmarks/backend-e2e/campaign-v2/`: `input-baseline-01`,
`core-public-01`, `core-native-live-01`, and `aggregate-01`. The final native-role
hardening changes evaluator identity: earlier reports remain bound to their
original evaluator and must not be relabelled as current campaign admission.
`native-post-hardening-revalidation-01.json` records the narrower retained-native
artifact/source revalidation; it does not claim a new acquisition.

Full configured typing remains red in `typing-full-ty-01.log` and
`typing-full-pyright-01.log`: 4,649 Ty diagnostics and 4,783 Pyright errors.
Modified production/qualification owners pass scoped checks. This does not close
T09 or substitute for full configured validation.

The final focused correctness/architecture/presentation ring passes 371 tests;
the official MCP CLI-parity regression passes separately. Ruff/formatting and the
zero-debt gate pass. All twelve retained native specimens pass post-hardening
artifact/source revalidation. Full regression membership, source-extraction and
promotion artifacts remain open; these bounded passes do not close T10.

Additional source-review gap: model workflows often label their test-model
declarations but omit changed production files from task-source bindings. Complete
the task oracle scope independently without silently changing native target
membership. Independent display/adversarial/capability review remains pending.

## Ordered work

### Implementation checkpoint: 2026-10-14, starting at `649b0d9`

The profiling entrypoint's initialization-order failure is repaired. Profiling
now measures the nominated public operation through the existing closed observer
dispatcher, preserving legacy action-map cases. Receipts include evaluator
identity, which profile-shard merging preserves and checks. Source-observation
cases translate the same member/context inputs used by CLI/MCP through their
existing context validator rather than passing wire names directly to CodeMap.

Optional `task_source_labels` contain independent before/after task scopes.
Native nominations still use `source_labels`; both label sets are source-checked.
All twelve successor model cases now bind their production owner, changed source
members and reviewed verifier paths as well as their original declaration labels.
This is source-binding completion, not independent semantic/capability review.

Aggregation accepts bounded `workflow_reports` and `native_reports` lists in
addition to singular references. Singular/plural forms are exclusive. Native
list entries retain their own report and capture-root pair; acquisition IDs are
validated separately. Every input is regraded before union. Overlapping workflow
outcomes are excluded with an explicit membership rejection; neither ordering
nor a passing duplicate chooses a winner. Valid other batches remain visible.
Witness artifact namespaces bind the exact originating report digest.

Independent display checks now contribute to hard transport/presentation gates,
in addition to mechanical projection conformance. Missing declared format checks
stay incomplete. Display witnesses refer to the actual top-level or stage-specific
oracle, independently of where task checks are declared.

The baseline full typing runs at this starting revision report 5,373 Ty
diagnostics and 5,445 Pyright errors, zero warnings. Their logs are
`/tmp/hashmarks-plan-ty-current.log` and
`/tmp/hashmarks-plan-pyright-current.log`; older counts above remain history.
Eight modified qualification owners pass scoped Ty/Pyright. Scoped proof does
not close T09. Full pytest collection observed 3,969 nodes before these additions;
the final candidate needs new collection and exact regression membership.

Current-source API-only acquisition is retained under
`.hashmarks/backend-e2e/implementation-20261014/api-baseline-01/`.
It explicitly omits CLI/MCP and cannot establish transport, initial-size,
capability-proof or final qualification. Completed receipts survive an interrupted
acquisition; incomplete work never counts as proof.

This acquisition completed all 36 entries. The seven core owner/symbol/verification
failures remain reproduced. Model misses concern iterable-response verification,
root-schema verification and the before-revision `sa_type` verifier. Three async
verification misses remain. The asyncpg class authority failure was independently
traced to an incorrect wildcard `equals` oracle rather than product escalation:
several retrieved classes have different source revisions. The corrected oracle
requires every class authority qualifier and binds the revision to the exact
source-reviewed file/class. Its genuine CLI/MCP acquisition is retained at
`async-oracle-public-01`; all facts/authority/freshness/transport/presentation/size
gates pass. Initial-recall and owner metrics remain unqualified. Maximum initial
MCP compact/text sizes are 3,500/2,769 tokens across both revisions.

Fresh core native acquisition is split into three disjoint batches of four under
`native-batch-00`, `native-batch-01` and `native-batch-02`, with separate matching
capture roots. All twelve specimen outcomes pass. Each batch report correctly
remains INCOMPLETE for its missing suite membership. `reports-02.json` and
`aggregate-02` demonstrate admission of all three original acquisition identities
without replay, a fabricated merged acquisition, or a duplicate workflow winner.
The aggregate remains FAIL with incomplete input integrity: model/async native
proof and eleven async public outcomes are missing, and reproduced failures stay
failed. None of the twenty rows is qualified.

The current focused source ring passes 221 tests. A deterministic source ZIP and
independent extraction under `source-candidate-01` pass 83 focused tests, import
origin verification and CLI import/help smoke. Source compilation, lock convergence,
Ruff/formatting, hygiene and zero-debt/size gates pass. These are bounded candidate
checks; the ZIP predates this documentation checkpoint update and does not claim
final artifact closure. Full regression membership and promotion qualification
remain open.

The twelve missing catalogs, independent capability/display/adversarial review,
remaining witness families and special metric acquisition/regrading, fresh
public/native transports, full typing, comparable economics, unseen holdouts and
exact-artifact final qualification remain open. No 5/5 completion is claimed.

### Implementation checkpoint: 2026-10-15, starting at `650e8f0`

Two generic verification defects are repaired in the existing relevance owner.
First, reverse-reference discovery could displace an already retrieved test from
the bounded candidate reply. Candidate disclosure now interleaves the existing
reference and task-retrieval orders after verifier selection. Selection, exact
reference claims and total candidate membership retain their existing owners.
Second, verification discarded two-letter identifier components that the shared
task tokenizer retains. Components such as `db` in `db_type` now remain visible
as lexical task evidence; lexical overlap does not establish a reference.

The neutral regressions reproduce both defects with the previous behavior.
They check bounded disclosure, unchanged selected verification, the complete
candidate count, initial-packet preservation and the absence of manufactured
references. The focused verification/initial-packet/CLI/service ring passes
58 tests. Both modified Python owners pass scoped Ty and Pyright. Ruff,
formatting, hygiene, complexity/file-size preflight and source compilation pass.

Current genuine CLI/MCP acquisition is retained under
`.hashmarks/backend-e2e/implementation-20261015/model-disclosure-public-02/`.
Litestar root-schema and SQLModel `sa_type` workflows pass their current facts,
freshness, revision, transport, presentation and initial-size gates at both
revisions. The selected Litestar verifier remains the backend test; its nested
schema regression is now also disclosed as a candidate. Compact/text initial
replies peak at 3,320 tokens for Litestar and 2,187 for SQLModel. The FastAPI
iterable-response verifier miss remains failed at both revisions. Its task has
not been rewritten and its expected verifier has not been waived. Independent
authority/initial-recall/capability checks remain incomplete for these cases.

The temporary native-tool installation was absent. Pinned development producers
were restored under `/tmp`; the official SCIP decoder archive was checked against
its release metadata digest before use. Fresh model-native acquisition now covers
all twelve specimens, in four disjoint reports `model-native-live-01` through
`model-native-live-04`, with matching `model-native-captures-*` roots. All twelve
specimen outcomes pass. Each report correctly remains incomplete for unselected
suite membership and retains its own acquisition identity. This proof covers
nominated native source bindings and transports, not task sufficiency or runtime
model validation.

Public model membership is also complete across `model-disclosure-public-02`
and `model-public-batch-01` through `model-public-batch-03`. Eleven workflows
have no failed current gates; FastAPI iterable-response remains failed.
`model-reports-01.json` selects these four reports and the four native reports.
`model-aggregate-01` independently regrades and ADMITs all eight inputs, with
their original artifact namespaces and acquisition identities. It remains FAIL:
the known FastAPI miss survives, authority/capability proof remains incomplete,
and current core/async inputs are not supplied. No historical report is relabelled
as current. All twelve model workflows meet the compact/text initial-size limit;
the full population maximum is 3,320 estimated tokens.

The pinned four-repository heldout corpus completes all 24 cases. Twenty pass
their expected classification; four Hashmarks cases fail: `paths-under`,
`sync-remove-stale` and `prune-discovery` are WRONG_AMBIGUOUS, and
`mcp-task-evidence` is OVER_AMBIGUOUS. A fresh comparison from an independent
extraction of starting commit `650e8f0` produces the same four failures. Both runs
retain zero FALSE_SAFE_EDIT, FALSE_UNIQUE and WRONG_VERIFIER classifications.
These failures predate this repair and remain required work; the heldout gate is
not green. Evidence is in `heldout-01` and `heldout-baseline-01`.

The starting revision's full configured runs report 3,479 Ty diagnostics and
3,484 Pyright errors (zero warnings), retained in `typecheck-baseline.log` and
`pyright-baseline.log` under the same output root. Scoped passes do not close T09.
The twelve missing catalogs, independent oracles and required witness membership,
remaining witness families, fresh full campaign, economics, unseen backend
holdouts, deterministic regressions and final artifacts remain open. No row is
claimed as qualified at 5/5.

### Messaging checkpoint: 2026-10-15, base `dfe9ea2`

The branch advanced through the prior verification repair and a separate
filesystem-evidence change. Both were preserved. Earlier reports remain bound
to their recorded observer/evaluator bytes and are not current qualification of
this later candidate.

The first missing catalog is now admitted at
`benchmarks/repository_evaluation/manifests/backend-campaign-v2/suites/messaging/`:
thirteen distinct genuine changes across aiokafka (four), aio-pika (four) and
FastStream (five). Twenty-six exact before/after archives pass source admission.
Method ranges, call lines, raw range hashes, definition lines and stage-correct
verifier sources are frozen independently of product responses. Method ownership
oracles use declaration ranges; native nominations retain their original scopes,
including coroutine decorators. The additional producer case preserves all
consumer cases and supplies actual publication evidence.

The suite requires fresh native acquisition and declares 2,286 exact positive/
adversarial boundary witness contexts. Its capability review remains explicitly
false. Existing checks prove literal calls/arguments, revisions and conservative
authority. They do not yet qualify all answer-bearing conditions, branch returns,
tuple selection, display facts or initial evidence sufficiency. The catalog README
names these remaining semantic assertions. Do not promote review because a run
passes the narrower checks. Three source-only holdouts are reserved separately;
their exact task/oracle admission is still pending.

Genuine baseline acquisition reproduced missing boolean keyword and positional
identifier facts. The existing `function_boundary_syntax` owner now exposes
bounded argument syntax, explicit expansion, omitted counts, literal values and
unknown expression/binding states. It never resolves or executes the callee.
Neutral regressions cover bounds, hidden expansion, oversized/nonfinite values,
unsupported expressions and actual CLI/official MCP formats. A further real CLI
wire probe reproduced JavaScript integer precision loss. Integer values now use
declared decimal-text encoding; the same Node decoder preserves the exact value.
The focused ring passes 72 tests; the expanded CLI/MCP precision fixture passes
separately. Both modified Python owners pass scoped Ty/Pyright and full Ruff.

Current post-repair public acquisition is in `messaging-public-precision-01`
through `-04` under `.hashmarks/backend-e2e/implementation-20261015/`. All thirteen
boundary check sets pass at both revisions. Eleven workflows pass their current
fact/transport gates. Two remain failed: `faststream-ack-cancellation` misses its
verifier at both revisions; `faststream-batch-nack` misses the before verifier.
Four additional top-three ordering failures remain visible: aiokafka commit
refresh, aio-pika nack scope, aio-pika iterator channel close and FastStream ack
error. They must not be hidden by changing the frozen population or oracle.
Every initial compact/text reply fits 4,000 tokens; the maximum is 3,606.

Fresh native acquisition after the precision repair covers all thirteen
specimens in `messaging-native-precision-01` through `-04`, with matching
`messaging-native-precision-captures-*` roots. All specimen outcomes pass. The
temporary tool prefix disappeared during work; pinned producers were restored
to ignored `.hashmarks/qualification-tools` storage, with the official decoder
checksum verified. The prerequisite failure is retained separately and never
counted as a native specimen failure or a completed capture.

`messaging-intake/precision-reports.json` selects the four public reports and
four original capture/report pairs. `messaging-aggregate-precision-01` regrades
and ADMITs all eight inputs, with zero rejections. It remains FAIL with incomplete
input integrity: the three verification misses remain failed, capability review
is incomplete, and current core/model/async inputs are not supplied. All 5,133
public witnesses retain their exact context and source/artifact bindings. The
first aggregate correctly rejected file-byte digests where canonical JSON
digests were required; the references were corrected without changing oracles,
captured bytes or admission rules. Earlier pre-precision reports remain history.

The latest full typing run still fails: 3,476 Ty diagnostics and 3,480 Pyright
errors, zero warnings. Logs are in `messaging-intake/full-ty.log` and
`messaging-intake/full-pyright.log`; scoped checks do not close T09. Eleven entire
catalogs remain missing (2, 4, 8, 9, 11, 14, 15, 16, 18, 19 and 20). Messaging
still needs full semantic/display review, the verification/ordering repairs and
final qualification. Runtime, dependency, service, language and economics witness
families, the remaining independent reviews, complete current campaign inputs,
unseen holdouts, deterministic regressions, typing and final artifacts remain
required. No capability is claimed at 5/5.

### Verification identity checkpoint: 2026-10-15, base `4de9225`

Genuine messaging observations exposed a hard authority defect that the earlier
authority-label checks did not detect. A reverse-reference row for `message.nack()`
could become a direct reference to Confluent's `KafkaMessage.nack` solely from
the leaf name. Kafka, Redis and other receiver identities were not established.
The same defect reproduced for a module function: `client.emit()` could become
an exact reference to an unrelated `alpha.emit`. Earlier authority-gate passes
therefore prove their recorded checks only; they do not close semantic authority.

The repair preserves the selected declaration's qualified name through direct
and bounded indirect lookup. An explicit imported member needs its declared
module and member scope; arbitrary, constructed, shadowed or conflicting receivers
remain unresolved candidates. Module-function use needs a qualified import/name
or module-attribute reference. An unused import plus an unrelated same-named
attribute cannot establish use. Indirect attribute proof is kept separate from
the direct endpoint. Any unresolved reference identity prevents qualified absence
or unique-verifier promotion even when another verifier has positive evidence.

`verification_reference_syntax.py` owns the immutable AST syntax projection.
Responsibility classification: EXTRACT RESPONSIBILITY under
`docs/maintainers/RESPONSIBILITY_REFACTORING.md`. The measured correctness risk
was file-level/short-name identity being promoted to exact member authority.
CodeMap keeps repository reads, cached AST acquisition, freshness, import
resolution and selection; the syntax module has only standard-library inputs
and the same process-local snapshot cache key. This introduces no persisted
identity, type inference, execution or second repository authority.

The initial focused ring passes 54 tests, including positive imported members and
functions, unknown/foreign receivers, rebinding, conflicting aliases, unused
imports and indirect-proof isolation. Nine CLI/service/official-MCP argument
regressions also pass. Scoped Ty/Pyright and `agent-preflight` pass. Logs are in
`.hashmarks/backend-e2e/verification-identity-20261015/`. These passes do not replace
full configured typing, the complete regression selection or current campaign
acquisition. Reports from before this repair remain historical.

The broader ring first exposed a false ambiguity for an explicit facade-local
override. Unresolved test-binding accounting now stays scoped to test candidates;
the canonical import resolver continues to own source-local override identity.
That regression passes after repair.

The production-heavy lexical loss below was then reproduced and repaired. The
existing store query accepts an optional exact path scope and applies it before
ranking/limit; decision-session cache identity includes that scope and
distinguishes an empty scope from an unrestricted one. Verification supplies
canonically classified test paths, observed once per request. Tests retain weak
candidate authority. A neutral fixture with 80 stronger production matches now
exposes its existing test and excludes production `src/test_cancellation.py`.
The combined correctness/authority/selection/contract/native-LSP/session ring
passes 183 tests. All seven modified production owners and the three modified
test owners pass scoped Ty/Pyright. Full-project checks remain open.

`genuine-after-public-01` completes both frozen workflows at the earlier repair
identity. Both after-verifier checks pass; both before checks fail. Authority,
freshness, revision, owner top-three and initial-size checks pass their recorded
assertions. Overall facts, initial evidence and transport/presentation gates
remain failed. The later facade and lexical repairs change observer identity;
`genuine-after-public-02` reacquires the same unchanged two-workflow population.

That acquisition completes at observer
`sha256:81556595b4030c5e05283df34f0799a79bafd59bacfbff58c811efb631b17c9e`.
Its two after-verifier checks pass and both original before expectations fail.
All sixteen initial CLI/MCP compact/text responses fit the limit; the maximum
is 3,586 tokens. These are current observations for the original oracle, not a
passing complete campaign.

Source review then corrects only the batch-nack before verifier to
`tests/brokers/confluent/test_consume.py::TestConsume.test_nack` (201–234), and
adds an exact after regression binding (32–53). The grader records the source
reason and limitation. Native nominations and capability review are unchanged.
The campaign's canonical grader reference is updated. Original grader/campaign
bytes, source review hashes and both failed acquisitions remain under
`oracle-review-01`. New acquisition uses `genuine-corrected-oracle-public-01`;
old reports must not be relabelled to this new grader identity. The corrected
batch-nack acquisition completes with all ten current workflow gates passing at
both revisions, 381 retained witnesses, and real CLI/MCP capture. Its summary is
still INCOMPLETE because the other workflows, capability review and complete
campaign evidence are not present. This does not promote capability 13 to 5/5.
The grading regression ring passes 81 tests. Full configured typing was rerun and still
reports 3,476 Ty diagnostics and 3,480 Pyright errors, zero warnings.

`source-candidate-02/source.zip` includes the new syntax owner and preserves
source modes. An independent extraction imports its own Hashmarks and passes
273 tests, including the authority, native-LSP, session, grading, CLI/service and
official-MCP rings. The ZIP is a bounded development candidate, not final
promotion proof. This paragraph updates documentation after that snapshot;
production, test and grader bytes remain identical. Re-prove the complete final
artifact only after the remaining implementation and qualification work.

Next steps, in order:

1. Preserve the completed `genuine-corrected-oracle-public-01` acquisition and
   inspect its exact witness/source/format contexts when composing the next
   current campaign report. The other twelve messaging workflows still need
   current acquisition under the corrected grader. Cancellation-before remains
   a failed original oracle and needs its own source
   review; do not change it based solely on the currently selected middleware test.
2. Extend independently source-bound authority checks beyond domain-label
   strings. A foreign receiver must never be asserted as a direct correspondence
   to the selected member. Unknown receivers must remain unknown in API, CLI,
   MCP and initial compact/text projections. Bind each assertion to the exact
   candidate record, declaration scope and revision; a matching path alone is
   insufficient. Retain a pre-repair failure and reacquire after the repair.
3. Preserve the completed batch-nack source review and exact before/after hashes.
   The before test supplies relevant existing negative-acknowledgement coverage;
   it does not prove tuple/batch seek behavior. Keep the after seek regression
   and its asserted behavior. Apply this source-first review to other before-test
   nominations before treating all remaining misses as product retrieval defects.
4. Qualify the scoped verifier-retrieval repair on genuine sources. Preserve the
   neutral production-fanout and scope-cache regressions. Keep visibility and
   completeness independent and preserve candidate-only authority. Re-run the
   cancellation workflow and compare initial candidates, omissions, token counts
   and edit identity. Investigate any remaining miss at its generic owner;
   never introduce a broker/framework name exception or change the selected edit
   to improve test retrieval. Source-candidate disclosure may carry a positive
   reference to another explicitly named declaration in `source_candidate_basis`
   while `edit_relationship` remains unestablished. Do not reinterpret that as
   direct correspondence to the selected edit owner or erase its admitted basis.
5. Reacquire the reviewed messaging population only after these semantic owners
   are frozen. Recheck all required source/display/adversarial assertions before
   admitting capability review. Then continue T03–T10, including the eleven
   missing catalogs. This checkpoint qualifies no capability at 5/5.

### Corpus and typing checkpoint: 2026-10-15, observer unchanged

Pinned-source review corrects cancellation-before to
`tests/brokers/kafka/test_ack_policy.py::TestAckPolicy.test_commit_called_in_middleware_on_error`
(173–211): the existing ordinary-error test explicitly asserts commit under
ACK/REJECT_ON_ERROR. The after-only cancellation/redelivery regression is bound
separately (18–62). The distinction is preserved; before coverage is not called
cancellation coverage. Original grader/campaign bytes and source hashes are in
`.hashmarks/backend-e2e/qualification-20261015/cancellation-oracle-review/`.

Full fresh messaging public acquisition completes all thirteen workflows under
the corrected oracle. Every fact, authority, freshness, revision, initial-size,
CLI/MCP and presentation gate passes its recorded checks. Four owner top-three
failures remain: aiokafka commit refresh, aio-pika nack scope, aio-pika channel
close and FastStream ack error. Do not discard them or turn exact target intent
into established edit ownership. The returned explicit target can be resolved
while retrieval buries its exact declaration below weaker file/doc/test hits;
investigate projection ordering independently of ownership authority.

Fresh native acquisition also completes all thirteen messaging specimens and
all twelve newly admitted transaction specimens. Both native reports are PASS
with no missing workflows. These are explicit source/native binding and transport
proof, not runtime success or complete capability review. Public messaging,
native reports and captures are under `qualification-20261015/{messaging-public,
messaging-native,messaging-native-captures,transaction-native,transaction-native-captures}`.

The new `suites/transaction/` catalog contains twelve distinct genuine changes,
four each from SQLAlchemy, databases and Litestar, over twenty-four exact Git
archives. Source admission passes. Declarations, direct call lines and exact
before/after test ranges were frozen from source/diffs before measurement.
The suite declares 2,043 exact positive/adversarial boundary witness contexts and
requires fresh native acquisition. Existing and new tests have separate stage
bindings; missing dedicated regressions and mocked-session limits are explicit.
The existing failed-BEGIN problem has independent transaction assertions here;
reuse does not create another distinct global problem. Source-only holdouts are
reserved separately in the catalog README.

All capability-14 review flags remain false. Conditions, assignment/cleanup
state, helper bodies, release scopes, essential initial display facts and any
required runtime witnesses still need independent executable proof. A helper
name does not establish a commit or an execution path. The public transaction run
completed all twelve workflows and its summary is FAIL. The prepared-transaction
workflow misses its engine verifier at both revisions and exceeds the initial
MCP compact bound after the change (4,121 tokens). Two Litestar cases miss the
bigint repository verifier at both revisions. Six owner top-three failures and
two additional initial-evidence failures remain in that historical population.
Keep the exact report under `qualification-20261015/transaction-public`; it is
bound to its original observer, not the later repairs below. The source map has
104 admitted source IDs. Campaign aggregation must preserve missing current
core/model/async public/native inputs and every retained failure.

Typing work adds checked object/record/scalar narrowing to the existing native
LSP tests; it adds no unchecked casts, ignores, Any or configuration exclusions.
All 33 native-LSP regressions pass, and that file passes Ty/Pyright. Full configured
typing decreases from 3,476/3,480 to 3,406 Ty diagnostics and 3,410 Pyright errors,
zero warnings. The backend grading/workflow regression ring passes 150 tests.
Full typing and full deterministic regression membership remain open.

Ten entire catalogs remain missing: 2, 4, 8, 9, 11, 15, 16, 18, 19 and 20.
Messaging and transaction breadth do not complete their independent semantic
reviews or final qualification. No capability is promoted to 5/5 here.

### Retrieval and verification checkpoint: 2026-10-16, base `50cdc10`

Two generic disclosure defects are repaired using existing repository indexes.
An exact qualified declaration named in the task now precedes weaker retrieval
matches, including at limits one and three. A supplied literal path confines
that disclosure to the requested file. Duplicate declarations remain visible
and unresolved; changing disclosure order does not establish edit ownership.
Canonical/supplement omissions remain accounted for and denied declarations
remain hidden. Neutral regressions exercise API/default/initial responses and
the actual CLI and official MCP across all presentation formats.

Candidate-only verifier discovery now includes source modules in the test
domain as bounded intermediates. For example, a test-model module references a
source class and a test imports that module's helper. Each admitted intermediate
has a current member revision, and the candidate retains its exact intermediate
path/revision. Direct reference evidence ranks before indirect evidence, which
ranks before lexical matches. A sixteen-module bound is explicit. Hidden,
stale or wrong-owner modules cannot provide the claimed source relationship.
This extends disclosure around unresolved source candidates only: selected
verification, edit ownership, execution and negative-evidence authority do not
change. Candidates still state `edit_relationship: unestablished` and
`verification_selection_authority: false`.

The frozen observer for the combined repairs is
`sha256:7dc0bebebb6cf5cfe7d3363f25e374fd24706599c4bc523984fb42553de91014`;
the evaluator remains
`sha256:0cbbd67136969bfebb591d219333d0b652ebc9dffe30668e960a08015c0767de`.
Outputs are under `.hashmarks/backend-e2e/explicit-retrieval-20261016/`.
`transaction-helper-public-01` completes fetched-value and auto-commit cases
through API/CLI/official MCP at both revisions. Both pass all ten recorded
workflow gates and expose `test_repo_bigint.py`; initial compact/text responses
peak at 3,469 tokens. `transaction-helper-native-01` regenerates both native
specimens, with every binding/definition/stale-reopen/transport gate passing.
The native subset summary correctly remains INCOMPLETE for missing suite members.
The public report was subsequently expanded, as recorded below. Neither report
qualifies capability 14 or independently reviews its semantics.

The earlier ordering-only observer
`sha256:1ea8dba5badf81508c822829fb449b1336015877dd7e21144c38f8d8a40fae8b`
passes all ten gates for the four original messaging owner-top-three failures
under `genuine-after`, with fresh native specimens under `native-after`.
Initial compact/text responses peak at 3,306 tokens. The combined candidate's
four-case messaging reacquisition under `ordering-with-helper-public-01` also
passes all ten gates for every case, with initial compact/text responses peaking
at 3,333 tokens. Both public acquisitions then completed their full original
suite populations, reusing only matching completed receipts. Messaging completes
thirteen cases, eleven passing every recorded gate; cancellation and batch-nack
lose their reviewed verifiers. Transactions complete twelve cases, ten passing
every gate; prepared-commit misses its verifier and delete-many misses owner
top-three/initial evidence. Both summaries are FAIL. Authority, freshness,
revision and initial-size gates pass throughout both populations; maximum
initial compact/text replies are 3,462 and 3,833 tokens respectively.

`verification-ring-helpers-01.log` records 114 passing focused regressions;
`explicit-transport-helpers-01.log` records ten passing disclosure/transport
tests with no skips. Both modified production owners and their new tests pass
scoped Ty/Pyright. Checked object/array/scalar assertions also repair the
handler-body regression file without casts, ignores or weaker assertions; all
seven handler tests pass and both scoped type checkers report zero errors.
Formatting, full Ruff, hygiene, zero complexity debt and file-size gates pass.
Full configured typing remains red: `full-ty-helpers.log` reports 3,366 diagnostics
and `full-pyright-helpers.log` reports 3,374 errors, zero warnings. The preceding
measurement was 3,401/3,406. Scoped passes do not close T09.

Actual pinned-source failure acquisition adds two SQLAlchemy problems and
27 retained frames under `runtime-captures`. Logging-token reset changes from
AttributeError to a successful query. Aggregate-strings changes from TypeError
to CompileError; the latter is still a failure, not a successful repair.
`runtime-correspondence/regraded.json` retains a strict runtime-function grade
of 24/27: two comprehension frames map to their containing source declaration,
and one canonical symbol includes a line disambiguator. Do not relabel these
as exact runtime callable identities. `runtime-correspondence-bound` separately
proves current source containment, matching qualified member bytes and rejection
of deliberately invalidated member revisions for all 27 frames. That is narrow
API location/revision proof over two problems in one repository. Public transport,
independent runtime identity review and the twelve-problem debugging catalog
remain INCOMPLETE. The original exploratory summary joined anchors by position;
use the retained anchor-ID regrade, never that summary as correspondence proof.

Next execute the remaining current suite populations without weakening their
oracles, then complete T03–T10 below. The prepared-transaction verifier remains
an open retrieval problem. A later size probe at both revisions is below 4,000,
but intervening branch changes prevent attributing that difference to the
ordering patch. Ten catalogs, independent capability/display/adversarial review,
required witness families, full typing, exact deterministic regression membership,
unseen holdouts and final artifact qualification remain open. No 5/5 completion
or saturation is claimed.

### Disclosure interaction checkpoint: 2026-10-16, base `02fdbd5`

The prior checkpoint's work was committed externally as `02fdbd5`; that commit
did not change its measured observer bytes. The full-population failures expose
two further generic disclosure interactions, each reproduced before repair in
neutral repositories:

- Candidate enrichment stopped when an edit owner was established. The same
  non-authoritative source/test evidence is useful for established and unresolved
  owners. Removing that early return leaves edit and verification selection
  unchanged. The cancellation workflow then passes all ten public gates, and
  prepared-commit retrieves its engine verifier in the API-only iteration.
- Source-reference enrichment re-sorted the bounded task candidates and could
  displace an already observed behavior test with broad module-reference tests.
  It now reuses the existing verification disclosure owner to interleave the
  original task order and the source-reference order. Population/omission counts,
  independent selection and unresolved reference identity remain unchanged.

Literal-path disclosure also preserves an already resolved file locator ahead
of same-named methods from other files when the task has no qualified method.
The same order supplies the bounded natural-language candidate paths. This is
source disclosure only; ambiguous ownership stays ambiguous. Qualified method
requests retain their more specific ordering.

The repaired observer is
`sha256:ac5a2520f4a3589b2b0a13a0103dddf429d5a20213dc0eb6c6948a3f2f70454a`.
The evaluator/oracles remain unchanged. `verification-ring-fanout-01.log`
records 116 passing focused regressions, `explicit-fanout-transport-01.log`
records twelve passing API/CLI/official-MCP disclosure tests without skips, and
`adjacent-literal-01.log` records 134 passing adjacent/boundary tests. All three
modified production owners and both test files pass scoped Ty/Pyright.
`preflight-fanout-01.log` passes full Ruff, formatting, hygiene, complexity and
file-size checks. Full typing remains open under its preceding measurement.

Fresh public checks of both messaging failures and both transaction failures
complete under `fanout-messaging-public-01` and `fanout-transaction-public-01`.
Both transaction cases pass all ten gates. Messaging then completes all thirteen
cases, every recorded workflow gate passing, with initial compact/text replies
peaking at 3,453 tokens. Fresh native acquisition passes all thirteen messaging
and all twelve transaction specimens under `fanout-*-native-01`, with matching
capture roots and no missing workflows. Transaction public membership still has
ten missing cases for this observer. The partial aggregate admits all four
reports without rejection and remains INCOMPLETE for missing populations/proof.
These reports bind `ac5a2520…`, before the subsequent optimization below.

The bounded source candidate at `source-candidate-helpers-01/source.zip` contains
1,106 members, including untracked tests and preserved modes, with SHA-256
`e305d0704fab6237322b6ab3551293494f1e6bf3d9ddb9b3ab4aa0139db5e649`.
Its independent extraction proves import origin and exact observer identity,
and passes 164 focused tests including actual CLI/MCP and native-LSP regressions.
That artifact binds the earlier `7dc0bebe…` observer, not this subsequent repair.
Do not describe it as current final artifact qualification.

### AST economics and language intake: 2026-10-16

The genuine prepared-commit query reveals repeated full-module AST walks in
filesystem-lifecycle call resolution. One instrumented initial query performs
422 local-binding lookups and spends about 34 seconds in lifecycle analysis.
The classification is KEEP COHESIVE: this is syntax acceleration in the existing
AST snapshot and structural-locality owners, without a responsibility extraction.
`PythonAstSnapshot` now lazily indexes function declarations by name. The index
belongs to that exact stable-read snapshot, retains duplicate/nested/async
declarations and has no separate cache lifetime or repository authority.
Structural locality reuses it while preserving its conservative short-name
ambiguity rule and local-binding checks.

The optimized observer is
`sha256:567428497fbb6fbbb96268b435a99975c103b4c4040ebe890fa35dd9a5d9e379`.
The 77-test AST/locality/lifecycle ring passes, including same-size rewrite and
duplicate-declaration regressions. The AST owner and new tests pass Ty/Pyright.
Structural-locality's 24 pre-existing typing diagnostics remain open; scoped
success elsewhere does not imply that owner or full project typing is green.

Nine-sample measurements of the same initial operation report median 7.82s
before and 2.80s after; the independent before-version repeat reports 7.32s.
Both same-version nine-pair controls are ADMITTED with stable semantics. The
strict whole-packet fingerprint differs because producer-bound context and
derived packet identities change. Retained decoded comparisons show all other
initial facts equal; full packets differ only in context/packet identity and
the lifecycle producer identity/derived observation identity. Both contexts
validate through their existing owner against their own frozen implementation.
Do not weaken or relabel the strict comparison as WIN. This is one measured
operation, not complete capability-20 economics qualification.

Measurements and packet differences are under `prepared-*` and `ast-index-*`
in the same output root. `source-before-ast-optimization/source.zip` freezes
the prior `ac5a2520…` bytes (SHA-256
`6c75f78896313e97c5ccc2a477d33d52b141f934aa8ede63577423b61e334759`),
including the future AST-index probes that intentionally fail on that version.
The before repeat runs from its independent extraction with checked import
origin. Its first attempt lacked the normal writable cache environment and is
an environment-incomplete run; `prepared-profile-before-repeat-02` is the
completed repeat. Current full messaging and transaction public acquisition is
under `ast-index-*-public-01`; native and artifact proof must also bind these
optimized bytes before claiming current qualification.

Typing repairs narrow the handler-input and native runner/witness tests without
casts, ignores or added Any. Their two focused rings each pass thirteen tests;
all three files pass Ty/Pyright. The last full measurement before the AST
optimization reports 3,316 Ty diagnostics and 3,324 Pyright errors. The AST
cache's previously undefined Any return annotation is also repaired using its
native return type; full typing must be refreshed before reporting a new count.

The language catalog now admits twelve distinct workflows across six repositories:
six retained Python problems and six newly pinned TypeScript problems from
Fastify, Hono and Nest. Independent TypeScript-parser ranges and exact source/test
bytes were frozen before any Hashmarks measurement of those cases. Fastify's
cases are TypeScript declarations, not TypeScript runtime implementations.
One Nest case includes a genuine added integration-test file. All capability-19
review flags remain false; executable language parity, full witness membership,
semantic/display review, fresh native/public proof and heldouts remain open.
See `suites/language/README.md` for exact commits, scope and three reserved
unseen TypeScript holdouts. Source admission alone never qualifies capability 19.

Nine entire catalogs remain missing: 2, 4, 8, 9, 11, 15, 16, 18 and 20.
Independent oracles, missing witness families, current complete populations,
full typing, deterministic regressions, unseen holdouts and final artifact
qualification remain required. No capability is claimed at 5/5.

### Native declaration and projection checkpoint: 2026-10-16

The optimized `567428497…` observer completed all thirteen messaging and twelve
transaction public workflows in `ast-index-*-public-01`. Every recorded workflow
gate passes; no workflow outcome is missing. Maximum complete initial compact/text
responses are 3,454 and 3,825 estimated tokens respectively. Both suite summaries
remain INCOMPLETE because capability review and required witness closure remain
open. These are workflow passes, not twenty-capability qualification.

`source-ast-index-01/source.zip` freezes those source bytes: SHA-256
`7a8e98aec5230ee886db7e3d9e8aadd151bf0cfaebc1ebb543fc309adfc06379`,
1,110 members, with per-member hashes/modes and observer/evaluator identities.
Source compilation passes. Its independent extraction passes 29 focused tests,
including actual CLI/MCP, with explicit extraction `PYTHONPATH` and verified
import origin. The first sandboxed smoke was interrupted during transport access;
it is incomplete. `extracted-smoke-02.log` is the completed run. This artifact
predates the native TypeScript changes below.

The first genuine TypeScript run retained four failing public workflows and one
completed native specimen before qualified namespace lookup aborted acquisition.
No missing native outcomes were counted as passed. Independent TypeScript-parser
oracles exposed header-only ranges, flattened namespaces, missing private callable
fields and missing arrow-function bindings in the advisory outline.

The existing optional Tree-sitter adapter now supplies lexical namespaces,
callable bindings/fields, nested function scope and complete declaration ranges.
Native JavaScript/TypeScript names replace flat advisory names after successful
parsing. Python and other existing range owners retain their existing merge.
The adapter contract uses checked structural types rather than Any; its cache
signature advances to v2. This is KEEP COHESIVE: grammar translation and range
enrichment stay in their existing owner, with no new graph or authority registry.
`pyproject.toml` declares the optional bundled syntax extra and the test requirement;
`uv.lock` records resolution. Normal frozen setup consumes that lock. Missing
native support still exposes the advisory capability explicitly.

The isolated candidate's fresh acquisition passes all six TypeScript native
specimens in `typescript-native-ranges-native-01`; its observer is `9d9bd305…`
and evaluator `b964b29e…`. That narrower source/transport evidence is historical
after later projection fixes and does not qualify the complete language suite.

Literal name matches inside a caller-nominated file now supplement retrieval
without changing edit or verification selection. Common names and private-member
syntax remain source observations; duplicate scopes stay visible. Genuine reruns
also exposed a generic projection defect: SearchHit wire records used `lines`
while retrieval locators consumed `start_line`/`end_line`. The supplement adapter
now retains both forms. Tests require exact endpoints in default and initial
responses, rather than checking names alone. Qualified task identifiers also
recognize JavaScript `$` and private `#` members; duplicate declarations still
prevent unique ownership.

`typescript-retained-ranges-public-01` completes all six cases against observer
`58d3d0a7…`. Three pass every gate. The Hono cases expose their required source
and test facts but retain incomplete symbol-owner authority; the observed file
owner claims no exact symbol. The grader distinguishes missing precision from a
contradictory assertion, retaining failure for wrong paths, names or spans. The
unchanged independent declaration/recall checks still require exact ranges.
Fastify HTTP options retains a missing relevant-test failure. Do not waive these
states or weaken the frozen oracles to obtain a passing summary.

The next verification repair observes matching indexed test filename prefixes as
weak candidates. It binds current source/test revisions, filters visibility before
the bound, and retains the filename fact in the source-specific basis. It asserts
no import, call, runtime compatibility or test sufficiency; selected verification
and edit ownership are unchanged. The 58-test disclosure/identity ring and
166-test adjacent task-evidence ring pass. Fresh public/native qualification must
bind the final integrated candidate after this repair.

The latest full configured measurement, before the final fake-parser narrowing,
reports 3,314 Ty diagnostics and 3,322 Pyright errors. Most remaining diagnostics
are tests (2,501 Ty), with 459 in scripts and 348 in production. The native parser
owner and projection repairs pass scoped checks; that does not close full typing.
The former SimpleNamespace parser fixtures are replaced by explicit protocol
fixtures, preserving their semantic assertions. Refresh full measurements before
claiming a new total. Final deterministic regression membership, all missing
catalogs/oracles/witness families, unseen holdouts and artifact proof remain open.

### T00: baseline and prerequisites

Record HEAD/worktree state, observer/evaluator identities, lock/configuration
digests and source admission. Retain old failed/incomplete reports without
overwriting them. Use new ignored output directories. Prepare source maps with
exact suite membership, and preflight every selected native producer before any
capture. Installed tool versions are provenance, not additional product policy.
Distinguish fresh acquisition from replay.

### T03: independent oracles

Work through existing entries in batches of four. Read pinned diffs, declarations
and relevant tests without candidate responses. Freeze exact stage labels/ranges,
owner scope and resolution, verifier relevance, essential initial facts, display
checks, metric eligibility and capability-specific adversaries. Test additions
in the after revision must not become before expectations. A separate source-only
review pass must precede `reviewed: true`; a passing evaluator is not that review.

Each `capability_proofs` entry names `positive_check_ids`,
`adversarial_check_ids` and `required_witnesses`. Each witness reference includes
gate, unit ID, stage, profile, surface, format, check ID and positive/adversarial
role. Missing membership is incomplete even when individual workflow gates pass.
Declaring `authority_oracles` or `verification_oracles` metadata is insufficient;
the relevant assertions must be executable checks.

### T04: artifact-bound witnesses and pure regrading

Reuse `FactObservation`, `witness_identity` and `grade_fact_observation`. Existing
task, boundary, declaration and delta witnesses are the foundation. Complete
authority, freshness, native, runtime-debugging, dependency, nominated-service
and economics witnesses one family at a time.

Every witness retains exact artifact bytes/digest, oracle pointer, expected and
observed fact, context and source revision bindings. Live and retained-artifact
grading share one semantic owner. Regrading reads bytes and never launches the
observer or trusts supplied gate verdicts. All referenced capture/index artifacts
must be checked, including binaries referenced from artifact manifests.

Task `authority_checks` are stage-overridable and apply to default and initial
observations on every captured surface. Top-level `freshness_checks` grade the
retained stale observations and bind before/after sources separately. These
optional additions do not manufacture capability proof for legacy manifests.

Checks may use `source_paths` for one repository or `source_bindings` selectors
containing repository/path and, for comparison inputs, revision stage. Do not mix
selector forms. Same relative paths in different repositories require qualified
selectors. Missing bindings cannot establish PASS; contradicted facts remain
FAIL even when bindings are missing.

For every family prove actual positive behavior, contradiction, missing artifact,
changed bytes, wrong binding/context and failure-plus-missing composition.

### T05: aggregate admission

Extend aggregation to admit/regrade all required families and merge their exact
witness contexts. Account for every expected input as ADMITTED, REJECTED or
MISSING. Keep valid inputs alongside rejection reasons. Reject duplicates,
unexpected workflows, source/implementation drift and unsupported claims.
Native binding cannot satisfy retrieval, debugging or verifier-recall proof.

### T06: genuine transitions and native acquisition

Admit real upstream additions, deletions and explicitly nominated renames across
Python/TypeScript populations. Independently label unchanged and invalidated
bindings. Exercise persisted-state reopening and all required native targets
through API/CLI/official MCP. Preserve source-binding and capture-generation
freshness as separate dimensions. Never invent a current digest for an absent
member. Unsupported/ambiguous producer output remains unresolved.

### T07: missing catalogs

The messaging source catalog has thirteen problems across three repositories;
the transaction/persistence catalog has twelve across three. The language
catalog has twelve across six, balanced between Python and TypeScript.
Their incomplete qualification is detailed above. Debugging now has four
SQLAlchemy problems and still needs eight problems across two repositories.
The selected-call catalog now has twelve problems across three repositories;
its independent review and qualification remain open. Seven other catalogs
still require genuine source intake: 8, 9, 11, 15, 16, 18 and 20.

Each catalog targets four genuine problems per repository in the initial pool.
Inspect source history from recorded revisions; pin exact before/after archives;
write answer-blind public tasks; review semantic facts/adversaries independently;
freeze accepted membership before measurement. Reject unsupported candidates.
If a pool is insufficient, retain the shortage and explicitly admit another
repository. Never fill it with synthetic fixtures or duplicate wording.

| Capability/catalog | Initial repository pool | Required evidence and uncertainty |
| --- | --- | --- |
| 2/path | aiokafka, SQLAlchemy, FastStream | Exact direct call endpoints/direction; missing edges explicit |
| 4/debug | SQLAlchemy, databases, Litestar | Actual failure frames; wrong/stale/foreign correspondence rejected |
| 8/handler | FastAPI, Litestar, FastStream | Decorators/parameters/branches; dynamic behavior unknown |
| 9/data | FastAPI, Litestar, FastStream | Nominated components/keys/branches; runtime compatibility unknown |
| 11/config | FastAPI, Litestar, FastStream | Declared wiring/providers; runtime configuration unresolved |
| 13/messaging | aiokafka, aio-pika, FastStream | Ack/retry/commit syntax; delivery outcomes unclaimed |
| 14/transaction | SQLAlchemy, databases, Litestar | Explicit scopes/commit/rollback; success/isolation unclaimed |
| 15/dependency | Hashmarks, uv-fleet-updater, MinIO Java | Genuine producer evidence/source correspondence; coverage independent |
| 16/service | doctor-scheduler, doctor-scheduler-core, doctor-scheduler-frontend | Independent endpoints and explicit nomination; no inferred graph |
| 18/native | aiokafka, SQLAlchemy, FastStream | Reviewed required native facts, actual fresh capture and adversaries |
| 19/language | Existing Python pools; Fastify, NestJS, Hono | Both languages and neutral contracts; unsupported syntax explicit |
| 20/economics | aiokafka, SQLAlchemy, FastStream | Comparable task/revision measurements with same-version controls |

For language coverage use six Python and six TypeScript problems by default.
Reserve one new problem in each of three repositories for final heldout use
before product repairs. Existing development populations need corresponding
unseen backend holdout problems before claiming new independent holdout evidence.

### T01/T02/T08: observer repairs and full-population dogfood

Run all reviewed existing entries and new catalogs. Retain each failure before
repair. Trace missing evidence, false authority, stale binding, presentation loss
or oversize to its existing owner. Add a minimal neutral regression, repair the
generic defect, test adjacent adversaries and reacquire both genuine revisions.
Do not use expected-owner hints, framework exceptions, removed cases or weakened
bounds. Preserve verifier candidates separately from edit/verification selection.
Compression must retain admitted facts, alternatives, uncertainty and omissions.

### T09: full typing

Refresh full Ty/Pyright diagnostic inventory. Repair producer types and narrowing
in bounded groups: evidence/verification/session/query owners, production
consumers, qualification/economics, other configured scripts/examples/benchmarks,
then fixtures/assertions. Inspect actual producers before assigning types.
Correct obsolete callers rather than recreate removed APIs. Run scoped checkers
and behavior tests per group, then unchanged full configuration. No blanket Any,
unchecked casts, ignores, exclusions or lowered severity to manufacture green.

### T10: economics, heldout and final artifacts

Profile actual frozen operations rather than substituting action-map timings.
Use two warmups, nine samples and independent same-version controls. Bind source,
operation, inputs, bounds, instrumentation and environment. Measure cold build,
warm recheck, incremental changes, rename/delete, incomplete-generation recovery,
packet bytes/tokens and index/persistence costs. Validate comparability first;
missing controls/unstable semantics remain incomplete. A speed win is optional;
comparable proof and retained correctness are mandatory. Run surface calibration
before changing persistent lexical representation.

Run the exact four existing heldout archives and the reserved backend holdouts.
Retain failures. A repaired exposed holdout needs an unseen replacement before
independent closure. Format before final source freeze. Complete public/native
acquisition, every deterministic regression batch, one deterministic source ZIP
with new files/modes, independent-extraction API/CLI/MCP checks, and final-promotion
rebuild/wheel/sdist qualification. Verify source did not drift during proof.

## Commands and handoff

Acquire suites using `scripts.repository_evaluation.run_backend --suite ...
--sources-file ... --output-dir NEW`; omit `--transport` for both CLI and MCP.
Acquire native proof using `run_backend_native` with the same suite/source map,
`--regenerate --capture-root NEW --output-dir NEW`. Suite summaries can remain
incomplete because they do not contain all twenty rows; inspect membership and
gates, then aggregate. Never interpret an exit code alone as semantic proof.

Run `make agent-finish` before focused/expensive checks. Final checks include
`lock-check`, `ruff-check`, `ruff-format-check`, `source-hygiene`, `lint-debt`,
`ty-check`, `pyright-check`, `compile`, `map`, dependency/semantic dogfood and
fresh semantic acquisition. Run every `make dev-check-batch DEV_BATCH=N` in the
frozen selection (currently 0–15). Resume later batches with `dev-check-tests
DEV_BATCH_START=N`; partial batches never count and host timeouts are not product
failures. Do not rerun proven batches solely because a controller window expired.

Aggregate the successor with complete source/report maps using
`scripts.repository_evaluation.aggregate_backend`. Aggregation reads retained
proof; it never launches missing work. Complete `make artifact-check` and
independent source-extraction qualification before final handoff.

Each ticket handoff names input identities, owner, expected behavior, actual
positive/adversarial proof and remaining failures. Low models can implement
specified fixtures/plumbing/type repairs; semantic admission, authority and
cross-repository binding need a separate source-focused review. Preserve unknown
or incomplete rather than guess. Claim clean 5/5 only with twenty passing rows,
complete input admission and all configured quality/artifact gates green.
