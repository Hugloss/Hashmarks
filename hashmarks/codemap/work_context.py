from __future__ import annotations

from typing import TYPE_CHECKING, cast

from .python_ast import estimate_tokens

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class WorkContextProjection:
    """Stateless disclosure of caller-supplied action evidence and role accounting."""

    @staticmethod
    def _work_context_anchor(row: dict[str, object], *, role: str) -> dict[str, object]:
        path = str(row.get("path") or "")
        symbol = str(row.get("qualname") or row.get("name") or "")
        signature = str(row.get("signature") or "").strip()
        content_parts = [f"path: {path}", f"role: {role}"]
        if symbol:
            content_parts.append(f"symbol: {symbol}")
        if signature:
            content_parts.append(f"signature: {signature}")
        content = "\n".join(content_parts)
        return {
            "path": path,
            "role": role,
            "symbol": symbol or None,
            "representation": "action-anchor",
            "content": content,
            "estimated_tokens": estimate_tokens(content),
            "canonical_rank": int(cast("int", row.get("canonical_rank") or 0)),
            "reason": f"{role}-anchor",
            "mandatory": role in {"edit", "verify", "contract"},
        }

    def _mandatory_work_context_items(
        self,
        action: Mapping[str, object],
    ) -> tuple[list[dict[str, object]], set[str]]:
        mandatory: list[dict[str, object]] = []
        seen: set[str] = set()
        by_path: dict[str, dict[str, object]] = {}
        for role in ("edit", "verify", "contract"):
            row = action.get(role)
            if not isinstance(row, dict):
                continue
            path = str(row.get("path") or "")
            if not path:
                continue
            existing = by_path.get(path)
            if existing is not None:
                covered = existing.setdefault("covered_roles", [str(existing["role"])])
                if isinstance(covered, list) and role not in covered:
                    covered.append(role)
                continue
            seen.add(path)
            item = self._work_context_anchor(row, role=role)
            item["covered_roles"] = [role]
            by_path[path] = item
            mandatory.append(item)
        return mandatory, seen

    def _optional_work_context_items(
        self,
        action: Mapping[str, object],
        *,
        seen: set[str],
    ) -> list[dict[str, object]]:
        optional: list[dict[str, object]] = []
        for key, role in (("related", "related"), ("inspect", "inspect")):
            rows = action.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                path = str(row.get("path") or "")
                if not path or path in seen:
                    continue
                seen.add(path)
                item = self._work_context_anchor(row, role=role)
                item["mandatory"] = False
                optional.append(item)
        return optional

    @staticmethod
    def _select_mandatory_work_context(
        mandatory: list[dict[str, object]],
        *,
        token_budget: int,
    ) -> tuple[list[dict[str, object]], int]:
        selected: list[dict[str, object]] = []
        used = 0
        for item in mandatory:
            cost = int(cast("int | str", item["estimated_tokens"]))
            if used + cost <= token_budget:
                selected.append(item)
                used += cost
        return selected, used

    @staticmethod
    def _work_context_role_state(
        action: Mapping[str, object],
        selected: list[dict[str, object]],
    ) -> tuple[dict[str, bool], list[str], list[str]]:
        roles = ("edit", "verify", "contract")
        role_coverage = {
            role: any(
                role
                in cast("Sequence[object]", item.get("covered_roles") or [item["role"]])
                for item in selected
            )
            for role in roles
        }
        required_roles = [role for role in roles if isinstance(action.get(role), dict)]
        missing_roles = [role for role in required_roles if not role_coverage[role]]
        return role_coverage, required_roles, missing_roles

    @staticmethod
    def _append_optional_work_context(
        selected: list[dict[str, object]],
        optional: list[dict[str, object]],
        *,
        used: int,
        token_budget: int,
    ) -> int:
        for item in optional:
            cost = int(cast("int | str", item["estimated_tokens"]))
            if used + cost > token_budget:
                continue
            selected.append(item)
            used += cost
        return used

    @staticmethod
    def _work_context_evidence_metrics(
        selected: list[dict[str, object]],
        *,
        used: int,
        safe: bool,
    ) -> dict[str, object]:
        supplied_bytes = sum(
            len(str(item["content"]).encode("utf-8")) for item in selected
        )
        useful_role_bytes = sum(
            len(str(item["content"]).encode("utf-8"))
            for item in selected
            if item["role"] in {"edit", "verify", "contract", "related", "inspect"}
        )
        duplicate_evidence_bytes = 0
        seen_content: set[tuple[str, str]] = set()
        for item in selected:
            identity = (str(item["path"]), str(item["content"]))
            size = len(str(item["content"]).encode("utf-8"))
            if identity in seen_content:
                duplicate_evidence_bytes += size
            seen_content.add(identity)
        return {
            "supplied_bytes": supplied_bytes,
            "useful_role_bytes": useful_role_bytes,
            "duplicate_evidence_bytes": duplicate_evidence_bytes,
            "useful_bytes_ratio": (
                useful_role_bytes / supplied_bytes if supplied_bytes else 0.0
            ),
            "tokens_per_safe_packet": used if safe else None,
        }

    def work(
        self,
        action: Mapping[str, object],
        *,
        token_budget: int = 512,
    ) -> dict[str, object]:
        """Build a deterministic, role-preserving worker context projection.

        Mandatory action anchors are selected before discretionary evidence. A
        larger budget therefore cannot evict edit/verification/contract evidence
        that fit at a smaller budget. The allocator does not rerank repository
        evidence and does not read SECRET benchmark data.
        """
        if token_budget < 1:
            raise ValueError("token_budget must be >= 1")

        mandatory, seen = self._mandatory_work_context_items(action)
        optional = self._optional_work_context_items(action, seen=seen)
        selected, used = self._select_mandatory_work_context(
            mandatory,
            token_budget=token_budget,
        )
        role_coverage, required_roles, missing_roles = self._work_context_role_state(
            action,
            selected,
        )
        if not missing_roles:
            used = self._append_optional_work_context(
                selected,
                optional,
                used=used,
                token_budget=token_budget,
            )
        safe = not missing_roles
        return {
            "schema": "hashmarks.agent-work-context.v1",
            "budget": token_budget,
            "estimated_tokens": used,
            "safe": safe,
            "required_roles": required_roles,
            "missing_roles": missing_roles,
            "role_coverage": role_coverage,
            "items": selected,
            "evidence_metrics": self._work_context_evidence_metrics(
                selected,
                used=used,
                safe=safe,
            ),
            "allocation": "mandatory-skeleton-then-discretionary",
            "monotonic_contract": "mandatory membership may only grow with budget",
        }

    def budget_sweep(
        self,
        action: Mapping[str, object],
        *,
        budgets: Sequence[int] = (128, 192, 256, 384, 512),
    ) -> dict[str, object]:
        """Measure minimum sufficient worker evidence without changing retrieval."""
        normalized = sorted({int(value) for value in budgets})
        if not normalized or normalized[0] < 1:
            raise ValueError("budgets must contain positive integers")
        rows: list[dict[str, object]] = []
        previous_mandatory: set[tuple[str, str]] = set()
        monotonic = True
        for budget in normalized:
            packet = self.work(action, token_budget=budget)
            mandatory = {
                (str(item["role"]), str(item["path"]))
                for item in cast("Sequence[Mapping[str, object]]", packet["items"])
                if bool(item["mandatory"])
            }
            if not previous_mandatory.issubset(mandatory):
                monotonic = False
            previous_mandatory = mandatory
            metrics = dict(cast("Mapping[str, object]", packet["evidence_metrics"]))
            rows.append(
                {
                    "budget": budget,
                    "safe": bool(packet["safe"]),
                    "estimated_tokens": int(
                        cast("int | str", packet["estimated_tokens"])
                    ),
                    "role_coverage": dict(
                        cast("Mapping[str, object]", packet["role_coverage"])
                    ),
                    **metrics,
                }
            )
        safe_budgets = [
            int(cast("int | str", row["budget"])) for row in rows if bool(row["safe"])
        ]
        return {
            "schema": "hashmarks.work-context-budget-sweep.v1",
            "rows": rows,
            "mandatory_monotonic": monotonic,
            "smallest_safe_budget": min(safe_budgets) if safe_budgets else None,
            "safe_budgets": safe_budgets,
            "optimization_target": "minimum-safe-evidence",
        }
