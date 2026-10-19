from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, TypeVar

from hashmarks._command_output import log_command_output

from .codemap.change_impact import (
    CHANGE_IMPACT_DEFAULT_REQUEST,
    ChangeImpactOptions,
)
from .codemap.context_defaults import REPOSITORY_CONTEXT_DEFAULTS
from .codemap.evidence_packet import TASK_EVIDENCE_DEFAULT_OPTIONS
from .codemap.find_engine import FIND_DEFAULT_OPTIONS
from .codemap.source_line_correspondence import validated_source_lines
from .codemap.verification_defaults import VERIFICATION_RELEVANCE_DEFAULTS
from .errors import RepositoryCliError
from .evidence_presentation import FORMATS, presentation_response
from .operation_contract import operation_default_mode, validate_operation_response
from .repository_retry import (
    is_transient_repository_race,
    retry_transient_repository_race,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace, _SubParsersAction
    from collections.abc import Callable

    from .codemap import CodeMap
    from .codemap.model import SyncResult


def _print(value: object, *, compact: bool = False) -> None:
    log_command_output(
        logger,
        json.dumps(
            value,
            indent=None if compact else 2,
            separators=(",", ":") if compact else None,
            sort_keys=True,
        ),
    )


def _print_operation(
    operation: str,
    value: object,
    *,
    mode: str | None = None,
    presentation: str = "none",
) -> None:
    native = validate_operation_response(operation, value, mode=mode)
    _print(
        presentation_response(operation, native, format=presentation, result_mode=mode),
        compact=presentation in {"compact", "text"},
    )


_T = TypeVar("_T")
_REPOSITORY_USER_ERRORS = (KeyError, PermissionError, ValueError, FileNotFoundError)


def _call_codemap(
    args: Namespace,
    operation: Callable[[CodeMap], _T],
    *,
    extra_errors: tuple[type[BaseException], ...] = (),
) -> _T:
    """Run one CodeMap request and translate expected failures at the CLI boundary."""

    try:
        with _codemap(args) as codemap:
            return retry_transient_repository_race(lambda: operation(codemap))
    except _REPOSITORY_USER_ERRORS + extra_errors as exc:
        raise RepositoryCliError(str(exc)) from exc
    except RuntimeError as exc:
        if not is_transient_repository_race(exc):
            raise
        raise RepositoryCliError(str(exc)) from exc


def _read_json_object(path: str | Path, *, option: str) -> dict[str, object]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RepositoryCliError(f"cannot read {option} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RepositoryCliError(f"{option} must contain one JSON object")
    return value


def _codemap(args: Namespace) -> CodeMap:
    # Lazy import is a performance firewall: identity/daemon commands do not
    # import parsing or agent-context code.
    from .codemap import CodeMap

    return CodeMap(args.workspace, state_dir=args.state_dir)


def _read_observation_request(
    args: Namespace, fields: frozenset[str]
) -> dict[str, object]:
    request = _read_json_object(args.input_json, option="--input-json")
    unexpected = sorted(set(request) - fields)
    if unexpected:
        raise RepositoryCliError(f"unknown observation input fields: {unexpected}")
    return request


def _request_mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RepositoryCliError(f"{name} must be a JSON object")
    return value


def _request_previous(value: object, name: str) -> dict[str, object] | None:
    return None if value is None else _request_mapping(value, name)


def _request_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise RepositoryCliError(f"{name} must be a string")
    return value


def _request_optional_text(value: object, name: str) -> str | None:
    return None if value is None else _request_text(value, name)


def _request_paths(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RepositoryCliError("changed_paths must be a JSON array")
    return [_request_text(path, "changed_paths member") for path in value]


def _request_queries(value: object) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RepositoryCliError("queries must be a JSON array")
    return [_request_mapping(row, "query") for row in value]


def _request_mappings(value: object, name: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise RepositoryCliError(f"{name} must be a JSON array")
    return [_request_mapping(row, f"{name} member") for row in value]


class _CorrelationOptions(TypedDict, total=False):
    path_mappings: list[dict[str, object]] | None
    relationship_limit_per_path: int
    include_relationships: bool
    previous_correlation: dict[str, object] | None


def _correlation_options(request: dict[str, object]) -> _CorrelationOptions:
    options: _CorrelationOptions = {}
    if "path_mappings" in request:
        value = request["path_mappings"]
        options["path_mappings"] = (
            None if value is None else _request_mappings(value, "path_mappings")
        )
    if "relationship_limit_per_path" in request:
        limit = request["relationship_limit_per_path"]
        if type(limit) is not int:
            raise RepositoryCliError("relationship_limit_per_path must be an integer")
        options["relationship_limit_per_path"] = limit
    if "include_relationships" in request:
        include = request["include_relationships"]
        if not isinstance(include, bool):
            raise RepositoryCliError("include_relationships must be a boolean")
        options["include_relationships"] = include
    if "previous_correlation" in request:
        options["previous_correlation"] = _request_previous(
            request["previous_correlation"], "previous_correlation"
        )
    return options


def _correlate_evidence_code(args: Namespace) -> int:
    request = _read_observation_request(
        args,
        frozenset({"bundles", *_CorrelationOptions.__annotations__}),
    )
    bundles = _request_mappings(request.get("bundles"), "bundles")
    options = _correlation_options(request)
    value = _call_codemap(
        args, lambda codemap: codemap.correlation.observe(bundles, **options)
    )
    _print_operation("correlate_evidence", value, presentation=args.presentation)
    return 0


def _dependency_codemap_code(args: Namespace) -> int:
    request = _read_observation_request(
        args, frozenset({"snapshot", "queries", "previous_observation", "result_mode"})
    )
    mode = _request_text(
        request.get("result_mode", operation_default_mode("dependency_codemap")),
        "result_mode",
    )
    snapshot = _request_mapping(request.get("snapshot"), "snapshot")
    queries = _request_queries(request.get("queries"))
    previous = _request_previous(
        request.get("previous_observation"), "previous_observation"
    )
    value = _call_codemap(
        args,
        lambda codemap: codemap.dependencies.codemap(
            snapshot, queries, previous_observation=previous, result_mode=mode
        ),
    )
    _print_operation(
        "dependency_codemap", value, mode=mode, presentation=args.presentation
    )
    return 0


def _repository_intelligence_query_code(args: Namespace) -> int:
    from .codemap.repository_intelligence_query import (
        REPOSITORY_INTELLIGENCE_QUERY_DEFAULT_OPTIONS,
        RepositoryIntelligenceQueryOptions,
    )

    request = _read_observation_request(
        args,
        frozenset(
            {
                "surface_name",
                "task",
                "changed_paths",
                "profile",
                "member_path",
                "previous_snapshot",
            }
        ),
    )
    surface = _request_text(request.get("surface_name"), "surface_name")
    task = _request_text(request.get("task"), "task")
    paths = _request_paths(request.get("changed_paths"))
    options = RepositoryIntelligenceQueryOptions(
        profile=_request_text(
            request.get(
                "profile", REPOSITORY_INTELLIGENCE_QUERY_DEFAULT_OPTIONS.profile
            ),
            "profile",
        ),
        member_path=_request_optional_text(request.get("member_path"), "member_path"),
        previous_snapshot=_request_previous(
            request.get("previous_snapshot"), "previous_snapshot"
        ),
        presentation=args.presentation,
    )
    value = _call_codemap(
        args,
        lambda codemap: codemap.views.query(surface, task, paths, options=options),
    )
    # The canonical query owns its presentation envelope, unlike other operations.
    native = validate_operation_response("repository_intelligence_query", value)
    _print(native, compact=args.presentation in {"compact", "text"})
    return 0


def _declaration_source_selection(args: Namespace) -> dict[str, object]:
    path_options = (
        args.python_backend_path,
        args.python_interface_json,
        args.make_path,
        args.shell_path,
        args.python_uv_manifest_path,
    )
    selected = any(value is not None for value in path_options)
    if args.source_selection_json is not None:
        if selected or args.include_class_fields:
            raise RepositoryCliError(
                "--source-selection-json cannot be combined with source selection flags"
            )
        return _read_json_object(
            args.source_selection_json, option="--source-selection-json"
        )
    if not selected:
        raise RepositoryCliError(
            "select --python-backend-path, --python-interface-json, --make-path, "
            "--shell-path, --python-uv-manifest-path or --source-selection-json"
        )
    return {
        "python_backend_paths": args.python_backend_path,
        "include_class_fields": args.include_class_fields,
        "python_interface": (
            _read_json_object(
                args.python_interface_json, option="--python-interface-json"
            )
            if args.python_interface_json is not None
            else None
        ),
        "make_shell": (
            {"make_paths": args.make_path or [], "shell_paths": args.shell_path or []}
            if args.make_path is not None or args.shell_path is not None
            else None
        ),
        "python_uv_manifest_paths": args.python_uv_manifest_path,
    }


def _repository_declarations_code(args: Namespace) -> int:
    from .codemap.repository_declaration_selection import source_declaration_providers

    selection = _declaration_source_selection(args)
    previous = (
        _read_json_object(args.previous_observation, option="--previous-observation")
        if args.previous_observation
        else None
    )
    value = _call_codemap(
        args,
        lambda codemap: codemap.declarations.operation(
            [],
            providers=source_declaration_providers("discovery", selection),
            previous_observation=previous,
            result_mode="discovery",
        ),
    )
    _print_operation(
        "repository_declarations",
        value,
        mode="discovery",
        presentation=args.presentation,
    )
    return 0


def _map_sync(args: Namespace) -> int:
    result = _call_codemap(args, lambda codemap: codemap.index.sync(args.path or None))
    _print(result.as_dict())
    return 0


def _map_findings(args: Namespace) -> int:
    value = _call_codemap(
        args, lambda codemap: codemap.ownership.findings(args.path or None)
    )
    _print_operation("repository_findings", value)
    return 0


def _map_import_ownership(args: Namespace) -> int:
    value = _call_codemap(
        args, lambda codemap: codemap.ownership.import_findings(args.path or None)
    )
    _print_operation("import_ownership", value)
    return 0


def _map_concurrency_risk(args: Namespace) -> int:
    value = _call_codemap(
        args, lambda codemap: codemap.ownership.concurrency_findings(args.path or None)
    )
    _print_operation("concurrency_risk", value)
    return 0


def _map_verification_ownership(args: Namespace) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.tasks.verification_ownership_graph(
            args.task, limit=args.limit, candidate_limit=args.candidate_limit
        ),
    )
    _print_operation("verification_ownership", value)
    return 0


def _map_repository_ownership(args: Namespace) -> int:
    value = _call_codemap(
        args, lambda codemap: codemap.ownership.repository_graph(args.path or None)
    )
    _print_operation("repository_ownership", value)
    return 0


def _map_cache_ownership(args: Namespace) -> int:
    value = _call_codemap(
        args, lambda codemap: codemap.ownership.cache_findings(args.path or None)
    )
    _print_operation("cache_ownership", value)
    return 0


def _map_cache_invalidation_ownership(args: Namespace) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.ownership.cache_invalidation_graph(args.path or None),
    )
    _print_operation("cache_invalidation_ownership", value)
    return 0


def _map_clean(args: Namespace) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.index.clean(shared_artifacts=args.shared_artifacts),
    )
    _print(value)
    return 0


def _map_watch(args: Namespace) -> int:
    def on_update(result: SyncResult, paths: list[str]) -> None:
        _print(
            {
                "event": "codemap_update",
                "paths": list(paths),
                "result": result.as_dict(),
            }
        )
        sys.stdout.flush()

    with _codemap(args) as codemap:
        codemap.index.watch_forever(debounce_seconds=args.debounce, on_update=on_update)
    return 0


def _map_status(args: Namespace) -> int:
    value = _call_codemap(args, lambda codemap: codemap.views.status())
    _print(value)
    return 0


def _map_enrich(args: Namespace) -> int:
    value = _call_codemap(
        args, lambda codemap: codemap.native.enrich_projects(args.provider or None)
    )
    _print(value)
    return 0


def _map_projects(args: Namespace) -> int:
    value = _call_codemap(args, lambda codemap: codemap.relationships.projects())
    _print_operation("projects", value)
    return 0


def _map_import_scip(args: Namespace) -> int:
    provenance = (
        _read_json_object(args.provenance, option="--provenance")
        if args.provenance
        else None
    )
    value = _call_codemap(
        args,
        lambda codemap: codemap.native.import_scip(args.path, provenance=provenance),
        extra_errors=(RuntimeError,),
    )
    _print(value)
    return 0


def _map_orient(args: Namespace) -> int:
    value = _call_codemap(args, lambda codemap: codemap.context.orient())
    _print_operation("repository_context", value)
    return 0


def _outline(args: Namespace) -> int:
    value = _call_codemap(args, lambda codemap: codemap.source.outline(args.path))
    _print_operation("outline", value)
    return 0


def _find_code(args: Namespace) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.search.packet(args.query, limit=args.limit),
    )
    _print_operation("find", value)
    return 0


