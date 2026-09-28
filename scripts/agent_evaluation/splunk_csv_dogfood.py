from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from typing import TextIO

from hashmarks._command_output import log_command_output
from hashmarks.codemap import (
    evidence_component_fits,
    evidence_request_budget_fits,
    validate_evidence_locator_claim,
)

logger = logging.getLogger(__name__)

_CSV_FIELD_LIMIT_LOCK = Lock()

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
_TIMESTAMP_START = re.compile(r"^\d{4}-\d{2}-\d{2}T")
_MODULE = re.compile(r'\bname=([^"\s]+)')
_TRACEBACK = re.compile(
    r'File\s+(?:"([^"]+)"|"?([^",\r\n]+)"?),'
    r'\s+line\s+(\d+)(?:,\s+in\s+([^"\r\n]+))?'
    r'(?="?(?:\r?\n|$))'
)
_HANDLING_IDENT = re.compile(r'\bhandling_ident=([^"\s]+)')
_COMMIT_VALUE = re.compile(r'\bcommit=([^"\s]+)')
_MAX_SCOPE_VALUES = 32
_MAX_ANCHOR_CONTEXT_VALUES = 8
_MAX_IDENTITY_SAMPLES = 3
_MAX_UNLOCATED_SAMPLE_EVENT_IDS = 3
_DEFAULT_MAX_ANCHORS = 256
_NORMALIZED_OBSERVATION_SCHEMA = "hashmarks.splunk-normalized-observation.v1"
_EVIDENCE_PROJECTION_SCHEMA = "hashmarks.splunk-evidence-projection.v3"
_PRODUCER_PAYLOAD_VALIDATION_STATE = "not-assessed"


@dataclass(frozen=True)
class _OpaqueRuntimeContext:
    handling_ident: str | None
    commit_value: str | None


@dataclass
class _TimeBounds:
    lexical_start: str | None = None
    lexical_end: str | None = None
    instant_start: tuple[datetime, str] | None = None
    instant_end: tuple[datetime, str] | None = None
    unparseable_count: int = 0

    def observe(self, timestamp: str) -> None:
        self.lexical_start = (
            timestamp
            if self.lexical_start is None
            else min(self.lexical_start, timestamp)
        )
        self.lexical_end = (
            timestamp if self.lexical_end is None else max(self.lexical_end, timestamp)
        )
        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError:
            self.unparseable_count += 1
            return
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            self.unparseable_count += 1
            return
        instant_key = (parsed.astimezone(timezone.utc), timestamp)
        self.instant_start = (
            instant_key
            if self.instant_start is None
            else min(self.instant_start, instant_key)
        )
        self.instant_end = (
            instant_key
            if self.instant_end is None
            else max(self.instant_end, instant_key)
        )

    @property
    def ordering_state(self) -> str:
        if self.lexical_start is None:
            return "not-observed"
        if self.unparseable_count:
            return "lexical-fallback"
        return "instant-aware"

    @property
    def start(self) -> str | None:
        if self.unparseable_count or self.instant_start is None:
            return self.lexical_start
        return self.instant_start[1]

    @property
    def end(self) -> str | None:
        if self.unparseable_count or self.instant_end is None:
            return self.lexical_end
        return self.instant_end[1]


