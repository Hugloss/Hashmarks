from __future__ import annotations

import argparse
import json
import logging
import shutil
import time
from pathlib import Path

from hashmarks._command_output import log_command_output
from hashmarks.codemap import CodeMap

logger = logging.getLogger(__name__)

_TOKENS = (
    "amber",
    "bravo",
    "cobalt",
    "delta",
    "ember",
    "fjord",
    "glint",
    "harbor",
    "indigo",
    "juno",
)


def _write_repo(
    root: Path, index: int, *, decoys: int
) -> tuple[list[dict], list[dict]]:
    token = _TOKENS[index % len(_TOKENS)] + str(index)
    backend = f"maven:com.example:api-{token}"
    web = f"npm:@demo/web-{token}"
    mobile = f"npm:@demo/mobile-{token}"
    backend_root = root / "backend"
    web_root = root / "web"
    mobile_root = root / "mobile"
    (backend_root / "src").mkdir(parents=True)
    (web_root / "src").mkdir(parents=True)
    (mobile_root / "src").mkdir(parents=True)
    (backend_root / "pom.xml").write_text(
        f"<project><groupId>com.example</groupId><artifactId>api-{token}</artifactId><version>1</version></project>",
        encoding="utf-8",
    )
    (web_root / "package.json").write_text(
        json.dumps({"name": f"@demo/web-{token}"}), encoding="utf-8"
    )
    (mobile_root / "package.json").write_text(
        json.dumps({"name": f"@demo/mobile-{token}"}), encoding="utf-8"
    )
    source_path = "backend/src/Api.java"
    shared_path = f"contracts/{token}.yaml"
    (backend_root / "src/Api.java").write_text(
        f'class Api {{ String marker = "{token}"; }}\n', encoding="utf-8"
    )
    (web_root / "src/api.ts").write_text(
        f"export const marker = '{token}';\n", encoding="utf-8"
    )
    (mobile_root / "src/api.ts").write_text(
        f"export const marker = '{token}';\n", encoding="utf-8"
    )
    (root / "contracts").mkdir()
    (root / shared_path).write_text(
        f"openapi: 3.1.0\ninfo:\n  title: {token}\n", encoding="utf-8"
    )

    links = [
        f"[[link]]\nsource='{web}'\ntarget='{backend}'\nkind='api-client'\n",
        f"[[link]]\nsource='{mobile}'\ntarget='{web}'\nkind='mobile-shell'\n",
        f"[[shared_input]]\npath='{shared_path}'\nprojects=['{web}','{backend}']\nkind='contract'\n",
    ]
    for decoy in range(decoys):
        name = f"decoy-{index}-{decoy}"
        droot = root / "decoys" / name
        droot.mkdir(parents=True)
        (droot / "package.json").write_text(
            json.dumps({"name": name}), encoding="utf-8"
        )
        (droot / "value.ts").write_text(
            f"export const value = '{name}';\n", encoding="utf-8"
        )
    (root / ".hashmarks-project-links.toml").write_text(
        "".join(links), encoding="utf-8"
    )

    public = [
        {
            "id": f"cross-{index:03d}-source",
            "query": f"Update {token} backend API implementation",
            "changed": source_path,
            "kind": "source",
        },
        {
            "id": f"cross-{index:03d}-shared",
            "query": f"Update {token} shared API contract",
            "changed": shared_path,
            "kind": "shared-input",
        },
    ]
    secret = [
        {
            "id": public[0]["id"],
            "projects": [mobile, web],
            "provenance": {web: 1, mobile: 2},
        },
        {
            "id": public[1]["id"],
            "projects": [backend, mobile, web],
            "provenance": {backend: 1, web: 1, mobile: 2},
        },
    ]
    return public, secret


