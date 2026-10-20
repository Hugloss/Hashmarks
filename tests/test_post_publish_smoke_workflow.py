from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import textwrap
import zipfile
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from scripts.release_contract import (
    PUBLICATION_SCHEMA,
    publication_asset_names,
    release_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
TAG = "v1.2.3"
SOURCE = "a" * 40


def _sign_manifest(manifest: dict[str, Any]) -> None:
    payload = {
        key: value for key, value in manifest.items() if key != "manifest_identity"
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    manifest["manifest_identity"] = (
        "sha256:"
        + hashlib.sha256(
            manifest["schema"].encode() + b"\0" + encoded.encode()
        ).hexdigest()
    )


def _resolver_script() -> str:
    workflow = (ROOT / ".github/workflows/post-publish-smoke.yml").read_text()
    scripts = re.findall(
        r"(?ms)^          python3 - <<'PY'\n(.*?)^          PY$", workflow
    )
    return next(
        textwrap.dedent(script) for script in scripts if "GITHUB_OUTPUT" in script
    )


def _qualified_package(root: Path) -> dict[str, Any]:
    snapshot = root / "source-snapshot"
    snapshot.mkdir()
    project = '[project]\nname = "hashmarks"\nversion = "1.2.3"\n'
    (snapshot / "pyproject.toml").write_text(project)
    (snapshot / "uv.lock").write_text("version = 1\n")
    packages = root / "publish-artifact/packages"
    packages.mkdir()
    with zipfile.ZipFile(packages / "hashmarks-1.2.3-py3-none-any.whl", "w") as archive:
        archive.writestr(
            "hashmarks-1.2.3.dist-info/METADATA", "Name: hashmarks\nVersion: 1.2.3\n"
        )
    with tarfile.open(packages / "hashmarks-1.2.3.tar.gz", "w:gz") as archive:
        member = tarfile.TarInfo("hashmarks-1.2.3/pyproject.toml")
        member.size = len(project.encode())
        with io.BytesIO(project.encode()) as stream:
            archive.addfile(member, stream)
    return release_manifest(snapshot, packages, tag=TAG)


def _current_release_request(root: Path) -> None:
    authored = {
        ".github/release-request.toml": 'version = "1.2.3"\n',
        "pyproject.toml": '[project]\nname = "hashmarks"\nversion = "1.2.3"\n',
        "hashmarks/_version.py": '__version__ = "1.2.3"\n',
        "README.md": "Current package version: **1.2.3**.\n",
        "CHANGELOG.md": "# Changelog\n\n## 1.2.3 — Published\n\n- Fix repository observations.\n",
    }
    for name, content in authored.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


@pytest.fixture
def smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], Callable[[str], str]]:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_REPOSITORY", "Hugloss/Hashmarks")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "event.json"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output"))
    (tmp_path / "publish-artifact").mkdir()
    package = _qualified_package(tmp_path)
    (tmp_path / "publish-artifact/source.sha").write_text(SOURCE + "\n")
    _current_release_request(tmp_path)
    manifest: dict[str, Any] = {
        "schema": PUBLICATION_SCHEMA,
        "project": package["project"],
        "tag": TAG,
        "version": "1.2.3",
        "source": {"commit_sha": SOURCE},
        "distributions": deepcopy(package["distributions"]),
        "standalones": [],
        "installer_checksums": [],
        "bootstrap_installers": [],
        "package_qualification_identity": package["manifest_identity"],
        "qualification_dependency_resolution": deepcopy(
            package["qualification_dependency_resolution"]
        ),
        "publication_authority": package["publication_authority"],
    }
    _sign_manifest(manifest)
    state: dict[str, Any] = {
        "event": {"inputs": {"release_tag": TAG}, "release": {"tag_name": TAG}},
        "manifest": manifest,
        "package": package,
        "source": SOURCE,
        "calls": [],
        "release": {
            "tag_name": TAG,
            "draft": False,
            "prerelease": False,
            "published_at": "2026-10-20T12:00:00Z",
            "target_commitish": SOURCE,
            "assets": publication_asset_names(manifest),
        },
    }

    def check_output(command: list[str], *, text: bool) -> str:
        assert text is True
        state["calls"].append(command)
        if command[:2] == ["gh", "api"]:
            assert command[2] == f"repos/Hugloss/Hashmarks/releases/tags/{TAG}"
            return json.dumps(state["release"])
        assert command == ["git", "rev-parse", "FETCH_HEAD^{commit}"]
        return state["source"] + "\n"

    def check_call(command: list[str]) -> int:
        state["calls"].append(command)
        if command[:3] == ["gh", "release", "download"]:
            assert command[3] == TAG
            directory = tmp_path / command[command.index("--dir") + 1]
            directory.mkdir()
            (directory / "release-manifest.json").write_text(
                json.dumps(state["manifest"])
            )
        elif command[:2] == ["git", "fetch"]:
            assert command == [
                "git",
                "fetch",
                "--no-tags",
                "--depth=1",
                "origin",
                f"refs/tags/{TAG}",
            ]
        elif command[:3] == ["git", "worktree", "add"]:
            assert command == [
                "git",
                "worktree",
                "add",
                "--detach",
                "qualified-source",
                state["source"],
            ]
            shutil.copytree(tmp_path / "source-snapshot", tmp_path / "qualified-source")
        else:
            assert command == ["git", "worktree", "remove", "qualified-source"]
            shutil.rmtree(tmp_path / "qualified-source")
        return 0

    monkeypatch.setattr(subprocess, "check_output", check_output)
    monkeypatch.setattr(subprocess, "check_call", check_call)

    def run(event_name: str) -> str:
        monkeypatch.setenv("GITHUB_EVENT_NAME", event_name)
        (tmp_path / "publish-artifact/package-manifest.json").write_text(
            json.dumps(state["package"])
        )
        (tmp_path / "event.json").write_text(json.dumps(state["event"]))
        exec(compile(_resolver_script(), "post-publish-smoke.yml", "exec"), {})
        return (tmp_path / "output").read_text()

    return state, run


