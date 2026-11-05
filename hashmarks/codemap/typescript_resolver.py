from __future__ import annotations

import base64
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
    inputs: tuple[tuple[str, bytes], ...] = ()
    files: tuple[str, ...] = ()
    compilers: tuple[dict[str, object], ...] = ()
    projects: tuple[dict[str, object], ...] = ()


_NODE_SCRIPT = r"""
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const request = JSON.parse(fs.readFileSync(0, 'utf8'));
const imports = request.imports;
const admitted = request.admitted_paths === null ? null : new Set(request.admitted_paths);
const root = process.cwd();
const configs = JSON.parse(process.argv[1] || '["tsconfig.json"]');
const out = [];
const inputs = new Map();
const seen = new Set();
const versions = new Set();
const compilers = new Map();
const files = new Set();
const projects = [];
const warnings = [];
let bytes = 0;
function rel(p) { return path.relative(root, p).split(path.sep).join('/'); }
function contained(p) { return p.startsWith(root + path.sep); }
function compiler(module) {
  if (compilers.has(module)) return;
  const before = fs.statSync(module);
  if (before.size > 33554432) throw new Error('TypeScript compiler entry exceeds provenance bound');
  const hash = crypto.createHash('sha256');
  const descriptor = fs.openSync(module, 'r');
  try {
    const buffer = Buffer.alloc(65536);
    for (;;) { const count = fs.readSync(descriptor, buffer, 0, buffer.length, null); if (!count) break; hash.update(buffer.subarray(0,count)); }
  } finally { fs.closeSync(descriptor); }
  const after = fs.statSync(module);
  if (['dev','ino','size','mtimeMs','ctimeMs'].some(key => before[key] !== after[key])) throw new Error('TypeScript compiler entry changed');
  compilers.set(module, {module:contained(module) ? rel(module) : 'typescript/'+path.basename(module), entry_file_sha256:hash.digest('hex'), scope:'selected-compiler-entry-file-only'});
}
function readInput(file) {
  const abs = path.resolve(file);
  if (!contained(abs)) throw new Error('TypeScript configuration input escaped repository');
  if (admitted !== null && !admitted.has(rel(abs))) throw new Error('TypeScript configuration input is not admitted');
  if (inputs.has(abs)) return Buffer.from(inputs.get(abs).content, 'base64').toString('utf8');
  if (!fs.existsSync(abs)) return undefined;
  const descriptor = fs.openSync(abs, 'r');
  const buffer = Buffer.alloc(1048577);
  let count = 0;
  try {
    const before = fs.fstatSync(descriptor);
    if (!before.isFile() || before.size > 1048576) throw new Error('TypeScript input exceeds byte bound');
    while (count < buffer.length) {
      const observed = fs.readSync(descriptor, buffer, count, buffer.length-count, null);
      if (!observed) break;
      count += observed;
    }
    const after = fs.fstatSync(descriptor);
    if (count > 1048576 || ['dev','ino','size','mtimeMs','ctimeMs'].some(key => before[key] !== after[key])) throw new Error('TypeScript input changed or exceeded bound');
  } finally { fs.closeSync(descriptor); }
  const raw = buffer.subarray(0,count);
  if (!inputs.has(abs)) {
    bytes += raw.length;
    if (inputs.size >= 128 || bytes > 8388608) throw new Error('TypeScript input closure exceeds bound');
    inputs.set(abs, {path: rel(abs), content: raw.toString('base64')});
  }
  return raw.toString('utf8');
}
function observe(configPath, depth) {
  configPath = path.resolve(configPath);
  if (seen.has(configPath)) return;
  if (depth > 16 || seen.size >= 32) throw new Error('TypeScript project reference closure exceeds bound');
  seen.add(configPath);
  let ts;
  try { const module = require.resolve('typescript', {paths:[path.dirname(configPath), root]}); compiler(module); ts = require(module); compilers.get(module).version = ts.version; }
  catch (e) { throw new Error('HASHMARKS_TYPESCRIPT_UNAVAILABLE'); }
  versions.add(ts.version);
  const read = ts.readConfigFile(configPath, readInput);
  if (read.error) throw new Error(ts.flattenDiagnosticMessageText(read.error.messageText, '\n'));
  const host = {...ts.sys, readFile: readInput};
  const parsed = ts.parseJsonConfigFileContent(read.config, host, path.dirname(configPath), undefined, configPath);
  if (parsed.errors && parsed.errors.length) throw new Error(ts.flattenDiagnosticMessageText(parsed.errors[0].messageText, '\n'));
  projects.push({config:rel(configPath),root:rel(path.dirname(configPath)) || '.',files:parsed.fileNames.map(file => rel(path.resolve(file))).filter(file => !file.startsWith('../'))});
  for (const file of parsed.fileNames) {
    const abs = path.resolve(file);
    if (!contained(abs)) continue;
    files.add(rel(abs));
    for (const specifier of imports[rel(abs)] || []) {
      const moduleHost = {...host, readFile: file => {
        const relative = rel(path.resolve(file));
        return relative.split('/').includes('node_modules') || !contained(path.resolve(file))
          ? ts.sys.readFile(file) : readInput(file);
      }};
      const resolved = ts.resolveModuleName(specifier, abs, parsed.options, moduleHost).resolvedModule;
      if (!resolved || !resolved.resolvedFileName) continue;
      const target = path.resolve(resolved.resolvedFileName);
      if (!contained(target) || rel(target).split('/').includes('node_modules')) continue;
      out.push({source: rel(abs), target: rel(target), specifier});
      if (out.length > 32768) throw new Error('TypeScript resolution edges exceed bound');
    }
  }
  for (const reference of parsed.projectReferences || []) {
    observe(ts.resolveProjectReferencePath(reference), depth + 1);
  }
}
try { for (const config of configs) observe(config, 0); }
catch (e) { console.error(String(e)); process.exit(5); }
const result = JSON.stringify({version:[...versions].sort().join(','),edges:out,inputs:[...inputs.values()],files:[...files].sort(),compilers:[...compilers.values()],projects,warnings});
if (Buffer.byteLength(result) > 16777216) { console.error('TypeScript result exceeds bound'); process.exit(6); }
process.stdout.write(result);
"""


