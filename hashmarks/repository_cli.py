from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from hashmarks._command_output import log_command_output

from .codemap.change_impact import ChangeImpactOptions
from .errors import RepositoryCliError
from .repository_retry import (
    is_transient_repository_race,
    retry_transient_repository_race,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable


def _print(value) -> None:
    log_command_output(logger, json.dumps(value, indent=2, sort_keys=True))


_T = TypeVar("_T")
_REPOSITORY_USER_ERRORS = (KeyError, PermissionError, ValueError, FileNotFoundError)


def _call_codemap(
    args,
    operation: Callable[[object], _T],
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


def _codemap(args):
    # Lazy import is a performance firewall: identity/daemon commands do not
    # import parsing or agent-context code.
    from .codemap import CodeMap

    return CodeMap(args.workspace, state_dir=args.state_dir)


def _map_sync(args) -> int:
    result = _call_codemap(args, lambda codemap: codemap.sync(args.path or None))
    _print(result.as_dict())
    return 0


def _map_findings(args) -> int:
    value = _call_codemap(
        args, lambda codemap: codemap.repository_findings(args.path or None)
    )
    _print(value)
    return 0


def _map_import_ownership(args) -> int:
    value = _call_codemap(
        args, lambda codemap: codemap.import_ownership_findings(args.path or None)
    )
    _print(value)
    return 0


def _map_concurrency_risk(args) -> int:
    value = _call_codemap(
        args, lambda codemap: codemap.concurrency_risk_findings(args.path or None)
    )
    _print(value)
    return 0


def _map_verification_ownership(args) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.verification_ownership_graph(
            args.task, limit=args.limit, candidate_limit=args.candidate_limit
        ),
    )
    _print(value)
    return 0


def _map_repository_ownership(args) -> int:
    value = _call_codemap(
        args, lambda codemap: codemap.repository_ownership_graph(args.path or None)
    )
    _print(value)
    return 0


def _map_cache_ownership(args) -> int:
    value = _call_codemap(
        args, lambda codemap: codemap.cache_ownership_findings(args.path or None)
    )
    _print(value)
    return 0


def _map_cache_invalidation_ownership(args) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.cache_invalidation_ownership_graph(args.path or None),
    )
    _print(value)
    return 0


def _map_clean(args) -> int:
    value = _call_codemap(
        args, lambda codemap: codemap.clean(shared_artifacts=args.shared_artifacts)
    )
    _print(value)
    return 0


def _map_watch(args) -> int:
    def on_update(result, paths):
        _print(
            {
                "event": "codemap_update",
                "paths": list(paths),
                "result": result.as_dict(),
            }
        )
        sys.stdout.flush()

    with _codemap(args) as codemap:
        codemap.watch_forever(debounce_seconds=args.debounce, on_update=on_update)
    return 0


def _map_status(args) -> int:
    value = _call_codemap(args, lambda codemap: codemap.status())
    _print(value)
    return 0


def _map_enrich(args) -> int:
    value = _call_codemap(
        args, lambda codemap: codemap.enrich_projects(args.provider or None)
    )
    _print(value)
    return 0


def _map_projects(args) -> int:
    value = _call_codemap(args, lambda codemap: codemap.projects())
    _print(value)
    return 0


def _map_import_scip(args) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.import_scip(args.path),
        extra_errors=(RuntimeError,),
    )
    _print(value)
    return 0


def _map_orient(args) -> int:
    value = _call_codemap(args, lambda codemap: codemap.orient())
    _print(value)
    return 0


def _outline(args) -> int:
    value = _call_codemap(args, lambda codemap: codemap.outline(args.path))
    _print(value)
    return 0


def _find_code(args) -> int:
    hits, status = _call_codemap(
        args,
        lambda codemap: (codemap.find(args.query, limit=args.limit), codemap.status()),
    )
    _print(
        {
            "schema": "hashmarks.find.v1",
            "query": args.query,
            "generation": status["generation"],
            "stale": status["daemon_generation_changed"],
            "hits": [hit.as_dict() for hit in hits],
        }
    )
    return 0


def _grep_code(args) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.grep(
            args.query, limit=args.limit, context_lines=args.context
        ),
    )
    _print(value)
    return 0


def _structural_code(args) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.structural(
            args.pattern, language=args.lang, limit=args.limit
        ),
    )
    _print(value)
    return 0


def _symbol_code(args) -> int:
    value = _call_codemap(args, lambda codemap: codemap.symbol(args.query))
    _print(value)
    return 0


def _source_code(args) -> int:
    value = _call_codemap(
        args, lambda codemap: codemap.source(args.query, token_budget=args.budget)
    )
    _print(value)
    return 0


