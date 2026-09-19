from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from .python_ast import estimate_tokens
from .query_primitives import _TASK_STOPWORDS, _WORD_RE

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .engine import CodeMap


@dataclass
class _JsonContainerScan:
    opener: str
    closer: str
    depth: int = 0
    in_string: bool = False
    escaped: bool = False
    started: bool = False

    def consume(self, char: str) -> bool:
        if self.in_string:
            if self.escaped:
                self.escaped = False
            elif char == "\\":
                self.escaped = True
            elif char == '"':
                self.in_string = False
            return False
        if char == '"':
            self.in_string = True
            return False
        if char == self.opener:
            self.depth += 1
            self.started = True
        elif char == self.closer and self.started:
            self.depth -= 1
            return self.depth == 0
        return False


class ConfigurationEvidenceMixin:
    """Exact task-local configuration evidence projection.

    This owner only projects a task-mentioned key or section from an already
    selected configuration path. It does not select ownership or infer values.
    """

    @staticmethod
    def _config_name_parts(value: str) -> tuple[str, ...]:
        return tuple(
            part.lower()
            for part in re.findall(r"[A-Za-z][A-Za-z0-9_-]*", value)
            if len(part) >= 2
        )

    @staticmethod
    def _config_task_terms(task: str) -> frozenset[str]:
        return frozenset(
            token.lower()
            for token in _WORD_RE.findall(task)
            if len(token) >= 2 and token.lower() not in _TASK_STOPWORDS
        )

    @classmethod
    def _config_candidate_score(
        cls, name: str, task_terms: frozenset[str]
    ) -> tuple[int, int] | None:
        parts = cls._config_name_parts(name)
        if not parts or not set(parts).issubset(task_terms):
            return None
        # More task-supported path components are more specific.  Length is a
        # deterministic secondary preference only; it never overcomes missing
        # task evidence.
        return (len(set(parts)), len(name))

    @staticmethod
    def _yaml_section_end(lines: list[str], start_index: int, indent: int) -> int:
        end = start_index
        for index in range(start_index + 1, len(lines)):
            raw = lines[index]
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                end = index
                continue
            current_indent = len(raw) - len(raw.lstrip(" "))
            if current_indent <= indent:
                break
            end = index
        return end

    @staticmethod
    def _json_value_line_segment(raw: str, *, first: bool) -> str:
        if not first:
            return raw
        colon = raw.find(":")
        return raw[colon + 1 :] if colon >= 0 else raw

    @staticmethod
    def _json_value_end(
        lines: list[str], start_index: int, value_text: str
    ) -> int | None:
        stripped = value_text.strip()
        if not stripped:
            return None
        scalar = stripped.rstrip(",").strip()
        try:
            json.loads(scalar)
        except json.JSONDecodeError:
            pass
        else:
            return start_index
        opener = stripped[0]
        if opener not in "[{":
            return None
        scan = _JsonContainerScan(opener, "]" if opener == "[" else "}")
        for index in range(start_index, len(lines)):
            segment = ConfigurationEvidenceMixin._json_value_line_segment(
                lines[index], first=index == start_index
            )
            for char in segment:
                if scan.consume(char):
                    return index
        return None

    def _toml_key_candidate(
        self, raw: str, index: int, section: str, task_terms: set[str]
    ) -> dict[str, object] | None:
        match = re.match(
            r'^\s*([A-Za-z0-9_.-]+|"[^"]+"|\'[^\']+\')\s*=\s*(.+?)\s*$', raw
        )
        if not match:
            return None
        key = match.group(1).strip().strip("\"'")
        try:
            tomllib.loads(f"{key} = {match.group(2)}\n")
        except tomllib.TOMLDecodeError:
            return None
        full_name = f"{section}.{key}" if section else key
        score = self._config_candidate_score(full_name, task_terms)
        if score is None:
            score = self._config_candidate_score(key, task_terms)
        if score is None:
            return None
        return {
            "kind": "key",
            "name": full_name,
            "start": index,
            "end": index,
            "score": score,
        }

    def _toml_config_candidates(
        self,
        source: str,
        lines: Sequence[str],
        task_terms: set[str],
    ) -> list[dict[str, object]] | None:
        """Return exact TOML key/section candidates, or None for invalid syntax."""
        try:
            tomllib.loads(source)
        except tomllib.TOMLDecodeError:
            return None
        candidates: list[dict[str, object]] = []
        section = ""
        headers: list[tuple[int, str]] = []
        for index, raw in enumerate(lines):
            match = re.match(r"^\s*\[\[?\s*([^\]]+?)\s*\]\]?\s*(?:#.*)?$", raw)
            if match:
                section = match.group(1).strip().strip("\"'")
                headers.append((index, section))
                continue
            candidate = self._toml_key_candidate(raw, index, section, task_terms)
            if candidate is not None:
                candidates.append(candidate)
        for header_index, (start, name) in enumerate(headers):
            score = self._config_candidate_score(name, task_terms)
            if score is None:
                continue
            end = (
                headers[header_index + 1][0] - 1
                if header_index + 1 < len(headers)
                else len(lines) - 1
            )
            while end > start and not lines[end].strip():
                end -= 1
            candidates.append(
                {
                    "kind": "section",
                    "name": name,
                    "start": start,
                    "end": end,
                    "score": score,
                }
            )
        return candidates

    def _json_config_candidates(
        self,
        source: str,
        lines: Sequence[str],
        task_terms: set[str],
    ) -> list[dict[str, object]] | None:
        """Return exact JSON key ranges, or None for invalid syntax."""
        try:
            json.loads(source)
        except json.JSONDecodeError:
            return None
        candidates: list[dict[str, object]] = []
        for index, raw in enumerate(lines):
            match = re.match(r'^\s*"([^"\\]+)"\s*:\s*(.*)$', raw)
            if not match:
                continue
            key = match.group(1)
            score = self._config_candidate_score(key, task_terms)
            if score is None:
                continue
            end = self._json_value_end(lines, index, match.group(2))
            if end is not None:
                candidates.append(
                    {
                        "kind": "key",
                        "name": key,
                        "start": index,
                        "end": end,
                        "score": score,
                    }
                )
        return candidates

    def _yaml_config_candidates(
        self,
        lines: Sequence[str],
        task_terms: set[str],
    ) -> list[dict[str, object]]:
        """Return indentation-bounded YAML key/section candidates."""
        candidates: list[dict[str, object]] = []
        stack: list[tuple[int, str]] = []
        for index, raw in enumerate(lines):
            if (
                not raw.strip()
                or raw.lstrip().startswith("#")
                or "\t" in raw[: len(raw) - len(raw.lstrip())]
            ):
                continue
            match = re.match(
                r'^(\s*)([A-Za-z0-9_.-]+|"[^"]+"|\'[^\']+\')\s*:\s*(.*)$', raw
            )
            if not match:
                continue
            indent = len(match.group(1))
            key = match.group(2).strip().strip("\"'")
            while stack and stack[-1][0] >= indent:
                stack.pop()
            parent = ".".join(name for _, name in stack)
            full_name = f"{parent}.{key}" if parent else key
            score = self._config_candidate_score(full_name, task_terms)
            score = (
                self._config_candidate_score(key, task_terms)
                if score is None
                else score
            )
            value = match.group(3).strip()
            if score is not None:
                end = (
                    index
                    if value and value not in {"|", ">", "|-", ">-", "|+", ">+"}
                    else self._yaml_section_end(lines, index, indent)
                )
                candidates.append(
                    {
                        "kind": "key" if end == index else "section",
                        "name": full_name,
                        "start": index,
                        "end": end,
                        "score": score,
                    }
                )
            if not value:
                stack.append((indent, key))
        return candidates

    def _config_candidates(
        self, source: str, suffix: str, task_terms: set[str]
    ) -> list[dict[str, object]] | None:
        lines = source.splitlines()
        if suffix == ".toml":
            return self._toml_config_candidates(source, lines, task_terms)
        if suffix == ".json":
            return self._json_config_candidates(source, lines, task_terms)
        return self._yaml_config_candidates(lines, task_terms)

    def _project_config_candidate(
        self,
        path: str,
        role: str,
        suffix: str,
        source: str,
        candidates: list[dict[str, object]],
        token_budget: int,
    ) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        if not candidates:
            return None, {
                "role": role,
                "path": path,
                "reason": "no-task-local-config-key",
            }
        best_score = max(candidate["score"] for candidate in candidates)
        best = [
            candidate for candidate in candidates if candidate["score"] == best_score
        ]
        unique_ranges = {
            (int(candidate["start"]), int(candidate["end"]), str(candidate["name"]))
            for candidate in best
        }
        if len(unique_ranges) != 1:
            return None, {
                "role": role,
                "path": path,
                "reason": "ambiguous-task-local-config-key",
                "candidate_count": len(unique_ranges),
            }
        chosen = best[0]
        start = int(chosen["start"])
        end = int(chosen["end"])
        lines = source.splitlines()
        content = "\n".join(lines[start : end + 1])
        if source.endswith("\n") and end == len(lines) - 1:
            content += "\n"
        estimated_tokens = estimate_tokens(content)
        pending = {
            "role": role,
            "path": path,
            "lines": [start + 1, end + 1],
            "reason": "exact-config-range-exceeds-start-budget",
            "estimated_tokens": estimated_tokens,
            "config": {
                "format": suffix.lstrip(".").replace("yml", "yaml"),
                "kind": str(chosen["kind"]),
                "name": str(chosen["name"]),
                "locator": "exact-task-key",
            },
        }
        if estimated_tokens > token_budget:
            return None, pending
        return {
            "role": role,
            "path": path,
            "symbol": str(chosen["name"]),
            "lines": [start + 1, end + 1],
            "representation": "config-key-range",
            "content": content,
            "estimated_tokens": estimated_tokens,
            "config": pending["config"],
        }, None

    def _task_evidence_config_evidence(
        self,
        path: str,
        *,
        task: str,
        role: str,
        token_budget: int,
    ) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        """Project an exact task-mentioned config key/section from one owner.

        This runs only after ``task_action_map`` has already selected ``path``.
        It does not select configuration ownership or infer a desired value.
        Candidate admission is deliberately lexical and fail-closed: the task
        must name every component of the key/section and the best candidate must
        be unique.  Unsupported/ambiguous syntax remains an explicit next-read.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        suffix = Path(path).suffix.lower()
        if suffix not in {".toml", ".json", ".yaml", ".yml"} or not task.strip():
            return None, None
        task_terms = self._config_task_terms(task)
        if not task_terms:
            return None, {
                "role": role,
                "path": path,
                "reason": "no-task-local-config-key",
            }
        # Reconcile the selected configuration path before reading it so the
        # emitted range and its source revision are bound to current bytes.
        # If this changes the CodeMap generation, task_evidence marks the
        # packet stale rather than pretending the earlier ownership decision
        # remained generation-bound.
        self._ensure_path_current(path)
        try:
            source = (self.workspace / path).read_text(encoding="utf-8")
        except (OSError, PermissionError, FileNotFoundError):
            return None, {
                "role": role,
                "path": path,
                "reason": "config-source-unavailable",
            }
        candidates = self._config_candidates(source, suffix, task_terms)
        if candidates is None:
            return None, {
                "role": role,
                "path": path,
                "reason": "invalid-config-syntax",
            }

        return self._project_config_candidate(
            path, role, suffix, source, candidates, token_budget
        )
