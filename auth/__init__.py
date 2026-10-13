from __future__ import annotations

"""Authentication initialization and server-side access control."""

import os
from datetime import timedelta
from urllib.parse import urlparse

from flask import abort, redirect, request, url_for
from flask_login import LoginManager, current_user

from auth.routes import create_auth_blueprint


def init_auth(
    server,
    user_store,
    *,
    secret_key: str,
    raster_signing_key: str | None = None,
) -> LoginManager:
    """Configure Flask-Login, authentication routes, and application access.

    Dash's callback endpoints are protected by this Flask before-request
    handler as well as the main page. The raster endpoint is handled separately
    because TiTiler fetches raster URLs server-to-server; that endpoint must
    validate its own short-lived, path-scoped raster signature.
    """

    if (
        not secret_key
        or len(secret_key) < 32
        or secret_key.startswith("replace_with_")
    ):
        raise RuntimeError(
            "GCP_SECRET_KEY must be set to a randomly generated secret of "
            "at least 32 characters. Copy .env.example to .env and configure it."
        )

    if raster_signing_key is not None and (
        len(raster_signing_key) < 32
        or raster_signing_key.startswith("replace_with_")
    ):
        raise RuntimeError(
            "RASTER_SIGNING_KEY must be set to a separate random secret of "
            "at least 32 characters. Configure it in .env."
        )

    secure_cookie = os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }

    server.config.update(
        SECRET_KEY=secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=secure_cookie,
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=secure_cookie,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.session_protection = "strong"
    login_manager.init_app(server)

    @login_manager.user_loader
    def load_user(user_id: str):
        return user_store.get_by_id(user_id)

    server.register_blueprint(create_auth_blueprint(user_store))

    @server.before_request
    def require_authentication_and_role():
        # Login/logout/admin routes enforce their own permissions.
        endpoint = request.endpoint or ""
        if endpoint.startswith("auth."):
            return None

        # TiTiler fetches raster URLs server-to-server. The route validates a
        # short-lived, path-scoped signature in callbacks/raster.py.
        if request.path.startswith("/raster/"):
            return None

        if not current_user.is_authenticated:
            if request.path == "/" and request.method == "GET":
                return redirect(url_for("auth.login", next="/"))
            abort(401)

        if getattr(current_user, "role", None) not in {"student", "admin"}:
            abort(403)

        # Keep the student GCP Dash interface separate from the Admin page.
        # A student may use Dash; an administrator is routed to /admin instead.
        if current_user.role == "admin":
            if request.path == "/" and request.method == "GET":
                return redirect(url_for("auth.admin"))
            if request.path.startswith(("/_dash", "/assets/")):
                abort(403)

        # Dash sends state-changing callbacks as same-origin POST requests.
        # Check Origin (or Referer as a fallback) instead of globally enabling
        # Flask-WTF CSRF, which would otherwise reject Dash's callback protocol.
        if request.method == "POST" and request.path.startswith("/_dash"):
            origin = request.headers.get("Origin")
            referer = request.headers.get("Referer")
            source = origin or referer
            if not source or urlparse(source).netloc != request.host:
                abort(403, description="Cross-origin Dash POST rejected.")

        return None

    return login_manager
