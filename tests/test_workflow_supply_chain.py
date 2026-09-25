from __future__ import annotations

import re
import tomllib
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


def _publish_workflow_text() -> str:
    return (_root() / ".github" / "workflows" / "publish.yml").read_text(
        encoding="utf-8"
    )


def test_publish_workflow_binds_reviewed_request_to_exact_source() -> None:
    text = _publish_workflow_text()
    assert "branches: [main]" in text
    assert '".github/release-request.toml"' in text
    assert "workflow_dispatch:" in text
    assert "source_sha:" in text
    assert "Optional exact reviewed source SHA" in text
    assert "Checkout reviewed release request" in text
    assert "Resolve reviewed release request" in text
    assert 'set(request) - {"version", "source_sha"}' in text
    assert 'request.get("source_sha", "")' in text
    assert "DISPATCH_SOURCE_SHA:" in text
    assert "TRIGGER_SOURCE_SHA:" in text
    assert "dispatch_source or request_source or trigger_source" in text
    assert "Checkout exact release source" in text
    assert "source_sha: ${{ steps.release.outputs.source_sha }}" in text
    assert "ref: ${{ steps.request.outputs.source_sha }}" in text
    assert "ref: ${{ needs.prepare.outputs.source_sha }}" in text
    assert "git merge-base --is-ancestor" in text
    assert "Materialize locked lint toolchain" in text
    assert (
        "UV_PROJECT_ENVIRONMENT=.ruff-venv uv sync --frozen --only-group lint" in text
    )
    assert "release:\n    types: [published]" not in text
    assert "release publication is authorized only from main" in text


def test_publish_job_separates_release_machinery_from_source_bytes() -> None:
    text = _publish_workflow_text()
    publish = text.split("  publish:\n", 1)[1]

    assert "Checkout release machinery" in publish
    assert "ref: ${{ github.sha }}" in publish
    assert "path: workflow" in publish
    assert "Checkout exact release source" in publish
    assert "ref: ${{ needs.prepare.outputs.source_sha }}" in publish
    assert "path: source" in publish
    assert "python3 workflow/scripts/release_contract.py verify" in publish
    assert "--root source" in publish
    assert 'pathlib.Path("source/CHANGELOG.md")' in publish
    assert 'git -C source rev-list -n 1 "$RELEASE_TAG"' in publish
    assert "GH_REPO: ${{ github.repository }}" in publish


def test_publish_workflow_publishes_only_verified_github_release_assets() -> None:
    text = _publish_workflow_text()
    assert "Publish exact qualified bytes to GitHub Release" in text
    assert "gh release create" in text
    assert '--target "${{ needs.prepare.outputs.source_sha }}"' in text
    assert "--notes-file release/release-notes.md" in text
    assert "--generate-notes" not in text
    assert 'git -C source rev-list -n 1 "$RELEASE_TAG"' in text
    assert 'if [ "$tag_commit" != "${{ needs.prepare.outputs.source_sha }}" ]' in text
    assert "Materialize reviewed changelog section as release notes" in text
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


def test_release_request_is_a_minimal_auditable_version_trigger() -> None:
    request = tomllib.loads(
        (_root() / ".github" / "release-request.toml").read_text(encoding="utf-8")
    )

    assert "version" in request
    assert set(request) <= {"version", "source_sha"}
    version = request["version"]
    assert isinstance(version, str)
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version)

    source_sha = request.get("source_sha")
    if source_sha is not None:
        assert isinstance(source_sha, str)
        assert re.fullmatch(r"[0-9a-f]{40}", source_sha)


def test_ci_standalone_installs_exact_frozen_artifact_through_public_installer() -> (
    None
):
    text = (_root() / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    standalone = text.split("  standalone-artifact:\n", 1)[1].split(
        "\n  precommit:\n",
        1,
    )[0]

    assert "Install exact standalone through public installer" in standalone
    assert 'HASHMARKS_DOWNLOAD_BASE_URL="file://$bundle"' in standalone
    assert 'HASHMARKS_INSTALL_DIR="$target"' in standalone
    assert 'HASHMARKS_VERSION="$version"' in standalone
    assert (
        'test "$("$target/hashmarks" --version)" = "hashmarks version $version"'
        in standalone
    )


def test_publish_standalone_binds_installer_and_asset_to_release_version() -> None:
    text = _publish_workflow_text()
    standalone = text.split("  standalone:\n", 1)[1].split("\n  publish:\n", 1)[0]
    publish = text.split("  publish:\n", 1)[1]

    assert "Install exact standalone through public installer" in standalone
    assert 'HASHMARKS_VERSION="$RELEASE_VERSION"' in standalone
    assert (
        'test "$(./dist/hashmarks --version)" = "hashmarks version $RELEASE_VERSION"'
        in standalone
    )
    assert (
        'test "$("$target/hashmarks" --version)" = '
        '"hashmarks version $RELEASE_VERSION"' in standalone
    )
    assert 'test "$(release/standalone/hashmarks-linux-x86_64 --version)" =' in publish
    assert '"hashmarks version $RELEASE_VERSION"' in publish


def test_release_profile_installs_mcp_before_full_native_qualification() -> None:
    text = (_root() / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release_job = text.split("  release-environment:\n", 1)[1].split(
        "\n  python-support:\n",
        1,
    )[0]

    assert "uv sync --frozen --group test --extra mcp --python 3.14" in release_job
    assert release_job.index("--extra mcp") < release_job.index("make test-profile")


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
