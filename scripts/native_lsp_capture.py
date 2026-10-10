"""Development-only, event-driven capture of installed language servers.

Request catalogs and owned sources define a finite QA experiment. Product code
never imports this client; capture freshness remains the external caller's claim.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from hashmarks.digest import FILE_DOMAIN, hash_bytes


class CaptureClient:
    def __init__(self, argv: list[str], root: Path) -> None:
        self.root_uri = root.as_uri()
        self.stderr = (root / "server.stderr").open("wb")
        self.process = subprocess.Popen(
            argv,
            cwd=root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.stderr,
        )
        self.sequence = 0
        self.transcript: list[dict[str, Any]] = []

    def send(self, message: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        raw = json.dumps(message).encode()
        self.process.stdin.write(f"Content-Length: {len(raw)}\r\n\r\n".encode() + raw)
        self.process.stdin.flush()
        self.transcript.append({"sent": message})

    def receive(self) -> dict[str, Any]:
        assert self.process.stdout is not None
        length = None
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError(
                    "language server closed its output before responding"
                )
            if line == b"\r\n":
                break
            key, value = line.decode().strip().split(":", 1)
            if key.lower() == "content-length":
                length = int(value)
        if length is None:
            raise RuntimeError("language server omitted Content-Length")
        message = json.loads(self.process.stdout.read(length))
        self.transcript.append({"received": message})
        return message

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: dict[str, Any]) -> tuple[dict, dict]:
        self.sequence += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.sequence,
            "method": method,
            "params": params,
        }
        self.send(request)
        while True:
            message = self.receive()
            if message.get("id") == self.sequence and "method" not in message:
                if "error" in message:
                    raise RuntimeError(f"native LSP request failed: {message}")
                return request, message
            if "id" in message and "method" in message:
                if message["method"] == "workspace/configuration":
                    result: Any = [{} for _ in message["params"]["items"]]
                elif message["method"] == "workspace/workspaceFolders":
                    result = [{"uri": self.root_uri, "name": "fixture"}]
                elif message["method"] in (
                    "client/registerCapability",
                    "window/workDoneProgress/create",
                ):
                    result = None
                else:
                    raise RuntimeError(f"unhandled language server request: {message}")
                self.send({"jsonrpc": "2.0", "id": message["id"], "result": result})

    def close(self) -> None:
        try:
            self.request("shutdown", {})
            self.notify("exit", {})
            assert self.process.stdin is not None
            self.process.stdin.close()
            if self.process.wait() != 0:
                raise RuntimeError("language server exited unsuccessfully")
        finally:
            self.stderr.close()
            if self.process.poll() is None:
                self.process.terminate()
                self.process.wait()


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _source_paths(root: Path) -> list[Path]:
    return [
        path
        for path in sorted((root / "src").rglob("*"))
        if path.is_file() and path.suffix in (".py", ".ts")
    ]


class FixtureSession:
    """Track only the document lifetimes in one finite fixture request catalog."""

    def __init__(self, client: CaptureClient, root: Path, language: str) -> None:
        self.client, self.root, self.language = client, root, language
        self.sources = {
            path.relative_to(root).as_posix(): path.read_text()
            for path in _source_paths(root)
        }
        self.versions = {path: 1 for path in self.sources}
        self.lifetimes = {path: 1 for path in self.sources}
        self.open_paths = set(self.sources)
        self.prepared: dict[str, dict] = {}

    def open(self, path: str) -> None:
        self.client.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": (self.root / path).as_uri(),
                    "languageId": self.language,
                    "version": self.versions[path],
                    "text": self.sources[path],
                }
            },
        )

    def initialize(self) -> dict:
        options = (
            {"tsserver": {"path": os.environ["HASHMARKS_QA_TSSERVER"]}}
            if self.language == "typescript"
            else {}
        )
        _, response = self.client.request(
            "initialize",
            {
                "processId": None,
                "rootUri": self.client.root_uri,
                "workspaceFolders": [{"uri": self.client.root_uri, "name": "fixture"}],
                "capabilities": {
                    "general": {"positionEncodings": ["utf-16"]},
                    "textDocument": {"callHierarchy": {"dynamicRegistration": False}},
                },
                "initializationOptions": options,
            },
        )
        self.client.notify("initialized", {})
        for path in self.sources:
            self.open(path)
        return response["result"]["capabilities"]

    def action(self, row: dict) -> None:
        path, action = row["path"], row["action"]
        document = {"uri": (self.root / path).as_uri()}
        if action == "change":
            self.versions[path] += 1
            self.sources[path] = row["text"]
            self.client.notify(
                "textDocument/didChange",
                {
                    "textDocument": {**document, "version": self.versions[path]},
                    "contentChanges": [{"text": self.sources[path]}],
                },
            )
        elif action == "close":
            self.client.notify("textDocument/didClose", {"textDocument": document})
            self.sources[path] = (self.root / path).read_text()
            self.open_paths.remove(path)
        elif action == "open":
            self.lifetimes[path] += 1
            self.versions[path] = 1
            self.open_paths.add(path)
            self.open(path)
        else:
            raise ValueError("unknown QA lifecycle action")

    def request(self, row: dict) -> tuple[dict, dict]:
        if "prepared" in row:
            params = {"item": self.prepared[row["prepared"]]}
        else:
            params = {
                "textDocument": {"uri": (self.root / row["path"]).as_uri()},
                "position": row["position"],
            }
            if row["method"] == "textDocument/references":
                params["context"] = {"includeDeclaration": row["includeDeclaration"]}
            if "workDoneToken" in row:
                params["workDoneToken"] = row["workDoneToken"]
        request, response = self.client.request(row["method"], params)
        if row["method"] == "textDocument/prepareCallHierarchy":
            items = response["result"]
            assert len(items) == 1, f"fixture prepare must identify one item: {items}"
            self.prepared[row["name"]] = items[0]
        return request, response

    def documents(self) -> dict:
        return {
            path: {
                "text": text,
                "revision_kind": "utf8-document-text",
                "provenance": {
                    "producer_session": "fixture-session",
                    "document_lifetime": f"open-{self.lifetimes[path]}",
                    "document_version": self.versions[path],
                    "source_kind": "buffer" if path in self.open_paths else "disk",
                    "binding_basis": "producer-snapshot",
                },
            }
            for path, text in self.sources.items()
        }


def _collect(session: FixtureSession, source: Path, producer: str) -> list[dict]:
    capabilities = session.initialize()
    configuration = {
        "requests": json.loads((source / "requests.json").read_text()),
        "files": _configuration(source),
        "initialization": session.client.transcript[0]["sent"]["params"],
    }
    identity = (
        "sha256:"
        + hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    )
    captures = []
    for row in configuration["requests"]:
        if "action" in row:
            session.action(row)
            continue
        request, response = session.request(row)
        captures.append(
            {
                "name": row["name"],
                "subject": row["subject"],
                "capture": {
                    "schema": "hashmarks.lsp-relationship-capture.v1",
                    "producer": producer,
                    "configuration_identity": identity,
                    "request": request,
                    "response": response,
                    "capabilities": capabilities,
                    "position_encoding": capabilities.get("positionEncoding", "utf-16"),
                    "collection_state": "fresh-complete",
                    "documents": session.documents(),
                },
            }
        )
    return captures


def _configuration(root: Path) -> dict:
    return {
        path.name: path.read_text()
        for path in root.iterdir()
        if path.name in ("pyrightconfig.json", "tsconfig.json", "package.json")
    }


def _revisions(root: Path) -> dict:
    return {
        path.relative_to(root).as_posix(): hash_bytes(
            path.read_bytes(), domain=FILE_DOMAIN
        ).hash
        for path in _source_paths(root)
    }


def _metadata(root: Path, producer: str, version: str, revisions: dict) -> dict:
    runtime = (
        os.environ.get("HASHMARKS_QA_TSSERVER")
        if producer == "typescript-language-server"
        else None
    )
    return {
        "producer": producer,
        "producer_version": version,
        "typescript_runtime": runtime,
        "typescript_runtime_sha256": hashlib.sha256(
            Path(runtime).read_bytes()
        ).hexdigest()
        if runtime
        else None,
        "source_revisions": revisions,
        "original_root_uri": root.as_uri(),
        "configuration": _configuration(root),
        "captures_sha256": hashlib.sha256(
            (root / "captures.json").read_bytes()
        ).hexdigest(),
        "transcript_sha256": hashlib.sha256(
            (root / "transcript.json").read_bytes()
        ).hexdigest(),
        "qualification_authority": "external-capture-caller-claim",
    }


def capture_lsp(source: Path, destination: Path, language: str) -> None:
    """Retain raw responses, protocol transcript, and exact snapshot provenance."""
    shutil.copytree(source, destination)
    for name in ("captures.json", "capture.json", "transcript.json", "server.stderr"):
        (destination / name).unlink(missing_ok=True)
    executable = (
        "pyright-langserver" if language == "python" else "typescript-language-server"
    )
    tool = shutil.which(executable)
    if tool is None:
        raise RuntimeError(
            f"native evidence qualification requires installed {executable}"
        )
    version_tool = shutil.which("pyright") if language == "python" else tool
    version = subprocess.run(
        [str(version_tool), "--version"], capture_output=True, text=True, check=True
    ).stdout.strip()
    revisions = _revisions(destination)
    client = CaptureClient([tool, "--stdio"], destination)
    try:
        captures = _collect(
            FixtureSession(client, destination, language), source, executable
        )
    finally:
        client.close()
    assert revisions == _revisions(destination), "capture changed disk sources"
    _write(destination / "captures.json", captures)
    _write(destination / "transcript.json", client.transcript)
    _write(
        destination / "capture.json",
        _metadata(destination, executable, version, revisions),
    )