def _deps_code(args) -> int:
    value = _call_codemap(args, lambda codemap: codemap.deps(args.query))
    _print(value)
    return 0


def _refs_code(args) -> int:
    value = _call_codemap(args, lambda codemap: codemap.refs(args.query))
    _print(value)
    return 0


def _affected_code(args) -> int:
    value = _call_codemap(
        args, lambda codemap: codemap.affected(args.query, max_depth=args.max_depth)
    )
    _print(value)
    return 0


def _tests_code(args) -> int:
    value = _call_codemap(
        args, lambda codemap: codemap.tests(args.query, max_depth=args.max_depth)
    )
    _print(value)
    return 0


def _structural_locality_code(args) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.structural_locality(
            args.target,
            max_depth=args.max_depth,
            call_limit_per_symbol=args.call_limit,
            ref_limit_per_symbol=args.ref_limit,
        ),
    )
    _print(value)
    return 0


def _structural_locality_delta_code(args) -> int:
    from .codemap import structural_locality_delta

    before = _read_json_object(args.before, option="--before")
    after = _read_json_object(args.after, option="--after")
    _print(structural_locality_delta(before, after))
    return 0


def _context_code(args) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.context(
            args.query,
            token_budget=args.budget,
            limit=args.limit,
            disclosure=args.level,
        ),
    )
    _print(value.as_dict())
    return 0


def _task_evidence_code(args) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.task_evidence(
            args.task,
            token_budget=args.budget,
            limit=args.limit,
            per_role=args.per_role,
        ),
    )
    _print(value)
    return 0


def _verification_relevance_code(args) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.verification_relevance(
            args.task, limit=args.limit, candidate_limit=args.candidate_limit
        ),
    )
    _print(value)
    return 0


def _change_impact_code(args) -> int:
    value = _call_codemap(
        args,
        lambda codemap: codemap.task_change_impact(
            args.task,
            args.changed,
            limit=args.limit,
            per_role=args.per_role,
            options=ChangeImpactOptions(
                impact_limit_per_surface=args.impact_limit,
                max_depth=args.max_depth,
                project_impact_limit=args.project_impact_limit,
                project_impact_encoding=args.project_impact_encoding,
            ),
        ),
    )
    _print(value)
    return 0


def _post_change_code(args) -> int:
    previous = _read_json_object(args.previous_evidence, option="--previous-evidence")
    value = _call_codemap(
        args,
        lambda codemap: codemap.task_post_change_delta(
            args.task,
            args.changed,
            previous_evidence=previous,
            token_budget=args.budget,
            limit=args.limit,
            per_role=args.per_role,
        ),
    )
    _print(value)
    return 0


def _add_map_cli(sub, *, add_common_arguments: Callable[..., None]) -> None:
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
    map_sync.set_defaults(func=_map_sync)
    map_status = map_sub.add_parser("status", help="show CodeMap generation/staleness")
    add_common_arguments(map_status, inherited=True)
    map_status.set_defaults(func=_map_status)
    _add_map_ownership_cli(map_sub, add_common_arguments=add_common_arguments)
    _add_map_enrichment_cli(map_sub, add_common_arguments=add_common_arguments)


