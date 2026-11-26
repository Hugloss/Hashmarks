import os
import stat
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks import CodeMap


def test_non_file_manifest_does_not_support_a_python_verification_nomination(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    test = "tests/test_demo.py"
    (root / test).write_text("def test_demo(): pass\n")
    manifest = root / "pyproject.toml"
    manifest.mkdir()
    with CodeMap(root, state_dir=tmp_path / "state") as repository:
        repository.index.sync()
        observation = repository.source.observe("pyproject.toml", literal="pytest")
        member = assert_object(observation["member"])
        assert (member["state"], member["reason"]) == (
            "unsupported",
            "member-not-regular-file",
        )
        assert observation["observed_match_count"] is None
        assert observation["negative_evidence"] == "not-admissible"
        nomination = repository.verification.nomination(test)
        assert (
            nomination["available"] is False
            and nomination["reason"] == "source-evidence-unqualified"
        )

        manifest.rmdir()
        absent = repository.verification.nomination(test)
        assert absent["available"] is True
        assert {"path": "pyproject.toml", "state": "known-absent"} in assert_records(
            absent["supporting_source_members"]
        )
        manifest.write_text("[tool.pytest.ini_options]\n")
        present = repository.verification.nomination(test)
        assert present["available"] is True
        assert any(
            m["path"] == "pyproject.toml" and m["state"] == "known-present"
            for m in assert_records(present["supporting_source_members"])
        )


@pytest.mark.parametrize("probe", ["admission", "metadata"])
def test_unavailable_member_probe_preserves_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, probe: str
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    member = root / "owner.py"
    member.write_text("OWNER = True\n")
    with CodeMap(root, state_dir=tmp_path / "state") as repository:
        repository.index.sync()
        if probe == "metadata":
            lstat = Path.lstat

            def denied(path: Path) -> os.stat_result:
                if path == member:
                    raise PermissionError("cannot inspect member")
                return lstat(path)

            monkeypatch.setattr(Path, "lstat", denied)
        else:

            def failed_admission(rel: str) -> bool:
                raise OSError(f"cannot inspect admission for {rel}")

            monkeypatch.setattr(
                repository.source.files, "is_admitted", failed_admission
            )
        observed, raw = repository.source.member("owner.py", include_bytes=True)
        assert observed["state"] == "unknown" and raw is None
        receipt = repository.source.range_receipt("owner.py", start_byte=0, end_byte=1)
        assert assert_object(receipt["member"])["state"] == "unknown"
        assert (
            receipt["content"] is None
            and receipt["negative_evidence"] == "not-admissible"
        )


@pytest.mark.skipif(
    os.name != "posix", reason="Requires POSIX directory search permissions"
)
def test_inaccessible_parent_is_unknown_until_it_can_be_observed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    parent = root / "private"
    parent.mkdir(parents=True)
    rel = "private/owner.py"
    (root / rel).write_text("OWNER = True\n")
    with CodeMap(root, state_dir=tmp_path / "state") as repository:
        repository.index.sync()
        mode = stat.S_IMODE(parent.stat().st_mode)
        try:
            parent.chmod(0)
            if os.access(parent, os.X_OK):
                pytest.skip("Process can traverse mode-000 directories")
            inaccessible = repository.source.observe(rel, literal="OWNER")
            assert assert_object(inaccessible["member"])["state"] == "unknown"
            assert inaccessible["observed_match_count"] is None
        finally:
            parent.chmod(mode)
        assert (
            repository.source.observe(rel, literal="OWNER")["observed_match_count"] == 1
        )
