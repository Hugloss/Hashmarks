"""B30-B34: explicit source-read guidance is bounded, optional and untrusted."""

from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.backend_evidence_navigation import (
    MAX_BACKEND_NAVIGATION_READS,
)
from hashmarks.codemap.repository_declaration_provider import (
    RepositoryDeclarationProviderError,
)
from hashmarks.codemap.static_python_backend_declarations import (
    StaticPythonBackendDeclarations,
)
from hashmarks.evidence_presentation import present_repository_evidence
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation

PATH = "backend.py"


def _observe(repo: Path, *, guidance: bool) -> dict:
    with CodeMap(repo) as codemap:
        codemap.sync()
        return codemap.discover_repository_declarations(
            [
                StaticPythonBackendDeclarations(
                    paths=(PATH,),
                    include_evidence_navigation=guidance,
                )
            ]
        )


def _values(packet: dict, kind: str) -> list[dict]:
    return [
        group["declarations"][0]["value"]
        for group in packet["declarations"]["groups"]
        if group["concept"]["kind"] == kind
    ]


def _write(repo: Path, source: str) -> None:
    (repo / PATH).write_text(source, encoding="utf-8")


def test_model_read_guidance_is_source_bound_and_does_not_claim_runtime(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "from pydantic import BaseSettings, Field\n"
        "class Settings(BaseSettings):\n"
        "    raw: str\n"
        "    source: str = os.getenv('REGION')\n"
        "    computed: str = Field(default_factory=load_secret)\n"
        "    constant: int = 3\n",
    )
    packet = _observe(tmp_path, guidance=True)
    model = _values(packet, "python-model-class-syntax")[0]
    guide = model["evidence_navigation"]
    assert guide["state"] == "bounded-source-syntax-read-guidance"
    assert guide["authority"] == "existing-selected-source-declaration"
    assert guide["observed_scope"] == "caller-selected-source-only"
    assert guide["read_candidates_observed"] == 3
    assert guide["read_candidates_retained"] == 3
    assert guide["read_candidates_omitted"] == 0
    assert guide["source_inspection_recommended"] is True
    assert guide["read_requests"] == [
        {
            "path": PATH,
            "start_line": 1,
            "end_line": 2,
            "reasons": ["inspect-class-base-and-nearby-import-syntax"],
            "purpose": "inspect-source-syntax",
            "runtime_proof": "not-established",
        },
        {
            "path": PATH,
            "start_line": 4,
            "end_line": 4,
            "reasons": [
                "initializer-syntax-requires-source-inspection",
                "environment-initializer-runtime-meaning-unresolved",
            ],
            "purpose": "inspect-source-syntax",
            "runtime_proof": "not-established",
        },
        {
            "path": PATH,
            "start_line": 5,
            "end_line": 5,
            "reasons": ["initializer-syntax-requires-source-inspection"],
            "purpose": "inspect-source-syntax",
            "runtime_proof": "not-established",
        },
    ]
    assert guide["runtime_contract"] == "unknown"
    assert guide["cross_artifact_correspondence"] == "unresolved"
    assert guide["negative_evidence_admissible"] is False
    assert guide["read_may_not_resolve_runtime"] is True
    assert (
        validate_evidence_presentation(
            packet, present_repository_evidence(packet, format="compact")
        )["valid"]
        is True
    )


def test_literal_env_syntax_needs_no_extra_syntax_read_but_runtime_is_unknown(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "import os\nregion = os.getenv('REGION', 'do_not_expose')\n")
    packet = _observe(tmp_path, guidance=True)
    value = _values(packet, "python-env-access-syntax")[0]
    guide = value["evidence_navigation"]
    assert guide["source_inspection_recommended"] is False
    assert guide["read_requests"] == []
    assert guide["runtime_binding"] == "not-established"
    assert guide["runtime_contract"] == "unknown"
    assert guide["negative_evidence_admissible"] is False
    assert "do_not_expose" not in str(packet)


