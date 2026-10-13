from __future__ import annotations

from unittest.mock import patch

import pytest
from flask import Flask
from werkzeug.exceptions import Forbidden

from admin.gcp_callbacks import _require_admin as require_admin_gcp
from admin.user_callbacks import _require_admin as require_admin_users


class _FakeUser:
    def __init__(self, authenticated: bool, role: str | None):
        self.is_authenticated = authenticated
        self.role = role


def test_admin_gcp_guard_rejects_students():
    app = Flask(__name__)
    with app.app_context(), patch("admin.gcp_callbacks.current_user", _FakeUser(True, "student")):
        with pytest.raises(Forbidden):
            require_admin_gcp()


def test_admin_user_guard_rejects_students():
    app = Flask(__name__)
    with app.app_context(), patch("admin.user_callbacks.current_user", _FakeUser(True, "student")):
        with pytest.raises(Forbidden):
            require_admin_users()
