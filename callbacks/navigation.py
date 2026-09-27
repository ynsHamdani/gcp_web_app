from __future__ import annotations

from dash import Input, Output, State, ctx, no_update


# =========================================================
# CALLBACKS
# =========================================================

def register_navigation_callbacks(app):
    """Register synchronized layer-navigation behavior for both maps."""

    @app.callback(
        Output(
            "reference-map",
            "center",
        ),
        Output(
            "reference-map",
            "zoom",
        ),
        Output(
            "historical-map",
            "center",
        ),
        Output(
            "historical-map",
            "zoom",
        ),
        Input(
            "reference-layer-zoom-button",
            "n_clicks",
        ),
        Input(
            "historical-layer-zoom-button",
            "n_clicks",
        ),
        State(
            "reference-layer-zoom-select",
            "value",
        ),
        State(
            "historical-layer-zoom-select",
            "value",
        ),
        State(
            "reference-layer-registry",
            "data",
        ),
        State(
            "historical-layer-registry",
            "data",
        ),
        prevent_initial_call=True,
    )
    def zoom_to_selected_layer(
        reference_clicks,
        historical_clicks,
        selected_reference_id,
        selected_historical_id,
        reference_registry,
        historical_registry,
    ):
        triggered = ctx.triggered_id

        if triggered == "reference-layer-zoom-button":
            registry = reference_registry or []
            selected_id = selected_reference_id

        elif triggered == "historical-layer-zoom-button":
            registry = historical_registry or []
            selected_id = selected_historical_id

        else:
            return (
                no_update,
                no_update,
                no_update,
                no_update,
            )

        if not selected_id:
            return (
                no_update,
                no_update,
                no_update,
                no_update,
            )

        selected_layer = next(
            (
                item
                for item in registry
                if item.get("id") == selected_id
            ),
            None,
        )

        if selected_layer is None:
            return (
                no_update,
                no_update,
                no_update,
                no_update,
            )

        center = selected_layer["center"]
        zoom = selected_layer["zoom"]

        # Both maps deliberately receive the same view. The
        # browser-side sync layer then keeps them linked during use.
        return (
            center,
            zoom,
            center,
            zoom,
        )
