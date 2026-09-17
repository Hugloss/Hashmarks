from __future__ import annotations

from pathlib import Path

from hashmarks.codemap.model import EvidenceVisibility
from hashmarks.codemap.policy import ContextPolicy


def test_builtin_secret_detection_covers_root_nested_and_windows_paths() -> None:
    policy = ContextPolicy()
    secret_paths = (
        ".env",
        ".env.local",
        "a/.env",
        "a/b/.env.production",
        "cert.pem",
        "a/cert.pem",
        "private.key",
        "a/b/private.key",
        "archive.p12",
        "a/archive.pfx",
        ".npmrc",
        "a/.npmrc",
        ".pypirc",
        "a/.pypirc",
        "id_rsa",
        "a/id_rsa",
        "id_ed25519",
        "a/id_ed25519",
        r"a\b\.env",
        r"a\b\cert.pem",
    )
    for relpath in secret_paths:
        decision = policy.decide(relpath)
        assert decision.index is False, relpath
        assert decision.evidence_visibility is EvidenceVisibility.DENY, relpath
        assert decision.reason == "secret-like path", relpath


def test_builtin_secret_detection_does_not_expand_policy() -> None:
    policy = ContextPolicy()
    visible_paths = (
        ".environment",
        "foo.env",
        "cert.PEM",
        "key.txt",
        "pem",
        "foo.pem.txt",
        "id_rsa.pub",
        "id_ed25519.pub",
        "src/normal.py",
        r"a\b\normal.py",
    )
    for relpath in visible_paths:
        decision = policy.decide(relpath)
        assert decision.index is True, relpath
        assert decision.evidence_visibility is EvidenceVisibility.SOURCE, relpath
        assert decision.reason is None, relpath


def test_custom_policy_rules_keep_original_glob_semantics(tmp_path: Path) -> None:
    config = tmp_path / ".hashmarks-context.toml"
    config.write_text(
        "[[rule]]\npattern = 'generated/**'\nindex = false\n"
        "[[rule]]\npattern = '**/*.snap'\nvisibility = 'outline'\n",
        encoding="utf-8",
    )
    policy = ContextPolicy.load(tmp_path)

    denied = policy.decide("generated/deep/value.py")
    assert denied.index is False
    assert denied.evidence_visibility is EvidenceVisibility.DENY

    metadata = policy.decide("tests/deep/value.snap")
    assert metadata.index is True
    assert metadata.evidence_visibility is EvidenceVisibility.OUTLINE
