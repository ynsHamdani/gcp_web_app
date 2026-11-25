from __future__ import annotations

"""Small, explicit helpers for the conservative unique-match policy."""

from typing import Any


def classify_match_count(match_count: int) -> tuple[str, str | None]:
    """Return the two-class assignment result and its non-unique reason.

    The sole spatial predicate is PostGIS ST_Covers. A GCP is assigned only
    when exactly one feature covers its reference point. A count of zero is
    uncovered; a count greater than one has multiple matches.
    """
    count = int(match_count)
    if count < 0:
        raise ValueError("match_count cannot be negative.")
    if count == 1:
        return "ASSIGNED_UNIQUE", None
    if count == 0:
        return "NOT_UNIQUE", "UNCOVERED"
    return "NOT_UNIQUE", "MULTIPLE_MATCHES"


def leaflet_bounds_to_dict(bounds: Any) -> dict[str, float]:
    """Normalize Dash Leaflet's [[south, west], [north, east]] bounds."""
    if isinstance(bounds, dict):
        if {"west", "south", "east", "north"}.issubset(bounds):
            values = {key: float(bounds[key]) for key in ("west", "south", "east", "north")}
        else:
            raise ValueError("The map viewport bounds are incomplete.")
    elif isinstance(bounds, (list, tuple)) and len(bounds) == 2:
        lower, upper = bounds
        if not isinstance(lower, (list, tuple)) or not isinstance(upper, (list, tuple)) or len(lower) < 2 or len(upper) < 2:
            raise ValueError("The map viewport bounds are incomplete.")
        values = {"south": float(lower[0]), "west": float(lower[1]), "north": float(upper[0]), "east": float(upper[1])}
    else:
        raise ValueError("The map viewport bounds are unavailable. Pan or zoom the map and try again.")

    if not (-180 <= values["west"] < values["east"] <= 180):
        raise ValueError("The map viewport longitude range is invalid.")
    if not (-90 <= values["south"] < values["north"] <= 90):
        raise ValueError("The map viewport latitude range is invalid.")
    return values


def context_breakdown_label(value: Any) -> str:
    """Render a JSON context-count object as compact, stable table text."""
    if not value:
        return "—"
    if isinstance(value, str):
        import json
        value = json.loads(value)
    return "; ".join(f"{label}: {count}" for label, count in sorted(value.items(), key=lambda pair: str(pair[0]).casefold()))
