# Genuine dependency-injection and configuration source intake

`source-catalog.json` records twelve pinned changes across FastAPI, Litestar and
FastStream, with four changes per repository and twenty-four exact Git trees.
The source population covers dependency traversal/bookkeeping, provider
classification and cleanup, declared dependency markers, context composition,
provider defaults and dependency-constructor adaptation.

This is **INCOMPLETE source intake**, outside active campaign membership. All
semantic/capability review flags remain false. Candidate owner and test paths
are nominations, not independently established causal ownership, relevant-test
authority or sufficient verification. The performance changes do not assert
reproduced runtime failures. Distinct commit identities are recorded; independent
problem-distinctness review remains required.

The source records bind exact commits, complete archive content identities,
archive SHA-256 and nominated file byte hashes. A path marked absent is absent
from that exact source tree; this does not establish semantic absence. Three
nominated test files and one owner file exist only after their changes.
Before-test relevance must be reviewed separately rather than copying those
later paths into an oracle.

For local development, the extracted trees, tar archives and `sources.json` are
retained under `.hashmarks/canonical-component-rewrite/cr19-configuration-source-intake/`.
To reproduce a source, use the caller-selected repository checkout and its
catalog commit with `git archive COMMIT`, extract using a data-only tar filter,
and verify `hashmarks.test_shards.repository_content_identity` against the catalog.
Verify archive and selected-file hashes as well. Source extraction does not run
the target repository, its broker or its tests.

`suite.json` and `grader.json` now admit eight selected workflows over all three
repositories: default-provider initializer references, dependency-parameter
traversal calls, bound-method classification, stateful callable arguments,
body-field construction arguments, repeat-bookkeeping calls, callable-cache
wrapping and generator-provider classification.
Their before/after oracles were written from exact AST/source hashes before
observer acquisition. Runtime binding and callee resolution remain explicitly
unknown. The default-provider source omission is reproduced on the original
observer. `call-source-oracles.json` records the four added call slices, exact
declarations and argument syntax. These slices do not establish the surrounding
guard behavior, runtime performance or causal test relevance. The other four
workflows, broader causal provider semantics,
adversaries and capability proof remain unreviewed; every capability flag is false.

The existing materializer and backend runner accept this suite. Use the three
caller-selected checkouts with
`scripts.repository_evaluation.materialize_backend --suite .../suite.json`, then
pass its `sources.json` to `scripts.repository_evaluation.run_backend --suite
.../suite.json`. The generic materializer verifies all twenty-four source trees;
the runner currently observes eight workflows and reports missing qualification.

Next, inspect the other source changes and their existing tests, write independent
declaration/wiring facts with exact ranges and revisions, and freeze answer-blind
tasks, unknowns, eligibility and adversaries. Configuration/provider syntax must
not become runtime configuration or compatibility authority. Extend the existing
suite and grader only after source review; source counts do not close gates.

The three reserved entries are metadata nominations only. No reserved tree is
extracted by this intake, and source exposure has not been audited. They do not
establish unseen holdout independence. Perform contamination and independent
oracle review before admitting them as final holdouts; replacements may be
required.
