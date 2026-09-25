from dash import html
import dash_ag_grid as dag

from ui.map_panels import create_map_panel
from ui.controls import bottom_controls


def create_layout(
    reference_map,
    historical_map,
):

    gcp_table = dag.AgGrid(
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


    return html.Div(
        className="app-container",
        children=[

            # ---------------------------------------------
            # HEADER
            # ---------------------------------------------

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


            # ---------------------------------------------
            # MAPS
            # ---------------------------------------------

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


            # ---------------------------------------------
            # GCP CONTROLS
            # ---------------------------------------------

            bottom_controls(),


            # ---------------------------------------------
            # GCP TABLE
            # ---------------------------------------------

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