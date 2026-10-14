"""Acquire real, finite upstream failure specimens for development qualification.

This QA producer runs two caller-selected SQLAlchemy examples against admitted
source archives. Hashmarks product code never imports it or executes a scenario.
Captured outcomes belong to this external producer, not repository authority.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, cast

from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.test_shards import repository_content_identity

from .backend_corpus import SUITE_PATH, load_corpus
from .common import write_json

SCENARIOS = {
    "sqlalchemy-logging-token-reset": "logging-token-reset",
    "sqlalchemy-aggregate-strings": "aggregate-strings",
}
_CHILD = (
    "import json,sys; from pathlib import Path; "
    "from scripts.repository_evaluation.capture_backend_failure import capture_scenario; "
    "print(json.dumps(capture_scenario(Path(sys.argv[1]),sys.argv[2]),ensure_ascii=False))"
)


def _logging_reset(sqlalchemy: object) -> dict[str, object]:
    engine = sqlalchemy.create_engine("sqlite://")
    try:
        with engine.connect() as connection:
            connection.execution_options(logging_token="first")
            connection.execution_options(logging_token=None)
            connection.execution_options(logging_token=None)
            return {
                "select_value": connection.execute(sqlalchemy.text("select 1")).scalar()
            }
    finally:
        engine.dispose()


def _aggregate_strings(sqlalchemy: object) -> dict[str, object]:
    compiler = cast("Any", importlib.import_module("sqlalchemy.sql.compiler"))
    dialect = cast("Any", importlib.import_module("sqlalchemy.engine.default"))
    statement = sqlalchemy.select(
        sqlalchemy.func.aggregate_strings(sqlalchemy.column("data"), ",")
    )
    return {
        "compiled_sql": str(compiler.SQLCompiler(dialect.DefaultDialect(), statement))
    }


def _repository_frames(
    exc: Exception, root: Path
) -> tuple[list[dict[str, object]], int]:
    frames: list[dict[str, object]] = []
    excluded = 0
    for frame, line in traceback.walk_tb(exc.__traceback__):
        path = Path(frame.f_code.co_filename).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            excluded += 1
            continue
        frames.append(
            {
                "path": path.relative_to(root).as_posix(),
                "line": line,
                "name": frame.f_code.co_name,
                "qualname": frame.f_code.co_qualname,
                "code_first_line": frame.f_code.co_firstlineno,
                "source_revision": hash_file(path, domain=FILE_DOMAIN).hash,
                "authority": "external-runtime-producer-claim",
            }
        )
    return frames, excluded


def capture_scenario(root: Path, scenario: str) -> dict[str, object]:
    """Record actual exceptions and stack frames, without choosing a repair."""
    examples = {
        "logging-token-reset": _logging_reset,
        "aggregate-strings": _aggregate_strings,
    }
    if scenario not in examples:
        raise ValueError("unsupported backend failure specimen")
    root = root.resolve()
    sqlalchemy = cast("Any", importlib.import_module("sqlalchemy"))
    if not Path(sqlalchemy.__file__).resolve().is_relative_to(root / "lib"):
        raise ValueError(
            "runtime did not import the explicitly selected source archive"
        )
    result: dict[str, object] = {
        "schema": "hashmarks.backend-runtime-failure-capture.v1",
        "scenario": scenario,
        "source_identity": repository_content_identity(root),
        "python_version": sys.version,
        "python_executable_sha256": hashlib.sha256(
            Path(sys.executable).read_bytes()
        ).hexdigest(),
        "producer_implementation_identity": "sha256:"
        + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_package_version": sqlalchemy.__version__,
        "scope": "one invocation; captured repository frames only",
        "authority": "external-runtime-producer-claim",
        "repository_negative_evidence": "not-admissible",
    }
    try:
        value = examples[scenario](sqlalchemy)
    except Exception as exc:
        frames, excluded = _repository_frames(exc, root)
        result.update(
            {
                "exception": {
                    "type": f"{type(exc).__module__}.{type(exc).__qualname__}",
                    "message": str(exc),
                },
                "frames": frames,
                "excluded_frame_count": excluded,
                "traceback": traceback.format_exc(),
            }
        )
    else:
        result.update(
            {"exception": None, "frames": [], "excluded_frame_count": 0, "value": value}
        )
    if repository_content_identity(root) != result["source_identity"]:
        raise ValueError("runtime source archive changed during acquisition")
    return result


def acquire_failure_capture(source: Path, scenario: str) -> dict[str, object]:
    """Use a fresh interpreter so before/after imports cannot contaminate each other."""
    completed = subprocess.run(
        [sys.executable, "-c", _CHILD, str(source.resolve()), scenario],
        env={
            **os.environ,
            "PYTHONPATH": str(source.resolve() / "lib"),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        raise ValueError(
            f"backend failure acquisition incomplete: {completed.stderr[-2000:]}"
        )
    return json.loads(completed.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources-file", type=Path, required=True)
    parser.add_argument("--workflow", choices=tuple(SCENARIOS), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    sources = {
        name: Path(path)
        for name, path in json.loads(args.sources_file.read_text()).items()
    }
    suite, _ = load_corpus(SUITE_PATH, sources)
    workflow = next(row for row in suite["workflows"] if row["id"] == args.workflow)
    for stage in ("before", "after"):
        capture = acquire_failure_capture(
            sources[workflow[stage]], SCENARIOS[args.workflow]
        )
        capture.update({"workflow": args.workflow, "stage": stage})
        write_json(args.output_dir / f"{stage}.json", capture)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
