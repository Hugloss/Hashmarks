from __future__ import annotations

import re
from pathlib import Path

_SHA_PIN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}(?:\s+#.*)?$")


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_external_github_actions_are_immutable_sha_pinned() -> None:
    workflows = sorted((_root() / ".github" / "workflows").glob("*.yml"))
    assert workflows
    offenders: list[str] = []
    for path in workflows:
        for line_no, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            stripped = line.strip()
            if not stripped.startswith("- uses:"):
                continue
            value = stripped.removeprefix("- uses:").strip()
            if value.startswith("./"):
                continue
            if not _SHA_PIN.fullmatch(value):
                offenders.append(f"{path.relative_to(_root())}:{line_no}: {value}")
    assert not offenders, "mutable/unpinned workflow actions:\n" + "\n".join(offenders)


def test_publish_workflow_uses_trusted_publishing_and_exact_artifact_handoff() -> None:
    text = (_root() / ".github" / "workflows" / "publish.yml").read_text(
        encoding="utf-8"
    )
    assert "types: [published]" in text
    assert "environment: pypi" in text
    assert "id-token: write" in text
    assert "PYPI_TOKEN" not in text
    assert "packages-dir: release/packages/" in text
    assert "release_contract.py manifest" in text
    assert "release_contract.py verify" in text
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in text
    assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in text
    assert (
        "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33" in text
    )


def test_ci_proves_exact_mcp_floor_and_latest_line_through_installed_wheel() -> None:
    text = (_root() / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert text.count('mcp: "mcp==2.2.0"') == 2
    assert 'mcp: "mcp>=2.2.0"' in text
    assert "mcp_installed_artifact_smoke.py" in text
    assert "uv build --wheel --out-dir dist" in text


def test_every_ci_and_publish_job_has_a_bounded_timeout() -> None:
    for name in ("ci.yml", "publish.yml"):
        text = (_root() / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert text.count("    runs-on: ubuntu-latest") == text.count(
            "    timeout-minutes:"
        )


def test_ci_checkout_does_not_persist_git_credentials() -> None:
    lines = (
        (_root() / ".github" / "workflows" / "ci.yml")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    checkout_indexes = [
        index
        for index, line in enumerate(lines)
        if "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in line
    ]
    assert checkout_indexes
    for index in checkout_indexes:
        assert any(
            "persist-credentials: false" in line
            for line in lines[index + 1 : index + 5]
        )
