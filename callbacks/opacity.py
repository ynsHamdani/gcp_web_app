from __future__ import annotations

from dash import ALL, Input, Output, State


# =========================================================
# CALLBACKS
# =========================================================

def register_opacity_callbacks(app):
    """Register opacity sliders for all uploaded raster overlays."""

    @app.callback(
        Output(
            {
                "type": "reference-raster-layer",
                "index": ALL,
            },
            "opacity",
        ),
        Input(
            "reference-opacity",
            "value",
        ),
        State(
            {
                "type": "reference-raster-layer",
                "index": ALL,
            },
            "id",
        ),
        prevent_initial_call=True,
    )
    def update_reference_opacity(
        value,
        layer_ids,
    ):
        opacity = value / 100.0

        return [
            opacity
            for _ in layer_ids
        ]

    @app.callback(
        Output(
            {
                "type": "historical-raster-layer",
                "index": ALL,
            },
            "opacity",
        ),
        Input(
            "historical-opacity",
            "value",
        ),
        State(
            {
                "type": "historical-raster-layer",
                "index": ALL,
            },
            "id",
        ),
        prevent_initial_call=True,
    )
    def update_historical_opacity(
        value,
        layer_ids,
    ):
        opacity = value / 100.0

        return [
            opacity
            for _ in layer_ids
        ]
