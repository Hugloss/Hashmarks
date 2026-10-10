# Native SCIP change corpus

These fixtures retain genuine binary indexes and untouched JSON decoded by
`scip print --json`. The initial captures use `scip-python` 0.6.6,
`scip-typescript` 0.4.0, and `scip` 0.10.0. Each `capture.json` records the
actual producer version, arguments, configuration, binary/JSON SHA-256 hashes,
and canonical source revisions. `provenance.json` supplies the corresponding
caller claim of a fresh complete collection. It does not certify the indexer
or assert unsupported relationship capabilities.

Python states exercise source movement and a function-body change. This
producer emitted zero direct relationships for the fixture; tests preserve
that fact without treating it as repository absence. TypeScript states move,
remove, and restore an explicit class implementation. The producer emits an
implementation claim for the class and reference/implementation flags for its
method. Tests preserve the original direction and do not manufacture calls,
inverse relationships, or transitive edges. `ambiguous` contains two classes
with the same method name and proves that exact native subject lookup does not
choose between them.

Python `metadata-before` and `metadata-after` change Unicode documentation while
retaining two reads of the same parameter at different columns on one line.
`metadata-bounded` contains 130 actual producer-reported reads on one line to
exercise bounded retention. Its `fmt: off` region keeps that deliberate source
shape intact through repository formatting; all captured hashes and revisions
still bind the exact producer inputs. These captures exercise reference roles,
source binding, documentation changes, and durable reopening without mocking
producer output or Hashmarks publication.

Tests materialize only `src` and project configuration inside the observed
repository. Captures stay outside it. They replace source files, import native
bytes through CodeMap, edit before reindexing, delete files, reopen durable
state, and compare fresh reconstruction. Presentation checks dereference every
selected JSON pointer and account for omitted rows. CLI tests launch the real
entry point; MCP tests call the official SDK without replacing handlers.

Run the offline ring with `make semantic-evidence-dogfood`. To qualify installed
producers, put `scip-python`, `scip-typescript`, `scip`, `uv`, and `mvn` on PATH
and run `make semantic-evidence-live`. That ring captures into temporary
directories and fails if a required producer or source document is missing.
No committed capture is used as fallback. It does not rewrite these fixtures.

For deliberate capture authoring, use a new destination outside the repository:

```sh
python -m scripts.native_evidence_capture typescript \
  tests/fixtures/native_scip/typescript/before \
  /tmp/hashmarks-scip-before
```

Review the source, decoded claims, hashes, and recorded tooling before replacing
committed capture files. Producer tooling and execution belong to development
qualification, not Hashmarks' installed observation surfaces.