@dataclass
class _ModuleStats:
    count: int = 0
    strict_valid: int = 0
    recovered: int = 0
    widened: int = 0
    time_bounds: _TimeBounds = field(default_factory=_TimeBounds)
    sample_occurrence_ids: list[str] = field(default_factory=list)
    sample_observation_identities: list[str] = field(default_factory=list)
    handling_idents: set[str] = field(default_factory=set)
    commit_values: set[str] = field(default_factory=set)
    handling_idents_truncated: bool = False
    commit_values_truncated: bool = False

    def observe(
        self,
        *,
        timestamp: str,
        parser_state: str,
        widened: bool,
        occurrence_id: str,
        observation_identity: str,
        context: _OpaqueRuntimeContext,
    ) -> None:
        self.count += 1
        self.strict_valid += int(parser_state == "strict-valid")
        self.recovered += int(parser_state == "recovered")
        self.widened += int(widened)
        self.time_bounds.observe(timestamp)
        if len(self.sample_occurrence_ids) < _MAX_IDENTITY_SAMPLES:
            self.sample_occurrence_ids.append(occurrence_id)
        _bounded_sorted_sample(
            self.sample_observation_identities,
            observation_identity,
            limit=_MAX_IDENTITY_SAMPLES,
        )
        self.handling_idents_truncated |= _bounded_value(
            self.handling_idents,
            context.handling_ident,
            limit=_MAX_ANCHOR_CONTEXT_VALUES,
        )
        self.commit_values_truncated |= _bounded_value(
            self.commit_values,
            context.commit_value,
            limit=_MAX_ANCHOR_CONTEXT_VALUES,
        )


@dataclass(frozen=True)
class _ParsedRecord:
    fields: tuple[str, ...]
    raw: str
    parser_state: str
    widened: bool


