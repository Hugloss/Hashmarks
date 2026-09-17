from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .paths import canonical_host_path, normalize_relative_path

if TYPE_CHECKING:
    from collections.abc import Sequence

# Explicit agent-lane helper. It uses documented Vitest/Vite advanced APIs but
# never invokes Vitest's test runner or imports test/application modules for
# execution. Vite transforms populate its native module graph and may execute
# repository config/plugin code, which is why this is never an Identity hot-path
# operation and is only run from explicit native enrichment/selection.
_VITEST_VITE_HELPER = r"""import fs from 'node:fs';
import path from 'node:path';
import { createVitest } from 'vitest/node';
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const root = path.resolve(input.root);
const changed = new Set(input.changed.map(p => path.resolve(root, p)));
const vitest = await createVitest('test', { watch: false }, { server: { watch: null } });
function cleanId(id) { return String(id || '').split('?', 1)[0]; }
function fileOf(mod) {
  const raw = mod?.file || mod?.id || '';
  if (!raw || raw.startsWith('virtual:') || raw.startsWith('\\0')) return null;
  const clean = cleanId(raw);
  return path.isAbsolute(clean) ? path.resolve(clean) : null;
}
async function expand(project, id, seen) {
  if (!id || seen.has(id)) return;
  seen.add(id);
  try { await project.vite.transformRequest(id); } catch (_) {}
  let mod = project.vite.moduleGraph.getModuleById(id);
  if (!mod && path.isAbsolute(cleanId(id))) {
    const candidates = project.vite.moduleGraph.getModulesByFile(path.resolve(cleanId(id)));
    if (candidates) mod = [...candidates][0];
  }
  if (!mod) return;
  for (const dep of mod.importedModules || []) {
    const depId = dep.id || dep.file || dep.url;
    if (depId) await expand(project, depId, seen);
  }
}
const specs = await vitest.globTestSpecifications();
const selected = [];
const edges = [];
for (const spec of specs) {
  const seenIds = new Set();
  await expand(spec.project, spec.moduleId, seenIds);
  const files = new Set();
  for (const id of seenIds) {
    const mod = spec.project.vite.moduleGraph.getModuleById(id);
    const file = fileOf(mod) || (path.isAbsolute(cleanId(id)) ? path.resolve(cleanId(id)) : null);
    if (file && file.startsWith(root + path.sep)) files.add(file);
  }
  const testFile = path.resolve(cleanId(spec.moduleId));
  if (testFile.startsWith(root + path.sep)) files.add(testFile);
  if ([...files].some(file => changed.has(file))) selected.push(testFile);
  for (const file of files) if (file !== testFile) edges.push([testFile, file]);
}
try { await vitest.close(); } catch (_) {}
process.stdout.write(JSON.stringify({ selected, edges }));
"""


@dataclass(frozen=True, slots=True)
class VitestViteEdge:
    source: str
    target: str
    kind: str = "vite-static-import"
    confidence: str = "native-static"
    producer: str = "vitest-vite"
    specifier: str | None = None


@dataclass(frozen=True, slots=True)
class VitestViteGraph:
    producer: str
    selected: tuple[str, ...]
    edges: tuple[VitestViteEdge, ...]
    command: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def local_vitest(root: Path) -> Path | None:
    for rel in (Path("node_modules/.bin/vitest"), Path("node_modules/.bin/vitest.cmd")):
        candidate = root / rel
        if candidate.is_file():
            return candidate
    return None


def _workspace_rel(root: Path, value: str, *, require_file: bool = True) -> str | None:
    try:
        resolved = Path(value).resolve(strict=False)
        rel = resolved.relative_to(root).as_posix()
    except (OSError, ValueError):
        return None
    if require_file and (not resolved.is_file() or resolved.is_symlink()):
        return None
    return rel


def _normalized_changed_paths(
    root: Path, changed_paths: Sequence[str]
) -> tuple[list[str], list[str]]:
    normalized: list[str] = []
    warnings: list[str] = []
    for raw in changed_paths:
        try:
            rel = normalize_relative_path(raw, allow_root=False)
        except ValueError:
            warnings.append(f"ignored invalid changed path: {raw!r}")
            continue
        candidate = root / rel
        if candidate.exists() and not candidate.is_symlink():
            normalized.append(rel)
        else:
            warnings.append(
                f"changed path is missing/symlink and cannot be resolved by Vite: {rel}"
            )
    return normalized, warnings


