import dash_leaflet as dl
from dash_extensions.javascript import Namespace


HISTORICAL_BASE_URL = (
    "https://{s}.tile.openstreetmap.org/"
    "{z}/{x}/{y}.png"
)


ns = Namespace(
    "gcpMapSync",
    "handlers",
)


# =========================================================
# INITIAL HISTORICAL MAP LAYERS
# =========================================================

def create_historical_layers():

    osm = dl.BaseLayer(
        dl.TileLayer(
            url=HISTORICAL_BASE_URL,
            attribution="© OpenStreetMap contributors",
        ),
        name="OpenStreetMap",
        checked=True,
    )

    return [
        dl.LayersControl(
            id="historical-layer-control",
            children=[
                osm
            ],
            position="topright",
        ),

        dl.FullScreenControl(
            position="bottomright"
        ),

        dl.ScaleControl(
            position="bottomleft"
        ),
    ]


# =========================================================
# HISTORICAL RASTER OVERLAY
# =========================================================

def create_historical_overlay(
    asset,
    filename,
    opacity=1.0,
):

    return dl.Overlay(
        dl.TileLayer(
            id={
                "type": "historical-raster-layer",
                "index": asset.cog_path.stem,
            },

            url=asset.tile_url,

            opacity=opacity,

            tileSize=256,

            maxZoom=24,

            zIndex=10,
        ),

        name=filename,

        checked=True,
    )