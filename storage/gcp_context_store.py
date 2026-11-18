from __future__ import annotations

"""Persistence and validation for the controlled GCP context vocabulary."""

import re
from typing import Any


_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_RESERVED_CODES = {"OTHER", "LEGACY_UNRECORDED"}
_MAX_REMARK_LENGTH = 2000


class GCPContextCategoryStore:
    """Manage context categories using the application's PostgreSQL pool adapter.

    Physical deletion is intentionally not exposed. Referenced categories are
    protected by the database foreign key and are retired by deactivation.
    """

    def __init__(self, pool) -> None:
        self.pool = pool

    @staticmethod
    def _clean_code(code: str) -> str:
        value = str(code or "").strip().upper()
        if not _CODE_RE.fullmatch(value):
            raise ValueError("Category code must use 2–64 uppercase letters, digits or underscores and start with a letter.")
        if value in _RESERVED_CODES:
            raise ValueError("This category code is reserved by the application.")
        return value

    @staticmethod
    def validate_remark(remark: str | None) -> str | None:
        if remark is None:
            return None
        value = str(remark).strip()
        if len(value) > _MAX_REMARK_LENGTH:
            raise ValueError(f"Context remark must not exceed {_MAX_REMARK_LENGTH} characters.")
        return value or None

    @staticmethod
    def _row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "context_category_id": int(row["context_category_id"]),
            "code": str(row["code"]),
            "label": str(row["label"]),
            "description": str(row.get("description") or ""),
            "is_active": bool(row["is_active"]),
            "is_system": bool(row["is_system"]),
            "sort_order": int(row["sort_order"]),
            "created_at": row["created_at"].isoformat() if hasattr(row.get("created_at"), "isoformat") else str(row.get("created_at") or ""),
            "updated_at": row["updated_at"].isoformat() if hasattr(row.get("updated_at"), "isoformat") else str(row.get("updated_at") or ""),
        }

    def list_all(self) -> list[dict]:
        sql = """
            SELECT context_category_id, code, label, description,
                   is_active, is_system, sort_order, created_at, updated_at
            FROM gcp_context_categories
            ORDER BY sort_order, label, context_category_id
        """
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql)
                return [self._row(row) for row in cur.fetchall()]

    def list_active(self) -> list[dict]:
        """Return selectable categories; the legacy system category is excluded."""
        sql = """
            SELECT context_category_id, code, label, description,
                   is_active, is_system, sort_order, created_at, updated_at
            FROM gcp_context_categories
            WHERE is_active = TRUE AND code <> 'LEGACY_UNRECORDED'
            ORDER BY sort_order, label, context_category_id
        """
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql)
                return [self._row(row) for row in cur.fetchall()]

    def get(self, category_id: int) -> dict | None:
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(
                    """SELECT context_category_id, code, label, description,
                              is_active, is_system, sort_order, created_at, updated_at
                       FROM gcp_context_categories WHERE context_category_id = %s""",
                    (int(category_id),),
                )
                row = cur.fetchone()
        return self._row(row) if row else None

    def validate_selectable(self, category_id: int) -> dict:
        category = self.get(int(category_id))
        if category is None:
            raise ValueError("Select a valid GCP context category.")
        if not category["is_active"] or category["code"] == "LEGACY_UNRECORDED":
            raise ValueError("This context category is not available for new GCP records.")
        return category

    def create(self, *, code: str, label: str, description: str = "", sort_order: int = 100) -> dict:
        code = self._clean_code(code)
        label = str(label or "").strip()
        description = str(description or "").strip()
        if not label or len(label) > 120:
            raise ValueError("Category label must contain 1–120 characters.")
        order = int(sort_order)
        if order < 0:
            raise ValueError("Display order must be zero or greater.")
        sql = """
            INSERT INTO gcp_context_categories
                (code, label, description, is_active, is_system, sort_order)
            VALUES (%s, %s, %s, TRUE, FALSE, %s)
            RETURNING context_category_id
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (code, label, description, order))
                row = cur.fetchone()
        if not row:
            raise RuntimeError("Category creation did not return an identifier.")
        return self.get(int(row[0]))

    def update(
        self,
        category_id: int,
        *,
        label: str,
        description: str = "",
        is_active: bool,
        sort_order: int,
    ) -> dict:
        category = self.get(int(category_id))
        if category is None:
            raise KeyError(f"Unknown GCP context category: {category_id}")
        if category["code"] == "LEGACY_UNRECORDED":
            raise ValueError("The reserved legacy category cannot be edited or activated.")
        label = str(label or "").strip()
        description = str(description or "").strip()
        if not label or len(label) > 120:
            raise ValueError("Category label must contain 1–120 characters.")
        if category["code"] == "OTHER" and not bool(is_active):
            raise ValueError("Other / not identifiable must remain active.")
        order = int(sort_order)
        if order < 0:
            raise ValueError("Display order must be zero or greater.")
        sql = """
            UPDATE gcp_context_categories
            SET label = %s, description = %s, is_active = %s,
                sort_order = %s, updated_at = CURRENT_TIMESTAMP
            WHERE context_category_id = %s
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (label, description, bool(is_active), order, int(category_id)))
                if cur.rowcount != 1:
                    raise KeyError(f"Unknown GCP context category: {category_id}")
        return self.get(int(category_id))

    def delete(self, category_id: int) -> None:
        raise NotImplementedError("Categories are never physically deleted; deactivate them instead.")
