from __future__ import annotations

from pathlib import Path
import unittest

from storage.gcp_context_store import GCPContextCategoryStore

ROOT = Path(__file__).resolve().parents[1]


class Phase11RefinementTests(unittest.TestCase):
    def test_stable_code_is_generated_from_label(self):
        self.assertEqual(
            GCPContextCategoryStore.code_from_label("River bend / meander"),
            "RIVER_BEND_MEANDER",
        )
        self.assertEqual(
            GCPContextCategoryStore.code_from_label("3rd-order stream"),
            "CATEGORY_3RD_ORDER_STREAM",
        )

    def test_reserved_names_cannot_be_recreated(self):
        with self.assertRaises(ValueError):
            GCPContextCategoryStore.code_from_label("Other")
        with self.assertRaises(ValueError):
            GCPContextCategoryStore.code_from_label("Legacy unrecorded")

    def test_category_store_keeps_sort_order_unmodified_and_sorts_alphabetically(self):
        source = (ROOT / "storage" / "gcp_context_store.py").read_text(encoding="utf-8")
        self.assertIn("ORDER BY LOWER(label), context_category_id", source)
        self.assertIn("RETURNING context_category_id", source)
        self.assertNotIn("cur.rowcount", source)
        self.assertNotIn("SET sort_order", source)
        self.assertIn("ON CONFLICT (code) DO NOTHING", source)

    def test_admin_category_form_has_separate_create_and_edit_inputs(self):
        source = (ROOT / "ui" / "gcp_context_components.py").read_text(encoding="utf-8")
        self.assertIn('id="admin-context-new-label"', source)
        self.assertIn('id="admin-context-category-select"', source)
        self.assertNotIn('id="admin-context-category-order"', source)
        self.assertIn('disabled=True', source)

    def test_student_modal_uses_a_fixed_overlay_and_discard_action(self):
        source = (ROOT / "ui" / "gcp_context_components.py").read_text(encoding="utf-8")
        callback = (ROOT / "callbacks" / "gcp_context.py").read_text(encoding="utf-8")
        self.assertIn('"position": "fixed"', source)
        self.assertIn('id="discard-gcp-context-button"', source)
        self.assertIn('"aria-modal": "true"', source)
        self.assertIn("student_context_modal_style(True)", callback)
        self.assertIn("Pending GCP discarded. No record was saved.", callback)

    def test_admin_missing_context_has_an_inline_actionable_warning(self):
        ui = (ROOT / "ui" / "gcp_context_components.py").read_text(encoding="utf-8")
        callbacks = (ROOT / "admin" / "collection_callbacks.py").read_text(encoding="utf-8")
        self.assertIn('id="admin-gcp-context-status"', ui)
        self.assertIn("Select a category above, then confirm again", callbacks)
        self.assertIn("The pending GCP has not been saved.", callbacks)

    def test_basemap_label_is_resolved_from_the_configured_provider(self):
        source = (ROOT / "services" / "admin_layers.py").read_text(encoding="utf-8")
        self.assertIn("resolve_basemap_provider", source)
        self.assertIn('"basemap_label": basemap_label', source)

    def test_admin_reference_selector_defaults_to_the_configured_basemap(self):
        source = (ROOT / "admin" / "dashboard.py").read_text(encoding="utf-8")
        self.assertIn('selected_reference_id = layer_state.get("basemap_reference_layer_id")', source)
        self.assertIn('"reference_layer_id")', source)

    def test_osm_referrer_policy_and_dash_toolbar_setting(self):
        auth = (ROOT / "auth" / "__init__.py").read_text(encoding="utf-8")
        app = (ROOT / "app1.py").read_text(encoding="utf-8")
        self.assertIn('Referrer-Policy", "strict-origin-when-cross-origin"', auth)
        self.assertIn("dev_tools_ui=False", app)

    def test_no_database_migration_is_added_by_this_patch(self):
        package = Path(__file__).resolve().parents[1]
        self.assertFalse((package / "migrations" / "005_gcp_context_refinement_up.sql").exists())


if __name__ == "__main__":
    unittest.main()