def _grep_code(args: Namespace) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.source.grep(
            args.query, limit=args.limit, context_lines=args.context
        ),
    )
    _print_operation("grep", value)
    return 0


def _structural_code(args: Namespace) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.structure.search(
            args.pattern, language=args.lang, limit=args.limit
        ),
    )
    _print_operation("structural", value)
    return 0


def _symbol_code(args: Namespace) -> int:
    value = _call_codemap(args, lambda codemap: codemap.source.symbol(args.query))
    _print_operation("symbol", value)
    return 0


def _source_code(args: Namespace) -> int:
    value = _call_codemap(
        args, lambda codemap: codemap.source.read(args.query, token_budget=args.budget)
    )
    _print_operation("source", value)
    return 0


def _deps_code(args: Namespace) -> int:
    value = _call_codemap(args, lambda codemap: codemap.relationships.deps(args.query))
    _print(value)
    return 0


def _refs_code(args: Namespace) -> int:
    value = _call_codemap(args, lambda codemap: codemap.relationships.refs(args.query))
    _print(value)
    return 0


def _affected_code(args: Namespace) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.relationships.affected(
            args.query, max_depth=args.max_depth
        ),
    )
    _print_operation("affected", value)
    return 0


def _tests_code(args: Namespace) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.relationships.tests(
            args.query, max_depth=args.max_depth
        ),
    )
    _print_operation("tests", value)
    return 0