def _write_vitest_helper(root: Path) -> Path:
    state = root / ".hashmarks"
    state.mkdir(parents=True, exist_ok=True)
    fd, helper_raw = tempfile.mkstemp(prefix="vitest-vite-", suffix=".mjs", dir=state)
    helper = Path(helper_raw)
    try:
        os.write(fd, _VITEST_VITE_HELPER.encode("utf-8"))
    finally:
        os.close(fd)
    return helper


def _run_vitest_helper(
    argv: tuple[str, ...], root: Path, payload: str, timeout: float
) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
    try:
        completed = subprocess.run(
            list(argv),
            cwd=root,
            input=payload,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"Vitest/Vite graph unavailable: {exc.__class__.__name__}"
    if completed.returncode == 0:
        return completed, None
    lines = completed.stderr.strip().splitlines()
    suffix = f": {lines[-1]}" if lines else ""
    return None, f"Vitest/Vite graph exited {completed.returncode}{suffix}"


def _vitest_payload(stdout: str) -> tuple[dict[str, object] | None, str | None]:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError:
        return None, "Vitest/Vite graph returned invalid JSON"
    if not isinstance(value, dict):
        return None, "Vitest/Vite graph returned invalid payload"
    return value, None


def _selected_paths(root: Path, value: dict[str, object]) -> tuple[str, ...]:
    raw_selected = value.get("selected", ())
    rows = raw_selected if isinstance(raw_selected, list) else ()
    selected = [
        rel for raw in rows if (rel := _workspace_rel(root, str(raw))) is not None
    ]
    return tuple(sorted(dict.fromkeys(selected)))


def _vite_edges(root: Path, value: dict[str, object]) -> tuple[VitestViteEdge, ...]:
    raw_edges = value.get("edges", ())
    if not isinstance(raw_edges, list):
        return ()
    edges: list[VitestViteEdge] = []
    for row in raw_edges:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            continue
        source = _workspace_rel(root, str(row[0]))
        target = _workspace_rel(root, str(row[1]))
        if source is not None and target is not None and source != target:
            edges.append(VitestViteEdge(source=source, target=target))
    return tuple(
        sorted(
            dict.fromkeys(edges), key=lambda edge: (edge.source, edge.target, edge.kind)
        )
    )


def _unavailable_vitest(
    argv: tuple[str, ...], warnings: list[str], error: str
) -> VitestViteGraph:
    return VitestViteGraph("vitest-vite", (), (), argv, (*warnings, error))


def _collect_vitest_value(
    argv: tuple[str, ...], root: Path, payload: str, timeout: float, warnings: list[str]
) -> tuple[dict[str, object] | None, VitestViteGraph | None]:
    completed, error = _run_vitest_helper(argv, root, payload, timeout)
    if completed is None:
        return None, _unavailable_vitest(
            argv, warnings, error or "Vitest/Vite graph unavailable"
        )
    value, error = _vitest_payload(completed.stdout)
    if value is None:
        return None, _unavailable_vitest(
            argv, warnings, error or "Vitest/Vite graph unavailable"
        )
    return value, None


def _vitest_result(
    root: Path, argv: tuple[str, ...], warnings: list[str], value: dict[str, object]
) -> VitestViteGraph:
    return VitestViteGraph(
        producer="vitest-vite",
        selected=_selected_paths(root, value),
        edges=_vite_edges(root, value),
        command=argv,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def collect_vitest_vite_graph(
    workspace: str | Path,
    *,
    changed_paths: Sequence[str] = (),
    node: str | None = None,
    timeout: float = 30.0,
) -> VitestViteGraph:
    root = canonical_host_path(workspace)
    node_exe = node or shutil.which("node")
    if node_exe is None:
        return VitestViteGraph(
            "vitest-vite", (), (), (), ("node executable not found",)
        )
    if local_vitest(root) is None:
        return VitestViteGraph(
            "vitest-vite", (), (), (), ("repository-local Vitest package not found",)
        )
    normalized, warnings = _normalized_changed_paths(root, changed_paths)
    helper = _write_vitest_helper(root)
    argv = (str(node_exe), str(helper))
    try:
        payload = json.dumps({"root": str(root), "changed": normalized})
        value, unavailable = _collect_vitest_value(
            argv, root, payload, timeout, warnings
        )
        return (
            unavailable
            if unavailable is not None
            else _vitest_result(root, argv, warnings, value or {})
        )
    finally:
        with contextlib.suppress(OSError):
            helper.unlink()
