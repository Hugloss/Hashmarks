from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from hashmarks._command_output import log_command_output

logger = logging.getLogger(__name__)

SCHEMA = "hashmarks.splunk-csv-dogfood.v1"
EXPECTED_HEADER = (
    "_serial",
    "_time",
    "source",
    "sourcetype",
    "host",
    "index",
    "splunk_server",
    "_raw",
)
_RECORD_START = re.compile(r'^"[^"]*","\d{4}-\d{2}-\d{2}T')
_MODULE = re.compile(r"\bname=([A-Za-z_][A-Za-z0-9_.]*)")
_TRACEBACK = re.compile(
    r'File\s+"?([^",]+)"?,\s+line\s+(\d+),\s+in\s+([A-Za-z_][A-Za-z0-9_]*)'
)
_MAX_SCOPE_VALUES = 32
_DEFAULT_MAX_ANCHORS = 256


@dataclass
class _ModuleStats:
    count: int = 0
    strict_valid: int = 0
    recovered: int = 0
    widened: int = 0
    first_time: str | None = None
    last_time: str | None = None
    sample_event_ids: list[str] = field(default_factory=list)

    def observe(
        self,
        *,
        timestamp: str,
        parser_state: str,
        widened: bool,
        event_id: str,
    ) -> None:
        self.count += 1
        self.strict_valid += int(parser_state == "strict-valid")
        self.recovered += int(parser_state == "recovered")
        self.widened += int(widened)
        self.first_time = (
            timestamp if self.first_time is None else min(self.first_time, timestamp)
        )
        self.last_time = (
            timestamp if self.last_time is None else max(self.last_time, timestamp)
        )
        if len(self.sample_event_ids) < 3:
            self.sample_event_ids.append(event_id)


@dataclass(frozen=True)
class _ParsedRecord:
    fields: tuple[str, ...]
    raw: str
    parser_state: str
    widened: bool


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _logical_records(handle: TextIO):
    current: list[str] = []
    ordinal = 0
    for line in handle:
        if _RECORD_START.match(line):
            if current:
                yield ordinal, "".join(current)
                ordinal += 1
            current = [line]
        elif current:
            current.append(line)
        elif line.strip():
            raise ValueError("non-empty content appeared before first Splunk record")
    if current:
        yield ordinal, "".join(current)


def _one_csv_row(text: str, *, strict: bool) -> list[str]:
    rows = list(csv.reader(io.StringIO(text), strict=strict))
    if len(rows) != 1:
        raise csv.Error("logical record did not parse to exactly one CSV row")
    return rows[0]


def _parse_record(text: str) -> _ParsedRecord | None:
    strict_valid = False
    try:
        strict_row = _one_csv_row(text, strict=True)
        strict_valid = len(strict_row) == len(EXPECTED_HEADER)
    except csv.Error:
        strict_row = []
    try:
        row = _one_csv_row(text, strict=False)
    except csv.Error:
        return None
    if len(row) < len(EXPECTED_HEADER):
        return None
    widened = len(row) > len(EXPECTED_HEADER)
    raw = row[7] if not widened else ",".join(row[7:])
    return _ParsedRecord(
        fields=tuple(row[:7]),
        raw=raw,
        parser_state="strict-valid" if strict_valid and not widened else "recovered",
        widened=widened,
    )


def _bounded_value(values: set[str], value: str) -> bool:
    if not value or value in values:
        return False
    if len(values) >= _MAX_SCOPE_VALUES:
        return True
    values.add(value)
    return False


