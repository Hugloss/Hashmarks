from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from scripts.agent_evaluation.repository_quality_authority import (
    PRESENTATION_ONLY_FAMILIES,
)


@dataclass(frozen=True)
class MutationChallenge:
    name: str
    expected_relation: str
    mutation: Callable[[dict[str, Any]], dict[str, Any]]


def _set(path: str, value: object) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def mutate(payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        result[path] = value
        return result

    return mutate


DEFAULT_CHALLENGES = (
    MutationChallenge("retrieval-limit", "invariant", _set("limit", 1)),
    MutationChallenge("pagination", "invariant", _set("page", 2)),
    MutationChallenge("candidate-order", "invariant", _set("reverse_candidates", True)),
    MutationChallenge("compact-full", "invariant", _set("compact", True)),
    MutationChallenge(
        "irrelevant-file-addition", "invariant", _set("irrelevant_file", True)
    ),
    MutationChallenge(
        "generation-mutation", "change", _set("owner_generation_mutation", True)
    ),
)


def run_mutation_challenges(
    baseline_input: Mapping[str, Any],
    *,
    evaluate: Callable[[Mapping[str, Any]], str],
    challenges: Sequence[MutationChallenge] = DEFAULT_CHALLENGES,
) -> list[dict[str, Any]]:
    baseline_payload = dict(baseline_input)
    baseline_identity = evaluate(baseline_payload)
    if not baseline_identity:
        raise ValueError("baseline evaluation must return an authority proof identity")
    results: list[dict[str, Any]] = []
    for challenge in challenges:
        mutated = challenge.mutation(dict(baseline_payload))
        candidate_identity = evaluate(mutated)
        if not candidate_identity:
            raise ValueError(f"{challenge.name} returned no authority proof identity")
        changed = baseline_identity != candidate_identity
        violation = (challenge.expected_relation == "invariant" and changed) or (
            challenge.expected_relation == "change" and not changed
        )
        results.append(
            {
                "family": challenge.name,
                "baseline_authority_proof_identity": baseline_identity,
                "candidate_authority_proof_identity": candidate_identity,
                "expected_relation": challenge.expected_relation,
                "proof_changed": changed,
                "violation": violation,
                "presentation_only": challenge.name in PRESENTATION_ONLY_FAMILIES,
            }
        )
    return results



def repository_counterfactual_challenges() -> tuple[MutationChallenge, ...]:
    return (
        MutationChallenge(
            "irrelevant-file-addition",
            "invariant",
            _set("repository_mutation", "add-unreferenced-file"),
        ),
        MutationChallenge(
            "generation-mutation",
            "change",
            _set("repository_mutation", "replace-owner-definition"),
        ),
        MutationChallenge(
            "generation-mutation",
            "change",
            _set("repository_mutation", "duplicate-exact-owner"),
        ),
        MutationChallenge(
            "generation-mutation",
            "change",
            _set("repository_mutation", "remove-decisive-evidence"),
        ),
    )


def mutation_coverage(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    families = sorted({str(row.get("family") or "") for row in results})
    violations = [row for row in results if row.get("violation") is True]
    return {
        "cases": len(results),
        "families": families,
        "violations": len(violations),
        "clean": bool(results) and not violations,
    }
