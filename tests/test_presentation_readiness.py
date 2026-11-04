from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / "files"
if not FILES.is_dir():  # When installed, tests live in <repo>/tests.
    FILES = ROOT


class PresentationReadinessTests(unittest.TestCase):
    def test_osm_host_uses_official_single_hostname(self):
        source = (FILES / "maps" / "map_views.py").read_text(encoding="utf-8")
        self.assertIn('OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"', source)
        self.assertNotIn("{s}.tile.openstreetmap.org", source)

    def test_carto_secret_is_environment_only(self):
        config = (FILES / "config.py").read_text(encoding="utf-8")
        map_views = (FILES / "maps" / "map_views.py").read_text(encoding="utf-8")
        self.assertIn('os.getenv("CARTO_API_KEY", "").strip()', config)
        self.assertNotIn("cb1_", config + map_views)

    def test_basemap_provider_is_persistent_and_validated(self):
        store = (FILES / "storage" / "settings_store.py").read_text(encoding="utf-8")
        layout = (FILES / "ui" / "admin_config_layout.py").read_text(encoding="utf-8")
        callback = (FILES / "admin" / "config_callbacks.py").read_text(encoding="utf-8")
        self.assertIn('"basemap_provider": BASEMAP_PROVIDER_DEFAULT', store)
        self.assertIn('{"label": "CARTO Voyager (recommended)", "value": "carto"}', layout)
        self.assertIn('{"label": "OpenStreetMap standard tiles", "value": "osm"}', layout)
        self.assertIn('"basemap_provider": provider', callback)

    def test_student_refresh_button_and_handler_are_present(self):
        layout = (FILES / "ui" / "layout.py").read_text(encoding="utf-8")
        self.assertIn('id="refresh-gcp-button"', layout)
        callback_path = ROOT / "callbacks" / "gcp.py"
        if callback_path.is_file():
            callback = callback_path.read_text(encoding="utf-8")
            self.assertIn('Input("refresh-gcp-button", "n_clicks")', callback)
            self.assertIn('if triggered == "refresh-gcp-button":', callback)
            self.assertIn("store.list_for_student(int(current_user.get_id()))", callback)
        else:
            updater = (ROOT.parent / "tools" / "apply_presentation_readiness.py").read_text(encoding="utf-8")
            self.assertIn('Input("refresh-gcp-button", "n_clicks")', updater)
            self.assertIn('if triggered == "refresh-gcp-button":', updater)
            self.assertIn("store.list_for_student(int(current_user.get_id()))", updater)

    def test_admin_and_user_pages_use_fixed_shell_scroll(self):
        nav = (FILES / "ui" / "admin_nav.py").read_text(encoding="utf-8")
        workspace = (FILES / "ui" / "admin_layout.py").read_text(encoding="utf-8")
        self.assertIn('id="admin-page-scroll"', nav)
        self.assertIn('"overflowY": "auto"', nav)
        self.assertIn('id="admin-workspace-scroll"', workspace)
        self.assertIn('"position": "fixed"', workspace)

    def test_student_maps_are_created_per_layout_using_persisted_provider(self):
        app1_path = ROOT / "app1.py"
        if app1_path.is_file():
            app1 = app1_path.read_text(encoding="utf-8")
            self.assertIn('get_runtime_setting("basemap_provider", "carto")', app1)
            self.assertIn("create_reference_map(basemap_provider)", app1)
            self.assertNotIn("reference_map = create_reference_map()\n", app1)
        else:
            updater = (ROOT.parent / "tools" / "apply_presentation_readiness.py").read_text(encoding="utf-8")
            self.assertIn('get_runtime_setting("basemap_provider", "carto")', updater)
            self.assertIn("create_reference_map(basemap_provider)", updater)

    def test_all_touched_python_modules_parse(self):
        paths = [
            "config.py", "maps/map_views.py", "services/runtime_settings.py",
            "storage/settings_store.py", "ui/admin_nav.py", "ui/admin_layout.py",
            "ui/admin_config_layout.py", "ui/layout.py", "admin/config_callbacks.py",
            "admin/config_dashboard.py", "admin/dashboard.py",
        ]
        for relative in paths:
            path = FILES / relative
            with self.subTest(path=relative):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


if __name__ == "__main__":
    unittest.main()