def _event_id(ordinal: int, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"event:{ordinal:06d}:sha256:{digest}"


def _physical_line_count(text: str) -> int:
    return text.count("\n") + int(bool(text) and not text.endswith("\n"))


def _stats_metadata(stats: _ModuleStats) -> dict[str, object]:
    return {
        "observed_count": stats.count,
        "strict_valid_count": stats.strict_valid,
        "recovered_count": stats.recovered,
        "widened_count": stats.widened,
        "first_time": stats.first_time,
        "last_time": stats.last_time,
        "sample_event_ids": stats.sample_event_ids,
    }


def _module_anchor(module: str, stats: _ModuleStats) -> dict[str, object]:
    return {
        "anchor_id": f"module:{module}",
        "module": module,
        "metadata": _stats_metadata(stats),
    }


def _traceback_anchor(
    key: tuple[str, int, str],
    stats: _ModuleStats,
) -> dict[str, object]:
    path, line, symbol = key
    return {
        "anchor_id": f"traceback:{path}:{line}:{symbol}",
        "path": path,
        "line": line,
        "symbol": symbol,
        "metadata": {
            "kind": "python-traceback-frame",
            **_stats_metadata(stats),
        },
    }


@dataclass
class _CollectionState:
    modules: dict[str, _ModuleStats] = field(default_factory=dict)
    tracebacks: dict[tuple[str, int, str], _ModuleStats] = field(default_factory=dict)
    sourcetypes: set[str] = field(default_factory=set)
    indexes: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    scope_values_truncated: bool = False
    event_count: int = 0
    strict_valid_count: int = 0
    recovered_count: int = 0
    malformed_count: int = 0
    widened_count: int = 0
    physical_lines: int = 1
    first_time: str | None = None
    last_time: str | None = None

    def observe(
        self,
        ordinal: int,
        text: str,
        parsed: _ParsedRecord | None,
    ) -> None:
        self.event_count += 1
        self.physical_lines += _physical_line_count(text)
        if parsed is None:
            self.malformed_count += 1
            return
        self._observe_parsed(ordinal, text, parsed)

    def _observe_parsed(
        self,
        ordinal: int,
        text: str,
        parsed: _ParsedRecord,
    ) -> None:
        self.strict_valid_count += int(parsed.parser_state == "strict-valid")
        self.recovered_count += int(parsed.parser_state == "recovered")
        self.widened_count += int(parsed.widened)
        _serial, timestamp, source, sourcetype, _host, index, _server = parsed.fields
        self._observe_scope(timestamp, source, sourcetype, index)
        event_id = _event_id(ordinal, text)
        self._observe_module(parsed, timestamp, event_id)
        self._observe_traceback(parsed, timestamp, event_id)

    def _observe_scope(
        self,
        timestamp: str,
        source: str,
        sourcetype: str,
        index: str,
    ) -> None:
        self.first_time = (
            timestamp if self.first_time is None else min(self.first_time, timestamp)
        )
        self.last_time = (
            timestamp if self.last_time is None else max(self.last_time, timestamp)
        )
        self.scope_values_truncated |= _bounded_value(self.sources, source)
        self.scope_values_truncated |= _bounded_value(self.sourcetypes, sourcetype)
        self.scope_values_truncated |= _bounded_value(self.indexes, index)

    def _observe_module(
        self,
        parsed: _ParsedRecord,
        timestamp: str,
        event_id: str,
    ) -> None:
        match = _MODULE.search(parsed.raw)
        if match is None:
            return
        module = match.group(1).strip(".")
        stats = self.modules.setdefault(module, _ModuleStats())
        stats.observe(
            timestamp=timestamp,
            parser_state=parsed.parser_state,
            widened=parsed.widened,
            event_id=event_id,
        )

    def _observe_traceback(
        self,
        parsed: _ParsedRecord,
        timestamp: str,
        event_id: str,
    ) -> None:
        match = _TRACEBACK.search(parsed.raw)
        if match is None:
            return
        key = (match.group(1), int(match.group(2)), match.group(3))
        stats = self.tracebacks.setdefault(key, _ModuleStats())
        stats.observe(
            timestamp=timestamp,
            parser_state=parsed.parser_state,
            widened=parsed.widened,
            event_id=event_id,
        )


@dataclass(frozen=True)
class _AnchorSelection:
    anchors: list[dict[str, object]]
    traceback_observed: int
    traceback_emitted: int
    module_observed: int
    module_emitted: int
    observed: int
    truncated: bool


def _validate_header(handle: TextIO) -> None:
    header = tuple(next(csv.reader([handle.readline()])))
    if header != EXPECTED_HEADER:
        raise ValueError("Splunk CSV header must be " + ",".join(EXPECTED_HEADER))


def _collect_stream(path: Path) -> _CollectionState:
    state = _CollectionState()
    with path.open("r", encoding="utf-8", newline="") as handle:
        _validate_header(handle)
        for ordinal, text in _logical_records(handle):
            state.observe(ordinal, text, _parse_record(text))
    return state


def _select_anchors(
    state: _CollectionState,
    max_anchors: int,
) -> _AnchorSelection:
    tracebacks = sorted(
        state.tracebacks.items(),
        key=lambda item: (-item[1].count, item[0]),
    )
    modules = sorted(
        state.modules.items(),
        key=lambda item: (-item[1].count, item[0]),
    )
    selected_tracebacks = tracebacks[:max_anchors]
    selected_modules = modules[: max_anchors - len(selected_tracebacks)]
    anchors = [_traceback_anchor(key, stats) for key, stats in selected_tracebacks]
    anchors.extend(_module_anchor(module, stats) for module, stats in selected_modules)
    observed = len(tracebacks) + len(modules)
    return _AnchorSelection(
        anchors=anchors,
        traceback_observed=len(tracebacks),
        traceback_emitted=len(selected_tracebacks),
        module_observed=len(modules),
        module_emitted=len(selected_modules),
        observed=observed,
        truncated=observed > len(anchors),
    )


def _bundle(
    source_sha256: str,
    state: _CollectionState,
    selection: _AnchorSelection,
) -> dict[str, object]:
    return {
        "bundle_id": "splunk-export:" + source_sha256.removeprefix("sha256:")[:32],
        "producer": {
            "kind": "splunk-style",
            "format": "csv-export",
        },
        "provenance": {
            "source_sha256": source_sha256,
            "logical_event_count": state.event_count,
            "physical_line_count": state.physical_lines,
            "strict_valid_count": state.strict_valid_count,
            "recovered_count": state.recovered_count,
            "malformed_count": state.malformed_count,
            "widened_count": state.widened_count,
        },
        "completeness": "unknown",
        "truncation": "truncated" if selection.truncated else "unknown",
        "scope": {
            "time_start": state.first_time,
            "time_end": state.last_time,
            "sources": sorted(state.sources),
            "sourcetypes": sorted(state.sourcetypes),
            "indexes": sorted(state.indexes),
            "scope_values_truncated": state.scope_values_truncated,
        },
        "anchors": selection.anchors,
    }


def _report(
    path: Path,
    source_sha256: str,
    state: _CollectionState,
    selection: _AnchorSelection,
) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "source": {
            "path": str(path),
            "sha256": source_sha256,
        },
        "summary": {
            "events": state.event_count,
            "physical_lines": state.physical_lines,
            "strict_valid": state.strict_valid_count,
            "recovered": state.recovered_count,
            "malformed": state.malformed_count,
            "widened": state.widened_count,
            "traceback_anchors_observed": selection.traceback_observed,
            "traceback_anchors_emitted": selection.traceback_emitted,
            "module_anchors_observed": selection.module_observed,
            "module_anchors_emitted": selection.module_emitted,
            "anchors_observed": selection.observed,
            "anchors_emitted": len(selection.anchors),
            "anchors_truncated": selection.truncated,
            "scope_values_truncated": state.scope_values_truncated,
        },
        "bundle": _bundle(source_sha256, state, selection),
    }


