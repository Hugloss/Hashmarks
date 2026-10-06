from __future__ import annotations

import argparse
import inspect
from typing import TYPE_CHECKING

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient
from hashmarks.codemap.verification_defaults import (
    VERIFICATION_RELEVANCE_DEFAULT_OPTIONS,
    VerificationRelevanceOptions,
)
from hashmarks.repository_cli import add_repository_cli

if TYPE_CHECKING:
    from pathlib import Path


def test_verification_relevance_defaults_have_one_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    defaults = VERIFICATION_RELEVANCE_DEFAULT_OPTIONS

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

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_repository_cli(
        sub,
        add_common_arguments=lambda _parser, *, inherited=False: None,
    )
    relevance = parser.parse_args(["verification-relevance", "inspect widget"])
    ownership = parser.parse_args(["map", "verification-ownership", "inspect widget"])
    for args in (relevance, ownership):
        assert args.limit == defaults.limit
        assert args.candidate_limit == defaults.candidate_limit

    captured: list[tuple[str, VerificationRelevanceOptions]] = []

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
                (
                    "relevance",
                    VerificationRelevanceOptions(
                        limit=limit,
                        candidate_limit=candidate_limit,
                    ),
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
                (
                    "ownership",
                    VerificationRelevanceOptions(
                        limit=limit,
                        candidate_limit=candidate_limit,
                    ),
                )
            )
            return {"schema": "hashmarks.verification-ownership.v2"}

    service = CodeMapService(tmp_path, socket_path=tmp_path / "service.sock")
    monkeypatch.setattr(service, "_map", lambda: _Map())

    service._verification_relevance_response({"task": "inspect widget"})
    service._verification_ownership_response({"task": "inspect widget"})

    assert captured == [
        ("relevance", defaults),
        ("ownership", defaults),
    ]
