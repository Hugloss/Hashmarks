# Repository quality qualification

Hashmarks repository-quality qualification is development measurement infrastructure. It evaluates frozen repository-intelligence behavior; it does not grant edit, execution, or release authority to an agent.

## Ordering

Quality is compared lexicographically:

1. benchmark integrity and ground-truth authority;
2. zero false authority;
3. evidence sufficiency and overclaim correctness;
4. abstention correctness;
5. useful resolution coverage;
6. projection, generation, and provenance fidelity;
7. retrieval, verification, and evidence quality;
8. metamorphic and semantic stability;
9. economics.

A lower level never compensates for failure at a higher level.

## Five-question QA for declarations and relationships

These prompts apply portable finding derivation to Hashmarks' producer boundary.
Use the questions relevant to the suspected failure; they are guidance, not
required report fields, a new scorer, corpus definition or CI/release gate.

1. **What implementation and evidence were inspected?** Identify the exact
   Hashmarks revision or loaded implementation, public API, selected source and
   packet/generation where relevant. Inspect the applicable producer contract
   and consumer path. Distinguish executed reproductions from static evidence
   and unrun tests; structural inspection can prove an explicit structure or
   absence contract without a runtime reproducer.
2. **What does the result actually claim?** Separate authored Python/uv/Make/
   shell declarations from *effective* native uv, Make or shell execution;
   distinguish static source/dependency relationships from runtime call truth.
   Preserve producer identity, evidence scope, freshness, value state,
   JSON scalar types, ambiguity, correspondence, completeness, truncation and
   negative-evidence limits. Similar hashes do not prove shared semantics.
3. **Where does an actual contract fail?** Trace the producer output or public
   adapter through the accepting decision and its consequence. Exact indexed
   projection of qualified relationships is legitimate; inventing omitted
   edges, repairing unknown scope locally, or treating nominations as execution
   authority is not. A false known result, missing promised capability or
   weakened qualifications can be a defect without two competing accepted
   producers. A proposed capability beyond the current contract is a proposal,
   not an existing defect. Hashmarks supplies repository evidence; external
   owners retain reasoning, admission, process work and results.
4. **What could disprove the suspicion?** Inspect the nearest relevant safe
   control, existing regression or native-tool guarantee. A qualified bounded
   relationship, unresolved declaration or Git execution witness may be correct.
   Test the suspected distinction; do not require every uncertainty scenario or
   infer fragility from a parser, repeated helper or grep hit alone.
5. **What verdict and repair are justified?** Report a `FINDING` only when
   the producer or consumer actually violates its contract with a material
   consequence. Otherwise `LEAVE ALONE` or mark missing proof
   `INSUFFICIENT EVIDENCE`; a `CLEAN` claim is limited to the completed
   inspected scope. Repair the responsible owner, preserving unknown states,
   and add the smallest regression that supplies missing detection power.
   Reuse an existing safe control where it already proves the distinction.
   Do not transfer Git/worktree execution or certification authority into Hashmarks.

The current contracts provide concrete review cases:

- [Dependency/verifier composition](../reference/DEPENDENCY_EVIDENCE.md#composed-dependency-and-verifier-evidence)
  retains native packets, exact chain indices and qualifications; consumers need
  not rebuild its relationships. Its public validator and the native delta
  validator check typed self-consistency/correspondence, not authenticity or live
  freshness. For example, rehashing a packet must not make JSON `true` substitute
  for integer `1`; the [existing regression](https://github.com/Hugloss/Hashmarks/blob/main/tests/test_dependency_verification.py)
  covers that distinction. Fresh source qualification uses the observer owner.
- [Make/shell](../reference/MAKE_SHELL_EVIDENCE.md) and
  [npm declarations](../reference/REPOSITORY_DECLARATIONS.md#selected-npm-manifest-declarations)
  describe selected authored sources. Unsupported native expansion, hooks,
  environment and resolution remain unestablished. Source/read bounds must
  refuse or preserve incomplete scope, never return partial bytes as a complete
  observation or upgrade a bounded result to absence.

These prompts do not replace the repository-quality ordering above or consumer
qualification. AgentsCookbook owns portable finding derivation; EvalShot owns
model-backed skill evaluation. Documentation and static checks alone do not
establish improved agent accuracy.

## Ground truth and corpus readiness

A case separates repository semantic truth from the evidence admitted to Hashmarks. A unique owner with insufficient admitted evidence is expected to remain unresolved; that is not a missed-resolution defect.

Missing measurements are unknown, never zero. Score-bearing cases must have valid ground truth, stable case identity, and explicit corpus membership. Shadow, canary, fresh-dogfood, historical, and superseded cases may remain diagnostic evidence but must not silently change the active qualification corpus.

Qualification requires representative active coverage of critical semantic slices such as unique ownership, true ambiguity, non-edit outcomes, and verification ownership. An empty, invalid, or materially incomplete corpus is not qualification evidence.

## Hard authority vetoes

False authority is non-compensatory. A qualification run fails its repository-intelligence contract when it produces false unique ownership, false safe-edit conclusions, invalid verification authority, provenance/identity mismatch, command/selection membership drift, or another result that claims stronger authority than the admitted evidence proves.

Ranking, latency, token economy, or aggregate quality cannot compensate for an authority violation.

## Positive quality evidence

After hard authority gates pass, qualification may report useful-resolution coverage, abstention quality, ranking metrics, evidence retention, generation/freshness stability, projection fidelity, and metamorphic behavior.

These metrics describe product quality; they are not permissions. Ranking quality never grants ownership or verification authority, and absence of a measurement remains unknown rather than zero.

## Stability and economics

Semantic stability should be exercised across equivalent wording, bounded retrieval limits, batching, cache/rebuild boundaries, generation changes, and consumer projections where those dimensions are relevant.

Economics are evaluated last. Record enough environment and mode information to distinguish cold, warm, and incremental observations. Runtime alone is never a correctness gate, and performance work must preserve repository meaning, freshness, ambiguity, provenance, and authority.

This infrastructure remains separate from Hashmarks runtime authority. Future qualification changes belong in reviewed code/tests and the pull request that introduces them rather than in a standing historical roadmap.
