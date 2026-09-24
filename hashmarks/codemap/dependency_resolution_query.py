from __future__ import annotations

from collections.abc import Mapping, Sequence

MAX_QUERIES = 32
MAX_RESULTS = 256
MAX_DEPTH = 16
MAX_VISITS = 4096


def _text(value: object, *, label: str, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{label} must not be empty")
    return text


def _bounds(request: Mapping[str, object]) -> tuple[int, int, int]:
    def bounded(name: str, default: int, maximum: int) -> int:
        raw = request.get(name, default)
        if isinstance(raw, bool):
            raise ValueError(f"{name} must be a positive integer")
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a positive integer") from exc
        if value < 1 or value > maximum:
            raise ValueError(f"{name} must be between 1 and {maximum}")
        return value

    return (
        bounded("max_depth", 8, MAX_DEPTH),
        bounded("max_results", 100, MAX_RESULTS),
        bounded("max_visits", 1024, MAX_VISITS),
    )


def _limited(
    rows: list[object],
    *,
    max_results: int,
    omissions: list[dict[str, object]],
) -> list[object]:
    if len(rows) > max_results:
        omissions.append({"reason": "result-limit", "omitted": len(rows) - max_results})
    return rows[:max_results]


def _adjacency(
    relationships: Sequence[Mapping[str, object]],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    outgoing: dict[str, list[str]] = {}
    incoming: dict[str, list[str]] = {}
    for row in relationships:
        source = str(row.get("source") or "")
        target = str(row.get("target") or "")
        outgoing.setdefault(source, []).append(target)
        incoming.setdefault(target, []).append(source)
    for values in outgoing.values():
        values.sort()
    for values in incoming.values():
        values.sort()
    return outgoing, incoming


def _walk(
    start: str,
    adjacency: Mapping[str, Sequence[str]],
    selections: Mapping[str, Mapping[str, object]],
    *,
    max_depth: int,
    max_results: int,
    max_visits: int,
) -> tuple[list[object], int, list[dict[str, object]]]:
    queue: list[tuple[str, int]] = [(start, 0)]
    seen = {start}
    rows: list[object] = []
    omissions: list[dict[str, object]] = []
    negative_evidence = "not-applicable"
    source_complete = True
    visited = 0
    while queue:
        current, depth = queue.pop(0)
        if depth >= max_depth:
            if adjacency.get(current):
                omissions.append({"reason": "depth-limit", "node_id": current})
            continue
        for candidate in adjacency.get(current, ()):
            if visited >= max_visits:
                omissions.append({"reason": "visit-limit"})
                queue.clear()
                break
            visited += 1
            if candidate in seen:
                continue
            seen.add(candidate)
            if len(rows) >= max_results:
                omissions.append({"reason": "result-limit"})
                queue.clear()
                break
            rows.append(
                {
                    "node_id": candidate,
                    "depth": depth + 1,
                    "selection": selections.get(candidate),
                }
            )
            queue.append((candidate, depth + 1))
    return rows, visited, omissions


# Query traversal is deliberately bounded and cycle-aware; splitting the state machine
# would obscure the omission semantics it owns.
def _reachability(  # noqa: C901
    start: str,
    target: str,
    outgoing: Mapping[str, Sequence[str]],
    *,
    max_depth: int,
    max_visits: int,
) -> tuple[bool, int, list[dict[str, object]]]:
    queue: list[tuple[str, int]] = [(start, 0)]
    seen = {start}
    omissions: list[dict[str, object]] = []
    visited = 0
    if start == target:
        return True, visited, omissions
    while queue:
        current, depth = queue.pop(0)
        if depth >= max_depth:
            if outgoing.get(current):
                omissions.append({"reason": "depth-limit", "node_id": current})
            continue
        for candidate in outgoing.get(current, ()):
            if visited >= max_visits:
                omissions.append({"reason": "visit-limit"})
                return False, visited, omissions
            visited += 1
            if candidate == target:
                return True, visited, omissions
            if candidate not in seen:
                seen.add(candidate)
                queue.append((candidate, depth + 1))
    return False, visited, omissions


def _paths(  # noqa: C901, PLR0912
    start: str,
    target: str,
    outgoing: Mapping[str, Sequence[str]],
    *,
    max_depth: int,
    max_results: int,
    max_visits: int,
) -> tuple[list[object], int, list[dict[str, object]]]:
    queue: list[list[str]] = [[start]]
    paths: list[object] = []
    omissions: list[dict[str, object]] = []
    visited = 0
    while queue:
        path = queue.pop(0)
        current = path[-1]
        if current == target:
            if len(paths) >= max_results:
                omissions.append({"reason": "result-limit"})
                break
            paths.append(path)
            continue
        if len(path) - 1 >= max_depth:
            if outgoing.get(current):
                omissions.append({"reason": "depth-limit", "node_id": current})
            continue
        for candidate in outgoing.get(current, ()):
            if visited >= max_visits:
                omissions.append({"reason": "visit-limit"})
                queue.clear()
                break
            visited += 1
            if candidate == target:
                if len(paths) >= max_results:
                    omissions.append({"reason": "result-limit"})
                    queue.clear()
                    break
                paths.append([*path, candidate])
            elif candidate not in path:
                queue.append([*path, candidate])
    return paths, visited, omissions


def _coverage_complete(
    observation: Mapping[str, object],
    *,
    context: str,
    kind: str = "resolution-graph",
) -> bool:
    rows = [
        row
        for row in observation.get("coverage", ())
        if isinstance(row, Mapping)
        and str(row.get("kind") or "") == kind
        and (not context or str(row.get("context") or "") == context)
    ]
    if not context:
        declared_contexts = {
            str(value) for value in observation.get("contexts", ()) if str(value)
        }
        covered_contexts = {str(row.get("context") or "") for row in rows}
        if declared_contexts - covered_contexts:
            return False
    return bool(rows) and all(
        row.get("completeness") == "complete" and row.get("truncation") == "complete"
        for row in rows
    )


def dependency_query(  # noqa: C901, PLR0912, PLR0914, PLR0915
    observation: Mapping[str, object],
    request: Mapping[str, object],
) -> dict[str, object]:
    operation = _text(
        request.get("operation"), label="dependency query operation", required=True
    )
    allowed = {
        "component",
        "dependencies",
        "dependents",
        "paths",
        "reachability",
        "contexts",
        "inventory",
        "module-owners",
    }
    if operation not in allowed:
        raise ValueError(f"unsupported dependency query operation: {operation}")
    max_depth, max_results, max_visits = _bounds(request)
    node_id = _text(request.get("node_id"), label="dependency query node_id")
    target_id = _text(request.get("target_id"), label="dependency query target_id")
    component_id = _text(
        request.get("component_id"), label="dependency query component_id"
    )
    context = _text(request.get("context"), label="dependency query context")
    module = _text(request.get("module"), label="dependency query module")
    declared_contexts = {
        str(value) for value in observation.get("contexts", ()) if str(value)
    }
    if context and context not in declared_contexts:
        raise ValueError(f"unknown dependency query context: {context}")
    omissions: list[dict[str, object]] = []
    visited = 0
    negative_evidence = "not-applicable"
    source_complete = True

    selections = {
        str(row["node_id"]): row
        for row in observation.get("selections", ())
        if isinstance(row, Mapping) and row.get("node_id")
    }
    relationships = [
        row
        for row in observation.get("relationships", ())
        if isinstance(row, Mapping)
        and (not context or str(row.get("context") or "") == context)
    ]

    if operation == "component":
        if not component_id:
            raise ValueError("component query requires component_id")
        rows = [
            dict(row)
            for row in observation.get("components", ())
            if isinstance(row, Mapping)
            and str(row.get("component_id") or "") == component_id
        ]
        result: object = _limited(rows, max_results=max_results, omissions=omissions)
        if not rows:
            negative_evidence = "admissible-within-declared-scope"
    elif operation == "inventory":
        rows = [
            dict(row)
            for row in observation.get("inventory", ())
            if isinstance(row, Mapping)
            and (not node_id or str(row.get("node_id") or "") == node_id)
            and (not context or str(row.get("context") or "") == context)
        ]
        result = _limited(rows, max_results=max_results, omissions=omissions)
        source_complete = _coverage_complete(
            observation, context=context, kind="resolved-inventory"
        )
        if node_id and not rows:
            negative_evidence = (
                "admissible-within-declared-scope"
                if source_complete
                else "not-admissible"
            )
    elif operation == "contexts":
        if not node_id:
            raise ValueError("contexts query requires node_id")
        if node_id not in selections:
            raise ValueError(f"unknown dependency query node_id: {node_id}")
        values = {
            str(row.get("context") or "")
            for row in observation.get("inventory", ())
            if isinstance(row, Mapping) and str(row.get("node_id") or "") == node_id
        }
        values.update(
            str(row.get("context") or "")
            for row in observation.get("relationships", ())
            if isinstance(row, Mapping)
            and (
                str(row.get("source") or "") == node_id
                or str(row.get("target") or "") == node_id
            )
        )
        values.update(
            str(value)
            for row in observation.get("selections", ())
            if isinstance(row, Mapping) and str(row.get("node_id") or "") == node_id
            for value in row.get("contexts", ())
        )
        result = _limited(
            sorted(value for value in values if value),
            max_results=max_results,
            omissions=omissions,
        )
        source_complete = _coverage_complete(
            observation, context="", kind="selection"
        )
    elif operation == "module-owners":
        if not module:
            raise ValueError("module-owners query requires module")
        rows = [
            dict(row)
            for row in observation.get("module_ownership", ())
            if isinstance(row, Mapping)
            and str(row.get("module") or "") == module
            and (not context or str(row.get("context") or "") == context)
        ]
        result = _limited(rows, max_results=max_results, omissions=omissions)
        source_complete = _coverage_complete(
            observation, context=context, kind="module-ownership"
        )
        if not rows:
            negative_evidence = (
                "admissible-within-declared-scope"
                if source_complete
                else "not-admissible"
            )
    else:
        if not node_id:
            raise ValueError(f"{operation} query requires node_id")
        if node_id not in selections:
            raise ValueError(f"unknown dependency query node_id: {node_id}")
        source_complete = _coverage_complete(observation, context=context)
        outgoing, incoming = _adjacency(relationships)
        if operation in {"dependencies", "dependents"}:
            result, visited, omissions = _walk(
                node_id,
                outgoing if operation == "dependencies" else incoming,
                selections,
                max_depth=max_depth,
                max_results=max_results,
                max_visits=max_visits,
            )
            if not result:
                negative_evidence = (
                    "admissible-within-declared-scope"
                    if source_complete and not omissions
                    else "not-admissible"
                )
        elif operation == "reachability":
            if not target_id:
                raise ValueError("reachability query requires target_id")
            if target_id not in selections:
                raise ValueError(f"unknown dependency query target_id: {target_id}")
            found, visited, omissions = _reachability(
                node_id,
                target_id,
                outgoing,
                max_depth=max_depth,
                max_visits=max_visits,
            )
            result = {
                "reachable": found,
                "negative_evidence": (
                    "admissible-within-declared-scope"
                    if not found
                    and not omissions
                    and _coverage_complete(observation, context=context)
                    else "not-admissible"
                    if not found
                    else "not-applicable"
                ),
            }
        else:
            if not target_id:
                raise ValueError("paths query requires target_id")
            if target_id not in selections:
                raise ValueError(f"unknown dependency query target_id: {target_id}")
            result, visited, omissions = _paths(
                node_id,
                target_id,
                outgoing,
                max_depth=max_depth,
                max_results=max_results,
                max_visits=max_visits,
            )
            if not result:
                negative_evidence = (
                    "admissible-within-declared-scope"
                    if source_complete and not omissions
                    else "not-admissible"
                )

    return {
        "schema": "hashmarks.dependency-query-result.v1",
        "operation": operation,
        "context": context or None,
        "result": result,
        "bounds": {
            "max_depth": max_depth,
            "max_results": max_results,
            "max_visits": max_visits,
            "visited": visited,
        },
        "completeness": (
            "complete" if not omissions and source_complete else "incomplete"
        ),
        "negative_evidence": negative_evidence,
        "omissions": omissions,
        "authority": "qualified-external-observation",
        "causation": "not-inferred",
    }


def dependency_queries(
    observation: Mapping[str, object],
    requests: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    if not isinstance(requests, Sequence) or isinstance(
        requests, (str, bytes, bytearray)
    ):
        raise ValueError("dependency queries must be a sequence")
    if len(requests) > MAX_QUERIES:
        raise ValueError(f"dependency queries exceeds {MAX_QUERIES} entries")
    results = []
    for request in requests:
        if not isinstance(request, Mapping):
            raise ValueError("each dependency query must be an object")
        results.append(dependency_query(observation, request))
    return {
        "schema": "hashmarks.dependency-query-batch.v1",
        "observation_identity": observation.get("observation_identity"),
        "results": results,
        "authority": "qualified-external-observation",
        "causation": "not-inferred",
    }
