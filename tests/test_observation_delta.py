from hashmarks.codemap.observation_delta import observation_delta


def _packet(*, repository: str, observer: str, rows: list[dict[str, object]]):
    return {
        "repository": {"identity": repository, "generation": 1},
        "observer": {"identity": observer},
        "observations": rows,
    }


def test_delta_separates_repository_change_from_observer_change() -> None:
    before = _packet(repository="repo:a", observer="observer:a", rows=[])
    after = _packet(repository="repo:a", observer="observer:b", rows=[])

    delta = observation_delta(before, after)

    assert delta["repository"]["changed"] is False
    assert delta["observer"]["changed"] is True
    assert delta["cause"] == "observer-changed"


def test_delta_matches_rows_only_by_stable_identity() -> None:
    before = _packet(
        repository="repo:a",
        observer="observer:a",
        rows=[
            {"identity": "finding:a", "count": 1},
            {"identity": "finding:b", "count": 2},
        ],
    )
    after = _packet(
        repository="repo:b",
        observer="observer:a",
        rows=[
            {"identity": "finding:a", "count": 3},
            {"identity": "finding:c", "count": 2},
        ],
    )

    delta = observation_delta(before, after)

    assert delta["observations"] == {
        "added": ["finding:c"],
        "removed": ["finding:b"],
        "changed": ["finding:a"],
        "unchanged": [],
    }
    assert delta["cause"] == "repository-changed"


def test_delta_does_not_invent_identity_for_rows_without_one() -> None:
    before = _packet(
        repository="repo:a",
        observer="observer:a",
        rows=[{"path": "same.py", "count": 1}],
    )
    after = _packet(
        repository="repo:a",
        observer="observer:a",
        rows=[{"path": "same.py", "count": 2}],
    )

    delta = observation_delta(before, after)

    assert delta["observations"] == {
        "added": [],
        "removed": [],
        "changed": [],
        "unchanged": [],
    }
