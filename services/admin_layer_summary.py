from __future__ import annotations


def summarize_unavailable_layers(unavailable: list[str] | None) -> dict:
    """Return compact counts plus expandable, grouped detail labels."""

    groups = {"reference": [], "historical": [], "other": []}
    for raw in unavailable or []:
        label = str(raw)
        prefix, separator, name = label.partition(":")
        kind = prefix.strip().lower() if separator else "other"
        if kind not in groups:
            kind = "other"
        groups[kind].append(name.strip() if separator else label)
    return {
        "total": sum(len(values) for values in groups.values()),
        "reference": len(groups["reference"]),
        "historical": len(groups["historical"]),
        "groups": groups,
    }
