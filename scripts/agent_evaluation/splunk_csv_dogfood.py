from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

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


def collect(
    path: Path, *, max_anchors: int = _DEFAULT_MAX_ANCHORS
) -> dict[str, object]:
    if max_anchors < 1 or max_anchors > _DEFAULT_MAX_ANCHORS:
        raise ValueError(f"max_anchors must be between 1 and {_DEFAULT_MAX_ANCHORS}")
    source_sha256 = _sha256_file(path)
    modules: dict[str, _ModuleStats] = {}
    tracebacks: dict[tuple[str, int, str], _ModuleStats] = {}
    sourcetypes: set[str] = set()
    indexes: set[str] = set()
    sources: set[str] = set()
    scope_values_truncated = False
    event_count = 0
    strict_valid_count = 0
    recovered_count = 0
    malformed_count = 0
    widened_count = 0
    physical_lines = 1
    first_time: str | None = None
    last_time: str | None = None

    with path.open("r", encoding="utf-8", newline="") as handle:
        header = tuple(next(csv.reader([handle.readline()])))
        if header != EXPECTED_HEADER:
            raise ValueError("Splunk CSV header must be " + ",".join(EXPECTED_HEADER))
        for ordinal, text in _logical_records(handle):
            event_count += 1
            physical_lines += _physical_line_count(text)
            parsed = _parse_record(text)
            if parsed is None:
                malformed_count += 1
                continue
            strict_valid_count += int(parsed.parser_state == "strict-valid")
            recovered_count += int(parsed.parser_state == "recovered")
            widened_count += int(parsed.widened)
            serial, timestamp, source, sourcetype, _host, index, _server = parsed.fields
            del serial
            first_time = timestamp if first_time is None else min(first_time, timestamp)
            last_time = timestamp if last_time is None else max(last_time, timestamp)
            scope_values_truncated |= _bounded_value(sources, source)
            scope_values_truncated |= _bounded_value(sourcetypes, sourcetype)
            scope_values_truncated |= _bounded_value(indexes, index)
            event_id = _event_id(ordinal, text)
            module_match = _MODULE.search(parsed.raw)
            if module_match is not None:
                module = module_match.group(1).strip(".")
                stats = modules.setdefault(module, _ModuleStats())
                stats.observe(
                    timestamp=timestamp,
                    parser_state=parsed.parser_state,
                    widened=parsed.widened,
                    event_id=event_id,
                )
            traceback_match = _TRACEBACK.search(parsed.raw)
            if traceback_match is not None:
                key = (
                    traceback_match.group(1),
                    int(traceback_match.group(2)),
                    traceback_match.group(3),
                )
                stats = tracebacks.setdefault(key, _ModuleStats())
                stats.observe(
                    timestamp=timestamp,
                    parser_state=parsed.parser_state,
                    widened=parsed.widened,
                    event_id=event_id,
                )

    ranked_tracebacks = sorted(
        tracebacks.items(),
        key=lambda item: (-item[1].count, item[0]),
    )
    ranked_modules = sorted(
        modules.items(),
        key=lambda item: (-item[1].count, item[0]),
    )
    selected_tracebacks = ranked_tracebacks[:max_anchors]
    module_slots = max_anchors - len(selected_tracebacks)
    selected_modules = ranked_modules[:module_slots]
    anchors = [_traceback_anchor(key, stats) for key, stats in selected_tracebacks]
    anchors.extend(_module_anchor(module, stats) for module, stats in selected_modules)
    observed_anchors = len(ranked_tracebacks) + len(ranked_modules)
    anchors_truncated = observed_anchors > len(anchors)
    bundle = {
        "bundle_id": "splunk-export:" + source_sha256.removeprefix("sha256:")[:32],
        "producer": {
            "kind": "splunk-style",
            "format": "csv-export",
        },
        "provenance": {
            "source_sha256": source_sha256,
            "logical_event_count": event_count,
            "physical_line_count": physical_lines,
            "strict_valid_count": strict_valid_count,
            "recovered_count": recovered_count,
            "malformed_count": malformed_count,
            "widened_count": widened_count,
        },
        "completeness": "unknown",
        "truncation": "truncated" if anchors_truncated else "unknown",
        "scope": {
            "time_start": first_time,
            "time_end": last_time,
            "sources": sorted(sources),
            "sourcetypes": sorted(sourcetypes),
            "indexes": sorted(indexes),
            "scope_values_truncated": scope_values_truncated,
        },
        "anchors": anchors,
    }
    return {
        "schema": SCHEMA,
        "source": {
            "path": str(path),
            "sha256": source_sha256,
        },
        "summary": {
            "events": event_count,
            "physical_lines": physical_lines,
            "strict_valid": strict_valid_count,
            "recovered": recovered_count,
            "malformed": malformed_count,
            "widened": widened_count,
            "traceback_anchors_observed": len(ranked_tracebacks),
            "traceback_anchors_emitted": len(selected_tracebacks),
            "module_anchors_observed": len(ranked_modules),
            "module_anchors_emitted": len(selected_modules),
            "anchors_observed": observed_anchors,
            "anchors_emitted": len(anchors),
            "anchors_truncated": anchors_truncated,
            "scope_values_truncated": scope_values_truncated,
        },
        "bundle": bundle,
    }


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
    print(  # noqa: T201 - intentional command output
        json.dumps(
            {
                "schema": SCHEMA,
                **report["summary"],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