def _structural_locality_code(args: Namespace) -> int:
    supplied = _supplied_relationship_observations(args)
    value = _call_codemap(
        args,
        lambda codemap: codemap.structure.locality(
            args.target,
            max_depth=args.max_depth,
            call_limit_per_symbol=args.call_limit,
            ref_limit_per_symbol=args.ref_limit,
            result_mode=args.result_mode,
            supplied_observations=supplied,
        ),
    )
    _print_operation(
        "structural_locality",
        value,
        mode=args.result_mode,
        presentation=args.presentation,
    )
    return 0


def _structural_locality_delta_code(args: Namespace) -> int:
    from .codemap.structural_locality_delta import structural_locality_delta

    before = _read_json_object(args.before, option="--before")
    after = _read_json_object(args.after, option="--after")
    if args.result_mode == "relationships":
        from .codemap.semantic_relationship_delta import semantic_relationship_delta

        value = semantic_relationship_delta(before, after)
    else:
        value = structural_locality_delta(before, after)
    _print_operation(
        "structural_locality_delta",
        value,
        mode=args.result_mode,
        presentation=args.presentation,
    )
    return 0


def _context_code(args: Namespace) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.context.build(
            args.query,
            token_budget=args.budget,
            limit=args.limit,
            disclosure=args.level,
        ),
    )
    _print_operation("context", value.as_dict())
    return 0


