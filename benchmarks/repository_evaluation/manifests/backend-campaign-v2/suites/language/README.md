# Language and framework source catalog

This catalog contains twelve distinct upstream problems: six Python and six
TypeScript problems across aiokafka, FastStream, SQLAlchemy, Fastify, Hono and
Nest. The six Python problems retain their original source revisions and task
oracles. Their reuse adds no distinct global problems. The six TypeScript
problems add twelve exact Git archives to the campaign.

This is source intake, not 5/5 qualification. All capability-19 review flags
remain false. Independent language-contract review, executable language-parity
observations, complete positive/adversarial witness membership, display review,
fresh public/native acquisition, heldouts and final qualification remain open.
Existing source/native checks cannot substitute for those missing proofs.

The TypeScript declarations were independently located with the installed
TypeScript 5.9.3 parser before running Hashmarks on these cases. The version is
acquisition provenance. Line ranges and hashes in `grader.json` bind the actual
source bytes. Fastify's cases concern declarations in `.d.ts` files; their
runtime implementations are JavaScript. These cases do not establish runtime
hook behavior, HTTP compatibility, thenable scheduling or request validation.

| Problem | Pinned upstream change | Relevant declarations and tests |
| --- | --- | --- |
| Fastify shorthand-hook `this` | [`09b4a17`](https://github.com/fastify/fastify/commit/09b4a17a12a67407a4131d48c26a0dc309c55ecf) | `types/route.d.ts::RouteShorthandHook`; `test/types/route.tst.ts` |
| Fastify explicit HTTP/2 false | [`0f54a40`](https://github.com/fastify/fastify/commit/0f54a40f63b399bfe06a3deeab832f8b5feb6345) | `fastify.FastifyHttpOptions` and `FastifyHttpsOptions`; `test/types/fastify.tst.ts` |
| Hono short-circuit response | [`afb2068`](https://github.com/honojs/hono/commit/afb2068c1c53a530528ac5f237e245793dd03c07) | `src/middleware/combine/index.ts::some`; sibling `index.test.ts` |
| Hono cached-body media type | [`edd138e`](https://github.com/honojs/hono/commit/edd138ee3049749190de3dcd7e32d7bcbf224e41) | `src/request.ts::HonoRequest.#cachedBody`, a private arrow-function property; `src/request.test.ts` |
| Nest async parameter value | [`8f9fbfd`](https://github.com/nestjs/nest/commit/8f9fbfd76ffc86139ea423f858d09bc382c12497) | `PipesConsumer.applyPipes`; `packages/core/test/pipes/pipes-consumer.spec.ts` |
| Nest redirect reply | [`52509a5`](https://github.com/nestjs/nest/commit/52509a55a929189ddb2e620bfa27054a784df3c1) | `RouterResponseController.redirect`; unit test and newly added `integration/hello-world/e2e/fastify-redirect.spec.ts` |

Before-revision test labels name existing related checks. The new regression
assertions belong only to the after revision. In particular, the old hook test
does not assert restored `this`, the old Hono caching tests do not prove the new
media-type sequence, and the old Nest tests do not prove promise settlement.
Source correspondence does not establish that an upstream test was executed.

The Python problems are commit timeout, commit refresh ordering, acknowledgement
cancellation, batch nack, logging-token reset and aggregate-string compilation.
Their original workflow checks and source/native nominations remain intact;
capability-19 semantic review is separate from those earlier capability roles.

All twelve workflows now have explicit native fact oracles. Four Python entries
previously had source/native binding checks without executable per-target fact
witnesses. Their eight before/after native targets now have exact independently
source-frozen path, declaration token/line and current-member binding checks,
plus a no-negative-evidence authority check. Native nominations, tasks, corpus
membership and review flags are unchanged. This strengthens capture qualification;
it does not complete language-parity review or qualify capability 18.

Reserve these three additional problems for final heldout use. Their source
bodies and expected regression assertions were not inspected during intake:

- Fastify custom-logger assignability:
  `6ed472b6fe023cd0e6283badda231b84e45582d0`.
- Hono malformed pretty-JSON response:
  `f950277cd3d9264622785e82785f21c648da699a`.
- Nest middleware rejection forwarding:
  `1435ed22f4ce494cf9f95f6601fc8ab1310bf42c`.

If a heldout exposes a repair, retain that result and reserve an unseen
replacement before claiming independent heldout closure. The Python populations
also need the corresponding previously reserved/unseen backend holdout proof.

Use the existing source materializer with local checkouts containing every
recorded commit:

```sh
uv run --frozen python -m scripts.repository_evaluation.materialize_backend \
  --suite benchmarks/repository_evaluation/manifests/backend-campaign-v2/suites/language/suite.json \
  --repository aiokafka=.hashmarks/backend-e2e/upstream/aiokafka \
  --repository faststream=.hashmarks/backend-e2e/upstream/faststream \
  --repository sqlalchemy=.hashmarks/backend-e2e/upstream/sqlalchemy \
  --repository fastify=.hashmarks/backend-e2e/upstream/fastify \
  --repository hono=.hashmarks/backend-e2e/upstream/hono \
  --repository nest=.hashmarks/backend-e2e/upstream/nest \
  --output-dir .hashmarks/backend-e2e/language-sources
```

The initial local source map is
`.hashmarks/backend-e2e/explicit-retrieval-20261016/language-intake/language-sources.json`.
It admits all twelve workflows and twenty-four source trees. Use
`run_backend --suite .../language/suite.json --sources-file ... --output-dir NEW`
for public observation and `run_backend_native` with `--regenerate`, a new
capture root and a new report directory for fresh native proof. Batches may
select named workflows; account for missing membership in aggregation. Keep
source/evaluator bytes frozen during acquisition. The initial TypeScript
population has not yet been measured through Hashmarks.