def collect(
    path: Path, *, max_anchors: int = _DEFAULT_MAX_ANCHORS
) -> dict[str, object]:
    if max_anchors < 1 or max_anchors > _DEFAULT_MAX_ANCHORS:
        raise ValueError(f"max_anchors must be between 1 and {_DEFAULT_MAX_ANCHORS}")
    source_sha256 = _sha256_file(path)
    state = _collect_stream(path)
    selection = _select_anchors(state, max_anchors)
    return _report(path, source_sha256, state, selection)


def _path_mappings(values: list[str]) -> list[dict[str, str]]:
    mappings = []
    for value in values:
        if "=" not in value:
            raise ValueError("path mapping must use EXTERNAL_PREFIX=REPOSITORY_PREFIX")
        external_prefix, repository_prefix = value.split("=", 1)
        if not external_prefix:
            raise ValueError("path mapping external prefix must not be empty")
        mappings.append(
            {
                "external_prefix": external_prefix,
                "repository_prefix": repository_prefix,
            }
        )
    return mappings


def correlate(
    workspace: Path,
    report: dict[str, object],
    *,
    path_mappings: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    from hashmarks.codemap import CodeMap

    bundle = report.get("bundle")
    if not isinstance(bundle, dict):
        raise ValueError("dogfood report has no bundle")
    with CodeMap(workspace) as codemap:
        sync = codemap.sync()
        packet = codemap.correlate_evidence(
            [bundle],
            path_mappings=path_mappings,
            include_relationships=False,
        )
    states: dict[str, int] = {}
    for anchor in packet["bundles"][0]["anchors"]:
        state = str(anchor["resolution"]["state"])
        states[state] = states.get(state, 0) + 1
    return {
        "sync": sync,
        "resolution_states": states,
        "correlation_identity": packet["correlation_identity"],
        "authority": packet["authority"],
        "interpretation_authority": packet["interpretation_authority"],
        "causation": packet["causation"],
        "packet": packet,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stream a Splunk CSV export into bounded producer-neutral "
            "Hashmarks dogfood evidence."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--max-anchors", type=int, default=_DEFAULT_MAX_ANCHORS)
    parser.add_argument(
        "--path-mapping",
        action="append",
        default=[],
        metavar="EXTERNAL=REPOSITORY",
    )
    args = parser.parse_args()
    report = collect(args.input, max_anchors=args.max_anchors)
    if args.workspace is not None:
        report["correlation"] = correlate(
            args.workspace,
            report,
            path_mappings=_path_mappings(args.path_mapping),
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    log_command_output(
        logger,
        json.dumps(
            {
                "schema": SCHEMA,
                **report["summary"],
                "output": str(args.output),
            },
            sort_keys=True,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
