import dash_leaflet as dl


REFERENCE_BASE_URL = (
    "https://{s}.tile.openstreetmap.org/"
    "{z}/{x}/{y}.png"
)


def create_reference_layers():

    osm = dl.BaseLayer(
        dl.TileLayer(
            url=REFERENCE_BASE_URL,
            attribution="© OpenStreetMap contributors",
        ),
        name="OpenStreetMap",
        checked=True,
    )

    return [
        dl.LayersControl(
            id="reference-layer-control",
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


def create_reference_overlay(
    asset,
    filename,
    opacity=1.0,
):

    return dl.Overlay(
        dl.TileLayer(
            id={
                "type": "reference-raster-layer",
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