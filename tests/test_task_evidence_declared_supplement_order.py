"""Already-disclosed class methods need no second initial retrieval slot."""

from pathlib import Path

from contract_assertions import assert_object, assert_records

from hashmarks.codemap import CodeMap


def _repository(root: Path) -> str:
    (root / "client.py").write_text(
        "class CatalogClient:\n"
        "    def _metadata_update(self, cluster_metadata):\n"
        "        return cluster_metadata\n"
        "    def force_metadata_update(self):\n"
        "        return None\n"
    )
    (root / "listener.py").write_text(
        "class CatalogCoordinator:\n"
        "    def _handle_metadata_update(self):\n"
        "        return None\n"
    )
    (root / "state.py").write_text(
        "class ClusterMetadata:\n"
        "    def failed_update(self, exception):\n"
        "        self._future.set_exception(exception)\n"
        "    def update_metadata(self, metadata):\n"
        "        self._future.set_result(metadata)\n"
    )
    return "Catalog metadata update notifications complete a future using methods that it does not support."


def test_already_declared_supplement_preserves_initial_canonical_source_diversity(
    tmp_path: Path,
) -> None:
    task = _repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.tasks.action_map(task)
        canonical = list(
            dict.fromkeys(hit.path for hit in codemap.search.find_task(task))
        )[:3]
        assert set(canonical) == {"client.py", "listener.py", "state.py"}
        packet = codemap.tasks.evidence(task)
    initial = packet["retrieval"]["results"][:3]
    assert set(canonical) <= {row["path"] for row in initial}
    assert packet["ownership"]["owner"] == action["admitted_edit"]
    assert packet["verification"]["selected"] == action["verify"]
    declarations = {
        row["symbol"]
        for locator in initial
        for row in assert_records(
            assert_object(locator.get("class_declarations", {})).get("declarations", [])
        )
    }
    assert "CatalogClient.force_metadata_update" in declarations
    assert "ClusterMetadata.failed_update" in declarations
    assert len(packet["retrieval"]["results"]) <= 20


def test_explicit_method_keeps_initial_precedence(tmp_path: Path) -> None:
    task = _repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.tasks.evidence(
            task + " Inspect client.py::CatalogClient.force_metadata_update."
        )
    assert (
        packet["retrieval"]["results"][0].get("symbol")
        == "CatalogClient.force_metadata_update"
    )


def test_method_outside_disclosed_class_bound_keeps_its_own_slot(
    tmp_path: Path,
) -> None:
    task = _repository(tmp_path)
    source = tmp_path / "client.py"
    declarations = "".join(
        f"    def unrelated_{i}(self): return None\n" for i in range(20)
    )
    source.write_text(
        source.read_text().replace(
            "    def force_metadata_update",
            declarations + "    def force_metadata_update",
        )
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.tasks.evidence(task)
    assert "CatalogClient.force_metadata_update" in {
        row.get("symbol") for row in packet["retrieval"]["results"][:3]
    }
