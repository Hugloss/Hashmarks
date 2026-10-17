"""Runtime producer specimens keep actual frame coordinates and declared scope."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest
from contract_assertions import assert_number, assert_records

from hashmarks.digest import FILE_DOMAIN, hash_file
from scripts.repository_evaluation.capture_backend_failure import (
    _DECLARATIVE_SPECIMENS,
    _captured_exception_chain,
    _declarative_specimen,
    _repository_frames,
)


def test_actual_trace_frames_keep_qualified_names_and_exclude_other_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "service.py"
    text = (
        "class Service:\n"
        "    def process(self):\n"
        "        raise ValueError('captured actual failure')\n"
    )
    source.write_text(text)
    namespace = {}
    exec(compile(text, str(source), "exec"), namespace)
    try:
        namespace["Service"]().process()
    except ValueError as exc:
        frames, excluded = _repository_frames(exc, tmp_path)
    else:
        raise AssertionError("fixture did not produce an exception")
    assert excluded >= 1
    assert len(frames) == 1
    assert frames[0] == {
        "path": "service.py",
        "line": 3,
        "name": "process",
        "qualname": "Service.process",
        "code_first_line": 2,
        "source_revision": hash_file(source, domain=FILE_DOMAIN).hash,
        "authority": "external-runtime-producer-claim",
    }


@pytest.mark.parametrize(
    ("cause", "expected_types"),
    [
        ("from error", ["builtins.LookupError", "builtins.ValueError"]),
        ("", ["builtins.LookupError", "builtins.ValueError"]),
        ("from None", ["builtins.ValueError"]),
    ],
)
def test_capture_retains_exact_displayed_exception_chain(
    tmp_path: Path, cause: str, expected_types: list[str]
) -> None:
    source = tmp_path / "service.py"
    source.write_text(
        "def inner():\n"
        '    raise LookupError("inner")\n'
        "def outer():\n"
        "    try:\n"
        "        inner()\n"
        "    except LookupError as error:\n"
        f'        raise ValueError("outer") {cause}\n'
        "outer()\n"
    )
    try:
        exec(compile(source.read_text(), str(source), "exec"), {})
    except ValueError as exc:
        capture = _captured_exception_chain(exc, tmp_path)
    else:
        raise AssertionError("fixture did not produce an exception")
    descriptions = assert_records(capture["exception_chain"])
    frames = assert_records(capture["frames"])
    assert [row["type"] for row in descriptions] == expected_types
    assert sum(assert_number(row["repository_frames"]) for row in descriptions) == len(
        frames
    )
    for index, row in enumerate(descriptions):
        members = [frame for frame in frames if frame["exception_chain_index"] == index]
        assert len(members) == row["repository_frames"]
        assert all(frame["exception_type"] == row["type"] for frame in members)
        assert [frame["name"] for frame in members] == (
            ["outer", "inner"]
            if row["type"] == "builtins.LookupError"
            else ["<module>", "outer"]
        )
        assert all(
            frame["source_revision"] == hash_file(source, domain=FILE_DOMAIN).hash
            for frame in members
        )


def test_exception_chain_cycle_does_not_repeat_members(tmp_path: Path) -> None:
    failure = ValueError("cycle")
    failure.__cause__ = failure
    capture = _captured_exception_chain(failure, tmp_path)
    assert [row["type"] for row in assert_records(capture["exception_chain"])] == [
        "builtins.ValueError"
    ]
    assert capture["frames"] == []


@pytest.mark.parametrize("fails", [False, True])
def test_native_annotation_specimen_keeps_future_flags_and_module_lifetime(
    monkeypatch: pytest.MonkeyPatch, fails: bool
) -> None:
    name = "_hashmarks_backend_failure_specimen"
    previous = ModuleType(name)
    monkeypatch.setitem(sys.modules, name, previous)
    source = (
        'def specimen(value: Missing): pass\nobservation = {"annotations": specimen.__annotations__}\n'
        if fails
        else 'import sys\nobservation = {"registered": __name__ in sys.modules}\n'
    )
    monkeypatch.setitem(_DECLARATIVE_SPECIMENS, "annotation-contract", source)
    if fails:
        with pytest.raises(NameError, match="Missing"):
            _declarative_specimen("annotation-contract")
    else:
        assert _declarative_specimen("annotation-contract") == {"registered": True}
    assert sys.modules[name] is previous
