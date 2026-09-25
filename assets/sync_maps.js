window.gcpMapSync = Object.assign(
    {},
    window.gcpMapSync,
    {
        handlers: {

            // =================================================
            // REGISTER MAPS
            // =================================================

            registerReference: function(e, ctx) {

                window.gcpMapSyncState =
                    window.gcpMapSyncState || {};

                window.gcpMapSyncState.reference =
                    ctx.map;
            },


            registerHistorical: function(e, ctx) {

                window.gcpMapSyncState =
                    window.gcpMapSyncState || {};

                window.gcpMapSyncState.historical =
                    ctx.map;
            },


            // =================================================
            // REFERENCE -> HISTORICAL
            // =================================================

            syncReference: function(e, ctx) {

                const state =
                    window.gcpMapSyncState;

                if (
                    !state ||
                    !state.historical
                ) {
                    return;
                }

                if (
                    state.fittingNewLayer
                ) {
                    return;
                }

                syncMapView(
                    ctx.map,
                    state.historical
                );
            },


            // =================================================
            // HISTORICAL -> REFERENCE
            // =================================================

            syncHistorical: function(e, ctx) {

                const state =
                    window.gcpMapSyncState;

                if (
                    !state ||
                    !state.reference
                ) {
                    return;
                }

                if (
                    state.fittingNewLayer
                ) {
                    return;
                }

                syncMapView(
                    ctx.map,
                    state.reference
                );
            }
        }
    }
);


// =========================================================
// SYNCHRONIZE MAP VIEW
// =========================================================

function syncMapView(
    source,
    target
) {

    const state =
        window.gcpMapSyncState;

    if (
        !state ||
        state.fittingNewLayer
    ) {
        return;
    }

    const sourceCenter =
        source.getCenter();

    const sourceZoom =
        source.getZoom();

    const targetCenter =
        target.getCenter();

    const targetZoom =
        target.getZoom();

    const sameView =
        sourceZoom === targetZoom &&
        Math.abs(
            sourceCenter.lat -
            targetCenter.lat
        ) < 1e-10 &&
        Math.abs(
            sourceCenter.lng -
            targetCenter.lng
        ) < 1e-10;

    if (sameView) {
        return;
    }

    if (target._gcpSyncLocked) {
        return;
    }

    target._gcpSyncLocked = true;

    target.setView(
        sourceCenter,
        sourceZoom,
        {
            animate: false
        }
    );

    setTimeout(
        function() {
            target._gcpSyncLocked = false;
        },
        100
    );
}


// =========================================================
// FIT NEW HISTORICAL RASTER
// =========================================================

window.gcpMapSync.fitHistoricalBounds =
    function(bounds) {

        const state =
            window.gcpMapSyncState;

        if (
            !state ||
            !state.reference ||
            !state.historical
        ) {
            return;
        }

        if (!bounds) {
            return;
        }


        // -----------------------------------------------------
        // TiTiler / RasterAsset bounds:
        //
        // [west, south, east, north]
        // -----------------------------------------------------

        const leafletBounds = [
            [
                bounds[1],
                bounds[0]
            ],
            [
                bounds[3],
                bounds[2]
            ]
        ];


        // -----------------------------------------------------
        // Temporarily stop two-way synchronization.
        // Otherwise the two maps can fight the fit operation.
        // -----------------------------------------------------

        state.fittingNewLayer = true;


        const reference =
            state.reference;

        const historical =
            state.historical;


        // -----------------------------------------------------
        // Make sure the map dimensions are current.
        // -----------------------------------------------------

        reference.invalidateSize({
            pan: false
        });

        historical.invalidateSize({
            pan: false
        });


        // -----------------------------------------------------
        // Small delay allows Dash/Leaflet to finish inserting
        // the newly uploaded layer.
        // -----------------------------------------------------

        setTimeout(
            function() {

                reference.fitBounds(
                    leafletBounds,
                    {
                        padding: [25, 25],
                        animate: false,
                        maxZoom: 24
                    }
                );

                historical.fitBounds(
                    leafletBounds,
                    {
                        padding: [25, 25],
                        animate: false,
                        maxZoom: 24
                    }
                );

            },
            200
        );


        // -----------------------------------------------------
        // Re-enable normal synchronization after fitBounds()
        // and its move/zoom events have finished.
        // -----------------------------------------------------

        setTimeout(
            function() {

                state.fittingNewLayer =
                    false;

            },
            1000
        );
    };