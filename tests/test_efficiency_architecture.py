from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _call_name(node: ast.Call) -> str:
    parts: list[str] = []
    value = node.func
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if isinstance(value, ast.Name):
        parts.append(value.id)
    return ".".join(reversed(parts))


def test_ordinary_tests_do_not_dynamically_reexecute_modules_per_test() -> None:
    forbidden = {
        "importlib.util.spec_from_file_location",
        "importlib.util.module_from_spec",
    }
    violations: list[str] = []
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) or not node.name.startswith("test_"):
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and _call_name(child) in forbidden:
                    violations.append(f"{path.name}:{node.lineno}:{_call_name(child)}")
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "exec_module"
                ):
                    violations.append(f"{path.name}:{node.lineno}:exec_module")
    assert violations == [], (
        "per-test dynamic module re-execution defeats normal module/cache ownership: "
        + ", ".join(violations)
    )


def test_lru_cache_ownership_is_module_level_or_explicit_static_pure_wrapper() -> None:
    violations: list[str] = []
    for path in sorted((ROOT / "hashmarks").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            cached = False
            for decorator in node.decorator_list:
                target = (
                    decorator.func if isinstance(decorator, ast.Call) else decorator
                )
                name = (
                    target.attr
                    if isinstance(target, ast.Attribute)
                    else target.id
                    if isinstance(target, ast.Name)
                    else ""
                )
                if name in {"lru_cache", "cache"}:
                    cached = True
            if not cached:
                continue
            parent = parents.get(node)
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                violations.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}:nested cached function"
                )
            elif isinstance(parent, ast.ClassDef):
                decorators = {
                    d.id for d in node.decorator_list if isinstance(d, ast.Name)
                }
                if "staticmethod" not in decorators:
                    violations.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}:instance/class-owned cache"
                    )
    assert violations == [], (
        "cache lifetime must not be owned by mutable objects or recreated inside calls: "
        + ", ".join(violations)
    )


def test_hot_codemap_loops_do_not_issue_known_row_at_a_time_store_reads() -> None:
    path = ROOT / "hashmarks" / "codemap" / "engine.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    guarded = {
        "_find_impl",
        "ownership_relation_graph",
        "task_graph_adjacency",
        "deps",
        "refs",
        "_context_impl",
    }
    row_reads = {"file_row", "edges_from", "refs", "symbols_named"}
    violations: list[str] = []
    for fn in [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name in guarded
    ]:
        for loop in [
            n
            for n in ast.walk(fn)
            if isinstance(
                n,
                (
                    ast.For,
                    ast.While,
                    ast.ListComp,
                    ast.SetComp,
                    ast.DictComp,
                    ast.GeneratorExp,
                ),
            )
        ]:
            for child in ast.walk(loop):
                if not isinstance(child, ast.Call) or not isinstance(
                    child.func, ast.Attribute
                ):
                    continue
                if (
                    child.func.attr in row_reads
                    and isinstance(child.func.value, ast.Attribute)
                    and child.func.value.attr == "store"
                ):
                    violations.append(
                        f"{fn.name}:{getattr(child, 'lineno', '?')}:{child.func.attr}"
                    )
    # Some graph/import loops still require context-dependent lookups; keep this guard
    # focused on newly closed high-volume paths and explicitly review any additions.
    allowed_prefixes = {
        "ownership_relation_graph:file_row",  # exact import source/visibility is path-context dependent
        "_context_impl:edges_from",  # bounded top-hit evidence escalation; tracked separately
        "deps:edges_from",  # single-symbol/file public query surface
        "refs:refs",  # one reverse-reference query feeding a comprehension
    }
    unexpected = [
        v
        for v in violations
        if not any(
            v.startswith(prefix.split(":")[0] + ":")
            and v.endswith(":" + prefix.split(":")[1])
            for prefix in allowed_prefixes
        )
    ]
    assert unexpected == [], (
        "hot path added row-at-a-time store reads instead of bulk/stable-key reuse: "
        + ", ".join(unexpected)
    )


