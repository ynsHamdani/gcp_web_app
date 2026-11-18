from __future__ import annotations

import ast
from pathlib import Path
import unittest

from storage.gcp_context_store import GCPContextCategoryStore
from services.gcp_export import CSV_COLUMNS, _flatten
from storage.semantic_gcp_store import SemanticGCPStore

ROOT = Path(__file__).resolve().parents[1]


class _Cursor:
    def __init__(self):
        self.sql = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return (55,)


class _Connection:
    def __init__(self):
        self.cur = _Cursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self, *args, **kwargs):
        return self.cur


class _Pool:
    def __init__(self):
        self.conn = _Connection()

    def connection(self):
        return self.conn


class SemanticContextContractTests(unittest.TestCase):
    def test_remark_is_normalized_and_limited(self):
        self.assertIsNone(GCPContextCategoryStore.validate_remark("   "))
        self.assertEqual(GCPContextCategoryStore.validate_remark("  river meander  "), "river meander")
        with self.assertRaises(ValueError):
            GCPContextCategoryStore.validate_remark("x" * 2001)

    def test_reserved_category_codes_cannot_be_created(self):
        for code in ("OTHER", "LEGACY_UNRECORDED"):
            with self.subTest(code=code), self.assertRaises(ValueError):
                GCPContextCategoryStore._clean_code(code)

    def test_code_validation_is_normalized(self):
        self.assertEqual(GCPContextCategoryStore._clean_code(" road_bridge "), "ROAD_BRIDGE")
        with self.assertRaises(ValueError):
            GCPContextCategoryStore._clean_code("road-bridge")

    def test_export_contains_semantic_context_fields(self):
        record = {
            "context_category_id": "3",
            "context_category_code": "ROAD_INTERSECTION",
            "context_category_label": "Road intersection",
            "context_remark": "stone bridge nearby",
        }
        flattened = _flatten(record)
        self.assertIn("context_category_id", CSV_COLUMNS)
        self.assertEqual(flattened["context_category"], "Road intersection")
        self.assertEqual(flattened["context_remark"], "stone bridge nearby")


    def test_gcp_insert_uses_one_statement_and_rejects_legacy_category(self):
        pool = _Pool()
        store = SemanticGCPStore(pool)
        store.get = lambda _gcp_id: {"gcp_id": "GCP-0055"}
        record = {
            "student_id": "7", "reference_layer_id": "2", "historical_layer_id": "8",
            "reference": {"x": 500000, "y": 6200000, "lon": 10.2, "lat": 56.1},
            "historical": {"pixel": 10, "line": 20, "x": 500001, "y": 6200001, "lon": 10.2001, "lat": 56.1001},
            "crs": "EPSG:25832", "offset_m": 1.4, "status": "confirmed",
            "recorded_at": "2026-11-17T10:00:00+00:00",
        }
        saved = store.create(record, context_category_id=4, context_remark="old stone bridge")
        self.assertEqual(saved["gcp_id"], "GCP-0055")
        sql = pool.conn.cur.sql.upper()
        self.assertIn("INSERT INTO GCPS", sql)
        self.assertIn("FROM GCP_CONTEXT_CATEGORIES", sql)
        self.assertIn("C.IS_ACTIVE = TRUE", sql)
        self.assertIn("C.CODE <> 'LEGACY_UNRECORDED'", sql)
        self.assertEqual(sql.count("INSERT INTO GCPS"), 1)
        self.assertEqual(pool.conn.cur.params[-2:], ("old stone bridge", 4))


    def test_update_context_is_single_statement_and_only_accepts_active_categories(self):
        pool = _Pool()
        store = SemanticGCPStore(pool)
        store.get = lambda _gcp_id: {"gcp_id": "GCP-0055"}
        updated = store.update_context("GCP-0055", 7, "corrected annotation")
        self.assertEqual(updated["gcp_id"], "GCP-0055")
        sql = pool.conn.cur.sql.upper()
        self.assertIn("UPDATE GCPS AS G", sql)
        self.assertIn("C.IS_ACTIVE = TRUE", sql)
        self.assertIn("C.CODE <> 'LEGACY_UNRECORDED'", sql)
        self.assertEqual(pool.conn.cur.params, ("corrected annotation", 55, 7))

    def test_migration_preserves_old_records_and_reserves_legacy_category(self):
        sql = (ROOT / "migrations" / "004_gcp_semantic_context_up.sql").read_text(encoding="utf-8")
        self.assertIn("LEGACY_UNRECORDED", sql)
        self.assertIn("UPDATE gcps AS g", sql)
        self.assertIn("ALTER COLUMN context_category_id SET NOT NULL", sql)
        self.assertIn("ON DELETE RESTRICT", sql)
        self.assertIn("ALTER TABLE gcps", sql)
        self.assertIn("SET DEFAULT", sql)

    def test_new_python_modules_parse(self):
        modules = [
            "storage/gcp_context_store.py", "storage/semantic_gcp_store.py",
            "callbacks/gcp_context.py", "admin/context_category_callbacks.py",
            "ui/gcp_context_components.py",
        ]
        for relative in modules:
            with self.subTest(module=relative):
                ast.parse((ROOT / relative).read_text(encoding="utf-8"), filename=relative)


if __name__ == "__main__":
    unittest.main()
