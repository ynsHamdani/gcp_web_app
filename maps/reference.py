import dash_leaflet as dl


REFERENCE_BASE_URL = (
    "https://{s}.tile.openstreetmap.org/"
    "{z}/{x}/{y}.png"
)


def create_reference_layers():

    base_layer = dl.BaseLayer(
        dl.TileLayer(
            url=REFERENCE_BASE_URL,
            attribution="© OpenStreetMap contributors",
        ),
        name="OpenStreetMap",
        checked=True,
    )

    reference_layer = dl.Overlay(
        dl.TileLayer(
            id="reference-raster-layer",
            url="",
            opacity=0.0,
            maxNativeZoom=22,
        ),
        name="Reference raster",
        checked=True,
    )

    return [
        dl.LayersControl(
            children=[
                base_layer,
                reference_layer,
            ],
            position="topright",
        ),

        dl.FullScreenControl(
            position="bottomright",
        ),

        dl.ScaleControl(
            position="bottomleft",
        ),
    ]