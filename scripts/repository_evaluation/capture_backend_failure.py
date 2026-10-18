"""Acquire real, finite upstream failure specimens for development qualification.

This QA producer runs finite caller-selected SQLAlchemy examples against admitted
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
from contextlib import AbstractContextManager
from pathlib import Path
from types import ModuleType
from typing import Protocol, runtime_checkable

from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.producer_identity import native_producer_implementation_identity
from hashmarks.test_shards import repository_content_identity

from .backend_corpus import SUITE_PATH, load_corpus
from .common import evaluator_implementation_identity, write_json

SCENARIOS = {
    "sqlalchemy-logging-token-reset": "logging-token-reset",
    "sqlalchemy-aggregate-strings": "aggregate-strings",
    "sqlalchemy-custom-metadata-warning": "custom-metadata-warning",
    "sqlalchemy-forwardref-diagnostic": "forwardref-diagnostic",
}
_DECLARATIVE_SPECIMENS = {
    "custom-metadata-warning": """
import warnings
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase
custom_metadata = sa.MetaData()
class Base(DeclarativeBase):
    pass
with warnings.catch_warnings():
    warnings.simplefilter('error', sa.exc.SAWarning)
    class User(Base):
        __tablename__ = 'users'
        metadata = custom_metadata
        id = sa.Column(sa.Integer, primary_key=True)
observation = {'custom_metadata_retained': User.__table__.metadata is custom_metadata}
""",
    "forwardref-diagnostic": """
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
class Base(DeclarativeBase):
    pass
class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Bogus
observation = {'class_created': User.__name__}
""",
}
_CHILD = (
    "import json,sys; from pathlib import Path; "
    "from scripts.repository_evaluation.capture_backend_failure import capture_scenario; "
    "print(json.dumps(capture_scenario(Path(sys.argv[1]),sys.argv[2]),ensure_ascii=False))"
)


class _ScalarResult(Protocol):
    def scalar(self) -> object: ...


class _Connection(Protocol):
    def execution_options(self, *, logging_token: str | None) -> object: ...
    def execute(self, statement: object) -> _ScalarResult: ...


class _Engine(Protocol):
    def connect(self) -> AbstractContextManager[_Connection]: ...
    def dispose(self) -> None: ...


class _Functions(Protocol):
    def aggregate_strings(self, expression: object, delimiter: str) -> object: ...


@runtime_checkable
class _SqlAlchemy(Protocol):
    __file__: str
    __version__: str
    func: _Functions

    def create_engine(self, url: str) -> _Engine: ...
    def text(self, source: str) -> object: ...
    def column(self, name: str) -> object: ...
    def select(self, expression: object) -> object: ...


def _logging_reset(sqlalchemy: _SqlAlchemy) -> dict[str, object]:
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


def _aggregate_strings(sqlalchemy: _SqlAlchemy) -> dict[str, object]:
    statement = sqlalchemy.select(
        sqlalchemy.func.aggregate_strings(sqlalchemy.column("data"), ",")
    )
    # The upstream defect concerns str(statement), which selects its own string
    # compiler. A manually constructed DefaultDialect exercises another contract.
    return {"compiled_sql": str(statement)}


def _repository_frames(
    exc: BaseException, root: Path
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


def _captured_exception_chain(exc: BaseException, root: Path) -> dict[str, object]:
    """Retain every ordinary exception shown by Python's cause/context chain."""
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = (
            current.__cause__
            if current.__cause__ is not None
            else None
            if current.__suppress_context__
            else current.__context__
        )
    frames: list[dict[str, object]] = []
    descriptions: list[dict[str, object]] = []
    excluded = 0
    for index, member in enumerate(reversed(chain)):
        captured, dropped = _repository_frames(member, root)
        exception_type = f"{type(member).__module__}.{type(member).__qualname__}"
        for frame in captured:
            frame.update(exception_chain_index=index, exception_type=exception_type)
        frames.extend(captured)
        excluded += dropped
        descriptions.append(
            {
                "index": index,
                "type": exception_type,
                "message": str(member),
                "repository_frames": len(captured),
                "excluded_frames": dropped,
            }
        )
    return {
        "exception": {
            "type": f"{type(exc).__module__}.{type(exc).__qualname__}",
            "message": str(exc),
        },
        "exception_chain": descriptions,
        "frames": frames,
        "excluded_frame_count": excluded,
    }


def _declarative_specimen(scenario: str) -> dict[str, object]:
    module = ModuleType("_hashmarks_backend_failure_specimen")
    previous = sys.modules.get(module.__name__)
    sys.modules[module.__name__] = module
    try:
        # Python 3.14's unquoted annotations must not inherit this producer's
        # future-annotations flag. Registration supplies their real globals.
        code = compile(
            _DECLARATIVE_SPECIMENS[scenario],
            f"<hashmarks-backend-specimen:{scenario}>",
            "exec",
            dont_inherit=True,
        )
        exec(code, module.__dict__)
        value: object = module.__dict__.get("observation")
        if not isinstance(value, dict) or not all(
            isinstance(key, str) for key in value
        ):
            raise ValueError("backend specimen did not produce an observation")
        return value
    finally:
        if previous is None:
            sys.modules.pop(module.__name__, None)
        else:
            sys.modules[module.__name__] = previous


def capture_scenario(root: Path, scenario: str) -> dict[str, object]:
    """Record actual exceptions and stack frames, without choosing a repair."""
    examples = {
        "logging-token-reset": _logging_reset,
        "aggregate-strings": _aggregate_strings,
    }
    if scenario not in {*examples, *_DECLARATIVE_SPECIMENS}:
        raise ValueError("unsupported backend failure specimen")
    if scenario == "forwardref-diagnostic" and sys.version_info < (3, 14):
        raise ValueError("forwardref-diagnostic requires Python 3.14 or newer")
    root = root.resolve()
    sqlalchemy = importlib.import_module("sqlalchemy")
    if not isinstance(sqlalchemy, _SqlAlchemy):
        raise ValueError("selected source does not expose the scenario's package API")
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
        "observer_implementation_identity": native_producer_implementation_identity(
            Path(__file__).resolve().parents[2] / "hashmarks"
        ),
        "evaluator_implementation_identity": evaluator_implementation_identity(),
        "source_package_version": sqlalchemy.__version__,
        "scope": "one invocation; repository frames from the displayed exception chain",
        "authority": "external-runtime-producer-claim",
        "repository_negative_evidence": "not-admissible",
    }
    try:
        value = (
            _declarative_specimen(scenario)
            if scenario in _DECLARATIVE_SPECIMENS
            else examples[scenario](sqlalchemy)
        )
    except Exception as exc:
        result.update(_captured_exception_chain(exc, root))
        result["traceback"] = traceback.format_exc()
    else:
        result.update(
            {
                "exception": None,
                "exception_chain": [],
                "frames": [],
                "excluded_frame_count": 0,
                "value": value,
            }
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
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ValueError("backend failure capture must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources-file", type=Path, required=True)
    parser.add_argument("--suite", type=Path, default=SUITE_PATH)
    parser.add_argument("--workflow", choices=tuple(SCENARIOS), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    raw_sources = json.loads(args.sources_file.read_text())
    if not isinstance(raw_sources, dict) or not all(
        isinstance(name, str) and isinstance(path, str)
        for name, path in raw_sources.items()
    ):
        raise ValueError("sources file requires repository names and path strings")
    sources = {name: Path(path) for name, path in raw_sources.items()}
    suite, _ = load_corpus(args.suite, sources)
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
