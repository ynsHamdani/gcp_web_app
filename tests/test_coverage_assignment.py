from __future__ import annotations

import pytest

from services.coverage_assignment import classify_match_count, context_breakdown_label, leaflet_bounds_to_dict


@pytest.mark.parametrize("count, expected", [
    (0, ("NOT_UNIQUE", "UNCOVERED")),
    (1, ("ASSIGNED_UNIQUE", None)),
    (2, ("NOT_UNIQUE", "MULTIPLE_MATCHES")),
    (17, ("NOT_UNIQUE", "MULTIPLE_MATCHES")),
])
def test_unique_assignment_classification(count, expected):
    assert classify_match_count(count) == expected


def test_negative_match_count_is_rejected():
    with pytest.raises(ValueError, match="negative"):
        classify_match_count(-1)


def test_leaflet_bounds_normalize_to_numeric_extent():
    assert leaflet_bounds_to_dict([[55.0, 8.0], [58.0, 13.0]]) == {
        "south": 55.0, "west": 8.0, "north": 58.0, "east": 13.0,
    }


def test_invalid_leaflet_bounds_are_rejected():
    with pytest.raises(ValueError):
        leaflet_bounds_to_dict([[58.0, 13.0], [55.0, 8.0]])


def test_context_breakdown_is_stable_and_readable():
    assert context_breakdown_label({"Water": 2, "Forest": 5}) == "Forest: 5; Water: 2"
    assert context_breakdown_label({}) == "—"
