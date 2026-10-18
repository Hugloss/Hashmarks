"""A completed nullable value remains distinct from an uncomputed result."""

from hashmarks.codemap.singleflight import SingleFlight
from hashmarks.graph import IdentityGraph


def test_singleflight_returns_none_and_releases_the_completed_slot() -> None:
    flight: SingleFlight[str | None] = SingleFlight()
    assert flight.run("observation", lambda: None) == (None, False)
    assert flight.in_flight() == 0
    assert flight.run("observation", lambda: "current") == ("current", False)
    assert flight.in_flight() == 0


def test_identity_graph_preserves_none_and_equality_cutoff_through_changes() -> None:
    value: list[str | None] = [None]
    graph: IdentityGraph[str, str | None] = IdentityGraph()
    graph.add("observation", lambda _dependencies: value[0])
    assert graph.get("observation") is None
    assert graph.version("observation") == 1
    graph.invalidate("observation")
    assert graph.get("observation") is None
    assert graph.version("observation") == 1
    value[0] = "current"
    graph.invalidate("observation")
    assert graph.get("observation") == "current"
    assert graph.version("observation") == 2
    value[0] = None
    graph.invalidate("observation")
    assert graph.get("observation") is None
    assert graph.version("observation") == 3
