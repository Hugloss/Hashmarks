import json
import sys
from types import SimpleNamespace

import pytest

from benchmarks import bench_daemon


class _FakeDaemon:
    def __init__(self, root, *, state_dir, socket_path):
        self.socket_path = socket_path
        self.engine = SimpleNamespace(
            changes=SimpleNamespace(
                snapshot=lambda: SimpleNamespace(state=SimpleNamespace(value="dirty"))
            )
        )

    def serve_forever(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self.socket_path.touch()


class _FakeClient:
    def __init__(self, root, *, socket_path, timeout):
        self.root = root
        self.registered = False

    def register_manifest(self, manifest):
        self.registered = True
        return "manifest-handle"

    def _identity(self):
        changed = any(
            path.read_text(encoding="utf-8") == "changed\n"
            for path in (self.root / "src").rglob("*.txt")
        )
        return {"hash": "edited" if changed else "initial"}

    def input_root_manifest(self, handle):
        assert self.registered
        assert handle == "manifest-handle"
        return self._identity()

    def input_root(self, paths):
        assert paths == ["src"]
        return self._identity()

    def status(self):
        return {"state": "ready"}

    def stop(self) -> None:
        return None


@pytest.mark.parametrize("manifest_mode", ["directory", "files"])
def test_daemon_benchmark_preserves_identity_protocol(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    manifest_mode: str,
) -> None:
    monkeypatch.setattr(bench_daemon, "IdentityDaemon", _FakeDaemon)
    monkeypatch.setattr(bench_daemon, "IdentityClient", _FakeClient)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bench_daemon.py",
            "--files",
            "4",
            "--files-per-dir",
            "2",
            "--hot-requests",
            "2",
            "--manifest",
            manifest_mode,
        ],
    )

    bench_daemon.main()

    result = json.loads(capsys.readouterr().out)
    assert result["manifest"] == manifest_mode
    assert result["identity_checks"] == {
        "edit_changes_identity": True,
        "hot_equals_cold": True,
    }
    assert result["daemon_status"] == {"state": "ready"}
    assert result["workspace"] is None
