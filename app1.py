from __future__ import annotations

from dash import Dash

from callbacks.navigation import register_navigation_callbacks
from callbacks.opacity import register_opacity_callbacks
from callbacks.raster import (
    register_raster_callbacks,
    register_raster_routes,
)

from maps.map_views import (
    create_reference_map,
    create_historical_map,
)

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
# MAPS
# =========================================================

reference_map = create_reference_map()
historical_map = create_historical_map()


# =========================================================
# LAYOUT
# =========================================================

app.layout = create_app_layout(
    reference_map=reference_map,
    historical_map=historical_map,
)


# =========================================================
# ROUTES
# =========================================================

register_raster_routes(app)


# =========================================================
# CALLBACKS
# =========================================================

register_raster_callbacks(app)
register_navigation_callbacks(app)
register_opacity_callbacks(app)


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    app.run(
        debug=True
    )