def _task_evidence_code(args: Namespace) -> int:
    supplied = _supplied_relationship_observations(args)
    value = _call_codemap(
        args,
        lambda codemap: codemap.tasks.evidence(
            args.task,
            token_budget=args.budget,
            limit=args.limit,
            per_role=args.per_role,
            supplied_observations=supplied,
            result_mode=args.result_mode,
        ),
    )
    _print_operation(
        "task_evidence", value, presentation=args.presentation, mode=args.result_mode
    )
    return 0


def _supplied_relationship_observations(
    args: Namespace,
) -> list[dict[str, object]] | None:
    if not args.supplied_observations:
        return None
    value = _read_json_object(
        args.supplied_observations, option="--supplied-observations"
    )
    if set(value) != {"observations"} or not isinstance(value["observations"], list):
        raise ValueError(
            "--supplied-observations requires an object containing observations"
        )
    return value["observations"]


def _verification_relevance_code(args: Namespace) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.tasks.verification_relevance(
            args.task, limit=args.limit, candidate_limit=args.candidate_limit
        ),
    )
    _print_operation("verification_relevance", value)
    return 0


def _changed_line_span_args(values: list[str] | None) -> list[dict[str, object]] | None:
    if values is None:
        return None
    rows: list[dict[str, object]] = []
    for value in values:
        parts = value.rsplit(":", 2)
        if len(parts) != 3:
            raise ValueError("--changed-line-span requires PATH:START:END")
        path, start, end = parts
        if not start.isdecimal() or not end.isdecimal():
            raise ValueError("--changed-line-span requires positive integer bounds")
        rows.append({"path": path, "start_line": int(start), "end_line": int(end)})
    return rows


def _change_impact_code(args: Namespace) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.changes.task_impact(
            args.task,
            args.changed,
            limit=args.limit,
            per_role=args.per_role,
            options=ChangeImpactOptions(
                impact_limit_per_surface=args.impact_limit,
                max_depth=args.max_depth,
                project_impact_limit=args.project_impact_limit,
                project_impact_encoding=args.project_impact_encoding,
                changed_line_spans=_changed_line_span_args(args.changed_line_span),
            ),
        ),
    )
    _print_operation("change_impact", value, presentation=args.presentation)
    return 0


def _post_change_code(args: Namespace) -> int:
    previous = _read_json_object(args.previous_evidence, option="--previous-evidence")
    value = _call_codemap(
        args,
        lambda codemap: codemap.changes.task_delta(
            args.task,
            args.changed,
            previous_evidence=previous,
            token_budget=args.budget,
            limit=args.limit,
            per_role=args.per_role,
        ),
    )
    _print_operation("post_change", value, presentation=args.presentation)
    return 0


def _source_observation_code(args: Namespace) -> int:
    requested = validated_source_lines(args.line or ())
    mode = args.result_mode
    options = _source_observation_options(args)

    def observe(codemap: CodeMap) -> object:
        codemap.index.sync([args.path])
        if mode == "range":
            return codemap.source.range_receipt(
                args.path,
                start_byte=args.start_byte,
                end_byte=args.end_byte,
                **options,
            )
        if mode == "ecmascript":
            return codemap.source.ecmascript(args.path, **options)
        return codemap.source.observe(
            args.path,
            lines=requested,
            anchor_context_lines=1 if requested else 0,
        )

    value = _call_codemap(args, observe)
    _print_operation(
        "source_observation", value, mode=mode, presentation=args.presentation
    )
    return 0


def _source_observation_options(args: Namespace) -> dict[str, int]:
    if args.result_mode != "member" and args.line:
        raise RepositoryCliError("--line requires member mode")
    if args.result_mode == "range":
        if args.start_byte is None or args.end_byte is None:
            raise RepositoryCliError("range mode requires --start-byte and --end-byte")
    elif args.start_byte is not None or args.end_byte is not None:
        raise RepositoryCliError("byte coordinates require range mode")
    if args.limit is not None and args.result_mode != "ecmascript":
        raise RepositoryCliError("--limit requires ecmascript mode")
    if args.max_bytes is not None and args.result_mode == "member":
        raise RepositoryCliError("--max-bytes requires range or ecmascript mode")
    return {
        name: value
        for name, value in (("max_bytes", args.max_bytes), ("limit", args.limit))
        if value is not None
    }


def _verification_membership_code(args: Namespace) -> int:
    report = _read_json_object(args.input_json, option="--input-json")

    def observe(codemap: CodeMap) -> dict[str, object]:
        codemap.index.sync()
        return codemap.verification.observe_membership(report)

    value = _call_codemap(args, observe)
    _print_operation("verification_membership", value, presentation=args.presentation)
    return 0


def _add_evidence_presentation_cli(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--presentation",
        choices=FORMATS,
        default="none",
        help="optional evidence projection alongside canonical JSON",
    )


