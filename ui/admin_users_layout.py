from __future__ import annotations

from dash import dcc, html
import dash_ag_grid as dag

from ui.admin_nav import create_page_shell


_CARD = {"background": "#fff", "border": "1px solid #dbe2ea", "borderRadius": "11px", "padding": "14px", "minWidth": "0"}
_LABEL = {"display": "block", "fontSize": "12px", "fontWeight": "650", "marginBottom": "5px", "color": "#334155"}
_INPUT = {"width": "100%", "boxSizing": "border-box", "padding": "9px 10px", "border": "1px solid #cbd5e1", "borderRadius": "7px", "fontSize": "13px"}
_BUTTON = {"padding": "9px 12px", "border": "1px solid #cbd5e1", "borderRadius": "7px", "background": "#fff", "fontSize": "12px", "fontWeight": "600", "cursor": "pointer"}
_PRIMARY = {**_BUTTON, "background": "#1d4ed8", "borderColor": "#1d4ed8", "color": "white"}
_DANGER = {**_BUTTON, "color": "#b91c1c", "borderColor": "#fecaca"}


def create_admin_users_layout(*, users: list[dict], admin_username: str, csrf_token: str):
    columns = [
        {"field": "user_id", "headerName": "ID", "width": 75},
        {"field": "username", "headerName": "Username", "width": 155},
        {"field": "email", "headerName": "Email", "width": 230},
        {"field": "user_role", "headerName": "Role", "width": 95},
        {"field": "account_status", "headerName": "Account", "width": 105},
        {"field": "must_change_password", "headerName": "Password reset required", "width": 165},
        {"field": "gcp_count", "headerName": "GCP contributions", "width": 140},
        {"field": "created_at", "headerName": "Created", "width": 180},
    ]
    rows = [{**u, "account_status": "Active" if u.get("is_active") else "Deactivated", "must_change_password": "Yes" if u.get("must_change_password") else "No"} for u in users]
    table = dag.AgGrid(
        id="admin-users-table", rowData=rows, columnDefs=columns,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={"rowSelection": {"mode": "singleRow"}, "animateRows": False},
        style={"height": "410px", "width": "100%"},
    )

    create_card = html.Section(
        style=_CARD,
        children=[
            html.H3("Create a student account", style={"fontSize": "15px", "margin": "0 0 10px"}),
            html.P("Registration is administrator-controlled. A strong temporary password is generated and must be changed on first sign-in.", style={"fontSize": "12px", "color": "#64748b", "margin": "0 0 12px"}),
            html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(2,minmax(0,1fr))", "gap": "10px"}, children=[
                html.Div([html.Label("Username", style=_LABEL), dcc.Input(id="admin-new-user-username", type="text", maxLength=100, style=_INPUT, placeholder="student.username")]),
                html.Div([html.Label("Email", style=_LABEL), dcc.Input(id="admin-new-user-email", type="email", maxLength=320, style=_INPUT, placeholder="student@example.org")]),
            ]),
            html.Button("Create student account", id="admin-create-user", n_clicks=0, style={**_PRIMARY, "marginTop": "10px"}),
            html.Div(id="admin-user-create-status", role="status", style={"fontSize": "12px", "marginTop": "8px"}),
        ],
    )

    roster_card = html.Section(
        style=_CARD,
        children=[
            html.H3("Import a student roster", style={"fontSize": "15px", "margin": "0 0 8px"}),
            html.P("CSV format: username,email. Up to 1,000 rows per import. The preview checks formatting and duplicates before creation.", style={"fontSize": "12px", "color": "#64748b", "margin": "0 0 10px"}),
            dcc.Upload(id="admin-user-roster-upload", children=html.Div("Choose or drop student_roster.csv", style={"border": "1px dashed #94a3b8", "borderRadius": "8px", "padding": "13px", "textAlign": "center", "fontSize": "12px", "cursor": "pointer"}), accept=".csv,text/csv", multiple=False),
            html.Div(id="admin-user-roster-status", role="status", style={"fontSize": "12px", "marginTop": "8px"}),
            dag.AgGrid(id="admin-user-roster-preview", rowData=[], columnDefs=[{"field": "line", "headerName": "CSV row", "width": 85}, {"field": "username", "headerName": "Username", "width": 150}, {"field": "email", "headerName": "Email", "width": 220}, {"field": "error", "headerName": "Validation", "flex": 1}], defaultColDef={"resizable": True}, dashGridOptions={"domLayout": "autoHeight", "animateRows": False}, style={"width": "100%", "marginTop": "8px"}),
            html.Button("Import valid students", id="admin-import-user-roster", n_clicks=0, style={**_PRIMARY, "marginTop": "10px"}),
        ],
    )

    manage_card = html.Section(
        style=_CARD,
        children=[
            html.H3("Manage selected student", style={"fontSize": "15px", "margin": "0 0 5px"}),
            html.P("Select a student row. Administrator accounts are displayed but are not editable here.", style={"fontSize": "12px", "color": "#64748b", "margin": "0 0 12px"}),
            html.Div(id="admin-user-selection-status", style={"fontSize": "12px", "color": "#64748b", "marginBottom": "8px"}, children="No account selected."),
            html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(2,minmax(0,1fr))", "gap": "10px"}, children=[
                html.Div([html.Label("Username", style=_LABEL), dcc.Input(id="admin-edit-user-username", type="text", style=_INPUT, maxLength=100)]),
                html.Div([html.Label("Email", style=_LABEL), dcc.Input(id="admin-edit-user-email", type="email", style=_INPUT, maxLength=320)]),
            ]),
            html.Div(style={"display": "flex", "gap": "7px", "flexWrap": "wrap", "marginTop": "10px"}, children=[
                html.Button("Save profile", id="admin-update-user", n_clicks=0, style=_BUTTON),
                html.Button("Reset password", id="admin-reset-user-password", n_clicks=0, style=_BUTTON),
                html.Button("Deactivate / reactivate", id="admin-toggle-user-active", n_clicks=0, style=_DANGER),
            ]),
            html.Div(id="admin-user-manage-status", role="status", style={"fontSize": "12px", "marginTop": "8px"}),
            html.Div(id="admin-user-one-time-credentials", role="status", style={"fontSize": "12px", "marginTop": "8px", "background": "#eff6ff", "padding": "9px", "borderRadius": "7px", "overflowWrap": "anywhere"}),
        ],
    )

    return create_page_shell(
        title="User Management",
        subtitle="Create and manage student accounts while preserving contribution history.",
        admin_username=admin_username, csrf_token=csrf_token, active_page="users",
        children=[
            html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(2,minmax(0,1fr))", "gap": "12px", "marginBottom": "12px"}, children=[create_card, roster_card]),
            manage_card,
            html.Section(style={**_CARD, "marginTop": "12px"}, children=[
                html.Div(style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "gap": "8px", "marginBottom": "10px"}, children=[html.H3("Accounts", style={"fontSize": "15px", "margin": 0}), html.Span(f"{len(users)} account(s)", style={"fontSize": "11px", "color": "#64748b"})]),
                table,
            ]),
            dcc.Store(id="admin-user-roster-store", data=[]),
            dcc.Store(id="admin-users-revision", data=0),
            dcc.Download(id="admin-user-credentials-download"),
        ],
    )
