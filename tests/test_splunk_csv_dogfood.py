from __future__ import annotations

import hashlib

from scripts.agent_evaluation.splunk_csv_dogfood import collect, correlate


HEADER = (
    '"_serial","_time","source","sourcetype","host","index","splunk_server","_raw"\n'
)


def _write(path, body: str) -> None:
    path.write_text(HEADER + body, encoding="utf-8")


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
        HEADER
        + '"9","2026-09-14T23:59:59.000+0200","[path]","kube:container:x",'
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