def _snapshot_source(source: Path, snapshot: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as source_handle, snapshot.open("wb") as snapshot_handle:
        for block in iter(lambda: source_handle.read(1024 * 1024), b""):
            digest.update(block)
            snapshot_handle.write(block)
    return "sha256:" + digest.hexdigest()


def _starts_logical_record(line: str) -> bool:
    """Recognize a Splunk row from its parsed stable CSV prefix."""
    try:
        rows = list(csv.reader([line], strict=False))
    except csv.Error:
        return False
    if len(rows) != 1:
        return False
    row = rows[0]
    if len(row) < len(EXPECTED_HEADER):
        return False
    return bool(_TIMESTAMP_START.match(row[1]))


def _logical_records(handle: TextIO):
    current: list[str] = []
    ordinal = 0
    for line in handle:
        if _starts_logical_record(line):
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


def _bounded_value(
    values: set[str],
    value: str | None,
    *,
    limit: int = _MAX_SCOPE_VALUES,
) -> bool:
    if not value or value in values:
        return False
    if len(values) < limit:
        values.add(value)
        return False

    largest = max(values)
    if value < largest:
        values.remove(largest)
        values.add(value)
    return True


def _bounded_sorted_sample(values: list[str], value: str, *, limit: int) -> None:
    if value in values:
        return
    values.append(value)
    values.sort()
    del values[limit:]


def _identity_json(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _normalized_observation_identity(parsed: _ParsedRecord) -> str:
    _serial, timestamp, source, sourcetype, host, index, server = parsed.fields
    return _identity_json(
        {
            "schema": _NORMALIZED_OBSERVATION_SCHEMA,
            "_time": timestamp,
            "source": source,
            "sourcetype": sourcetype,
            "host": host,
            "index": index,
            "splunk_server": server,
            "_raw": parsed.raw,
        }
    )


def _opaque_runtime_context(raw: str) -> _OpaqueRuntimeContext:
    handling_match = _HANDLING_IDENT.search(raw)
    commit_match = _COMMIT_VALUE.search(raw)
    return _OpaqueRuntimeContext(
        handling_ident=(handling_match.group(1) if handling_match else None),
        commit_value=(commit_match.group(1) if commit_match else None),
    )


def _occurrence_id(ordinal: int, text: str) -> str:
    """Artifact-local source occurrence reference; not semantic event identity."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"event:{ordinal:06d}:sha256:{digest}"


def _physical_line_count(text: str) -> int:
    return text.count("\n") + int(bool(text) and not text.endswith("\n"))


def _stats_metadata(stats: _ModuleStats) -> dict[str, object]:
    runtime_context = {
        "handling_ident_values": [],
        "handling_ident_values_truncated": True,
        "commit_values": [],
        "commit_values_truncated": True,
        "values_truncated": True,
    }
    metadata: dict[str, object] = {
        "observed_count": stats.count,
        "strict_valid_count": stats.strict_valid,
        "recovered_count": stats.recovered,
        "widened_count": stats.widened,
        "first_time": stats.time_bounds.start,
        "last_time": stats.time_bounds.end,
        "time_ordering_state": stats.time_bounds.ordering_state,
        "timestamp_parse_failure_count": stats.time_bounds.unparseable_count,
        "sample_event_ids": stats.sample_occurrence_ids,
        "sample_occurrence_ids": stats.sample_occurrence_ids,
        "sample_observation_identities": stats.sample_observation_identities,
        "csv_parsing": {
            "strict_valid_count": stats.strict_valid,
            "recovered_count": stats.recovered,
            "widened_count": stats.widened,
        },
        "producer_payload_validation": {
            "state": _PRODUCER_PAYLOAD_VALIDATION_STATE,
        },
        "runtime_context": runtime_context,
        "metadata_values_truncated": True,
    }
    handling_truncated = stats.handling_idents_truncated
    commit_truncated = stats.commit_values_truncated
    metadata_truncated = False

    for value in sorted(stats.handling_idents):
        runtime_context["handling_ident_values"].append(value)
        if not evidence_component_fits(metadata):
            runtime_context["handling_ident_values"].pop()
            handling_truncated = True
            metadata_truncated = True

    for value in sorted(stats.commit_values):
        runtime_context["commit_values"].append(value)
        if not evidence_component_fits(metadata):
            runtime_context["commit_values"].pop()
            commit_truncated = True
            metadata_truncated = True

    runtime_context["handling_ident_values_truncated"] = handling_truncated
    runtime_context["commit_values_truncated"] = commit_truncated
    runtime_context["values_truncated"] = handling_truncated or commit_truncated

    if not evidence_component_fits(metadata):
        metadata["first_time"] = None
        metadata["last_time"] = None
        metadata_truncated = True

    if metadata_truncated:
        metadata["metadata_values_truncated"] = True
    else:
        metadata.pop("metadata_values_truncated", None)

    if not evidence_component_fits(metadata):
        raise ValueError(
            "Splunk anchor metadata could not fit evidence component budget"
        )
    return metadata


def _module_anchor(module: str, stats: _ModuleStats) -> dict[str, object]:
    anchor_identity = _identity_json(
        {
            "kind": "module",
            "module": module,
        }
    )
    return {
        "anchor_id": f"module:{anchor_identity}",
        "module": module,
        "metadata": _stats_metadata(stats),
    }


def _traceback_anchor(
    key: tuple[str, int, str],
    stats: _ModuleStats,
) -> dict[str, object]:
    path, line, symbol = key
    locator_claim: dict[str, object] = {
        "kind": "python-traceback-frame",
        "path": path,
        "line": line,
    }
    if symbol:
        locator_claim["symbol"] = symbol
    anchor_identity = _identity_json(locator_claim)
    return {
        "anchor_id": f"traceback:{anchor_identity}",
        "path": path,
        "line": line,
        **({"symbol": symbol} if symbol else {}),
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
    hosts: set[str] = field(default_factory=set)
    splunk_servers: set[str] = field(default_factory=set)
    scope_values_truncated: bool = False
    event_count: int = 0
    strict_valid_count: int = 0
    recovered_count: int = 0
    malformed_count: int = 0
    widened_count: int = 0
    events_with_extracted_locator: int = 0
    events_without_extracted_locator: int = 0
    module_locator_occurrences: int = 0
    traceback_locator_occurrences: int = 0
    unlocated_sample_occurrence_ids: list[str] = field(default_factory=list)
    unlocated_sample_observation_identities: list[str] = field(default_factory=list)
    physical_lines: int = 1
    record_framing_state: str = "native-csv"
    time_bounds: _TimeBounds = field(default_factory=_TimeBounds)

    @property
    def context_values_truncated(self) -> bool:
        stats = [*self.modules.values(), *self.tracebacks.values()]
        return any(
            item.handling_idents_truncated or item.commit_values_truncated
            for item in stats
        )

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
        _serial, timestamp, source, sourcetype, host, index, server = parsed.fields
        self._observe_scope(timestamp, source, sourcetype, host, index, server)
        occurrence_id = _occurrence_id(ordinal, text)
        observation_identity = _normalized_observation_identity(parsed)
        context = _opaque_runtime_context(parsed.raw)
        module_found = self._observe_module(
            parsed,
            timestamp,
            occurrence_id,
            observation_identity,
            context,
        )
        traceback_occurrences = self._observe_tracebacks(
            parsed,
            timestamp,
            occurrence_id,
            observation_identity,
            context,
        )
        locator_occurrences = int(module_found) + traceback_occurrences
        self.module_locator_occurrences += int(module_found)
        self.traceback_locator_occurrences += traceback_occurrences
        if locator_occurrences:
            self.events_with_extracted_locator += 1
        else:
            self.events_without_extracted_locator += 1
            if (
                len(self.unlocated_sample_occurrence_ids)
                < _MAX_UNLOCATED_SAMPLE_EVENT_IDS
            ):
                self.unlocated_sample_occurrence_ids.append(occurrence_id)
            _bounded_sorted_sample(
                self.unlocated_sample_observation_identities,
                observation_identity,
                limit=_MAX_UNLOCATED_SAMPLE_EVENT_IDS,
            )

    def _observe_scope(
        self,
        timestamp: str,
        source: str,
        sourcetype: str,
        host: str,
        index: str,
        server: str,
    ) -> None:
        self.time_bounds.observe(timestamp)
        self.scope_values_truncated |= _bounded_value(self.sources, source)
        self.scope_values_truncated |= _bounded_value(self.sourcetypes, sourcetype)
        self.scope_values_truncated |= _bounded_value(self.hosts, host)
        self.scope_values_truncated |= _bounded_value(self.indexes, index)
        self.scope_values_truncated |= _bounded_value(self.splunk_servers, server)

    def _observe_module(
        self,
        parsed: _ParsedRecord,
        timestamp: str,
        occurrence_id: str,
        observation_identity: str,
        context: _OpaqueRuntimeContext,
    ) -> bool:
        match = _MODULE.search(parsed.raw)
        if match is None:
            return False
        module = match.group(1)
        try:
            validate_evidence_locator_claim(module=module)
        except ValueError:
            return False
        stats = self.modules.setdefault(module, _ModuleStats())
        stats.observe(
            timestamp=timestamp,
            parser_state=parsed.parser_state,
            widened=parsed.widened,
            occurrence_id=occurrence_id,
            observation_identity=observation_identity,
            context=context,
        )
        return True

    def _observe_tracebacks(
        self,
        parsed: _ParsedRecord,
        timestamp: str,
        occurrence_id: str,
        observation_identity: str,
        context: _OpaqueRuntimeContext,
    ) -> int:
        occurrences = 0
        for match in _TRACEBACK.finditer(parsed.raw):
            path = (match.group(1) or match.group(2)).strip()
            line = int(match.group(3))
            symbol = match.group(4).strip() if match.group(4) is not None else ""
            try:
                validate_evidence_locator_claim(
                    path=path,
                    line=line,
                    symbol=(symbol or None),
                )
            except ValueError:
                continue
            key = (path, line, symbol)
            stats = self.tracebacks.setdefault(key, _ModuleStats())
            stats.observe(
                timestamp=timestamp,
                parser_state=parsed.parser_state,
                widened=parsed.widened,
                occurrence_id=occurrence_id,
                observation_identity=observation_identity,
                context=context,
            )
            occurrences += 1
        return occurrences


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


class _TrackingLineIterator:
    def __init__(self, handle: TextIO) -> None:
        self.handle = handle
        self.consumed: list[str] = []

    def __iter__(self) -> _TrackingLineIterator:
        return self

    def __next__(self) -> str:
        line = self.handle.readline()
        if line == "":
            raise StopIteration
        self.consumed.append(line)
        return line

    def take(self) -> str:
        text = "".join(self.consumed)
        self.consumed.clear()
        return text


def _strict_logical_records(handle: TextIO):
    tracker = _TrackingLineIterator(handle)
    reader = csv.reader(tracker, strict=True)
    ordinal = 0
    for _row in reader:
        yield ordinal, tracker.take()
        ordinal += 1


def _collect_native_csv_stream(path: Path) -> _CollectionState:
    state = _CollectionState(record_framing_state="native-csv")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        _validate_header(handle)
        for ordinal, text in _strict_logical_records(handle):
            state.observe(ordinal, text, _parse_record(text))
    return state


def _collect_recovery_stream(path: Path) -> _CollectionState:
    state = _CollectionState(record_framing_state="recovery-heuristic")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        _validate_header(handle)
        for ordinal, text in _logical_records(handle):
            state.observe(ordinal, text, _parse_record(text))
    return state


def _collect_stream(path: Path) -> _CollectionState:
    field_limit = max(1, path.stat().st_size)
    with _CSV_FIELD_LIMIT_LOCK:
        previous_limit = csv.field_size_limit(field_limit)
        try:
            try:
                return _collect_native_csv_stream(path)
            except csv.Error:
                return _collect_recovery_stream(path)
        finally:
            csv.field_size_limit(previous_limit)


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


def _selection_context_truncated(selection: _AnchorSelection) -> bool:
    for anchor in selection.anchors:
        metadata = anchor.get("metadata")
        if not isinstance(metadata, dict):
            continue
        runtime_context = metadata.get("runtime_context")
        if (
            isinstance(runtime_context, dict)
            and runtime_context.get("values_truncated") is True
        ):
            return True
    return False


def _selection_metadata_truncated(selection: _AnchorSelection) -> bool:
    return any(
        isinstance(anchor.get("metadata"), dict)
        and anchor["metadata"].get("metadata_values_truncated") is True
        for anchor in selection.anchors
    )


def _selection_prefix(
    selection: _AnchorSelection,
    count: int,
) -> _AnchorSelection:
    anchors = selection.anchors[:count]
    traceback_emitted = min(selection.traceback_emitted, count)
    module_emitted = max(0, count - traceback_emitted)
    return _AnchorSelection(
        anchors=anchors,
        traceback_observed=selection.traceback_observed,
        traceback_emitted=traceback_emitted,
        module_observed=selection.module_observed,
        module_emitted=module_emitted,
        observed=selection.observed,
        truncated=(selection.truncated or count < len(selection.anchors)),
    )


def _fit_selection_to_request(
    source_sha256: str,
    state: _CollectionState,
    selection: _AnchorSelection,
) -> _AnchorSelection:
    low = 0
    high = len(selection.anchors)
    while low < high:
        midpoint = (low + high + 1) // 2
        candidate = _selection_prefix(selection, midpoint)
        bundle = _bundle(source_sha256, state, candidate)
        if evidence_request_budget_fits([bundle]):
            low = midpoint
        else:
            high = midpoint - 1
    fitted = _selection_prefix(selection, low)
    if not evidence_request_budget_fits([_bundle(source_sha256, state, fitted)]):
        raise ValueError(
            "Splunk evidence bundle could not fit correlation request budget"
        )
    return fitted


def _projection_truncated(
    state: _CollectionState,
    selection: _AnchorSelection,
) -> bool:
    return (
        selection.truncated
        or bool(_scope(state)["scope_values_truncated"])
        or state.context_values_truncated
        or _selection_metadata_truncated(selection)
    )


def _scope(state: _CollectionState) -> dict[str, object]:
    scope: dict[str, object] = {
        "time_start": None,
        "time_end": None,
        "time_ordering_state": state.time_bounds.ordering_state,
        "timestamp_parse_failure_count": state.time_bounds.unparseable_count,
        "sources": [],
        "sourcetypes": [],
        "hosts": [],
        "indexes": [],
        "splunk_servers": [],
        "scope_values_truncated": True,
    }
    truncated = state.scope_values_truncated

    for field, value in (
        ("time_start", state.time_bounds.start),
        ("time_end", state.time_bounds.end),
    ):
        if value is None:
            continue
        scope[field] = value
        if not evidence_component_fits(scope):
            scope[field] = None
            truncated = True

    for field, values in (
        ("sources", state.sources),
        ("sourcetypes", state.sourcetypes),
        ("hosts", state.hosts),
        ("indexes", state.indexes),
        ("splunk_servers", state.splunk_servers),
    ):
        projected = scope[field]
        assert isinstance(projected, list)
        for value in sorted(values):
            projected.append(value)
            if not evidence_component_fits(scope):
                projected.pop()
                truncated = True

    scope["scope_values_truncated"] = truncated
    if not evidence_component_fits(scope):
        raise ValueError("Splunk scope could not fit evidence component budget")
    return scope


def _identity_anchor(anchor: dict[str, object]) -> dict[str, object]:
    result = dict(anchor)
    metadata = result.get("metadata")
    if isinstance(metadata, dict):
        stable_metadata = dict(metadata)
        stable_metadata.pop("sample_event_ids", None)
        stable_metadata.pop("sample_occurrence_ids", None)
        result["metadata"] = stable_metadata
    return result


def _evidence_projection_identity(
    state: _CollectionState,
    selection: _AnchorSelection,
) -> str:
    anchors = sorted(
        (_identity_anchor(anchor) for anchor in selection.anchors),
        key=lambda anchor: str(anchor["anchor_id"]),
    )
    return _identity_json(
        {
            "schema": _EVIDENCE_PROJECTION_SCHEMA,
            "producer": {
                "kind": "splunk-style",
                "format": "csv-export",
            },
            "completeness": "unknown",
            "truncation": (
                "truncated" if _projection_truncated(state, selection) else "unknown"
            ),
            "scope": _scope(state),
            "accounting": {
                "logical_event_count": state.event_count,
                "strict_valid_count": state.strict_valid_count,
                "recovered_count": state.recovered_count,
                "malformed_count": state.malformed_count,
                "widened_count": state.widened_count,
                "events_with_extracted_locator": state.events_with_extracted_locator,
                "events_without_extracted_locator": (
                    state.events_without_extracted_locator
                ),
                "locator_occurrences": (
                    state.module_locator_occurrences
                    + state.traceback_locator_occurrences
                ),
            },
            "anchors": anchors,
        }
    )


def _bundle(
    source_sha256: str,
    state: _CollectionState,
    selection: _AnchorSelection,
) -> dict[str, object]:
    projection_identity = _evidence_projection_identity(state, selection)
    return {
        "bundle_id": ("splunk-evidence:" + projection_identity.removeprefix("sha256:")),
        "producer": {
            "kind": "splunk-style",
            "format": "csv-export",
        },
        "provenance": {
            "source_sha256": source_sha256,
            "source_artifact_identity": source_sha256,
            "evidence_projection_identity": projection_identity,
            "logical_event_count": state.event_count,
            "physical_line_count": state.physical_lines,
            "strict_valid_count": state.strict_valid_count,
            "recovered_count": state.recovered_count,
            "malformed_count": state.malformed_count,
            "widened_count": state.widened_count,
            "record_framing_state": state.record_framing_state,
            "csv_parsing": {
                "strict_valid_count": state.strict_valid_count,
                "recovered_count": state.recovered_count,
                "malformed_count": state.malformed_count,
                "widened_count": state.widened_count,
            },
            "producer_payload_validation": {
                "state": _PRODUCER_PAYLOAD_VALIDATION_STATE,
            },
            "events_with_extracted_locator": state.events_with_extracted_locator,
            "events_without_extracted_locator": (
                state.events_without_extracted_locator
            ),
            "locator_occurrences": (
                state.module_locator_occurrences + state.traceback_locator_occurrences
            ),
            "unlocated_sample_event_ids": state.unlocated_sample_occurrence_ids,
            "unlocated_sample_occurrence_ids": (state.unlocated_sample_occurrence_ids),
            "unlocated_sample_observation_identities": (
                state.unlocated_sample_observation_identities
            ),
        },
        "completeness": "unknown",
        "truncation": (
            "truncated" if _projection_truncated(state, selection) else "unknown"
        ),
        "scope": _scope(state),
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
            "artifact_identity": source_sha256,
        },
        "summary": {
            "events": state.event_count,
            "physical_lines": state.physical_lines,
            "strict_valid": state.strict_valid_count,
            "recovered": state.recovered_count,
            "malformed": state.malformed_count,
            "widened": state.widened_count,
            "csv_strict_valid": state.strict_valid_count,
            "csv_recovered": state.recovered_count,
            "csv_malformed": state.malformed_count,
            "csv_widened": state.widened_count,
            "record_framing_state": state.record_framing_state,
            "producer_payload_validation_state": (_PRODUCER_PAYLOAD_VALIDATION_STATE),
            "time_ordering_state": state.time_bounds.ordering_state,
            "timestamp_parse_failure_count": state.time_bounds.unparseable_count,
            "parsed_events": state.strict_valid_count + state.recovered_count,
            "events_with_extracted_locator": state.events_with_extracted_locator,
            "events_without_extracted_locator": (
                state.events_without_extracted_locator
            ),
            "module_locator_occurrences": state.module_locator_occurrences,
            "traceback_locator_occurrences": (state.traceback_locator_occurrences),
            "locator_occurrences": (
                state.module_locator_occurrences + state.traceback_locator_occurrences
            ),
            "traceback_anchors_observed": selection.traceback_observed,
            "unique_traceback_anchors_observed": selection.traceback_observed,
            "traceback_anchors_emitted": selection.traceback_emitted,
            "module_anchors_observed": selection.module_observed,
            "unique_module_anchors_observed": selection.module_observed,
            "module_anchors_emitted": selection.module_emitted,
            "anchors_observed": selection.observed,
            "unique_anchors_observed": selection.observed,
            "anchors_emitted": len(selection.anchors),
            "anchors_truncated": selection.truncated,
            "scope_values_truncated": bool(_scope(state)["scope_values_truncated"]),
            "context_values_truncated": (
                state.context_values_truncated
                or _selection_context_truncated(selection)
            ),
            "metadata_values_truncated": _selection_metadata_truncated(selection),
            "projection_truncated": _projection_truncated(state, selection),
        },
        "bundle": _bundle(source_sha256, state, selection),
    }


def collect(
    path: Path, *, max_anchors: int = _DEFAULT_MAX_ANCHORS
) -> dict[str, object]:
    if max_anchors < 1 or max_anchors > _DEFAULT_MAX_ANCHORS:
        raise ValueError(f"max_anchors must be between 1 and {_DEFAULT_MAX_ANCHORS}")
    with TemporaryDirectory(prefix="hashmarks-splunk-") as temp_dir:
        snapshot = Path(temp_dir) / "source.csv"
        source_sha256 = _snapshot_source(path, snapshot)
        state = _collect_stream(snapshot)
    selection = _select_anchors(state, max_anchors)
    selection = _fit_selection_to_request(source_sha256, state, selection)
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
