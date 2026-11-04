from __future__ import annotations

from dash import dcc, html

from ui.admin_nav import create_page_shell

_CARD = {"background": "#fff", "border": "1px solid #dbe2ea", "borderRadius": "11px", "padding": "15px", "minWidth": "0"}
_LABEL = {"display": "block", "fontSize": "12px", "fontWeight": "650", "marginBottom": "5px", "color": "#334155"}
_INPUT = {"width": "100%", "boxSizing": "border-box", "padding": "10px", "border": "1px solid #cbd5e1", "borderRadius": "7px", "fontSize": "13px"}
_BUTTON = {"padding": "9px 13px", "border": "1px solid #1d4ed8", "borderRadius": "7px", "background": "#1d4ed8", "color": "#fff", "fontWeight": "650", "fontSize": "12px", "cursor": "pointer"}


def create_admin_config_layout(*, settings: dict, gcp_crs: str, admin_username: str, csrf_token: str, secure_cookie: bool, debug_mode: bool):
    security_status = "Secure cookie enabled" if secure_cookie else "Secure cookie disabled — required for HTTPS production deployment"
    return create_page_shell(
        title="Configuration",
        subtitle="Manage the small set of operational settings that can safely change at runtime.",
        admin_username=admin_username, csrf_token=csrf_token, active_page="config",
        children=[
            html.Section(style=_CARD, children=[
                html.H3("Coordinate reference system", style={"fontSize": "15px", "margin": "0 0 8px"}),
                html.Label("GCP coordinate reference system", style=_LABEL),
                html.Div(gcp_crs, style={"fontFamily": "monospace", "fontSize": "14px", "fontWeight": "700", "padding": "10px", "background": "#f1f5f9", "borderRadius": "7px", "display": "inline-block"}),
                html.P("Read-only. Changing this value requires a planned coordinate migration and validation of existing GCPs.", style={"fontSize": "12px", "color": "#64748b", "margin": "8px 0 0"}),
            ]),
            html.Section(style={**_CARD, "marginTop": "12px"}, children=[
                html.H3("Raster and upload settings", style={"fontSize": "15px", "margin": "0 0 12px"}),
                html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(2,minmax(240px,1fr))", "gap": "14px"}, children=[
                    html.Div([
                        html.Label("Temporary raster retention (hours)", style=_LABEL),
                        dcc.Input(id="admin-config-raster-ttl", type="number", min=1, max=8760, step=1, value=int(settings.get("raster_ttl_hours", 24)), style=_INPUT),
                        html.Div("1–8760 hours. Applied by the next temporary-raster cleanup operation.", style={"fontSize": "11px", "color": "#64748b", "marginTop": "5px"}),
                    ]),
                    html.Div([
                        html.Label("Maximum upload size (MB)", style=_LABEL),
                        dcc.Input(id="admin-config-max-upload-mb", type="number", min=16, max=2048, step=1, value=int(settings.get("max_upload_size_mb", 256)), style=_INPUT),
                        html.Div("16–2048 MB. Enforced on decoded TIFF bytes and by the HTTP request body limit.", style={"fontSize": "11px", "color": "#64748b", "marginTop": "5px"}),
                    ]),
                ]),
                html.Button("Save configuration", id="admin-config-save", n_clicks=0, style={**_BUTTON, "marginTop": "14px"}),
                html.Div(id="admin-config-status", role="status", style={"fontSize": "12px", "marginTop": "9px"}),
            ]),
            html.Section(style={**_CARD, "marginTop": "12px"}, children=[
                html.H3("Production security status", style={"fontSize": "15px", "margin": "0 0 10px"}),
                html.Div([
                    html.Div([html.Strong("Session cookie"), html.Span(f" · {security_status}", style={"color": "#166534" if secure_cookie else "#b45309"})], style={"fontSize": "12px", "marginBottom": "7px"}),
                    html.Div([html.Strong("Application debug mode"), html.Span(" · enabled" if debug_mode else " · disabled", style={"color": "#b45309" if debug_mode else "#166534"})], style={"fontSize": "12px", "marginBottom": "7px"}),
                    html.P("For production, serve the application behind HTTPS, set SESSION_COOKIE_SECURE=true, keep debug mode disabled, protect TiTiler and database network access, and use separate high-entropy GCP_SECRET_KEY and RASTER_SIGNING_KEY values.", style={"fontSize": "12px", "color": "#64748b", "lineHeight": "1.5", "margin": "8px 0 0"}),
                    html.P("Server-side sessions are revocable. Password reset and account deactivation revoke all sessions for the affected student. Full live-session browsing/revocation UI is intentionally a later security dashboard.", style={"fontSize": "12px", "color": "#64748b", "lineHeight": "1.5", "margin": "8px 0 0"}),
                ]),
            ]),
        ],
    )
