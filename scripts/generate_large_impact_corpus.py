from __future__ import annotations

import hashlib
import json
import shutil
import string
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

SCHEMA = "hashmarks.large-impact-corpus.v1"
KINDS = ("python", "typescript", "go", "polyglot")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _digest(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _word(index: int) -> str:
    value = index
    chars: list[str] = []
    for _ in range(4):
        chars.append(string.ascii_lowercase[value % 26])
        value //= 26
    return "".join(chars).capitalize()


def _noise_python(repo: Path, count: int) -> None:
    for index in range(count):
        _write(
            repo / f"noise/python/p{index // 50:04d}/m{index:06d}.py",
            f'def helper_{index}(value: str) -> str:\n    return value + "-{index % 17}"\n',
        )


def _noise_typescript(repo: Path, count: int) -> None:
    for index in range(count):
        _write(
            repo / f"noise/typescript/p{index // 50:04d}/m{index:06d}.ts",
            f'export function helper{index}(value: string) {{ return value + "-{index % 19}"; }}\n',
        )


def _noise_go(repo: Path, count: int) -> None:
    for index in range(count):
        package = f"n{index // 20:05d}"
        _write(
            repo / f"noise/go/{package}/m{index:06d}.go",
            f"package {package}\nfunc Helper{index}(value string) string {{ return value }}\n",
        )


def _python_task(repo: Path, index: int, prefix: str = "Py") -> dict[str, str]:
    token = f"QuartzMeadow{prefix}{_word(index)}"
    namespace = f"{prefix.lower()}_{_word(index).lower()}"
    base = f"app/{namespace}"
    _write(repo / "app/__init__.py", "")
    _write(repo / f"{base}/__init__.py", "")
    _write(
        repo / f"{base}/engine.py",
        f'def Resolve{token}(value: str) -> str:\n    return value + "-old"\n',
    )
    _write(
        repo / f"{base}/service.py",
        f"from .engine import Resolve{token}\n\ndef ServiceValue(value: str) -> str:\n    return Resolve{token}(value)\n",
    )
    _write(
        repo / f"{base}/route.py",
        f"from .service import ServiceValue\n\ndef Route{token}(value: str) -> str:\n    return ServiceValue(value)\n",
    )
    verify = f"tests/test_{token.lower()}.py"
    _write(
        repo / verify,
        f'from app.{namespace}.route import Route{token}\n\n# quartz meadow accepted response verification\ndef test_{token}():\n    assert Route{token}("x") == "x-new"\n',
    )
    return {
        "id": token,
        "query": f"Change {token} accepted response from old to new",
        "expected_edit_path": f"{base}/engine.py",
        "expected_verify_path": verify,
        "expected_dependency_path": f"{base}/service.py",
    }


def _typescript_task(repo: Path, index: int, prefix: str = "Ts") -> dict[str, str]:
    token = f"VelvetHarbor{prefix}{_word(index)}"
    namespace = f"{prefix.lower()}_{_word(index).lower()}"
    base = f"src/{namespace}"
    _write(
        repo / f"{base}/engine.ts",
        f'export function Resolve{token}(value: string) {{ return value + "-old"; }}\n',
    )
    _write(
        repo / f"{base}/service.ts",
        f'import {{ Resolve{token} }} from "./engine.js";\nexport function ServiceValue(value: string) {{ return Resolve{token}(value); }}\n',
    )
    _write(
        repo / f"{base}/route.ts",
        f'import {{ ServiceValue }} from "./service.js";\nexport function Route{token}(value: string) {{ return ServiceValue(value); }}\n',
    )
    verify = f"tests/{token.lower()}.test.ts"
    _write(
        repo / verify,
        f'import {{ Route{token} }} from "../{base}/route.js";\nconst actual = Route{token}("x"); void actual;\n// velvet harbor accepted response verification\n',
    )
    return {
        "id": token,
        "query": f"Change {token} accepted response from old to new",
        "expected_edit_path": f"{base}/engine.ts",
        "expected_verify_path": verify,
        "expected_dependency_path": f"{base}/service.ts",
    }


def _go_task(repo: Path, index: int, prefix: str = "Go") -> dict[str, str]:
    token = f"CobaltRidge{prefix}{_word(index)}"
    namespace = f"{prefix.lower()}{_word(index).lower()}"
    base = f"cases/{namespace}"
    _write(
        repo / f"{base}/engine/engine.go",
        f'package engine\nfunc Resolve{token}(value string) string {{ return value + "-old" }}\n',
    )
    _write(
        repo / f"{base}/service/service.go",
        f'package service\nimport "example.local/large/{base}/engine"\nfunc ServiceValue(value string) string {{ return engine.Resolve{token}(value) }}\n',
    )
    _write(
        repo / f"{base}/route/route.go",
        f'package route\nimport "example.local/large/{base}/service"\nfunc RouteValue(value string) string {{ return service.ServiceValue(value) }}\n',
    )
    verify = f"{base}/route/{token.lower()}_test.go"
    _write(
        repo / verify,
        f'package route\nimport "testing"\nfunc Test{token}(t *testing.T) {{}}\n// cobalt ridge accepted response verification\n',
    )
    return {
        "id": token,
        "query": f"Change {token} accepted response from old to new",
        "expected_edit_path": f"{base}/engine/engine.go",
        "expected_verify_path": verify,
        "expected_dependency_path": f"{base}/service/service.go",
    }


def _validate_destinations(repo: Path, *external_paths: Path) -> None:
    for external in external_paths:
        try:
            external.relative_to(repo)
        except ValueError:
            continue
        raise ValueError(
            "PUBLIC and SECRET corpus files must live outside the worker repository"
        )


def _write_project_configuration(repo: Path, kind: str) -> None:
    if kind in {"python", "polyglot"}:
        _write(
            repo / "pyproject.toml", '[tool.pytest.ini_options]\ntestpaths=["tests"]\n'
        )
    if kind in {"typescript", "polyglot"}:
        _write(repo / "package.json", '{"type":"module"}\n')
        _write(
            repo / "tsconfig.json",
            '{"compilerOptions":{"module":"NodeNext","moduleResolution":"NodeNext","target":"ES2022"},"include":["src/**/*.ts","tests/**/*.ts"]}\n',
        )
    if kind in {"go", "polyglot"}:
        _write(repo / "go.mod", "module example.local/large\n\ngo 1.23\n")


def _generate_rows(
    repo: Path, kind: str, noise_files: int, tasks: int
) -> list[dict[str, str]]:
    if kind == "python":
        _noise_python(repo, noise_files)
        return [_python_task(repo, index) for index in range(tasks)]
    if kind == "typescript":
        _noise_typescript(repo, noise_files)
        return [_typescript_task(repo, index) for index in range(tasks)]
    if kind == "go":
        _noise_go(repo, noise_files)
        return [_go_task(repo, index) for index in range(tasks)]
    each = noise_files // 3
    _noise_python(repo, each)
    _noise_typescript(repo, each)
    _noise_go(repo, noise_files - (2 * each))
    makers = (_python_task, _typescript_task, _go_task)
    return [makers[index % 3](repo, index, "Mix") for index in range(tasks)]


def generate(
    repo: Path,
    public_path: Path,
    secret_path: Path,
    *,
    kind: str,
    noise_files: int,
    tasks: int,
) -> dict[str, object]:
    if kind not in KINDS:
        raise ValueError(f"unsupported kind: {kind}")
    if noise_files < 0 or tasks < 1:
        raise ValueError("noise_files must be >= 0 and tasks must be >= 1")
    repo = repo.resolve()
    public_path = public_path.resolve()
    secret_path = secret_path.resolve()
    _validate_destinations(repo, public_path, secret_path)
    shutil.rmtree(repo, ignore_errors=True)
    repo.mkdir(parents=True)
    _write_project_configuration(repo, kind)
    rows = _generate_rows(repo, kind, noise_files, tasks)

    public = {
        "schema": SCHEMA,
        "tasks": [{"id": row["id"], "query": row["query"]} for row in rows],
    }
    secret = {
        "schema": SCHEMA,
        "tasks": [
            {key: value for key, value in row.items() if key != "query"} for row in rows
        ],
    }
    public_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(
        json.dumps(public, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    secret_path.write_text(
        json.dumps(secret, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "schema": "hashmarks.large-impact-corpus-manifest.v1",
        "kind": kind,
        "noise_files": noise_files,
        "tasks": tasks,
        "public_identity": _digest(public),
        "secret_identity": _digest(secret),
        "answer_key_inside_worker_repo": False,
    }
