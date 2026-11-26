from __future__ import annotations

"""Central role predicates shared by Flask routes and Dash callbacks."""

ADMIN_ROLES = frozenset({"admin", "super_admin"})
ALL_ROLES = frozenset({"student", "admin", "super_admin"})


def is_admin_role(role: object) -> bool:
    return str(role or "").strip().lower() in ADMIN_ROLES


def is_super_admin_role(role: object) -> bool:
    return str(role or "").strip().lower() == "super_admin"
