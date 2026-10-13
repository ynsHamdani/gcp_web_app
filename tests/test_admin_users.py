from __future__ import annotations

from admin.user_callbacks import _options, _rows, _temporary_password


def test_temporary_password_is_long_and_random():
    first = _temporary_password()
    second = _temporary_password()
    assert len(first) >= 12
    assert first != second


def test_user_table_does_not_expose_hash_and_shows_active_state():
    users = [{
        "user_id": 7,
        "username": "student7",
        "email": "student7@example.org",
        "user_role": "student",
        "is_active": False,
        "created_at": "2026-10-01T10:00:00+00:00",
        "password_hash": "MUST_NOT_APPEAR",
    }]
    row = _rows(users)[0]
    assert row["active"] == "no"
    assert "password_hash" not in row
    assert _options(users)[0]["value"] == "7"
    assert "[inactive]" in _options(users)[0]["label"]
