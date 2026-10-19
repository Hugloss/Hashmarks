"""Registered source providers keep their native evidence across CLI and IPC."""

from __future__ import annotations

import json
import os
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks.codemap import CodeMap, CodeMapService, CodeMapServiceClient
from hashmarks.codemap.repository_declaration_selection import (
    source_declaration_providers,
)
from hashmarks.codemap.service import PROTOCOL
from hashmarks.operation_contract import operation_schema

_SELECTION: dict[str, object] = {
    "make_shell": {
        "make_paths": ["Makefile"],
        "shell_paths": ["demo.sh", "missing.sh"],
    },
    "python_uv_manifest_paths": ["pyproject.toml", "packages/tool/pyproject.toml"],
}
_FLAGS = [
    "--make-path",
    "Makefile",
    "--shell-path",
    "demo.sh",
    "--shell-path",
    "missing.sh",
    "--python-uv-manifest-path",
    "pyproject.toml",
    "--python-uv-manifest-path",
    "packages/tool/pyproject.toml",
]


@pytest.fixture
def source_repository(tmp_path: Path) -> tuple[Path, Path]:
    root, state = tmp_path / "repository", tmp_path / "state"
    (root / "packages/tool").mkdir(parents=True)
    (root / "Makefile").write_text("RUNNER = echo\ncheck:\n\t@$(RUNNER) fixture\n")
    (root / "demo.sh").write_text("echo before\n")
    (root / "pyproject.toml").write_text(
        '[project]\nname="fixture"\nversion="1"\n'
        '[tool.uv.workspace]\nmembers=["packages/*"]\n'
    )
    (root / "packages/tool/pyproject.toml").write_text(
        '[project]\nname="tool"\nversion="1"\n'
        '[project.scripts]\ntool="unimported_package:main"\n'
    )
    with CodeMap(root, state_dir=state) as repository:
        repository.index.sync()
    return root, state


def _cli(
    root: Path, state: Path, arguments: list[str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "hashmarks.cli",
            "--workspace",
            str(root),
            "--state-dir",
            str(state),
            "repository-declarations",
            *arguments,
        ],
        env={**os.environ, "HASHMARKS_NO_UPDATE_CHECK": "1"},
        capture_output=True,
        text=True,
        check=False,
    )


def _assert_selected(packet: dict[str, object]) -> None:
    assert packet["schema"] == operation_schema("repository_declarations", "discovery")
    providers = assert_records(packet["providers"])
    assert [row["name"] for row in providers] == [
        "make-shell-syntax",
        "python-uv-manifests",
    ]
    assert assert_object(providers[0]["provenance"])["missing_selected_paths"] == [
        "missing.sh"
    ]
    assert all(
        assert_object(row["provenance"])["negative_evidence_admissible"] is False
        for row in providers
    )
    assert all(
        item["member_revision"]
        for row in providers
        for item in assert_records(row["inputs"])
        if item["state"] == "known-present"
    )
    groups = assert_records(assert_object(packet["declarations"])["groups"])
    assert groups
    assert all(assert_object(row["absence"])["state"] == "unknown" for row in groups)


@pytest.mark.parametrize("mode", ["flags", "json"])
def test_cli_registered_provider_selection_matches_native_discovery(
    source_repository: tuple[Path, Path], tmp_path: Path, mode: str
) -> None:
    root, state = source_repository
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps(_SELECTION), encoding="utf-8")
    arguments = (
        _FLAGS if mode == "flags" else ["--source-selection-json", str(selection)]
    )
    with CodeMap(root, state_dir=state) as repository:
        expected = repository.declarations.operation(
            [],
            result_mode="discovery",
            providers=source_declaration_providers("discovery", _SELECTION),
        )
    completed = _cli(root, state, arguments)
    assert completed.returncode == 0, completed.stderr
    observed = assert_object(json.loads(completed.stdout))
    assert observed == expected
    _assert_selected(observed)


def test_cli_explicit_empty_selection_does_not_restore_previous_provider_sources(
    source_repository: tuple[Path, Path], tmp_path: Path
) -> None:
    root, state = source_repository
    with CodeMap(root, state_dir=state) as repository:
        before = repository.declarations.operation(
            [],
            result_mode="discovery",
            providers=source_declaration_providers("discovery", _SELECTION),
        )
    previous, selection = tmp_path / "previous.json", tmp_path / "selection.json"
    previous.write_text(json.dumps(before), encoding="utf-8")
    selection.write_text("{}", encoding="utf-8")
    completed = _cli(
        root,
        state,
        [
            "--source-selection-json",
            str(selection),
            "--previous-observation",
            str(previous),
        ],
    )
    assert completed.returncode == 0, completed.stderr
    observed = assert_object(json.loads(completed.stdout))
    assert observed["providers"] == []
    assert assert_object(observed["declarations"])["groups"] == []
    assert observed["delta_from_previous"]


