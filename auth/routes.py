from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
from urllib.parse import urlparse

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user
from flask_wtf.csrf import generate_csrf, validate_csrf
from wtforms.validators import ValidationError

from auth.forms import LoginForm


def _safe_next_url(target: str | None) -> bool:
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc


def create_auth_blueprint(user_store) -> Blueprint:
    blueprint = Blueprint("auth", __name__)

    @blueprint.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("auth.admin") if current_user.role == "admin" else "/")
        form = LoginForm()
        if form.validate_on_submit():
            user = user_store.authenticate(form.identifier.data, form.password.data)
            if user is not None and user.is_active:
                # Create the revocable server-side session before marking the
                # browser as authenticated. If PostgreSQL is unavailable, no
                # authenticated or remember cookie is issued for a session
                # that the server cannot validate.
                session.clear()
                remember = bool(form.remember.data)
                sid = None
                if callable(getattr(user_store, "create_session", None)):
                    sid = secrets.token_urlsafe(32)
                    expiry = datetime.now(timezone.utc) + (timedelta(days=30) if remember else timedelta(hours=8))
                    user_store.create_session(sid, int(user.get_id()), expiry, request.headers.get("User-Agent", ""))
                login_user(user, remember=remember, fresh=True, duration=timedelta(days=30) if remember else None)
                session.permanent = remember
                if sid:
                    session["gcp_session_id"] = sid
                if getattr(user, "must_change_password", False):
                    return redirect(url_for("auth.change_password"))
                target = request.args.get("next")
                if _safe_next_url(target):
                    return redirect(target)
                return redirect(url_for("auth.admin") if user.role == "admin" else "/")
            flash("Invalid username/email or password.", "error")
        return render_template("login.html", form=form, next_url=request.args.get("next", ""))

    @blueprint.route("/change-password", methods=["GET", "POST"])
    def change_password():
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next="/change-password"))
        error = None
        if request.method == "POST":
            try:
                validate_csrf(request.form.get("csrf_token", ""))
            except ValidationError:
                abort(400, description="Invalid or missing CSRF token.")
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")
            if new_password != confirm_password:
                error = "The new password and confirmation do not match."
            elif len(new_password) < 12 or len(new_password) > 1024:
                error = "The new password must contain 12–1024 characters."
            elif not user_store.verify_password(int(current_user.get_id()), current_password):
                error = "The current/temporary password is incorrect."
            else:
                sid = session.get("gcp_session_id", "")
                user_store.change_own_password(int(current_user.get_id()), new_password, sid)
                flash("Your password has been changed. Other sessions have been revoked.", "success")
                return redirect(url_for("auth.admin") if current_user.role == "admin" else "/")
        return render_template("change_password.html", csrf_token=generate_csrf(), error=error, must_change=bool(getattr(current_user, "must_change_password", False)))

    @blueprint.route("/logout", methods=["POST"])
    def logout():
        if current_user.is_authenticated:
            try:
                validate_csrf(request.form.get("csrf_token", ""))
            except ValidationError:
                abort(400, description="Invalid or missing CSRF token.")
            sid = session.get("gcp_session_id")
            if sid and callable(getattr(user_store, "revoke_session", None)):
                user_store.revoke_session(sid, int(current_user.get_id()), "logout")
        logout_user()
        session.clear()
        # Keep the remember-cookie cleanup marker; clearing it would allow a
        # remember cookie to silently recreate the just-logged-out identity.
        session["_remember"] = "clear"
        return redirect(url_for("auth.login", logged_out="1"))

    @blueprint.route("/admin", methods=["GET"])
    def admin():
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next="/admin/"))
        if current_user.role != "admin":
            abort(403)
        return redirect("/admin/")

    return blueprint
