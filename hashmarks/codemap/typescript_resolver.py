from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class NativeFileEdge:
    source: str
    target: str
    kind: str
    confidence: str
    producer: str
    specifier: str | None = None


@dataclass(frozen=True)
class TypeScriptResolution:
    producer: str
    edges: tuple[NativeFileEdge, ...]
    warnings: tuple[str, ...] = ()


_NODE_SCRIPT = r"""
const fs = require('fs');
const path = require('path');
let ts;
try { ts = require(require.resolve('typescript', {paths:[process.cwd()]})); }
catch (e) { console.error('HASHMARKS_TYPESCRIPT_UNAVAILABLE'); process.exit(3); }
const configName = process.argv[1] || 'tsconfig.json';
const configPath = path.resolve(configName);
if (!fs.existsSync(configPath)) { console.error('HASHMARKS_TSCONFIG_MISSING'); process.exit(4); }
const read = ts.readConfigFile(configPath, ts.sys.readFile);
if (read.error) { console.error(ts.flattenDiagnosticMessageText(read.error.messageText, '\n')); process.exit(5); }
const parsed = ts.parseJsonConfigFileContent(read.config, ts.sys, path.dirname(configPath));
const imports = JSON.parse(fs.readFileSync(0, 'utf8'));
const root = process.cwd();
const out = [];
function rel(p) { return path.relative(root, p).split(path.sep).join('/'); }
for (const file of parsed.fileNames) {
  const abs = path.resolve(file);
  if (!abs.startsWith(root + path.sep) && abs !== root) continue;
  // Hashmarks' admitted syntax owns occurrences; TypeScript owns resolution.
  for (const specifier of imports[rel(abs)] || []) {
    const resolved = ts.resolveModuleName(specifier, abs, parsed.options, ts.sys).resolvedModule;
    if (!resolved || !resolved.resolvedFileName) continue;
    let target = path.resolve(resolved.resolvedFileName);
    target = target.replace(/\.d\.ts$/, '.ts');
    if (!target.startsWith(root + path.sep) && target !== root) continue;
    out.push({source: rel(abs), target: rel(target), specifier});
  }
}
process.stdout.write(JSON.stringify({version: ts.version, config: rel(configPath), edges: out}));
"""


class TypeScriptResolverProvider:
    name = "typescript-resolver"

    def __init__(self, node: str | None = None) -> None:
        self.node = node or shutil.which("node")

    def detect(self, workspace: Path) -> bool:
        if self.node is None or not (workspace / "tsconfig.json").is_file():
            return False
        local = workspace / "node_modules" / "typescript"
        return local.exists()

    def collect(
        self,
        workspace: Path,
        imports: Mapping[str, Sequence[str]] | None = None,
        *,
        timeout: float = 20.0,
    ) -> TypeScriptResolution:
        """Resolve supplied canonical imports without discovering source syntax."""
        unavailable = self._unavailable_reason(workspace, imports)
        if unavailable is not None:
            return TypeScriptResolution(self.name, (), (unavailable,))
        assert imports is not None and self.node is not None
        try:
            completed = subprocess.run(
                [self.node, "-e", _NODE_SCRIPT, "tsconfig.json"],
                cwd=workspace,
                capture_output=True,
                text=True,
                input=json.dumps(imports, sort_keys=True),
                timeout=timeout,
                check=False,
                env=os.environ.copy(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return TypeScriptResolution(
                self.name, (), (f"TypeScript resolver failed: {exc}",)
            )
        if completed.returncode != 0:
            detail = (
                completed.stderr.strip().splitlines()[-1]
                if completed.stderr.strip()
                else f"exit {completed.returncode}"
            )
            return TypeScriptResolution(
                self.name, (), (f"TypeScript resolver unavailable: {detail}",)
            )
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return TypeScriptResolution(
                self.name, (), ("TypeScript resolver returned invalid JSON",)
            )
        return self._resolution(value, imports)

    def _unavailable_reason(
        self, workspace: Path, imports: Mapping[str, Sequence[str]] | None
    ) -> str | None:
        if imports is None:
            return "canonical source imports unavailable"
        if self.node is None:
            return "node executable unavailable"
        if not (workspace / "tsconfig.json").is_file():
            return "tsconfig.json unavailable"
        return None

    @staticmethod
    def _resolution(
        value: object, imports: Mapping[str, Sequence[str]]
    ) -> TypeScriptResolution:
        if not isinstance(value, dict):
            return TypeScriptResolution(
                TypeScriptResolverProvider.name, (), ("invalid resolver response",)
            )
        version = str(value.get("version") or "unknown")
        producer = f"typescript-resolver:{version}:canonical-syntax.v1"
        rows = value.get("edges")
        if not isinstance(rows, list):
            return TypeScriptResolution(
                producer, (), ("TypeScript resolver edges unavailable: expected array",)
            )
        edges: list[NativeFileEdge] = []
        rejected = 0
        for row in rows:
            if (
                not isinstance(row, dict)
                or not row.get("source")
                or not row.get("target")
            ):
                rejected += 1
                continue
            if row.get("specifier") not in imports.get(str(row["source"]), ()):
                rejected += 1
                continue
            edges.append(
                NativeFileEdge(
                    source=str(row["source"]),
                    target=str(row["target"]),
                    kind="module-resolution",
                    confidence="native",
                    producer=producer,
                    specifier=str(row["specifier"]),
                )
            )
        warnings = (
            (f"TypeScript resolver discarded {rejected} unqualified source edges",)
            if rejected
            else ()
        )
        return TypeScriptResolution(producer, tuple(edges), warnings)
