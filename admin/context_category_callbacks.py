from __future__ import annotations

"""Administrator callbacks for controlled GCP context vocabulary."""

from dash import Input, Output, State, ctx, no_update
from flask import abort
from flask_login import current_user


def _require_admin() -> int:
    if not current_user.is_authenticated or getattr(current_user, "role", None) != "admin":
        abort(403)
    return int(current_user.get_id())


def _options(categories: list[dict]) -> list[dict]:
    return [
        {"label": f"{item['label']} · {item['code']}" + (" (inactive)" if not item["is_active"] else ""),
         "value": str(item["context_category_id"])}
        for item in categories
    ]


def register_context_category_callbacks(app, context_store, auth_store) -> None:
    @app.callback(
        Output("admin-context-category-code", "value"),
        Output("admin-context-category-label", "value"),
        Output("admin-context-category-description", "value"),
        Output("admin-context-category-order", "value"),
        Output("admin-context-category-active", "value"),
        Output("admin-context-category-code", "disabled"),
        Output("admin-context-category-active", "disabled"),
        Input("admin-context-category-select", "value"),
        prevent_initial_call=True,
    )
    def load_category(category_id):
        if category_id in (None, ""):
            return "", "", "", 100, ["active"], False, False
        _require_admin()
        category = context_store.get(int(category_id))
        if not category:
            return "", "", "", 100, [], True, True
        is_legacy = category["code"] == "LEGACY_UNRECORDED"
        return (
            category["code"], category["label"], category["description"],
            category["sort_order"], ["active"] if category["is_active"] else [],
            True, is_legacy or category["code"] == "OTHER",
        )

    @app.callback(
        Output("admin-context-category-status", "children"),
        Output("admin-context-category-select", "options"),
        Output("admin-context-category-select", "value"),
        Input("admin-context-category-create", "n_clicks"),
        Input("admin-context-category-save", "n_clicks"),
        State("admin-context-category-select", "value"),
        State("admin-context-category-code", "value"),
        State("admin-context-category-label", "value"),
        State("admin-context-category-description", "value"),
        State("admin-context-category-order", "value"),
        State("admin-context-category-active", "value"),
        prevent_initial_call=True,
    )
    def persist_category(create_clicks, save_clicks, selected_id, code, label, description, order, active_values):
        _require_admin()
        actor_id = int(current_user.get_id())
        try:
            if ctx.triggered_id == "admin-context-category-create":
                category = context_store.create(
                    code=code, label=label, description=description or "", sort_order=order or 0
                )
                action = "gcp_context_category_created"
            else:
                if selected_id in (None, ""):
                    raise ValueError("Select a category to update, or choose Create new category.")
                category = context_store.update(
                    int(selected_id), label=label, description=description or "",
                    is_active="active" in (active_values or []), sort_order=order or 0,
                )
                action = "gcp_context_category_updated"
            try:
                auth_store.log_admin_action(
                    actor_id, action, "gcp_context_category",
                    category["context_category_id"],
                    {"code": category["code"], "label": category["label"], "is_active": category["is_active"]},
                )
            except Exception:
                # The category operation is authoritative; an audit-log
                # outage must not misreport a successful database change.
                import logging
                logging.getLogger(__name__).exception("Could not write context-category audit record")
            categories = context_store.list_all()
            status = f"Saved category: {category['label']}. Changes apply to new GCPs and historical labels remain intact."
            return status, _options(categories), str(category["context_category_id"])
        except Exception as exc:
            return f"Category was not saved: {exc}", no_update, no_update
