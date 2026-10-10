"""Genuine dependency captures through repository changes and public projections."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from native_evidence_support import (
    assert_projection,
    dependency_capture,
    input_revisions,
    materialize_dependency,
    semantic_dependency_fields,
)

from hashmarks.codemap import CodeMap
from hashmarks.evidence_presentation import present_repository_evidence


@pytest.mark.parametrize("producer", ["uv", "maven"])
def test_native_dependency_sequence_binds_real_inputs_and_reopens(
    tmp_path: Path, producer: str, native_dependency_corpus: Path
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    previous: Any = None
    component = "dummy-dep" if producer == "uv" else "example.fixture:dummy-dep"
    for name, expected in (
        ("absent", None),
        ("v1", "1.0.0"),
        ("v2", "2.0.0"),
        ("absent", None),
    ):
        source = native_dependency_corpus / producer / name
        paths = materialize_dependency(root, source)
        raw = dependency_capture(producer, source, input_revisions(root, paths))
        with CodeMap(root, state_dir=state) as cm:
            cm.sync()
            current: Any = cm.dependency_resolution_evidence(raw)
            assert all(
                row["source_equivalence"] == "proven"
                for row in current["repository_inputs"]
            )
            selected = [
                row["version"]
                for row in current["selections"]
                if row["component_id"] == component
            ]
            assert selected == ([] if expected is None else [expected])
            if previous is not None:
                delta: Any = cm.dependency_resolution_delta(previous, current)
                assert delta["comparability"] == "comparable"
                assert delta["change_axes"]["repository_inputs"] == "changed"
                assert delta["change_axes"]["semantic_resolution"] == "changed"
                assert_projection(delta, "dependency_codemap", "compare")
        with CodeMap(root, state_dir=state) as reopened:
            restored: Any = reopened.dependency_resolution_evidence(raw)
        with CodeMap(root, state_dir=tmp_path / f"fresh-{name}-{expected}") as fresh:
            fresh.sync()
            rebuilt: Any = fresh.dependency_resolution_evidence(raw)
        assert semantic_dependency_fields(restored) == semantic_dependency_fields(
            current
        )
        assert semantic_dependency_fields(rebuilt) == semantic_dependency_fields(
            current
        )
        previous = current


@pytest.mark.parametrize("producer", ["uv", "maven"])
def test_old_native_capture_keeps_input_mismatch_visible(
    tmp_path: Path, producer: str, native_dependency_corpus: Path
) -> None:
    root = tmp_path / "repo"
    before_source = native_dependency_corpus / producer / "v1"
    paths = materialize_dependency(root, before_source)
    raw = dependency_capture(producer, before_source, input_revisions(root, paths))
    with CodeMap(root, state_dir=tmp_path / "state") as cm:
        cm.sync()
        before: Any = cm.dependency_resolution_evidence(raw)
        materialize_dependency(root, native_dependency_corpus / producer / "v2")
        cm.sync()
        reused: Any = cm.dependency_resolution_evidence(raw)
        delta: Any = cm.dependency_resolution_delta(before, reused)
        response = cm.dependency_codemap(raw)
    assert any(
        row["source_equivalence"] == "mismatch" for row in reused["repository_inputs"]
    )
    assert before["resolution_identity"] == reused["resolution_identity"]
    assert delta["change_axes"]["repository_inputs"] == "changed"
    assert delta["change_axes"]["semantic_resolution"] == "unchanged"
    assert_projection(response, "dependency_codemap", "observation")


@pytest.mark.parametrize("producer", ["uv", "maven"])
def test_native_dependency_formatting_change_is_not_resolution_change(
    tmp_path: Path, producer: str, native_dependency_corpus: Path
) -> None:
    root = tmp_path / "repo"
    source = native_dependency_corpus / producer / "v1"
    paths = materialize_dependency(root, source)
    raw = dependency_capture(producer, source, input_revisions(root, paths))
    with CodeMap(root, state_dir=tmp_path / "state") as cm:
        cm.sync()
        before: Any = cm.dependency_resolution_evidence(raw)
        path = root / ("uv.lock" if producer == "uv" else "pom.xml")
        prefix = (
            "# format-only observation\n"
            if producer == "uv"
            else "<!-- format-only observation -->\n"
        )
        content = path.read_text()
        path.write_text(
            prefix + content
            if producer == "uv"
            else content.replace("</project>", prefix + "</project>")
        )
        cm.sync()
        after_raw = dependency_capture(producer, source, input_revisions(root, paths))
        if producer == "uv":
            from hashmarks.adapters import uv_lock_dependency_observation

            after_raw = uv_lock_dependency_observation(
                lock=path.read_bytes(), repository_inputs=input_revisions(root, paths)
            )
        after: Any = cm.dependency_resolution_evidence(after_raw)
        delta: Any = cm.dependency_resolution_delta(before, after)
    assert delta["change_axes"]["repository_inputs"] == "changed"
    assert delta["change_axes"]["semantic_resolution"] == "unchanged"
    assert delta["change_axes"]["physical_evidence_content"] == (
        "changed" if producer == "uv" else "unchanged"
    )
    assert delta["component_selection_transitions"] == []


@pytest.mark.parametrize(
    "scenario,transitions,removed",
    [("transitive-upgrade", 16, 5), ("mediation", 5, 0), ("exclusion", 0, 6)],
)
def test_native_maven_file_changes_preserve_expected_delta_and_projection(
    tmp_path: Path,
    scenario: str,
    transitions: int,
    removed: int,
    native_dependency_corpus: Path,
) -> None:
    root = tmp_path / "repo"
    observations: list[Any] = []
    with CodeMap(root, state_dir=tmp_path / "state") as cm:
        for endpoint in ("before", "after"):
            source = native_dependency_corpus / "maven" / scenario / endpoint
            paths = materialize_dependency(root, source)
            cm.sync()
            observations.append(
                cm.dependency_resolution_evidence(
                    dependency_capture("maven", source, input_revisions(root, paths))
                )
            )
        delta: Any = cm.dependency_resolution_delta(*observations)
    assert delta["comparability"] == "comparable"
    assert len(delta["component_selection_transitions"]) == transitions
    assert len(delta["components_removed"]) == removed
    assert all(
        row["source_equivalence"] == "proven"
        for packet in observations
        for row in packet["repository_inputs"]
    )
    assert_projection(delta, "dependency_codemap", "compare")
    projection: Any = present_repository_evidence(delta, format="text")
    findings = next(
        group["findings"]
        for group in projection["groups"]
        if group["family"] == "dependency"
    )
    assert findings[0]["kind"] == "change_axes"
    if transitions:
        assert findings[1]["kind"] == "component_selection_transitions"
        assert findings[1]["details"]["removed"] and findings[1]["details"]["added"]
    assert projection["text"].startswith("Dependency comparison: comparable\n")
    assert "Causation: not-inferred" in projection["text"]


def test_native_uv_grouped_bounds_and_incomplete_inventory_cannot_prove_absence(
    tmp_path: Path,
    native_dependency_corpus: Path,
) -> None:
    root = tmp_path / "repo"
    source = native_dependency_corpus / "uv" / "grouped"
    paths = materialize_dependency(root, source)
    raw = dependency_capture("uv", source, input_revisions(root, paths))
    with CodeMap(root, state_dir=tmp_path / "state") as cm:
        cm.sync()
        observation: Any = cm.dependency_resolution_evidence(raw)
        request = {
            "operation": "dependencies",
            "node_id": observation["roots"][0]["node_id"],
            "context": "lock",
        }
        results = [
            cast(
                Any,
                cm.dependency_resolution_queries(
                    observation, [{**request, "max_results": limit}]
                ),
            )["results"][0]
            for limit in (1, 16)
        ]
        incomplete = deepcopy(raw)
        for row in incomplete["coverage"]:
            row["completeness"] = "incomplete"
        partial: Any = cm.dependency_resolution_evidence(incomplete)
        response = cm.dependency_codemap(incomplete)
        missing = cast(
            Any,
            cm.dependency_resolution_queries(
                partial,
                [
                    {
                        "operation": "inventory",
                        "node_id": "unobserved",
                        "context": "lock",
                    }
                ],
            ),
        )["results"][0]
    assert all(result["negative_evidence"] == "not-applicable" for result in results)
    assert observation["resolution_identity"] == partial["resolution_identity"]
    assert missing["result"] == []
    assert missing["negative_evidence"] == "not-admissible"
    assert_projection(response, "dependency_codemap", "observation")


def test_native_maven_bounded_search_does_not_turn_unvisited_into_absent(
    tmp_path: Path, native_dependency_corpus: Path
) -> None:
    root = tmp_path / "repo"
    source = native_dependency_corpus / "maven" / "transitive-upgrade" / "after"
    paths = materialize_dependency(root, source)
    with CodeMap(root, state_dir=tmp_path / "state") as cm:
        cm.sync()
        observation: Any = cm.dependency_resolution_evidence(
            dependency_capture("maven", source, input_revisions(root, paths))
        )
        target = next(
            row["node_id"]
            for row in observation["selections"]
            if row["component_id"] == "com.squareup.okio:okio-jvm"
        )
        request = {
            "operation": "paths",
            "node_id": observation["roots"][0]["node_id"],
            "target_id": target,
            "context": "compile",
        }
        bounded = cast(
            Any,
            cm.dependency_resolution_queries(
                observation, [{**request, "max_visits": 1}]
            ),
        )["results"][0]
        complete = cast(Any, cm.dependency_resolution_queries(observation, [request]))[
            "results"
        ][0]
    assert bounded["result"] == []
    assert bounded["negative_evidence"] == "not-admissible"
    assert bounded["omissions"]
    assert complete["result"]


def test_native_maven_profiles_do_not_promote_context_absence_to_global_absence(
    tmp_path: Path, native_dependency_corpus: Path
) -> None:
    from hashmarks.adapters import maven_dependency_observation

    root = tmp_path / "repo"
    source = native_dependency_corpus / "maven" / "profiles"
    paths = materialize_dependency(root, source)
    contexts = ("default", "extra")
    raw = maven_dependency_observation(
        trees={
            context: (source / context / "tree.json").read_bytes()
            for context in contexts
        },
        inventories={
            context: (source / context / "list.txt").read_bytes()
            for context in contexts
        },
        complete_tree_contexts=contexts,
        complete_inventory_contexts=contexts,
        repository_inputs=input_revisions(root, paths),
    )
    with CodeMap(root, state_dir=tmp_path / "state") as cm:
        cm.sync()
        observation: Any = cm.dependency_resolution_evidence(raw)
        selection = next(
            row
            for row in observation["selections"]
            if row["component_id"] == "org.apache.commons:commons-compress"
        )
        assert selection["contexts"] == ["extra"]
        request = {"operation": "inventory", "node_id": selection["node_id"]}
        default = cast(
            Any,
            cm.dependency_resolution_queries(
                observation, [{**request, "context": "default"}]
            ),
        )["results"][0]
        extra = cast(
            Any,
            cm.dependency_resolution_queries(
                observation, [{**request, "context": "extra"}]
            ),
        )["results"][0]
        response = cm.dependency_codemap(raw)
    assert default["result"] == []
    assert default["negative_evidence"] == "admissible-within-declared-scope"
    assert extra["result"] and extra["negative_evidence"] == "not-applicable"
    assert_projection(response, "dependency_codemap", "observation")
