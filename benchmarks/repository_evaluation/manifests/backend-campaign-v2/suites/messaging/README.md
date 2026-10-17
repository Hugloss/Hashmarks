# Genuine messaging qualification corpus

This catalog pins thirteen distinct upstream changes: four each from aiokafka
and aio-pika, and five from FastStream. The additional FastStream case includes
producer publication alongside the consumer/acknowledgement cases. Each stage has
an exact archive identity, independently
selected method range and call site, and relevant existing test source. All
26 archives passed `load_corpus` before observing these workflows. Tasks, literal
expectations and verifier nominations were selected from upstream diffs and test
assertions rather than Hashmarks output.

| Workflow | Pinned upstream change | Source evidence and verification basis |
| --- | --- | --- |
| aiokafka-commit-unknown-member | `deb9e06e1f459cde884fffc44f7c14a05c640ea0` | `_maybe_do_autocommit`; new UnknownMemberId retry assertion in coordinator tests |
| aiokafka-commit-timeout | `214297859ed224e2259ded617fef90d5931e343f` | `_do_commit_offsets` coordinator invalidation; existing commit-failure tests, no new dedicated test |
| aiokafka-commit-refresh-order | `d8941bece2c34be571942887db4320ccb945bd13` | `_commit_refresh_routine` event clearing changes physical position; existing refresh tests do not prove race coverage |
| aiokafka-join-autocommit-error | `19494402b63dc33eef04c8b3bc3882e07f780b1d` | `_on_join_prepare` commit and exception syntax; new expired-membership regression |
| aio-pika-processing-channel-close | `f0f5c1ee7387cc6210c693f635c847c98f27755b` | `ProcessContext.__aexit__`; closed-channel rejection and original-error identity tests |
| aio-pika-iterator-cleanup-timeout | `f4b9ab8055a7f74053f7ed69bb2b609f7486a3fc` | `QueueIterator.__aexit__`; new cleanup timeout and repeated-cancellation tests |
| aio-pika-iterator-nack-scope | `b722542bd7d4ef1d6613c675ce25cebbc1a92597` | `QueueIterator.close`; `multiple=True` becomes `False`, with two-subscription regression |
| aio-pika-iterator-channel-close | `ac382090e095a94e5b333b68c544901e3f03ccee` | `QueueIterator.__anext__`; message-or-closed wait and iterator integration tests |
| faststream-ack-cancellation | `b437a29e5b9707def86169f14dbab1493193b060` | `_AcknowledgementMiddleware.__aexit__`; explicit cancellation argument and new Kafka cancellation tests |
| faststream-batch-nack | `16417cce116e5578cd4fcd2e8d397461d87b7026` | `KafkaMessage.nack`; tuple-member offset expression and seek regression |
| faststream-ack-error | `8b8a82ee6f4ff911f4bf4d1cda5b7d87546fdc12` | `WatcherContext.__ack`; acknowledgement/exception syntax and existing pushback assertions |
| faststream-consumer-commit-failure | `380740d1c9a0c1a6e5deeb4d41310dd3a3b13f1e` | `AsyncConfluentConsumer.stop`; explicit `asynchronous=True` becomes `False`, with existing broker lifecycle tests |
| faststream-empty-batch-publisher | `146a16fc14fa1ccb5016a2ba741a3be6b802be38` | `BatchPublisher._publish`; nominated producer call and new empty-result publication assertions |

Full upstream URLs, before/after commits, source-range hashes, exact call lines
and review limitations are in `suite.json` and `grader.json`. The grader retains
new argument-syntax expectations before their implementation. Missing facts
must fail; no expectation is removed to obtain a passing acquisition.

These are explicit source/method and line nominations. They do not establish
answer-blind owner recall, test sufficiency, runtime callee binding, delivery or
retry outcomes, ordering, broker compatibility or cancellation ownership.
`source_labels` nominate native method targets; `task_source_labels` additionally
bind production files and stage-correct verifier sources. Newly added test files
are never expected at the before revision. Native capture observes only nominated
production members; imports do not admit dependency implementations.

