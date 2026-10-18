"""Debugging proof binds actual runtime frames, independent source and artifacts."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records

from hashmarks.codemap import CodeMap
from hashmarks.test_shards import repository_content_identity
from scripts.repository_evaluation.backend_grading import FactObservation
from scripts.repository_evaluation.backend_runtime_witnesses import (
    freeze_runtime_oracles,
    retained_runtime_witnesses,
    runtime_correlation_request,
    runtime_frame_checks,
    runtime_frame_observations,
)
from scripts.repository_evaluation.capture_backend_failure import _repository_frames
from scripts.repository_evaluation.common import write_json

RuntimeSpecimen = tuple[dict[str, object], dict[str, object], Path, FactObservation]


def _capture(source: Path, text: str, expression: str) -> dict[str, object]:
    path = source / "service.py"
    path.write_text(text)
    namespace: dict[str, object] = {}
    exec(compile(text, str(path), "exec"), namespace)
    try:
        eval(expression, namespace)
    except (ValueError, ZeroDivisionError) as exc:
        frames, _ = _repository_frames(exc, source)
    else:
        raise AssertionError("fixture did not produce a runtime failure")
    return {
        "source_identity": repository_content_identity(source),
        "workflow": "actual-failure",
        "stage": "before",
        "frames": frames,
    }


@pytest.fixture
def runtime_specimen(tmp_path: Path) -> RuntimeSpecimen:
    source = tmp_path / "source"
    source.mkdir()
    capture = _capture(
        source,
        "from typing import overload\n"
        "def decorate(method):\n    return method\n"
        "class Service:\n"
        "    @overload\n    def process(self, value: int): ...\n"
        "    @overload\n    def process(self, value: str): ...\n"
        "    @decorate\n    def process(self, value):\n"
        "        raise ValueError('real traceback')\n",
        "Service().process(1)",
    )
    oracle = freeze_runtime_oracles(
        source, capture, repository="repo", bundle_id="runtime:1"
    )
    frame = assert_object(assert_array(capture["frames"])[0])
    with CodeMap(source, state_dir=tmp_path / "index") as codemap:
        codemap.index.sync()
        packet = codemap.correlation.observe(
            [
                {
                    "bundle_id": "runtime:1",
                    "producer": {"kind": "actual-traceback"},
                    "completeness": "complete",
                    "truncation": "complete",
                    "scope": {},
                    "anchors": [
                        {
                            "anchor_id": "frame-0",
                            "path": frame["path"],
                            "line": frame["line"],
                            "member_revision": frame["source_revision"],
                        }
                    ],
                }
            ],
            include_relationships=False,
        )
    output = tmp_path / "observations"
    write_json(output / "api.json", packet)
    write_json(output / "cli.json", [])
    write_json(output / "mcp.json", [])
    revision = frame["source_revision"]
    assert isinstance(revision, str)
    context = FactObservation(
        "debug_correspondence",
        "actual-failure",
        "before",
        None,
        "api",
        "none",
        "/cases/actual-failure/runtime_oracles/before/checks",
        None,
        ({"repository": "repo", "path": "service.py", "revision": revision},),
    )
    return oracle, packet, output, context


def test_exact_source_coordinates_qualify_overload_and_decorator_identity(
    runtime_specimen: RuntimeSpecimen,
) -> None:
    oracle, packet, output, context = runtime_specimen
    assert oracle["reviewed"] is False
    rows = runtime_frame_observations(packet, oracle, stage="before")
    assert rows == [
        {
            "unit_id": "before:frame-0",
            "correspondence": True,
            "declaration_state": "exact",
        }
    ]
    witnesses = retained_runtime_witnesses(output, oracle, context)
    assert witnesses and all(row["state"] == "PASS" for row in witnesses)
    assert {row["surface"] for row in witnesses} == {"api"}
    assert {row["artifact"] for row in witnesses} == {"before/api.json"}
    # Missing transports have no fabricated witnesses; required membership must
    # still be checked by the existing campaign/proof accounting owner.


@pytest.mark.parametrize(
    "field,value", [("path", "other.py"), ("start_line", 1), ("name", "different")]
)
def test_wrong_declaration_cannot_pass_same_name_or_containment(
    runtime_specimen: RuntimeSpecimen, field: str, value: object
) -> None:
    oracle, packet, output, context = runtime_specimen
    forged = copy.deepcopy(packet)
    bundle = assert_object(assert_array(forged["bundles"])[0])
    anchor = assert_object(assert_array(bundle["anchors"])[0])
    candidate = assert_object(
        assert_array(assert_object(anchor["resolution"])["candidates"])[0]
    )
    candidate[field] = value
    write_json(output / "api.json", forged)
    witnesses = retained_runtime_witnesses(output, oracle, context)
    assert any(row["state"] == "FAIL" for row in witnesses)
    assert (
        runtime_frame_observations(forged, oracle, stage="before")[0]["correspondence"]
        is False
    )


def test_other_bundle_cannot_supply_missing_runtime_anchor(
    runtime_specimen: RuntimeSpecimen,
) -> None:
    oracle, packet, output, context = runtime_specimen
    forged = copy.deepcopy(packet)
    bundle = assert_object(assert_array(forged["bundles"])[0])
    other = copy.deepcopy(bundle)
    other["bundle_id"] = "unrelated"
    bundle["anchors"] = []
    assert_array(forged["bundles"]).append(other)
    write_json(output / "api.json", forged)
    assert any(
        row["state"] == "FAIL"
        for row in retained_runtime_witnesses(output, oracle, context)
    )
    assert (
        runtime_frame_observations(forged, oracle, stage="before")[0]["correspondence"]
        is False
    )


@pytest.mark.parametrize("change", ["stage", "unit", "revision", "repository"])
def test_runtime_context_and_source_identity_must_match(
    runtime_specimen: RuntimeSpecimen, change: str
) -> None:
    oracle, _, output, context = runtime_specimen
    if change in {"stage", "unit"}:
        context = replace(
            context,
            **({"stage": "after"} if change == "stage" else {"unit_id": "other"}),
        )
    else:
        context = replace(
            context, source_bindings=({**context.source_bindings[0], change: "other"},)
        )
    with pytest.raises(ValueError, match="different"):
        retained_runtime_witnesses(output, oracle, context)


def test_missing_source_binding_cannot_promote_matching_facts(
    runtime_specimen: RuntimeSpecimen,
) -> None:
    oracle, _, output, context = runtime_specimen
    witnesses = retained_runtime_witnesses(
        output, oracle, replace(context, source_bindings=())
    )
    assert witnesses and all(row["state"] == "INCOMPLETE" for row in witnesses)
    packet = json.loads((output / "api.json").read_bytes())
    assert_object(assert_array(packet["bundles"])[0])["anchors"] = []
    write_json(output / "api.json", packet)
    witnesses = retained_runtime_witnesses(
        output, oracle, replace(context, source_bindings=())
    )
    assert any(row["state"] == "FAIL" for row in witnesses)


def test_retained_runtime_grading_requires_actual_artifact_bytes(
    runtime_specimen: RuntimeSpecimen,
) -> None:
    oracle, _, output, context = runtime_specimen
    (output / "api.json").unlink()
    with pytest.raises(ValueError, match="not a repository file"):
        retained_runtime_witnesses(output, oracle, context)


def test_pseudo_callable_is_retained_as_a_metric_miss(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    # Generator expressions retain a separate frame; Python 3.12+ inlines list
    # comprehensions, which would stop exercising unsupported pseudo-callables.
    capture = _capture(
        source, "def process():\n    return list(1 / 0 for value in [1])\n", "process()"
    )
    oracle = freeze_runtime_oracles(
        source, capture, repository="repo", bundle_id="runtime:1"
    )
    frames = assert_records(oracle["frames"])
    assert len(frames) == 2
    assert [frame["declaration_state"] for frame in frames] == ["exact", "unsupported"]
    observations = runtime_frame_observations({"bundles": []}, oracle, stage="before")
    assert len(observations) == 2
    assert observations[1]["correspondence"] is False


def test_empty_success_control_does_not_manufacture_frame_proof(tmp_path: Path) -> None:
    oracle = freeze_runtime_oracles(
        tmp_path,
        {
            "source_identity": repository_content_identity(tmp_path),
            "frames": [],
            "workflow": "success-control",
            "stage": "after",
        },
        repository="repo",
        bundle_id="runtime:1",
    )
    assert runtime_frame_checks(oracle) == []
    assert runtime_frame_observations({}, oracle, stage="after") == []


def test_duplicate_frame_units_cannot_inflate_metrics(
    runtime_specimen: RuntimeSpecimen,
) -> None:
    oracle, _, _, _ = runtime_specimen
    forged = copy.deepcopy(oracle)
    frames = assert_array(forged["frames"])
    frames.append(copy.deepcopy(frames[0]))
    with pytest.raises(ValueError, match="duplicate frame membership"):
        runtime_frame_checks(forged)


def test_frame_metrics_cannot_change_the_frozen_source_stage(
    runtime_specimen: RuntimeSpecimen,
) -> None:
    oracle, packet, _, _ = runtime_specimen
    with pytest.raises(ValueError, match="exact source stage"):
        runtime_frame_observations(packet, oracle, stage="after")


def test_invalidated_variant_requires_observed_mismatch(
    runtime_specimen: RuntimeSpecimen,
) -> None:
    oracle, packet, output, context = runtime_specimen
    original = retained_runtime_witnesses(output, oracle, context, invalidated=True)
    assert any(row["state"] == "FAIL" for row in original)
    frame = assert_object(
        assert_array(assert_object(assert_array(packet["bundles"])[0])["anchors"])[0]
    )
    frame["source_equivalence"] = {"state": "mismatch", "basis": []}
    write_json(output / "api.json", packet)
    updated = retained_runtime_witnesses(output, oracle, context, invalidated=True)
    assert all(row["state"] == "PASS" for row in updated)
    assert {row["artifact_sha256"] for row in original} != {
        row["artifact_sha256"] for row in updated
    }


def test_correlation_request_preserves_external_chain_metadata(tmp_path: Path) -> None:
    capture = _capture(tmp_path, "def process():\n    return 1 / 0\n", "process()")
    frame = assert_records(capture["frames"])[0]
    frame.update(exception_chain_index=2, exception_type="builtins.ZeroDivisionError")
    request = runtime_correlation_request(capture, bundle_id="runtime:chain")
    bundle = assert_object(assert_array(request["bundles"])[0])
    anchor = assert_object(assert_array(bundle["anchors"])[0])
    assert anchor["metadata"] == {
        "runtime_qualname": "process",
        "code_first_line": 1,
        "exception_chain_index": 2,
        "exception_type": "builtins.ZeroDivisionError",
    }
    invalidated = runtime_correlation_request(
        capture, bundle_id="runtime:chain", invalidated=True
    )
    bad_anchor = assert_object(
        assert_array(assert_object(assert_array(invalidated["bundles"])[0])["anchors"])[
            0
        ]
    )
    assert bad_anchor["metadata"] == anchor["metadata"]
    assert bad_anchor["member_revision"] == "0" * 64
    assert anchor["member_revision"] == frame["source_revision"]
