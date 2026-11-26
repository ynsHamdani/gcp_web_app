from __future__ import annotations

"""Administrator callbacks for the controlled GCP context vocabulary."""

from dash import Input, Output, State, ctx, no_update
from flask import abort
from flask_login import current_user

from auth.permissions import is_admin_role


def _require_admin() -> int:
    if not current_user.is_authenticated or not is_admin_role(getattr(current_user, "role", None)):
        abort(403)
    return int(current_user.get_id())


def _options(categories: list[dict]) -> list[dict]:
    return [
        {
            "label": f"{item['label']} · {item['code']}" + (" (inactive)" if not item["is_active"] else ""),
            "value": str(item["context_category_id"]),
            "disabled": item.get("code") == "LEGACY_UNRECORDED",
        }
        for item in categories
    ]


def _audit(auth_store, actor_id: int, action: str, category: dict) -> None:
    try:
        auth_store.log_admin_action(
            actor_id,
            action,
            "gcp_context_category",
            category["context_category_id"],
            {"code": category["code"], "label": category["label"], "is_active": category["is_active"]},
        )
    except Exception:
        # The category write is authoritative; an audit-log outage must not
        # report a successful database operation as failed.
        import logging
        logging.getLogger(__name__).exception("Could not write context-category audit record")


def register_context_category_callbacks(app, context_store, auth_store) -> None:
    @app.callback(
        Output("admin-context-category-code", "value"),
        Output("admin-context-category-label", "value"),
        Output("admin-context-category-description", "value"),
        Output("admin-context-category-active", "value"),
        Output("admin-context-category-label", "disabled"),
        Output("admin-context-category-description", "disabled"),
        Output("admin-context-category-active", "options"),
        Input("admin-context-category-select", "value"),
        prevent_initial_call=True,
    )
    def load_category(category_id):
        active_option = lambda disabled: [{
            "label": "Active for new GCPs",
            "value": "active",
            "disabled": disabled,
        }]

        if category_id in (None, ""):
            return "", "", "", [], True, True, active_option(True)

        _require_admin()
        category = context_store.get(int(category_id))

        if not category:
            return "", "", "", [], True, True, active_option(True)

        code = category["code"]
        is_legacy = code == "LEGACY_UNRECORDED"
        is_restricted = code in {"OTHER", "LEGACY_UNRECORDED"}

        return (
            code,
            category["label"],
            category["description"],
            ["active"] if category["is_active"] else [],
            is_legacy,
            is_legacy,
            active_option(is_restricted),
        )
    
    @app.callback(
        Output("admin-context-new-code", "value"),
        Input("admin-context-new-label", "value"),
        prevent_initial_call=True,
    )
    def preview_new_category_code(label):
        _require_admin()
        if not label or not str(label).strip():
            return ""
        try:
            return context_store.code_from_label(label)
        except ValueError:
            return ""

    @app.callback(
        Output("admin-context-category-create-status", "children"),
        Output("admin-context-category-status", "children"),
        Output("admin-context-category-select", "options"),
        Output("admin-context-category-select", "value"),
        Output("admin-context-new-label", "value"),
        Output("admin-context-new-description", "value"),
        Input("admin-context-category-create", "n_clicks"),
        Input("admin-context-category-save", "n_clicks"),
        State("admin-context-new-label", "value"),
        State("admin-context-new-description", "value"),
        State("admin-context-category-select", "value"),
        State("admin-context-category-label", "value"),
        State("admin-context-category-description", "value"),
        State("admin-context-category-active", "value"),
        prevent_initial_call=True,
    )
    def persist_category(
        create_clicks,
        save_clicks,
        new_label,
        new_description,
        selected_id,
        edit_label,
        edit_description,
        active_values,
    ):
        del create_clicks, save_clicks
        actor_id = _require_admin()
        try:
            if ctx.triggered_id == "admin-context-category-create":
                category = context_store.create(
                    label=new_label,
                    description=new_description or "",
                )
                _audit(auth_store, actor_id, "gcp_context_category_created", category)
                categories = context_store.list_all()
                return (
                    f"Created '{category['label']}' (stable code: {category['code']}).",
                    "",
                    _options(categories),
                    str(category["context_category_id"]),
                    "",
                    "",
                )

            if selected_id in (None, ""):
                raise ValueError("Select an existing category to update.")
            category = context_store.update(
                int(selected_id),
                label=edit_label,
                description=edit_description or "",
                is_active="active" in (active_values or []),
            )
            _audit(auth_store, actor_id, "gcp_context_category_updated", category)
            categories = context_store.list_all()
            return (
                no_update,
                f"Saved '{category['label']}'. Existing GCP annotations remain unchanged.",
                _options(categories),
                str(category["context_category_id"]),
                no_update,
                no_update,
            )
        except Exception as exc:
            message = f"Category was not saved: {exc}"
            if ctx.triggered_id == "admin-context-category-create":
                return message, no_update, no_update, no_update, no_update, no_update
            return no_update, message, no_update, no_update, no_update, no_update
