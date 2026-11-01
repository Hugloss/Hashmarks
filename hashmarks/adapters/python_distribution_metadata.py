"""Translate explicitly supplied Python distribution metadata, without discovery."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections.abc import Mapping, Sequence
from email.parser import Parser
from pathlib import PurePosixPath
from typing import cast

_MAX_ARTIFACT_BYTES = 4_194_304
_MAX_METADATA_BYTES = 8_388_608
_FIELDS = frozenset({"node_id", "metadata", "record"})


def _text(raw: object, field: str) -> tuple[bytes, str]:
    if not isinstance(raw, bytes) or len(raw) > _MAX_ARTIFACT_BYTES:
        raise ValueError(f"Python distribution {field} requires bounded bytes")
    try:
        return raw, raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Python distribution {field} is not UTF-8") from exc


def _distribution_identity(raw: object) -> tuple[bytes, str, str]:
    data, text = _text(raw, "metadata")
    metadata = Parser().parsestr(text, headersonly=True)
    values: list[str] = []
    for name in ("Name", "Version"):
        headers = metadata.get_all(name, [])
        if len(headers) != 1 or not headers[0].strip():
            raise ValueError(f"Python distribution metadata requires one {name}")
        values.append(headers[0].strip())
    return data, values[0], values[1]


def _distribution_name(value: object) -> str:
    return re.sub(r"[-_.]+", "-", str(value)).lower()


def _record_modules(text: str) -> set[str]:
    modules: set[str] = set()
    try:
        rows = csv.reader(io.StringIO(text), strict=True)
        for row in rows:
            if len(row) != 3:
                raise ValueError("Python distribution RECORD requires three columns")
            path = PurePosixPath(row[0])
            if path.is_absolute() or ".." in path.parts or path.suffix != ".py":
                continue
            parts = list(path.with_suffix("").parts)
            if parts and parts[-1] == "__init__":
                parts.pop()
            if parts and all(part.isidentifier() for part in parts):
                modules.add(".".join(parts))
    except csv.Error as exc:
        raise ValueError("invalid Python distribution RECORD") from exc
    return modules


def _source(node_id: str, field: str, raw: bytes) -> dict[str, object]:
    identity = hashlib.sha256(node_id.encode()).hexdigest()[:24]
    return {
        "source_id": f"python:{identity}:{field}",
        "kind": f"python-distribution-{field}",
        "authorities": ["module-ownership"],
        "context": "lock",
        "completeness": "complete",
        "truncation": "complete",
        "producer_digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
    }


def _selection(
    raw: Mapping[str, object], selections: Sequence[Mapping[str, object]]
) -> Mapping[str, object]:
    if set(raw) - _FIELDS:
        raise ValueError("unknown Python distribution metadata field")
    matches = [row for row in selections if row["node_id"] == raw.get("node_id")]
    if len(matches) != 1:
        raise ValueError("Python distribution requires one exact dependency selection")
    return matches[0]


def _ownership_inputs(
    raw: Mapping[str, object], selection: Mapping[str, object]
) -> tuple[set[str], list[dict[str, object]]]:
    metadata, name, version = _distribution_identity(raw.get("metadata"))
    if (
        _distribution_name(name) != _distribution_name(selection["component_id"])
        or version != selection["version"]
    ):
        raise ValueError(
            "Python distribution metadata does not match dependency selection"
        )
    node_id = str(selection["node_id"])
    sources = [_source(node_id, "metadata", metadata)]
    if raw.get("record") is None:
        return set(), sources
    data, text = _text(raw["record"], "record")
    sources.append(_source(node_id, "record", data))
    return _record_modules(text), sources


def _validate_metadata_entries(distributions: Sequence[Mapping[str, object]]) -> None:
    if not isinstance(distributions, Sequence) or isinstance(
        distributions, (str, bytes)
    ):
        raise ValueError("Python distribution metadata must be a sequence")
    if len(distributions) > 64:
        raise ValueError("Python distribution metadata exceeds 64 selections")
    if any(not isinstance(row, Mapping) for row in distributions):
        raise ValueError("Python distribution metadata entries must be objects")
    total = sum(
        len(value)
        for row in distributions
        for value in row.values()
        if isinstance(value, bytes)
    )
    if total > _MAX_METADATA_BYTES:
        raise ValueError("Python distribution metadata exceeds aggregate byte bound")


def add_python_distribution_metadata(
    snapshot: dict[str, object], distributions: Sequence[Mapping[str, object]]
) -> None:
    """Add observed module claims to the existing raw dependency packet in place.

    Artifact fingerprints bind supplied bytes, not installed-environment identity
    or authenticity. RECORD does not close all runtime owners.
    """
    _validate_metadata_entries(distributions)
    if not distributions:
        return
    selections = cast("Sequence[Mapping[str, object]]", snapshot["selections"])
    sources = cast("list[dict[str, object]]", snapshot["evidence_sources"])
    owners: dict[str, set[str]] = {}
    evidence: dict[str, set[str]] = {}
    seen: set[str] = set()
    for raw in distributions:
        selection = _selection(raw, selections)
        node_id = str(selection["node_id"])
        if node_id in seen:
            raise ValueError("duplicate Python distribution selection")
        seen.add(node_id)
        modules, observed_sources = _ownership_inputs(raw, selection)
        sources.extend(observed_sources)
        source_ids = {str(row["source_id"]) for row in observed_sources}
        for module in modules:
            owners.setdefault(module, set()).add(node_id)
            evidence.setdefault(module, set()).update(source_ids)
    snapshot["module_ownership"] = [
        {
            "module": module,
            "context": "lock",
            "owners": sorted(owners[module]),
            "completeness": "incomplete",
            "evidence_sources": sorted(evidence[module]),
        }
        for module in sorted(owners)
    ]
    cast("list[dict[str, object]]", snapshot["coverage"]).append(
        {
            "context": "lock",
            "kind": "module-ownership",
            "completeness": "incomplete",
            "truncation": "complete",
            "evidence_sources": [
                str(row["source_id"])
                for row in sources
                if "module-ownership" in cast("Sequence[str]", row["authorities"])
            ],
        }
    )
    producer = cast("dict[str, object]", snapshot["producer"])
    producer["adapter_semantics"] = "hashmarks.uv-dependency-adapter.v2"
    producer["module_ownership_scope"] = "supplied-python-distribution-metadata"
    producer["module_ownership_limits"] = [
        "producer-and-environment-authority-caller-claimed",
        "namespace-and-other-providers-not-exhaustive",
        "dynamic-import-and-loader-behavior-not-observed",
        "stubs-native-extensions-and-top-level-declarations-not-runtime-owner-proof",
    ]
