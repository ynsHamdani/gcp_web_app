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
    """Create one complete map panel without any cross-module dependency."""

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
                        marks={
                            0: "0",
                            50: "50",
                            100: "100",
                        },
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
# GCP TABLE
# =========================================================


def create_gcp_table():
    """Create the control-point table used below the maps."""

    return dag.AgGrid(
        id="gcp-table",
        rowData=[],
        columnDefs=[
            {
                "field": "gcp_id",
                "headerName": "GCP",
            },
            {
                "field": "feature_type",
                "headerName": "Feature",
            },
            {
                "field": "reference",
                "headerName": "Reference",
            },
            {
                "field": "historical",
                "headerName": "Historical",
            },
            {
                "field": "offset",
                "headerName": "Offset",
            },
            {
                "field": "student",
                "headerName": "Student",
            },
            {
                "field": "status",
                "headerName": "Status",
            },
        ],
        defaultColDef={
            "sortable": True,
            "filter": True,
            "resizable": True,
        },
        dashGridOptions={
            "animateRows": False,
        },
        style={
            "height": "170px",
            "width": "100%",
        },
    )


# =========================================================
# PAGE LAYOUT
# =========================================================


def create_layout(reference_map, historical_map):
    """Build the main application page.

    This module is intentionally self-contained:
    - no ui.map_panels import
    - no import from ui.controls
    - no circular dependencies
    """

    gcp_table = create_gcp_table()

    return html.Div(
        className="app-container",
        children=[
            # -------------------------------------------------
            # HEADER
            # -------------------------------------------------

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

            # -------------------------------------------------
            # MAPS
            # -------------------------------------------------

            html.Div(
                className="maps-area",
                children=[
                    create_map_panel(
                        title="REFERENCE MAP",
                        subtitle="Orthophoto / web map / reference raster",
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

            # -------------------------------------------------
            # GCP AREA
            # -------------------------------------------------
            # The previous layout called bottom_controls(), but the
            # supplied controls.py contains no such function. We do
            # not create a fake control block here; the table remains
            # available and this keeps the module dependency clean.

            # -------------------------------------------------
            # GCP TABLE
            # -------------------------------------------------

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
        ],
    )
