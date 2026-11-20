from __future__ import annotations

"""Persistence and validation for the controlled GCP context vocabulary."""

import re
import unicodedata
from typing import Any


_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_RESERVED_CODES = {"OTHER", "LEGACY_UNRECORDED"}
_MAX_REMARK_LENGTH = 2000


class GCPContextCategoryStore:
    """Manage context categories without changing the existing table schema.

    Categories are never physically deleted. Existing ``sort_order`` values
    are retained, but presentation order is alphabetical by label.
    """

    def __init__(self, pool) -> None:
        self.pool = pool

    @staticmethod
    def _clean_code(code: str) -> str:
        value = str(code or "").strip().upper()
        if not _CODE_RE.fullmatch(value):
            raise ValueError(
                "Category code must use 2–64 uppercase letters, digits or underscores and start with a letter."
            )
        if value in _RESERVED_CODES:
            raise ValueError("This category code is reserved by the application.")
        return value

    @staticmethod
    def code_from_label(label: str) -> str:
        """Create a deterministic stable code from a human-readable label."""
        value = str(label or "").strip()
        if not value:
            raise ValueError("Enter a category name first.")
        ascii_label = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        code = re.sub(r"[^A-Za-z0-9]+", "_", ascii_label).strip("_").upper()
        if not code:
            raise ValueError("The category name must contain letters or numbers.")
        if not code[0].isalpha():
            code = f"CATEGORY_{code}"
        code = code[:64].rstrip("_")
        if len(code) == 1:
            code = f"{code}_CATEGORY"
        if code in _RESERVED_CODES:
            raise ValueError("This name maps to a reserved system category code. Choose a more specific name.")
        return GCPContextCategoryStore._clean_code(code)

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
            ORDER BY LOWER(label), context_category_id
        """
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql)
                return [self._row(row) for row in cur.fetchall()]

    def list_active(self) -> list[dict]:
        """Return alphabetically sorted categories selectable for new GCPs."""
        sql = """
            SELECT context_category_id, code, label, description,
                   is_active, is_system, sort_order, created_at, updated_at
            FROM gcp_context_categories
            WHERE is_active = TRUE AND code <> 'LEGACY_UNRECORDED'
            ORDER BY LOWER(label), context_category_id
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

    def get_by_code(self, code: str) -> dict | None:
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(
                    """SELECT context_category_id, code, label, description,
                              is_active, is_system, sort_order, created_at, updated_at
                       FROM gcp_context_categories WHERE code = %s""",
                    (str(code).upper(),),
                )
                row = cur.fetchone()
        return self._row(row) if row else None

    def get_by_label(self, label: str) -> dict | None:
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(
                    """SELECT context_category_id, code, label, description,
                              is_active, is_system, sort_order, created_at, updated_at
                       FROM gcp_context_categories WHERE LOWER(label) = LOWER(%s)
                       ORDER BY context_category_id LIMIT 1""",
                    (str(label).strip(),),
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

    def create(self, *, label: str, description: str = "") -> dict:
        label = str(label or "").strip()
        description = str(description or "").strip()
        if not label or len(label) > 120:
            raise ValueError("Category name must contain 1–120 characters.")

        code = self.code_from_label(label)
        existing_label = self.get_by_label(label)
        if existing_label:
            state = "inactive" if not existing_label["is_active"] else "active"
            action = (
                "Select it under Existing categories and reactivate it."
                if not existing_label["is_active"]
                else "Select it under Existing categories to edit it."
            )
            raise ValueError(f"A category with this name already exists ({state}). {action}")

        existing_code = self.get_by_code(code)
        if existing_code:
            state = "inactive" if not existing_code["is_active"] else "active"
            action = (
                "Select it under Existing categories and reactivate it."
                if not existing_code["is_active"]
                else "Select it under Existing categories to edit it."
            )
            raise ValueError(f"Stable code {code} already exists ({state}). {action}")

        # sort_order is intentionally omitted: its existing database default
        # supplies an internal value. It is not edited or used for display order.
        sql = """
            INSERT INTO gcp_context_categories
                (code, label, description, is_active, is_system)
            VALUES (%s, %s, %s, TRUE, FALSE)
            ON CONFLICT (code) DO NOTHING
            RETURNING context_category_id
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (code, label, description))
                row = cur.fetchone()

        if not row:
            # Also handles a concurrent create without leaking a raw
            # UniqueViolation/SQLAlchemy error to the administrator.
            existing = self.get_by_code(code)
            if existing:
                state = "inactive" if not existing["is_active"] else "active"
                action = "Select the existing category and reactivate it." if not existing["is_active"] else "Select the existing category to edit it."
                raise ValueError(f"Stable code {code} already exists ({state}). {action}")
            raise RuntimeError("Category creation did not return an identifier.")
        return self.get(int(row[0]))

    def update(
        self,
        category_id: int,
        *,
        label: str,
        description: str = "",
        is_active: bool,
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

        duplicate_label = self.get_by_label(label)
        if duplicate_label and int(duplicate_label["context_category_id"]) != int(category_id):
            raise ValueError("Another category already uses this display label.")

        sql = """
            UPDATE gcp_context_categories
            SET label = %s, description = %s, is_active = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE context_category_id = %s
            RETURNING context_category_id
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (label, description, bool(is_active), int(category_id)))
                row = cur.fetchone()
        if row is None:
            raise KeyError(f"Unknown GCP context category: {category_id}")
        return self.get(int(category_id))

    def delete(self, category_id: int) -> None:
        raise NotImplementedError("Categories are never physically deleted; deactivate them instead.")
