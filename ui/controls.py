from __future__ import annotations

from dash import dcc, html


ZOOM_CONTROL_STYLE = {
    "position": "fixed",
    "top": "80px",
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


def create_layer_zoom_control(map_type: str, title: str, placeholder: str):
    """Create a layer selector and synchronized zoom button."""

    if map_type not in {"reference", "historical"}:
        raise ValueError("map_type must be 'reference' or 'historical'")

    position_style = {
        **ZOOM_CONTROL_STYLE,
        "left": "20px" if map_type == "reference" else "calc(50% + 20px)",
    }

    return html.Div(
        [
            html.Div(title, style=ZOOM_TITLE_STYLE),
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


def create_zoom_controls():
    return [
        create_layer_zoom_control(
            "reference", "Zoom to reference layer", "Select a reference map..."
        ),
        create_layer_zoom_control(
            "historical", "Zoom to historical layer", "Select a historical map..."
        ),
    ]


def create_app_layout(reference_map, historical_map, initial_rows=None, initial_records=None):
    """Build the complete application layout and browser-side GCP stores."""

    from ui.layout import create_layout

    records = initial_records or []

    return html.Div(
        [
            create_layout(
                reference_map=reference_map,
                historical_map=historical_map,
                initial_rows=initial_rows or [],
            ),
            *create_zoom_controls(),
            dcc.Store(id="reference-layer-registry", data=[]),
            dcc.Store(id="historical-layer-registry", data=[]),
            dcc.Store(id="gcp-records", data=records),
            dcc.Store(id="gcp-pending", data=None),
            dcc.Store(id="gcp-drag-event", data=None),
            dcc.Store(id="gcp-selected-id", data=None),
        ]
    )
