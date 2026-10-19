"""Thin service mappings preserve current Source and membership observations."""

from __future__ import annotations

import base64
import socketserver
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from contract_assertions import assert_object, assert_text

from hashmarks import validate_native_consumer_bundle
from hashmarks.codemap import CodeMap, CodeMapService, CodeMapServiceClient
from hashmarks.codemap import service as service_module
from hashmarks.codemap.service import PROTOCOL
from hashmarks.operation_contract import operation_schema


def _write_repository(root: Path) -> None:
    root.mkdir()
    (root / "sample.ts").write_bytes(
        b'export const value = external.call("fixture");\r\nvalue();\r\n'
    )
    (root / "test_sample.py").write_text(
        "raise RuntimeError('source is never imported')\n"
        "class TestGroup:\n    def test_item(self): pass\n",
        encoding="utf-8",
    )


def _report(repository: CodeMap) -> dict[str, object]:
    member, _ = repository.source.member("test_sample.py")
    return {
        "schema": "hashmarks.verification-membership-report.v1",
        "selection_kind": "native-collected",
        "producer": {"name": "supplied-neutral-fixture", "version": "1"},
        "provenance": {"synthetic": True},
        "scope": {"paths": ["test_sample.py"]},
        "status": "succeeded",
        "completeness": "complete",
        "truncation": "complete",
        "members": [
            {"path": "test_sample.py", "test_symbol": "TestGroup::test_item[a::b]"}
        ],
        "inputs": [
            {"path": "test_sample.py", "member_revision": member["member_revision"]}
        ],
    }


@pytest.fixture
def local_observer(tmp_path: Path) -> Iterator[tuple[CodeMap, CodeMapService]]:
    root = tmp_path / "repository"
    _write_repository(root)
    with CodeMap(root, state_dir=tmp_path / "state") as repository:
        repository.index.sync()
        service = CodeMapService(root)
        service._codemap = repository
        yield repository, service


@pytest.mark.parametrize(
    "operation, method, options",
    [
        (
            "source_range_receipt",
            "range_receipt",
            {"start_byte": 0, "end_byte": 6, "max_bytes": 512},
        ),
        ("source_ecmascript", "ecmascript", {"limit": 1, "max_bytes": 512}),
    ],
)
def test_source_service_dispatch_preserves_the_exact_native_packet(
    local_observer: tuple[CodeMap, CodeMapService],
    operation: str,
    method: str,
    options: dict[str, object],
) -> None:
    repository, service = local_observer
    expected = getattr(repository.source, method)("sample.ts", **options)
    response = service.dispatch(
        {"protocol": PROTOCOL, "op": operation, "path": "sample.ts", **options}
    )
    assert response[operation] == expected


def test_membership_service_dispatch_preserves_claim_and_source_authorities(
    local_observer: tuple[CodeMap, CodeMapService],
) -> None:
    repository, service = local_observer
    report = _report(repository)
    expected = repository.verification.observe_membership(report)
    response = service.dispatch(
        {"protocol": PROTOCOL, "op": "verification_membership", "report": report}
    )
    assert response["verification_membership"] == expected
    assert expected["membership_authority"] == "caller-claimed"
    assert expected["repository_absence"] == "not-inferred"


@pytest.mark.parametrize(
    "operation, payload, message",
    [
        (
            "source_range_receipt",
            {"path": "sample.ts"},
            "requires start_byte and end_byte",
        ),
        (
            "source_range_receipt",
            {"path": "sample.ts", "start_byte": False, "end_byte": 1},
            "source range",
        ),
        (
            "source_range_receipt",
            {"path": "sample.ts", "start_byte": 0, "end_byte": 1, "max_bytes": True},
            "max_bytes",
        ),
        ("source_ecmascript", {"path": "sample.ts", "limit": False}, "limit"),
        (
            "source_ecmascript",
            {"path": "sample.ts", "execute": True},
            "unsupported source request",
        ),
        ("source_ecmascript", {"path": ["sample.ts"]}, "path must be"),
        (
            "verification_membership",
            {"report": {}, "collector": "pytest"},
            "only a supplied report",
        ),
    ],
)
def test_source_service_leaves_bounds_and_native_selection_with_the_existing_owner(
    local_observer: tuple[CodeMap, CodeMapService],
    operation: str,
    payload: dict[str, object],
    message: str,
) -> None:
    _repository, service = local_observer
    with pytest.raises(ValueError, match=message):
        service.dispatch({"protocol": PROTOCOL, "op": operation, **payload})