@pytest.mark.parametrize(
    "selection, flags, message",
    [
        ({}, ["--make-path", "Makefile"], "cannot be combined"),
        ({"provider_import": "repository.execute"}, [], "supported source options"),
        ({"make_shell": {"shell_paths": ["../outside.sh"]}}, [], "input path"),
    ],
)
def test_cli_rejects_ambiguous_or_unsupported_provider_selection(
    source_repository: tuple[Path, Path],
    tmp_path: Path,
    selection: dict[str, object],
    flags: list[str],
    message: str,
) -> None:
    root, state = source_repository
    path = tmp_path / "invalid-selection.json"
    path.write_text(json.dumps(selection), encoding="utf-8")
    result = _cli(root, state, ["--source-selection-json", str(path), *flags])
    assert result.returncode != 0
    assert message in result.stderr


def test_service_dispatch_uses_the_native_selected_declaration_operation(
    source_repository: tuple[Path, Path],
) -> None:
    root, state = source_repository
    service = CodeMapService(root)
    with CodeMap(root, state_dir=state) as repository:
        service._codemap = repository
        expected = repository.declarations.operation(
            [],
            result_mode="discovery",
            providers=source_declaration_providers("discovery", _SELECTION),
        )
        response = service.dispatch(
            {
                "protocol": PROTOCOL,
                "op": "repository_declarations",
                "groups": [],
                "result_mode": "discovery",
                "source_selection": _SELECTION,
            }
        )
    observed = assert_object(response["repository_declarations"])
    assert observed == expected
    _assert_selected(observed)


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"result_mode": []}, "result_mode must be a string"),
        ({"result_mode": "run"}, "result_mode must be one of"),
        (
            {"providers": ["repository.execute"]},
            "unsupported declaration request fields",
        ),
        ({"groups": {}}, "groups must be an array"),
        ({"previous_observation": []}, "previous_observation must be an object"),
        (
            {"source_selection": {"make_shell": {"execute": True}}},
            "source selection requires",
        ),
    ],
)
def test_service_rejects_invalid_declaration_transport_before_observing(
    tmp_path: Path, payload: dict[str, object], message: str
) -> None:
    service = CodeMapService(tmp_path)
    with pytest.raises(ValueError, match=message):
        service.dispatch(
            {"protocol": PROTOCOL, "op": "repository_declarations", **payload}
        )


def _wait(client: CodeMapServiceClient) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            client.status()
            return
        except (OSError, RuntimeError):
            time.sleep(0.02)
    raise AssertionError("service did not become ready")


@pytest.mark.skipif(
    getattr(socketserver, "UnixStreamServer", None) is None,
    reason="Unix socket service unavailable",
)
def test_registered_declarations_use_one_live_service_and_existing_delta(
    source_repository: tuple[Path, Path],
) -> None:
    root, _state = source_repository
    with TemporaryDirectory(prefix="hm-decl-socket-") as directory:
        socket_path = Path(directory) / "service.sock"
        service = CodeMapService(root, socket_path=socket_path)
        thread = threading.Thread(target=service.serve_forever, daemon=True)
        client = CodeMapServiceClient(root, socket_path=socket_path)
        thread.start()
        try:
            _wait(client)
            before = client.repository_declarations(
                [], result_mode="discovery", source_selection=_SELECTION
            )
            _assert_selected(before)
            (root / "demo.sh").write_text("echo after\n", encoding="utf-8")
            with pytest.raises(RuntimeError):
                client.repository_declarations(
                    [], result_mode="discovery", source_selection=_SELECTION
                )
            client.sync()
            after = client.repository_declarations(
                [],
                result_mode="discovery",
                source_selection=_SELECTION,
                previous_observation=before,
            )
            assert before["observation_identity"] != after["observation_identity"]
            delta = assert_object(
                assert_object(after["delta_from_previous"])["declarations"]
            )
            assert delta["changed_groups"]
            empty = client.repository_declarations(
                [],
                result_mode="discovery",
                source_selection={},
                previous_observation=after,
            )
            assert empty["providers"] == []
            assert assert_object(empty["declarations"])["groups"] == []
            for mode in ("observation", "explain"):
                assert client.repository_declarations([], result_mode=mode)[
                    "schema"
                ] == operation_schema("repository_declarations", mode)
        finally:
            if service._server is not None:
                client.stop()
            thread.join(timeout=5)
        assert not thread.is_alive()
