import dash_leaflet as dl


HISTORICAL_BASE_URL = (
    "https://{s}.tile.openstreetmap.org/"
    "{z}/{x}/{y}.png"
)


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
            children=[osm],
            position="topright",
        ),

        dl.FullScreenControl(
            position="bottomright",
        ),

        dl.ScaleControl(
            position="bottomleft",
        ),
    ]