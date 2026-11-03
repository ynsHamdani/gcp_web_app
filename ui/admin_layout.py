from __future__ import annotations

from dash import dcc, html
import dash_ag_grid as dag

from maps.admin_gcp import build_admin_gcp_row


_BASE_BUTTON = {
    "padding": "8px 12px",
    "border": "1px solid #cbd5e1",
    "borderRadius": "7px",
    "background": "#ffffff",
    "cursor": "pointer",
    "fontSize": "13px",
}
_PRIMARY_BUTTON = {
    **_BASE_BUTTON,
    "background": "#1d4ed8",
    "border": "1px solid #1d4ed8",
    "color": "white",
}
_DANGER_BUTTON = {
    **_BASE_BUTTON,
    "color": "#b91c1c",
    "border": "1px solid #fecaca",
}
_DISABLED_BUTTON = {**_BASE_BUTTON, "opacity": 0.55, "cursor": "not-allowed"}


def create_admin_layout(
    *,
    reference_map,
    historical_map,
    records: list[dict] | None = None,
    historical_options: list[dict] | None = None,
    contributor_options: list[dict] | None = None,
    layer_state: dict | None = None,
    reference_layer_options: list[dict] | None = None,
    historical_available_options: list[dict] | None = None,
    selected_reference_layer_id: str | None = None,
    selected_historical_layer_id: str | None = None,
    unavailable_layers: list[str] | None = None,
    csrf_token: str = "",
    admin_username: str = "Administrator",
):
    """Build the administrator GCP workspace with layer management/collection."""

    records = records or []
    layer_state = layer_state or {}
    unavailable_layers = unavailable_layers or []
    historical_options = historical_options or []
    contributor_options = contributor_options or []
    reference_layer_options = reference_layer_options or []
    historical_available_options = historical_available_options or []

    table_columns = [
        {"field": "gcp_id", "headerName": "GCP", "width": 105},
        {"field": "student_username", "headerName": "Contributor", "width": 155},
        {"field": "contributor_role", "headerName": "Role", "width": 95},
        {"field": "historical_layer_name", "headerName": "Historical layer", "width": 190},
        {"field": "reference_layer_name", "headerName": "Reference layer", "width": 190},
        {"field": "offset_m", "headerName": "Offset (m)", "width": 105},
        {"field": "reference_raster_available", "headerName": "Reference raster", "width": 125},
        {"field": "historical_raster_available", "headerName": "Historical raster", "width": 130},
        {"field": "status", "headerName": "Status", "width": 100},
        {"field": "recorded_at", "headerName": "Recorded", "width": 180},
    ]

    table = dag.AgGrid(
        id="admin-gcp-table",
        rowData=[build_admin_gcp_row(record) for record in records],
        columnDefs=table_columns,
        defaultColDef={
            "sortable": True,
            "filter": True,
            "resizable": True,
            "minWidth": 90,
        },
        dashGridOptions={
            "animateRows": False,
            "rowSelection": {"mode": "singleRow"},
            "suppressRowClickSelection": False,
        },
        style={"height": "265px", "width": "100%"},
    )

    card_style = {
        "minWidth": "0",
        "border": "1px solid #dbe2ea",
        "borderRadius": "10px",
        "background": "#ffffff",
        "padding": "12px",
    }
    map_style = {"height": "350px", "width": "100%"}
    field_label = {"fontWeight": "600", "fontSize": "12px", "display": "block", "marginBottom": "5px"}
    muted = {"fontSize": "12px", "color": "#64748b"}
    upload_box = {
        "border": "1px dashed #94a3b8",
        "borderRadius": "8px",
        "padding": "13px",
        "background": "#f8fafc",
        "textAlign": "center",
        "fontSize": "12px",
        "color": "#334155",
        "cursor": "pointer",
    }

    collection_ready = bool(selected_reference_layer_id and selected_historical_layer_id)

    return html.Div(
        className="app-container admin-container",
        style={
            "maxWidth": "1800px",
            "margin": "0 auto",
            "padding": "12px 18px 24px",
            "background": "#f5f7fb",
            "minHeight": "100vh",
            "boxSizing": "border-box",
        },
        children=[
            html.Header(
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "space-between",
                    "gap": "16px",
                    "flexWrap": "wrap",
                    "padding": "8px 2px 12px",
                },
                children=[
                    html.Div(
                        children=[
                            html.H2("GCP Workspace", style={"margin": "0", "fontSize": "22px", "color": "#172033"}),
                            html.Div(
                                f"Signed in as {admin_username} · Administrator",
                                style={"fontSize": "12px", "color": "#64748b", "marginTop": "3px"},
                            ),
                        ]
                    ),
                    html.Div(
                        style={"display": "flex", "alignItems": "center", "gap": "15px", "flexWrap": "wrap"},
                        children=[
                            html.Nav(
                                style={"display": "flex", "gap": "14px", "fontSize": "13px", "flexWrap": "wrap"},
                                children=[
                                    html.A("Add a GCP", href="#admin-add-gcp-panel", style={"color": "#1d4ed8", "fontWeight": "600"}),
                                    html.A("Filter GCPs", href="#admin-filter-panel", style={"color": "#334155"}),
                                    html.A("Maps", href="#admin-maps", style={"color": "#334155"}),
                                    html.A("GCP records", href="#admin-records", style={"color": "#334155"}),
                                ],
                            ),
                            html.Form(
                                action="/logout",
                                method="post",
                                style={"display": "inline"},
                                children=[
                                    dcc.Input(type="hidden", name="csrf_token", value=csrf_token or ""),
                                    html.Button("Log out", type="submit", style=_BASE_BUTTON),
                                ],
                            ),
                        ],
                    ),
                ],
            ),

            # Step 2: choose shared layers or upload new GeoTIFFs.
            html.Section(
                id="admin-add-gcp-panel",
                style={**card_style, "marginBottom": "12px"},
                children=[
                    html.Div(
                        style={"display": "flex", "justifyContent": "space-between", "alignItems": "baseline", "gap": "12px", "flexWrap": "wrap"},
                        children=[
                            html.H3("Add a GCP", style={"margin": "0", "fontSize": "17px", "color": "#172033"}),
                            html.Span("Select a reference and historical layer before collecting points", style=muted),
                        ],
                    ),
                    html.Div(
                        style={"display": "grid", "gridTemplateColumns": "minmax(300px, 1.1fr) minmax(300px, 1fr)", "gap": "14px", "marginTop": "12px"},
                        children=[
                            html.Div(
                                style={"background": "#f8fafc", "border": "1px solid #e2e8f0", "borderRadius": "8px", "padding": "12px", "minWidth": "0"},
                                children=[
                                    html.Div("Option A · Use existing layers", style={"fontWeight": "700", "fontSize": "13px", "marginBottom": "4px"}),
                                    html.Div("Recommended. Only available rasters are listed; OpenStreetMap is also available as a reference basemap.", style=muted),
                                    html.Div(
                                        style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "10px", "marginTop": "10px"},
                                        children=[
                                            html.Div(
                                                children=[
                                                    html.Label("Select reference layer", style=field_label),
                                                    dcc.Dropdown(
                                                        id="admin-reference-existing-select",
                                                        options=reference_layer_options,
                                                        value=selected_reference_layer_id,
                                                        searchable=True,
                                                        clearable=True,
                                                        placeholder="Choose a reference layer",
                                                    ),
                                                ]
                                            ),
                                            html.Div(
                                                children=[
                                                    html.Label("Select historical layer", style=field_label),
                                                    dcc.Dropdown(
                                                        id="admin-historical-existing-select",
                                                        options=historical_available_options,
                                                        value=selected_historical_layer_id,
                                                        searchable=True,
                                                        clearable=True,
                                                        placeholder="Choose a historical layer",
                                                    ),
                                                ]
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"display": "flex", "alignItems": "center", "gap": "10px", "marginTop": "10px", "flexWrap": "wrap"},
                                        children=[
                                            html.Button("Load selected layers", id="admin-load-selected-layers", n_clicks=0, style=_PRIMARY_BUTTON),
                                            html.Span(id="admin-layer-load-status", children="Available layers are ready to select.", style=muted),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                style={"background": "#f8fafc", "border": "1px solid #e2e8f0", "borderRadius": "8px", "padding": "12px", "minWidth": "0"},
                                children=[
                                    html.Div("Option B · Upload new layers", style={"fontWeight": "700", "fontSize": "13px", "marginBottom": "4px"}),
                                    html.Div("Upload a reference GeoTIFF, a historical GeoTIFF, or both. Files go through the existing COG conversion and registration pipeline.", style=muted),
                                    html.Div(
                                        style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "10px", "marginTop": "10px"},
                                        children=[
                                            html.Div(
                                                children=[
                                                    html.Label("Reference GeoTIFF", style=field_label),
                                                    dcc.Upload(
                                                        id="admin-reference-upload",
                                                        children=html.Div("Choose or drop reference .tif/.tiff", style=upload_box),
                                                        accept=".tif,.tiff,image/tiff",
                                                        multiple=False,
                                                    ),
                                                ]
                                            ),
                                            html.Div(
                                                children=[
                                                    html.Label("Historical GeoTIFF", style=field_label),
                                                    dcc.Upload(
                                                        id="admin-historical-upload",
                                                        children=html.Div("Choose or drop historical .tif/.tiff", style=upload_box),
                                                        accept=".tif,.tiff,image/tiff",
                                                        multiple=False,
                                                    ),
                                                ]
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"display": "flex", "alignItems": "center", "gap": "10px", "marginTop": "10px", "flexWrap": "wrap"},
                                        children=[
                                            html.Button("Upload selected file(s)", id="admin-upload-layers", n_clicks=0, style=_BASE_BUTTON),
                                            html.Span(id="admin-upload-status", children="No new files selected.", style=muted),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        id="admin-unavailable-layer-note",
                        children=("Unavailable layers are retained in the database but are not offered for loading: " + "; ".join(unavailable_layers)) if unavailable_layers else "",
                        style={"fontSize": "11px", "color": "#92400e", "marginTop": "9px"},
                    ),
                ],
            ),

            # GCP placement and confirmation controls.
            html.Section(
                style={**card_style, "marginBottom": "12px"},
                children=[
                    html.Div(
                        style={"display": "flex", "alignItems": "center", "gap": "8px", "flexWrap": "wrap"},
                        children=[
                            html.Strong("Collection tools", style={"fontSize": "13px"}),
                            html.Button("Add GCP", id="admin-add-gcp-button", n_clicks=0, disabled=not collection_ready, style=_PRIMARY_BUTTON if collection_ready else _DISABLED_BUTTON),
                            html.Button("Confirm GCP", id="admin-confirm-gcp-button", n_clicks=0, disabled=True, style=_BASE_BUTTON),
                            html.Button("Cancel", id="admin-cancel-gcp-button", n_clicks=0, disabled=True, style=_BASE_BUTTON),
                            html.Span("Click the reference map, then drag the historical marker to refine its position.", style=muted),
                        ],
                    ),
                    html.Div(
                        id="admin-gcp-collection-status",
                        children=("Choose and load both layers to enable GCP collection." if not collection_ready else "Layers loaded. Click Add GCP to start collecting."),
                        role="status",
                        style={"fontSize": "12px", "color": "#334155", "marginTop": "8px"},
                    ),
                ],
            ),

            html.Section(
                id="admin-filter-panel",
                style={**card_style, "marginBottom": "12px"},
                children=[
                    html.Div(
                        style={"display": "grid", "gridTemplateColumns": "minmax(220px, 1fr) minmax(220px, 1fr) auto", "gap": "12px", "alignItems": "end"},
                        children=[
                            html.Div(
                                children=[
                                    html.Label("Contributor", style=field_label),
                                    dcc.Dropdown(
                                        id="admin-contributor-filter",
                                        options=[{"label": "All contributors", "value": "all"}, *contributor_options],
                                        value="all",
                                        clearable=False,
                                        searchable=True,
                                        placeholder="Select a student or administrator",
                                    ),
                                ]
                            ),
                            html.Div(
                                children=[
                                    html.Label("Historical layer", style=field_label),
                                    dcc.Dropdown(
                                        id="admin-historical-filter",
                                        options=[{"label": "All historical layers", "value": "all"}, *historical_options],
                                        value="all",
                                        clearable=False,
                                        searchable=True,
                                        placeholder="Select a historical layer",
                                    ),
                                ]
                            ),
                            html.Div(
                                style={"display": "flex", "gap": "7px", "flexWrap": "wrap"},
                                children=[
                                    html.Button("Apply filters", id="admin-apply-filter", n_clicks=0, style=_PRIMARY_BUTTON),
                                    html.Button("Refresh", id="admin-refresh", n_clicks=0, style=_BASE_BUTTON),
                                    html.Button("Delete selected", id="admin-delete-gcp", n_clicks=0, style=_DANGER_BUTTON),
                                    html.Button("Export CSV", id="admin-export-gcps", n_clicks=0, style=_BASE_BUTTON),
                                    dcc.Download(id="admin-gcp-download"),
                                ],
                            ),
                        ],
                    ),
                    html.Div(id="admin-gcp-status", children=f"Loaded {len(records)} GCP(s).", role="status", style={"fontSize": "12px", "color": "#334155", "marginTop": "9px"}),
                    html.Div(
                        id="admin-raster-status",
                        children=("Unavailable raster(s): " + "; ".join(unavailable_layers)) if unavailable_layers else "All registered raster files and map services are available.",
                        role="status",
                        style={"fontSize": "12px", "color": "#92400e" if unavailable_layers else "#166534", "marginTop": "4px"},
                    ),
                ],
            ),

            html.Section(
                id="admin-maps",
                style={"display": "grid", "gridTemplateColumns": "repeat(2, minmax(0, 1fr))", "gap": "12px", "marginBottom": "12px"},
                children=[
                    html.Div(style=card_style, children=[html.H3("Reference map", style={"margin": "0 0 8px", "fontSize": "15px"}), html.Div(reference_map, style=map_style)]),
                    html.Div(style=card_style, children=[html.H3("Historical map", style={"margin": "0 0 8px", "fontSize": "15px"}), html.Div(historical_map, style=map_style)]),
                ],
            ),

            html.Section(
                id="admin-records",
                style=card_style,
                children=[
                    html.Div(
                        style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "10px", "marginBottom": "8px"},
                        children=[
                            html.H3("GCP records", style={"margin": "0", "fontSize": "15px"}),
                            html.Span("Select a row to zoom both maps to that GCP", style=muted),
                        ],
                    ),
                    table,
                ],
            ),

            # State shared by the Step 1 workspace and the Step 2 collection flow.
            dcc.Store(id="admin-gcp-records", data=records),
            dcc.Store(id="admin-layer-state", data=layer_state),
            dcc.Store(id="admin-selection-layer-state", data=layer_state),
            dcc.Store(
                id="admin-loaded-layer-selection",
                data={
                    "reference_db_layer_id": str(selected_reference_layer_id) if selected_reference_layer_id else None,
                    "historical_db_layer_id": str(selected_historical_layer_id) if selected_historical_layer_id else None,
                },
            ),
            dcc.Store(id="admin-gcp-pending", data=None),
            dcc.Store(id="admin-gcp-collection-active", data=False),
            dcc.Store(id="admin-gcp-drag-event", data=None),
            dcc.Store(id="admin-gcp-collection-revision", data=0),
        ],
    )
