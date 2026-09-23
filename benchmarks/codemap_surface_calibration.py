from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sqlite3
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from benchmarks.research_receipts import (
    atomic_write_json as _atomic_write_json,
)
from benchmarks.research_receipts import (
    durability_summary,
    evaluate_with_receipt,
    work_identity,
)
from hashmarks._command_output import log_command_output
from hashmarks.codemap.decision_contract import (
    DecisionPacketContract,
)
from hashmarks.codemap.engine import (
    CodeMap,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Iterable

EXPENSIVE_SURFACES = frozenset(
    {"generated", "openapi", "docs", "translation", "snapshot", "fixture", "lockfile"}
)


@dataclass
class _TaskEvaluation:
    row: dict[str, Any]
    phase_seconds: dict[str, Any]
    elapsed: float
    edit_graded: int
    exact_edit: int
    verify_graded: int
    exact_verify: int
    false_safe: int
    discrimination_needed: int
    discrimination_graded: int
    discrimination_correct: int


@dataclass
class _EvaluationState:
    rows: list[dict[str, Any]] = field(default_factory=list)
    latencies: list[float] = field(default_factory=list)
    phase_samples: dict[str, list[float]] = field(default_factory=dict)
    contribution: dict[str, dict[str, int]] = field(default_factory=dict)
    edit_graded: int = 0
    exact_edit: int = 0
    verify_graded: int = 0
    exact_verify: int = 0
    false_safe: int = 0
    discrimination_needed: int = 0
    discrimination_graded: int = 0
    discrimination_correct: int = 0

    def add(self, task: _TaskEvaluation) -> None:
        self.rows.append(task.row)
        self.latencies.append(task.elapsed)
        self.edit_graded += task.edit_graded
        self.exact_edit += task.exact_edit
        self.verify_graded += task.verify_graded
        self.exact_verify += task.exact_verify
        self.false_safe += task.false_safe
        self.discrimination_needed += task.discrimination_needed
        self.discrimination_graded += task.discrimination_graded
        self.discrimination_correct += task.discrimination_correct
        surfaces = task.row["evidence_surfaces"]
        for role in ("edit", "verify"):
            surface = surfaces.get(role)
            if surface:
                bucket = self.contribution.setdefault(
                    str(surface), {"edit_selected": 0, "verify_selected": 0}
                )
                bucket[f"{role}_selected"] += 1
        for phase, value in task.phase_seconds.items():
            if isinstance(value, (int, float)):
                self.phase_samples.setdefault(str(phase), []).append(float(value))


@dataclass(frozen=True)
class ExistingGroupOptions:
    variant: str = "full"
    group_size: int = 8
    group_index: int = 0
    manifest_path: Path | None = None


@dataclass(frozen=True)
class _BaselineCalibration:
    state_dir: Path
    artifact_db: Path
    preflight: dict[str, Any]
    sync_economics: dict[str, Any]
    decision: dict[str, Any]
    cold_seconds: float
    lexical_rows: int
    database_bytes: int


def _task_identity(item: dict[str, Any]) -> str:
    return str(
        item.get("id") or hashlib.sha256(str(item["task"]).encode()).hexdigest()[:16]
    )


def evaluate_resumable(
    codemap: CodeMap,
    corpus: list[dict[str, Any]],
    *,
    receipt_dir: Path,
    manifest_sha256: str,
    group_index: int,
    expected_task_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Persist one calibration receipt per completed task.

    This is benchmark evidence durability, not runtime retry/resume authority. Existing
    receipts are reused only when manifest/group/task identity matches exactly. Timing
    from a resumed run is explicitly marked non-comparable because cache/session state
    may differ across process boundaries.
    """
    receipt_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    reused = 0
    created = 0
    expected_ids = (
        {str(value) for value in expected_task_ids}
        if expected_task_ids is not None
        else {_task_identity(item) for item in corpus}
    )
    for item in corpus:
        task_id = _task_identity(item)
        receipt_path = receipt_dir / f"group-{group_index:03d}-task-{task_id}.json"
        expected_identity = work_identity(
            protocol_identity=manifest_sha256,
            lane=f"group-{group_index:03d}",
            work_id=task_id,
            work_payload={"task": str(item["task"]), "task_id": task_id},
        )
        try:
            result, was_reused = evaluate_with_receipt(
                receipt_path=receipt_path,
                identity=expected_identity,
                evaluate=lambda item=item: evaluate(
                    codemap, [item], session_batch_size=1
                ),
            )
        except ValueError as exc:
            raise ValueError("calibration task receipt identity mismatch") from exc
        reused += int(was_reused)
        created += int(not was_reused)
        results.append(result)

    rows = [row for result in results for row in result.get("rows", [])]
    latencies = [float(row.get("seconds", 0.0)) for row in rows]
    phase_values: dict[str, list[float]] = {}
    session_totals: dict[str, int] = {}
    for result in results:
        for phase, metrics in (result.get("phase_seconds") or {}).items():
            phase_values.setdefault(str(phase), []).append(
                float((metrics or {}).get("total", 0.0))
            )
        for key, value in (result.get("decision_session") or {}).items():
            if key in {"batch_size", "batches"}:
                continue
            if isinstance(value, int):
                session_totals[str(key)] = session_totals.get(str(key), 0) + value
    combined = {
        "tasks": sum(int(result.get("tasks", 0)) for result in results),
        "edit_graded": sum(int(result.get("edit_graded", 0)) for result in results),
        "exact_edit": sum(int(result.get("exact_edit", 0)) for result in results),
        "verify_graded": sum(int(result.get("verify_graded", 0)) for result in results),
        "exact_verify": sum(int(result.get("exact_verify", 0)) for result in results),
        "false_safe": sum(int(result.get("false_safe", 0)) for result in results),
        "discrimination_needed": sum(
            int(result.get("discrimination_needed", 0)) for result in results
        ),
        "discrimination_graded": sum(
            int(result.get("discrimination_graded", 0)) for result in results
        ),
        "discrimination_correct": sum(
            int(result.get("discrimination_correct", 0)) for result in results
        ),
        "decision_seconds": {
            "total": sum(latencies),
            "median": statistics.median(latencies) if latencies else 0.0,
            "p95": _percentile(latencies, 0.95),
            "max": max(latencies) if latencies else 0.0,
        },
        "phase_seconds": {
            phase: {"total": sum(values)}
            for phase, values in sorted(phase_values.items())
        },
        "decision_session": {
            **session_totals,
            "batch_size": 1,
            "batches": len(results),
        },
        "rows": rows,
        "durability": {
            **durability_summary(
                expected_work_ids=expected_ids,
                completed_work_ids=[_task_identity(item) for item in corpus],
                reused=reused,
                created=created,
            ),
            "receipt_dir": str(receipt_dir),
            "expected_tasks": len(expected_ids),
            "created": created,
            "reused": reused,
            "performance_comparable": reused == 0,
        },
    }
    return combined


def _checkpoint(db_path: Path) -> None:
    db = sqlite3.connect(db_path)
    try:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        db.close()


def _lexical_rows(db_path: Path) -> int:
    db = sqlite3.connect(db_path)
    try:
        return int(db.execute("SELECT COUNT(*) FROM lexical").fetchone()[0])
    finally:
        db.close()


def _db_bytes(db_path: Path) -> int:
    total = 0
    for suffix in ("", "-wal"):
        path = Path(str(db_path) + suffix)
        if path.exists():
            total += path.stat().st_size
    return total


def _surface_paths(db_path: Path, surfaces: set[str]) -> list[str]:
    db = sqlite3.connect(db_path)
    try:
        paths = [
            str(row[0]) for row in db.execute("SELECT path FROM file_map ORDER BY path")
        ]
    finally:
        db.close()
    return [path for path in paths if CodeMap._index_surface_for_path(path) in surfaces]


def apply_variant(
    db_path: Path, variant: str, *, surfaces: Iterable[str] = EXPENSIVE_SURFACES
) -> dict[str, Any]:
    """Apply a benchmark-only lexical representation to a closed CodeMap DB.

    This deliberately mutates only a copied benchmark database. It is not a runtime
    indexing policy. `membership` keeps one representative row per (path, token),
    preserving file-level token membership while discarding line multiplicity.
    `cap4` preserves at most four line positions per (path, token).
    """
    selected = set(surfaces)
    if variant == "full":
        return {
            "variant": variant,
            "selected_surfaces": sorted(selected),
            "changed_paths": 0,
        }
    if variant not in {"membership", "cap4"}:
        raise ValueError(f"unknown variant: {variant}")
    paths = _surface_paths(db_path, selected)
    if not paths:
        return {
            "variant": variant,
            "selected_surfaces": sorted(selected),
            "changed_paths": 0,
        }
    db = sqlite3.connect(db_path)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TEMP TABLE selected_path(path TEXT PRIMARY KEY)")
        db.executemany(
            "INSERT INTO selected_path(path) VALUES (?)", ((path,) for path in paths)
        )
        db.execute(
            "CREATE TEMP TABLE lexical_keep(path TEXT NOT NULL, token TEXT NOT NULL, line INTEGER NOT NULL, PRIMARY KEY(token,path,line)) WITHOUT ROWID"
        )
        if variant == "membership":
            db.execute(
                "INSERT INTO lexical_keep(path,token,line) "
                "SELECT l.path,l.token,MIN(l.line) FROM lexical l JOIN selected_path s ON s.path=l.path GROUP BY l.path,l.token"
            )
        else:
            db.execute(
                "INSERT INTO lexical_keep(path,token,line) "
                "SELECT path,token,line FROM ("
                "SELECT l.path,l.token,l.line,ROW_NUMBER() OVER (PARTITION BY l.path,l.token ORDER BY l.line) AS rn "
                "FROM lexical l JOIN selected_path s ON s.path=l.path) WHERE rn<=4"
            )
        db.execute("DELETE FROM lexical WHERE path IN (SELECT path FROM selected_path)")
        db.execute(
            "INSERT INTO lexical(path,token,line) SELECT path,token,line FROM lexical_keep"
        )
        db.commit()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.execute("VACUUM")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {
        "variant": variant,
        "selected_surfaces": sorted(selected),
        "changed_paths": len(paths),
    }


def _selected_path(packet: dict[str, Any], role: str) -> str | None:
    row = packet.get(role)
    if isinstance(row, dict):
        value = row.get("path")
        return str(value) if value else None
    return None


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def _decision_phase_seconds(packet: dict[str, Any]) -> dict[str, Any]:
    metrics = packet.get("decision_metrics")
    if metrics is None:
        return {}
    if not isinstance(metrics, dict):
        raise ValueError("decision_metrics must be an object")
    seconds = metrics.get("seconds")
    if seconds is None:
        return {}
    if not isinstance(seconds, dict):
        raise ValueError("decision_metrics seconds must be an object")
    return seconds


def _evaluate_task(codemap: CodeMap, item: dict[str, Any]) -> _TaskEvaluation:
    started = time.perf_counter()
    packet = codemap.task_decision_packet(str(item["task"]))
    contract = DecisionPacketContract.parse(packet)
    elapsed = time.perf_counter() - started
    edit, verify = contract.edit.path, contract.verify.path
    expected_edit = [str(value) for value in item.get("expected_edit", [])]
    expected_verify = [str(value) for value in item.get("expected_verify", [])]
    expected_discrimination = item.get("expected_discrimination")
    edit_ok = None if not expected_edit else edit in expected_edit
    verify_ok = None if not expected_verify else verify in expected_verify
    discrimination_needed = contract.discrimination_needed
    confident = not discrimination_needed and not contract.ambiguous
    false_safe = (confident and bool(expected_edit) and not bool(edit_ok)) or (
        expected_discrimination is True and not discrimination_needed
    )
    return _TaskEvaluation(
        row={
            "id": item.get("id"),
            "task": item["task"],
            "edit": edit,
            "verify": verify,
            "edit_ok": edit_ok,
            "verify_ok": verify_ok,
            "discrimination_needed": discrimination_needed,
            "expected_discrimination": expected_discrimination,
            "ambiguous": contract.ambiguous,
            "status": "complete" if contract.codemap_complete else "incomplete",
            "seconds": elapsed,
            "evidence_surfaces": packet.get("evidence_surfaces") or {},
        },
        phase_seconds=_decision_phase_seconds(packet),
        elapsed=elapsed,
        edit_graded=int(bool(expected_edit)),
        exact_edit=int(bool(expected_edit) and bool(edit_ok)),
        verify_graded=int(bool(expected_verify)),
        exact_verify=int(bool(expected_verify) and bool(verify_ok)),
        false_safe=int(false_safe),
        discrimination_needed=int(discrimination_needed),
        discrimination_graded=int(expected_discrimination is not None),
        discrimination_correct=int(
            expected_discrimination is not None
            and discrimination_needed is bool(expected_discrimination)
        ),
    )


def _evaluation_result(
    state: _EvaluationState,
    task_count: int,
    session_batch_size: int,
    session_totals: dict[str, int],
) -> dict[str, Any]:
    return {
        "tasks": task_count,
        "edit_graded": state.edit_graded,
        "exact_edit": state.exact_edit,
        "verify_graded": state.verify_graded,
        "exact_verify": state.exact_verify,
        "false_safe": state.false_safe,
        "discrimination_needed": state.discrimination_needed,
        "discrimination_graded": state.discrimination_graded,
        "discrimination_correct": state.discrimination_correct,
        "decision_seconds": {
            "total": sum(state.latencies),
            "median": statistics.median(state.latencies) if state.latencies else 0.0,
            "p95": _percentile(state.latencies, 0.95),
            "max": max(state.latencies) if state.latencies else 0.0,
        },
        "phase_seconds": {
            phase: {
                "total": sum(values),
                "median": statistics.median(values),
                "p95": _percentile(values, 0.95),
                "max": max(values),
            }
            for phase, values in sorted(state.phase_samples.items())
        },
        "decision_session": {
            **session_totals,
            "batch_size": session_batch_size,
            "batches": (task_count + session_batch_size - 1) // session_batch_size
            if task_count
            else 0,
        },
        "selected_surface_contribution": {
            key: state.contribution[key] for key in sorted(state.contribution)
        },
        "rows": state.rows,
    }


def evaluate(
    codemap: CodeMap, corpus: list[dict[str, Any]], *, session_batch_size: int = 8
) -> dict[str, Any]:
    if session_batch_size < 1:
        raise ValueError("session_batch_size must be >= 1")
    state = _EvaluationState()
    session_totals = {
        "symbols_hit": 0,
        "symbols_miss": 0,
        "df_hit": 0,
        "df_miss": 0,
        "candidates_hit": 0,
        "candidates_miss": 0,
    }
    for offset in range(0, len(corpus), session_batch_size):
        with codemap.decision_session():
            for item in corpus[offset : offset + session_batch_size]:
                state.add(_evaluate_task(codemap, item))
            session_stats = codemap.decision_session_stats()
            for key, value in session_stats.items():
                session_totals[key] = session_totals.get(key, 0) + int(value)
    return _evaluation_result(state, len(corpus), session_batch_size, session_totals)


def decision_scale_point(
    codemap: CodeMap, corpus: list[dict[str, Any]], size: int
) -> dict[str, Any]:
    count = int(size)
    if count < 1 or count > len(corpus):
        raise ValueError("scale point outside corpus")
    result = evaluate(codemap, corpus[:count])
    total = float(result["decision_seconds"]["total"])
    return {
        "schema": "hashmarks.codemap-decision-scale-point.v1",
        "tasks": count,
        "total_seconds": total,
        "seconds_per_task": total / count,
        "p95_seconds": result["decision_seconds"]["p95"],
        "false_safe": result["false_safe"],
        "session": result["decision_session"],
        "phase_seconds": result["phase_seconds"],
    }


def decision_scale_ladder(
    codemap: CodeMap,
    corpus: list[dict[str, Any]],
    sizes: Iterable[int] = (1, 8, 16, 32, 64, 128),
) -> dict[str, Any]:
    rows = [
        decision_scale_point(codemap, corpus, int(size))
        for size in sizes
        if 1 <= int(size) <= len(corpus)
    ]
    return {
        "schema": "hashmarks.codemap-decision-scale-ladder.v1",
        "rows": rows,
        "execution_note": "scale points may be persisted independently; aggregation is identity checking, not retry/resume authority",
    }


def candidate_source_identity() -> str:
    root = Path(__file__).resolve().parents[1] / "hashmarks"
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def build_manifest(
    corpus: list[dict[str, Any]],
    *,
    repository_identity: str,
    generation: int,
    variant: str,
    group_size: int = 8,
    candidate_identity: str | None = None,
) -> dict[str, Any]:
    if group_size < 1:
        raise ValueError("group_size must be >= 1")
    canonical = json.dumps(corpus, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    corpus_sha = hashlib.sha256(canonical).hexdigest()
    task_ids = [
        str(
            item.get("id")
            or hashlib.sha256(str(item["task"]).encode()).hexdigest()[:16]
        )
        for item in corpus
    ]
    groups = [task_ids[i : i + group_size] for i in range(0, len(task_ids), group_size)]
    payload = {
        "corpus_sha256": corpus_sha,
        "repository_identity": repository_identity,
        "codemap_generation": generation,
        "candidate_identity": candidate_identity or candidate_source_identity(),
        "scorer_schema": "hashmarks.codemap-calibration-scorer.v2",
        "variant": variant,
        "group_size": group_size,
        "groups": groups,
    }
    manifest_sha = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema": "hashmarks.codemap-calibration-manifest.v1",
        **payload,
        "manifest_sha256": manifest_sha,
        "complete": False,
    }


def corpus_group(
    corpus: list[dict[str, Any]], manifest: dict[str, Any], group_index: int
) -> list[dict[str, Any]]:
    groups = manifest.get("groups")
    if not isinstance(groups, list) or not (0 <= group_index < len(groups)):
        raise ValueError("group_index outside calibration manifest")
    wanted = {str(v) for v in groups[group_index]}
    rows = [
        item
        for item in corpus
        if str(
            item.get("id")
            or hashlib.sha256(str(item["task"]).encode()).hexdigest()[:16]
        )
        in wanted
    ]
    if len(rows) != len(wanted):
        raise ValueError("calibration manifest task identity mismatch")
    return rows


def evaluate_existing_group(
    workspace: Path,
    corpus_path: Path,
    state_dir: Path,
    artifact_db: Path,
    options: ExistingGroupOptions = ExistingGroupOptions(),
) -> dict[str, Any]:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    if not isinstance(corpus, list):
        raise ValueError("corpus must be a JSON list")
    with CodeMap(workspace, state_dir=state_dir, artifact_db=artifact_db) as codemap:
        generation = codemap.store.generation()
        repository_identity = codemap._repository_packet_identity()
        manifest = build_manifest(
            corpus,
            repository_identity=repository_identity,
            generation=generation,
            variant=options.variant,
            group_size=options.group_size,
        )
        if options.manifest_path is not None:
            if options.manifest_path.exists():
                existing = json.loads(options.manifest_path.read_text(encoding="utf-8"))
                if existing.get("manifest_sha256") != manifest["manifest_sha256"]:
                    raise ValueError("existing calibration manifest identity mismatch")
                manifest = existing
            else:
                _atomic_write_json(options.manifest_path, manifest)
        rows = corpus_group(corpus, manifest, options.group_index)
        receipt_dir = (
            options.manifest_path.parent / (options.manifest_path.stem + "-receipts")
            if options.manifest_path is not None
            else None
        )
        decision = (
            evaluate_resumable(
                codemap,
                rows,
                receipt_dir=receipt_dir,
                manifest_sha256=manifest["manifest_sha256"],
                group_index=options.group_index,
                expected_task_ids=manifest["groups"][options.group_index],
            )
            if receipt_dir is not None
            else evaluate(codemap, rows)
        )
    return {
        "schema": "hashmarks.codemap-calibration-group.v1",
        "manifest_sha256": manifest["manifest_sha256"],
        "group_index": options.group_index,
        "group_count": len(manifest["groups"]),
        "task_ids": list(manifest["groups"][options.group_index]),
        "complete": True,
        "decision": decision,
    }


def scale_point_from_group_results(
    manifest: dict[str, Any], groups: list[dict[str, Any]], task_count: int
) -> dict[str, Any]:
    if task_count < 1:
        raise ValueError("task_count must be >= 1")
    ordered = sorted(groups, key=lambda row: int(row.get("group_index", -1)))
    selected: list[dict[str, Any]] = []
    tasks = 0
    for row in ordered:
        if (
            row.get("manifest_sha256") != manifest.get("manifest_sha256")
            or row.get("complete") is not True
        ):
            raise ValueError("scale point requires complete identity-matched groups")
        decision = row.get("decision") or {}
        count = int(decision.get("tasks", 0))
        if tasks + count > task_count:
            break
        selected.append(row)
        tasks += count
        if tasks == task_count:
            break
    if tasks != task_count:
        raise ValueError(
            "task_count must align with available completed group boundaries"
        )
    totals = [
        float((row["decision"].get("decision_seconds") or {}).get("total", 0.0))
        for row in selected
    ]
    p95s = [
        float((row["decision"].get("decision_seconds") or {}).get("p95", 0.0))
        for row in selected
    ]
    false_safe = sum(int(row["decision"].get("false_safe", 0)) for row in selected)
    total = sum(totals)
    return {
        "schema": "hashmarks.codemap-decision-scale-point.v1",
        "tasks": tasks,
        "groups": [int(row["group_index"]) for row in selected],
        "total_seconds": total,
        "seconds_per_task": total / tasks,
        "p95_group_task_seconds": max(p95s, default=0.0),
        "false_safe": false_safe,
        "aggregation": "identity-matched-completed-groups",
    }


def aggregate_group_results(
    manifest: dict[str, Any], groups: list[dict[str, Any]]
) -> dict[str, Any]:
    expected = len(manifest.get("groups") or [])
    by_index: dict[int, dict[str, Any]] = {}
    for row in groups:
        if row.get("manifest_sha256") != manifest.get("manifest_sha256"):
            raise ValueError("group result manifest identity mismatch")
        index = int(row.get("group_index", -1))
        if index in by_index:
            raise ValueError("duplicate calibration group result")
        by_index[index] = row
    completed = sorted(
        index for index, row in by_index.items() if row.get("complete") is True
    )
    return {
        "schema": "hashmarks.codemap-calibration-aggregate.v1",
        "manifest_sha256": manifest.get("manifest_sha256"),
        "completed_groups": completed,
        "completed": len(completed),
        "expected": expected,
        "complete": completed == list(range(expected)),
        "missing_groups": [
            index for index in range(expected) if index not in completed
        ],
        "tasks_completed": sum(
            int((by_index[index].get("decision") or {}).get("tasks", 0))
            for index in completed
        ),
    }


def _build_baseline(
    workspace: Path, output_dir: Path, corpus: list[dict[str, Any]]
) -> _BaselineCalibration:
    state_dir = output_dir / "state-full"
    artifact_db = output_dir / "artifacts.sqlite3"
    shutil.rmtree(state_dir, ignore_errors=True)
    started = time.perf_counter()
    with CodeMap(workspace, state_dir=state_dir, artifact_db=artifact_db) as codemap:
        preflight = codemap.index_preflight()
        sync = codemap.sync()
        decision = evaluate(codemap, corpus)
    cold_seconds = time.perf_counter() - started
    database = state_dir / "codemap.sqlite3"
    _checkpoint(database)
    return _BaselineCalibration(
        state_dir=state_dir,
        artifact_db=artifact_db,
        preflight=preflight,
        sync_economics=sync.economics,
        decision=decision,
        cold_seconds=cold_seconds,
        lexical_rows=_lexical_rows(database),
        database_bytes=_db_bytes(database),
    )


def run(
    workspace: Path,
    corpus_path: Path,
    output_dir: Path,
    variants: list[str],
    surfaces: set[str],
) -> dict[str, Any]:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    if not isinstance(corpus, list) or not all(
        isinstance(item, dict) and item.get("task") for item in corpus
    ):
        raise ValueError("corpus must be a JSON list of task objects")
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline = _build_baseline(workspace, output_dir, corpus)
    results: dict[str, Any] = {}
    for variant in variants:
        if variant == "full":
            state = baseline.state_dir
            transform = {
                "variant": "full",
                "selected_surfaces": sorted(surfaces),
                "changed_paths": 0,
            }
        else:
            state = output_dir / f"state-{variant}"
            shutil.rmtree(state, ignore_errors=True)
            shutil.copytree(baseline.state_dir, state)
            transform = apply_variant(
                state / "codemap.sqlite3", variant, surfaces=surfaces
            )
        with CodeMap(
            workspace, state_dir=state, artifact_db=baseline.artifact_db
        ) as codemap:
            decision = (
                baseline.decision if variant == "full" else evaluate(codemap, corpus)
            )
        rows = _lexical_rows(state / "codemap.sqlite3")
        bytes_ = _db_bytes(state / "codemap.sqlite3")
        results[variant] = {
            "transform": transform,
            "lexical_rows": rows,
            "lexical_rows_vs_full": rows / baseline.lexical_rows
            if baseline.lexical_rows
            else None,
            "workspace_map_bytes": bytes_,
            "workspace_map_bytes_vs_full": bytes_ / baseline.database_bytes
            if baseline.database_bytes
            else None,
            "decision": decision,
        }
    full_decision = results["full"]["decision"]
    for _name, result in results.items():
        decision = result["decision"]
        result["delta_vs_full"] = {
            "exact_edit": decision["exact_edit"] - full_decision["exact_edit"],
            "exact_verify": decision["exact_verify"] - full_decision["exact_verify"],
            "false_safe": decision["false_safe"] - full_decision["false_safe"],
            "discrimination_needed": decision["discrimination_needed"]
            - full_decision["discrimination_needed"],
        }
    return {
        "schema": "hashmarks.codemap-realworld-surface-calibration.v1",
        "workspace": str(workspace),
        "corpus": str(corpus_path),
        "surfaces": sorted(surfaces),
        "preflight": baseline.preflight,
        "cold_build_seconds": baseline.cold_seconds,
        "sync_economics": baseline.sync_economics,
        "variants": results,
        "acceptance_rule": "zero new false-safe decisions; economics changes are evidence only until this holds on frozen real-world corpora",
        "execution_policy": None,
        "retry_policy": None,
        "timeout_policy": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare CodeMap lexical-surface representations on a frozen real-world task corpus"
    )
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--variant",
        action="append",
        choices=("full", "membership", "cap4"),
        dest="variants",
    )
    parser.add_argument("--surface", action="append", dest="surfaces")
    parser.add_argument("--json-out")
    parser.add_argument("--existing-state")
    parser.add_argument("--artifact-db")
    parser.add_argument("--group-size", type=int, default=8)
    parser.add_argument("--group-index", type=int)
    parser.add_argument("--manifest-out")
    args = parser.parse_args()
    variants = args.variants or ["full", "membership", "cap4"]
    if "full" not in variants:
        variants.insert(0, "full")
    if args.existing_state is not None or args.group_index is not None:
        if args.existing_state is None or args.group_index is None:
            raise SystemExit(
                "--existing-state and --group-index must be supplied together"
            )
        artifact_db = (
            Path(args.artifact_db)
            if args.artifact_db
            else Path(args.output_dir) / "artifacts.sqlite3"
        )
        result = evaluate_existing_group(
            Path(args.workspace),
            Path(args.corpus),
            Path(args.existing_state),
            artifact_db,
            ExistingGroupOptions(
                variant=variants[0],
                group_size=args.group_size,
                group_index=args.group_index,
                manifest_path=Path(args.manifest_out) if args.manifest_out else None,
            ),
        )
    else:
        result = run(
            Path(args.workspace),
            Path(args.corpus),
            Path(args.output_dir),
            variants,
            set(args.surfaces or EXPENSIVE_SURFACES),
        )
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.json_out:
        _atomic_write_json(Path(args.json_out), result)
    log_command_output(logger, text, end="")


if __name__ == "__main__":
    main()
