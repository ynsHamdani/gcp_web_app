from __future__ import annotations

"""Reusable compact controls for Phase 1 semantic GCP context."""

from dash import dcc, html


_FIELD_LABEL = {"display": "block", "fontSize": "12px", "fontWeight": "650", "marginBottom": "5px", "color": "#334155"}
_INPUT = {"width": "100%", "boxSizing": "border-box", "padding": "9px", "border": "1px solid #cbd5e1", "borderRadius": "7px", "fontSize": "13px"}


def context_options(categories: list[dict] | None) -> list[dict]:
    return [
        {
            "label": f"{item['label']} — {item.get('description', '')}".rstrip(" —"),
            "value": str(item["context_category_id"]),
        }
        for item in (categories or [])
        if item.get("is_active") and item.get("code") != "LEGACY_UNRECORDED"
    ]


def create_student_context_modal(categories: list[dict] | None = None):
    """Overlay shown after the user confirms the two GCP endpoints."""
    return html.Div(
        id="gcp-context-modal",
        style={
            "display": "none", "position": "fixed", "inset": "0", "zIndex": 3000,
            "background": "rgba(15, 23, 42, 0.42)", "alignItems": "center",
            "justifyContent": "center", "padding": "16px",
        },
        children=html.Div(
            style={"width": "min(460px, 100%)", "background": "#fff", "borderRadius": "12px",
                      "boxShadow": "0 18px 55px rgba(15,23,42,.22)", "padding": "20px"},
            children=[
                html.H3("GCP spatial context", style={"margin": "0 0 6px", "fontSize": "17px"}),
                html.P("Describe the geographical feature used to identify this control point.", style={"fontSize": "12px", "color": "#64748b", "margin": "0 0 14px"}),
                html.Label("Context category (required)", style=_FIELD_LABEL),
                dcc.Dropdown(
                    id="gcp-context-category", options=context_options(categories), value=None,
                    placeholder="Select a context category", clearable=False, searchable=True,
                ),
                html.Label("Remark (optional)", style={**_FIELD_LABEL, "marginTop": "12px"}),
                dcc.Textarea(
                    id="gcp-context-remark", value="", maxLength=2000,
                    placeholder="Add a brief clarification (maximum 2,000 characters)",
                    style={**_INPUT, "minHeight": "76px", "resize": "vertical"},
                ),
                html.Div(id="gcp-context-status", role="status", style={"fontSize": "12px", "color": "#b45309", "marginTop": "9px", "minHeight": "18px"}),
                html.Div(
                    style={"display": "flex", "justifyContent": "flex-end", "gap": "8px", "marginTop": "12px"},
                    children=[
                        html.Button("Close", id="close-gcp-context-button", n_clicks=0, style={"padding": "8px 12px", "border": "1px solid #cbd5e1", "borderRadius": "7px", "background": "#fff", "cursor": "pointer"}),
                        html.Button("Save GCP", id="save-gcp-context-button", n_clicks=0, style={"padding": "8px 13px", "border": "1px solid #1d4ed8", "borderRadius": "7px", "background": "#1d4ed8", "color": "#fff", "fontWeight": "650", "cursor": "pointer"}),
                    ],
                ),
            ],
        ),
    )


def create_admin_context_creation_controls(categories: list[dict] | None = None):
    return html.Div(
        style={"display": "grid", "gridTemplateColumns": "minmax(220px, 1fr) minmax(220px, 1fr)", "gap": "8px", "marginTop": "8px"},
        children=[
            html.Div([
                html.Label("GCP context (required)", style=_FIELD_LABEL),
                dcc.Dropdown(id="admin-gcp-context-category", options=context_options(categories), value=None, clearable=False, searchable=True, placeholder="Select context category"),
            ]),
            html.Div([
                html.Label("Context remark (optional)", style=_FIELD_LABEL),
                dcc.Textarea(id="admin-gcp-context-remark", value="", maxLength=2000, style={**_INPUT, "minHeight": "38px"}, placeholder="Optional clarification"),
            ]),
        ],
    )


