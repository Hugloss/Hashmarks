"""B35-B39: frozen backend navigation A/B packets are descriptive only."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.agent_evaluation.backend_navigation_ablation import (
    MANIFEST_SCHEMA,
    SCHEMA,
    _digest,
    _encode,
    export_cases,
    main,
    validate_export,
)

PATH = "service.py"


def _manifest(*, mode: str = "both") -> dict:
    return {
        "schema": MANIFEST_SCHEMA,
        "cases": [
            {
                "id": "settings-key",
                "prompt": "Find the declared configuration key and its source.",
                "paths": [PATH],
                "model_fields": mode != "environment",
                "environment_reads": mode != "model",
            },
        ],
    }


def _write(repo: Path, source: str | None = None) -> None:
    (repo / PATH).write_text(
        source
        or (
            "import os\n"
            "class Settings(BaseSettings):\n"
            "    token: str = os.getenv('ACCESS_TOKEN', 'DONT_COPY_THIS_VALUE')\n"
            "    computed: str = Field(default_factory=lookup_secret)\n"
        ),
        encoding="utf-8",
    )


def test_same_bound_source_facts_in_both_arms_and_only_navigation_added(
    tmp_path: Path,
) -> None:
    _write(tmp_path)
    result = export_cases(tmp_path, _manifest())
    validate_export(result)
    assert result["schema"] == SCHEMA
    assert result["source_fact_equivalence"] == "checked"
    assert result["model_delivery"] == "not-observed"
    assert result["paired_correctness"] == "not-measured"
    assert len(result["cases"]) == 1
    pair = result["cases"][0]
    before, after = pair["arms"]
    assert [row["arm"] for row in pair["arms"]] == ["syntax-only", "navigation"]
    assert before["prompt"] == after["prompt"]
    assert before["fact_identity"] == after["fact_identity"]
    assert before["fact_identity"] == pair["source_facts_identity"]
    assert (
        before["provider_packet"]["repository"]
        == (after["provider_packet"]["repository"])
    )
    assert before["host_visible"] == after["host_visible"] == "not-established"
    assert before["agent_used"] == after["agent_used"] == "not-established"
    left = before["provider_packet"]["declarations"]["groups"]
    right = after["provider_packet"]["declarations"]["groups"]
    assert len(left) == len(right) == 2
    assert all(
        "evidence_navigation" not in group["declarations"][0]["value"] for group in left
    )
    assert all(
        "evidence_navigation" in group["declarations"][0]["value"] for group in right
    )
    assert "DONT_COPY_THIS_VALUE" not in json.dumps(result)
    assert export_cases(tmp_path, _manifest()) == result


def test_modes_are_real_independent_source_experiments(tmp_path: Path) -> None:
    _write(tmp_path)
    for mode, kind in (
        ("model", "python-model-class-syntax"),
        ("environment", "python-env-access-syntax"),
    ):
        result = export_cases(tmp_path, _manifest(mode=mode))
        validate_export(result)
        assert (
            len(
                result["cases"][0]["arms"][0]["provider_packet"]["declarations"][
                    "groups"
                ]
            )
            == 1
        )
        assert (
            result["cases"][0]["arms"][0]["provider_packet"]["declarations"]["groups"][
                0
            ]["concept"]["kind"]
            == kind
        )


def test_source_edit_changes_snapshot_identity_and_exposed_navigation(
    tmp_path: Path,
) -> None:
    _write(tmp_path)
    first = export_cases(tmp_path, _manifest())
    _write(
        tmp_path,
        "import os\n"
        "class Settings(BaseSettings):\n"
        "    token: str = os.getenv(make_key(), 'DONT_COPY_THIS_VALUE')\n",
    )
    next_snapshot = export_cases(tmp_path, _manifest())
    validate_export(next_snapshot)
    assert first["export_identity"] != next_snapshot["export_identity"]
    assert (
        first["cases"][0]["source_facts_identity"]
        != next_snapshot["cases"][0]["source_facts_identity"]
    )
    env = next_snapshot["cases"][0]["arms"][1]["provider_packet"]["declarations"][
        "groups"
    ]
    reads = [
        group["declarations"][0]["value"]["evidence_navigation"]["read_requests"]
        for group in env
        if group["concept"]["kind"] == "python-env-access-syntax"
    ]
    assert reads[0][0]["start_line"] == 3
    assert "DONT_COPY_THIS_VALUE" not in json.dumps(next_snapshot)


@pytest.mark.parametrize(
    "defect",
    [
        "wrong-schema",
        "duplicate-case",
        "extra-field",
        "bad-flag",
        "bad-path",
        "empty-case-list",
        "no-observer",
    ],
)
def test_malformed_manifest_fails_before_index_source_work(
    tmp_path: Path, defect: str
) -> None:
    manifest = _manifest()
    if defect == "wrong-schema":
        manifest["schema"] = "wrong"
    elif defect == "duplicate-case":
        manifest["cases"] *= 2
    elif defect == "extra-field":
        manifest["cases"][0]["oracle"] = "unsupported"
    elif defect == "bad-flag":
        manifest["cases"][0]["model_fields"] = 1
    elif defect == "bad-path":
        manifest["cases"][0]["paths"] = ["../secrets.py"]
    elif defect == "empty-case-list":
        manifest["cases"] = []
    else:
        manifest["cases"][0]["model_fields"] = False
        manifest["cases"][0]["environment_reads"] = False
    with pytest.raises(ValueError):
        export_cases(tmp_path, manifest)
    assert not any(tmp_path.iterdir())


def test_manipulated_arm_identity_fails_validation(tmp_path: Path) -> None:
    _write(tmp_path)
    original = export_cases(tmp_path, _manifest())
    tampered = copy.deepcopy(original)
    tampered["cases"][0]["arms"][0]["prompt"] = "fabricated"
    with pytest.raises(ValueError, match="export identity"):
        validate_export(tampered)
    # Even after self-consistent outer re-digestion, an unchanged inner receipt fails.
    tampered["export_identity"] = _digest(
        {k: v for k, v in tampered.items() if k != "export_identity"}
    )
    with pytest.raises(ValueError, match="observation identity"):
        validate_export(tampered)


def test_navigation_not_forgeable_by_relabeling_an_arm(tmp_path: Path) -> None:
    _write(tmp_path)
    tampered = copy.deepcopy(export_cases(tmp_path, _manifest()))
    case = tampered["cases"][0]
    case["arms"][1]["provider_packet"] = copy.deepcopy(
        case["arms"][0]["provider_packet"]
    )
    for arm in case["arms"]:
        observation = {
            k: v
            for k, v in arm.items()
            if k not in {"observation_identity", "utf8_bytes"}
        }
        arm["observation_identity"] = _digest(observation)
        arm["utf8_bytes"] = len(_encode(observation))
    tampered["export_identity"] = _digest(
        {k: v for k, v in tampered.items() if k != "export_identity"}
    )
    with pytest.raises(ValueError, match="navigation"):
        validate_export(tampered)


def test_source_divergence_fails_even_if_both_arm_checksums_recomputed(
    tmp_path: Path,
) -> None:
    _write(tmp_path)
    tampered = copy.deepcopy(export_cases(tmp_path, _manifest()))
    case = tampered["cases"][0]
    after = case["arms"][1]
    value = after["provider_packet"]["declarations"]["groups"][0]["declarations"][0][
        "value"
    ]
    value["class_name_syntax"] = "OtherSettings"
    for arm in case["arms"]:
        observation = {
            k: v
            for k, v in arm.items()
            if k not in {"observation_identity", "utf8_bytes"}
        }
        arm["observation_identity"] = _digest(observation)
        arm["utf8_bytes"] = len(_encode(observation))
    tampered["export_identity"] = _digest(
        {k: v for k, v in tampered.items() if k != "export_identity"}
    )
    with pytest.raises(ValueError, match="differs beyond navigation"):
        validate_export(tampered)


def test_export_cli_writes_only_validated_complete_pair(tmp_path: Path) -> None:
    _write(tmp_path)
    manifest_path = tmp_path / "cases.json"
    output = tmp_path / "frozen.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    expected = export_cases(tmp_path, _manifest())
    assert (
        main(
            [
                "--repo",
                str(tmp_path),
                "--manifest",
                str(manifest_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert json.loads(output.read_text(encoding="utf-8")) == expected
    assert output.read_bytes().endswith(b"\n")


def test_outline_source_visibility_denied_before_export(tmp_path: Path) -> None:
    _write(tmp_path)
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "service.py"\nvisibility = "outline"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        export_cases(tmp_path, _manifest())
