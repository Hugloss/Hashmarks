import sys
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_records

from hashmarks import CodeMap


def test_grep_applies_source_visibility_before_its_candidate_bound(
    tmp_path: Path,
) -> None:
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "a_hidden.py"\nvisibility = "deny"\n'
        '[[rule]]\npattern = "b_outline.py"\nvisibility = "outline"\n'
    )
    (tmp_path / "a_hidden.py").write_text("# account_flag\n" * 51)
    (tmp_path / "b_outline.py").write_text("# account_flag\n" * 50)
    (tmp_path / "z_visible.py").write_text("account_flag = True\n")
    with CodeMap(tmp_path) as repository:
        result = repository.source.grep("account_flag", limit=1)
    assert result["omissions"] == []
    assert result["negative_evidence"] == "not-admissible"
    (only,) = assert_records(result["matches"])
    assert (only["path"], only["line"], only["content"]) == (
        "z_visible.py",
        1,
        "account_flag = True",
    )


def test_grep_uses_one_qualified_capture_per_member_and_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lines = (
        ["# header"] + [f'value_{i} = "retry_count"' for i in range(32)] + ["# tail"]
    )
    first = tmp_path / "a.py"
    first.write_text("\r\n".join(lines) + "\r\n")
    (tmp_path / "b.py").write_text("retry_count = 1\n")
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        member = repository.source.member
        reads: list[str] = []

        def capture(
            path: str, *, include_bytes: bool = False, max_bytes: int | None = None
        ) -> tuple[dict[str, object], bytes | None]:
            if include_bytes:
                reads.append(path)
            return member(path, include_bytes=include_bytes, max_bytes=max_bytes)

        monkeypatch.setattr(repository.source, "member", capture)
        packet = repository.source.grep("retry_count", limit=33, context_lines=1)
        hits = assert_records(packet["matches"])
        assert reads == ["a.py", "b.py"]
        assert [(h["path"], h["line"]) for h in hits] == [
            *(("a.py", line) for line in range(2, 34)),
            ("b.py", 1),
        ]
        assert hits[0]["range"] == [1, 3] and hits[0]["content"] == "\n".join(lines[:3])
        assert packet["omissions"] == []
        first.write_text('retry_count = "new"\n')
        repository.index.sync(["a.py"])
        reads.clear()
        current = repository.source.grep("retry_count", limit=1)
        assert reads == ["a.py", "b.py"]
        assert assert_records(current["matches"])[0]["content"] == 'retry_count = "new"'
        assert current["omissions"] == ["result-limit"]


def test_grep_qualifies_a_candidate_that_disappears_before_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = tmp_path / "transient.py"
    candidate.write_text("token_name = 1\n")
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        member = repository.source.member

        def disappear(
            path: str, *, include_bytes: bool = False, max_bytes: int | None = None
        ) -> tuple[dict[str, object], bytes | None]:
            candidate.unlink()
            return member(path, include_bytes=include_bytes, max_bytes=max_bytes)

        monkeypatch.setattr(repository.source, "member", disappear)
        result = repository.source.grep("token_name")
    assert result["matches"] == []
    assert result["omissions"] == ["source-unavailable"]
    assert result["negative_evidence"] == "not-admissible"


@pytest.mark.parametrize("count", [100, 101])
def test_grep_reports_candidate_and_result_cuts_separately(
    tmp_path: Path, count: int
) -> None:
    (tmp_path / "module.py").write_text("# token_name\n" * count)
    with CodeMap(tmp_path) as repository:
        result = repository.source.grep("token_name", limit=1)
        assert len(assert_records(result["matches"])) == 1
        assert result["omissions"] == (
            ["lexical-candidate-limit", "result-limit"]
            if count > 100
            else ["result-limit"]
        )
        assert repository.source.grep("!")["omissions"] == ["no-indexed-query-terms"]
        assert (
            repository.source.grep("unseen_name")["negative_evidence"]
            == "not-admissible"
        )
        zero = repository.source.grep("token_name", limit=0)
        assert zero["matches"] == [] and "result-limit" in assert_array(
            zero["omissions"]
        )
        assert (
            len(
                assert_records(
                    repository.source.grep("token_name", limit=sys.maxsize)["matches"]
                )
            )
            == count
        )
        with pytest.raises(ValueError, match="nonnegative integer"):
            repository.source.grep("token_name", limit=-1)
