from __future__ import annotations

from dash import Input, Output, State, ctx, no_update


# =========================================================
# HELPERS
# =========================================================


def _find_layer(registry, layer_id):
    if not layer_id:
        return None

    return next(
        (
            item
            for item in (registry or [])
            if item.get("id") == layer_id
        ),
        None,
    )


def _find_gcp(records, gcp_id):
    if not gcp_id:
        return None

    return next(
        (
            record
            for record in (records or [])
            if record.get("gcp_id") == gcp_id
        ),
        None,
    )


# =========================================================
# CALLBACKS
# =========================================================


def register_navigation_callbacks(app):
    """Register layer navigation and GCP focus behavior for both maps."""

    @app.callback(
        Output("reference-map", "center"),
        Output("reference-map", "zoom"),
        Output("historical-map", "center"),
        Output("historical-map", "zoom"),
        Input("reference-layer-zoom-button", "n_clicks"),
        Input("historical-layer-zoom-button", "n_clicks"),
        Input("gcp-selected-id", "data"),
        State("reference-layer-zoom-select", "value"),
        State("historical-layer-zoom-select", "value"),
        State("reference-layer-registry", "data"),
        State("historical-layer-registry", "data"),
        State("gcp-records", "data"),
        prevent_initial_call=True,
    )
    def navigate(
        reference_clicks,
        historical_clicks,
        selected_gcp_id,
        selected_reference_id,
        selected_historical_id,
        reference_registry,
        historical_registry,
        gcp_records,
    ):
        del reference_clicks, historical_clicks

        triggered = ctx.triggered_id

        # -------------------------------------------------
        # Click a GCP row
        # -------------------------------------------------
        if triggered == "gcp-selected-id":
            gcp = _find_gcp(gcp_records, selected_gcp_id)

            if gcp is None:
                return (
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                )

            reference = gcp.get("reference", {})
            historical = gcp.get("historical", {})

            reference_lat = reference.get("lat")
            reference_lon = reference.get("lon")
            historical_lat = historical.get("lat")
            historical_lon = historical.get("lon")

            if reference_lat is None or reference_lon is None:
                return (
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                )

            # Use the midpoint so both the reference and historical GCP
            # markers remain visible even when there is a small offset.
            if historical_lat is not None and historical_lon is not None:
                center = [
                    (float(reference_lat) + float(historical_lat)) / 2.0,
                    (float(reference_lon) + float(historical_lon)) / 2.0,
                ]
            else:
                center = [
                    float(reference_lat),
                    float(reference_lon),
                ]

            # A fixed close-in zoom is appropriate for GCP inspection.
            zoom = 18

            return (
                center,
                zoom,
                center,
                zoom,
            )

        # -------------------------------------------------
        # Zoom to selected raster layer
        # -------------------------------------------------

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

        selected_layer = _find_layer(
            registry,
            selected_id,
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

        # Both maps deliberately receive the same view. The browser-side sync
        # layer then keeps them linked during use.
        return (
            center,
            zoom,
            center,
            zoom,
        )
