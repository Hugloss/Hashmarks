from pathlib import Path

from hashmarks.codemap.engine import CodeMap
from hashmarks.codemap.indexing_lifecycle import _DiscoveredFile


def test_preflight_scale_ladder_classifies_repository_shape_without_predicting_timeout(
    tmp_path: Path,
) -> None:
    # Cheap QA for the scale contract. Real performance qualification may use
    # larger corpora, but unit QA must not itself become an execution timeout.
    cases = ((100, "small"), (500, "medium"), (1500, "large"), (5001, "very-large"))
    codemap = CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3")
    try:
        for count, expected in cases:
            visibility = codemap.policy.decide("src/f.py").evidence_visibility
            discovered = [
                _DiscoveredFile(
                    f"src/f{i}.py",
                    tmp_path / f"missing-{i}.py",
                    "python",
                    visibility,
                    0,
                )
                for i in range(count)
            ]
            # Missing paths deliberately make bytes zero: this proves file-count
            # scaling is independently represented and no timeout is invented.
            preflight = codemap._preflight_from_discovered(discovered)
            assert preflight["indexable_files"] == count
            assert preflight["work_class"] == expected
            assert preflight["estimated_lexical_rows"] is None
    finally:
        codemap.close()
