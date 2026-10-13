from __future__ import annotations

import re
from pathlib import Path

import pytest
from flask import Flask
from werkzeug.security import check_password_hash, generate_password_hash

from auth import init_auth
from auth.store import AuthUser


class FakeUserStore:
    def __init__(self):
        self.users = {
            "student": AuthUser(10, "student", "student@example.org", "student", True),
            "admin": AuthUser(20, "admin", "admin@example.org", "admin", True),
        }
        self.hashes = {
            "student": generate_password_hash("student-pass-123"),
            "admin": generate_password_hash("admin-pass-1234"),
        }

    def get_by_id(self, user_id):
        return next((u for u in self.users.values() if u.get_id() == str(user_id)), None)

    def authenticate(self, identifier, password):
        user = self.users.get((identifier or "").strip().lower())
        if user is None or not user.is_active:
            return None
        if not check_password_hash(self.hashes[user.username], password or ""):
            return None
        return user


def make_client():
    project_root = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        template_folder=str(project_root / "templates"),
    )
    app.config.update(TESTING=True)

    @app.route("/")
    def dash_index():
        return "student GCP page"

    @app.route("/_dash-layout")
    def dash_layout():
        return "dash layout payload"

    @app.route("/_dash-update-component", methods=["POST"])
    def dash_update():
        return "callback accepted"

    init_auth(app, FakeUserStore(), secret_key="test-secret-key-long-enough-for-tests-0123456789")
    return app.test_client()


def csrf_from_login_page(client) -> str:
    response = client.get("/login")
    assert response.status_code == 200
    match = re.search(
        r'name="csrf_token" type="hidden" value="([^"]+)"',
        response.get_data(as_text=True),
    )
    assert match, "Login form should contain a CSRF token."
    return match.group(1)


def login(client, username: str, password: str):
    token = csrf_from_login_page(client)
    return client.post(
        "/login",
        data={
            "csrf_token": token,
            "identifier": username,
            "password": password,
        },
        follow_redirects=False,
    ), token


def test_anonymous_users_cannot_open_dash_or_call_layout():
    client = make_client()
    assert client.get("/").status_code == 302
    assert client.get("/_dash-layout").status_code == 401


def test_student_can_login_and_is_denied_admin_page():
    client = make_client()
    response, _ = login(client, "student", "student-pass-123")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    assert client.get("/").status_code == 200
    assert client.get("/_dash-layout").status_code == 200
    assert client.get("/admin").status_code == 403


def test_admin_is_routed_to_admin_and_cannot_call_dash_endpoints():
    client = make_client()
    response, _ = login(client, "admin", "admin-pass-1234")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin")
    assert client.get("/admin").status_code == 200
    assert client.get("/").headers["Location"].endswith("/admin")
    assert client.get("/_dash-layout").status_code == 403


def test_login_rejects_bad_credentials_and_logout_requires_csrf():
    client = make_client()
    token = csrf_from_login_page(client)
    response = client.post(
        "/login",
        data={"csrf_token": token, "identifier": "student", "password": "wrong"},
    )
    assert response.status_code == 200
    assert b"Invalid username/email or password" in response.data

    response, token = login(client, "student", "student-pass-123")
    assert response.status_code == 302
    bad_logout = client.post("/logout", data={"csrf_token": "invalid-token"})
    assert bad_logout.status_code == 400
    good_logout = client.post("/logout", data={"csrf_token": token})
    assert good_logout.status_code == 302
    assert client.get("/").status_code == 302


def test_dash_post_rejects_cross_origin_requests():
    client = make_client()
    response, _ = login(client, "student", "student-pass-123")
    assert response.status_code == 302

    blocked = client.post(
        "/_dash-update-component",
        headers={"Origin": "https://attacker.example"},
    )
    assert blocked.status_code == 403

    accepted = client.post(
        "/_dash-update-component",
        headers={"Origin": "http://localhost"},
    )
    assert accepted.status_code == 200