def _add_source_observation_cli(
    sub: _SubParsersAction[ArgumentParser], *, add_common_arguments: Callable[..., None]
) -> None:
    source = sub.add_parser(
        "source-observation",
        help="observe one member, exact byte range, or ECMAScript syntax",
    )
    add_common_arguments(source, inherited=True)
    _add_evidence_presentation_cli(source)
    source.add_argument("path")
    source.add_argument(
        "--result-mode", choices=("member", "range", "ecmascript"), default="member"
    )
    source.add_argument(
        "--start-byte", type=int, help="zero-based inclusive byte start"
    )
    source.add_argument("--end-byte", type=int, help="zero-based exclusive byte end")
    source.add_argument(
        "--max-bytes", type=int, help="maximum full source member bytes"
    )
    source.add_argument("--limit", type=int, help="maximum ECMAScript syntax facts")
    source.add_argument(
        "--line", type=int, action="append", help="1-based source line; repeatable"
    )
    source.set_defaults(func=_source_observation_code, automatic_update_check=True)


def _add_map_cli(
    sub: _SubParsersAction[ArgumentParser], *, add_common_arguments: Callable[..., None]
) -> None:
    map_cmd = sub.add_parser("map", help="derived repository CodeMap")
    add_common_arguments(map_cmd, inherited=True)
    map_sub = map_cmd.add_subparsers(dest="map_command", required=True)
    map_sync = map_sub.add_parser(
        "sync", help="index repository structure; use --path for incremental updates"
    )
    add_common_arguments(map_sync, inherited=True)
    map_sync.add_argument(
        "--path", action="append", help="changed path to reindex; repeatable"
    )
    map_sync.set_defaults(func=_map_sync, automatic_update_check=True)
    map_status = map_sub.add_parser("status", help="show CodeMap generation/staleness")
    add_common_arguments(map_status, inherited=True)
    map_status.set_defaults(func=_map_status, automatic_update_check=True)
    _add_map_ownership_cli(map_sub, add_common_arguments=add_common_arguments)
    _add_map_enrichment_cli(map_sub, add_common_arguments=add_common_arguments)


def _add_map_ownership_cli(
    map_sub: _SubParsersAction[ArgumentParser],
    *,
    add_common_arguments: Callable[..., None],
) -> None:
    map_findings = map_sub.add_parser(
        "findings",
        help="project actionable repository-analysis findings from existing analyzers",
    )
    add_common_arguments(map_findings, inherited=True)
    map_findings.add_argument(
        "--path",
        action="append",
        help="workspace-relative path scope; repeatable (default: analyzer-nominated repository candidates)",
    )
    map_findings.set_defaults(func=_map_findings, automatic_update_check=True)
    map_import_ownership = map_sub.add_parser(
        "import-ownership",
        help="report Python loaders that bypass normal module/cache ownership",
    )
    add_common_arguments(map_import_ownership, inherited=True)
    map_import_ownership.add_argument(
        "--path",
        action="append",
        help="workspace-relative Python path to inspect; repeatable (default: CodeMap-nominated candidates)",
    )
    map_import_ownership.set_defaults(
        func=_map_import_ownership, automatic_update_check=True
    )
    map_cache_ownership = map_sub.add_parser(
        "cache-ownership",
        help="report process-local Python cache owners and invalidation evidence",
    )
    add_common_arguments(map_cache_ownership, inherited=True)
    map_cache_ownership.add_argument(
        "--path",
        action="append",
        help="workspace-relative Python path to inspect; repeatable (default: CodeMap-nominated candidates)",
    )
    map_cache_ownership.set_defaults(
        func=_map_cache_ownership, automatic_update_check=True
    )
    map_cache_invalidation = map_sub.add_parser(
        "cache-invalidation-ownership",
        help="resolve static Python cache invalidators to exact repository cache owners",
    )
    add_common_arguments(map_cache_invalidation, inherited=True)
    map_cache_invalidation.add_argument(
        "--path",
        action="append",
        help="workspace-relative Python invalidator path to inspect; repeatable (default: all indexed Python)",
    )
    map_cache_invalidation.set_defaults(
        func=_map_cache_invalidation_ownership, automatic_update_check=True
    )
    map_authority_ownership = map_sub.add_parser(
        "authority-ownership",
        help="compose repository owner/reader/cache/import authority evidence",
    )
    add_common_arguments(map_authority_ownership, inherited=True)
    map_authority_ownership.add_argument(
        "--path", action="append", help="workspace-relative path scope; repeatable"
    )
    map_authority_ownership.set_defaults(
        func=_map_repository_ownership, automatic_update_check=True
    )
    map_concurrency_risk = map_sub.add_parser(
        "concurrency-risk", help="nominate static read-modify-write concurrency risks"
    )
    add_common_arguments(map_concurrency_risk, inherited=True)
    map_concurrency_risk.add_argument(
        "--path", action="append", help="workspace-relative Python path; repeatable"
    )
    map_concurrency_risk.set_defaults(
        func=_map_concurrency_risk, automatic_update_check=True
    )
    map_verification_ownership = map_sub.add_parser(
        "verification-ownership", help="map task-local verification evidence owners"
    )
    add_common_arguments(map_verification_ownership, inherited=True)
    map_verification_ownership.add_argument("task")
    map_verification_ownership.add_argument(
        "--limit", type=int, default=VERIFICATION_RELEVANCE_DEFAULTS.limit
    )
    map_verification_ownership.add_argument(
        "--candidate-limit",
        type=int,
        default=VERIFICATION_RELEVANCE_DEFAULTS.candidate_limit,
    )
    map_verification_ownership.set_defaults(
        func=_map_verification_ownership, automatic_update_check=True
    )


