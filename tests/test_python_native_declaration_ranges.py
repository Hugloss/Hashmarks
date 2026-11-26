from pathlib import Path

from contract_assertions import assert_records

from hashmarks import CodeMap
from hashmarks.codemap.python_ast import estimate_tokens


def test_default_range_provider_keeps_native_python_occurrences(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = (
        b"# first physical line\r# second physical line\n"
        b"def upper(): return 'UPPER'\r\n"
        b"def lower(): return 'LOWER'\n"
        b"class Left:\n    def pick(self): return 'LEFT'\n"
        b"class Right:\n    def pick(self): return 'RIGHT'\n"
        b"    def pick(self): return 'LATER'\n"
    )
    (repo / "member.py").write_bytes(source)
    expected = {
        "upper": (3, "def upper(): return 'UPPER'"),
        "lower": (4, "def lower(): return 'LOWER'"),
        "Left.pick": (6, "    def pick(self): return 'LEFT'"),
        "Right.pick": (8, "    def pick(self): return 'RIGHT'"),
        "Right.pick@L9": (9, "    def pick(self): return 'LATER'"),
    }
    for _ in range(2):
        with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
            outline = assert_records(codemap.source.outline("member.py")["symbols"])
            assert {row["qualname"] for row in outline} == {"Left", "Right", *expected}
            for key, (line, body) in expected.items():
                evidence = codemap.source.read(f"member.py::{key}")
                assert evidence["lines"] == [line, line]
                assert evidence["content"] == body
                row = next(item for item in outline if item["qualname"] == key)
                assert row["body_tokens"] == estimate_tokens(body)
