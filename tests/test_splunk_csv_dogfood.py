from __future__ import annotations

import csv
import hashlib

import pytest

import scripts.agent_evaluation.splunk_csv_dogfood as splunk_csv_dogfood
from scripts.agent_evaluation.splunk_csv_dogfood import collect, correlate

HEADER = (
    '"_serial","_time","source","sourcetype","host","index","splunk_server","_raw"\n'
)


def _write(path, body: str) -> None:
    path.write_text(HEADER + body, encoding="utf-8")


def test_splunk_csv_dogfood_binds_artifact_hash_and_parse_to_same_snapshot(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    original_body = (
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[server]","INFO name=tasks.before"\n'
    )
    replacement_body = (
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[server]","INFO name=tasks.after"\n'
    )
    _write(source, original_body)
    original_bytes = source.read_bytes()
    expected_sha = "sha256:" + hashlib.sha256(original_bytes).hexdigest()

    real_collect_stream = splunk_csv_dogfood._collect_stream
    snapshots = []

    def mutate_source_then_collect(snapshot):
        snapshots.append(snapshot)
        _write(source, replacement_body)
        return real_collect_stream(snapshot)

    monkeypatch.setattr(
        splunk_csv_dogfood,
        "_collect_stream",
        mutate_source_then_collect,
    )

    report = collect(source)

    assert report["source"]["artifact_identity"] == expected_sha
    assert report["bundle"]["provenance"]["source_artifact_identity"] == expected_sha
    assert report["bundle"]["anchors"][0]["module"] == "tasks.before"
    assert "tasks.after" not in {
        anchor.get("module") for anchor in report["bundle"]["anchors"]
    }
    assert snapshots
    assert snapshots[0] != source
    assert not snapshots[0].exists()


def test_splunk_csv_dogfood_accepts_strict_valid_raw_above_runtime_csv_limit(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    raw = "INFO name=tasks.worker " + ("x" * 150_000)
    _write(
        source,
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        f'"[host]","idx","[server]","{raw}"\n',
    )

    assert source.stat().st_size > csv.field_size_limit()
    report = collect(source)
    assert report["summary"]["events"] == 1
    assert report["summary"]["csv_strict_valid"] == 1
    assert report["summary"]["record_framing_state"] == "native-csv"
    assert report["bundle"]["anchors"][0]["module"] == "tasks.worker"


def test_splunk_csv_dogfood_restores_runtime_csv_field_limit(tmp_path) -> None:
    source = tmp_path / "masked.csv"
    raw = "INFO name=tasks.worker " + ("x" * 150_000)
    _write(
        source,
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        f'"[host]","idx","[server]","{raw}"\n',
    )

    before = csv.field_size_limit()
    collect(source)
    assert csv.field_size_limit() == before


def test_splunk_csv_dogfood_accepts_utf8_bom_as_transport_marker(
    tmp_path,
) -> None:
    plain = tmp_path / "plain.csv"
    bom = tmp_path / "bom.csv"
    body = (
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[server]","INFO name=tasks.worker"\n'
    )
    _write(plain, body)
    bom.write_text("\ufeff" + HEADER + body, encoding="utf-8")

    plain_report = collect(plain)
    bom_report = collect(bom)

    assert (
        plain_report["source"]["artifact_identity"]
        != (bom_report["source"]["artifact_identity"])
    )
    assert plain_report["summary"] == bom_report["summary"]
    assert plain_report["bundle"]["bundle_id"] == bom_report["bundle"]["bundle_id"]
    assert (
        plain_report["bundle"]["provenance"]["evidence_projection_identity"]
        == bom_report["bundle"]["provenance"]["evidence_projection_identity"]
    )


def test_splunk_csv_dogfood_accepts_equivalent_header_quoting(tmp_path) -> None:
    source = tmp_path / "masked.csv"
    source.write_text(
        "_serial,_time,source,sourcetype,host,index,splunk_server,_raw\n"
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[server]","INFO name=tasks.worker"\n',
        encoding="utf-8",
    )

    report = collect(source)
    assert report["summary"]["events"] == 1
    assert report["summary"]["csv_strict_valid"] == 1


def test_splunk_csv_dogfood_keeps_header_schema_exact(tmp_path) -> None:
    source = tmp_path / "masked.csv"
    source.write_text(
        "_serial,_time,source,host,sourcetype,index,splunk_server,_raw\n"
        '"1","2026-09-14T23:59:59.000+0200","[path]","[host]",'
        '"kube:container:x","idx","[server]","INFO name=tasks.worker"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Splunk CSV header must be"):
        collect(source)


def test_splunk_csv_dogfood_accepts_unquoted_serial_record_start(tmp_path) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '0,"2026-09-28T08:09:45.000+0200",kubernetes,"kube:events",'
        '"[host]","idx","[server]","INFO name=tasks.worker ok"\n',
    )

    report = collect(source)
    assert report["summary"]["events"] == 1
    assert report["summary"]["strict_valid"] == 1
    assert report["summary"]["malformed"] == 0
    assert report["bundle"]["anchors"][0]["module"] == "tasks.worker"


def test_splunk_csv_dogfood_native_framing_ignores_full_row_like_raw_continuation(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[server]","first line\n'
        "7,2026-09-14T23:59:57.000+0200,[path],kube:container:x,"
        "[host],idx,[server],fake raw\n"
        'last line"\n'
        '"2","2026-09-14T23:59:56.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[server]","INFO name=tasks.worker"\n',
    )

    report = collect(source)
    assert report["summary"]["events"] == 2
    assert report["summary"]["csv_strict_valid"] == 2
    assert report["summary"]["malformed"] == 0
    assert report["summary"]["record_framing_state"] == "native-csv"
    assert report["bundle"]["provenance"]["record_framing_state"] == "native-csv"
    assert report["bundle"]["anchors"][0]["module"] == "tasks.worker"


def test_splunk_csv_dogfood_falls_back_only_for_damaged_csv_framing(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[server]","INFO GET [url] "HTTP/1.1 200 OK" '
        'name=httpx"\n',
    )

    report = collect(source)
    assert report["summary"]["events"] == 1
    assert report["summary"]["recovered"] == 1
    assert report["summary"]["record_framing_state"] == "recovery-heuristic"
    assert report["bundle"]["provenance"]["record_framing_state"] == (
        "recovery-heuristic"
    )


def test_splunk_csv_dogfood_does_not_split_record_like_raw_continuation(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","ERROR first line\n'
        '"7","2026-09-14T23:59:57.000+0200"\n'
        'continuation payload"\n',
    )

    report = collect(source)
    assert report["summary"]["events"] == 1
    assert report["summary"]["malformed"] == 1


def test_splunk_csv_dogfood_recovers_invalid_raw_without_hiding_parser_state(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"0","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","INFO name=api.kafka_consumer ok"\n'
        '"1","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","INFO GET [url] "HTTP/1.1 200 OK" '
        'name=httpx"\n'
        '"2","2026-09-14T23:59:57.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","INFO | {"data":[{"x":1,"y":2}]} '
        'name=pipelines.file_processor"\n',
    )

    report = collect(source)
    summary = report["summary"]
    assert summary["events"] == 3
    assert summary["strict_valid"] == 1
    assert summary["recovered"] == 2
    assert summary["malformed"] == 0
    assert summary["widened"] == 1

    bundle = report["bundle"]
    assert bundle["completeness"] == "unknown"
    assert bundle["truncation"] == "unknown"
    modules = {
        anchor["module"]: anchor["metadata"]["observed_count"]
        for anchor in bundle["anchors"]
    }
    assert modules == {
        "api.kafka_consumer": 1,
        "httpx": 1,
        "pipelines.file_processor": 1,
    }


def test_splunk_csv_dogfood_does_not_confuse_csv_validity_with_payload_validity(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[server]","INFO | {""data"":[{""x"":1}]}"\n'
        '"2","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[server]","INFO | {""data"":[{""x"":1]"\n',
    )

    report = collect(source)
    summary = report["summary"]
    assert summary["events"] == 2
    assert summary["strict_valid"] == 2
    assert summary["csv_strict_valid"] == 2
    assert summary["csv_recovered"] == 0
    assert summary["csv_malformed"] == 0
    assert summary["producer_payload_validation_state"] == "not-assessed"

    provenance = report["bundle"]["provenance"]
    assert provenance["csv_parsing"] == {
        "strict_valid_count": 2,
        "recovered_count": 0,
        "malformed_count": 0,
        "widened_count": 0,
    }
    assert provenance["producer_payload_validation"] == {
        "state": "not-assessed",
    }


def test_splunk_csv_dogfood_accounts_for_locator_free_events(tmp_path) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","INFO name=api.kafka_consumer"\n'
        '"2","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","Back-off restarting failed container"\n'
        '"3","2026-09-14T23:59:57.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","detections: 3, timing: 9ms"\n',
    )

    report = collect(source)
    summary = report["summary"]
    assert summary["parsed_events"] == 3
    assert summary["events_with_extracted_locator"] == 1
    assert summary["events_without_extracted_locator"] == 2
    assert (
        summary["events_with_extracted_locator"]
        + summary["events_without_extracted_locator"]
        == summary["parsed_events"]
    )
    assert summary["module_locator_occurrences"] == 1
    assert summary["traceback_locator_occurrences"] == 0
    assert summary["locator_occurrences"] == 1
    assert summary["unique_module_anchors_observed"] == 1
    assert summary["unique_anchors_observed"] == 1
    sample_ids = report["bundle"]["provenance"]["unlocated_sample_event_ids"]
    assert len(sample_ids) == 2
    assert all(value.startswith("event:") for value in sample_ids)


def test_splunk_csv_dogfood_rejects_invalid_module_locator_without_repair(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","INFO name=tasks..worker"\n',
    )

    report = collect(source)
    summary = report["summary"]
    assert summary["parsed_events"] == 1
    assert summary["module_locator_occurrences"] == 0
    assert summary["events_with_extracted_locator"] == 0
    assert summary["events_without_extracted_locator"] == 1
    assert report["bundle"]["anchors"] == []


def test_splunk_csv_dogfood_rejects_locator_beyond_core_module_bound(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    module = "m" * 1025
    _write(
        source,
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        f'"[host]","idx","[host]","INFO name={module}"\n',
    )

    report = collect(source)
    assert report["summary"]["module_locator_occurrences"] == 0
    assert report["summary"]["events_without_extracted_locator"] == 1
    assert report["bundle"]["anchors"] == []


def test_splunk_csv_dogfood_rejects_invalid_traceback_locator_without_repair(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","Traceback:\n'
        '  File ""/app/../src/worker.py"", line 7, in worker\n'
        'RuntimeError: boom"\n',
    )

    report = collect(source)
    assert report["summary"]["traceback_locator_occurrences"] == 0
    assert report["summary"]["events_without_extracted_locator"] == 1
    assert report["bundle"]["anchors"] == []


def test_splunk_csv_dogfood_does_not_strip_invalid_module_suffix(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","INFO name=tasks.worker..."\n',
    )

    report = collect(source)
    assert report["summary"]["module_locator_occurrences"] == 0
    assert report["summary"]["events_without_extracted_locator"] == 1
    assert report["bundle"]["anchors"] == []


def test_splunk_csv_dogfood_does_not_salvage_module_prefix_before_slash(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","INFO name=tasks/worker"\n',
    )

    report = collect(source)
    assert report["summary"]["module_locator_occurrences"] == 0
    assert report["summary"]["events_without_extracted_locator"] == 1
    assert report["bundle"]["anchors"] == []


def test_splunk_csv_dogfood_counts_multiple_locator_types_once_per_event(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","INFO name=api.kafka_consumer '
        'File /app/src/utils/__init__.py, line 2, in process_output_data"\n',
    )

    report = collect(source)
    summary = report["summary"]
    assert summary["parsed_events"] == 1
    assert summary["events_with_extracted_locator"] == 1
    assert summary["events_without_extracted_locator"] == 0
    assert summary["module_locator_occurrences"] == 1
    assert summary["traceback_locator_occurrences"] == 1
    assert summary["locator_occurrences"] == 2
    assert summary["unique_module_anchors_observed"] == 1
    assert summary["unique_traceback_anchors_observed"] == 1
    assert summary["unique_anchors_observed"] == 2


def test_splunk_csv_dogfood_bounds_unlocated_event_samples(tmp_path) -> None:
    source = tmp_path / "masked.csv"
    rows = []
    for index in range(5):
        rows.append(
            f'"{index}","2026-09-14T23:59:{index:02d}.000+0200",'
            '"[path]","kube:container:x","[host]","idx","[host]",'
            f'"unlocated event {index}"\n'
        )
    _write(source, "".join(rows))

    report = collect(source)
    assert report["summary"]["events_without_extracted_locator"] == 5
    sample_ids = report["bundle"]["provenance"]["unlocated_sample_event_ids"]
    assert len(sample_ids) == 3
    assert len(set(sample_ids)) == 3


def test_splunk_csv_dogfood_separates_artifact_occurrence_and_observation_identity(
    tmp_path,
) -> None:
    quoted = tmp_path / "quoted.csv"
    unquoted = tmp_path / "unquoted.csv"
    _write(
        quoted,
        '"7","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[server]","INFO name=tasks.worker"\n',
    )
    _write(
        unquoted,
        '7,"2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[server]","INFO name=tasks.worker"\n',
    )

    quoted_report = collect(quoted)
    unquoted_report = collect(unquoted)
    assert (
        quoted_report["source"]["artifact_identity"]
        != (unquoted_report["source"]["artifact_identity"])
    )
    assert (
        quoted_report["bundle"]["bundle_id"] == unquoted_report["bundle"]["bundle_id"]
    )
    quoted_metadata = quoted_report["bundle"]["anchors"][0]["metadata"]
    unquoted_metadata = unquoted_report["bundle"]["anchors"][0]["metadata"]
    assert (
        quoted_metadata["sample_occurrence_ids"]
        != (unquoted_metadata["sample_occurrence_ids"])
    )
    assert (
        quoted_metadata["sample_event_ids"]
        == (quoted_metadata["sample_occurrence_ids"])
    )
    assert (
        unquoted_metadata["sample_event_ids"]
        == (unquoted_metadata["sample_occurrence_ids"])
    )
    assert (
        quoted_metadata["sample_observation_identities"]
        == (unquoted_metadata["sample_observation_identities"])
    )


def test_splunk_csv_dogfood_projection_identity_is_order_independent(
    tmp_path,
) -> None:
    first = tmp_path / "first.csv"
    reversed_source = tmp_path / "reversed.csv"
    row_a = (
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host-a]","idx","[server-a]","INFO name=tasks.worker '
        'handling_ident=[DOC_A]"\n'
    )
    row_b = (
        '"2","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host-b]","idx","[server-b]","INFO name=utils.kafka '
        'handling_ident=[DOC_B]"\n'
    )
    _write(first, row_a + row_b)
    _write(reversed_source, row_b + row_a)

    first_report = collect(first)
    reversed_report = collect(reversed_source)
    assert (
        first_report["source"]["artifact_identity"]
        != (reversed_report["source"]["artifact_identity"])
    )
    assert first_report["bundle"]["bundle_id"] == reversed_report["bundle"]["bundle_id"]
    assert (
        first_report["bundle"]["provenance"]["evidence_projection_identity"]
        == (reversed_report["bundle"]["provenance"]["evidence_projection_identity"])
    )
    first_observations = {
        identity
        for anchor in first_report["bundle"]["anchors"]
        for identity in anchor["metadata"]["sample_observation_identities"]
    }
    reversed_observations = {
        identity
        for anchor in reversed_report["bundle"]["anchors"]
        for identity in anchor["metadata"]["sample_observation_identities"]
    }
    assert first_observations == reversed_observations


def test_splunk_csv_dogfood_repeated_observation_keeps_distinct_occurrences(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"7","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[server]","INFO name=utils.kafka same"\n'
        '"8","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[server]","INFO name=utils.kafka same"\n',
    )

    metadata = collect(source)["bundle"]["anchors"][0]["metadata"]
    assert metadata["observed_count"] == 2
    assert len(metadata["sample_occurrence_ids"]) == 2
    assert len(set(metadata["sample_occurrence_ids"])) == 2
    assert len(metadata["sample_observation_identities"]) == 1


def test_splunk_csv_dogfood_orders_scope_by_instant_across_offsets(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-10-25T02:15:00.000+0100","[path]","kube:container:x",'
        '"[host]","idx","[server]","INFO name=tasks.worker later"\n'
        '"2","2026-10-25T02:30:00.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[server]","INFO name=tasks.worker earlier"\n',
    )

    report = collect(source)
    scope = report["bundle"]["scope"]
    assert scope["time_start"] == "2026-10-25T02:30:00.000+0200"
    assert scope["time_end"] == "2026-10-25T02:15:00.000+0100"
    assert scope["time_ordering_state"] == "instant-aware"
    assert scope["timestamp_parse_failure_count"] == 0
    assert report["summary"]["time_ordering_state"] == "instant-aware"
    assert report["summary"]["timestamp_parse_failure_count"] == 0

    metadata = report["bundle"]["anchors"][0]["metadata"]
    assert metadata["first_time"] == "2026-10-25T02:30:00.000+0200"
    assert metadata["last_time"] == "2026-10-25T02:15:00.000+0100"
    assert metadata["time_ordering_state"] == "instant-aware"
    assert metadata["timestamp_parse_failure_count"] == 0


def test_splunk_csv_dogfood_marks_unparseable_timestamp_ordering_fallback(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-10-25T02:15:00.000+0100","[path]","kube:container:x",'
        '"[host]","idx","[server]","INFO name=tasks.worker valid"\n'
        '"2","2026-10-25Tbad","[path]","kube:container:x",'
        '"[host]","idx","[server]","INFO name=tasks.worker invalid"\n',
    )

    report = collect(source)
    scope = report["bundle"]["scope"]
    assert scope["time_ordering_state"] == "lexical-fallback"
    assert scope["timestamp_parse_failure_count"] == 1
    assert report["summary"]["time_ordering_state"] == "lexical-fallback"
    assert report["summary"]["timestamp_parse_failure_count"] == 1
    metadata = report["bundle"]["anchors"][0]["metadata"]
    assert metadata["time_ordering_state"] == "lexical-fallback"
    assert metadata["timestamp_parse_failure_count"] == 1


def test_splunk_csv_dogfood_preserves_bounded_opaque_context_per_anchor(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host-a]","idx","[server-a]","INFO name=pipelines.worker '
        'handling_ident=[DOCUMENT_A] commit=[REV_A]"\n'
        '"2","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host-a]","idx","[server-b]","INFO name=pipelines.worker '
        'handling_ident=[DOCUMENT_B] commit=[REV_A]"\n'
        '"3","2026-09-14T23:59:57.000+0200","[path]","kube:container:x",'
        '"[host-b]","idx","[server-b]","INFO name=pipelines.worker '
        'handling_ident=[DOCUMENT_B] commit=[REV_B]"\n',
    )

    report = collect(source)
    assert report["summary"]["unique_module_anchors_observed"] == 1
    anchor = report["bundle"]["anchors"][0]
    assert anchor["metadata"]["observed_count"] == 3
    context = anchor["metadata"]["runtime_context"]
    assert context["handling_ident_values"] == ["[DOCUMENT_A]", "[DOCUMENT_B]"]
    assert context["handling_ident_values_truncated"] is False
    assert context["commit_values"] == ["[REV_A]", "[REV_B]"]
    assert context["commit_values_truncated"] is False
    assert context["values_truncated"] is False


