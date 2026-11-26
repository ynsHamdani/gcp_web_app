from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_super_admin_user_management_exposes_separate_privileged_console():
    dashboard = read("admin/users_dashboard.py")
    layout = read("ui/admin_users_layout.py")
    assert "is_super_admin_role" in dashboard
    assert "is_super_admin=is_super_admin" in dashboard
    assert "SUPER ADMIN ACCESS" in layout
    assert 'href="/super-admin/"' in layout
    assert "student accounts" in layout


def test_super_admin_root_routes_to_console_not_ordinary_admin_workspace():
    source = read("auth/__init__.py")
    assert 'if is_super_admin_role(role):' in source
    assert 'return redirect("/super-admin/")' in source
    assert 'elif role == "admin":' in source
    assert 'return redirect("/admin/")' in source


def test_student_polygon_clicks_are_mode_aware():
    source = read("maps/student_coverage.py")
    handlers = read("assets/student_coverage_map.js")
    assert "bubblingMouseEvents=True" in source
    assert "if (isGcpCollectionActive())" in handlers
    assert "L.DomEvent.stopPropagation(event.originalEvent)" in handlers
