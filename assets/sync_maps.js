window.gcpMapSync = Object.assign({}, window.gcpMapSync, {
    handlers: {

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

        syncReference: function(e, ctx) {
            const state = window.gcpMapSyncState;

            if (!state || !state.historical) {
                return;
            }

            syncMapViewDebounced(
                ctx.map,
                state.historical
            );
        },

        syncHistorical: function(e, ctx) {
            const state = window.gcpMapSyncState;

            if (!state || !state.reference) {
                return;
            }

            syncMapViewDebounced(
                ctx.map,
                state.reference
            );
        }
    }
});


function syncMapViewDebounced(source, target) {

    const state = window.gcpMapSyncState;

    if (!state || state.fittingLayer) {
        return;
    }

    if (source._gcpSyncTimer) {
        clearTimeout(source._gcpSyncTimer);
    }

    source._gcpSyncTimer = setTimeout(function() {

        if (state.fittingLayer) {
            return;
        }

        const sourceCenter = source.getCenter();
        const sourceZoom = source.getZoom();

        const targetCenter = target.getCenter();
        const targetZoom = target.getZoom();

        const sameView =
            sourceZoom === targetZoom &&
            Math.abs(
                sourceCenter.lat - targetCenter.lat
            ) < 1e-10 &&
            Math.abs(
                sourceCenter.lng - targetCenter.lng
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

        setTimeout(function() {
            target._gcpSyncLocked = false;
        }, 250);

    }, 100);
}


/*
 * Optional helper for future coordinated programmatic
 * view changes.
 */
window.gcpMapSync.setSynchronizedView =
    function(center, zoom) {

        const state = window.gcpMapSyncState;

        if (
            !state ||
            !state.reference ||
            !state.historical
        ) {
            return;
        }

        state.fittingLayer = true;

        state.reference.setView(
            center,
            zoom,
            {
                animate: false
            }
        );

        state.historical.setView(
            center,
            zoom,
            {
                animate: false
            }
        );

        setTimeout(function() {
            state.fittingLayer = false;
        }, 300);
    };
