from __future__ import annotations

from dash import Dash

from callbacks.gcp import register_gcp_callbacks
from callbacks.navigation import register_navigation_callbacks
from callbacks.opacity import register_opacity_callbacks
from callbacks.raster import (
    register_raster_callbacks,
    register_raster_routes,
)
from config import GCP_JSON_PATH
from maps.map_views import (
    create_historical_map,
    create_reference_map,
)
from models.gcp import gcp_table_row
from storage.gcp_store import JSONGCPStore
from ui.controls import create_app_layout


# =========================================================
# APPLICATION
# =========================================================

app = Dash(
    __name__,
    title="Historical Map GCP Collection",
    suppress_callback_exceptions=True,
)


# =========================================================
# STORAGE BACKEND
# =========================================================
#
# Dash callbacks depend on the GCPStore interface, not this JSON class.
# When PostgreSQL is introduced, this is the only application wiring that
# needs to change.
# =========================================================

gcp_store = JSONGCPStore(GCP_JSON_PATH)
initial_gcp_records = gcp_store.list()
initial_gcp_rows = [
    gcp_table_row(record)
    for record in initial_gcp_records
]


# =========================================================
# MAPS + PAGE LAYOUT
# =========================================================

reference_map = create_reference_map()
historical_map = create_historical_map()

app.layout = create_app_layout(
    reference_map=reference_map,
    historical_map=historical_map,
    initial_records=initial_gcp_records,
    initial_rows=initial_gcp_rows,
)


# =========================================================
# ROUTES + CALLBACKS
# =========================================================

register_raster_routes(app)
register_raster_callbacks(app)
register_navigation_callbacks(app)
register_opacity_callbacks(app)
register_gcp_callbacks(app, gcp_store)


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    app.run(debug=True)
