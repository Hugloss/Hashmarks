"""Identity IPC preserves one engine observation and its negative evidence."""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks import Directory, File, Glob, RepositoryIdentity
from hashmarks.client import (
    DaemonCompatibilityError,
    DaemonProtocolError,
    DaemonUnavailableError,
    IdentityClient,
)
from hashmarks.daemon import IdentityDaemon
from hashmarks.input_observation_transport import (
    decode_input_observation_request,
    encode_input_observation_request,
)
from hashmarks.ipc_boundary import dispatch_json_request
from hashmarks.schema import DAEMON_PROTOCOL_VERSION, DAEMON_REQUIRED_CAPABILITIES
from hashmarks.snapshot import InputObservation
from hashmarks.specs import InputValue


@pytest.fixture
def daemon(tmp_path: Path) -> Iterator[IdentityDaemon]:
    workspace = tmp_path / "repository"
    (workspace / "src/generated").mkdir(parents=True)
    (workspace / "src/empty").mkdir()
    (workspace / "src/keep").write_bytes(b"keep")
    (workspace / "src/generated/ignored").write_bytes(b"generated")
    server = IdentityDaemon(workspace, state_dir=tmp_path / "daemon-state")
    try:
        yield server
    finally:
        server.engine.close()


@pytest.fixture
def client(daemon: IdentityDaemon, monkeypatch: pytest.MonkeyPatch) -> IdentityClient:
    peer = IdentityClient(daemon.workspace, state_dir=daemon.state_dir)

    def request(op: str, **payload: object) -> dict[str, object]:
        raw = json.dumps(
            {"protocol": DAEMON_PROTOCOL_VERSION, "op": op, **payload}
        ).encode()
        response = dispatch_json_request(raw, daemon.dispatch)
        stream = io.BytesIO()
        daemon._write_response(stream, response)
        return peer._decode_response(stream.getvalue())

    monkeypatch.setattr(peer, "request", request)
    return peer


def _identity(
    client: IdentityClient, monkeypatch: pytest.MonkeyPatch, mode: str
) -> RepositoryIdentity:
    monkeypatch.setattr(
        "hashmarks.identity.IdentityClient", lambda *_args, **_kwargs: client
    )
    return RepositoryIdentity(client.workspace, mode=mode, state_dir=client.state_dir)


def _arguments(**changes: object) -> dict[str, object]:
    return {
        "inputs": [{"kind": "directory", "value": "src"}],
        "exclude": [{"kind": "pattern", "value": "src/generated"}],
        "require_matches": True,
        "verify": False,
        "max_members": 100,
        **changes,
    }


def test_typed_request_roundtrip_keeps_native_specs(daemon: IdentityDaemon) -> None:
    request = encode_input_observation_request(
        daemon.workspace,
        [Directory("src"), File("src/keep"), Glob("src/*"), Path("src/empty")],
        exclude=(Directory("src/generated"),),
        require_matches=True,
        verify=True,
        max_members=100,
    )
    decoded = decode_input_observation_request(json.loads(json.dumps(request)))
    assert decoded == {
        "inputs": (Directory("src"), File("src/keep"), Glob("src/*"), "src/empty"),
        "exclude": (Directory("src/generated"),),
        "require_matches": True,
        "verify": True,
        "max_members": 100,
    }


