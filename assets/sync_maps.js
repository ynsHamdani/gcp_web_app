window.gcpMapSync = Object.assign({}, window.gcpMapSync, {
    handlers: {

        // =================================================
        // REGISTER REFERENCE MAP
        // =================================================

        registerReference: function(e, ctx) {

            window.gcpMapSyncState =
                window.gcpMapSyncState || {};

            window.gcpMapSyncState.reference =
                ctx.map;
        },


        // =================================================
        // REGISTER HISTORICAL MAP
        // =================================================

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

            syncMapViewDebounced(
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

            syncMapViewDebounced(
                ctx.map,
                state.reference
            );
        }
    }
});


// =========================================================
// SYNCHRONIZE MAPS
// =========================================================
//
// Small debounce prevents the first programmatic zoom
// ("Zoom to layer") from being immediately overwritten by
// the other map's moveend/zoomend event.
// =========================================================

function syncMapViewDebounced(
    source,
    target
) {

    const state =
        window.gcpMapSyncState;

    if (!state) {
        return;
    }

    // Do not interfere with a coordinated map movement.
    if (state.fittingLayer) {
        return;
    }


    // Cancel any previous pending sync.
    if (source._gcpSyncTimer) {

        clearTimeout(
            source._gcpSyncTimer
        );
    }


    // Wait briefly for Leaflet to finish its current
    // movement/zoom operation.
    source._gcpSyncTimer =
        setTimeout(
            function() {

                if (state.fittingLayer) {
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


                // Prevent the resulting target events
                // from immediately bouncing back.
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


                // Keep the lock long enough for Leaflet's
                // moveend/zoomend events to finish.
                setTimeout(
                    function() {

                        target._gcpSyncLocked =
                            false;

                    },
                    250
                );

            },
            100
        );
}


// =========================================================
// COORDINATED VIEW CHANGE
// =========================================================
//
// Useful when Python/Dash explicitly changes both maps,
// e.g. when clicking "Zoom to layer".
// =========================================================

window.gcpMapSync.setSynchronizedView =
    function(center, zoom) {

        const state =
            window.gcpMapSyncState;

        if (
            !state ||
            !state.reference ||
            !state.historical
        ) {
            return;
        }


        // Stop normal synchronization while both maps
        // are being moved together.
        state.fittingLayer = true;


        const reference =
            state.reference;

        const historical =
            state.historical;


        reference._gcpSyncLocked = true;
        historical._gcpSyncLocked = true;


        reference.setView(
            center,
            zoom,
            {
                animate: false
            }
        );


        historical.setView(
            center,
            zoom,
            {
                animate: false
            }
        );


        // Release the locks after Leaflet has finished
        // emitting its movement events.
        setTimeout(
            function() {

                reference._gcpSyncLocked =
                    false;

                historical._gcpSyncLocked =
                    false;

                state.fittingLayer =
                    false;

            },
            300
        );
    };