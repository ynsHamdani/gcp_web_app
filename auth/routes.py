from __future__ import annotations

from urllib.parse import urlparse

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_user, logout_user
from flask_wtf.csrf import generate_csrf, validate_csrf
from wtforms.validators import ValidationError

from auth.forms import LoginForm


def _safe_next_url(target: str | None) -> bool:
    """Allow only same-origin, absolute-path redirects (no open redirects)."""

    if not target or not target.startswith("/") or target.startswith("//"):
        return False
    if "\\" in target:
        return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc


def create_auth_blueprint(user_store) -> Blueprint:
    blueprint = Blueprint("auth", __name__)

    @blueprint.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(
                url_for("auth.admin")
                if current_user.role == "admin"
                else "/"
            )

        form = LoginForm()
        if form.validate_on_submit():
            user = user_store.authenticate(
                form.identifier.data,
                form.password.data,
            )

            if user is not None and user.is_active:
                login_user(user, remember=bool(form.remember.data), fresh=True)
                session.permanent = bool(form.remember.data)

                target = request.args.get("next")
                if _safe_next_url(target):
                    return redirect(target)

                return redirect(
                    url_for("auth.admin") if user.role == "admin" else "/"
                )

            flash("Invalid username/email or password.", "error")

        return render_template(
            "login.html",
            form=form,
            next_url=request.args.get("next", ""),
        )

    @blueprint.route("/logout", methods=["POST"])
    def logout():
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))

        try:
            validate_csrf(request.form.get("csrf_token", ""))
        except ValidationError:
            abort(400, description="Invalid or missing CSRF token.")

        logout_user()
        # Keep Flask-Login's remember-cookie cleanup marker, but rotate the
        # form CSRF token so it cannot be reused after logout.
        session.pop("csrf_token", None)
        return redirect(url_for("auth.login", logged_out="1"))

    @blueprint.route("/admin", methods=["GET"])
    def admin():
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next="/admin"))
        if current_user.role != "admin":
            abort(403)
        return render_template(
            "admin.html",
            user=current_user,
            csrf_token=generate_csrf(),
        )

    return blueprint
