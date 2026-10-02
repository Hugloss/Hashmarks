from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import hashmarks.codemap.project_graph as project_graph
from hashmarks.codemap.project_graph import CargoProjectGraphProvider


def _cargo_manifest(tmp_path: Path) -> Path:
    manifest = tmp_path / "Cargo.toml"
    manifest.write_text(
        '[package]\nname = "app"\nversion = "0.1.0"\n'
        '[dependencies]\nshared = { path = "shared" }\n',
        encoding="utf-8",
    )
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "Cargo.toml").write_text(
        '[package]\nname = "shared"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    return manifest


def test_cargo_provider_does_not_replace_missing_native_authority_with_manifest_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _cargo_manifest(tmp_path)
    provider = CargoProjectGraphProvider(lambda _name: (manifest,))

    monkeypatch.setattr(project_graph.shutil, "which", lambda _name: None)

    evidence = provider.collect(tmp_path)

    assert evidence.nodes == ()
    assert evidence.edges == ()
    assert evidence.warnings == (
        "cargo executable unavailable; native Cargo project graph not collected",
    )


def test_cargo_provider_does_not_replace_native_failure_with_manifest_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _cargo_manifest(tmp_path)
    provider = CargoProjectGraphProvider(lambda _name: (manifest,))

    monkeypatch.setattr(project_graph.shutil, "which", lambda _name: "/usr/bin/cargo")
    monkeypatch.setattr(
        provider,
        "_run_cargo_metadata",
        lambda _workspace, _cargo: (None, "cargo metadata failed: boom"),
    )

    evidence = provider.collect(tmp_path)

    assert evidence.nodes == ()
    assert evidence.edges == ()
    assert evidence.warnings == ("cargo metadata failed: boom",)


def test_cargo_provider_does_not_replace_invalid_native_output_with_manifest_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _cargo_manifest(tmp_path)
    provider = CargoProjectGraphProvider(lambda _name: (manifest,))

    monkeypatch.setattr(project_graph.shutil, "which", lambda _name: "/usr/bin/cargo")
    monkeypatch.setattr(
        provider,
        "_run_cargo_metadata",
        lambda _workspace, _cargo: (
            subprocess.CompletedProcess(["cargo"], 0, stdout="not-json", stderr=""),
            None,
        ),
    )

    evidence = provider.collect(tmp_path)

    assert evidence.nodes == ()
    assert evidence.edges == ()
    assert evidence.warnings == ("cargo metadata returned invalid JSON",)