def create_admin_context_editor(categories: list[dict] | None = None):
    return html.Details(
        style={"marginTop": "9px", "padding": "9px", "border": "1px solid #e2e8f0", "borderRadius": "8px", "background": "#f8fafc"},
        children=[
            html.Summary("Inspect / correct context annotation", style={"cursor": "pointer", "fontWeight": "700", "fontSize": "12px"}),
            html.Div("Select a GCP row first. Historical annotations remain visible even if their category is later deactivated.", style={"fontSize": "11px", "color": "#64748b", "margin": "7px 0"}),
            html.Label("Context category", style=_FIELD_LABEL),
            dcc.Dropdown(id="admin-context-edit-category", options=context_options(categories), value=None, clearable=False, searchable=True, placeholder="Select an active category"),
            html.Label("Remark", style={**_FIELD_LABEL, "marginTop": "8px"}),
            dcc.Textarea(id="admin-context-edit-remark", value="", maxLength=2000, style={**_INPUT, "minHeight": "55px"}),
            html.Button("Save context correction", id="admin-save-context-changes", n_clicks=0, style={"marginTop": "8px", "padding": "8px 12px", "border": "1px solid #1d4ed8", "borderRadius": "7px", "background": "#1d4ed8", "color": "#fff", "cursor": "pointer"}),
        ],
    )


def create_admin_context_filter(categories: list[dict] | None = None):
    # Admins must be able to inspect annotations from inactive categories and
    # the reserved legacy bucket, even though neither can be used for new GCPs.
    options = [
        {
            "label": f"{item['label']} — {item['code']}" + (" (inactive)" if not item["is_active"] else ""),
            "value": str(item["context_category_id"]),
        }
        for item in (categories or [])
    ]
    return dcc.Dropdown(
        id="admin-context-filter",
        options=[{"label": "All context categories", "value": "all"}, *options],
        value="all", clearable=False, searchable=True,
        placeholder="Filter by semantic context",
    )


def create_admin_category_manager(categories: list[dict] | None = None):
    options = [
        {"label": f"{c['label']} · {c['code']}" + (" (inactive)" if not c["is_active"] else ""),
         "value": str(c["context_category_id"])}
        for c in (categories or [])
    ]
    return html.Section(
        style={"background": "#fff", "border": "1px solid #dbe2ea", "borderRadius": "11px", "padding": "15px", "marginTop": "12px"},
        children=[
            html.H3("GCP semantic context categories", style={"fontSize": "15px", "margin": "0 0 6px"}),
            html.P("Manage the controlled vocabulary used when creating GCPs. Categories already referenced by GCPs are retired by deactivation, never deleted.", style={"fontSize": "12px", "color": "#64748b", "margin": "0 0 12px"}),
            html.Label("Existing category", style=_FIELD_LABEL),
            dcc.Dropdown(id="admin-context-category-select", options=options, value=None, clearable=True, searchable=True, placeholder="Choose a category to edit"),
            html.Div(style={"display": "grid", "gridTemplateColumns": "minmax(180px, .7fr) minmax(220px, 1fr)", "gap": "10px", "marginTop": "10px"}, children=[
                html.Div([html.Label("Stable code", style=_FIELD_LABEL), dcc.Input(id="admin-context-category-code", type="text", value="", maxLength=64, style=_INPUT, placeholder="e.g. ROAD_BRIDGE")]),
                html.Div([html.Label("Display label", style=_FIELD_LABEL), dcc.Input(id="admin-context-category-label", type="text", value="", maxLength=120, style=_INPUT, placeholder="e.g. Road bridge")]),
            ]),
            html.Label("Description", style={**_FIELD_LABEL, "marginTop": "9px"}),
            dcc.Textarea(id="admin-context-category-description", value="", style={**_INPUT, "minHeight": "58px"}),
            html.Div(style={"display": "grid", "gridTemplateColumns": "150px 1fr", "gap": "10px", "marginTop": "9px", "alignItems": "end"}, children=[
                html.Div([html.Label("Display order", style=_FIELD_LABEL), dcc.Input(id="admin-context-category-order", type="number", min=0, step=1, value=100, style=_INPUT)]),
                dcc.Checklist(id="admin-context-category-active", options=[{"label": "Active for new GCPs", "value": "active"}], value=["active"], inline=True, style={"fontSize": "12px", "paddingBottom": "8px"}),
            ]),
            html.Div(style={"display": "flex", "gap": "8px", "marginTop": "12px", "flexWrap": "wrap"}, children=[
                html.Button("Create new category", id="admin-context-category-create", n_clicks=0),
                html.Button("Save selected category", id="admin-context-category-save", n_clicks=0),
            ]),
            html.Div(id="admin-context-category-status", role="status", style={"fontSize": "12px", "marginTop": "9px"}),
        ],
    )