def _add_map_enrichment_cli(
    map_sub: _SubParsersAction[ArgumentParser],
    *,
    add_common_arguments: Callable[..., None],
) -> None:
    map_enrich = map_sub.add_parser(
        "enrich", help="collect slower/native package graph evidence explicitly"
    )
    add_common_arguments(map_enrich, inherited=True)
    map_enrich.add_argument(
        "--provider",
        action="append",
        choices=(
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
        ),
        help="native/manifest evidence provider to run; repeatable",
    )
    map_enrich.set_defaults(func=_map_enrich, automatic_update_check=True)
    map_projects = map_sub.add_parser(
        "projects", help="show retained native/manifest package graph"
    )
    add_common_arguments(map_projects, inherited=True)
    map_projects.set_defaults(func=_map_projects, automatic_update_check=True)
    map_scip = map_sub.add_parser(
        "import-scip",
        help="import an existing SCIP index/JSON as native code-intelligence evidence",
    )
    add_common_arguments(map_scip, inherited=True)
    map_scip.add_argument("path")
    map_scip.add_argument(
        "--provenance",
        help="JSON file containing producer-owned source, capability and collection claims",
    )
    map_scip.set_defaults(func=_map_import_scip, automatic_update_check=True)
    map_clean = map_sub.add_parser("clean", help="clear workspace CodeMap state")
    add_common_arguments(map_clean, inherited=True)
    map_clean.add_argument(
        "--shared-artifacts",
        action="store_true",
        help="also purge content-addressed worktree-shared parse artifacts",
    )
    map_clean.set_defaults(func=_map_clean, automatic_update_check=True)
    map_watch = map_sub.add_parser(
        "watch", help="maintain CodeMap from filesystem changes in a separate process"
    )
    add_common_arguments(map_watch, inherited=True)
    map_watch.add_argument("--debounce", type=float, default=0.05)
    map_watch.set_defaults(func=_map_watch, automatic_update_check=True)


def _add_navigation_cli(
    sub: _SubParsersAction[ArgumentParser], *, add_common_arguments: Callable[..., None]
) -> None:
    orient = sub.add_parser("orient", help="compact repository capsule")
    add_common_arguments(orient, inherited=True)
    orient.set_defaults(func=_map_orient, automatic_update_check=True)

    outline = sub.add_parser(
        "outline", help="show structure/signatures without full implementation bodies"
    )
    add_common_arguments(outline, inherited=True)
    outline.add_argument("path")
    outline.set_defaults(func=_outline, automatic_update_check=True)

    find_code = sub.add_parser("find", help="search the maintained path/symbol index")
    add_common_arguments(find_code, inherited=True)
    find_code.add_argument("query")
    find_code.add_argument("--limit", type=int, default=FIND_DEFAULT_OPTIONS.limit)
    find_code.set_defaults(func=_find_code, automatic_update_check=True)

    grep_code = sub.add_parser(
        "grep", help="persistent lexical grep narrowed by CodeMap"
    )
    add_common_arguments(grep_code, inherited=True)
    grep_code.add_argument("query")
    grep_code.add_argument("--limit", type=int, default=50)
    grep_code.add_argument(
        "--context", type=int, default=0, help="source context lines around each match"
    )
    grep_code.set_defaults(func=_grep_code, automatic_update_check=True)


def _add_graph_cli(
    sub: _SubParsersAction[ArgumentParser], *, add_common_arguments: Callable[..., None]
) -> None:
    structural_code = sub.add_parser(
        "structural", help="optional syntax-aware search via local ast-grep"
    )
    add_common_arguments(structural_code, inherited=True)
    structural_code.add_argument("pattern")
    structural_code.add_argument("--lang")
    structural_code.add_argument("--limit", type=int, default=100)
    structural_code.set_defaults(func=_structural_code, automatic_update_check=True)

    for name, help_text, handler in (
        ("symbol", "show matching symbol records", _symbol_code),
        ("deps", "show static dependency/call evidence", _deps_code),
        ("refs", "show static references/calls to a symbol name", _refs_code),
    ):
        query_command = sub.add_parser(name, help=help_text)
        add_common_arguments(query_command, inherited=True)
        query_command.add_argument("query")
        query_command.set_defaults(func=handler, automatic_update_check=True)

    source_code = sub.add_parser(
        "source", help="return one exact symbol body under an explicit token budget"
    )
    add_common_arguments(source_code, inherited=True)
    source_code.add_argument("query", help="symbol name or path::qualname")
    source_code.add_argument("--budget", type=int, default=4000)
    source_code.set_defaults(func=_source_code, automatic_update_check=True)

    affected_code = sub.add_parser(
        "affected", help="show reverse file dependents from the CodeMap graph"
    )
    add_common_arguments(affected_code, inherited=True)
    affected_code.add_argument("query")
    affected_code.add_argument("--max-depth", type=int, default=12)
    affected_code.set_defaults(func=_affected_code, automatic_update_check=True)

    tests_code = sub.add_parser(
        "tests", help="show structurally related tests from reverse dependencies"
    )
    add_common_arguments(tests_code, inherited=True)
    tests_code.add_argument("query")
    tests_code.add_argument("--max-depth", type=int, default=12)
    tests_code.set_defaults(func=_tests_code, automatic_update_check=True)

    _add_structural_locality_cli(sub, add_common_arguments=add_common_arguments)


