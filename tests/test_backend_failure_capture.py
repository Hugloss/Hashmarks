"""Runtime producer specimens keep actual frame coordinates and declared scope."""

from __future__ import annotations

from pathlib import Path

from hashmarks.digest import FILE_DOMAIN, hash_file
from scripts.repository_evaluation.capture_backend_failure import _repository_frames


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