@pytest.mark.parametrize(
    "event_name", ["workflow_run", "workflow_dispatch", "release", "push"]
)
def test_all_smoke_entry_points_bind_one_exact_published_release(
    smoke: tuple[dict[str, Any], Callable[[str], str]], event_name: str
) -> None:
    _, run = smoke
    assert run(event_name) == f"release_tag={TAG}\nsource_sha={SOURCE}\n"


def test_publish_completion_uses_its_qualified_artifact_not_the_current_request(
    smoke: tuple[dict[str, Any], Callable[[str], str]],
) -> None:
    _, run = smoke
    Path(".github/release-request.toml").write_text('version = "9.9.9"\n')
    Path("pyproject.toml").write_text(
        '[project]\nname = "hashmarks"\nversion = "9.9.9"\n'
    )
    assert run("workflow_run") == f"release_tag={TAG}\nsource_sha={SOURCE}\n"


def test_smoke_rejects_unsupported_events_before_native_calls(
    smoke: tuple[dict[str, Any], Callable[[str], str]],
) -> None:
    state, run = smoke
    with pytest.raises(SystemExit, match="Unsupported"):
        run("pull_request")
    assert state["calls"] == []
    assert not Path("output").exists()


def test_workflow_self_check_uses_canonical_release_request_admission(
    smoke: tuple[dict[str, Any], Callable[[str], str]],
) -> None:
    state, run = smoke
    Path(".github/release-request.toml").write_text('version = "9.9.9"\n')
    with pytest.raises(ValueError, match="request/version mismatch"):
        run("push")
    assert state["calls"] == []
    assert not Path("output").exists()


@pytest.mark.parametrize(
    "tag", ["main", "latest", "v1.2", "v1.2.3-rc1", "v1.2.3\nsource_sha=foreign", 123]
)
def test_dispatch_rejects_non_release_tags_before_network_or_git(
    smoke: tuple[dict[str, Any], Callable[[str], str]], tag: object
) -> None:
    state, run = smoke
    state["event"]["inputs"]["release_tag"] = tag
    with pytest.raises(SystemExit, match="exact published"):
        run("workflow_dispatch")
    assert state["calls"] == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("draft", True),
        ("prerelease", True),
        ("published_at", None),
        ("tag_name", "v9.9.9"),
    ],
)
def test_smoke_rejects_unpublished_or_different_release_authority(
    smoke: tuple[dict[str, Any], Callable[[str], str]], field: str, value: object
) -> None:
    state, run = smoke
    state["release"][field] = value
    with pytest.raises(SystemExit, match="published stable"):
        run("workflow_dispatch")
    assert len(state["calls"]) == 1


@pytest.mark.parametrize(
    "names", [[], ["unexpected.whl"], ["SHA256SUMS.txt", "SHA256SUMS.txt"]]
)
def test_smoke_rejects_missing_added_or_duplicate_public_assets(
    smoke: tuple[dict[str, Any], Callable[[str], str]], names: list[str]
) -> None:
    state, run = smoke
    state["release"]["assets"] = names
    with pytest.raises(SystemExit, match="asset membership"):
        run("workflow_dispatch")


@pytest.mark.parametrize(
    ("field", "value"),
    [("tag", "v9.9.9"), ("version", "9.9.9"), ("source", {"commit_sha": "b" * 40})],
)
def test_smoke_rejects_self_consistent_manifest_with_foreign_release_source(
    smoke: tuple[dict[str, Any], Callable[[str], str]], field: str, value: object
) -> None:
    state, run = smoke
    state["manifest"][field] = value
    _sign_manifest(state["manifest"])
    with pytest.raises(SystemExit, match="source authority differ"):
        run("workflow_dispatch")


def test_smoke_rejects_manifest_identity_tampering(
    smoke: tuple[dict[str, Any], Callable[[str], str]],
) -> None:
    state, run = smoke
    state["manifest"]["source"]["commit_sha"] = "b" * 40
    with pytest.raises(ValueError, match="manifest identity mismatch"):
        run("workflow_dispatch")


