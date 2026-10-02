from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import hashmarks.native_maven as native_maven
from hashmarks.native_maven import collect_maven_modules


def _output_path(command: list[str]) -> Path:
    value = next(item for item in command if item.startswith("-Doutput="))
    return Path(value.removeprefix("-Doutput="))


def test_collect_maven_modules_uses_native_effective_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "pom.xml"
    manifest.write_text(
        "<project>"
        "<parent><groupId>raw.parent</groupId></parent>"
        "<artifactId>raw-app</artifactId>"
        "<dependencies>"
        "<dependency><groupId>raw.libs</groupId><artifactId>raw-core</artifactId></dependency>"
        "</dependencies>"
        "</project>",
        encoding="utf-8",
    )
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs):
        commands.append(command)
        _output_path(command).write_text(
            "<project>"
            "<groupId>org.effective</groupId>"
            "<artifactId>app</artifactId>"
            "<dependencies>"
            "<dependency><groupId>org.effective</groupId><artifactId>core</artifactId></dependency>"
            "</dependencies>"
            "</project>",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(native_maven.subprocess, "run", fake_run)

    snapshot = collect_maven_modules(
        tmp_path,
        (manifest,),
        executable="/repo/mvnw",
    )

    assert snapshot.executable == "/repo/mvnw"
    assert len(snapshot.modules) == 1
    module = snapshot.modules[0]
    assert module.module_id == "org.effective:app"
    assert module.group_id == "org.effective"
    assert module.artifact_id == "app"
    assert module.root == "."
    assert module.manifest == "pom.xml"
    assert module.dependencies == (("org.effective", "core"),)
    assert snapshot.warnings == ()
    assert len(commands) == 1
    assert commands[0][:5] == [
        "/repo/mvnw",
        "-q",
        "-N",
        "-f",
        str(manifest),
    ]
    assert "help:effective-pom" in commands[0]


def test_collect_maven_modules_does_not_parse_raw_pom_after_native_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "pom.xml"
    manifest.write_text(
        "<project><groupId>org.raw</groupId><artifactId>app</artifactId></project>",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        native_maven.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 1, stdout="", stderr="native model failed"
        ),
    )

    snapshot = collect_maven_modules(
        tmp_path,
        (manifest,),
        executable="/repo/mvnw",
    )

    assert snapshot.modules == ()
    assert len(snapshot.warnings) == 1
    assert "native model failed" in snapshot.warnings[0]


def test_collect_maven_modules_uses_only_admitted_manifests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    admitted = tmp_path / "pom.xml"
    admitted.write_text("<project/>", encoding="utf-8")
    hidden = tmp_path / "target" / "pom.xml"
    hidden.parent.mkdir()
    hidden.write_text("<project/>", encoding="utf-8")
    seen: list[Path] = []

    def fake_run(command: list[str], **_kwargs):
        manifest = Path(command[command.index("-f") + 1])
        seen.append(manifest)
        _output_path(command).write_text(
            "<project><groupId>org.example</groupId><artifactId>root</artifactId></project>",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(native_maven.subprocess, "run", fake_run)

    snapshot = collect_maven_modules(
        tmp_path,
        (admitted,),
        executable="/repo/mvnw",
    )

    assert seen == [admitted]
    assert [module.module_id for module in snapshot.modules] == ["org.example:root"]


def test_collect_maven_modules_fails_closed_without_maven(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "pom.xml"
    manifest.write_text(
        "<project><groupId>org.raw</groupId><artifactId>app</artifactId></project>",
        encoding="utf-8",
    )
    monkeypatch.setattr(native_maven, "find_maven", lambda _workspace: None)

    snapshot = collect_maven_modules(tmp_path, (manifest,))

    assert snapshot.executable is None
    assert snapshot.modules == ()
    assert snapshot.warnings == ("Maven POMs detected but mvn/mvnw is unavailable",)