def _response_rows(value: Mapping[str, object], name: str) -> list[dict[str, object]]:
    rows = value.get(name, [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("invalid TypeScript " + name)
    return rows


def _response_scope(
    value: Mapping[str, object],
) -> tuple[
    tuple[tuple[str, bytes], ...],
    tuple[str, ...],
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
]:
    inputs = []
    total = 0
    for member in _response_rows(value, "inputs"):
        path, content = member.get("path"), member.get("content")
        if not isinstance(path, str) or not isinstance(content, str):
            raise ValueError("invalid TypeScript input closure")
        raw = base64.b64decode(content, validate=True)
        total += len(raw)
        if len(raw) > 1_048_576 or total > 8_388_608 or len(inputs) >= 128:
            raise ValueError("TypeScript input closure exceeds bound")
        inputs.append((path, raw))
    files = value.get("files", [])
    if not isinstance(files, list) or any(not isinstance(path, str) for path in files):
        raise ValueError("invalid TypeScript project members")
    return (
        tuple(inputs),
        tuple(files),
        tuple(_response_rows(value, "compilers")),
        tuple(_response_rows(value, "projects")),
    )


class TypeScriptResolverProvider:
    name = "typescript-resolver"

    def __init__(self, node: str | None = None) -> None:
        self.node = node or shutil.which("node")

    def detect(
        self, workspace: Path, *, config_paths: Sequence[str] = ("tsconfig.json",)
    ) -> bool:
        if self.node is None or not any(
            (workspace / config).is_file() for config in config_paths
        ):
            return False
        return any(
            (workspace / config).parent.joinpath("node_modules/typescript").exists()
            or (workspace / "node_modules/typescript").exists()
            for config in config_paths
        )

    def collect(
        self,
        workspace: Path,
        imports: Mapping[str, Sequence[str]] | None = None,
        *,
        timeout: float = 20.0,
        config_paths: Sequence[str] = ("tsconfig.json",),
        admitted_paths: Sequence[str] | None = None,
    ) -> TypeScriptResolution:
        """Resolve supplied canonical imports without discovering source syntax."""
        unavailable = self._unavailable_reason(workspace, imports, config_paths)
        if unavailable is not None:
            return TypeScriptResolution(self.name, (), (unavailable,))
        assert imports is not None and self.node is not None
        try:
            completed = subprocess.run(
                [self.node, "-e", _NODE_SCRIPT, json.dumps(list(config_paths))],
                cwd=workspace,
                capture_output=True,
                text=True,
                input=json.dumps(
                    {"imports": imports, "admitted_paths": admitted_paths},
                    sort_keys=True,
                ),
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
        self,
        workspace: Path,
        imports: Mapping[str, Sequence[str]] | None,
        config_paths: Sequence[str],
    ) -> str | None:
        if imports is None:
            return "canonical source imports unavailable"
        if self.node is None:
            return "node executable unavailable"
        if (
            not config_paths
            or len(config_paths) > 32
            or any(not (workspace / config).is_file() for config in config_paths)
        ):
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
        producer = f"typescript-resolver:{version}:canonical-syntax.v2"
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
        try:
            inputs, files, compilers, projects = _response_scope(value)
        except (KeyError, TypeError, ValueError):
            return TypeScriptResolution(
                producer, (), ("invalid TypeScript input closure",)
            )
        return TypeScriptResolution(
            producer, tuple(edges), warnings, inputs, files, compilers, projects
        )