@pytest.mark.parametrize("field", ["source", "target_commitish"])
def test_smoke_rejects_native_git_or_release_target_drift(
    smoke: tuple[dict[str, Any], Callable[[str], str]], field: str
) -> None:
    state, run = smoke
    if field == "source":
        state["source"] = "b" * 40
    else:
        state["release"][field] = "main"
    with pytest.raises(SystemExit, match="source authority differ"):
        run("workflow_dispatch")


@pytest.mark.parametrize("source", ["main", "", "A" * 40, SOURCE + "\nforeign"])
def test_publish_source_receipt_requires_one_exact_commit_before_native_calls(
    smoke: tuple[dict[str, Any], Callable[[str], str]], source: str
) -> None:
    state, run = smoke
    Path("publish-artifact/source.sha").write_text(source)
    with pytest.raises(SystemExit, match="exact source commit"):
        run("workflow_run")
    assert state["calls"] == []
    assert not Path("output").exists()


def test_publish_smoke_rejects_self_consistent_public_release_with_foreign_source(
    smoke: tuple[dict[str, Any], Callable[[str], str]],
) -> None:
    state, run = smoke
    state["source"] = "b" * 40
    state["release"]["target_commitish"] = state["source"]
    state["manifest"]["source"] = {"commit_sha": state["source"]}
    _sign_manifest(state["manifest"])
    with pytest.raises(SystemExit, match="source differs from the exact Publish"):
        run("workflow_run")
    assert not Path("output").exists()


@pytest.mark.parametrize("field", ["version", "distributions"])
def test_publish_smoke_revalidates_qualified_package_manifest_against_native_bytes(
    smoke: tuple[dict[str, Any], Callable[[str], str]], field: str
) -> None:
    state, run = smoke
    if field == "version":
        state["package"][field] = "9.9.9"
    else:
        state["package"][field][0]["sha256"] = "sha256:" + "b" * 64
    _sign_manifest(state["package"])
    with pytest.raises(
        SystemExit, match="package manifest differs from its distribution"
    ):
        run("workflow_run")
    assert not Path("qualified-source").exists()
    assert not Path("output").exists()


@pytest.mark.parametrize(
    "filename", ["hashmarks-1.2.3-py3-none-any.whl", "hashmarks-1.2.3.tar.gz"]
)
def test_publish_smoke_rejects_tampered_qualified_distribution_bytes(
    smoke: tuple[dict[str, Any], Callable[[str], str]], filename: str
) -> None:
    _, run = smoke
    with (Path("publish-artifact/packages") / filename).open("ab") as stream:
        stream.write(b"\0")
    with pytest.raises(
        SystemExit, match="package manifest differs from its distribution"
    ):
        run("workflow_run")
    assert not Path("qualified-source").exists()
    assert not Path("output").exists()


def test_publish_smoke_rejects_self_consistent_public_package_replacement(
    smoke: tuple[dict[str, Any], Callable[[str], str]],
) -> None:
    state, run = smoke
    foreign = deepcopy(state["package"])
    foreign["distributions"][0]["sha256"] = "sha256:" + "b" * 64
    _sign_manifest(foreign)
    state["manifest"]["distributions"] = foreign["distributions"]
    state["manifest"]["package_qualification_identity"] = foreign["manifest_identity"]
    _sign_manifest(state["manifest"])
    with pytest.raises(SystemExit, match="package differs from the exact Publish"):
        run("workflow_run")
    assert not Path("output").exists()


@pytest.mark.parametrize("correct_source", [True, False])
def test_publish_emits_source_receipt_only_after_native_head_matches_resolved_authority(
    tmp_path: Path, correct_source: bool
) -> None:
    workflow = (ROOT / ".github/workflows/publish.yml").read_text()
    body = workflow.split("      - name: Bind exact package qualification bytes\n", 1)[
        1
    ]
    body = body.split("        run: |\n", 1)[1].split("      - name:", 1)[0]
    script = textwrap.dedent(body).replace("${{ needs.prepare.outputs.tag }}", TAG)
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    (repository / "file").write_text("source\n")
    subprocess.run(["git", "-C", str(repository), "add", "file"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "source",
        ],
        check=True,
    )
    native_source = subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
    ).strip()
    (repository / "release").mkdir()
    tools = tmp_path / "tools"
    tools.mkdir()
    uv = tools / "uv"
    uv.write_text('#!/bin/sh\n: > "$SMOKE_TEST_UV_MARKER"\n')
    uv.chmod(0o755)
    marker = tmp_path / "uv-called"
    environment = {
        **os.environ,
        "PATH": str(tools) + os.pathsep + os.environ["PATH"],
        "RELEASE_SOURCE_SHA": native_source if correct_source else "b" * 40,
        "SMOKE_TEST_UV_MARKER": str(marker),
    }
    completed = subprocess.run(
        ["bash", "-eu", "-c", script],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
    )
    receipt = repository / "release/source.sha"
    if correct_source:
        assert completed.returncode == 0, completed.stderr
        assert receipt.read_text() == native_source + "\n"
        assert marker.exists()
    else:
        assert completed.returncode != 0
        assert not receipt.exists()
        assert not marker.exists()
