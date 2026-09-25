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


def test_publish_workflow_is_reviewed_request_driven_and_github_native() -> None:
    text = (_root() / ".github" / "workflows" / "publish.yml").read_text(
        encoding="utf-8"
    )
    assert 'branches: [main]' in text
    assert '".github/release-request.toml"' in text
    assert "workflow_dispatch:" in text
    assert "release:\n    types: [published]" not in text
    assert "Validate reviewed release request" in text
    assert "release publication is authorized only from main" in text
    assert "ref: ${{ github.sha }}" in text
    assert "Publish exact qualified bytes to GitHub Release" in text
    assert "gh release create" in text
    assert "--draft" in text
    assert 'gh release edit "$RELEASE_TAG" --draft=false' in text
    assert "gh release upload" in text
    assert "qualified-python-release-bundle" in text
    assert "qualified-standalone-release-bundle" in text
    assert "hashmarks-linux-x86_64.sha256" in text
    assert "sha256sum -c hashmarks-linux-x86_64.sha256" in text
    assert "environment: pypi" not in text
    assert "id-token: write" not in text
    assert "PYPI_TOKEN" not in text
    assert "pypa/gh-action-pypi-publish@" not in text


def test_every_ci_and_publish_job_has_a_bounded_timeout() -> None:
    job_heading = re.compile(r"(?m)^  ([A-Za-z0-9_-]+):\n")
    for name in ("ci.yml", "publish.yml"):
        text = (_root() / ".github" / "workflows" / name).read_text(encoding="utf-8")
        jobs = text.split("jobs:\n", 1)[1]
        matches = list(job_heading.finditer(jobs))
        assert matches
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(jobs)
            block = jobs[match.end() : end]
            assert "    runs-on:" in block, f"{name}:{match.group(1)} has no runner"
            assert "    timeout-minutes:" in block, (
                f"{name}:{match.group(1)} has no bounded timeout"
            )


def test_ci_checkout_does_not_persist_git_credentials() -> None:
    lines = (
        (_root() / ".github" / "workflows" / "ci.yml")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    checkout_indexes = [
        index for index, line in enumerate(lines) if "actions/checkout@" in line
    ]
    assert checkout_indexes
    for index in checkout_indexes:
        assert any(
            "persist-credentials: false" in line
            for line in lines[index + 1 : index + 5]
        )
