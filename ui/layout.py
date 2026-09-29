from __future__ import annotations

import dash_ag_grid as dag
from dash import dcc, html


# =========================================================
# MAP PANEL
# =========================================================


def create_map_panel(
    title: str,
    subtitle: str,
    upload_id: str,
    upload_label: str,
    opacity_id: str,
    map_component,
    status_id: str,
):
    """Create one complete map panel."""

    return html.Div(
        className="map-panel",
        children=[
            html.Div(
                className="map-panel-header",
                children=[
                    html.Div(
                        children=[
                            html.Div(
                                title,
                                className="map-panel-title",
                            ),
                            html.Div(
                                subtitle,
                                className="map-panel-subtitle",
                            ),
                        ],
                    ),
                    dcc.Upload(
                        id=upload_id,
                        children=html.Button(
                            upload_label,
                            className="upload-button",
                        ),
                        multiple=False,
                        accept=".tif,.tiff",
                    ),
                ],
            ),
            html.Div(
                className="map-panel-status",
                children=[
                    html.Div(
                        id=status_id,
                        className="upload-status",
                    ),
                ],
            ),
            html.Div(
                className="map-panel-opacity",
                children=[
                    html.Label(
                        "Opacity",
                        htmlFor=opacity_id,
                        className="opacity-label",
                    ),
                    dcc.Slider(
                        id=opacity_id,
                        min=0,
                        max=100,
                        step=1,
                        value=100,
                        marks={0: "0", 50: "50", 100: "100"},
                        tooltip={
                            "placement": "bottom",
                            "always_visible": False,
                        },
                    ),
                ],
            ),
            html.Div(
                className="map-container",
                children=map_component,
            ),
        ],
    )


# =========================================================
# GCP CONTROLS
# =========================================================


def create_gcp_controls():
    """Create controls for GCP collection and deletion."""

    button_style = {
        "padding": "7px 12px",
        "borderRadius": "5px",
        "border": "1px solid #d1d5db",
        "background": "#ffffff",
        "cursor": "pointer",
        "fontSize": "12px",
    }

    return html.Div(
        className="bottom-controls",
        children=[
            html.Div(
                children=[
                    html.Div(
                        "GCP COLLECTION",
                        className="gcp-title",
                    ),
                    html.Div(
                        id="gcp-status",
                        className="gcp-status",
                        children=(
                            "GCP collection inactive — "
                            "click Add GCP to start."
                        ),
                    ),
                ],
            ),
            html.Div(
                className="gcp-buttons",
                children=[
                    html.Button(
                        "Add GCP",
                        id="add-gcp-button",
                        n_clicks=0,
                        className="primary-button",
                        style=button_style,
                    ),
                    html.Button(
                        "Confirm GCP",
                        id="confirm-gcp-button",
                        n_clicks=0,
                        disabled=True,
                        className="primary-button",
                        style=button_style,
                    ),
                    html.Button(
                        "Cancel",
                        id="cancel-gcp-button",
                        n_clicks=0,
                        disabled=True,
                        className="secondary-button",
                        style=button_style,
                    ),
                    html.Button(
                        "Delete GCP",
                        id="delete-gcp-button",
                        n_clicks=0,
                        disabled=True,
                        className="secondary-button",
                        style={
                            **button_style,
                            "color": "#b91c1c",
                        },
                    ),
                ],
            ),
        ],
    )


# =========================================================
# GCP TABLE
# =========================================================


def create_gcp_table(initial_rows=None):
    """Create the confirmed-GCP table with single-row selection."""

    return dag.AgGrid(
        id="gcp-table",
        rowData=initial_rows or [],
        columnDefs=[
            {"field": "gcp_id", "headerName": "GCP"},
            {"field": "feature_type", "headerName": "Feature"},
            {"field": "reference", "headerName": "Reference"},
            {"field": "historical", "headerName": "Historical"},
            {"field": "offset", "headerName": "Offset"},
            {"field": "student", "headerName": "Student"},
            {"field": "status", "headerName": "Status"},
        ],
        defaultColDef={
            "sortable": True,
            "filter": True,
            "resizable": True,
        },
        dashGridOptions={
            "animateRows": False,
            "rowSelection": {"mode": "singleRow"},
        },
        style={
            "height": "170px",
            "width": "100%",
        },
    )


# =========================================================
# PAGE LAYOUT
# =========================================================


def create_layout(reference_map, historical_map, initial_rows=None):
    """Build the main application page."""

    gcp_table = create_gcp_table(initial_rows=initial_rows)

    return html.Div(
        className="app-container",
        children=[
            html.Div(
                className="app-header",
                children=[
                    html.Div(
                        children=[
                            html.Div(
                                "Historical Map GCP Collection",
                                className="app-title",
                            ),
                            html.Div(
                                "Reference ↔ Historical map alignment",
                                className="app-subtitle",
                            ),
                        ],
                    ),
                    html.Div(
                        "Prototype",
                        className="prototype-badge",
                    ),
                ],
            ),
            html.Div(
                className="maps-area",
                children=[
                    create_map_panel(
                        title="REFERENCE MAP",
                        subtitle=(
                            "Orthophoto / web map / reference raster"
                        ),
                        upload_id="reference-upload",
                        upload_label="+ Add Reference Layer",
                        opacity_id="reference-opacity",
                        map_component=reference_map,
                        status_id="reference-upload-status",
                    ),
                    create_map_panel(
                        title="HISTORICAL MAP",
                        subtitle="Historical GeoTIFF / COG",
                        upload_id="historical-upload",
                        upload_label="+ Upload Historical TIFF",
                        opacity_id="historical-opacity",
                        map_component=historical_map,
                        status_id="historical-upload-status",
                    ),
                ],
            ),
            create_gcp_controls(),
            html.Div(
                className="table-section",
                children=[
                    html.Div(
                        "CONTROL POINTS",
                        className="table-title",
                    ),
                    gcp_table,
                ],
            ),

            # GCP workflow stores.
            dcc.Store(id="gcp-pending", data=None),
            dcc.Store(id="gcp-records", data=initial_rows or []),
            dcc.Store(id="gcp-selected-id", data=None),
            dcc.Store(id="gcp-drag-event", data=None),
            dcc.Store(id="gcp-collection-active", data=False),
        ],
    )
