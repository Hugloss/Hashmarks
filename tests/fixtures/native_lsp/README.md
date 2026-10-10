# Genuine language-server capture corpus

`python` records Pyright 1.1.414. `typescript` records TypeScript Language
Server 5.3.0 with TypeScript 5.9.3. These are capture provenance, not a required
version matrix. The offline tests launch no language server and need no network.

Each state retains untouched JSON-RPC requests/responses in `captures.json`,
the protocol transcript, configuration, tool version, snapshot text, document
versions/lifetimes, disk revisions, and SHA-256 hashes in `capture.json`.
`requests.json` defines the finite capture experiment independently of Hashmarks.
The external capture caller claims collection completeness; it does not certify
the server or make absence admissible. Call hierarchy requests reuse the exact
prepared item, including producer data when present.

Python exercises cross-file definition, references with and without declarations,
prepare/incoming/outgoing calls, duplicate symbol names, file movement, disk
changes, and an unsaved buffer followed by close/reopen. A definition request at a
call inside `caller` points to `target`: the supplied `caller` label must remain
unresolved even though its document bytes match. Matching file bytes alone do
not prove the query symbol. Call ranges belong to the caller document; Pyright
may give a prepared item's range that covers only its declaration name.

TypeScript uses the same sources as the genuine SCIP fixtures. Its methods are
native-only targets and must stay unavailable to lexical edit lookup. Tests
combine actual captures from both producers without filling in SCIP's omitted
position encoding. Such endpoints remain unresolved rather than manufacturing
positive correspondence. External runtime-library call locations are retained
as external evidence; the corpus does not analyze library implementations.

Replay rebases only exact fixture-owned file URIs to the admitted test directory.
The raw files and hashes stay unchanged. Tests undo that rebase and compare all
other fields exactly. Materialization removes previous fixture-owned files,
including renamed/deleted members, while preserving unrelated repository inputs.
CLI checks launch the executable entry point. MCP checks use the official SDK
stdio transport with actual handlers. Presentation tests assert semantic facts,
exact selected source references, and explicit omissions across all formats.

Run `make semantic-evidence-dogfood` for offline validation. For an explicit live
capture, supply the installed servers and TypeScript runtime:

```sh
export PATH="/path/to/qa-tools/bin:$PATH"
export HASHMARKS_QA_TSSERVER=/path/to/typescript/lib/tsserver.js
python -m scripts.native_evidence_capture lsp-python \
  tests/fixtures/native_lsp/python/before /tmp/hashmarks-pyright-capture
python -m scripts.native_evidence_capture lsp-typescript \
  tests/fixtures/native_lsp/typescript/before /tmp/hashmarks-ts-capture
```

`make semantic-evidence-live` also needs `scip-python`, `scip-typescript`, `scip`,
`uv`, and `mvn` on PATH. It regenerates the bounded corpus in temporary directories,
fails on missing tools, and never substitutes committed captures or rewrites the
root development lock. This QA-only client is never imported by product code.
