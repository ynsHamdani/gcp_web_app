import dash_leaflet as dl


HISTORICAL_BASE_URL = (
    "https://{s}.tile.openstreetmap.org/"
    "{z}/{x}/{y}.png"
)


def create_historical_layers():

    # -----------------------------------------------------
    # OpenStreetMap base layer
    # -----------------------------------------------------

    osm = dl.TileLayer(
        id="historical-osm-layer",
        url=HISTORICAL_BASE_URL,
        attribution="© OpenStreetMap contributors",
        opacity=1.0,
    )

    # -----------------------------------------------------
    # Historical raster
    # -----------------------------------------------------
    #
    # Keep this TileLayer directly on the map.
    # Do NOT wrap it inside LayersControl.
    #

    historical = dl.TileLayer(
        id="historical-raster-layer",
        url="",
        opacity=1.0,
        tileSize=256,
        maxZoom=24,
        zIndex=10,
    )

    return [
        osm,
        historical,

        dl.FullScreenControl(
            position="bottomright",
        ),

        dl.ScaleControl(
            position="bottomleft",
        ),
    ]