def test_bounded_rerank_topn_matches_reference_full_sort(tmp_path: Path) -> None:
    from hashmarks.codemap.engine import CodeMap
    from hashmarks.codemap.query_primitives import _query_terms

    rows: list[dict] = []
    for index in range(420):
        path = f"src/pkg_{index % 97:03d}/module_{index % 31:02d}.py"
        rows.append(
            {
                "path": path,
                "name": f"release_contract_{index % 43}",
                "qualname": f"Owner.release_contract_{index % 43}",
                "signature": "release authority privacy contract",
                "_relation_boost": float(index % 7),
            }
        )
    query = "release authority privacy contract"
    tokens = tuple(_query_terms(query))
    limit = 20
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        raw = query.strip().lower()
        ordered = sorted(
            rows,
            key=lambda row: (
                -codemap._candidate_prescore(query, row, tokens=tokens, raw_query=raw),
                str(row.get("path", "")),
                str(row.get("qualname", "")),
            ),
        )
        rerank_limit = max(256, limit * 16)
        path_quota = min(64, max(16, rerank_limit // 4))
        reference: list[dict] = []
        selected_ids: set[int] = set()
        seen_paths: set[str] = set()
        for row in ordered:
            path = str(row.get("path", ""))
            if path in seen_paths:
                continue
            reference.append(row)
            selected_ids.add(id(row))
            seen_paths.add(path)
            if len(reference) >= path_quota:
                break
        for row in ordered:
            if id(row) in selected_ids:
                continue
            reference.append(row)
            if len(reference) >= rerank_limit:
                break
        actual = codemap._bounded_rerank_rows(
            query, tuple(rows), limit=limit, tokens=tokens
        )
    assert list(actual) == reference


def test_symbols_for_paths_many_matches_per_path_prefixes(tmp_path: Path) -> None:
    from hashmarks.codemap.engine import CodeMap

    (tmp_path / "a.py").write_text(
        "def a1():\n    pass\n\ndef a2():\n    pass\n\ndef a3():\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "b.py").write_text(
        "class B:\n    def b1(self):\n        pass\n    def b2(self):\n        pass\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        expected = {
            path: codemap.store.symbols_for_path(path)[:2] for path in ("a.py", "b.py")
        }
        codemap.store.reset_read_counters()
        actual = codemap.store.symbols_for_paths_many(
            ["a.py", "b.py"], limit_per_path=2
        )
        counters = codemap.store.read_counters()
    assert actual == expected
    assert counters == {"symbols_for_paths_many": 1}


def test_decision_session_exact_symbol_cache_reuses_larger_prefix(
    tmp_path: Path,
) -> None:
    from hashmarks.codemap.engine import CodeMap

    (tmp_path / "owners.py").write_text(
        "class AlphaOwner:\n    pass\n\nclass BetaOwner:\n    pass\n\nclass GammaOwner:\n    pass\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        with codemap.decision_session():
            broad = codemap._session_exact_symbol_candidates(
                ["AlphaOwner", "BetaOwner", "GammaOwner"], limit=20
            )
            narrow = codemap._session_exact_symbol_candidates(
                ["GammaOwner", "AlphaOwner", "BetaOwner", "AlphaOwner"], limit=2
            )
            stats = codemap.decision_session_stats()
        assert narrow == broad[:2]
        assert stats.get("store_exact_symbol_candidates") == 1
        assert stats.get("exact_symbols_miss") == 1
        assert stats.get("exact_symbols_hit") == 1
        assert codemap._decision_exact_symbols_cache == {}
        assert codemap._decision_module_paths_cache == {}


def test_decision_session_caches_missing_file_rows_and_detaches_sessions(
    tmp_path: Path,
) -> None:
    from hashmarks.codemap.engine import CodeMap

    (tmp_path / "owner.py").write_text("value = 1\n", encoding="utf-8")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        with codemap.decision_session():
            first = codemap._session_file_rows(["owner.py", "missing.py", "owner.py"])
            second = codemap._session_file_rows(["missing.py", "owner.py"])
            stats = codemap.decision_session_stats()
        assert set(first) == {"owner.py"}
        assert second == first
        assert stats["file_row_miss"] == 2
        assert stats["file_row_hit"] == 2
        assert codemap._decision_file_row_cache == {}


def test_decision_session_reuses_graph_prefixes_and_file_rows(tmp_path: Path) -> None:
    from hashmarks.codemap.engine import CodeMap

    (tmp_path / "owner.py").write_text(
        "class Owner:\n    def work(self):\n        return helper()\n\ndef helper():\n    return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "test_owner.py").write_text(
        "from owner import Owner\n\ndef test_work():\n    assert Owner().work() == 1\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        with codemap.decision_session():
            rows = codemap._session_file_rows(["owner.py", "test_owner.py"])
            assert set(rows) == {"owner.py", "test_owner.py"}
            assert codemap._session_file_row("owner.py") is not None

            refs_wide = codemap._session_refs_many(["Owner"], limit_per_target=20)
            refs_narrow = codemap._session_refs_many(["Owner"], limit_per_target=1)
            assert refs_narrow["Owner"] == refs_wide["Owner"][:1]

            edges_wide = codemap._session_edges_from_many(
                [("owner.py", "Owner.work")], limit_per_seed=20
            )
            edges_narrow = codemap._session_edges_from_many(
                [("owner.py", "Owner.work")], limit_per_seed=1
            )
            assert (
                edges_narrow[("owner.py", "Owner.work")]
                == edges_wide[("owner.py", "Owner.work")][:1]
            )

            by_path_wide = codemap._session_edges_for_paths_many(
                ["owner.py"], limit_per_path=20
            )
            by_path_narrow = codemap._session_edges_for_paths_many(
                ["owner.py"], limit_per_path=1
            )
            assert by_path_narrow["owner.py"] == by_path_wide["owner.py"][:1]
            stats = codemap.decision_session_stats()

        assert stats.get("store_file_rows") == 1
        assert stats.get("store_file_row", 0) == 0
        assert stats.get("store_refs_many") == 1
        assert stats.get("store_edges_from_many") == 1
        assert stats.get("store_edges_for_paths_many") == 1
        assert stats.get("refs_hit") == 1
        assert stats.get("edges_from_hit") == 1
        assert stats.get("edges_for_path_hit") == 1
        assert codemap._decision_refs_cache == {}
        assert codemap._decision_edges_from_cache == {}
        assert codemap._decision_edges_for_path_cache == {}


def test_reverse_reference_identity_is_canonicalized_by_target_short(
    tmp_path: Path,
) -> None:
    from hashmarks.codemap.engine import CodeMap

    (tmp_path / "owner.py").write_text(
        "class Owner:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "consumer.py").write_text(
        "from owner import Owner\n\ndef build():\n    return Owner()\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        unqualified = codemap.store.refs("Owner", limit=20)
        qualified = codemap.store.refs("owner.Owner", limit=20)
        assert qualified == unqualified

        codemap.store.reset_read_counters()
        grouped = codemap.store.refs_many(
            ["Owner", "owner.Owner", "pkg.other.Owner"], limit_per_target=20
        )
        counters = codemap.store.read_counters()
        assert grouped["Owner"] == grouped["owner.Owner"] == grouped["pkg.other.Owner"]
        assert counters == {"refs_many": 1}

        with codemap.decision_session():
            first = codemap._session_refs_many(["owner.Owner"], limit_per_target=20)
            second = codemap._session_refs_many(["pkg.other.Owner"], limit_per_target=5)
            stats = codemap.decision_session_stats()
        assert second["pkg.other.Owner"] == first["owner.Owner"][:5]
        assert stats.get("store_refs_many") == 1
        assert stats.get("refs_miss") == 1
        assert stats.get("refs_hit") == 1


def test_decision_symbol_preload_uses_complete_multi_path_evidence(
    tmp_path: Path,
) -> None:
    from hashmarks.codemap.engine import CodeMap

    (tmp_path / "dense.py").write_text(
        "\n".join(f"def dense_{i}():\n    return {i}\n" for i in range(40)),
        encoding="utf-8",
    )
    (tmp_path / "later.py").write_text(
        "def later_one():\n    return 1\n\ndef later_two():\n    return 2\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        expected_dense = codemap.store.symbols_for_path("dense.py")
        expected_later = codemap.store.symbols_for_path("later.py")
        codemap.store.reset_read_counters()
        with codemap.decision_session():
            codemap._session_preload_symbols(["dense.py", "later.py"])
            dense = codemap._session_symbols_for_path("dense.py")
            later = codemap._session_symbols_for_path("later.py")
            stats = codemap.decision_session_stats()
        assert [row["qualname"] for row in dense] == [
            row["qualname"] for row in expected_dense
        ]
        assert [row["qualname"] for row in later] == [
            row["qualname"] for row in expected_later
        ]
        assert stats.get("store_symbols_for_paths_complete") == 1
        assert stats.get("store_symbols_for_path", 0) == 0


def test_module_paths_many_matches_individual_and_session_preload(
    tmp_path: Path,
) -> None:
    from hashmarks.codemap.engine import CodeMap

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text(
        "from .owner import Owner\n", encoding="utf-8"
    )
    (tmp_path / "pkg" / "owner.py").write_text(
        "class Owner:\n    pass\n", encoding="utf-8"
    )
    (tmp_path / "pkg" / "helper.py").write_text(
        "def helper():\n    return 1\n", encoding="utf-8"
    )
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        modules = [
            "pkg.owner.Owner",
            "pkg.owner",
            "pkg.helper.helper",
            "pkg.helper",
            "pkg.missing",
        ]
        expected = {module: codemap.store.module_paths(module) for module in modules}
        codemap.store.reset_read_counters()
        actual = codemap.store.module_paths_many(modules)
        assert actual == expected
        assert codemap.store.read_counters() == {"module_paths_many": 1}

        codemap.store.reset_read_counters()
        with codemap.decision_session():
            codemap._session_preload_module_paths(modules)
            resolved = {
                module: codemap._session_module_paths(module) for module in modules
            }
            stats = codemap.decision_session_stats()
        assert resolved == expected
        assert stats.get("store_module_paths_many") == 1
        assert stats.get("store_module_paths", 0) == 0
        assert stats.get("module_paths_miss") == len(set(modules))
        assert stats.get("module_paths_hit") == len(modules)
        assert codemap._decision_module_paths_cache == {}


def test_tooling_does_not_parse_direct_path_read_text_without_ast_cache() -> None:
    roots = (ROOT / "hashmarks", ROOT / "scripts", ROOT / "benchmarks")
    violations: list[str] = []
    for base in roots:
        for path in sorted(base.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    not isinstance(node, ast.Call)
                    or _call_name(node) != "ast.parse"
                    or not node.args
                ):
                    continue
                first = node.args[0]
                if not isinstance(first, ast.Call) or not isinstance(
                    first.func, ast.Attribute
                ):
                    continue
                if first.func.attr == "read_text":
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert violations == [], (
        "route file-backed Python AST parsing through hashmarks.python_ast_cache: "
        + ", ".join(violations)
    )