@pytest.mark.parametrize(
    "method, arguments, options, expected",
    [
        (
            "source_range_receipt",
            ("sample.ts",),
            {"start_byte": 0, "end_byte": 1},
            {"path": "sample.ts", "start_byte": 0, "end_byte": 1},
        ),
        ("source_ecmascript", ("sample.ts",), {}, {"path": "sample.ts"}),
        (
            "source_ecmascript",
            ("sample.ts",),
            {"limit": 1, "max_bytes": 512},
            {"path": "sample.ts", "limit": 1, "max_bytes": 512},
        ),
        (
            "verification_membership",
            ({"fixture": True},),
            {},
            {"report": {"fixture": True}},
        ),
    ],
)
def test_service_clients_transport_explicit_options_without_mirroring_source_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    arguments: tuple[object, ...],
    options: dict[str, object],
    expected: dict[str, object],
) -> None:
    client = CodeMapServiceClient(tmp_path)
    requests = []
    native = {
        "schema": operation_schema(method),
        "future": {"false": False, "zero": 0, "unknown": None},
    }

    def request(op: str, **payload: object) -> dict[str, object]:
        requests.append((op, payload))
        return {"ok": True, method: native}

    monkeypatch.setattr(client, "request", request)
    observed = getattr(client, method)(*arguments, **options)
    assert requests == [(method, expected)]
    assert observed == native
    assert assert_object(observed["future"])["false"] is False


def test_service_and_client_validate_discovery_against_the_requested_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrong = {
        "ok": True,
        "repository_declarations": {
            "schema": operation_schema("repository_declarations")
        },
    }
    service = CodeMapService(tmp_path)
    monkeypatch.setattr(
        service, "_repository_declarations_response", lambda _request: wrong
    )
    with pytest.raises(RuntimeError, match="schema drift"):
        service.dispatch(
            {
                "protocol": PROTOCOL,
                "op": "repository_declarations",
                "result_mode": "discovery",
            }
        )
    client = CodeMapServiceClient(tmp_path)
    monkeypatch.setattr(client, "request", lambda _op, **_payload: wrong)
    with pytest.raises(RuntimeError, match="schema drift"):
        client.repository_declarations([], result_mode="discovery", source_selection={})


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
def test_source_and_supplied_membership_roundtrip_through_one_live_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repository"
    _write_repository(root)
    with CodeMap(root) as repository:
        repository.index.sync()
        report = _report(repository)
    with TemporaryDirectory(prefix="hm-observe-socket-") as directory:
        socket_path = Path(directory) / "service.sock"
        service = CodeMapService(root, socket_path=socket_path)
        thread = threading.Thread(target=service.serve_forever, daemon=True)
        client = CodeMapServiceClient(root, socket_path=socket_path)
        thread.start()
        try:
            _wait(client)
            receipt = client.source_range_receipt("sample.ts", start_byte=0, end_byte=6)
            content = assert_object(receipt["content"])
            assert (
                base64.b64decode(assert_text(content["data"]), validate=True)
                == b"export"
            )
            syntax = client.source_ecmascript("sample.ts", limit=1)
            assert syntax["schema"] == operation_schema("source_ecmascript")
            assert syntax["execution_effect"] == "none"
            observed = client.verification_membership(report)
            assert validate_native_consumer_bundle(observed)["valid"] is True
            assert assert_object(observed["source_equivalence"])["state"] == "proven"
            (root / "test_sample.py").write_text("# changed source\n", encoding="utf-8")
            client.sync()
            changed = client.verification_membership(report)
            assert assert_object(changed["source_equivalence"])["state"] == "mismatch"
            monkeypatch.setattr(service_module, "MAX_RESPONSE", 256)
            with pytest.raises(RuntimeError, match="response exceeded size limit"):
                client.source_range_receipt("sample.ts", start_byte=0, end_byte=1)
        finally:
            if service._server is not None:
                client.stop()
            thread.join(timeout=5)
        assert not thread.is_alive()
