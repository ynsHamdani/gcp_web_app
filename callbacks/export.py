from __future__ import annotations

from dash import Input, Output, dcc, no_update
from flask import abort
from flask_login import current_user

from services.gcp_export import build_gcp_csv


def register_student_export_callbacks(app, gcp_store) -> None:
    """Register a server-scoped CSV export for the currently authenticated student."""

    @app.callback(
        Output("student-gcp-download", "data"),
        Input("student-export-gcps", "n_clicks"),
        prevent_initial_call=True,
    )
    def export_my_gcps(n_clicks):
        if not n_clicks:
            return no_update
        if not current_user.is_authenticated or getattr(current_user, "role", None) != "student":
            abort(403)
        records = gcp_store.list_for_student(int(current_user.get_id()))
        return dcc.send_bytes(build_gcp_csv(records), "my_gcps.csv")