def _add_structural_locality_cli(
    sub: _SubParsersAction[ArgumentParser], *, add_common_arguments: Callable[..., None]
) -> None:
    locality = sub.add_parser(
        "structural-locality",
        help="project bounded structural locality facts for one exact path::qualname",
    )
    add_common_arguments(locality, inherited=True)
    _add_evidence_presentation_cli(locality)
    locality.add_argument("target", help="exact repository-relative path::qualname")
    locality.add_argument("--max-depth", type=int, default=2)
    locality.add_argument("--call-limit", type=int, default=64)
    locality.add_argument("--ref-limit", type=int, default=256)
    locality.add_argument(
        "--result-mode", choices=("default", "relationships"), default="default"
    )
    locality.add_argument(
        "--supplied-observations", help="JSON file containing captured LSP observations"
    )
    locality.set_defaults(func=_structural_locality_code, automatic_update_check=True)

    locality_delta = sub.add_parser(
        "structural-locality-delta",
        help="compare two structural-locality evidence packets without policy",
    )
    add_common_arguments(locality_delta, inherited=True)
    _add_evidence_presentation_cli(locality_delta)
    locality_delta.add_argument("--before", required=True)
    locality_delta.add_argument("--after", required=True)
    locality_delta.add_argument(
        "--result-mode", choices=("default", "relationships"), default="default"
    )
    locality_delta.set_defaults(
        func=_structural_locality_delta_code, automatic_update_check=True
    )


def _add_context_cli(
    sub: _SubParsersAction[ArgumentParser], *, add_common_arguments: Callable[..., None]
) -> None:
    context_code = sub.add_parser(
        "context", help="build a token-budgeted repository context pack"
    )
    add_common_arguments(context_code, inherited=True)
    context_code.add_argument("query")
    context_code.add_argument(
        "--budget",
        type=int,
        default=REPOSITORY_CONTEXT_DEFAULTS.token_budget,
    )
    context_code.add_argument(
        "--limit",
        type=int,
        default=REPOSITORY_CONTEXT_DEFAULTS.limit,
    )
    context_code.add_argument(
        "--level",
        choices=("orient", "outline", "evidence", "source"),
        default=REPOSITORY_CONTEXT_DEFAULTS.disclosure.value,
        help="progressive disclosure level; source preserves the pre-0.10.12 behavior",
    )
    context_code.set_defaults(func=_context_code, automatic_update_check=True)


def _add_task_evidence_cli(
    sub: _SubParsersAction[ArgumentParser], *, add_common_arguments: Callable[..., None]
) -> None:
    task_evidence = sub.add_parser(
        "task-evidence",
        help="resolve one task into bounded edit/verify/source repository evidence",
    )
    add_common_arguments(task_evidence, inherited=True)
    _add_evidence_presentation_cli(task_evidence)
    task_evidence.add_argument("task")
    task_evidence.add_argument(
        "--result-mode", choices=("default", "initial"), default="default"
    )
    task_evidence.add_argument(
        "--supplied-observations", help="JSON file containing captured LSP observations"
    )
    task_evidence.add_argument(
        "--budget",
        type=int,
        default=TASK_EVIDENCE_DEFAULT_OPTIONS.token_budget,
        help="maximum estimated tokens of source evidence",
    )
    task_evidence.add_argument(
        "--limit", type=int, default=TASK_EVIDENCE_DEFAULT_OPTIONS.limit
    )
    task_evidence.add_argument(
        "--per-role", type=int, default=TASK_EVIDENCE_DEFAULT_OPTIONS.per_role
    )
    task_evidence.set_defaults(func=_task_evidence_code, automatic_update_check=True)

    verification_relevance = sub.add_parser(
        "verification-relevance",
        help="rank bounded deterministic verification surfaces for an external consumer",
    )
    add_common_arguments(verification_relevance, inherited=True)
    verification_relevance.add_argument("task")
    verification_relevance.add_argument(
        "--limit", type=int, default=VERIFICATION_RELEVANCE_DEFAULTS.limit
    )
    verification_relevance.add_argument(
        "--candidate-limit",
        type=int,
        default=VERIFICATION_RELEVANCE_DEFAULTS.candidate_limit,
    )
    verification_relevance.set_defaults(
        func=_verification_relevance_code, automatic_update_check=True
    )