def generate(
    base: Path,
    public_path: Path,
    secret_path: Path,
    *,
    scenarios: int = 6,
    decoys: int = 24,
) -> None:
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    public_rows: list[dict] = []
    secret_rows: list[dict] = []
    for index in range(scenarios):
        repo = base / f"scenario-{index:03d}"
        repo.mkdir()
        pub, sec = _write_repo(repo, index, decoys=decoys)
        for row in pub:
            row["repo"] = repo.relative_to(base).as_posix()
        public_rows.extend(pub)
        secret_rows.extend(sec)
    public_path.write_text(
        json.dumps(
            {"schema": "hashmarks.cross-repo-public.v1", "tasks": public_rows},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    secret_path.write_text(
        json.dumps(
            {"schema": "hashmarks.cross-repo-secret.v1", "tasks": secret_rows},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _freeze_task(base: Path, task: dict) -> tuple[dict, float]:
    repo = base / task["repo"]
    changed = str(task["changed"])
    with CodeMap(repo, artifact_db=repo / "artifacts.sqlite3") as codemap:
        started = time.perf_counter()
        codemap.sync()
        codemap.enrich_projects(
            ("npm-package-graph", "maven-pom-graph", "declared-project-links")
        )
        sync_ms = (time.perf_counter() - started) * 1000.0
        path = repo / changed
        if task["kind"] == "shared-input":
            text = path.read_text(encoding="utf-8").replace(
                "openapi: 3.1.0", "openapi: 3.1.1"
            )
            path.write_text(text, encoding="utf-8")
        else:
            path.write_text(
                path.read_text(encoding="utf-8") + "// external edit\n",
                encoding="utf-8",
            )
        started = time.perf_counter()
        packet = codemap.task_change_impact(str(task["query"]), [changed])
        impact_ms = (time.perf_counter() - started) * 1000.0
    return {
        "id": task["id"],
        "kind": task["kind"],
        "packet": packet,
        "packet_bytes": len(
            json.dumps(packet, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ),
        "impact_ms": impact_ms,
    }, sync_ms


def _score_task(row: dict, expected: dict) -> dict:
    packet = row["packet"]
    projects = sorted(str(value) for value in packet.get("projects", []))
    project_fragment = (
        packet.get("project_impact")
        if isinstance(packet.get("project_impact"), dict)
        else {}
    )
    provenance_rows = {
        str(value.get("project")): value
        for value in project_fragment.get("affected", [])
        if isinstance(value, dict)
    }
    edges = project_fragment.get("edges", [])
    provenance_correct = bool(edges) and all(
        isinstance(edge, dict) and edge.get("producer") == "declared-project-links"
        for edge in edges
    )
    for project, depth in expected["provenance"].items():
        candidate = provenance_rows.get(project)
        if candidate is None or int(candidate.get("depth", -1)) != int(depth):
            provenance_correct = False
            break
    project_correct = projects == sorted(expected["projects"])
    refresh = packet.get("project_refresh")
    refresh_correct = row["kind"] != "shared-input" or (
        isinstance(refresh, dict)
        and refresh.get("producer") == "declared-project-links"
    )
    return {
        **{key: row[key] for key in ("id", "kind", "packet_bytes", "impact_ms")},
        "project_correct": project_correct,
        "provenance_correct": provenance_correct,
        "refresh_correct": refresh_correct,
        "fully_correct": project_correct and provenance_correct and refresh_correct,
    }


def _summary(scored: list[dict], sync_ms: float) -> dict:
    tasks = len(scored)
    return {
        "tasks": tasks,
        "fully_correct": sum(int(row["fully_correct"]) for row in scored),
        "project_correct": sum(int(row["project_correct"]) for row in scored),
        "provenance_correct": sum(int(row["provenance_correct"]) for row in scored),
        "shared_refresh_correct": sum(
            int(row["refresh_correct"])
            for row in scored
            if row["kind"] == "shared-input"
        ),
        "shared_tasks": sum(int(row["kind"] == "shared-input") for row in scored),
        "mean_packet_bytes": sum(row["packet_bytes"] for row in scored) / max(1, tasks),
        "mean_impact_ms": sum(row["impact_ms"] for row in scored) / max(1, tasks),
        "sync_enrich_ms": sync_ms,
    }


def run(base: Path, public_path: Path, secret_path: Path, output: Path) -> dict:
    public = json.loads(public_path.read_text(encoding="utf-8"))["tasks"]
    frozen: list[dict] = []
    sync_ms = 0.0
    for task in public:
        frozen_row, task_sync_ms = _freeze_task(base, task)
        frozen.append(frozen_row)
        sync_ms += task_sync_ms

    # SECRET is opened only after every packet is frozen.
    secret = {
        row["id"]: row
        for row in json.loads(secret_path.read_text(encoding="utf-8"))["tasks"]
    }
    scored = [_score_task(row, secret[row["id"]]) for row in frozen]
    payload = {
        "schema": "hashmarks.cross-repository-impact-qualification.v1",
        "protocol": {
            "public_only_until_packets_frozen": True,
            "secret_join_after_packet_freeze": True,
            "external_edit_simulated_before_impact": True,
            "execution_owner": "external",
        },
        "summary": _summary(scored, sync_ms),
        "rows": scored,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("public", type=Path)
    parser.add_argument("secret", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--scenarios", type=int, default=6)
    parser.add_argument("--decoys", type=int, default=24)
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    if args.generate:
        generate(
            args.base,
            args.public,
            args.secret,
            scenarios=args.scenarios,
            decoys=args.decoys,
        )
    payload = run(args.base, args.public, args.secret, args.output)
    log_command_output(logger, json.dumps(payload["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
