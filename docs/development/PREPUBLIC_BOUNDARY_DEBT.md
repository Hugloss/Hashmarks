# Historical boundary-debt removal record

Status: **pre-public cleanup record**. This document explains runtime-shaped surfaces that existed during Hashmarks development and the disposition applied before the first public release. It is not a compatibility promise.

## Public-release decision

Hashmarks does not owe backward compatibility for unpublished development APIs. Historical surfaces whose authority belongs to an agent/consumer or execution system are therefore removed from the installed public contract rather than deprecated into the first release.

The governing rule is [`PRODUCT_BOUNDARY.md`](../reference/PRODUCT_BOUNDARY.md): Hashmarks owns repository intelligence and repository-derived evidence. It does not own the consumer solution loop or an Oh-Goon-style execution/certification motor.

## Execution-shaped development surfaces

The following historical concepts were removed from the first public runtime/API surface:

- historical execution/work identity that bound argv, process environment, executable/runtime identity, or working-directory execution semantics;
- `ActionResult`, `ActionCache`, and `ExecutionCache` result-reuse models;
- generic work-unit/process execution helpers and execution-result promotion semantics;
- installed CLI commands whose purpose was to launch arbitrary benchmark/work processes rather than derive repository evidence.

Content-addressed storage remains valid **internally where it stores repository-derived artifacts**. Removing execution-result cache semantics does not prohibit content-addressed parse/evidence reuse.

## Agent-loop development surfaces

The following historical concepts were also removed from the first public runtime/API surface:

- failed-edit / failed-attempt memory as Hashmarks state;
- `AgentWorkSession` attempt/recovery state;
- recovery classification and retry/delegation policy;
- negative-evidence receipts whose authority came from a consumer assertion that an attempted edit failed;
- scout/sub-agent admission policy;
- verification execution owned by a Hashmarks session/workflow object.

Useful repository primitives remain: ownership, candidate alternatives, ambiguity/discrimination evidence, freshness, change impact, verification relevance, provenance, and bounded task evidence.

## Measurement infrastructure

Agent/worker experiments may remain in the source repository under development/evaluation tooling such as `scripts/agent_evaluation/`. Those harnesses measure how external consumers use Hashmarks; they do not become installed product APIs or product authority.

A successful end-to-end agent benchmark does not authorize moving the benchmark's workflow into Hashmarks.

## Compatibility rule for the first public release

There is intentionally **no compatibility shim** for the removed unpublished surfaces. New integrations must target the documented current API/CLI. Historical names, benchmark fixtures, archived release notes, or old source patches are evidence of development history only and cannot be cited as public contract precedent.

## IdentityEngine clarification

`hashmarks.engine.IdentityEngine` remains part of Hashmarks because the public contract narrows it to canonical repository-content identity: manifests, file/directory digests, Merkle roots, snapshots, and observation/freshness. It no longer composes execution-result caching or process/work authority. Historical references that grouped `IdentityEngine` with execution compatibility describe an older development shape, not the current public contract.