def _add_change_cli(
    sub: _SubParsersAction[ArgumentParser], *, add_common_arguments: Callable[..., None]
) -> None:
    change_impact = sub.add_parser(
        "change-impact",
        help="expose bounded changed-code impact and verification relevance",
    )
    add_common_arguments(change_impact, inherited=True)
    _add_evidence_presentation_cli(change_impact)
    change_impact.add_argument("task")
    change_impact.add_argument(
        "--changed",
        action="append",
        required=True,
        help="repository-relative changed path; repeatable",
    )
    change_impact.add_argument(
        "--changed-line-span",
        action="append",
        metavar="PATH:START:END",
        help="explicit 1-based inclusive source lines; repeatable, requires --changed",
    )
    defaults = CHANGE_IMPACT_DEFAULT_REQUEST
    options = defaults.options
    change_impact.add_argument("--limit", type=int, default=defaults.limit)
    change_impact.add_argument("--per-role", type=int, default=defaults.per_role)
    change_impact.add_argument(
        "--impact-limit",
        type=int,
        default=options.impact_limit_per_surface,
        help="maximum affected paths per surface",
    )
    change_impact.add_argument("--max-depth", type=int, default=options.max_depth)
    change_impact.add_argument(
        "--project-impact-limit",
        type=int,
        help="independent maximum affected-project provenance rows",
    )
    change_impact.add_argument(
        "--project-impact-encoding",
        choices=("verbose", "compact"),
        default=options.project_impact_encoding,
        help="project provenance transport encoding",
    )
    change_impact.set_defaults(func=_change_impact_code, automatic_update_check=True)

    post_change = sub.add_parser(
        "post-change",
        help="refresh reported changed paths and emit changed/reusable repository evidence",
    )
    add_common_arguments(post_change, inherited=True)
    _add_evidence_presentation_cli(post_change)
    post_change.add_argument("task")
    post_change.add_argument(
        "--changed",
        action="append",
        required=True,
        help="repository-relative changed path; repeatable",
    )
    post_change.add_argument(
        "--previous-evidence",
        required=True,
        help="JSON file containing the exact prior task-evidence packet",
    )
    post_change.add_argument(
        "--budget",
        type=int,
        default=TASK_EVIDENCE_DEFAULT_OPTIONS.token_budget,
    )
    post_change.add_argument(
        "--limit",
        type=int,
        default=TASK_EVIDENCE_DEFAULT_OPTIONS.limit,
    )
    post_change.add_argument(
        "--per-role",
        type=int,
        default=TASK_EVIDENCE_DEFAULT_OPTIONS.per_role,
    )
    post_change.set_defaults(func=_post_change_code, automatic_update_check=True)


def add_repository_cli(
    sub: _SubParsersAction[ArgumentParser], *, add_common_arguments: Callable[..., None]
) -> None:
    """Register repository-intelligence CLI families without owning top-level CLI policy."""
    _add_map_cli(sub, add_common_arguments=add_common_arguments)
    _add_navigation_cli(sub, add_common_arguments=add_common_arguments)
    _add_graph_cli(sub, add_common_arguments=add_common_arguments)
    _add_context_cli(sub, add_common_arguments=add_common_arguments)
    _add_task_evidence_cli(sub, add_common_arguments=add_common_arguments)
    _add_change_cli(sub, add_common_arguments=add_common_arguments)
    _add_source_observation_cli(sub, add_common_arguments=add_common_arguments)
    _add_json_observation_cli(sub, add_common_arguments=add_common_arguments)
    declarations = sub.add_parser(
        "repository-declarations",
        help="observe declarations in explicitly selected repository source files",
    )
    add_common_arguments(declarations, inherited=True)
    _add_evidence_presentation_cli(declarations)
    declarations.add_argument("--python-backend-path", action="append", metavar="PATH")
    declarations.add_argument(
        "--python-interface-json",
        metavar="FILE",
        help="JSON object selecting interface paths, receiver names and syntax options",
    )
    declarations.add_argument("--include-class-fields", action="store_true")
    declarations.add_argument("--make-path", action="append", metavar="PATH")
    declarations.add_argument("--shell-path", action="append", metavar="PATH")
    declarations.add_argument(
        "--python-uv-manifest-path", action="append", metavar="PATH"
    )
    declarations.add_argument(
        "--source-selection-json",
        metavar="FILE",
        help="JSON object selecting registered source providers; replaces selection flags",
    )
    declarations.add_argument(
        "--previous-observation", help="JSON file containing the prior discovery packet"
    )
    declarations.set_defaults(
        func=_repository_declarations_code, automatic_update_check=True
    )


def _add_json_observation_cli(
    sub: _SubParsersAction[ArgumentParser], *, add_common_arguments: Callable[..., None]
) -> None:
    for name, handler, description in (
        (
            "verification-membership",
            _verification_membership_code,
            "bind a supplied verification membership report to repository sources",
        ),
        (
            "correlate-evidence",
            _correlate_evidence_code,
            "correlate caller-supplied evidence with repository sources",
        ),
        (
            "dependency-codemap",
            _dependency_codemap_code,
            "observe caller-supplied dependency evidence",
        ),
        (
            "repository-intelligence-query",
            _repository_intelligence_query_code,
            "observe a bounded repository-intelligence surface",
        ),
    ):
        command = sub.add_parser(name, help=description)
        add_common_arguments(command, inherited=True)
        _add_evidence_presentation_cli(command)
        command.add_argument("--input-json", required=True, metavar="FILE")
        command.set_defaults(func=handler, automatic_update_check=True)
