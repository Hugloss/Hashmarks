from __future__ import annotations

import argparse
import inspect
from typing import TYPE_CHECKING

import pytest

from hashmarks.cli import _add_common_arguments
from hashmarks.codemap import CodeMap
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient
from hashmarks.codemap.verification_defaults import (
    VERIFICATION_RELEVANCE_DEFAULTS,
    VerificationRelevanceOptions,
)
from hashmarks.repository_cli import add_repository_cli

if TYPE_CHECKING:
    from pathlib import Path


def test_verification_defaults_have_one_core_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    defaults = VERIFICATION_RELEVANCE_DEFAULTS
    for owner in (
        CodeMap.verification_relevance,
        CodeMap.verification_ownership_graph,
        CodeMapServiceClient.verification_relevance,
        CodeMapServiceClient.verification_ownership_graph,
    ):
        parameters = inspect.signature(owner).parameters
        assert parameters["limit"].default == defaults.limit
        assert parameters["candidate_limit"].default == defaults.candidate_limit

    private_parameters = inspect.signature(CodeMap._verification_relevance).parameters
    assert private_parameters["limit"].default == defaults.candidate_limit

    explanation = inspect.signature(CodeMap.explain_verification_selection).parameters
    assert explanation["limit"].default == defaults.limit
    assert explanation["candidate_limit"].default == 16

    captured: list[VerificationRelevanceOptions] = []

    class _Map:
        def verification_relevance(
            self,
            task: str,
            *,
            limit: int,
            candidate_limit: int,
        ) -> dict[str, object]:
            del task
            captured.append(
                VerificationRelevanceOptions(
                    limit=limit,
                    candidate_limit=candidate_limit,
                )
            )
            return {"schema": "hashmarks.verification-relevance.v1"}

        def verification_ownership_graph(
            self,
            task: str,
            *,
            limit: int,
            candidate_limit: int,
        ) -> dict[str, object]:
            del task
            captured.append(
                VerificationRelevanceOptions(
                    limit=limit,
                    candidate_limit=candidate_limit,
                )
            )
            return {"schema": "hashmarks.verification-ownership.v2"}

    service = CodeMapService(tmp_path, socket_path=tmp_path / "service.sock")
    monkeypatch.setattr(service, "_map", lambda: _Map())

    service._verification_relevance_response({"task": "inspect widget"})
    service._verification_ownership_response({"task": "inspect widget"})

    assert captured == [defaults, defaults]


def test_verification_cli_defaults_consume_core_authority() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_repository_cli(sub, add_common_arguments=_add_common_arguments)

    relevance = parser.parse_args(["verification-relevance", "inspect widget"])
    assert relevance.limit == VERIFICATION_RELEVANCE_DEFAULTS.limit
    assert relevance.candidate_limit == VERIFICATION_RELEVANCE_DEFAULTS.candidate_limit

    ownership = parser.parse_args(["map", "verification-ownership", "inspect widget"])
    assert ownership.limit == VERIFICATION_RELEVANCE_DEFAULTS.limit
    assert ownership.candidate_limit == VERIFICATION_RELEVANCE_DEFAULTS.candidate_limit