@pytest.mark.parametrize("mode", ["auto", "daemon"])
def test_facade_transports_one_canonical_engine_observation(
    client: IdentityClient,
    daemon: IdentityDaemon,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    original = daemon.engine.observe_inputs
    observed: list[InputObservation] = []

    def observe(
        inputs: tuple[InputValue, ...],
        *,
        exclude: tuple[InputValue, ...],
        require_matches: bool,
        verify: bool,
        max_members: int,
    ) -> InputObservation:
        assert inputs == (Directory("src"),)
        assert exclude == (Directory("src/generated"),)
        assert require_matches is verify is True
        assert max_members == 10
        result = original(
            inputs,
            exclude=exclude,
            require_matches=require_matches,
            verify=verify,
            max_members=max_members,
        )
        observed.append(result)
        return result

    monkeypatch.setattr(daemon.engine, "observe_inputs", observe)
    with _identity(client, monkeypatch, mode) as identity:
        result = identity.observe_inputs(
            Directory("src"),
            exclude=(Directory("src/generated"),),
            verify=True,
            max_members=10,
        )
        assert identity._engine is None
    assert len(observed) == 1
    expected = observed[0].as_dict()
    expected["snapshot"] = {**observed[0].snapshot.as_dict(), "mode": "daemon"}
    assert result.as_dict() == expected
    assert result.counts.entry_count == 3
    assert result.counts.regular_file_bytes == 4


@pytest.mark.parametrize("mode", ["auto", "daemon"])
def test_daemon_and_local_keep_equivalent_digests_after_selection_change(
    client: IdentityClient,
    daemon: IdentityDaemon,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    with (
        RepositoryIdentity(
            daemon.workspace,
            mode="local",
            state_dir=daemon.state_dir.parent / "local-state",
        ) as local,
        _identity(client, monkeypatch, mode) as remote,
    ):
        first = remote.observe_inputs(Glob("src/*"), exclude=("src/generated",))
        (daemon.workspace / "src/new").write_bytes(b"new")
        second = remote.observe_inputs(Glob("src/*"), exclude=("src/generated",))
        expected = local.observe_inputs(Glob("src/*"), exclude=("src/generated",))
        assert second.snapshot.digest != first.snapshot.digest
        assert second.snapshot.digest == expected.snapshot.digest
        assert second.members == expected.members
        assert second.manifest == expected.manifest
        assert second.counts == expected.counts


@pytest.mark.parametrize(
    ("inputs", "exclude", "require_matches"),
    [((), (), True), ((Glob("missing*"),), (), False), (("src",), ("src",), True)],
)
def test_empty_selected_scope_is_preserved(
    client: IdentityClient,
    inputs: tuple[InputValue, ...],
    exclude: tuple[InputValue, ...],
    require_matches: bool,
) -> None:
    result = client.observe_inputs(
        inputs, exclude=exclude, require_matches=require_matches
    )
    assert result.snapshot.mode == "daemon"
    assert result.manifest.paths == result.members == ()
    assert result.counts.entry_count == result.counts.regular_file_bytes == 0
    assert result.completeness == "complete"
    assert (client.workspace / "src/keep").is_file()


def test_symlink_transport_keeps_literal_target_without_following_it(
    client: IdentityClient,
) -> None:
    link = client.workspace / "link"
    try:
        link.symlink_to("../missing-target")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    result = client.observe_inputs((File("link"),), verify=True)
    assert result.members[0].kind == "symlink"
    assert result.members[0].link_target == "../missing-target"
    assert result.members[0].executable is None
    assert result.counts.symlink_count == 1
    assert result.counts.regular_file_bytes == 0


def test_explicit_walk_ignored_root_is_still_a_valid_complete_scope(
    client: IdentityClient,
) -> None:
    selected = client.workspace / "src/__pycache__"
    selected.mkdir()
    (selected / "entry").write_bytes(b"kept")
    result = client.observe_inputs((Directory("src/__pycache__"),))
    assert "__pycache__" in result.walk_ignore_names
    assert [member.path for member in result.members] == [
        "src/__pycache__",
        "src/__pycache__/entry",
    ]
    assert result.counts.regular_file_bytes == 4
    assert result.completeness == "complete"


@pytest.mark.parametrize("value", [File("src"), Directory("src/keep"), Glob("src")])
def test_direct_client_validates_typed_specs_before_status(
    client: IdentityClient, monkeypatch: pytest.MonkeyPatch, value: InputValue
) -> None:
    monkeypatch.setattr(
        client, "request", lambda *_args, **_kwargs: pytest.fail("unexpected IPC")
    )
    with pytest.raises(ValueError):
        client.observe_inputs((value,))


@pytest.mark.parametrize("mode", ["local", "auto", "daemon"])
@pytest.mark.parametrize("excluded", [False, True])
def test_wrong_kind_typed_specs_fail_at_caller_before_operation(
    client: IdentityClient, monkeypatch: pytest.MonkeyPatch, mode: str, excluded: bool
) -> None:
    with _identity(client, monkeypatch, mode) as identity:
        monkeypatch.setattr(
            client, "request", lambda *_args, **_kwargs: pytest.fail("unexpected IPC")
        )
        with pytest.raises(ValueError, match="not a file"):
            if excluded:
                identity.observe_inputs("src", exclude=(File("src"),))
            else:
                identity.observe_inputs(File("src"))
        assert identity._engine is None


@pytest.mark.parametrize(
    "changes",
    [
        {"require_matches": 1},
        {"verify": "false"},
        {"max_members": True},
        {"max_members": 1.0},
        {"max_members": 0},
        {"inputs": "src"},
        {"inputs": [{"kind": "file", "value": "src/*"}]},
        {"inputs": [{"kind": "glob", "value": "src"}]},
        {"inputs": [{"kind": "pattern", "value": "../escape"}]},
        {"inputs": [{"kind": "pattern", "value": "src/./keep"}]},
        {"inputs": [{"kind": "unrecognized", "value": "src"}]},
        {"exclude": [{"kind": "directory", "value": "src", "extra": True}]},
        {"ref": "HEAD"},
    ],
)
def test_malformed_requests_fail_before_engine_observation(
    daemon: IdentityDaemon, monkeypatch: pytest.MonkeyPatch, changes: dict[str, object]
) -> None:
    monkeypatch.setattr(
        daemon.engine,
        "observe_inputs",
        lambda **_kwargs: pytest.fail("unexpected engine read"),
    )
    with pytest.raises(ValueError):
        daemon.dispatch(
            {
                "protocol": DAEMON_PROTOCOL_VERSION,
                "op": "observe_inputs",
                **_arguments(**changes),
            }
        )


@pytest.mark.parametrize("freshness", ["current", "stale", "unknown"])
def test_response_decoding_preserves_supplied_freshness(
    client: IdentityClient, monkeypatch: pytest.MonkeyPatch, freshness: str
) -> None:
    observed = client.observe_inputs((File("src/keep"),)).as_dict()
    observed["freshness"] = freshness
    monkeypatch.setattr(
        client,
        "request",
        lambda *_args, **_kwargs: {"ok": True, "observation": observed},
    )
    result = client.observe_inputs((File("src/keep"),))
    assert result.as_dict() == observed
    assert result.freshness == freshness


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("root", "schema", "wrong"),
        ("root", "authority", "execution"),
        ("root", "completeness", "partial"),
        ("root", "freshness", "latest"),
        ("root", "unexpected", True),
        ("snapshot", "hash", "f" * 63),
        ("snapshot", "size", 1.0),
        ("snapshot", "generation", True),
        ("snapshot", "generation", None),
        ("snapshot", "generation", 1 << 53),
        ("snapshot", "manifest", "0" * 64),
        ("snapshot", "mode", "local"),
        ("snapshot", "observed_paths", ["../escape"]),
        ("scope", "roots", ["missing"]),
        ("scope", "roots", ["src/keep", "src/keep"]),
        ("scope", "excluded_paths", ["src/keep"]),
        ("scope", "excluded_paths", ["missing", "missing/child"]),
        ("scope", "walk_ignore_names", ["src/generated"]),
        ("scope", "mandatory_exclude_names", ["src"]),
        ("scope", "mandatory_exclude_names", ["keep"]),
        ("scope", "internal_excluded_paths", ["src"]),
        ("scope", "internal_excluded_paths", ["src/keep"]),
        ("member", "kind", "socket"),
        ("member", "path", "/src/keep"),
        ("member", "revision", "unknown"),
        ("member", "regular_file_bytes", True),
        ("member", "executable", 1),
        ("member", "link_target", "elsewhere"),
        ("counts", "entry_count", True),
        ("counts", "file_count", 1.0),
        ("counts", "regular_file_bytes", 999),
    ],
)
def test_response_decoder_rejects_noncanonical_or_incoherent_envelopes(
    client: IdentityClient,
    monkeypatch: pytest.MonkeyPatch,
    section: str,
    key: str,
    value: object,
) -> None:
    packet = deepcopy(client.observe_inputs((File("src/keep"),)).as_dict())
    if section == "root":
        target = packet
    elif section == "member":
        target = assert_records(packet["members"])[0]
    else:
        target = assert_object(packet[section])
    target[key] = value
    monkeypatch.setattr(
        client, "request", lambda *_args, **_kwargs: {"ok": True, "observation": packet}
    )
    with pytest.raises(DaemonProtocolError, match="invalid input observation"):
        client.observe_inputs((File("src/keep"),))


