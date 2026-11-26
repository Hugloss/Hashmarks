import os
from pathlib import Path

import pytest

from hashmarks import CodeMap
from hashmarks.codemap.model import EvidenceVisibility


@pytest.mark.parametrize("explicit", [False, True])
def test_dangling_policy_link_remains_unavailable_until_restored_or_removed(
    tmp_path: Path, explicit: bool
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "owner.py").write_bytes(b"owner = 1\n")
    target = root / "rules.toml"
    target.write_text('[[rule]]\npattern = "owner.py"\nvisibility = "deny"\n')
    entry = root / ("selected.toml" if explicit else ".hashmarks-context.toml")
    entry.symlink_to(target.name)
    with CodeMap(
        root, state_dir=tmp_path / "state", policy_path=entry.name if explicit else None
    ) as repository:
        member, raw = repository.source.member("owner.py", include_bytes=True)
        assert (member["reason"], raw) == ("repository-evidence-denied", None)
        target.unlink()
        member, raw = repository.source.member("owner.py", include_bytes=True)
        assert (member["state"], member["reason"], raw) == (
            "unknown",
            "repository-evidence-policy-unavailable",
            None,
        )
        observed = repository.source.observe("owner.py", literal="owner")
        assert observed["member"] == member
        assert (
            observed["observed_match_count"] is None
            and observed["negative_evidence"] == "not-admissible"
        )
        target.write_text('[[rule]]\npattern = "owner.py"\nvisibility = "outline"\n')
        member, raw = repository.source.member("owner.py", include_bytes=True)
        assert (member["reason"], raw) == ("source-evidence-not-visible", None)
        entry.unlink()
        member, raw = repository.source.member("owner.py", include_bytes=True)
        assert (member["state"], raw) == ("known-present", b"owner = 1\n")


def test_standalone_member_observes_new_denial_before_returning_bytes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "owner.py").write_bytes(b"owner = 1\n")
    with CodeMap(root, state_dir=tmp_path / "state") as repository:
        repository.index.sync()
        present, raw = repository.source.member("owner.py", include_bytes=True)
        assert present["state"] == "known-present" and raw == b"owner = 1\n"
        (root / ".hashmarks-context.toml").write_text(
            '[[rule]]\npattern = "owner.py"\nvisibility = "deny"\n'
        )
        for include_bytes in (True, False):
            member, raw = repository.source.member(
                "owner.py", include_bytes=include_bytes
            )
            assert (member["state"], member["reason"], raw) == (
                "unsupported",
                "repository-evidence-denied",
                None,
            )


@pytest.mark.skipif(
    os.name != "posix", reason="Requires POSIX directory search permissions"
)
def test_unreadable_configured_policy_stays_unknown_until_reobserved(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    config_dir = root / "config"
    config_dir.mkdir(parents=True)
    policy = config_dir / "observer.toml"
    policy.write_text('[[rule]]\npattern = "owner.py"\nvisibility = "outline"\n')
    (root / "owner.py").write_text("owner = 1\n")
    with CodeMap(root, state_dir=tmp_path / "state", policy_path=policy) as repository:
        repository.index.sync()
        assert (
            repository.files.decide("owner.py").evidence_visibility
            is EvidenceVisibility.OUTLINE
        )
        try:
            config_dir.chmod(0)
            if os.access(config_dir, os.X_OK):
                pytest.skip("Current account can still search this directory")
            for path in ("owner.py", "missing.py"):
                for include_bytes in (False, True):
                    member, raw = repository.source.member(
                        path, include_bytes=include_bytes
                    )
                    assert member == {
                        "path": path,
                        "state": "unknown",
                        "reason": "repository-evidence-policy-unavailable",
                    }
                    assert raw is None
                observed = repository.source.observe(path, literal="owner")
                assert observed["member"] == member
                assert (
                    observed["freshness"] == "unknown"
                    and observed["observed_match_count"] is None
                )
                assert observed["negative_evidence"] == "not-admissible"
            with pytest.raises(PermissionError):
                repository.files.refresh_policy()
            assert (
                repository.files.decide("owner.py").evidence_visibility
                is EvidenceVisibility.OUTLINE
            )
        finally:
            config_dir.chmod(0o700)
        recovered, raw = repository.source.member("owner.py", include_bytes=True)
        assert recovered["reason"] == "source-evidence-not-visible" and raw is None
        missing, raw = repository.source.member("missing.py", include_bytes=True)
        assert missing["state"] == "known-absent" and raw is None
