from __future__ import annotations

from dash import dcc, html


# =========================================================
# COMMON STYLES
# =========================================================

ZOOM_CONTROL_STYLE = {
    "position": "fixed",
    "top": "195px",
    "zIndex": "1000",
    "width": "280px",
    "backgroundColor": "white",
    "padding": "12px",
    "borderRadius": "8px",
    "boxShadow": "0 2px 10px rgba(0,0,0,0.15)",
}

ZOOM_BUTTON_STYLE = {
    "marginTop": "8px",
    "width": "100%",
    "cursor": "pointer",
}

ZOOM_TITLE_STYLE = {
    "fontWeight": "600",
    "marginBottom": "6px",
}


# =========================================================
# LAYER ZOOM CONTROL
# =========================================================


def create_layer_zoom_control(
    map_type: str,
    title: str,
    placeholder: str,
):
    """Create one layer selector and synchronized zoom button."""

    if map_type not in {"reference", "historical"}:
        raise ValueError(
            "map_type must be 'reference' or 'historical'"
        )

    position_style = {
        **ZOOM_CONTROL_STYLE,
        "left": (
            "20px"
            if map_type == "reference"
            else "calc(50% + 20px)"
        ),
    }

    return html.Div(
        [
            html.Div(
                title,
                style=ZOOM_TITLE_STYLE,
            ),
            dcc.Dropdown(
                id=f"{map_type}-layer-zoom-select",
                options=[],
                value=None,
                placeholder=placeholder,
                clearable=False,
            ),
            html.Button(
                "Zoom to layer",
                id=f"{map_type}-layer-zoom-button",
                n_clicks=0,
                style=ZOOM_BUTTON_STYLE,
            ),
        ],
        style=position_style,
    )


# =========================================================
# BOTH MAP ZOOM CONTROLS
# =========================================================


def create_zoom_controls():
    """Create the layer-navigation controls for both maps."""

    return [
        create_layer_zoom_control(
            map_type="reference",
            title="Zoom to reference layer",
            placeholder="Select a reference map...",
        ),
        create_layer_zoom_control(
            map_type="historical",
            title="Zoom to historical layer",
            placeholder="Select a historical map...",
        ),
    ]


# =========================================================
# APP LAYOUT COMPATIBILITY WRAPPER
# =========================================================


def create_app_layout(
    reference_map,
    historical_map,
    initial_records=None,
    initial_rows=None,
):
    """Build the complete application layout."""

    from ui.layout import create_layout

    if initial_records is not None:
        records = initial_records
    else:
        records = initial_rows or []

    return html.Div(
        [
            create_layout(
                reference_map=reference_map,
                historical_map=historical_map,
                initial_rows=records,
            ),
            *create_zoom_controls(),

            # Uploaded raster metadata registries.
            dcc.Store(
                id="reference-layer-registry",
                data=[],
            ),
            dcc.Store(
                id="historical-layer-registry",
                data=[],
            ),

            # Browser-side navigation command and acknowledgements.
            dcc.Store(
                id="map-navigation-command",
                data=None,
            ),
            dcc.Store(
                id="map-navigation-ack",
                data=None,
            ),
            dcc.Store(
                id="map-cursor-ack",
                data=None,
            ),
        ]
    )