def test_ambiguous_and_dynamic_key_guidance_points_to_exact_sites(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "import os\n"
        "key = os.getenv(make_key(), **options)\n"
        "copy = os.environ['COPY']\n"
        "del os.environ['COPY']\n",
    )
    packet = _observe(tmp_path, guidance=True)
    env = _values(packet, "python-env-access-syntax")
    assert len(env) == 3
    first = env[0]["evidence_navigation"]["read_requests"][0]
    assert (first["start_line"], first["end_line"]) == (2, 2)
    assert first["reasons"] == [
        "environment-key-expression-unresolved",
        "call-argument-binding-unresolved",
    ]
    assert env[1]["evidence_navigation"]["read_requests"] == []
    delete = env[2]["evidence_navigation"]["read_requests"][0]
    assert (delete["start_line"], delete["end_line"]) == (4, 4)
    assert delete["reasons"] == ["environment-target-effect-unverified"]
    assert env[2]["evidence_navigation"]["runtime_contract"] == "unknown"


def test_read_budget_reports_omission_without_claiming_negative_coverage(
    tmp_path: Path,
) -> None:
    fields = "\n".join(
        f"    field_{i}: str = Field(default_factory=build_{i})" for i in range(20)
    )
    _write(tmp_path, f"class Settings(BaseSettings):\n{fields}\n")
    packet = _observe(tmp_path, guidance=True)
    guide = _values(packet, "python-model-class-syntax")[0]["evidence_navigation"]
    assert guide["read_candidates_observed"] == 21
    assert guide["read_candidates_retained"] == MAX_BACKEND_NAVIGATION_READS
    assert guide["read_candidates_omitted"] == 21 - MAX_BACKEND_NAVIGATION_READS
    assert len(guide["read_requests"]) == MAX_BACKEND_NAVIGATION_READS
    assert guide["read_limit"] == MAX_BACKEND_NAVIGATION_READS
    assert guide["negative_evidence_admissible"] is False


def test_default_provider_identity_is_not_modified_without_opt_in(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "import os\nx = os.getenv('K')\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        implicit = codemap.discover_repository_declarations(
            [StaticPythonBackendDeclarations(paths=(PATH,))]
        )
        explicit_false = codemap.discover_repository_declarations(
            [
                StaticPythonBackendDeclarations(
                    paths=(PATH,), include_evidence_navigation=False
                )
            ]
        )
        opt_in = codemap.discover_repository_declarations(
            [
                StaticPythonBackendDeclarations(
                    paths=(PATH,), include_evidence_navigation=True
                )
            ]
        )
    assert implicit == explicit_false
    assert implicit["observation_identity"] != opt_in["observation_identity"]
    assert "evidence_navigation" not in str(implicit)
    assert "evidence_navigation" in str(opt_in)


@pytest.mark.parametrize("invalid", [None, 0, 1, "yes", [], {}])
def test_navigation_requires_exact_bool_at_admission(invalid: object) -> None:
    with pytest.raises(ValueError, match="include_evidence_navigation"):
        StaticPythonBackendDeclarations(
            paths=(PATH,), include_evidence_navigation=invalid
        )


def test_source_revision_delta_includes_guidance_without_cached_old_ranges(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "import os\nx = os.getenv('A')\n")
    provider = StaticPythonBackendDeclarations(
        paths=(PATH,), include_evidence_navigation=True
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.discover_repository_declarations([provider])
        _write(tmp_path, "import os\nx = os.getenv(make_key())\n")
        codemap.sync([PATH])
        after = codemap.discover_repository_declarations(
            [provider], previous_observation=before
        )
    guide = _values(after, "python-env-access-syntax")[0]["evidence_navigation"]
    assert guide["source_inspection_recommended"] is True
    assert guide["read_requests"][0]["start_line"] == 2
    assert before["observation_identity"] != after["observation_identity"]


def test_visibility_blocks_source_guidance_without_leaking_literals(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "import os\nx = os.getenv('SENSITIVE_KEY')\n")
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "backend.py"\nvisibility = "outline"\n',
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(RepositoryDeclarationProviderError):
            codemap.discover_repository_declarations(
                [
                    StaticPythonBackendDeclarations(
                        paths=(PATH,), include_evidence_navigation=True
                    )
                ]
            )
