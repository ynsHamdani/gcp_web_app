from __future__ import annotations

from dash import dcc, html


_NAV_LINK = {
    "padding": "8px 11px",
    "borderRadius": "7px",
    "textDecoration": "none",
    "fontSize": "13px",
    "fontWeight": "600",
    "whiteSpace": "nowrap",
}


def create_admin_header(*, admin_username: str, csrf_token: str, active_page: str):
    pages = [
        ("workspace", "GCP Workspace", "/admin/"),
        ("users", "User Management", "/admin/users/"),
        ("config", "Configuration", "/admin/config/"),
    ]
    links = []
    for key, label, href in pages:
        active = key == active_page
        links.append(html.A(
            label,
            href=href,
            style={
                **_NAV_LINK,
                "background": "#dbeafe" if active else "transparent",
                "color": "#1d4ed8" if active else "#334155",
                "border": "1px solid #bfdbfe" if active else "1px solid transparent",
            },
            **{"aria-current": "page" if active else "false"},
        ))
    return html.Header(
        id="admin-global-header",
        style={
            "position": "fixed", "top": "0", "left": "0", "right": "0",
            "zIndex": "3000", "minHeight": "62px", "boxSizing": "border-box",
            "display": "flex", "alignItems": "center", "justifyContent": "space-between",
            "gap": "12px", "flexWrap": "wrap", "padding": "8px max(16px, calc((100vw - 1760px)/2))",
            "background": "rgba(255,255,255,0.97)", "backdropFilter": "blur(9px)",
            "borderBottom": "1px solid #dbe2ea", "boxShadow": "0 2px 8px #0f172a0b",
        },
        children=[
            html.Div([
                html.Div("Historical Map GCP", style={"fontWeight": "750", "fontSize": "17px", "color": "#172033"}),
                html.Div(f"{admin_username} · Administrator", style={"fontSize": "11px", "color": "#64748b"}),
            ]),
            html.Div(
                style={"display": "flex", "alignItems": "center", "gap": "5px", "flexWrap": "wrap"},
                children=[
                    html.Nav(links, style={"display": "flex", "gap": "3px", "flexWrap": "wrap"}),
                    html.Form(
                        action="/logout", method="post", style={"display": "inline", "marginLeft": "7px"},
                        children=[
                            dcc.Input(type="hidden", name="csrf_token", value=csrf_token or ""),
                            html.Button("Log out", type="submit", style={
                                "padding": "8px 11px", "border": "1px solid #cbd5e1", "borderRadius": "7px",
                                "background": "#fff", "fontSize": "12px", "cursor": "pointer",
                            }),
                        ],
                    ),
                ],
            ),
        ],
    )


def create_page_shell(*, title: str, subtitle: str, admin_username: str, csrf_token: str, active_page: str, children):
    return html.Div(
        style={"minHeight": "100vh", "background": "#f5f7fb", "color": "#172033", "fontFamily": "Arial, sans-serif"},
        children=[
            create_admin_header(admin_username=admin_username, csrf_token=csrf_token, active_page=active_page),
            html.Div(style={"height": "76px"}),
            html.Main(
                style={"maxWidth": "1760px", "margin": "0 auto", "padding": "14px 18px 32px", "boxSizing": "border-box"},
                children=[
                    html.Div([html.H1(title, style={"fontSize": "23px", "margin": "0 0 4px"}), html.P(subtitle, style={"fontSize": "13px", "color": "#64748b", "margin": "0 0 16px"})]),
                    *children,
                ],
            ),
        ],
    )


def create_workspace_header(*, admin_username: str, csrf_token: str):
    """Fixed global navigation plus in-page controls for the GCP workspace."""
    internal = [
        ("Add a GCP", "admin-add-gcp-panel", True),
        ("Filter GCPs", "admin-filter-panel", False),
        ("Maps", "admin-maps", False),
        ("GCP records", "admin-records", False),
    ]
    internal_links = [
        html.Button(label, type="button", **{"data-admin-nav": target, "className": "admin-nav-link" + (" is-active" if active else "")}, style={
            **_NAV_LINK,
            "background": "#dbeafe" if active else "transparent",
            "color": "#1d4ed8" if active else "#334155",
            "border": "1px solid #bfdbfe" if active else "1px solid transparent",
            "cursor": "pointer",
        }) for label, target, active in internal
    ]
    page_links = [
        html.A("Users", href="/admin/users/", style={**_NAV_LINK, "color": "#334155"}),
        html.A("Configuration", href="/admin/config/", style={**_NAV_LINK, "color": "#334155"}),
    ]
    return html.Header(
        id="admin-global-header",
        style={
            "position": "fixed", "top": "0", "left": "0", "right": "0",
            "zIndex": "3000", "minHeight": "62px", "boxSizing": "border-box",
            "display": "flex", "alignItems": "center", "justifyContent": "space-between",
            "gap": "10px", "flexWrap": "wrap", "padding": "8px max(14px, calc((100vw - 1760px)/2))",
            "background": "rgba(255,255,255,0.97)", "backdropFilter": "blur(9px)",
            "borderBottom": "1px solid #dbe2ea", "boxShadow": "0 2px 8px #0f172a0b",
        },
        children=[
            html.Div([
                html.Div("GCP Workspace", style={"fontWeight": "750", "fontSize": "17px", "color": "#172033"}),
                html.Div(f"{admin_username} · Administrator", style={"fontSize": "11px", "color": "#64748b"}),
            ]),
            html.Div(style={"display": "flex", "alignItems": "center", "gap": "5px", "flexWrap": "wrap"}, children=[
                html.Nav([*internal_links, *page_links], style={"display": "flex", "gap": "2px", "flexWrap": "wrap"}),
                html.Form(action="/logout", method="post", style={"display": "inline", "marginLeft": "5px"}, children=[
                    dcc.Input(type="hidden", name="csrf_token", value=csrf_token or ""),
                    html.Button("Log out", type="submit", style={"padding": "8px 11px", "border": "1px solid #cbd5e1", "borderRadius": "7px", "background": "#fff", "fontSize": "12px", "cursor": "pointer"}),
                ]),
            ]),
        ],
    )