def _add_map_ownership_cli(
    map_sub, *, add_common_arguments: Callable[..., None]
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
    map_findings.set_defaults(func=_map_findings)
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
    map_import_ownership.set_defaults(func=_map_import_ownership)
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
    map_cache_ownership.set_defaults(func=_map_cache_ownership)
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
    map_cache_invalidation.set_defaults(func=_map_cache_invalidation_ownership)
    map_authority_ownership = map_sub.add_parser(
        "authority-ownership",
        help="compose repository owner/reader/cache/import authority evidence",
    )
    add_common_arguments(map_authority_ownership, inherited=True)
    map_authority_ownership.add_argument(
        "--path", action="append", help="workspace-relative path scope; repeatable"
    )
    map_authority_ownership.set_defaults(func=_map_repository_ownership)
    map_concurrency_risk = map_sub.add_parser(
        "concurrency-risk", help="nominate static read-modify-write concurrency risks"
    )
    add_common_arguments(map_concurrency_risk, inherited=True)
    map_concurrency_risk.add_argument(
        "--path", action="append", help="workspace-relative Python path; repeatable"
    )
    map_concurrency_risk.set_defaults(func=_map_concurrency_risk)
    map_verification_ownership = map_sub.add_parser(
        "verification-ownership", help="map task-local verification evidence owners"
    )
    add_common_arguments(map_verification_ownership, inherited=True)
    map_verification_ownership.add_argument("task")
    map_verification_ownership.add_argument("--limit", type=int, default=20)
    map_verification_ownership.add_argument("--candidate-limit", type=int, default=8)
    map_verification_ownership.set_defaults(func=_map_verification_ownership)


def _add_map_enrichment_cli(
    map_sub, *, add_common_arguments: Callable[..., None]
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
    map_enrich.set_defaults(func=_map_enrich)
    map_projects = map_sub.add_parser(
        "projects", help="show retained native/manifest package graph"
    )
    add_common_arguments(map_projects, inherited=True)
    map_projects.set_defaults(func=_map_projects)
    map_scip = map_sub.add_parser(
        "import-scip",
        help="import an existing SCIP index/JSON as native code-intelligence evidence",
    )
    add_common_arguments(map_scip, inherited=True)
    map_scip.add_argument("path")
    map_scip.set_defaults(func=_map_import_scip)
    map_clean = map_sub.add_parser("clean", help="clear workspace CodeMap state")
    add_common_arguments(map_clean, inherited=True)
    map_clean.add_argument(
        "--shared-artifacts",
        action="store_true",
        help="also purge content-addressed worktree-shared parse artifacts",
    )
    map_clean.set_defaults(func=_map_clean)
    map_watch = map_sub.add_parser(
        "watch", help="maintain CodeMap from filesystem changes in a separate process"
    )
    add_common_arguments(map_watch, inherited=True)
    map_watch.add_argument("--debounce", type=float, default=0.05)
    map_watch.set_defaults(func=_map_watch)


def _add_navigation_cli(sub, *, add_common_arguments: Callable[..., None]) -> None:
    orient = sub.add_parser("orient", help="compact repository capsule")
    add_common_arguments(orient, inherited=True)
    orient.set_defaults(func=_map_orient)

    outline = sub.add_parser(
        "outline", help="show structure/signatures without full implementation bodies"
    )
    add_common_arguments(outline, inherited=True)
    outline.add_argument("path")
    outline.set_defaults(func=_outline)

    find_code = sub.add_parser("find", help="search the maintained path/symbol index")
    add_common_arguments(find_code, inherited=True)
    find_code.add_argument("query")
    find_code.add_argument("--limit", type=int, default=20)
    find_code.set_defaults(func=_find_code)

    grep_code = sub.add_parser(
        "grep", help="persistent lexical grep narrowed by CodeMap"
    )
    add_common_arguments(grep_code, inherited=True)
    grep_code.add_argument("query")
    grep_code.add_argument("--limit", type=int, default=50)
    grep_code.add_argument(
        "--context", type=int, default=0, help="source context lines around each match"
    )
    grep_code.set_defaults(func=_grep_code)


def _add_graph_cli(sub, *, add_common_arguments: Callable[..., None]) -> None:
    structural_code = sub.add_parser(
        "structural", help="optional syntax-aware search via local ast-grep"
    )
    add_common_arguments(structural_code, inherited=True)
    structural_code.add_argument("pattern")
    structural_code.add_argument("--lang")
    structural_code.add_argument("--limit", type=int, default=100)
    structural_code.set_defaults(func=_structural_code)

    for name, help_text, handler in (
        ("symbol", "show matching symbol records", _symbol_code),
        ("deps", "show static dependency/call evidence", _deps_code),
        ("refs", "show static references/calls to a symbol name", _refs_code),
    ):
        query_command = sub.add_parser(name, help=help_text)
        add_common_arguments(query_command, inherited=True)
        query_command.add_argument("query")
        query_command.set_defaults(func=handler)

    source_code = sub.add_parser(
        "source", help="return one exact symbol body under an explicit token budget"
    )
    add_common_arguments(source_code, inherited=True)
    source_code.add_argument("query", help="symbol name or path::qualname")
    source_code.add_argument("--budget", type=int, default=4000)
    source_code.set_defaults(func=_source_code)

    affected_code = sub.add_parser(
        "affected", help="show reverse file dependents from the CodeMap graph"
    )
    add_common_arguments(affected_code, inherited=True)
    affected_code.add_argument("query")
    affected_code.add_argument("--max-depth", type=int, default=12)
    affected_code.set_defaults(func=_affected_code)

    tests_code = sub.add_parser(
        "tests", help="show structurally related tests from reverse dependencies"
    )
    add_common_arguments(tests_code, inherited=True)
    tests_code.add_argument("query")
    tests_code.add_argument("--max-depth", type=int, default=12)
    tests_code.set_defaults(func=_tests_code)

    locality = sub.add_parser(
        "structural-locality",
        help="project bounded structural locality facts for one exact path::qualname",
    )
    add_common_arguments(locality, inherited=True)
    locality.add_argument("target", help="exact repository-relative path::qualname")
    locality.add_argument("--max-depth", type=int, default=2)
    locality.add_argument("--call-limit", type=int, default=64)
    locality.add_argument("--ref-limit", type=int, default=256)
    locality.set_defaults(func=_structural_locality_code)

    locality_delta = sub.add_parser(
        "structural-locality-delta",
        help="compare two structural-locality evidence packets without policy",
    )
    add_common_arguments(locality_delta, inherited=True)
    locality_delta.add_argument("--before", required=True)
    locality_delta.add_argument("--after", required=True)
    locality_delta.set_defaults(func=_structural_locality_delta_code)


def _add_context_cli(sub, *, add_common_arguments: Callable[..., None]) -> None:
    context_code = sub.add_parser(
        "context", help="build a token-budgeted repository context pack"
    )
    add_common_arguments(context_code, inherited=True)
    context_code.add_argument("query")
    context_code.add_argument("--budget", type=int, default=4000)
    context_code.add_argument("--limit", type=int, default=30)
    context_code.add_argument(
        "--level",
        choices=("orient", "outline", "evidence", "source"),
        default="source",
        help="progressive disclosure level; source preserves the pre-0.10.12 behavior",
    )
    context_code.set_defaults(func=_context_code)


def _add_task_evidence_cli(sub, *, add_common_arguments: Callable[..., None]) -> None:
    task_evidence = sub.add_parser(
        "task-evidence",
        help="resolve one task into bounded edit/verify/source repository evidence",
    )
    add_common_arguments(task_evidence, inherited=True)
    task_evidence.add_argument("task")
    task_evidence.add_argument(
        "--budget",
        type=int,
        default=1536,
        help="maximum estimated tokens of source evidence",
    )
    task_evidence.add_argument("--limit", type=int, default=20)
    task_evidence.add_argument("--per-role", type=int, default=3)
    task_evidence.set_defaults(func=_task_evidence_code)

    verification_relevance = sub.add_parser(
        "verification-relevance",
        help="rank bounded deterministic verification surfaces for an external consumer",
    )
    add_common_arguments(verification_relevance, inherited=True)
    verification_relevance.add_argument("task")
    verification_relevance.add_argument("--limit", type=int, default=20)
    verification_relevance.add_argument("--candidate-limit", type=int, default=8)
    verification_relevance.set_defaults(func=_verification_relevance_code)


def _add_change_cli(sub, *, add_common_arguments: Callable[..., None]) -> None:
    change_impact = sub.add_parser(
        "change-impact",
        help="expose bounded changed-code impact and verification relevance",
    )
    add_common_arguments(change_impact, inherited=True)
    change_impact.add_argument("task")
    change_impact.add_argument(
        "--changed",
        action="append",
        required=True,
        help="repository-relative changed path; repeatable",
    )
    change_impact.add_argument("--limit", type=int, default=20)
    change_impact.add_argument("--per-role", type=int, default=3)
    change_impact.add_argument(
        "--impact-limit", type=int, default=6, help="maximum affected paths per surface"
    )
    change_impact.add_argument("--max-depth", type=int, default=4)
    change_impact.add_argument(
        "--project-impact-limit",
        type=int,
        help="independent maximum affected-project provenance rows",
    )
    change_impact.add_argument(
        "--project-impact-encoding",
        choices=("verbose", "compact"),
        default="verbose",
        help="project provenance transport encoding",
    )
    change_impact.set_defaults(func=_change_impact_code)

    post_change = sub.add_parser(
        "post-change",
        help="refresh reported changed paths and emit changed/reusable repository evidence",
    )
    add_common_arguments(post_change, inherited=True)
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
    post_change.add_argument("--budget", type=int, default=1536)
    post_change.add_argument("--limit", type=int, default=20)
    post_change.add_argument("--per-role", type=int, default=3)
    post_change.set_defaults(func=_post_change_code)


def add_repository_cli(sub, *, add_common_arguments: Callable[..., None]) -> None:
    """Register repository-intelligence CLI families without owning top-level CLI policy."""
    _add_map_cli(sub, add_common_arguments=add_common_arguments)
    _add_navigation_cli(sub, add_common_arguments=add_common_arguments)
    _add_graph_cli(sub, add_common_arguments=add_common_arguments)
    _add_context_cli(sub, add_common_arguments=add_common_arguments)
    _add_task_evidence_cli(sub, add_common_arguments=add_common_arguments)
    _add_change_cli(sub, add_common_arguments=add_common_arguments)
