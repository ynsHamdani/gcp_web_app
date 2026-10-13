from __future__ import annotations

from dash import dcc, html
import dash_ag_grid as dag

from maps.admin_gcp import build_admin_gcp_markers, build_admin_gcp_row
from services.layer_availability import annotate_gcp_raster_availability


_BASE_BUTTON = {
    "padding": "8px 12px",
    "border": "1px solid #cbd5e1",
    "borderRadius": "6px",
    "background": "#ffffff",
    "cursor": "pointer",
}
_PRIMARY_BUTTON = {
    **_BASE_BUTTON,
    "background": "#1d4ed8",
    "border": "1px solid #1d4ed8",
    "color": "white",
}


def _table_rows(records: list[dict]) -> list[dict]:
    return [build_admin_gcp_row(record) for record in annotate_gcp_raster_availability(records)]


def _user_rows(users: list[dict]) -> list[dict]:
    return [
        {
            "user_id": user.get("user_id"),
            "username": user.get("username"),
            "email": user.get("email"),
            "role": user.get("user_role"),
            "active": "yes" if user.get("is_active") else "no",
            "created_at": user.get("created_at", ""),
        }
        for user in users
    ]


def create_admin_layout(
    *,
    reference_map,
    historical_map,
    records: list[dict] | None = None,
    historical_options: list[dict] | None = None,
    student_options: list[dict] | None = None,
    users: list[dict] | None = None,
    unavailable_layers: list[str] | None = None,
    csrf_token: str = "",
):
    """Create the admin dashboard. Data passed here is loaded server-side."""

    records = records or []
    users = users or []
    unavailable_layers = unavailable_layers or []
    user_select_options = student_options or []
    active_students = [u for u in users if bool(u.get("is_active"))]

    gcp_columns = [
        {"field": "gcp_id", "headerName": "GCP", "width": 105},
        {"field": "student_username", "headerName": "Student", "width": 130},
        {"field": "historical_layer_name", "headerName": "Historical layer", "width": 180},
        {"field": "reference_layer_name", "headerName": "Reference layer", "width": 180},
        {"field": "offset_m", "headerName": "Offset (m)", "width": 110},
        {"field": "reference_raster_available", "headerName": "Reference raster", "width": 130},
        {"field": "historical_raster_available", "headerName": "Historical raster", "width": 135},
        {"field": "status", "headerName": "Status", "width": 110},
    ]
    user_columns = [
        {"field": "user_id", "headerName": "ID", "width": 85},
        {"field": "username", "headerName": "Username", "width": 150},
        {"field": "email", "headerName": "Email", "width": 240},
        {"field": "active", "headerName": "Active", "width": 85},
        {"field": "created_at", "headerName": "Created", "width": 190},
    ]

    gcp_table = dag.AgGrid(
        id="admin-gcp-table",
        rowData=_table_rows(records),
        columnDefs=gcp_columns,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={"animateRows": False, "rowSelection": {"mode": "singleRow"}},
        style={"height": "300px", "width": "100%"},
    )
    user_table = dag.AgGrid(
        id="admin-user-table",
        rowData=_user_rows(users),
        columnDefs=user_columns,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={"animateRows": False, "rowSelection": {"mode": "singleRow"}},
        style={"height": "210px", "width": "100%"},
    )

    map_panel_style = {
        "minWidth": "0",
        "height": "450px",
        "border": "1px solid #dbe2ea",
        "borderRadius": "8px",
        "padding": "10px",
    }

    return html.Div(
        className="app-container admin-container",
        children=[
            html.Div(
                className="app-header",
                children=[
                    html.Div(
                        children=[
                            html.Div("Administration", className="app-title"),
                            html.Div("Shared GCPs, raster availability, and student accounts", className="app-subtitle"),
                        ]
                    ),
                    html.Div(
                        children=[
                            html.Span("Administrator", style={"fontSize": "12px", "fontWeight": "600", "marginRight": "10px"}),
                            html.Form(
                                action="/logout",
                                method="post",
                                children=[
                                    dcc.Input(type="hidden", name="csrf_token", value=csrf_token or ""),
                                    html.Button("Log out", type="submit", style=_BASE_BUTTON),
                                ],
                                style={"display": "inline"},
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center", "gap": "8px"},
                    ),
                ],
            ),
            html.Div(
                children=[
                    html.Label("Student"),
                    dcc.Dropdown(
                        id="admin-student-filter",
                        options=[{"label": "All students", "value": "all"}, *user_select_options],
                        value="all",
                        clearable=False,
                    ),
                    html.Label("Historical layer", style={"marginTop": "8px"}),
                    dcc.Dropdown(
                        id="admin-historical-filter",
                        options=[{"label": "All historical layers", "value": "all"}, *(historical_options or [])],
                        value="all",
                        clearable=False,
                    ),
                    html.Div(
                        children=[
                            html.Button("Apply filters", id="admin-apply-filter", n_clicks=0, style=_PRIMARY_BUTTON),
                            html.Button("Refresh", id="admin-refresh", n_clicks=0, style=_BASE_BUTTON),
                            html.Button("Delete selected GCP", id="admin-delete-gcp", n_clicks=0, style={**_BASE_BUTTON, "color": "#b91c1c"}),
                            html.Button("Export filtered GCPs (CSV)", id="admin-export-gcps", n_clicks=0, style=_BASE_BUTTON),
                            dcc.Download(id="admin-gcp-download"),
                        ],
                        style={"display": "flex", "flexWrap": "wrap", "gap": "8px", "marginTop": "10px"},
                    ),
                    html.Div(id="admin-gcp-status", children=f"Loaded {len(records)} GCP(s).", style={"marginTop": "8px"}),
                    html.Div(
                        ("Raster files or map services unavailable: " + "; ".join(unavailable_layers)) if unavailable_layers else "All registered raster layers are available.",
                        id="admin-raster-status",
                        style={"marginTop": "6px", "color": "#92400e" if unavailable_layers else "#166534"},
                    ),
                ],
                style={"padding": "12px 0"},
            ),
            html.Div(
                children=[
                    html.Div(
                        [html.H3("Reference map"), html.Div(reference_map, style={"height": "390px"})],
                        style={**map_panel_style, "height": "auto"},
                    ),
                    html.Div(
                        [html.H3("Historical map"), html.Div(historical_map, style={"height": "390px"})],
                        style={**map_panel_style, "height": "auto"},
                    ),
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(2, minmax(0, 1fr))", "gap": "12px"},
            ),
            html.Div([html.H3("All GCPs"), gcp_table], style={"marginTop": "18px"}),
            html.Hr(),
            html.Div(
                children=[
                    html.H2("Student accounts"),
                    html.Div("New temporary passwords are displayed only in this response. Share them securely with the student."),
                    html.Div(
                        children=[
                            dcc.Input(id="new-student-username", placeholder="Username", type="text", maxLength=100),
                            dcc.Input(id="new-student-email", placeholder="Email", type="email", maxLength=320, style={"minWidth": "250px"}),
                            html.Button("Create student", id="admin-create-student", n_clicks=0, style=_PRIMARY_BUTTON),
                        ],
                        style={"display": "flex", "flexWrap": "wrap", "gap": "8px", "margin": "10px 0"},
                    ),
                    html.Div(id="admin-user-result", role="status"),
                    html.Div(id="admin-user-temp-password", style={"fontFamily": "monospace", "fontWeight": "600", "margin": "8px 0", "overflowWrap": "anywhere"}),
                    html.H3("Update or deactivate a student"),
                    dcc.Dropdown(id="admin-user-select", options=user_select_options, placeholder="Select a student account", clearable=True),
                    html.Div(
                        children=[
                            dcc.Input(id="edit-student-username", placeholder="Username", type="text", maxLength=100),
                            dcc.Input(id="edit-student-email", placeholder="Email", type="email", maxLength=320, style={"minWidth": "250px"}),
                            html.Button("Save details", id="admin-save-student", n_clicks=0, style=_BASE_BUTTON),
                            html.Button("Generate new temporary password", id="admin-reset-student-password", n_clicks=0, style=_BASE_BUTTON),
                            html.Button("Deactivate/reactivate", id="admin-toggle-student", n_clicks=0, style=_BASE_BUTTON),
                        ],
                        style={"display": "flex", "flexWrap": "wrap", "gap": "8px", "margin": "10px 0"},
                    ),
                    user_table,
                    dcc.Store(id="admin-gcp-records", data=records),
                    dcc.Store(id="admin-layer-metadata", data=unavailable_layers),
                ],
                style={"marginTop": "18px", "paddingBottom": "28px"},
            ),
        ],
    )