The batch-nack before verifier was corrected after reviewing the pinned source.
`TestConsume.test_nack` in `tests/brokers/confluent/test_consume.py:201` awaits
`msg.nack()` and asserts commit was not called. The seek regression
`TestTestclient.test_message_nack_seek` at `test_test_client.py:32` exists only
after the change. Exact method ranges and hashes now bind both nominations in
`task_source_labels`; the original before test-client file remains as context.
This qualifies relevant existing test evidence, not batch correctness or test
sufficiency. Original failed acquisitions and the original grader are retained
under the verification-identity checkpoint. Native nominations are unchanged.

The cancellation before verifier was also corrected from generic shared consume
coverage to the existing Kafka acknowledgement-policy regression.
`TestAckPolicy.test_commit_called_in_middleware_on_error` (173–211) raises an
ordinary handler error under ACK/REJECT_ON_ERROR and asserts commit was awaited.
The after-only cancellation/redelivery test (18–62) remains required. Exact
method ranges and hashes bind both stages. The before test is relevant ordinary
error coverage, not evidence that cancellation was already covered; original
oracles and failed reports remain retained.

Capability membership is 13. The suite requires fresh native acquisition and
declares 2,286 exact boundary witness contexts across revisions, surfaces and
formats. Source binding, declaration, literal/argument facts and conservative
authority qualifiers have separate positive/adversarial roles. Capability proof
remains `reviewed: false`: complete independent capability/display review and
current public/native qualification are still required. A completed witness
table does not set the review flag or establish 5/5.

Source-only reserved holdouts are aiokafka `81a5f363d05e823242c476487690c0ca7f65862e`,
aio-pika `7e5adfba60f56ed6b4c473a6f01de6e578901844` and FastStream's codec wiring
change `f7ba76bff489fec92c74df2dd2f8b4d6e04eff18`. They are excluded from development
membership and have not been measured as these qualification tasks. Exact
holdout tasks, source admission and oracles still need separate completion.

Materialize with the existing QA command, supplying explicitly selected upstream
checkouts:

```sh
uv run --frozen --no-sync --group test python -m scripts.repository_evaluation.materialize_backend \
  --suite benchmarks/repository_evaluation/manifests/backend-campaign-v2/suites/messaging/suite.json \
  --repository aiokafka=/path/to/aiokafka \
  --repository aio-pika=/path/to/aio-pika \
  --repository faststream=/path/to/faststream \
  --output-dir .hashmarks/backend-e2e/messaging-sources
```

## Observer ownership note: direct call argument syntax

Observed repository fact/evidence: bounded positional/keyword argument syntax,
including boolean literals, identifiers and explicit argument expansion.
Authority source: the current admitted Python AST and exact source/index binding.
Completeness/freshness behavior: per-call omission counts and explicit unknown
expressions; existing member revision checks remain authoritative.
Existing Hashmarks owner extended: `function_boundary_syntax`.
Consumer/execution responsibility explicitly not acquired: argument binding,
callee execution, acknowledgement/retry decisions and broker delivery outcomes.
Decision: OBSERVER.

The argument observation keeps eight positional and eight keyword entries per
call, with explicit omitted counts and truncation. Literal strings are bounded
to 128 characters and integers to 256 bits. Exact integer values use decimal
text with `encoding: decimal-text`, preserving precision for JSON clients that
decode numeric values as binary64. Unknown expressions, mapping/positional
expansion and unsupported or oversized values never establish runtime binding.

Remaining capability review must cover the answer-bearing source conditions,
not merely the existence of each nominated call. In particular, commit timeout
classification, retry-error categories, event-clear/fetch source order, closed
channel guards, cancellation returns, tuple-member selection and watcher
removal under `else` need independent source/display assertions. The currently
passing literal and argument checks do not certify those conditions or their
runtime consequences. The initial owner/verifier checks also do not establish
complete initial evidence sufficiency. Keep `reviewed: false` until those
required facts and their witness membership are reviewed and executable.
