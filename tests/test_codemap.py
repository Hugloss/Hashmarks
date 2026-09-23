from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.model import EvidenceVisibility
from hashmarks.codemap.parsers import parse_source
from hashmarks.codemap.repository_index_store import WorkspaceMapStore


def _write_repo(root: Path) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "src" / "auth.py").write_text(
        """from src.users import User\n\nclass AuthService:\n    def login(self, name: str) -> User:\n        return User(name)\n\n    def logout(self) -> None:\n        return None\n""",
        encoding="utf-8",
    )
    (root / "src" / "users.py").write_text(
        """class User:\n    def __init__(self, name: str):\n        self.name = name\n""",
        encoding="utf-8",
    )
    (root / "tests" / "test_auth.py").write_text(
        """from src.auth import AuthService\n\ndef test_login():\n    assert AuthService().login('a').name == 'a'\n""",
        encoding="utf-8",
    )


def test_identity_import_graph_does_not_import_codemap():
    code = "import hashmarks; import sys; print(any(k.startswith('hashmarks.codemap') for k in sys.modules))"
    completed = subprocess.run(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1])},
    )
    assert completed.stdout.strip() == "False"


def test_codemap_sync_outline_find_and_context(tmp_path: Path):
    _write_repo(tmp_path)
    with CodeMap(
        tmp_path, artifact_db=tmp_path / "shared-artifacts.sqlite3"
    ) as codemap:
        first = codemap.sync()
        assert first.discovered == 3
        assert first.parsed_artifacts == 3
        assert first.parse_errors == 0

        second = codemap.sync()
        assert second.parsed_artifacts == 0
        assert second.reused_artifacts == 3
        assert second.generation == first.generation

        outline = codemap.outline("src/auth.py")
        assert "class AuthService" in outline["outline"]
        assert "def login" in outline["outline"]
        assert outline["outline_tokens"] < outline["full_tokens"]

        hits = codemap.find("AuthService login")
        assert hits
        assert any(hit.qualname == "AuthService.login" for hit in hits)

        pack = codemap.context("AuthService login", token_budget=500)
        assert not pack.abstained
        assert pack.confidence in {"high", "medium"}
        assert 0 < pack.estimated_tokens <= 500
        assert any(item.symbol == "AuthService.login" for item in pack.items)
        assert all(item.representation != "full-file" for item in pack.items)


