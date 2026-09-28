window.gcpMapGcp = Object.assign({}, window.gcpMapGcp, {
    handlers: {

        captureHistoricalDrag: function(e, ctx) {
            const latlng = e.target.getLatLng();

            if (
                !window.dash_clientside ||
                !window.dash_clientside.set_props
            ) {
                return;
            }

            window.dash_clientside.set_props(
                "gcp-drag-event",
                {
                    data: {
                        position: [latlng.lat, latlng.lng],
                        timestamp: Date.now()
                    }
                }
            );
        }
    }
});
