from __future__ import annotations

from dash import dcc, html
import dash_ag_grid as dag

_CARD = {
    "background": "#fff", "border": "1px solid #dbe2ea", "borderRadius": "11px",
    "padding": "14px", "minWidth": "0",
}
_LABEL = {"display": "block", "fontSize": "12px", "fontWeight": "650", "marginBottom": "5px", "color": "#334155"}
_INPUT = {"width": "100%", "boxSizing": "border-box", "padding": "9px 10px", "border": "1px solid #cbd5e1", "borderRadius": "7px", "fontSize": "13px"}
_BUTTON = {"padding": "9px 12px", "border": "1px solid #1d4ed8", "borderRadius": "7px", "background": "#1d4ed8", "color": "white", "fontSize": "12px", "fontWeight": "650", "cursor": "pointer"}
_DANGER = {**_BUTTON, "background": "#fff", "color": "#b91c1c", "borderColor": "#fecaca"}


def create_super_admin_layout(*, users: list[dict], audit_rows: list[dict], username: str, csrf_token: str):
    account_columns = [
        {"field": "user_id", "headerName": "ID", "width": 75},
        {"field": "username", "headerName": "Username", "width": 165},
        {"field": "email", "headerName": "Email", "width": 230},
        {"field": "user_role", "headerName": "Role", "width": 125},
        {"field": "account_status", "headerName": "Account", "width": 110},
        {"field": "created_at", "headerName": "Created", "width": 180},
    ]
    accounts = [{**item, "account_status": "Active" if item.get("is_active") else "Deactivated"} for item in users]
    account_table = dag.AgGrid(
        id="super-admin-accounts-table", rowData=accounts, columnDefs=account_columns,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={"rowSelection": {"mode": "singleRow"}, "animateRows": False},
        style={"height": "330px", "width": "100%"},
    )

    audit_columns = [
        {"field": "created_at", "headerName": "When", "width": 190},
        {"field": "actor_username", "headerName": "Performed by", "width": 150},
        {"field": "action", "headerName": "Action", "width": 205},
        {"field": "target_username", "headerName": "Account", "width": 160},
        {"field": "details_text", "headerName": "Change details", "flex": 1, "minWidth": 260},
    ]
    audit_table = dag.AgGrid(
        id="super-admin-audit-table", rowData=audit_rows, columnDefs=audit_columns,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={"animateRows": False, "pagination": True, "paginationPageSize": 10},
        style={"height": "300px", "width": "100%"},
    )

    return html.Div(
        style={
            "height": "100vh",
            "minHeight": "0",
            "display": "flex",
            "flexDirection": "column",
            "overflow": "hidden",
            "background": "#f5f7fb",
            "color": "#172033",
            "fontFamily": "Arial, sans-serif",
        },
        children=[
            html.Header(
                style={"position": "relative", "flex": "0 0 auto", "zIndex": 10, "display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "12px", "padding": "12px 20px", "background": "#fff", "borderBottom": "1px solid #dbe2ea"},
                children=[
                    html.Div([
                        html.Div("Super Admin Console", style={"fontSize": "17px", "fontWeight": "800"}),
                        html.Div(f"{username} · Super Administrator", style={"fontSize": "11px", "color": "#64748b", "marginTop": "3px"}),
                    ]),
                    html.Div(style={"display": "flex", "alignItems": "center", "gap": "8px", "flexWrap": "wrap"}, children=[
                        html.A("GCP Workspace", href="/admin/", style={"fontSize": "12px", "fontWeight": "600", "color": "#334155", "textDecoration": "none"}),
                        html.A("User Management", href="/admin/users/", style={"fontSize": "12px", "fontWeight": "600", "color": "#334155", "textDecoration": "none"}),
                        html.Form(action="/logout", method="post", style={"display": "inline"}, children=[
                            dcc.Input(type="hidden", name="csrf_token", value=csrf_token or ""),
                            html.Button("Log out", type="submit", style={"padding": "8px 10px", "border": "1px solid #cbd5e1", "borderRadius": "7px", "background": "#fff", "fontSize": "12px", "cursor": "pointer"}),
                        ]),
                    ]),
                ],
            ),
            html.Main(
                id="super-admin-scroll-container",
                className="super-admin-scroll-container",
                style={
                    "width": "100%",
                    "maxWidth": "1500px",
                    "boxSizing": "border-box",
                    "margin": "0 auto",
                    "padding": "18px 18px 40px",
                    "flex": "1 1 auto",
                    "minHeight": "0",
                    "overflowY": "auto",
                    "overflowX": "hidden",
                    "overscrollBehavior": "contain",
                    "WebkitOverflowScrolling": "touch",
                },
                children=[
                html.H1("Privileged account management", style={"fontSize": "23px", "margin": "0 0 5px"}),
                html.P("Promote or demote accounts across Student, Admin and Super Admin. Existing student profile, roster and GCP workflows remain in User Management.", style={"fontSize": "13px", "color": "#64748b", "margin": "0 0 16px"}),
                html.Section(style={**_CARD, "marginBottom": "12px"}, children=[
                    html.H2("Create a privileged account", style={"fontSize": "15px", "margin": "0 0 8px"}),
                    html.P("A random temporary password is generated and shown once. The new account must change it at first sign-in.", style={"fontSize": "12px", "color": "#64748b", "margin": "0 0 12px"}),
                    html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(3,minmax(0,1fr))", "gap": "10px"}, children=[
                        html.Div([html.Label("Username", style=_LABEL), dcc.Input(id="super-admin-new-username", type="text", maxLength=100, style=_INPUT)]),
                        html.Div([html.Label("Email", style=_LABEL), dcc.Input(id="super-admin-new-email", type="email", maxLength=320, style=_INPUT)]),
                        html.Div([html.Label("Role", style=_LABEL), dcc.Dropdown(id="super-admin-new-role", options=[{"label": "Admin", "value": "admin"}, {"label": "Super Admin", "value": "super_admin"}], value="admin", clearable=False)]),
                    ]),
                    html.Div(style={"display": "flex", "alignItems": "end", "gap": "10px", "flexWrap": "wrap", "marginTop": "10px"}, children=[
                        html.Div([html.Label("Type CREATE PRIVILEGED ACCOUNT to confirm", style=_LABEL), dcc.Input(id="super-admin-create-confirmation", type="text", style={**_INPUT, "maxWidth": "360px"}, autoComplete="off")]),
                        html.Button("Create account", id="super-admin-create-account", n_clicks=0, style=_BUTTON),
                    ]),
                    html.Div(id="super-admin-create-status", role="status", style={"fontSize": "12px", "marginTop": "8px"}),
                    html.Div(id="super-admin-one-time-credentials", role="status", style={"fontSize": "12px", "marginTop": "8px", "background": "#eff6ff", "padding": "9px", "borderRadius": "7px", "overflowWrap": "anywhere"}),
                ]),
                html.Section(style={**_CARD, "marginBottom": "12px"}, children=[
                    html.H2("Manage accounts and roles", style={"fontSize": "15px", "margin": "0 0 5px"}),
                    html.P("Select any account to change its role or status. You cannot change your own role or account status, and the last active Super Admin is protected.", style={"fontSize": "12px", "color": "#64748b", "margin": "0 0 10px"}),
                    account_table,
                    html.Div(id="super-admin-selection-status", style={"fontSize": "12px", "color": "#64748b", "margin": "10px 0 8px"}, children="Select an account to manage."),
                    html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(3,minmax(0,1fr))", "gap": "10px", "alignItems": "end"}, children=[
                        html.Div([html.Label("Role", style=_LABEL), dcc.Dropdown(id="super-admin-edit-role", options=[{"label": "Student", "value": "student"}, {"label": "Admin", "value": "admin"}, {"label": "Super Admin", "value": "super_admin"}], value="student", clearable=False)]),
                        html.Div([html.Label("Account status", style=_LABEL), dcc.Dropdown(id="super-admin-edit-active", options=[{"label": "Active", "value": "active"}, {"label": "Deactivated", "value": "inactive"}], value="active", clearable=False)]),
                        html.Div([html.Label("Type APPLY PRIVILEGED CHANGE to confirm", style=_LABEL), dcc.Input(id="super-admin-edit-confirmation", type="text", style=_INPUT, autoComplete="off")]),
                    ]),
                    html.Button("Apply change", id="super-admin-apply-change", n_clicks=0, style={**_DANGER, "marginTop": "10px"}),
                    html.Div(id="super-admin-manage-status", role="status", style={"fontSize": "12px", "marginTop": "8px"}),
                ]),
                html.Section(style=_CARD, children=[
                    html.H2("Super Admin change audit", style={"fontSize": "15px", "margin": "0 0 8px"}),
                    html.P("Role and account-status changes made from this console are written in the same database transaction as the account update.", style={"fontSize": "12px", "color": "#64748b", "margin": "0 0 10px"}),
                    audit_table,
                ]),
                dcc.Store(id="super-admin-revision", data=0),
                ],
            ),
        ],
    )