@pytest.mark.parametrize(
    "mutation", ["duplicate", "reordered", "missing-directory", "too-many"]
)
def test_member_inventory_cannot_silently_change_shape_or_bound(
    client: IdentityClient, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    packet = client.observe_inputs(("src",)).as_dict()
    members = assert_records(packet["members"])
    maximum = 100
    if mutation == "duplicate":
        members.append(deepcopy(members[-1]))
    elif mutation == "reordered":
        members.reverse()
    elif mutation == "missing-directory":
        members[:] = [member for member in members if member["path"] != "src/generated"]
    else:
        maximum = 1
    packet["members"] = members
    monkeypatch.setattr(
        client, "request", lambda *_args, **_kwargs: {"ok": True, "observation": packet}
    )
    with pytest.raises(DaemonProtocolError, match="invalid input observation"):
        client.observe_inputs(("src",), max_members=maximum)


def _old_daemon(daemon: IdentityDaemon, monkeypatch: pytest.MonkeyPatch) -> None:
    original = daemon._status_response

    def status(request: dict[str, object]) -> dict[str, object]:
        result = original(request)
        result["capabilities"] = list(DAEMON_REQUIRED_CAPABILITIES)
        return result

    monkeypatch.setattr(daemon, "_status_response", status)


def test_older_v3_daemon_keeps_snapshot_support_but_auto_observation_falls_back(
    client: IdentityClient, daemon: IdentityDaemon, monkeypatch: pytest.MonkeyPatch
) -> None:
    _old_daemon(daemon, monkeypatch)
    assert client.status()["protocol"] == DAEMON_PROTOCOL_VERSION
    assert client.input_root(("src/keep",))["mode"] == "daemon"
    with _identity(client, monkeypatch, "auto") as identity:
        result = identity.observe_inputs(Directory("src"))
        assert result.snapshot.mode == "local"
        assert result.counts.regular_file_bytes == 13


def test_explicit_daemon_does_not_fall_back_when_observation_capability_is_missing(
    client: IdentityClient, daemon: IdentityDaemon, monkeypatch: pytest.MonkeyPatch
) -> None:
    _old_daemon(daemon, monkeypatch)
    with _identity(client, monkeypatch, "daemon") as identity:
        with pytest.raises(DaemonCompatibilityError, match="input-observation.v1"):
            identity.observe_inputs("src")
        assert identity._engine is None


@pytest.mark.parametrize("mode", ["auto", "daemon"])
def test_unavailable_daemon_after_status_uses_only_existing_mode_fallback(
    client: IdentityClient, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    with _identity(client, monkeypatch, mode) as identity:
        assert identity.active_mode == "daemon"

        def unavailable(*_args: object, **_kwargs: object) -> dict[str, object]:
            raise DaemonUnavailableError("stopped")

        monkeypatch.setattr(client, "request", unavailable)
        if mode == "daemon":
            with pytest.raises(DaemonUnavailableError, match="stopped"):
                identity.observe_inputs("src")
            assert identity._engine is None
        else:
            assert identity.observe_inputs("src").snapshot.mode == "local"


@pytest.mark.parametrize("mode", ["auto", "daemon"])
def test_response_budget_error_has_no_partial_observation_or_local_fallback(
    client: IdentityClient, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    with _identity(client, monkeypatch, mode) as identity:
        assert identity.active_mode == "daemon"
        monkeypatch.setattr("hashmarks.daemon._MAX_RESPONSE", 512)
        with pytest.raises(DaemonProtocolError, match="response exceeded size limit"):
            identity.observe_inputs("src")
        assert identity._engine is None
    stream = io.BytesIO()
    IdentityDaemon._write_response(stream, {"ok": True, "observation": "x" * 1024})
    assert len(stream.getvalue()) <= 512
    assert json.loads(stream.getvalue()) == {
        "ok": False,
        "error": "daemon response exceeded size limit",
    }


def test_actual_engine_member_bound_remains_an_error(client: IdentityClient) -> None:
    with pytest.raises(DaemonProtocolError, match="member limit exceeded"):
        client.observe_inputs(("src",), max_members=1)
    assert client.observe_inputs(("src",)).counts.entry_count == 5


@pytest.mark.parametrize("mode", ["auto", "daemon"])
def test_input_observation_uses_actual_socket_transport(
    tmp_path: Path, mode: str
) -> None:
    from test_developer_api import _start_daemon

    workspace = tmp_path / "repository"
    (workspace / "src/generated").mkdir(parents=True)
    (workspace / "src/entry").write_bytes(b"entry")
    (workspace / "src/generated/omit").write_bytes(b"omit")
    server, watcher, socket_path, thread = _start_daemon(workspace, tmp_path)
    peer = IdentityClient(workspace, socket_path=socket_path)
    try:
        with RepositoryIdentity(
            workspace, mode=mode, socket_path=socket_path, state_dir=server.state_dir
        ) as identity:
            first = identity.observe_inputs(
                Directory("src"), exclude=("src/generated",)
            )
            (workspace / "src/new").write_bytes(b"new")
            server.engine.record_changes(("src/new",))
            second = identity.observe_inputs(
                Directory("src"), exclude=("src/generated",)
            )
            assert first.snapshot.mode == second.snapshot.mode == "daemon"
            assert second.snapshot.digest != first.snapshot.digest
            assert [member.path for member in second.members] == [
                "src",
                "src/entry",
                "src/new",
            ]
            assert second.counts.regular_file_bytes == 8
            assert identity._engine is None
    finally:
        peer.stop()
        thread.join(timeout=2)
        assert watcher.stopped
