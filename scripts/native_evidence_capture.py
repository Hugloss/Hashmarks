"""Opt-in development capture of real producers; never imported by product code.

The caller supplies installed tooling and owns execution. Captures are temporary
QA inputs, not repository truth or independent certification of the producers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from hashmarks.digest import FILE_DOMAIN, hash_bytes


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"native evidence qualification requires installed {name}")
    return path


def _run(argv: list[str], cwd: Path) -> str:
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(
            f"producer command failed ({result.returncode}): {argv!r}\n{result.stderr[-4000:]}\n{result.stdout[-4000:]}"
        )
    return result.stdout


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _source_revisions(root: Path, suffixes: tuple[str, ...]) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hash_bytes(
            path.read_bytes(), domain=FILE_DOMAIN
        ).hash
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and path.suffix in suffixes
        and "node_modules" not in path.parts
    }


def capture_scip(source: Path, destination: Path, language: str) -> None:
    """Index one explicit fixture and retain untouched decoded producer output."""
    shutil.copytree(source, destination)
    for name in ("index.json", "index.scip", "provenance.json", "capture.json"):
        (destination / name).unlink(missing_ok=True)
    producer = _tool("scip-python" if language == "python" else "scip-typescript")
    decoder = _tool("scip")
    before = _source_revisions(
        destination, (".py",) if language == "python" else (".ts",)
    )
    arguments = ["index", "--output", "index.scip"]
    if language == "python":
        arguments += [
            "--project-name",
            "hashmarks-native-python",
            "--project-version",
            "1.0.0",
            "--environment",
            "environment.json",
        ]
    else:
        arguments += ["--no-progress-bar"]
    version = _run([producer, "--version"], destination).strip()
    _run([producer, *arguments], destination)
    decoded = _run([decoder, "print", "--json", "index.scip"], destination)
    (destination / "index.json").write_text(decoded, encoding="utf-8")
    assert before == _source_revisions(
        destination, (".py",) if language == "python" else (".ts",)
    ), "capture inputs changed while indexing"
    documents = json.loads(decoded)["documents"]
    assert set(before) <= {
        row.get("relativePath", row.get("relative_path")) for row in documents
    }, "producer omitted a fixture source"
    configuration = {
        "producer": Path(producer).name,
        "version": version,
        "arguments": arguments,
        "configuration": {
            name: (destination / name).read_text()
            for name in ("pyrightconfig.json", "environment.json")
            if (destination / name).exists()
        },
    }
    if language == "typescript":
        configuration["configuration"] = {
            name: (destination / name).read_text()
            for name in ("package.json", "tsconfig.json")
        }
    configuration_identity = (
        "sha256:"
        + hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    )
    _write_json(
        destination / "provenance.json",
        {
            "configuration_identity": configuration_identity,
            "collection_state": "fresh-complete",
            "source_revisions": before,
        },
    )
    _write_json(
        destination / "capture.json",
        {
            "configuration": configuration,
            "decoder_version": _run([decoder, "--version"], destination).strip(),
            "source_revisions": before,
            "binary_sha256": hashlib.sha256(
                (destination / "index.scip").read_bytes()
            ).hexdigest(),
            "json_sha256": hashlib.sha256(
                (destination / "index.json").read_bytes()
            ).hexdigest(),
            "qualification_authority": "external-capture-caller-claim",
        },
    )


def _capture_maven(
    root: Path, destination: Path, *, repository: Path, profile: str | None = None
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    producer = _tool("mvn")
    commands = []
    before = _source_revisions(root, (".xml",))
    for goal, name, options in (
        ("tree", "tree.json", ["-DoutputType=json"]),
        ("list", "list.txt", []),
    ):
        output = destination / name
        output.unlink(missing_ok=True)
        arguments = [
            "-B",
            "-q",
            "-Dstyle.color=never",
            "org.apache.maven.plugins:maven-dependency-plugin:3.9.0:" + goal,
            "-DoutputFile=" + str(output),
            *options,
        ]
        if profile:
            arguments.append("-P" + profile)
        _run([producer, "-Dmaven.repo.local=" + str(repository), *arguments], root)
        assert output.is_file() and output.stat().st_size, "Maven emitted no capture"
        commands.append(arguments)
    assert before == _source_revisions(root, (".xml",)), "Maven changed fixture inputs"
    _write_json(
        destination / "capture.json",
        {
            "producer_version": _run([producer, "--version"], root),
            "commands": commands,
            "repository_inputs": before,
            "qualification_authority": "external-capture-caller-claim",
        },
    )


def _install_maven_fixture(root: Path, manifest: Path, repository: Path) -> None:
    jar = root / "dummy-dep.jar"
    with zipfile.ZipFile(jar, "w") as archive:
        archive.writestr("META-INF/MANIFEST.MF", manifest.read_bytes())
    for version in ("1.0.0", "2.0.0"):
        _run(
            [
                _tool("mvn"),
                "-Dmaven.repo.local=" + str(repository),
                "-B",
                "-q",
                "-Dstyle.color=never",
                "org.apache.maven.plugins:maven-install-plugin:2.4:install-file",
                "-Dfile=" + str(jar),
                "-DgroupId=example.fixture",
                "-DartifactId=dummy-dep",
                "-Dversion=" + version,
                "-Dpackaging=jar",
            ],
            root,
        )


def capture_dependencies(source: Path, destination: Path) -> None:
    """Regenerate only the bounded scenarios used by the integration ring."""
    shutil.copytree(source, destination)
    uv = _tool("uv")
    for state in ("absent", "v1", "v2", "grouped"):
        root = destination / "uv" / state
        (root / "uv.lock").unlink()
        arguments = ["lock", "--offline", "--python", sys.executable]
        _run([uv, *arguments], root)
        _write_json(
            root / "capture.json",
            {
                "producer_version": _run([uv, "--version"], root).strip(),
                "arguments": arguments,
                "lock_sha256": hashlib.sha256(
                    (root / "uv.lock").read_bytes()
                ).hexdigest(),
            },
        )
    repository = destination / "maven-repository"
    _install_maven_fixture(
        destination / "maven", source / "maven" / "dummy-dep-manifest.mf", repository
    )
    for state in ("absent", "v1", "v2"):
        root = destination / "maven" / state
        _capture_maven(root, root, repository=repository)
    for scenario in ("transitive-upgrade", "mediation", "exclusion"):
        for state in ("before", "after"):
            root = destination / "maven" / scenario / state
            _capture_maven(root, root, repository=repository)
    profiles = destination / "maven" / "profiles"
    _capture_maven(profiles, profiles / "default", repository=repository)
    _capture_maven(profiles, profiles / "extra", repository=repository, profile="extra")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family", choices=("dependencies", "python", "typescript"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    if args.family == "dependencies":
        capture_dependencies(args.source.resolve(), args.destination.resolve())
    else:
        capture_scip(args.source.resolve(), args.destination.resolve(), args.family)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
