# Hashmarks ↔ Oh-Goon integration contract

**Status: current normative integration guidance.** Superseded integration notes are recoverable from Git history and are not product authority.

## Three-plane model

Hashmarks and Oh-Goon are complementary systems with different authority.

```text
Repository state
      │
      ▼
  Hashmarks
repository-evidence plane
      │
      ├──────────────► Agent / human
      │                  solution plane
      │
      └──────────────► Oh-Goon
                         execution/certification plane
```

- **Hashmarks** answers what repository evidence says matters: identity, topology, ownership, impact, freshness, verification relevance, and provenance.
- **The agent/human** decides what change to make and owns its reasoning, hypotheses, attempt history, and solution behavior.
- **Oh-Goon** decides whether work is admitted, how it runs, how processes/environments are controlled, and whether execution evidence is certifiable.

**Interoperability transfers evidence, never authority.**

## Hashmarks owns

- canonical repository/input/content identities;
- repository observation and freshness evidence;
- CodeMap and repository-derived ownership/impact evidence;
- deterministic repository-work/test membership selection;
- verification relevance and repository-bound verification descriptions;
- producer identity, provenance, evidence contexts, and consumer-conformance validation;
- evidence economics and qualification of Hashmarks-owned semantics.

## Oh-Goon owns

- admission and policy enforcement;
- work scheduling and placement;
- sandbox/workspace/runtime-environment authority;
- process launch and process-tree supervision;
- timeout, cancellation, retry, resume, and recovery policy;
- network/egress/resource policy;
- execution-result authority;
- certification and release promotion;
- Game Tape and execution-history ownership.

Hashmarks must never become Oh-Goon's execution motor. Oh-Goon must not create a second competing implementation of Hashmarks repository identity/intelligence.

## Agent responsibilities remain external

Hashmarks may expose repository ambiguity, alternative candidates, likely repair surfaces, and verification relevance. It does not own:

- solution reasoning or patch design;
- edit execution;
- attempt/failed-edit memory;
- delegation/scout/sub-agent choices;
- model routing or prompt/context strategy;
- interpretation of verification outcomes as a recovery strategy.

The agent can query Hashmarks again after repository bytes change, but its own workflow history does not become repository authority.

## Repository-work selection handoff

Hashmarks may emit deterministic work/test membership evidence such as `hashmarks.test-shards.v3` and a repository-bound `hashmarks.repository-work-selection.v1` envelope.

An execution system should:

1. validate the Hashmarks producer/schema/identity contract;
2. bind repository-selection evidence to the source/repository it admitted;
3. preserve required isolation semantics such as `isolated_process`;
4. reject stale or mismatched evidence;
5. execute the selected membership under its own policies.

Oh-Goon may refine runtime grouping after a timeout only if membership is conserved exactly. Hashmarks may provide a membership identity/proof; it does not choose timeout budgets, retry policies, worker counts, schedules, machines, or refinement strategy.

## Verification handoff

Hashmarks can identify repository-derived verification relevance and mechanically describe verification surfaces. The presence of a verification description is **not** proof that verification ran or passed.

Oh-Goon/external runners own:

- whether a verification command is admitted;
- where and how it executes;
- actual exit code/output provenance;
- PASS/FAIL/result authority;
- recovery after failure.

## Freshness handoff

Consumers should treat Hashmarks freshness/provenance as a repository-evidence contract:

- `proven` means the required repository evidence is positively current under the relevant observation authority;
- `stale` means a relevant change invalidated it;
- `unknown` means currentness cannot be proven.

A consumer must not convert `unknown` to fresh based on recency or convenience.

## Trust and producer policy

Repository-controlled declarations are claims unless the consumer's policy explicitly trusts the producer/source. Hashmarks can validate the structure and identity of evidence; the execution/certification layer decides which producers and evidence classes are trusted for admission or reuse.

## Dependency strategy

Keep Hashmarks standalone. Oh-Goon should consume a pinned Hashmarks package/version through a thin adapter rather than copying Hashmarks internals into the Oh-Goon tree.

Record the resolved Hashmarks version and relevant evidence/contract identities in execution provenance so later certification can reproduce the exact decision inputs.

## CodeMap integration

CodeMap is optional derived intelligence. A typical local topology is:

```text
Hashmarks identity/observation  -> canonical repository identity/freshness
Hashmarks CodeMap service      -> derived repository intelligence
Agent                           -> reasoning and edits
Oh-Goon                         -> admission/execution/certification
```

A CodeMap service/watch process may be managed as infrastructure, but its failure must not silently weaken execution/certification policy. Consumers should reconcile or fall back when freshness is insufficient.

## Pre-public boundary history

Execution-shaped and agent-loop responsibilities are outside the current public contract. Git history preserves earlier experiments; they are not an integration compatibility surface and must not be treated as architectural precedent.

## Normative references

- [`../reference/PRODUCT_BOUNDARY.md`](../reference/PRODUCT_BOUNDARY.md)
- [`../reference/ARCHITECTURE.md`](../reference/ARCHITECTURE.md)
- [`../reference/INVARIANTS.md`](../reference/INVARIANTS.md)