def test_splunk_csv_dogfood_preserves_runtime_placement_scope(tmp_path) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host-a]","idx","[server-a]","INFO name=tasks.worker"\n'
        '"2","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host-b]","idx","[server-b]","INFO name=tasks.worker"\n',
    )

    scope = collect(source)["bundle"]["scope"]
    assert scope["hosts"] == ["[host-a]", "[host-b]"]
    assert scope["splunk_servers"] == ["[server-a]", "[server-b]"]
    assert scope["scope_values_truncated"] is False


def test_splunk_csv_dogfood_scope_truncation_is_order_independent(
    tmp_path,
) -> None:
    forward = tmp_path / "forward.csv"
    reverse = tmp_path / "reverse.csv"
    rows = []
    for index in range(40):
        rows.append(
            f'"{index}","2026-09-14T23:59:{index % 60:02d}.000+0200",'
            f'"[source-{index:02d}]","kube:container:x","[host-{index:02d}]",'
            f'"idx","[server-{index:02d}]","INFO name=tasks.worker"\n'
        )
    _write(forward, "".join(rows))
    _write(reverse, "".join(reversed(rows)))

    forward_report = collect(forward)
    reverse_report = collect(reverse)

    assert forward_report["bundle"]["scope"] == reverse_report["bundle"]["scope"]
    assert forward_report["bundle"]["scope"]["scope_values_truncated"] is True
    assert forward_report["bundle"]["truncation"] == "truncated"
    assert forward_report["summary"]["scope_values_truncated"] is True
    assert forward_report["summary"]["projection_truncated"] is True
    assert (
        forward_report["bundle"]["bundle_id"] == reverse_report["bundle"]["bundle_id"]
    )
    assert (
        forward_report["bundle"]["provenance"]["evidence_projection_identity"]
        == reverse_report["bundle"]["provenance"]["evidence_projection_identity"]
    )


