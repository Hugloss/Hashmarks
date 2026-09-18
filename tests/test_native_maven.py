from __future__ import annotations

from pathlib import Path

from hashmarks.native_maven import collect_maven_modules


def test_collect_maven_modules_keeps_valid_modules_and_reports_bad_pom(
    tmp_path: Path,
) -> None:
    (tmp_path / "pom.xml").write_text(
        "<project><parent><groupId>org.example</groupId></parent>"
        "<artifactId>app</artifactId><dependencies>"
        "<dependency><groupId>org.example</groupId><artifactId>core</artifactId></dependency>"
        "<dependency><groupId>org.example</groupId></dependency>"
        "<other><artifactId>ignored</artifactId></other>"
        "</dependencies></project>",
        encoding="utf-8",
    )
    invalid = tmp_path / "broken" / "pom.xml"
    invalid.parent.mkdir()
    invalid.write_text("<project>", encoding="utf-8")
    snapshot = collect_maven_modules(tmp_path)
    assert len(snapshot.modules) == 1
    module = snapshot.modules[0]
    assert module.module_id == "org.example:app"
    assert module.root == "."
    assert module.manifest == "pom.xml"
    assert module.dependencies == (("org.example", "core"),)
    assert len(snapshot.warnings) == 1
    assert snapshot.warnings[0].startswith("cannot parse broken/pom.xml:")


def test_collect_maven_modules_skips_pruned_and_symlinked_manifests(
    tmp_path: Path,
) -> None:
    (tmp_path / "pom.xml").write_text(
        "<project><artifactId>root</artifactId></project>", encoding="utf-8"
    )
    generated = tmp_path / "target"
    generated.mkdir()
    (generated / "pom.xml").write_text(
        "<project><artifactId>generated</artifactId></project>", encoding="utf-8"
    )
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / "pom.xml").symlink_to(tmp_path / "pom.xml")
    snapshot = collect_maven_modules(tmp_path)
    assert [module.module_id for module in snapshot.modules] == ["root"]
