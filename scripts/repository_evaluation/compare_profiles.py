from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Mapping
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.repository_evaluation.common import load_json, write_json
from scripts.repository_evaluation.profile_cases import PROFILE_SCHEMA


def _p90(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(0.9 * len(ordered)) - 1))]


def _rows(doc: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    cases = doc.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("profile cases must be a list")
    rows: dict[str, Mapping[str, object]] = {}
    for row in cases:
        if not isinstance(row, Mapping):
            raise ValueError("profile case must be an object")
        case_id = row.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("profile case id must be nonempty")
        if case_id in rows:
            raise ValueError(f"duplicate profile case: {case_id}")
        fingerprint = row.get("semantic_fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint.strip():
            raise ValueError("profile case requires a semantic fingerprint")
        if type(row.get("semantic_stable")) is not bool:
            raise ValueError("profile semantic_stable must be a boolean")
        rows[case_id] = row
    return rows


def _median_ns(row: Mapping[str, object]) -> float:
    value = row["median_ns"]
    if not isinstance(value, (int, float, str)) or isinstance(value, bool):
        raise ValueError("profile median_ns must be numeric")
    median = float(value)
    if not math.isfinite(median) or median <= 0:
        raise ValueError("profile median_ns must be finite and positive")
    return median


def _noise_by_case(
    baseline: Mapping[str, Mapping[str, object]],
    repeat: Mapping[str, Mapping[str, object]] | None,
) -> dict[str, float | None]:
    if repeat is None:
        return {case_id: None for case_id in baseline}
    if set(baseline) != set(repeat):
        raise ValueError("profile repeat case membership mismatch")
    for case_id, row in baseline.items():
        if (
            repeat[case_id]["semantic_stable"] is not True
            or row["semantic_stable"] is not True
            or row["semantic_fingerprint"] != repeat[case_id]["semantic_fingerprint"]
        ):
            raise ValueError("profile repeat semantic identity is not stable")
    return {
        case_id: abs(_median_ns(row) - _median_ns(repeat[case_id]))
        / _median_ns(row)
        * 100.0
        for case_id, row in baseline.items()
    }


def _protocol_integer(doc: Mapping[str, object], key: str, minimum: int) -> int:
    value = doc.get(key)
    if type(value) is not int or value < minimum:
        raise ValueError("profile measurement protocol bounds are invalid")
    return value


def _profile_provenance(doc: Mapping[str, object]) -> dict[str, object]:
    fields = (
        "cases_sha256",
        "repository_identity",
        "producer_implementation_identity",
        "evaluator_implementation_identity",
    )
    if any(
        not isinstance(doc.get(key), str) or not str(doc[key]).strip() for key in fields
    ):
        raise ValueError("profile measurement provenance is missing")
    if doc.get("schema") != PROFILE_SCHEMA:
        raise ValueError("profile provenance requires the current profile schema")
    protocol = {
        "warmups": _protocol_integer(doc, "warmups", 0),
        "samples": _protocol_integer(doc, "samples", 3),
        "shard_count": _protocol_integer(doc, "shard_count", 1),
    }
    if "shard_index" not in doc:
        raise ValueError("profile shard protocol identity is missing")
    index = doc.get("shard_index")
    if index is None:
        if doc.get("complete") is not True:
            raise ValueError("profile merged provenance must be complete")
    elif type(index) is not int or not 0 <= index < protocol["shard_count"]:
        raise ValueError("profile shard protocol is invalid")
    return {key: doc.get(key) for key in (*fields, *protocol, "shard_index", "suite")}


def _comparable_profiles(
    baseline: Mapping[str, object],
    candidate: Mapping[str, object],
    repeat: Mapping[str, object] | None,
) -> None:
    base = _profile_provenance(baseline)
    observed = [candidate] if repeat is None else [candidate, repeat]
    for doc in observed:
        provenance = _profile_provenance(doc)
        if any(
            provenance[key] != value
            for key, value in base.items()
            if key != "producer_implementation_identity"
        ):
            raise ValueError("profile identity or measurement protocol mismatch")
    if repeat is not None and (
        repeat["producer_implementation_identity"]
        != base["producer_implementation_identity"]
    ):
        raise ValueError("profile repeat producer identity mismatch")


def _decision(semantic_equal: bool, gain: float, threshold: float | None) -> str:
    if not semantic_equal:
        return "SEMANTIC_CHANGE"
    if threshold is None:
        return "UNCALIBRATED"
    if gain > threshold:
        return "WIN"
    return "REGRESSION" if gain < -threshold else "NOISE_BAND"


def compare_profiles(
    *,
    baseline: Mapping[str, object],
    candidate: Mapping[str, object],
    repeat: Mapping[str, object] | None = None,
    minimum_gain_pct: float = 3.0,
) -> dict[str, object]:
    b, c = _rows(baseline), _rows(candidate)
    r = _rows(repeat) if repeat is not None else None
    if set(b) != set(c):
        raise ValueError("profile case membership mismatch")
    if not b:
        raise ValueError("profile comparison requires non-empty cases")
    _comparable_profiles(baseline, candidate, repeat)
    noise_by_case = _noise_by_case(b, r)
    global_noise = (
        _p90([value for value in noise_by_case.values() if value is not None])
        if r is not None
        else None
    )
    output = []
    for case_id in sorted(b):
        br, cr = b[case_id], c[case_id]
        semantic_equal = (
            br.get("semantic_fingerprint") == cr.get("semantic_fingerprint")
            and bool(br.get("semantic_stable"))
            and bool(cr.get("semantic_stable"))
        )
        base = _median_ns(br)
        cand = _median_ns(cr)
        raw = (base - cand) / base * 100.0
        noise = noise_by_case[case_id]
        threshold = max(float(minimum_gain_pct), noise) if noise is not None else None
        decision = _decision(semantic_equal, raw, threshold)
        output.append(
            {
                "id": case_id,
                "baseline_median_ns": int(base),
                "candidate_median_ns": int(cand),
                "raw_gain_pct": raw,
                "same_version_noise_pct": noise,
                "required_gain_pct": threshold,
                "semantic_equal": semantic_equal,
                "decision": decision,
            }
        )
    return {
        "schema": "hashmarks.repository-evaluation-profile-comparison.v1",
        "cases": output,
        "wins": sum(x["decision"] == "WIN" for x in output),
        "semantic_changes": sum(x["decision"] == "SEMANTIC_CHANGE" for x in output),
        "noise_floor_percent": global_noise,
        "noise_floor_authority": "per-case same-version noise; global p90 is diagnostic only",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--repeat", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--minimum-gain-pct", type=float, default=3.0)
    a = p.parse_args()
    result = compare_profiles(
        baseline=load_json(a.baseline, schema=PROFILE_SCHEMA),
        candidate=load_json(a.candidate, schema=PROFILE_SCHEMA),
        repeat=load_json(a.repeat, schema=PROFILE_SCHEMA) if a.repeat else None,
        minimum_gain_pct=a.minimum_gain_pct,
    )
    write_json(a.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