def test_splunk_csv_dogfood_context_truncation_is_order_independent(
    tmp_path,
) -> None:
    forward = tmp_path / "forward.csv"
    reverse = tmp_path / "reverse.csv"
    rows = []
    for index in range(12):
        rows.append(
            f'"{index}","2026-09-14T23:59:{index:02d}.000+0200",'
            '"[path]","kube:container:x","[host]","idx","[server]",'
            f'"INFO name=pipelines.worker handling_ident=[DOC_{index:02d}] '
            f'commit=[REV_{index:02d}]"\n'
        )
    _write(forward, "".join(rows))
    _write(reverse, "".join(reversed(rows)))

    forward_report = collect(forward)
    reverse_report = collect(reverse)
    forward_context = forward_report["bundle"]["anchors"][0]["metadata"][
        "runtime_context"
    ]
    reverse_context = reverse_report["bundle"]["anchors"][0]["metadata"][
        "runtime_context"
    ]

    assert forward_context == reverse_context
    assert forward_context["handling_ident_values_truncated"] is True
    assert forward_context["commit_values_truncated"] is True
    assert forward_report["bundle"]["truncation"] == "truncated"
    assert forward_report["summary"]["context_values_truncated"] is True
    assert forward_report["summary"]["projection_truncated"] is True
    assert (
        forward_report["bundle"]["bundle_id"] == reverse_report["bundle"]["bundle_id"]
    )


