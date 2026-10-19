"""Identity observation wire shapes; no filesystem resolution or digest owner.

Requests retain the existing typed input declarations. Response validation checks
the complete envelope and internal consistency; it does not reobserve source or
establish the authenticity of a peer's supplied digest and freshness claims.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal, TypedDict, cast

from .digest import Digest
from .generation_domain import require_generation
from .inputs import InputManifest
from .paths import normalize_relative_path, normalize_relative_pattern
from .schema import SNAPSHOT_SCHEMA
from .snapshot import InputCounts, InputMember, InputObservation, Snapshot
from .specs import Directory, File, Glob, InputValue, validate_input_values

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


class InputObservationArguments(TypedDict):
    inputs: tuple[InputValue, ...]
    exclude: tuple[InputValue, ...]
    require_matches: bool
    verify: bool
    max_members: int


def validate_observation_options(
    require_matches: bool, verify: bool, max_members: int
) -> None:
    if type(require_matches) is not bool or type(verify) is not bool:
        raise ValueError("require_matches and verify must be booleans")
    if type(max_members) is not int or max_members < 1:
        raise ValueError("max_members must be a positive integer")


def _encoded_specs(
    workspace: str | Path, values: Iterable[InputValue], *, require_matches: bool
) -> list[dict[str, str]]:
    values = tuple(values)
    patterns = validate_input_values(workspace, values, require_matches=require_matches)
    kinds = {File: "file", Directory: "directory", Glob: "glob"}
    return [
        {
            "kind": next(
                (kind for cls, kind in kinds.items() if isinstance(value, cls)),
                "pattern",
            ),
            "value": normalize_relative_pattern(pattern),
        }
        for value, pattern in zip(values, patterns, strict=True)
    ]


def encode_input_observation_request(
    workspace: str | Path,
    inputs: Iterable[InputValue],
    *,
    exclude: Iterable[InputValue],
    require_matches: bool,
    verify: bool,
    max_members: int,
) -> dict[str, object]:
    validate_observation_options(require_matches, verify, max_members)
    return {
        "inputs": _encoded_specs(workspace, inputs, require_matches=require_matches),
        "exclude": _encoded_specs(workspace, exclude, require_matches=False),
        "require_matches": require_matches,
        "verify": verify,
        "max_members": max_members,
    }


def _object(value: object, keys: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} must contain exactly {sorted(keys)}")
    return cast(dict[str, object], value)


def _decoded_spec(value: object) -> InputValue:
    row = _object(value, {"kind", "value"}, "input specification")
    kind, pattern = row["kind"], row["value"]
    if not isinstance(pattern, str) or normalize_relative_pattern(pattern) != pattern:
        raise ValueError("input specification value must be a canonical pattern")
    constructors = {"file": File, "directory": Directory, "glob": Glob}
    if kind == "pattern":
        return pattern
    if not isinstance(kind, str) or kind not in constructors:
        raise ValueError("input specification kind is unsupported")
    spec = constructors[kind](pattern)
    spec.as_pattern()
    return spec


def _decoded_specs(value: object) -> tuple[InputValue, ...]:
    if not isinstance(value, list):
        raise ValueError("input specifications must be an array")
    return tuple(_decoded_spec(row) for row in value)


def decode_input_observation_request(
    request: Mapping[str, object],
) -> InputObservationArguments:
    allowed = {
        "protocol",
        "op",
        "inputs",
        "exclude",
        "require_matches",
        "verify",
        "max_members",
    }
    if set(request) - allowed:
        raise ValueError("input observation request has unsupported fields")
    require_matches = request.get("require_matches", True)
    verify = request.get("verify", False)
    max_members = request.get("max_members")
    validate_observation_options(
        cast(bool, require_matches), cast(bool, verify), cast(int, max_members)
    )
    return {
        "inputs": _decoded_specs(request.get("inputs")),
        "exclude": _decoded_specs(request.get("exclude", [])),
        "require_matches": cast(bool, require_matches),
        "verify": cast(bool, verify),
        "max_members": cast(int, max_members),
    }


def _integer(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _revision(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a canonical SHA-256 revision")
    return value


def _paths(value: object, label: str, *, allow_root: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(path, str) for path in value):
        raise ValueError(f"{label} must be an array of paths")
    paths = cast(list[str], value)
    for path in paths:
        if normalize_relative_path(path, allow_root=allow_root) != path:
            raise ValueError(f"{label} contains a noncanonical path")
    if paths != sorted(set(paths)):
        raise ValueError(f"{label} must be sorted and unique")
    return tuple(paths)


def _names(value: object, label: str) -> tuple[str, ...]:
    names = _paths(value, label)
    if any("/" in name for name in names):
        raise ValueError(f"{label} must contain entry names")
    return names


def _snapshot(value: object, manifest: InputManifest) -> Snapshot:
    row = _object(
        value,
        {"schema", "hash", "size", "manifest", "generation", "observed_paths", "mode"},
        "input observation snapshot",
    )
    if row["schema"] != SNAPSHOT_SCHEMA or row["mode"] != "daemon":
        raise ValueError("input observation snapshot schema or mode is invalid")
    if row["manifest"] != manifest.fingerprint:
        raise ValueError("input observation manifest fingerprint does not match roots")
    return Snapshot(
        digest=Digest(
            hash=_revision(row["hash"], "snapshot hash"),
            size=_integer(row["size"], "snapshot size"),
        ),
        manifest_fingerprint=manifest.fingerprint,
        generation=require_generation(row["generation"], field="snapshot generation"),
        observed_paths=_paths(row["observed_paths"], "observed paths", allow_root=True),
        mode="daemon",
    )


def _member(value: object) -> InputMember:
    row = _object(
        value,
        {"path", "kind", "revision", "regular_file_bytes", "executable", "link_target"},
        "input member",
    )
    path, kind = row["path"], row["kind"]
    if (
        not isinstance(path, str)
        or normalize_relative_path(path, allow_root=False) != path
    ):
        raise ValueError("input member path must be canonical")
    if kind not in ("file", "directory", "symlink"):
        raise ValueError("input member kind is invalid")
    length = _integer(row["regular_file_bytes"], "member regular_file_bytes")
    executable, target = row["executable"], row["link_target"]
    _member_details(str(kind), length, executable, target)
    return InputMember(
        path=path,
        kind=cast(Literal["file", "directory", "symlink"], kind),
        revision=_revision(row["revision"], "member revision"),
        regular_file_bytes=length,
        executable=cast(bool | None, executable),
        link_target=cast(str | None, target),
    )


def _member_details(kind: str, length: int, executable: object, target: object) -> None:
    if kind == "file":
        if type(executable) is not bool or target is not None:
            raise ValueError(
                "file member must have a boolean executable bit and no target"
            )
    elif length != 0 or executable is not None:
        raise ValueError("non-file member cannot have file bytes or an executable bit")
    if kind == "symlink":
        if not isinstance(target, str) or not target or "\x00" in target:
            raise ValueError("symlink member must have a literal target")
    elif target is not None:
        raise ValueError("non-symlink member cannot have a target")


def _members(value: object, max_members: int) -> tuple[InputMember, ...]:
    if not isinstance(value, list) or len(value) > max_members:
        raise ValueError("input observation members must be a bounded array")
    members = tuple(_member(row) for row in value)
    paths = [member.path for member in members]
    if paths != sorted(
        set(paths), key=lambda path: path.encode("utf-8", "surrogateescape")
    ):
        raise ValueError("input observation members must be ordered and unique")
    return members


def _counts(value: object, members: tuple[InputMember, ...]) -> InputCounts:
    row = _object(
        value,
        {
            "entry_count",
            "file_count",
            "directory_count",
            "symlink_count",
            "regular_file_bytes",
        },
        "input observation counts",
    )
    for key, count in row.items():
        _integer(count, key)
    counts = InputCounts(
        file_count=sum(member.kind == "file" for member in members),
        directory_count=sum(member.kind == "directory" for member in members),
        symlink_count=sum(member.kind == "symlink" for member in members),
        regular_file_bytes=sum(member.regular_file_bytes for member in members),
    )
    if counts.as_dict() != row:
        raise ValueError("input observation counts do not match members")
    return counts


def _ancestors(path: str) -> tuple[str, ...]:
    parts = path.split("/")
    return tuple("/".join(parts[:end]) for end in range(1, len(parts) + 1))


def _validate_member_scope(
    manifest: InputManifest,
    excluded: tuple[str, ...],
    members: tuple[InputMember, ...],
) -> None:
    roots, exclusions = set(manifest.paths), set(excluded)
    kinds = {member.path: member.kind for member in members}
    if not roots.issubset(kinds):
        raise ValueError("input observation is missing a selected root")
    if any(exclusions.intersection(_ancestors(path)[:-1]) for path in exclusions):
        raise ValueError("input observation exclusions must collapse descendants")
    for member in members:
        ancestors = set(_ancestors(member.path))
        if len(roots.intersection(ancestors)) != 1 or exclusions.intersection(
            ancestors
        ):
            raise ValueError("input observation member is outside the selected scope")
        if (
            member.path not in roots
            and kinds.get(member.path.rpartition("/")[0]) != "directory"
        ):
            raise ValueError(
                "input observation member is missing its selected directory"
            )


def _validate_internal_policy(
    members: tuple[InputMember, ...],
    mandatory_names: tuple[str, ...],
    internal_paths: tuple[str, ...],
) -> None:
    names, paths = set(mandatory_names), set(internal_paths)
    for member in members:
        if names.intersection(member.path.split("/")) or paths.intersection(
            _ancestors(member.path)
        ):
            raise ValueError(
                "input observation member contradicts an internal exclusion"
            )


def decode_input_observation(value: object, *, max_members: int) -> InputObservation:
    """Decode one complete daemon envelope without acquiring source authority."""
    row = _object(
        value,
        {
            "schema",
            "snapshot",
            "scope",
            "members",
            "counts",
            "completeness",
            "freshness",
            "authority",
            "execution_effect",
        },
        "input observation",
    )
    expected = {
        "schema": "hashmarks.input-observation.v1",
        "completeness": "complete",
        "authority": "repository-evidence-only",
        "execution_effect": "none",
    }
    if any(row[key] != expected_value for key, expected_value in expected.items()):
        raise ValueError("input observation schema or authority is invalid")
    if row["freshness"] not in ("current", "stale", "unknown"):
        raise ValueError("input observation freshness is invalid")
    scope = _object(
        row["scope"],
        {
            "roots",
            "excluded_paths",
            "walk_ignore_names",
            "mandatory_exclude_names",
            "internal_excluded_paths",
        },
        "input observation scope",
    )
    manifest = InputManifest(_paths(scope["roots"], "selected roots"))
    excluded = _paths(scope["excluded_paths"], "excluded paths")
    mandatory = _names(scope["mandatory_exclude_names"], "mandatory exclude names")
    internal = _paths(scope["internal_excluded_paths"], "internal excluded paths")
    members = _members(row["members"], max_members)
    _validate_member_scope(manifest, excluded, members)
    _validate_internal_policy(members, mandatory, internal)
    return InputObservation(
        snapshot=_snapshot(row["snapshot"], manifest),
        manifest=manifest,
        excluded_paths=excluded,
        members=members,
        counts=_counts(row["counts"], members),
        freshness=cast(str, row["freshness"]),
        walk_ignore_names=_names(scope["walk_ignore_names"], "walk ignore names"),
        mandatory_exclude_names=mandatory,
        internal_excluded_paths=internal,
    )
