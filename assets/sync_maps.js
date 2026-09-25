window.gcpMapSync = Object.assign({}, window.gcpMapSync, {
    handlers: {

        registerReference: function(e, ctx) {
            window.gcpMapSyncState = window.gcpMapSyncState || {};
            window.gcpMapSyncState.reference = ctx.map;
        },

        registerHistorical: function(e, ctx) {
            window.gcpMapSyncState = window.gcpMapSyncState || {};
            window.gcpMapSyncState.historical = ctx.map;
        },

        syncReference: function(e, ctx) {
            const state = window.gcpMapSyncState;

            if (!state || !state.historical) {
                return;
            }

            const source = ctx.map;
            const target = state.historical;

            if (source === target || source._gcpSyncLocked) {
                return;
            }

            syncMapView(source, target);
        },

        syncHistorical: function(e, ctx) {
            const state = window.gcpMapSyncState;

            if (!state || !state.reference) {
                return;
            }

            const source = ctx.map;
            const target = state.reference;

            if (source === target || source._gcpSyncLocked) {
                return;
            }

            syncMapView(source, target);
        }
    }
});


function syncMapView(source, target) {

    const sourceCenter = source.getCenter();
    const sourceZoom = source.getZoom();

    const targetCenter = target.getCenter();
    const targetZoom = target.getZoom();

    const sameView =
        sourceZoom === targetZoom &&
        Math.abs(sourceCenter.lat - targetCenter.lat) < 1e-10 &&
        Math.abs(sourceCenter.lng - targetCenter.lng) < 1e-10;

    if (sameView) {
        return;
    }

    // Prevent the target map's own event from syncing back.
    target._gcpSyncLocked = true;

    target.setView(
        sourceCenter,
        sourceZoom,
        {
            animate: false
        }
    );

    // setView with animate:false completes immediately.
    setTimeout(function() {
        target._gcpSyncLocked = false;
    }, 0);
}