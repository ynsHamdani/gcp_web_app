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


def create_admin_layout(
    *,
    reference_map,
    historical_map,
    records: list[dict] | None = None,
    historical_options: list[dict] | None = None,
    contributor_options: list[dict] | None = None,
    layer_state: dict | None = None,
    unavailable_layers: list[str] | None = None,
    csrf_token: str = "",
    admin_username: str = "Administrator",
):
    """Build the compact Admin GCP Workspace; both maps remain mounted."""

    records = records or []
    layer_state = layer_state or {}
    unavailable_layers = unavailable_layers or []
    historical_options = historical_options or []
    contributor_options = contributor_options or []

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
        "padding": "10px",
    }
    map_style = {"height": "350px", "width": "100%"}

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
            # Header and compact section navigation.
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
                            html.H2(
                                "GCP Workspace",
                                style={"margin": "0", "fontSize": "22px", "color": "#172033"},
                            ),
                            html.Div(
                                f"Signed in as {admin_username} · Administrator",
                                style={"fontSize": "12px", "color": "#64748b", "marginTop": "3px"},
                            ),
                        ]
                    ),
                    html.Div(
                        style={"display": "flex", "alignItems": "center", "gap": "12px", "flexWrap": "wrap"},
                        children=[
                            html.Nav(
                                style={"display": "flex", "gap": "14px", "fontSize": "13px"},
                                children=[
                                    html.A("Filter GCPs", href="#admin-filter-panel", style={"color": "#1d4ed8", "fontWeight": "600"}),
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

            # Filter controls are kept in one compact, responsive toolbar.
            html.Section(
                id="admin-filter-panel",
                style={**card_style, "marginBottom": "12px"},
                children=[
                    html.Div(
                        style={
                            "display": "grid",
                            "gridTemplateColumns": "minmax(220px, 1fr) minmax(220px, 1fr) auto",
                            "gap": "12px",
                            "alignItems": "end",
                        },
                        children=[
                            html.Div(
                                children=[
                                    html.Label("Contributor", style={"fontWeight": "600", "fontSize": "12px"}),
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
                                    html.Label("Historical layer", style={"fontWeight": "600", "fontSize": "12px"}),
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
                    html.Div(
                        id="admin-gcp-status",
                        children=f"Loaded {len(records)} GCP(s).",
                        role="status",
                        style={"fontSize": "12px", "color": "#334155", "marginTop": "9px"},
                    ),
                    html.Div(
                        id="admin-raster-status",
                        children=(
                            "Unavailable raster(s): " + "; ".join(unavailable_layers)
                            if unavailable_layers
                            else "All registered raster files and map services are available."
                        ),
                        role="status",
                        style={
                            "fontSize": "12px",
                            "color": "#92400e" if unavailable_layers else "#166534",
                            "marginTop": "4px",
                        },
                    ),
                ],
            ),

            # The two maps stay mounted while filters and table selection change.
            html.Section(
                id="admin-maps",
                style={
                    "display": "grid",
                    "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
                    "gap": "12px",
                    "marginBottom": "12px",
                },
                children=[
                    html.Div(
                        style=card_style,
                        children=[html.H3("Reference map", style={"margin": "0 0 8px", "fontSize": "15px"}), html.Div(reference_map, style=map_style)],
                    ),
                    html.Div(
                        style=card_style,
                        children=[html.H3("Historical map", style={"margin": "0 0 8px", "fontSize": "15px"}), html.Div(historical_map, style=map_style)],
                    ),
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
                            html.Span("Select a row to zoom both maps to that GCP", style={"fontSize": "11px", "color": "#64748b"}),
                        ],
                    ),
                    table,
                ],
            ),

            dcc.Store(id="admin-gcp-records", data=records),
            dcc.Store(id="admin-layer-state", data=layer_state),
        ],
    )
