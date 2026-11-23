from __future__ import annotations

from dash import dcc, html

_NAV_LINK = {
    "padding": "8px 11px",
    "borderRadius": "7px",
    "textDecoration": "none",
    "fontSize": "13px",
    "fontWeight": "600",
    "whiteSpace": "nowrap",
    "flex": "0 0 auto",
}

_HEADER_STYLE = {
    "position": "fixed",
    "top": "0",
    "left": "0",
    "right": "0",
    "height": "72px",
    "zIndex": "4000",
    "boxSizing": "border-box",
    "display": "flex",
    "alignItems": "center",
    "justifyContent": "space-between",
    "gap": "12px",
    "flexWrap": "nowrap",
    "padding": "8px max(14px, calc((100vw - 1760px)/2))",
    "background": "rgba(255,255,255,0.98)",
    "backdropFilter": "blur(9px)",
    "borderBottom": "1px solid #dbe2ea",
    "boxShadow": "0 2px 8px #0f172a0b",
}


def _logout_form(csrf_token: str):
    return html.Form(
        action="/logout", method="post", style={"display": "inline", "flex": "0 0 auto"},
        children=[
            dcc.Input(type="hidden", name="csrf_token", value=csrf_token or ""),
            html.Button("Log out", type="submit", style={
                "padding": "8px 11px", "border": "1px solid #cbd5e1", "borderRadius": "7px",
                "background": "#fff", "fontSize": "12px", "cursor": "pointer", "whiteSpace": "nowrap",
            }),
        ],
    )


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
        style=_HEADER_STYLE,
        children=[
            html.Div(
                style={"minWidth": "145px", "flex": "0 0 auto"},
                children=[
                    html.Div("Historical Map GCP", style={"fontWeight": "750", "fontSize": "17px", "color": "#172033", "whiteSpace": "nowrap"}),
                    html.Div(f"{admin_username} · Administrator", style={"fontSize": "11px", "color": "#64748b", "whiteSpace": "nowrap"}),
                ],
            ),
            html.Div(
                style={"display": "flex", "alignItems": "center", "justifyContent": "flex-end", "gap": "7px", "minWidth": "0", "flex": "1 1 auto"},
                children=[
                    html.Nav(links, style={"display": "flex", "gap": "3px", "flexWrap": "nowrap", "overflowX": "auto", "overflowY": "hidden", "minWidth": "0", "maxWidth": "75vw"}),
                    _logout_form(csrf_token),
                ],
            ),
        ],
    )


def create_page_shell(*, title: str, subtitle: str, admin_username: str, csrf_token: str, active_page: str, children):
    """Shared admin shell: fixed nav and an independently scrollable page body."""
    return html.Div(
        style={
            "height": "100vh",
            "overflow": "hidden",
            "background": "#f5f7fb",
            "color": "#172033",
            "fontFamily": "Arial, sans-serif",
        },
        children=[
            create_admin_header(admin_username=admin_username, csrf_token=csrf_token, active_page=active_page),
            html.Main(
                id="admin-page-scroll",
                style={
                    "position": "fixed", "top": "72px", "bottom": "0", "left": "0", "right": "0",
                    "overflowY": "auto", "overflowX": "hidden", "overscrollBehavior": "contain",
                    "padding": "14px 18px 32px", "boxSizing": "border-box",
                },
                children=[
                    html.Div(
                        style={"maxWidth": "1760px", "margin": "0 auto", "boxSizing": "border-box"},
                        children=[
                            html.Div([
                                html.H1(title, style={"fontSize": "23px", "margin": "0 0 4px"}),
                                html.P(subtitle, style={"fontSize": "13px", "color": "#64748b", "margin": "0 0 16px"}),
                            ]),
                            *children,
                        ],
                    )
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
        html.Button(
            label,
            type="button",
            **{"data-admin-nav": target, "className": "admin-nav-link" + (" is-active" if active else "")},
            style={
                **_NAV_LINK,
                "background": "#dbeafe" if active else "transparent",
                "color": "#1d4ed8" if active else "#334155",
                "border": "1px solid #bfdbfe" if active else "1px solid transparent",
                "cursor": "pointer",
            },
        ) for label, target, active in internal
    ]
    page_links = [
        html.A("Users", href="/admin/users/", style={**_NAV_LINK, "color": "#334155"}),
        html.A("Configuration", href="/admin/config/", style={**_NAV_LINK, "color": "#334155"}),
    ]
    return html.Header(
        id="admin-global-header",
        style=_HEADER_STYLE,
        children=[
            html.Div(
                style={"minWidth": "132px", "flex": "0 0 auto"},
                children=[
                    html.Div("GCP Workspace", style={"fontWeight": "750", "fontSize": "17px", "color": "#172033", "whiteSpace": "nowrap"}),
                    html.Div(f"{admin_username} · Administrator", style={"fontSize": "11px", "color": "#64748b", "whiteSpace": "nowrap"}),
                ],
            ),
            html.Div(
                style={"display": "flex", "alignItems": "center", "justifyContent": "flex-end", "gap": "5px", "minWidth": "0", "flex": "1 1 auto"},
                children=[
                    html.Nav(
                        [*internal_links, *page_links],
                        style={"display": "flex", "gap": "2px", "flexWrap": "nowrap", "overflowX": "auto", "overflowY": "hidden", "minWidth": "0", "maxWidth": "76vw"},
                    ),
                    _logout_form(csrf_token),
                ],
            ),
        ],
    )