def test_splunk_csv_dogfood_bounds_context_without_splitting_anchor(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    rows = []
    for index in range(10):
        rows.append(
            f'"{index}","2026-09-14T23:59:{index:02d}.000+0200",'
            '"[path]","kube:container:x","[host]","idx","[server]",'
            f'"INFO name=pipelines.worker handling_ident=[DOC_{index}] '
            f'commit=[REV_{index}]"\n'
        )
    _write(source, "".join(rows))

    report = collect(source)
    assert report["summary"]["unique_module_anchors_observed"] == 1
    anchor = report["bundle"]["anchors"][0]
    assert anchor["metadata"]["observed_count"] == 10
    context = anchor["metadata"]["runtime_context"]
    assert len(context["handling_ident_values"]) == 8
    assert context["handling_ident_values_truncated"] is True
    assert len(context["commit_values"]) == 8
    assert context["commit_values_truncated"] is True
    assert context["values_truncated"] is True


def test_splunk_csv_dogfood_fits_oversized_scope_to_core_budget(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    oversized_source = "[source-" + ("x" * 9_000) + "]"
    _write(
        source,
        f'"1","2026-09-14T23:59:59.000+0200","{oversized_source}",'
        '"kube:container:x","[host]","idx","[server]",'
        '"INFO name=tasks.worker"\n',
    )

    report = collect(source)
    scope = report["bundle"]["scope"]
    assert oversized_source not in scope["sources"]
    assert scope["scope_values_truncated"] is True
    assert report["summary"]["scope_values_truncated"] is True
    assert report["summary"]["projection_truncated"] is True
    assert report["bundle"]["truncation"] == "truncated"

    workspace = tmp_path / "repo"
    (workspace / "tasks").mkdir(parents=True)
    (workspace / "tasks" / "__init__.py").write_text("", encoding="utf-8")
    (workspace / "tasks" / "worker.py").write_text(
        "def run():\n    return 1\n",
        encoding="utf-8",
    )
    result = correlate(workspace, report)
    assert result["resolution_states"] == {"resolved-unique": 1}


def test_splunk_csv_dogfood_fits_oversized_context_to_core_budget(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    oversized_context = "[DOC-" + ("x" * 9_000) + "]"
    _write(
        source,
        '"1","2026-09-14T23:59:59.000+0200","[path]",'
        '"kube:container:x","[host]","idx","[server]",'
        f'"INFO name=tasks.worker handling_ident={oversized_context}"\n',
    )

    report = collect(source)
    metadata = report["bundle"]["anchors"][0]["metadata"]
    runtime_context = metadata["runtime_context"]
    assert oversized_context not in runtime_context["handling_ident_values"]
    assert runtime_context["handling_ident_values_truncated"] is True
    assert runtime_context["values_truncated"] is True
    assert metadata["metadata_values_truncated"] is True
    assert report["summary"]["context_values_truncated"] is True
    assert report["summary"]["metadata_values_truncated"] is True
    assert report["summary"]["projection_truncated"] is True
    assert report["bundle"]["truncation"] == "truncated"

    workspace = tmp_path / "repo"
    (workspace / "tasks").mkdir(parents=True)
    (workspace / "tasks" / "__init__.py").write_text("", encoding="utf-8")
    (workspace / "tasks" / "worker.py").write_text(
        "def run():\n    return 1\n",
        encoding="utf-8",
    )
    result = correlate(workspace, report)
    assert result["resolution_states"] == {"resolved-unique": 1}


def test_splunk_csv_dogfood_nontruncated_projection_remains_unknown(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[server]","INFO name=tasks.worker '
        'handling_ident=[DOC] commit=[REV]"\n',
    )

    report = collect(source)
    assert report["bundle"]["truncation"] == "unknown"
    assert report["summary"]["anchors_truncated"] is False
    assert report["summary"]["scope_values_truncated"] is False
    assert report["summary"]["context_values_truncated"] is False
    assert report["summary"]["projection_truncated"] is False


def test_splunk_csv_dogfood_preserves_multiline_record_and_exact_source_identity(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    body = (
        '"7","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","ERROR first line\n'
        'Traceback continuation name=tasks.ner"\n'
    )
    _write(source, body)

    report = collect(source)
    expected = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    assert report["source"]["sha256"] == expected
    assert report["summary"]["events"] == 1
    assert report["summary"]["physical_lines"] == 3
    assert report["bundle"]["anchors"][0]["module"] == "tasks.ner"


def test_splunk_csv_dogfood_never_uses_repeated_serial_as_event_identity(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"7","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","INFO name=utils.kafka one"\n'
        '"7","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","INFO name=utils.kafka two"\n',
    )

    report = collect(source)
    metadata = report["bundle"]["anchors"][0]["metadata"]
    assert metadata["observed_count"] == 2
    assert len(metadata["sample_event_ids"]) == 2
    assert len(set(metadata["sample_event_ids"])) == 2
    assert all(value.startswith("event:") for value in metadata["sample_event_ids"])


def test_splunk_csv_dogfood_bounds_module_anchor_projection(tmp_path) -> None:
    source = tmp_path / "masked.csv"
    rows = []
    for index in range(20):
        rows.append(
            f'"{index}","2026-09-14T23:59:{index:02d}.000+0200",'
            '"[path]","kube:container:x","[host]","idx","[host]",'
            f'"INFO name=module_{index}"\n'
        )
    _write(source, "".join(rows))

    report = collect(source, max_anchors=5)
    assert report["summary"]["module_anchors_observed"] == 20
    assert report["summary"]["module_anchors_emitted"] == 5
    assert report["summary"]["anchors_truncated"] is True
    assert report["bundle"]["truncation"] == "truncated"


def test_splunk_csv_dogfood_correlates_through_existing_repository_owner(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","INFO name=api.kafka_consumer"\n',
    )
    workspace = tmp_path / "repo"
    (workspace / "api").mkdir(parents=True)
    (workspace / "api" / "__init__.py").write_text("", encoding="utf-8")
    (workspace / "api" / "kafka_consumer.py").write_text(
        "def consume():\n    return 1\n",
        encoding="utf-8",
    )

    result = correlate(workspace, collect(source))
    assert result["resolution_states"] == {"resolved-unique": 1}
    assert result["authority"] == "repository-intelligence-only"
    assert result["interpretation_authority"] == "consumer-owned"
    assert result["causation"] == "not-inferred"


def test_splunk_csv_dogfood_prioritizes_traceback_path_line_symbol_anchor(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","  File "/app/src/utils/__init__.py", '
        'line 280, in process_output_data"\n'
        '"2","2026-09-14T23:59:57.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","INFO name=api.kafka_consumer"\n',
    )

    report = collect(source, max_anchors=1)
    assert report["summary"]["traceback_anchors_observed"] == 1
    assert report["summary"]["traceback_anchors_emitted"] == 1
    assert report["summary"]["module_anchors_observed"] == 1
    assert report["summary"]["module_anchors_emitted"] == 0
    anchor = report["bundle"]["anchors"][0]
    assert anchor["path"] == "/app/src/utils/__init__.py"
    assert anchor["line"] == 280
    assert anchor["symbol"] == "process_output_data"
    assert anchor["metadata"]["kind"] == "python-traceback-frame"


def test_splunk_csv_dogfood_anchor_ids_do_not_collide_for_distinct_tracebacks(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","Traceback:\n'
        '  File ""a.py"", line 1, in b:2:c\n'
        '  File ""a.py:1:b"", line 2, in c\n'
        'RuntimeError: boom"\n',
    )

    report = collect(source)
    anchors = report["bundle"]["anchors"]
    assert len(anchors) == 2
    assert len({anchor["anchor_id"] for anchor in anchors}) == 2
    assert all(len(str(anchor["anchor_id"])) <= 512 for anchor in anchors)


def test_splunk_csv_dogfood_module_anchor_id_stays_within_core_bound(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    module = "m" * 600
    _write(
        source,
        '"1","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        f'"[host]","idx","[host]","INFO name={module}"\n',
    )

    report = collect(source)
    anchor = report["bundle"]["anchors"][0]
    assert anchor["module"] == module
    assert len(str(anchor["anchor_id"])) <= 512


def test_splunk_csv_dogfood_traceback_anchor_id_stays_within_core_bound(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    path = "/" + ("p" * 700) + ".py"
    _write(
        source,
        '"1","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        f'"[host]","idx","[host]","Traceback:\n'
        f'  File ""{path}"", line 17, in parse_result\n'
        'ValueError: bad payload"\n',
    )

    report = collect(source)
    anchor = report["bundle"]["anchors"][0]
    assert anchor["path"] == path
    assert len(str(anchor["anchor_id"])) <= 512


def test_splunk_csv_dogfood_preserves_pseudo_traceback_symbols(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","Traceback:\n'
        '  File ""/app/src/main.py"", line 9, in <module>\n'
        '  File ""/app/src/main.py"", line 4, in <lambda>\n'
        'RuntimeError: boom"\n',
    )

    report = collect(source)
    summary = report["summary"]
    assert summary["traceback_locator_occurrences"] == 2
    assert summary["unique_traceback_anchors_observed"] == 2
    anchors = {
        (anchor["path"], anchor["line"], anchor["symbol"])
        for anchor in report["bundle"]["anchors"]
    }
    assert anchors == {
        ("/app/src/main.py", 9, "<module>"),
        ("/app/src/main.py", 4, "<lambda>"),
    }


def test_splunk_csv_dogfood_preserves_comma_in_quoted_traceback_path(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","Traceback:\n'
        '  File ""/app/src/parser,legacy.py"", line 17, in parse_result\n'
        'ValueError: bad payload"\n',
    )

    report = collect(source)
    summary = report["summary"]
    assert summary["traceback_locator_occurrences"] == 1
    assert summary["unique_traceback_anchors_observed"] == 1
    anchor = report["bundle"]["anchors"][0]
    assert anchor["path"] == "/app/src/parser,legacy.py"
    assert anchor["line"] == 17
    assert anchor["symbol"] == "parse_result"


def test_splunk_csv_dogfood_preserves_all_traceback_frames_in_one_event(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","Traceback (most recent call last):\n'
        '  File ""/app/src/api/worker.py"", line 14, in handle\n'
        '  File ""/app/src/utils/helpers.py"", line 7, in parse_result\n'
        'ValueError: bad payload"\n',
    )

    report = collect(source)
    summary = report["summary"]
    assert summary["events"] == 1
    assert summary["events_with_extracted_locator"] == 1
    assert summary["traceback_locator_occurrences"] == 2
    assert summary["unique_traceback_anchors_observed"] == 2
    assert summary["unique_anchors_observed"] == 2

    anchors = {
        (anchor["path"], anchor["line"], anchor["symbol"])
        for anchor in report["bundle"]["anchors"]
    }
    assert anchors == {
        ("/app/src/api/worker.py", 14, "handle"),
        ("/app/src/utils/helpers.py", 7, "parse_result"),
    }


def test_splunk_csv_dogfood_counts_repeated_traceback_frame_occurrences(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","Traceback:\n'
        '  File ""/app/src/utils/helpers.py"", line 7, in parse_result\n'
        '  File ""/app/src/utils/helpers.py"", line 7, in parse_result"\n',
    )

    report = collect(source)
    summary = report["summary"]
    assert summary["events"] == 1
    assert summary["traceback_locator_occurrences"] == 2
    assert summary["unique_traceback_anchors_observed"] == 1
    anchor = report["bundle"]["anchors"][0]
    assert anchor["metadata"]["observed_count"] == 2


def test_splunk_csv_dogfood_correlates_traceback_with_explicit_path_mapping(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","  File "/app/src/utils/__init__.py", '
        'line 2, in process_output_data"\n',
    )
    workspace = tmp_path / "repo"
    (workspace / "utils").mkdir(parents=True)
    (workspace / "utils" / "__init__.py").write_text(
        "def process_output_data():\n    return 1\n",
        encoding="utf-8",
    )

    result = correlate(
        workspace,
        collect(source),
        path_mappings=[
            {
                "external_prefix": "/app/src",
                "repository_prefix": "",
            }
        ],
    )
    assert result["resolution_states"] == {"resolved-unique": 1}
    anchor = result["packet"]["bundles"][0]["anchors"][0]
    assert anchor["resolution"]["repository_path"] == "utils/__init__.py"
    assert anchor["resolution"]["path_origin"] == "explicit-path-mapping"


def test_splunk_csv_dogfood_counts_final_physical_line_without_newline(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    source.write_text(
        HEADER + '"9","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","INFO name=utils"',
        encoding="utf-8",
    )

    report = collect(source)
    assert report["summary"]["events"] == 1
    assert report["summary"]["physical_lines"] == 2


def test_splunk_csv_dogfood_recovers_traceback_after_quote_damage(
    tmp_path,
) -> None:
    source = tmp_path / "masked.csv"
    _write(
        source,
        '"1","2026-09-14T23:59:58.000+0200","[path]","kube:container:x",'
        '"[host]","idx","[host]","  File "/app/src/utils/__init__.py", '
        'line 280, in process_output_data"\n',
    )

    report = collect(source)
    assert report["summary"]["recovered"] == 1
    assert report["summary"]["widened"] == 1
    anchor = report["bundle"]["anchors"][0]
    assert anchor["path"] == "/app/src/utils/__init__.py"
    assert anchor["line"] == 280
    assert anchor["symbol"] == "process_output_data"
