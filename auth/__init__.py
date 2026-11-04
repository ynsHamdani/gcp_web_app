from __future__ import annotations

"""Authentication, role separation and server-side session revocation."""

import os
from datetime import timedelta
from urllib.parse import urlparse

from flask import abort, redirect, request, session, url_for
from flask_login import LoginManager, current_user, logout_user

from auth.routes import create_auth_blueprint
from services.runtime_settings import dash_request_max_content_length


def init_auth(server, user_store, *, secret_key: str, raster_signing_key: str | None = None) -> LoginManager:
    if not secret_key or len(secret_key) < 32 or secret_key.startswith("replace_with_"):
        raise RuntimeError("GCP_SECRET_KEY must contain at least 32 random characters.")
    if raster_signing_key is not None and (
        len(raster_signing_key) < 32 or raster_signing_key.startswith("replace_with_")
    ):
        raise RuntimeError("RASTER_SIGNING_KEY must be a separate random secret of at least 32 characters.")

    secure_cookie = os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
    server.config.update(
        SECRET_KEY=secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=secure_cookie,
        SESSION_COOKIE_NAME="gcp_session",
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=secure_cookie,
        REMEMBER_COOKIE_DURATION=timedelta(days=30),
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        SESSION_REFRESH_EACH_REQUEST=False,
        MAX_CONTENT_LENGTH=258 * 1024 * 1024,
    )

    # The database migration is required for production AuthStore instances.
    # Lightweight fake stores used by unit tests can omit .pool/session methods.
    settings_store = None
    pool = getattr(user_store, "pool", None)
    if pool is not None:
        from storage.settings_store import PostgresSettingsStore
        settings_store = PostgresSettingsStore(pool)
        try:
            settings = settings_store.get_settings()
            server.extensions["gcp_settings_store"] = settings_store
            server.config["MAX_CONTENT_LENGTH"] = dash_request_max_content_length(
                int(settings.get("max_upload_size_mb", 256))
            )
        except Exception as exc:
            raise RuntimeError(
                "Admin production database migration 003 is missing or unavailable. "
                "Run migrations/003_admin_production_up.sql before starting app1.py."
            ) from exc

    session_store_enabled = callable(getattr(user_store, "touch_session", None))

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
        endpoint = request.endpoint or ""

        # TiTiler fetches short-lived, signed raster capabilities directly.
        if request.path.startswith("/raster/"):
            return None

        # Refresh the HTTP body cap from PostgreSQL before Dash parses upload
        # POSTs. This also keeps multiple application workers consistent after
        # an administrator changes the upload-size setting.
        if settings_store is not None and request.method == "POST" and "/_dash" in request.path:
            try:
                configured_mb = int(settings_store.get_value("max_upload_size_mb", 256))
                server.config["MAX_CONTENT_LENGTH"] = dash_request_max_content_length(configured_mb)
            except Exception as exc:
                abort(503, description=f"Could not load upload-size configuration: {exc}")

        # Validate every authenticated browser request, including admin Dash
        # callback endpoints. This makes session revocation effective on the
        # next request after password reset or account deactivation.
        if current_user.is_authenticated and session_store_enabled:
            session_id = session.get("gcp_session_id")
            if not session_id or not user_store.touch_session(session_id, int(current_user.get_id())):
                logout_user()
                session.clear()
                # Preserve Flask-Login's remember-cookie deletion marker after
                # clearing the signed session data.
                session["_remember"] = "clear"
                if request.method == "GET":
                    return redirect(url_for("auth.login", next=request.path))
                abort(401)

        if endpoint.startswith("auth."):
            return None

        is_admin_path = request.path == "/admin" or request.path.startswith("/admin/")
        if not current_user.is_authenticated:
            if request.method == "GET" and (request.path == "/" or is_admin_path):
                target = "/admin/" if is_admin_path else "/"
                return redirect(url_for("auth.login", next=target))
            abort(401)

        role = getattr(current_user, "role", None)
        if role not in {"student", "admin"}:
            abort(403)
        if role == "student" and is_admin_path:
            abort(403)
        if role == "admin":
            if request.path == "/" and request.method == "GET":
                return redirect("/admin/")
            if request.path.startswith(("/_dash", "/assets/")):
                abort(403)

        # A temporary password grants access only to the password-change page
        # until the user chooses a new password.
        if getattr(current_user, "must_change_password", False):
            if endpoint not in {"auth.change_password", "auth.logout"}:
                return redirect(url_for("auth.change_password"))

        is_dash_request = "/_dash" in request.path
        if request.method == "POST" and is_dash_request:
            origin = request.headers.get("Origin")
            referer = request.headers.get("Referer")
            source = origin or referer
            if not source or urlparse(source).netloc != request.host:
                abort(403, description="Cross-origin Dash POST rejected.")
        return None

    @server.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        if request.path.startswith("/admin/") or request.path in {"/login", "/change-password"}:
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    return login_manager
