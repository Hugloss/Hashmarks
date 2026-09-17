from __future__ import annotations

from hashmarks.codemap.find_engine import FindEngineMixin
from hashmarks.codemap.model import SearchHit
from hashmarks.codemap.query_router import route_query


def _hit(path: str, score: float) -> SearchHit:
    return SearchHit(path=path, score=score, kind="file")


def test_control_hits_reserve_one_qualified_hit_per_preferred_domain() -> None:
    route = route_query("architecture ownership config")
    ranked = (
        _hit("README.md", 80.0),
        _hit("docs/architecture.md", 70.0),
        _hit("AGENTS.md", 60.0),
        _hit("pyproject.toml", 50.0),
        _hit("docs/low-score-architecture.md", 20.0),
    )

    selected = FindEngineMixin._find_control_hits(route, ranked, limit=20)

    assert [hit.path for hit in selected] == [
        "README.md",
        "AGENTS.md",
        "pyproject.toml",
    ]
