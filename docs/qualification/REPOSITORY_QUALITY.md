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

Use these questions when an agent claims a repository-intelligence defect,
especially with limited reasoning or context. This is source-review guidance,
not a new scorer, corpus definition or CI/release gate.

1. **Which producer result exists?** Identify the exact Hashmarks revision,
   public API, declaration/relationship packet, selected member and observed
   generation. Inspect the producer implementation and existing contracts,
   not only a consumer snippet or the presence of a parser.
2. **What does the result actually claim?** Separate authored Python/uv/Make/
   shell declarations from *effective* native uv, Make or shell execution;
   distinguish static source/dependency relationships from runtime call truth.
   Preserve producer identity, evidence scope, freshness, value state,
   ambiguity, correspondence, completeness, truncation and negative-evidence
   limits. Similar hashes across consumers do not prove shared semantics.
3. **Where would a consumer misuse it?** Trace producer -> public adapter ->
   downstream decision. Ask whether a consumer treats an incomplete source
   observation as repository-wide absence, a producer relationship as its own
   reconstructed graph, or a verification nomination as execution authority.
   Hashmarks supplies repository facts; Oh-Goon or the harness owns admission,
   process work and results.
4. **What is the safe neighboring case?** Check a valid refined declaration,
   unresolved/ambiguous value, unavailable source, stale observation, a
   bounded relationship and a legitimate native-tool execution witness.
   Existing validation, typed projections and upstream format guarantees may
   refute a claimed defect. A grep hit or repeated syntax is not a reproducer.
5. **What verdict and repair are justified?** Report a `FINDING` only when
   the producer or consumer actually violates its contract with a material
   consequence. Otherwise `LEAVE ALONE` or mark missing proof
   `INSUFFICIENT EVIDENCE`; a `CLEAN` claim is limited to the completed
   inspected scope. Repair the responsible owner, preserving unknown states,
   with one focused positive and safe-control regression. Do not transfer
   Git/worktree execution or certification authority into Hashmarks.

This complements, but does not replace, the existing repository-quality
measurement ordering below and the consumer's own qualification. AgentsCookbook
owns portable finding derivation; EvalShot owns model-backed skill evaluation.
A text instruction or a passing source scan does not prove a weak-thinking
agent will distinguish these cases reliably.

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