def test_codemap_unknown_query_abstains(tmp_path: Path):
    _write_repo(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        pack = codemap.context("quantum banana unrelated subsystem", token_budget=500)
    assert pack.abstained
    assert pack.confidence == "insufficient"
    assert not pack.items


def test_outline_refreshes_only_changed_file(tmp_path: Path):
    _write_repo(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        first = codemap.sync()
        old = codemap.outline("src/auth.py")
        (tmp_path / "src" / "auth.py").write_text(
            (tmp_path / "src" / "auth.py").read_text(encoding="utf-8")
            + "\ndef reset_password(user: str) -> None:\n    return None\n",
            encoding="utf-8",
        )
        new = codemap.outline("src/auth.py")
        assert "reset_password" in new["outline"]
        assert new["file_digest"] != old["file_digest"]
        assert new["generation"] > first.generation


def test_evidence_visibility_is_separate_from_indexing(tmp_path: Path):
    _write_repo(tmp_path)
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "lib.py").write_text(
        "def vendor_secret_algorithm():\n    return 'implementation-secret'\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.py").write_text("SECRET = 'never-index-me'\n", encoding="utf-8")
    (tmp_path / ".hashmarks-context.toml").write_text(
        """[[rule]]\npattern = "vendor/**"\nvisibility = "outline"\n""",
        encoding="utf-8",
    )

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        result = codemap.sync()
        assert (
            result.discovered == 4
        )  # three normal Python files + vendor; .env.py denied
        outline = codemap.outline("vendor/lib.py")
        assert outline["evidence_visibility"] == "outline"
        pack = codemap.context("vendor_secret_algorithm", token_budget=500)
        assert not pack.abstained
        vendor_items = [item for item in pack.items if item.path == "vendor/lib.py"]
        assert vendor_items
        assert all(item.representation == "signature" for item in vendor_items)
        assert all("implementation-secret" not in item.content for item in vendor_items)
        assert all(hit.path != ".env.py" for hit in codemap.find("never-index-me"))


def test_path_only_index_supports_other_repo_languages(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text(
        "export function login() { return true }\n", encoding="utf-8"
    )
    (tmp_path / "main.go").write_text(
        "package main\nfunc main() {}\n", encoding="utf-8"
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        result = codemap.sync()
        capsule = codemap.orient()
        hits = codemap.find("app.ts")
    assert result.discovered == 2
    assert capsule["languages"] == {"go": 1, "typescript": 1}
    assert hits and hits[0].path == "src/app.ts"


@pytest.mark.host_git
def test_content_addressed_artifacts_reused_across_git_worktrees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    if not shutil_which("git"):
        pytest.skip("git not installed")
    # Exercise the production default shared-cache routing without depending on
    # or mutating the developer's persistent Hashmarks cache.  pytest temp paths
    # can repeat across separate native runs, while ~/.cache/hashmarks correctly
    # survives them; without this isolation the first sync may legitimately reuse
    # an artifact left by an earlier test-profile run.
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "hashmarks@example.invalid"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Hashmarks Test"], cwd=repo, check=True
    )
    subprocess.run(["git", "add", "mod.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    worktree = tmp_path / "worktree"
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "other", str(worktree)],
        cwd=repo,
        check=True,
    )

    with CodeMap(repo) as first_map:
        first = first_map.sync()
        first_artifact_db = first_map.artifacts.db_path
    with CodeMap(worktree) as second_map:
        second = second_map.sync()
        second_artifact_db = second_map.artifacts.db_path

    assert first.parsed_artifacts == 1
    assert second.parsed_artifacts == 0
    assert second.reused_artifacts == 1
    assert first_artifact_db == second_artifact_db


def shutil_which(name: str) -> str | None:
    from shutil import which

    return which(name)


def test_incremental_sync_reindexes_only_changed_path_and_handles_subtree_removal(
    tmp_path: Path,
):
    _write_repo(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        (tmp_path / "src" / "auth.py").write_text(
            (tmp_path / "src" / "auth.py").read_text(encoding="utf-8")
            + "\ndef only_changed():\n    return 1\n",
            encoding="utf-8",
        )
        update = codemap.sync(["src/auth.py"])
        assert update.discovered == 1
        assert update.parsed_artifacts == 1
        assert "only_changed" in codemap.outline("src/auth.py")["outline"]

        for child in (tmp_path / "tests").iterdir():
            child.unlink()
        (tmp_path / "tests").rmdir()
        removal = codemap.sync(["tests"])
        assert removal.removed == 1
        assert all(not path.startswith("tests/") for path in codemap.store.paths())


def test_persistent_grep_returns_only_candidate_lines_and_respects_outline_only(
    tmp_path: Path,
):
    _write_repo(tmp_path)
    (tmp_path / "src" / "errors.py").write_text(
        "def fail():\n    raise RuntimeError('terminal cancellation handshake failed')\n",
        encoding="utf-8",
    )
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "hidden.py").write_text(
        "def hidden():\n    return 'terminal cancellation handshake failed'\n",
        encoding="utf-8",
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        "[[rule]]\npattern='vendor/**'\nvisibility='outline'\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        result = codemap.grep("terminal cancellation handshake", context_lines=0)
    by_path = {row["path"]: row for row in result["matches"]}
    assert "src/errors.py" in by_path
    assert (
        "terminal cancellation handshake failed" in by_path["src/errors.py"]["content"]
    )
    assert "vendor/hidden.py" not in by_path


def test_find_auto_indexes_cold_repo(tmp_path: Path):
    _write_repo(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        assert codemap.status()["files"] == 0
        hits = codemap.find("AuthService")
        assert hits
        assert codemap.status()["files"] == 3


def test_polyglot_advisory_outlines_are_provenance_bounded(tmp_path: Path):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "auth.ts").write_text(
        """import { user } from './user'\nexport class AuthService {}\nexport async function login(token: string): Promise<boolean> { return true }\nexport const logout = () => false\n""",
        encoding="utf-8",
    )
    (tmp_path / "main.go").write_text(
        'package main\nimport "example/auth"\ntype Service struct {}\nfunc (s *Service) Login() bool { return true }\n',
        encoding="utf-8",
    )
    (tmp_path / "lib.rs").write_text(
        "use crate::auth::Token;\npub struct Session {}\npub fn validate(token: Token) -> bool { true }\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        ts = codemap.outline("web/auth.ts")
        go = codemap.outline("main.go")
        rust = codemap.outline("lib.rs")
        deps = codemap.deps("web/auth.ts")
    assert (
        "AuthService" in ts["outline"]
        and "login" in ts["outline"]
        and "logout" in ts["outline"]
    )
    assert "Service" in go["outline"] and "Login" in go["outline"]
    assert "Session" in rust["outline"] and "validate" in rust["outline"]
    assert any(
        edge["target"] == "./user" and edge["confidence"] == "lexical"
        for edge in deps["edges"]
    )


def test_symbol_source_is_exact_budgeted_and_policy_checked(tmp_path: Path):
    _write_repo(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        source = codemap.source("src/auth.py::AuthService.login", token_budget=200)
        assert source["too_large"] is False
        assert "def login" in source["content"]
        assert "def logout" not in source["content"]
        tiny = codemap.source("src/auth.py::AuthService", token_budget=20)
        assert tiny["too_large"] is True
        assert "content" not in tiny


def test_reverse_dependency_graph_finds_transitive_tests(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "users.py").write_text(
        "class User:\n    pass\n", encoding="utf-8"
    )
    (tmp_path / "src" / "auth.py").write_text(
        "from src.users import User\n\ndef login():\n    return User()\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_auth.py").write_text(
        "from src.auth import login\n\ndef test_login():\n    assert login()\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        affected = codemap.affected("src/users.py")
        tests = codemap.tests("User")
    assert "src/auth.py" in affected["affected_files"]
    assert "tests/test_auth.py" in affected["tests"]
    assert "tests/test_auth.py" in tests["tests"]


def test_public_codemap_api_is_lazy_and_identity_owns_lazy_map(tmp_path: Path):
    code = (
        "import sys; import hashmarks; "
        "print(any(k.startswith('hashmarks.codemap') for k in sys.modules)); "
        "from hashmarks import CodeMap; "
        "print(CodeMap.__name__); "
        "print(any(k.startswith('hashmarks.codemap') for k in sys.modules))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1])},
    )
    assert completed.stdout.splitlines() == ["False", "CodeMap", "True"]

    from hashmarks import RepositoryIdentity

    identity = RepositoryIdentity(tmp_path, mode="local")
    assert identity._codemap is None
    codemap = identity.code_map()
    assert codemap.workspace == tmp_path.resolve()
    assert identity.code_map() is codemap
    identity.close()
    assert identity._codemap is None


def test_optional_precision_provider_changes_artifact_namespace(tmp_path: Path):
    _write_repo(tmp_path)

    class FakeStatus:
        def as_dict(self):
            return {
                "name": "fake-structural",
                "available": True,
                "version": "1",
                "detail": None,
            }

    class FakeProvider:
        def signature(self, language):
            return f"fake.v1:{language}"

        def enrich(self, artifact, source, language):
            return artifact

        def status(self):
            return FakeStatus()

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.range_provider = FakeProvider()
        first = codemap.sync()
        key = str(codemap.store.file_row("src/auth.py")["artifact_key"])
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as plain:
        plain.range_provider = type(
            "Off",
            (),
            {
                "signature": lambda self, language: None,
                "enrich": lambda self, artifact, source, language: artifact,
                "status": lambda self: FakeStatus(),
            },
        )()
        second = plain.sync()
        plain_key = str(plain.store.file_row("src/auth.py")["artifact_key"])
    assert first.parsed_artifacts == 3
    assert second.parsed_artifacts == 3
    assert key != plain_key


def test_npm_project_graph_enrichment_and_reverse_project_impact(tmp_path: Path):
    (tmp_path / "packages" / "a" / "src").mkdir(parents=True)
    (tmp_path / "packages" / "b" / "src").mkdir(parents=True)
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "root", "private": True, "workspaces": ["packages/*"]}),
        encoding="utf-8",
    )
    (tmp_path / "packages" / "a" / "package.json").write_text(
        json.dumps({"name": "@hm/a", "dependencies": {"@hm/b": "workspace:*"}}),
        encoding="utf-8",
    )
    (tmp_path / "packages" / "b" / "package.json").write_text(
        json.dumps({"name": "@hm/b"}), encoding="utf-8"
    )
    (tmp_path / "packages" / "a" / "src" / "a.ts").write_text(
        "export function a() { return 1 }\n", encoding="utf-8"
    )
    (tmp_path / "packages" / "b" / "src" / "b.ts").write_text(
        "export function b() { return 2 }\n", encoding="utf-8"
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        enriched = codemap.enrich_projects(("npm-package-graph",))
        impacted = codemap.affected("packages/b/src/b.ts")
        capsule = codemap.orient()
    ids = {row["project_id"] for row in enriched["projects"]}
    assert {"npm:root", "npm:@hm/a", "npm:@hm/b"} <= ids
    assert any(
        edge["source"] == "npm:@hm/a" and edge["target"] == "npm:@hm/b"
        for edge in enriched["edges"]
    )
    assert impacted["root_projects"] == ["npm:@hm/b"]
    assert "npm:@hm/a" in impacted["affected_projects"]
    assert capsule["projects"]


def test_ast_grep_structural_search_is_optional_local_and_policy_filtered(
    tmp_path: Path,
):
    _write_repo(tmp_path)
    binary = tmp_path / "node_modules" / ".bin" / "ast-grep"
    binary.parent.mkdir(parents=True)
    binary.write_text(
        """#!/usr/bin/env python3
import json, sys
if '--version' in sys.argv:
    print('ast-grep 99.0-test')
    raise SystemExit(0)
print(json.dumps({
  'text': 'AuthService().login(name)',
  'file': 'src/auth.py',
  'language': 'Python',
  'range': {'start': {'line': 3, 'column': 4}, 'end': {'line': 3, 'column': 29}}
}))
""",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        result = codemap.structural("$A.login($B)", language="python")
        status = codemap.status()
    assert result["available"] is True
    assert result["matches"][0]["path"] == "src/auth.py"
    assert result["matches"][0]["range"] == [4, 4]
    providers = {row["name"]: row for row in status["precision_providers"]}
    assert providers["ast-grep-structural-search"]["available"] is True


def test_ast_grep_structural_search_never_discloses_outline_only_match(tmp_path: Path):
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "secret.py").write_text(
        "def secret_impl():\n    return 42\n", encoding="utf-8"
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        "[[rule]]\npattern='vendor/**'\nvisibility='outline'\n", encoding="utf-8"
    )
    binary = tmp_path / "node_modules" / ".bin" / "ast-grep"
    binary.parent.mkdir(parents=True)
    binary.write_text(
        """#!/usr/bin/env python3
import json, sys
if '--version' in sys.argv:
    print('ast-grep test')
    raise SystemExit(0)
print(json.dumps({'text':'return 42','file':'vendor/secret.py','language':'Python','range':{'start':{'line':1},'end':{'line':1}}}))
""",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        result = codemap.structural("return $A", language="python")
    assert result["matches"] == []


def test_scip_json_import_adds_native_definitions_and_references(tmp_path: Path):
    _write_repo(tmp_path)
    scip_json = tmp_path / "index.json"
    scip_json.write_text(
        json.dumps(
            {
                "metadata": {"toolInfo": {"name": "scip-python", "version": "test"}},
                "documents": [
                    {
                        "relativePath": "src/auth.py",
                        "occurrences": [
                            {
                                "range": [2, 6, 17],
                                "symbol": "scip-python python demo 0.1.0 `src.auth`/AuthService#",
                                "symbolRoles": 1,
                            }
                        ],
                    },
                    {
                        "relativePath": "tests/test_auth.py",
                        "occurrences": [
                            {
                                "range": [3, 11, 22],
                                "symbol": "scip-python python demo 0.1.0 `src.auth`/AuthService#",
                                "symbolRoles": 0,
                            }
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        imported = codemap.import_scip(scip_json)
        refs = codemap.refs("AuthService")
        deps = codemap.deps("test_login")
        hits = codemap.find("AuthService", limit=10)
    assert imported["producer"] == "scip-python:test"
    assert imported["definitions"] == 1
    assert imported["references"] == 1
    assert any(
        row["path"] == "tests/test_auth.py" and row["target_name"] == "AuthService"
        for row in refs["native_references"]
    )
    assert any(row["target_name"] == "AuthService" for row in deps["native_edges"])
    assert any(hit.path == "src/auth.py" for hit in hits)


def test_graph_reference_expansion_prefers_referenced_source_over_unreferenced_source(
    tmp_path: Path,
):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "central.py").write_text(
        "def shared_name():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "src" / "lonely.py").write_text(
        "def shared_name():\n    return 2\n", encoding="utf-8"
    )
    (tmp_path / "src" / "caller_a.py").write_text(
        "from src.central import shared_name\n", encoding="utf-8"
    )
    (tmp_path / "src" / "caller_b.py").write_text(
        "from src.central import shared_name\n", encoding="utf-8"
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        hits = [
            hit
            for hit in codemap.find("shared_name", limit=10)
            if hit.qualname == "shared_name"
        ]
    assert hits
    assert hits[0].path == "src/central.py"


def test_typescript_native_resolver_edges_close_path_alias_impact(tmp_path: Path):
    from hashmarks.codemap.typescript_resolver import TypeScriptResolverProvider

    (tmp_path / "src").mkdir()
    (tmp_path / "node_modules" / "typescript").mkdir(parents=True)
    (tmp_path / "tsconfig.json").write_text(
        json.dumps(
            {"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["src/*"]}}}
        ),
        encoding="utf-8",
    )
    (tmp_path / "src" / "user.ts").write_text(
        "export const user = 1\n", encoding="utf-8"
    )
    (tmp_path / "src" / "auth.ts").write_text(
        "import { user } from '@app/user'\nexport const auth = user\n", encoding="utf-8"
    )
    fake_node = tmp_path / "fake-node"
    fake_node.write_text(
        """#!/usr/bin/env python3
import json
print(json.dumps({'version':'test-ts','config':'tsconfig.json','edges':[{'source':'src/auth.ts','target':'src/user.ts','specifier':'@app/user'}]}))
""",
        encoding="utf-8",
    )
    fake_node.chmod(0o755)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        codemap.typescript_resolver = TypeScriptResolverProvider(node=str(fake_node))
        enriched = codemap.enrich_projects(("typescript-resolver",))
        affected = codemap.affected("src/user.ts")
        deps = codemap.deps("src/auth.ts")
    assert enriched["native_file_edges"][0]["target"] == "src/user.ts"
    assert "src/auth.ts" in affected["affected_files"]
    assert any(row["specifier"] == "@app/user" for row in deps["native_file_edges"])


def test_context_orients_before_source_and_does_not_spend_budget_on_test_bodies(
    tmp_path: Path,
):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "policy.py").write_text(
        "class ImpactTrustPolicy:\n"
        "    def allows_complete_evidence(self, producer: str) -> bool:\n"
        '        trusted = {"native-runner", "compiler-depfile"}\n'
        "        return producer in trusted\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_policy.py").write_text(
        "from src.policy import ImpactTrustPolicy\n\n"
        "def test_impact_trust_policy_complete_evidence_from_trusted_producer():\n"
        "    policy = ImpactTrustPolicy()\n"
        "    # Deliberately verbose body: this should not crowd source context\n"
        "    evidence = [str(i) for i in range(200)]\n"
        "    assert evidence\n"
        "    assert policy.allows_complete_evidence('native-runner')\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        pack = codemap.context(
            "ImpactTrustPolicy complete evidence trusted producer", token_budget=420
        )

    assert not pack.abstained
    source_items = [item for item in pack.items if item.path == "src/policy.py"]
    test_items = [item for item in pack.items if item.path == "tests/test_policy.py"]
    assert source_items
    assert any(
        item.symbol == "ImpactTrustPolicy.allows_complete_evidence"
        for item in source_items
    )
    assert any(item.representation == "source-range" for item in source_items)
    assert test_items
    assert all(item.representation != "source-range" for item in test_items)
    assert all("range(200)" not in item.content for item in test_items)


def test_context_can_include_test_body_when_task_explicitly_requests_tests(
    tmp_path: Path,
):
    _write_repo(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        pack = codemap.context("test login AuthService", token_budget=500)
    assert any(
        item.path == "tests/test_auth.py" and item.representation == "source-range"
        for item in pack.items
    )


def test_scip_evidence_is_ignored_after_codemap_generation_changes(tmp_path: Path):
    _write_repo(tmp_path)
    scip_json = tmp_path / "index.json"
    scip_json.write_text(
        json.dumps(
            {
                "metadata": {
                    "toolInfo": {"name": "scip-python", "version": "freshness-test"}
                },
                "documents": [
                    {
                        "relativePath": "src/auth.py",
                        "occurrences": [
                            {
                                "range": [2, 6, 17],
                                "symbol": "scip-python python demo 0.1.0 `src.auth`/AuthService#",
                                "symbolRoles": 1,
                            }
                        ],
                    },
                    {
                        "relativePath": "tests/test_auth.py",
                        "occurrences": [
                            {
                                "range": [3, 11, 22],
                                "symbol": "scip-python python demo 0.1.0 `src.auth`/AuthService#",
                                "symbolRoles": 0,
                            }
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        codemap.import_scip(scip_json)
        assert codemap.refs("AuthService")["native_references"]
        auth = tmp_path / "src" / "auth.py"
        auth.write_text(
            auth.read_text(encoding="utf-8")
            + "\ndef changed_after_scip():\n    return True\n",
            encoding="utf-8",
        )
        codemap.sync(["src/auth.py"])
        refs = codemap.refs("AuthService")
        status = codemap.status()
    assert refs["native_references"] == []
    scip_status = [row for row in status["native_evidence"] if row["kind"] == "scip"]
    assert scip_status and scip_status[0]["fresh"] is False
    assert "generation changed" in str(scip_status[0]["reason"])


def test_typescript_native_edges_are_ignored_after_source_generation_changes(
    tmp_path: Path,
):
    from hashmarks.codemap.typescript_resolver import TypeScriptResolverProvider

    (tmp_path / "src").mkdir()
    (tmp_path / "node_modules" / "typescript").mkdir(parents=True)
    (tmp_path / "tsconfig.json").write_text(
        json.dumps(
            {"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["src/*"]}}}
        ),
        encoding="utf-8",
    )
    (tmp_path / "src" / "user.ts").write_text(
        "export const user = 1\n", encoding="utf-8"
    )
    (tmp_path / "src" / "auth.ts").write_text(
        "import { user } from '@app/user'\nexport const auth = user\n", encoding="utf-8"
    )
    fake_node = tmp_path / "fake-node"
    fake_node.write_text(
        "#!/usr/bin/env python3\nimport json\nprint(json.dumps({'version':'fresh-ts','config':'tsconfig.json','edges':[{'source':'src/auth.ts','target':'src/user.ts','specifier':'@app/user'}]}))\n",
        encoding="utf-8",
    )
    fake_node.chmod(0o755)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        codemap.typescript_resolver = TypeScriptResolverProvider(node=str(fake_node))
        codemap.enrich_projects(("typescript-resolver",))
        assert "src/auth.ts" in codemap.affected("src/user.ts")["affected_files"]
        user = tmp_path / "src" / "user.ts"
        user.write_text("export const user = 2\n", encoding="utf-8")
        codemap.sync(["src/user.ts"])
        affected = codemap.affected("src/user.ts")
        deps = codemap.deps("src/auth.ts")
    assert "src/auth.ts" not in affected["affected_files"]
    assert deps["native_file_edges"] == []


def test_project_graph_is_ignored_when_manifest_bytes_change(tmp_path: Path):
    (tmp_path / "packages" / "a" / "src").mkdir(parents=True)
    (tmp_path / "packages" / "b" / "src").mkdir(parents=True)
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "root", "workspaces": ["packages/*"]}), encoding="utf-8"
    )
    a_manifest = tmp_path / "packages" / "a" / "package.json"
    a_manifest.write_text(
        json.dumps({"name": "@hm/a", "dependencies": {"@hm/b": "workspace:*"}}),
        encoding="utf-8",
    )
    (tmp_path / "packages" / "b" / "package.json").write_text(
        json.dumps({"name": "@hm/b"}), encoding="utf-8"
    )
    (tmp_path / "packages" / "a" / "src" / "a.ts").write_text(
        "export const a = 1\n", encoding="utf-8"
    )
    (tmp_path / "packages" / "b" / "src" / "b.ts").write_text(
        "export const b = 2\n", encoding="utf-8"
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        codemap.enrich_projects(("npm-package-graph",))
        assert (
            "npm:@hm/a" in codemap.affected("packages/b/src/b.ts")["affected_projects"]
        )
        a_manifest.write_text(json.dumps({"name": "@hm/a"}), encoding="utf-8")
        affected = codemap.affected("packages/b/src/b.ts")
        projects = codemap.projects()
    assert affected["root_projects"] == []
    assert affected["affected_projects"] == []
    assert projects["projects"] == []


def test_nx_native_project_graph_enrichment_and_generation_freshness(tmp_path: Path):
    (tmp_path / "apps" / "web" / "src").mkdir(parents=True)
    (tmp_path / "libs" / "core" / "src").mkdir(parents=True)
    (tmp_path / "nx.json").write_text(
        '{"extends":"nx/presets/npm.json"}', encoding="utf-8"
    )
    (tmp_path / "package.json").write_text(
        '{"name":"demo","private":true}', encoding="utf-8"
    )
    (tmp_path / "apps" / "web" / "project.json").write_text(
        '{"name":"web"}', encoding="utf-8"
    )
    (tmp_path / "libs" / "core" / "project.json").write_text(
        '{"name":"core"}', encoding="utf-8"
    )
    (tmp_path / "apps" / "web" / "src" / "main.ts").write_text(
        "export const web = 1\n", encoding="utf-8"
    )
    (tmp_path / "libs" / "core" / "src" / "index.ts").write_text(
        "export const core = 1\n", encoding="utf-8"
    )
    nx = tmp_path / "node_modules" / ".bin" / "nx"
    nx.parent.mkdir(parents=True)
    nx.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "print(json.dumps({'graph':{'nodes':{"
        "'web':{'name':'web','type':'app','data':{'root':'apps/web','targets':{'test':{}}}},"
        "'core':{'name':'core','type':'lib','data':{'root':'libs/core','targets':{}}}},"
        "'dependencies':{'web':[{'source':'web','target':'core','type':'static'}],'core':[]}}}))\n",
        encoding="utf-8",
    )
    nx.chmod(0o755)

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        enriched = codemap.enrich_projects(("nx-project-graph",))
        affected = codemap.affected("libs/core/src/index.ts")
        assert any(row["project_id"] == "nx:web" for row in enriched["projects"])
        assert any(
            row["source"] == "nx:web" and row["target"] == "nx:core"
            for row in enriched["edges"]
        )
        assert affected["root_projects"] == ["nx:core"]
        assert "nx:web" in affected["affected_projects"]

        # Nx graph edges can be inferred from source imports, so any CodeMap
        # generation change invalidates the retained native graph until enrich.
        (tmp_path / "libs" / "core" / "src" / "index.ts").write_text(
            "export const core = 2\n", encoding="utf-8"
        )
        codemap.sync()
        projects = codemap.projects()
        assert projects["projects"] == []
        assert projects["edges"] == []


def test_pants_native_target_graph_enrichment_and_generation_freshness(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "pants.toml").write_text("[GLOBAL]\n", encoding="utf-8")
    (tmp_path / "src" / "lib.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_lib.py").write_text(
        "from src.lib import VALUE\n", encoding="utf-8"
    )
    pants = tmp_path / "pants"
    pants.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "print(json.dumps(["
        "{'address':'src:lib','target_type':'python_sources','dependencies':[],'sources':['src/lib.py'],'goals':['lint']},"
        "{'address':'tests:test_lib.py','target_type':'python_test','dependencies':['src:lib'],'sources':['tests/test_lib.py'],'goals':['test']}"
        "]))\n",
        encoding="utf-8",
    )
    pants.chmod(0o755)

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        enriched = codemap.enrich_projects(("pants-target-graph",))
        affected = codemap.affected("src/lib.py")
        assert any(row["project_id"] == "pants:src:lib" for row in enriched["projects"])
        assert any(
            row["source"] == "pants:tests:test_lib.py"
            and row["target"] == "pants:src:lib"
            for row in enriched["edges"]
        )
        assert "pants:tests:test_lib.py" in affected["affected_projects"]

        (tmp_path / "src" / "lib.py").write_text("VALUE = 2\n", encoding="utf-8")
        codemap.sync()
        assert codemap.projects()["projects"] == []


def test_maven_project_graph_enrichment_and_reverse_impact(tmp_path: Path):
    (tmp_path / "core" / "src" / "main" / "java").mkdir(parents=True)
    (tmp_path / "app" / "src" / "main" / "java").mkdir(parents=True)
    (tmp_path / "pom.xml").write_text(
        "<project><groupId>com.example</groupId><artifactId>root</artifactId><version>1</version>"
        "<modules><module>core</module><module>app</module></modules></project>",
        encoding="utf-8",
    )
    (tmp_path / "core" / "pom.xml").write_text(
        "<project><groupId>com.example</groupId><artifactId>core</artifactId><version>1</version></project>",
        encoding="utf-8",
    )
    (tmp_path / "app" / "pom.xml").write_text(
        "<project><groupId>com.example</groupId><artifactId>app</artifactId><version>1</version>"
        "<dependencies><dependency><groupId>com.example</groupId><artifactId>core</artifactId><version>1</version></dependency></dependencies></project>",
        encoding="utf-8",
    )
    (tmp_path / "core" / "src" / "main" / "java" / "Core.java").write_text(
        "class Core {}\n", encoding="utf-8"
    )
    (tmp_path / "app" / "src" / "main" / "java" / "App.java").write_text(
        "class App {}\n", encoding="utf-8"
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        enriched = codemap.enrich_projects(("maven-pom-graph",))
        affected = codemap.affected("core/src/main/java/Core.java")
    assert any(
        row["project_id"] == "maven:com.example:core" for row in enriched["projects"]
    )
    assert any(
        row["source"] == "maven:com.example:app"
        and row["target"] == "maven:com.example:core"
        for row in enriched["edges"]
    )
    assert "maven:com.example:app" in affected["affected_projects"]


def test_gradle_native_project_graph_enrichment_and_reverse_impact(tmp_path: Path):
    (tmp_path / "core" / "src" / "main" / "java").mkdir(parents=True)
    (tmp_path / "app" / "src" / "main" / "java").mkdir(parents=True)
    (tmp_path / "settings.gradle").write_text(
        "include(':core', ':app')\n", encoding="utf-8"
    )
    (tmp_path / "core" / "build.gradle").write_text(
        "plugins { id 'java' }\n", encoding="utf-8"
    )
    (tmp_path / "app" / "build.gradle").write_text(
        "plugins { id 'java' }\n", encoding="utf-8"
    )
    (tmp_path / "core" / "src" / "main" / "java" / "Core.java").write_text(
        "class Core {}\n", encoding="utf-8"
    )
    (tmp_path / "app" / "src" / "main" / "java" / "App.java").write_text(
        "class App {}\n", encoding="utf-8"
    )
    gradle = tmp_path / "gradlew"
    payload = [
        {
            "path": ":core",
            "name": "core",
            "projectDir": str(tmp_path / "core"),
            "dependencies": [],
            "tasks": ["build", "test"],
        },
        {
            "path": ":app",
            "name": "app",
            "projectDir": str(tmp_path / "app"),
            "dependencies": [":core"],
            "tasks": ["build", "test"],
        },
    ]
    gradle.write_text(
        "#!/usr/bin/env python3\nimport json\nprint('__HASHMARKS_GRADLE_JSON__' + json.dumps("
        + repr(payload)
        + "))\n",
        encoding="utf-8",
    )
    gradle.chmod(0o755)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        enriched = codemap.enrich_projects(("gradle-project-graph",))
        affected = codemap.affected("core/src/main/java/Core.java")
    assert any(row["project_id"] == "gradle::core" for row in enriched["projects"])
    assert any(
        row["source"] == "gradle::app" and row["target"] == "gradle::core"
        for row in enriched["edges"]
    )
    assert "gradle::app" in affected["affected_projects"]


def test_cli_accepts_every_codemap_enrichment_provider(tmp_path: Path, capsys):
    from hashmarks.cli import main

    providers = (
        "nx-project-graph",
        "pants-target-graph",
        "npm-package-graph",
        "maven-pom-graph",
        "gradle-project-graph",
        "go-list",
        "cargo-metadata",
        "declared-project-links",
        "typescript-resolver",
        "pyright-typeserver",
        "vitest-vite",
    )
    for provider in providers:
        assert (
            main(
                [
                    "--workspace",
                    str(tmp_path),
                    "map",
                    "enrich",
                    "--provider",
                    provider,
                ]
            )
            == 0
        )
        capsys.readouterr()


def test_declared_cross_ecosystem_links_compose_native_projects_and_shared_inputs(
    tmp_path: Path,
):
    (tmp_path / "backend" / "src").mkdir(parents=True)
    (tmp_path / "frontend" / "src").mkdir(parents=True)
    (tmp_path / "backend" / "pom.xml").write_text(
        "<project><groupId>com.example</groupId><artifactId>api</artifactId><version>1</version></project>",
        encoding="utf-8",
    )
    (tmp_path / "frontend" / "package.json").write_text(
        json.dumps({"name": "@demo/web"}), encoding="utf-8"
    )
    (tmp_path / "backend" / "src" / "Api.java").write_text(
        "class Api {}\n", encoding="utf-8"
    )
    (tmp_path / "frontend" / "src" / "api.ts").write_text(
        "export const api = 1\n", encoding="utf-8"
    )
    (tmp_path / "openapi.yaml").write_text("openapi: 3.1.0\n", encoding="utf-8")
    (tmp_path / ".hashmarks-project-links.toml").write_text(
        "[[link]]\n"
        "source='npm:@demo/web'\n"
        "target='maven:com.example:api'\n"
        "kind='api-client'\n\n"
        "[[shared_input]]\n"
        "path='openapi.yaml'\n"
        "projects=['npm:@demo/web','maven:com.example:api']\n"
        "kind='contract'\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        codemap.enrich_projects(
            ("npm-package-graph", "maven-pom-graph", "declared-project-links")
        )
        backend = codemap.affected("backend/src/Api.java")
        shared = codemap.affected("openapi.yaml")
        assert "npm:@demo/web" in backend["affected_projects"]
        assert "maven:com.example:api" in shared["affected_projects"]
        assert "npm:@demo/web" in shared["affected_projects"]

        # The composition evidence is manifest/input-bound, not immortal.
        (tmp_path / "openapi.yaml").write_text("openapi: 3.1.1\n", encoding="utf-8")
        shared_after = codemap.affected("openapi.yaml")
        assert shared_after["affected_projects"] == []


def test_declared_project_links_reject_invalid_shared_input_escape(tmp_path: Path):
    (tmp_path / ".hashmarks-project-links.toml").write_text(
        "[[shared_input]]\npath='../secret'\nprojects=['npm:web']\n", encoding="utf-8"
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        enriched = codemap.enrich_projects(("declared-project-links",))
    assert enriched["projects"] == []
    assert any("invalid path" in warning for warning in enriched["warnings"])


def test_vitest_vite_native_graph_enrichment_and_generation_freshness(
    tmp_path: Path, monkeypatch
):
    import hashmarks.codemap.engine as codemap_engine
    from hashmarks.codemap import CodeMap
    from hashmarks.native_vitest import VitestViteEdge, VitestViteGraph

    (tmp_path / "node_modules" / ".bin").mkdir(parents=True)
    (tmp_path / "node_modules" / ".bin" / "vitest").write_text("", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    (tmp_path / "src" / "auth.ts").write_text(
        "export const auth = 1\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "auth.test.ts").write_text(
        "test('auth',()=>{})\n", encoding="utf-8"
    )

    monkeypatch.setattr(
        codemap_engine,
        "local_vitest",
        lambda _root: tmp_path / "node_modules/.bin/vitest",
    )
    monkeypatch.setattr(
        codemap_engine,
        "collect_vitest_vite_graph",
        lambda _root: VitestViteGraph(
            producer="vitest-vite",
            selected=(),
            edges=(VitestViteEdge("tests/auth.test.ts", "src/auth.ts"),),
            command=("node", "helper.mjs"),
        ),
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        enriched = codemap.enrich_projects(("vitest-vite",))
        assert any(row["producer"] == "vitest-vite" for row in enriched["providers"])
        affected = codemap.affected("src/auth.ts")
        assert "tests/auth.test.ts" in affected["affected_files"]
        (tmp_path / "src" / "auth.ts").write_text(
            "export const auth = 2\n", encoding="utf-8"
        )
        codemap.sync(["src/auth.ts"])
        stale = codemap.affected("src/auth.ts")
        assert "tests/auth.test.ts" not in stale["affected_files"]


def test_pyright_type_server_resolves_absolute_and_relative_imports(tmp_path: Path):
    from hashmarks.codemap.pyright_type_server import PyrightTypeServerProvider

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "util.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "pkg" / "auth.py").write_text(
        "import pkg.util\nfrom . import util\n",
        encoding="utf-8",
    )
    fake_executable = tmp_path / "pyright-typeserver"
    fake_executable.write_text("", encoding="utf-8")

    class FakeClient:
        protocol_version = "0.4.1"

        def __init__(self):
            self.calls = []

        def initialize(self):
            return None

        def snapshot(self):
            return 7

        def resolve_import(self, source_uri, leading_dots, name_parts, snapshot):
            self.calls.append((source_uri, leading_dots, name_parts, snapshot))
            if (leading_dots, name_parts) in {
                (0, ("pkg", "util")),
                (1, ("util",)),
            }:
                return (tmp_path / "pkg" / "util.py").as_uri()
            return None

        def close(self):
            return None

    client = FakeClient()
    provider = PyrightTypeServerProvider(
        executable=fake_executable,
        client_factory=lambda _exe, _workspace, _timeout: client,
    )
    result = provider.collect(tmp_path, ("pkg/auth.py",))

    assert result.protocol_version == "0.4.1"
    assert {(edge.source, edge.target, edge.specifier) for edge in result.edges} == {
        ("pkg/auth.py", "pkg/util.py", "pkg.util"),
        ("pkg/auth.py", "pkg/util.py", ".util"),
    }
    assert {(leading, parts) for _, leading, parts, _ in client.calls} == {
        (0, ("pkg", "util")),
        (1, ("util",)),
    }


def test_pyright_type_server_ignores_resolutions_outside_workspace(tmp_path: Path):
    from hashmarks.codemap.pyright_type_server import PyrightTypeServerProvider

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("import external\n", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text("VALUE = 1\n", encoding="utf-8")
    fake_executable = tmp_path / "pyright-typeserver"
    fake_executable.write_text("", encoding="utf-8")

    class FakeClient:
        protocol_version = "0.4.1"

        def initialize(self):
            return None

        def snapshot(self):
            return 1

        def resolve_import(self, source_uri, leading_dots, name_parts, snapshot):
            return outside.as_uri()

        def close(self):
            return None

    provider = PyrightTypeServerProvider(
        executable=fake_executable,
        client_factory=lambda _exe, _workspace, _timeout: FakeClient(),
    )
    result = provider.collect(tmp_path, ("src/app.py",))
    assert result.edges == ()


def test_pyright_type_server_retries_once_after_stale_snapshot(tmp_path: Path):
    from hashmarks.codemap.pyright_type_server import (
        PyrightTypeServerProvider,
        _JsonRpcError,
    )

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "dep.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "src" / "app.py").write_text("import src.dep\n", encoding="utf-8")
    fake_executable = tmp_path / "pyright-typeserver"
    fake_executable.write_text("", encoding="utf-8")

    class FakeClient:
        protocol_version = "0.4.1"

        def __init__(self):
            self.snapshots = iter((10, 11))
            self.resolve_calls = 0

        def initialize(self):
            return None

        def snapshot(self):
            return next(self.snapshots)

        def resolve_import(self, source_uri, leading_dots, name_parts, snapshot):
            self.resolve_calls += 1
            if self.resolve_calls == 1:
                raise _JsonRpcError(-32802, "stale snapshot")
            assert snapshot == 11
            return (tmp_path / "src" / "dep.py").as_uri()

        def close(self):
            return None

    client = FakeClient()
    provider = PyrightTypeServerProvider(
        executable=fake_executable,
        client_factory=lambda _exe, _workspace, _timeout: client,
    )
    result = provider.collect(tmp_path, ("src/app.py",))
    assert [(edge.source, edge.target) for edge in result.edges] == [
        ("src/app.py", "src/dep.py")
    ]
    assert client.resolve_calls == 2


def test_pyright_type_server_rejects_unsupported_tsp_minor(tmp_path: Path):
    from hashmarks.codemap.pyright_type_server import _PyrightTypeServerClient

    class FakeRpc:
        def request(self, method, params=None):
            if method == "initialize":
                return {"capabilities": {}}
            if method == "typeServer/getSupportedProtocolVersion":
                return "0.5.0"
            raise AssertionError(method)

        def notify(self, method, params=None):
            assert method == "initialized"

    client = _PyrightTypeServerClient.__new__(_PyrightTypeServerClient)
    client.workspace = tmp_path
    client._rpc = FakeRpc()
    client.protocol_version = ""
    with pytest.raises(RuntimeError, match="unsupported Type Server Protocol 0.5.0"):
        client.initialize()


def test_pyright_native_edges_are_generation_bound_and_become_stale(tmp_path: Path):
    from hashmarks.codemap import CodeMap
    from hashmarks.codemap.pyright_type_server import PyrightTypeServerProvider

    (tmp_path / "src").mkdir()
    dep = tmp_path / "src" / "dep.py"
    app = tmp_path / "src" / "app.py"
    dep.write_text("VALUE = 1\n", encoding="utf-8")
    app.write_text("import src.dep\n", encoding="utf-8")
    fake_executable = tmp_path / "pyright-typeserver"
    fake_executable.write_text("", encoding="utf-8")

    class FakeClient:
        protocol_version = "0.4.1"

        def initialize(self):
            return None

        def snapshot(self):
            return 1

        def resolve_import(self, source_uri, leading_dots, name_parts, snapshot):
            return dep.as_uri()

        def close(self):
            return None

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.pyright_type_server = PyrightTypeServerProvider(
            executable=fake_executable,
            client_factory=lambda _exe, _workspace, _timeout: FakeClient(),
        )
        codemap.sync()
        enriched = codemap.enrich_projects(("pyright-typeserver",))
        assert enriched["providers"][0]["protocol_version"] == "0.4.1"
        affected = codemap.affected("src/dep.py")
        assert "src/app.py" in affected["affected_files"]

        app.write_text("import src.dep\nCHANGED = True\n", encoding="utf-8")
        codemap.sync(("src/app.py",))
        deps_after = codemap.deps("src/app.py")
        assert deps_after["native_file_edges"] == []
        status = codemap.status()
        pyright_status = [
            row
            for row in status["native_evidence"]
            if row["kind"] == "native-file"
            and str(row["producer"]).startswith("pyright-typeserver")
        ]
        assert pyright_status and pyright_status[0]["fresh"] is False
        assert "generation changed" in str(pyright_status[0]["reason"])


def test_pyright_jsonrpc_client_answers_server_requests_without_stealing_response():
    import queue

    from hashmarks.codemap.pyright_type_server import _JsonRpcProcess

    rpc = _JsonRpcProcess.__new__(_JsonRpcProcess)
    rpc.timeout = 0.1
    rpc._next_id = 1
    rpc._responses = queue.Queue()
    rpc._stderr_lines = []
    sent = []
    rpc._send = lambda message: sent.append(message)

    # A server request intentionally reuses id=1 before our response id=1.
    # Method presence must win over response-id matching.
    rpc._responses.put(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "workspace/configuration",
            "params": {
                "items": [{"section": "python"}, {"section": "python.analysis"}]
            },
        }
    )
    rpc._responses.put({"jsonrpc": "2.0", "id": 1, "result": "0.4.1"})

    assert rpc.request("typeServer/getSupportedProtocolVersion") == "0.4.1"
    assert sent[0]["method"] == "typeServer/getSupportedProtocolVersion"
    assert sent[1] == {"jsonrpc": "2.0", "id": 1, "result": [None, None]}


def test_codemap_disambiguates_repeated_lexical_qualnames_in_one_file(tmp_path: Path):
    """Repeated local helper names are legal source, not a map-sync failure."""
    (tmp_path / "mod.py").write_text(
        """
def outer(flag):
    if flag:
        def value():
            return 1
        return value()
    if not flag:
        def value():
            return 2
        return value()
    def value():
        return 3
    return value()
""".lstrip(),
        encoding="utf-8",
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        result = codemap.sync()
        assert result.parse_errors == 0
        rows = [
            row
            for row in codemap.outline("mod.py")["symbols"]
            if row["name"] == "value"
        ]
        assert len(rows) == 3
        assert len({row["qualname"] for row in rows}) == 3
        assert rows[0]["qualname"] == "outer.value"
        assert all(row["qualname"].startswith("outer.value") for row in rows)


def test_codemap_indexes_small_control_files_but_skips_noisy_lockfiles(tmp_path: Path):
    (tmp_path / "Makefile").write_text(
        "DEPENDENCY_RESOLUTION_RUNNER = python3 tools/bootstrap.py\ninit:\n\t$(DEPENDENCY_RESOLUTION_RUNNER)\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='demo'\n", encoding="utf-8"
    )
    (tmp_path / "package-lock.json").write_text(
        '{"lockfileVersion": 3}', encoding="utf-8"
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        result = codemap.sync()
        assert result.discovered == 2
        assert codemap.outline("Makefile")["language"] == "text"
        assert codemap.outline("pyproject.toml")["language"] == "text"
        with pytest.raises(FileNotFoundError):
            codemap.outline("package-lock.json")
        hits = codemap.find("DEPENDENCY_RESOLUTION_RUNNER bootstrap")
        assert any(hit.path == "Makefile" for hit in hits)


def test_find_preserves_path_diversity_when_one_file_has_many_matching_symbols(
    tmp_path: Path,
) -> None:
    (tmp_path / "primary.py").write_text(
        "\n".join(
            f"def protocol_snapshot_resolve_{i}():\n    return {i}" for i in range(20)
        ),
        encoding="utf-8",
    )
    (tmp_path / "companion.py").write_text(
        "def protocol_snapshot_resolve_bridge():\n    return 'bridge'\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as code_map:
        code_map.sync()
        hits = code_map.find("protocol snapshot resolve", limit=10)
    assert any(hit.path == "primary.py" for hit in hits)
    assert any(hit.path == "companion.py" for hit in hits)


def test_find_promotes_symbol_less_control_file_with_broad_lexical_coverage(
    tmp_path: Path,
) -> None:
    (tmp_path / "Makefile").write_text(
        "DEPENDENCY_RESOLUTION_RUNNER := python bootstrap.py\ninit:\n\t$(DEPENDENCY_RESOLUTION_RUNNER) init\n",
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    for index in range(20):
        (src / f"module_{index}.py").write_text(
            f"def dependency_resolution_runner_bootstrap_{index}():\n    return {index}\n",
            encoding="utf-8",
        )
    with CodeMap(tmp_path) as code_map:
        code_map.sync()
        hits = code_map.find(
            "DEPENDENCY_RESOLUTION_RUNNER make init bootstrap", limit=10
        )
    assert any(hit.path == "Makefile" for hit in hits)


def test_context_progressive_disclosure_levels_share_one_evidence_base(tmp_path: Path):
    _write_repo(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        orient = codemap.context(
            "AuthService login", token_budget=500, disclosure="orient"
        )
        outline = codemap.context(
            "AuthService login", token_budget=500, disclosure="outline"
        )
        evidence = codemap.context(
            "AuthService login", token_budget=500, disclosure="evidence"
        )
        source = codemap.context(
            "AuthService login", token_budget=500, disclosure="source"
        )

    assert orient.disclosure.value == "orient"
    assert orient.as_dict()["schema"] == "hashmarks.context-pack.v2"
    assert orient.as_dict()["next_disclosure"] == "outline"
    assert orient.items and {item.representation for item in orient.items} == {
        "candidate"
    }

    assert outline.disclosure.value == "outline"
    assert outline.as_dict()["next_disclosure"] == "evidence"
    assert outline.items
    assert all(
        item.representation in {"signature", "outline"} for item in outline.items
    )

    assert evidence.disclosure.value == "evidence"
    assert evidence.as_dict()["next_disclosure"] == "source"
    assert evidence.items
    assert all(
        item.representation in {"signature", "outline"} for item in evidence.items
    )

    assert source.disclosure.value == "source"
    assert source.as_dict()["next_disclosure"] is None
    assert any(item.representation == "source-range" for item in source.items)

    # Escalation is a projection of the same retrieval result/generation rather
    # than a parallel index or another freshness authority.
    assert {pack.generation for pack in (orient, outline, evidence, source)} == {
        source.generation
    }
    assert {pack.stale for pack in (orient, outline, evidence, source)} == {
        source.stale
    }
    orient_paths = {item.path for item in orient.items}
    assert {item.path for item in outline.items}.issubset(orient_paths)


def test_context_lower_disclosure_levels_never_read_source_bodies(tmp_path: Path):
    _write_repo(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        for level in ("orient", "outline", "evidence"):
            pack = codemap.context(
                "test login AuthService", token_budget=500, disclosure=level
            )
            assert all(item.representation != "source-range" for item in pack.items)
            assert all(
                "AuthService().login('a')" not in item.content for item in pack.items
            )


def test_context_rejects_unknown_disclosure_level(tmp_path: Path):
    _write_repo(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="invalid context disclosure"):
            codemap.context("AuthService login", disclosure="everything")


def test_candidate_rerank_stage_bounds_large_working_set_with_path_diversity(
    tmp_path: Path,
):
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        rows = []
        for index in range(600):
            path = f"src/group_{index % 100}/module.py"
            name = "TargetService" if index == 599 else f"helper_{index}"
            rows.append(
                {
                    "row_type": "symbol",
                    "path": path,
                    "name": name,
                    "qualname": name,
                    "signature": f"def {name}(): ...",
                    "evidence_visibility": "source",
                    "_relation_boost": 0.0,
                }
            )
        bounded = codemap._bounded_rerank_rows(
            "TargetService", tuple(rows), limit=20, tokens=("target", "service")
        )

    assert len(bounded) == 320  # max(256, limit * 16)
    assert any(row["name"] == "TargetService" for row in bounded)
    assert len({row["path"] for row in bounded}) >= 64


def test_candidate_rerank_stage_does_not_truncate_normal_queries(tmp_path: Path):
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        rows = tuple({"path": f"src/{i}.py", "name": f"n{i}"} for i in range(30))
        bounded = codemap._bounded_rerank_rows("n1", rows, limit=20, tokens=("n1",))
    assert bounded == rows


def test_context_cas_reuses_structural_payload_without_replaying_freshness(
    tmp_path: Path,
):
    _write_repo(tmp_path)
    state = tmp_path / ".state"
    with CodeMap(
        tmp_path, state_dir=state, artifact_db=tmp_path / "artifacts.sqlite3"
    ) as codemap:
        codemap.sync()
        first = codemap.context(
            "AuthService login", token_budget=500, disclosure="outline"
        )
        second = codemap.context(
            "AuthService login", token_budget=500, disclosure="outline"
        )

    assert not first.cache_hit
    assert first.context_action_hash
    assert first.context_result_digest
    assert second.cache_hit
    assert second.context_action_hash == first.context_action_hash
    assert second.context_result_digest == first.context_result_digest
    assert second.items == first.items
    assert second.generation == first.generation
    # Warnings are rebuilt from current freshness rather than persisted in CAS.
    assert second.warnings


def test_context_cas_source_payload_requires_positive_freshness(tmp_path: Path):
    _write_repo(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        first = codemap.context(
            "AuthService login", token_budget=500, disclosure="source"
        )
        second = codemap.context(
            "AuthService login", token_budget=500, disclosure="source"
        )

    assert first.stale is None
    assert second.stale is None
    assert not first.cache_hit and not second.cache_hit
    assert first.context_action_hash is None
    assert second.context_action_hash is None
    assert any(item.representation == "source-range" for item in second.items)


def test_context_cas_action_binds_budget_disclosure_and_policy(tmp_path: Path):
    _write_repo(tmp_path)
    state = tmp_path / ".state"
    with CodeMap(
        tmp_path, state_dir=state, artifact_db=tmp_path / "artifacts.sqlite3"
    ) as codemap:
        codemap.sync()
        outline = codemap.context(
            "AuthService login", token_budget=500, disclosure="outline"
        )
        evidence = codemap.context(
            "AuthService login", token_budget=500, disclosure="evidence"
        )
        smaller = codemap.context(
            "AuthService login", token_budget=400, disclosure="outline"
        )

    assert outline.context_action_hash
    assert (
        len(
            {
                outline.context_action_hash,
                evidence.context_action_hash,
                smaller.context_action_hash,
            }
        )
        == 3
    )

    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "src/**"\nvisibility = "outline"\n', encoding="utf-8"
    )
    with CodeMap(
        tmp_path, state_dir=state, artifact_db=tmp_path / "artifacts.sqlite3"
    ) as changed_policy:
        changed_policy.sync()
        policy_pack = changed_policy.context(
            "AuthService login", token_budget=500, disclosure="outline"
        )
    assert policy_pack.context_action_hash != outline.context_action_hash


def test_find_singleflight_shares_equivalent_concurrent_work(tmp_path: Path):
    import threading
    import time

    _write_repo(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        original = codemap._find_impl
        calls = 0
        calls_lock = threading.Lock()
        barrier = threading.Barrier(5)
        results = []
        errors = []

        def slow_find(query: str, *, limit: int = 20):
            nonlocal calls
            with calls_lock:
                calls += 1
            time.sleep(0.08)
            return original(query, limit=limit)

        codemap._find_impl = slow_find  # type: ignore[method-assign]

        def worker():
            try:
                barrier.wait()
                results.append(codemap.find("AuthService login", limit=20))
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert not errors
    assert calls == 1
    assert len(results) == 5
    assert all(result == results[0] for result in results)


def test_context_singleflight_returns_only_shared_immutable_result(tmp_path: Path):
    import threading
    import time

    _write_repo(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        original = codemap._context_impl
        calls = 0
        calls_lock = threading.Lock()
        barrier = threading.Barrier(5)
        results = []
        errors = []

        def slow_context(
            query: str,
            *,
            token_budget: int = 4000,
            limit: int = 30,
            disclosure="source",
        ):
            nonlocal calls
            with calls_lock:
                calls += 1
            time.sleep(0.08)
            return original(
                query, token_budget=token_budget, limit=limit, disclosure=disclosure
            )

        codemap._context_impl = slow_context  # type: ignore[method-assign]

        def worker():
            try:
                barrier.wait()
                results.append(
                    codemap.context(
                        "AuthService login", token_budget=500, disclosure="outline"
                    )
                )
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert not errors
    assert calls == 1
    assert len(results) == 5
    assert sum(pack.shared_flight for pack in results) == 4
    leader = next(pack for pack in results if not pack.shared_flight)
    assert all(pack.items == leader.items for pack in results)
    assert all(
        pack.context_result_digest == leader.context_result_digest for pack in results
    )


def test_source_singleflight_requires_positive_freshness(tmp_path: Path):
    import threading
    import time

    _write_repo(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        original = codemap._context_impl
        calls = 0
        calls_lock = threading.Lock()
        barrier = threading.Barrier(3)
        results = []

        def slow_context(
            query: str,
            *,
            token_budget: int = 4000,
            limit: int = 30,
            disclosure="source",
        ):
            nonlocal calls
            with calls_lock:
                calls += 1
            time.sleep(0.05)
            return original(
                query, token_budget=token_budget, limit=limit, disclosure=disclosure
            )

        codemap._context_impl = slow_context  # type: ignore[method-assign]

        def worker():
            barrier.wait()
            results.append(
                codemap.context(
                    "AuthService login", token_budget=500, disclosure="source"
                )
            )

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert calls == 3
    assert all(pack.stale is None for pack in results)
    assert all(not pack.shared_flight for pack in results)


def test_annotation_relationship_protects_return_type_from_test_name_crowding(
    tmp_path: Path,
):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "context.py").write_text(
        "class ContextPack:\n    pass\n\n"
        "class CodeMap:\n"
        "    def context(self, token_budget: int = 4000) -> ContextPack:\n"
        "        return ContextPack()\n",
        encoding="utf-8",
    )
    for index in range(30):
        (tmp_path / "tests" / f"test_context_{index}.py").write_text(
            f"def test_codemap_context_token_budget_retrieval_confidence_{index}():\n    pass\n",
            encoding="utf-8",
        )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        edges = codemap.store.edges_from("src/context.py", "CodeMap.context")
        hits = codemap.find(
            "CodeMap context token budget retrieval confidence", limit=20
        )
    assert any(
        edge["kind"] == "return-type" and edge["target"] == "ContextPack"
        for edge in edges
    )
    symbols = {hit.qualname for hit in hits}
    assert "ContextPack" in symbols


def test_python_annotations_emit_bounded_type_relationships(tmp_path: Path):
    (tmp_path / "model.py").write_text(
        "class Base:\n    pass\n\n"
        "class Payload:\n    pass\n\n"
        "class Service(Base):\n"
        "    cached: Payload\n"
        "    def run(self, value: Payload) -> list[Payload]:\n"
        "        return [value]\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        edges = codemap.store.edges_from("model.py")
    triples = {(edge["source"], edge["kind"], edge["target"]) for edge in edges}
    assert ("Service", "inherits", "Base") in triples
    assert ("Service", "attribute-type", "Payload") in triples
    assert ("Service.run", "parameter-type", "Payload") in triples
    assert ("Service.run", "return-type", "Payload") in triples


def test_edge_relationship_indexes_cover_path_and_source_lookup(tmp_path: Path):
    (tmp_path / "service.py").write_text("class Payload:\n    pass\n", encoding="utf-8")
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        names = {
            row[1]
            for row in codemap.store._db.execute("PRAGMA index_list(edge)").fetchall()
        }
    assert "edge_path_line_idx" in names
    assert "edge_path_source_line_idx" in names


def test_fresh_lexical_schema_uses_token_primary_key_and_path_index(tmp_path: Path):
    store = WorkspaceMapStore(tmp_path / "codemap.sqlite3")
    try:
        sql = str(
            store._db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='lexical'"
            ).fetchone()[0]
        )
        shape = "".join(sql.lower().split())
        indexes = {
            row[1] for row in store._db.execute("PRAGMA index_list(lexical)").fetchall()
        }
    finally:
        store.close()

    assert "withoutrowid" in shape
    assert "primarykey(token,path,line)" in shape
    assert "lexical_path_idx" in indexes
    assert "lexical_token_idx" not in indexes
    assert "lexical_token_path_idx" not in indexes


def test_incompatible_lexical_schema_is_discarded_and_rebuilt(tmp_path: Path):
    db_path = tmp_path / "legacy-codemap.sqlite3"
    db = sqlite3.connect(db_path)
    db.executescript(
        """
        CREATE TABLE lexical (
          path TEXT NOT NULL,
          token TEXT NOT NULL,
          line INTEGER NOT NULL,
          PRIMARY KEY(path,token,line)
        );
        CREATE INDEX lexical_token_idx ON lexical(token);
        INSERT INTO lexical(path,token,line) VALUES ('src/a.py','workspace',3);
        """
    )
    db.commit()
    db.close()

    store = WorkspaceMapStore(db_path)
    try:
        rows = store._db.execute("SELECT path,token,line FROM lexical").fetchall()
        sql = str(
            store._db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='lexical'"
            ).fetchone()[0]
        )
        shape = "".join(sql.lower().split())
        indexes = {
            row[1] for row in store._db.execute("PRAGMA index_list(lexical)").fetchall()
        }
    finally:
        store.close()

    assert rows == []
    assert "withoutrowid" in shape
    assert "primarykey(token,path,line)" in shape
    assert "lexical_path_idx" in indexes
    assert "lexical_token_idx" not in indexes


def test_bulk_file_writes_commit_completed_chunks_and_rollback_only_current_chunk(
    tmp_path: Path,
):
    db_path = tmp_path / "codemap.sqlite3"
    store = WorkspaceMapStore(db_path)

    def artifact(name: str):
        return parse_source(
            f"def {name}():\n    return '{name}'\n",
            file_digest=f"digest-{name}",
            language="python",
        )

    with pytest.raises(RuntimeError, match="stop-current-chunk"):
        with store.bulk_file_writes(batch_size=2):
            store.set_file(
                "a.py",
                artifact("alpha"),
                module_name="a",
                visibility=EvidenceVisibility.SOURCE,
            )
            store.set_file(
                "b.py",
                artifact("beta"),
                module_name="b",
                visibility=EvidenceVisibility.SOURCE,
            )

            # The completed two-file chunk is already durable to another
            # connection before the context finishes.
            observer = sqlite3.connect(db_path)
            try:
                assert (
                    observer.execute("SELECT COUNT(*) FROM file_map").fetchone()[0] == 2
                )
            finally:
                observer.close()

            store.set_file(
                "c.py",
                artifact("gamma"),
                module_name="c",
                visibility=EvidenceVisibility.SOURCE,
            )
            raise RuntimeError("stop-current-chunk")

    observer = sqlite3.connect(db_path)
    try:
        paths = [
            row[0]
            for row in observer.execute(
                "SELECT path FROM file_map ORDER BY path"
            ).fetchall()
        ]
    finally:
        observer.close()
        store.close()

    assert paths == ["a.py", "b.py"]


def test_bulk_file_writes_commits_final_chunk_and_reports_durable_count(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "codemap.sqlite3"
    store = WorkspaceMapStore(db_path)
    commits: list[int] = []
    artifact = parse_source(
        "def alpha():\n    return 1\n",
        file_digest="digest-alpha",
        language="python",
    )
    try:
        with store.bulk_file_writes(batch_size=2, on_commit=commits.append):
            store.set_file(
                "a.py",
                artifact,
                module_name="a",
                visibility=EvidenceVisibility.SOURCE,
            )
        assert commits == [1]
        with sqlite3.connect(db_path) as observer:
            assert observer.execute("SELECT COUNT(*) FROM file_map").fetchone()[0] == 1
        with pytest.raises(RuntimeError, match="nested bulk file writes"):
            with store.bulk_file_writes():
                with store.bulk_file_writes():
                    pass
        with pytest.raises(ValueError, match="batch_size"):
            with store.bulk_file_writes(batch_size=0):
                pass
    finally:
        store.close()


def test_bulk_file_writes_releases_batch_state_after_commit_callback_failure(
    tmp_path: Path,
) -> None:
    store = WorkspaceMapStore(tmp_path / "codemap.sqlite3")

    def fail_after_commit(_count: int) -> None:
        raise RuntimeError("callback failed")

    artifact = parse_source(
        "def alpha():\n    return 1\n",
        file_digest="digest-alpha",
        language="python",
    )
    try:
        with pytest.raises(RuntimeError, match="callback failed"):
            with store.bulk_file_writes(batch_size=2, on_commit=fail_after_commit):
                store.set_file(
                    "a.py",
                    artifact,
                    module_name="a",
                    visibility=EvidenceVisibility.SOURCE,
                )
        with store.bulk_file_writes():
            pass
    finally:
        store.close()


def test_codemap_indexes_bounded_repository_docs_and_scripts_as_control_surfaces(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs" / "development"
    docs.mkdir(parents=True)
    (docs / "APP_CERTIFICATION.md").write_text(
        "Certification ownership boundary and release acceptance contract.\n",
        encoding="utf-8",
    )
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "verify.sh").write_text(
        "#!/bin/sh\necho certification verify\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        result = codemap.sync()
        assert result.parse_errors == 0
        assert (
            codemap.outline("docs/development/APP_CERTIFICATION.md")["language"]
            == "text"
        )
        assert codemap.outline("scripts/verify.sh")["language"] == "text"


def test_find_task_preserves_exact_identifier_symbol_anchor(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "adapter.py").write_text(
        "class ExactAnchorAdapter:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_adapter.py").write_text(
        "def test_exact_anchor_adapter_native_project_graph_test_tasks():\n    pass\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        hits = codemap.find_task(
            "ExactAnchorAdapter native project graph test tasks", limit=10
        )
    assert hits
    assert hits[0].path == "src/adapter.py"


def test_index_preflight_and_economics_report_measured_surfaces_without_execution_policy(
    tmp_path: Path,
):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "src/app.py").write_text("def run(value):\n    return value + 1\n")
    (tmp_path / "tests/test_app.py").write_text(
        "from src.app import run\ndef test_run(): assert run(1) == 2\n"
    )
    (tmp_path / "docs/readme.md").write_text("# App\nrun behavior\n")
    (tmp_path / "package-lock.json").write_text('{"lockfileVersion": 3}\n')
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        preflight = codemap.index_preflight()
        result = codemap.sync()
        status = codemap.status()
    assert preflight["indexable_files"] >= 3
    assert preflight["estimated_lexical_rows"] is None
    assert preflight["surfaces"]["source"]["files"] == 1
    assert preflight["surfaces"]["test"]["files"] == 1
    assert result.build_state == "COMPLETE"
    assert result.economics["deadline_policy"] is None
    assert result.economics["retry_policy"] is None
    assert result.economics["persistence_batch_files"] == 32
    assert result.economics["surfaces"]["source"]["lexical_occurrences"] > 0
    assert status["build"]["complete"] is True


def test_bulk_reverse_reference_queries_preserve_per_target_semantics(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text(
        "class Alpha:\n    pass\n\nclass Beta:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "use.py").write_text(
        "from owner import Alpha, Beta\n\ndef use(a: Alpha, b: Beta):\n    return a, b\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        expected_alpha = codemap.store.refs("Alpha", limit=32)
        expected_beta = codemap.store.refs("Beta", limit=32)
        actual = codemap.store.refs_many(["Alpha", "Beta"], limit_per_target=32)
        assert actual["Alpha"] == expected_alpha
        assert actual["Beta"] == expected_beta


def test_lexical_file_expansion_does_not_promote_unrelated_symbols(
    tmp_path: Path,
) -> None:
    dense = ["# calibrationneedle lives at file scope"]
    dense.extend(
        f"def unrelated_{index}():\n    return {index}" for index in range(300)
    )
    (tmp_path / "dense.py").write_text("\n\n".join(dense) + "\n", encoding="utf-8")
    (tmp_path / "owner.py").write_text(
        "def calibrationneedle_owner():\n    return True\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        hits = codemap.find("calibrationneedle", limit=20)
    # File-level lexical recall remains available for dense.py, but hundreds of
    # symbols with no symbol-local task evidence are not sent through reranking.
    assert any(hit.path == "dense.py" for hit in hits)
    assert not any(hit.path == "dense.py" and hit.kind != "file" for hit in hits)
    assert any(hit.path == "owner.py" for hit in hits)


def test_incremental_economics_uses_compact_exact_per_file_facts(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "src/app.py").write_text("def run(value):\n    return value + 1\n")
    (tmp_path / "tests/test_app.py").write_text(
        "from src.app import run\ndef test_run(): assert run(1) == 2\n"
    )
    (tmp_path / "docs/readme.md").write_text("# App\nrun behavior\n")
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        first = codemap.sync()
        expected_lexical = codemap.store.stats()["lexical_occurrences"]
        expected_by_path = codemap.store.lexical_counts_by_path()
        assert first.economics["lexical_occurrences"] == expected_lexical
        assert sum(
            row["lexical_occurrences"] for row in first.economics["surfaces"].values()
        ) == sum(expected_by_path.values())
        (tmp_path / "src/app.py").write_text(
            "def run(value):\n    return value + 200\n"
        )
        second = codemap.sync(paths=["src/app.py"])
        assert (
            second.economics["lexical_occurrences"]
            == codemap.store.stats()["lexical_occurrences"]
        )
        assert second.economics["files"] == 3
        assert (
            second.economics["surfaces"]["source"]["files_with_lexical_evidence"] == 1
        )
        assert second.economics["surfaces"]["test"]["files_with_lexical_evidence"] == 1
        assert second.economics["surfaces"]["docs"]["files_with_lexical_evidence"] == 1
