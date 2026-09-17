from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def _repo(root: Path) -> None:
    package = root / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from .owner import widget\n", encoding="utf-8"
    )
    (package / "owner.py").write_text(
        "def widget() -> int:\n    return 1\n", encoding="utf-8"
    )
    (root / "consumer.py").write_text("from pkg import widget\n", encoding="utf-8")


def test_exact_ownership_import_paths_reuses_exact_request_in_one_session(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        calls = 0
        original = codemap._resolve_import_owner_evidence

        def counted(source_path: str, target: str):
            nonlocal calls
            calls += 1
            return original(source_path, target)

        monkeypatch.setattr(codemap, "_resolve_import_owner_evidence", counted)
        with codemap.decision_session():
            first = codemap._exact_ownership_import_paths("consumer.py", "pkg.widget")
            second = codemap._exact_ownership_import_paths("consumer.py", "pkg.widget")
            stats = codemap.decision_session_stats()
        assert second == first and calls == 1
        assert (
            stats["ownership_import_paths_miss"] == 1
            and stats["ownership_import_paths_hit"] == 1
        )


def test_ownership_import_path_cache_key_includes_source_and_target(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        calls = 0
        original = codemap._resolve_import_owner_evidence

        def counted(source_path: str, target: str):
            nonlocal calls
            calls += 1
            return original(source_path, target)

        monkeypatch.setattr(codemap, "_resolve_import_owner_evidence", counted)
        with codemap.decision_session():
            codemap._exact_ownership_import_paths("consumer.py", "pkg.widget")
            codemap._exact_ownership_import_paths("consumer.py", "pkg.missing")
            codemap._exact_ownership_import_paths("pkg/__init__.py", ".owner.widget")
            stats = codemap.decision_session_stats()
        assert (
            calls == 3
            and stats["ownership_import_paths_miss"] == 3
            and stats["ownership_import_paths_hit"] == 0
        )


def test_cached_ownership_import_paths_are_detached_from_caller_mutation(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with codemap.decision_session():
            first = codemap._exact_ownership_import_paths("consumer.py", "pkg.widget")
            expected = list(first)
            first.append("mutated.py")
            second = codemap._exact_ownership_import_paths("consumer.py", "pkg.widget")
        assert second == expected and "mutated.py" not in second


def test_ownership_import_path_cache_is_not_reused_across_sessions(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        calls = 0
        original = codemap._resolve_import_owner_evidence

        def counted(source_path: str, target: str):
            nonlocal calls
            calls += 1
            return original(source_path, target)

        monkeypatch.setattr(codemap, "_resolve_import_owner_evidence", counted)
        with codemap.decision_session():
            codemap._exact_ownership_import_paths("consumer.py", "pkg.widget")
            codemap._exact_ownership_import_paths("consumer.py", "pkg.widget")
        with codemap.decision_session():
            codemap._exact_ownership_import_paths("consumer.py", "pkg.widget")
        assert calls == 2


def test_public_ownership_graph_batches_repeated_exact_module_probes_without_changing_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    imports: list[str] = []
    for index in range(12):
        (package / f"owner_{index}.py").write_text(
            f"def owner_{index}() -> int:\n    return {index}\n",
            encoding="utf-8",
        )
        imports.append(f"from pkg.owner_{index} import owner_{index}")
    (tmp_path / "consumer.py").write_text("\n".join(imports) + "\n", encoding="utf-8")

    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        original = codemap._preload_direct_ownership_import_modules
        monkeypatch.setattr(
            codemap, "_preload_direct_ownership_import_modules", lambda *_: None
        )
        codemap.store.reset_read_counters()
        with codemap.decision_session():
            baseline = codemap.ownership_relation_graph(
                "change imported owners", "consumer.py", max_depth=1
            )
        baseline_reads = codemap.store.read_counters()

        monkeypatch.setattr(
            codemap, "_preload_direct_ownership_import_modules", original
        )
        codemap.store.reset_read_counters()
        with codemap.decision_session():
            candidate = codemap.ownership_relation_graph(
                "change imported owners", "consumer.py", max_depth=1
            )
        candidate_reads = codemap.store.read_counters()

    assert candidate == baseline
    assert candidate_reads.get("module_paths_many") == 1
    assert candidate_reads.get("module_paths", 0) < baseline_reads.get(
        "module_paths", 0
    )
