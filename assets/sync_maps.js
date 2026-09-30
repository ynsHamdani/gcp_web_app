/* =========================================================
 * Historical Map GCP Collection
 * Reliable two-map Leaflet synchronisation
 *
 * Synchronisation is attached through dash-leaflet's native
 * eventHandlers in maps/map_views.py:
 *   - drag / dragend  -> pan synchronisation
 *   - zoom / zoomend  -> zoom synchronisation
 *
 * No secondary map.on(...) listener installation is used.
 * This avoids duplicate handlers and makes the synchronisation
 * path explicit and deterministic.
 * ========================================================= */

window.gcpMapSync = Object.assign({}, window.gcpMapSync, {
    handlers: {
        registerReference: function(e, ctx) {
            const map = getMap(e, ctx);
            if (map) {
                registerMap("reference", map);
            }
        },

        registerHistorical: function(e, ctx) {
            const map = getMap(e, ctx);
            if (map) {
                registerMap("historical", map);
            }
        },

        syncReference: function(e, ctx) {
            syncMap("reference", getMap(e, ctx));
        },

        syncHistorical: function(e, ctx) {
            syncMap("historical", getMap(e, ctx));
        }
    }
});


function getMap(e, ctx) {
    // For Leaflet map events, e.target is the map that emitted the event.
    // ctx.map is the dash-leaflet documented map reference.
    if (e && e.target) {
        return e.target;
    }

    if (ctx && ctx.map) {
        return ctx.map;
    }

    return null;
}


function ensureState() {
    window.gcpMapSyncState = window.gcpMapSyncState || {};
    const state = window.gcpMapSyncState;

    if (!state.maps) {
        state.maps = {
            reference: null,
            historical: null
        };
    }

    if (!state.lastViews) {
        state.lastViews = {
            reference: null,
            historical: null
        };
    }

    return state;
}


function registerMap(name, map) {
    if (!map) {
        return;
    }

    const state = ensureState();
    const previous = state.maps[name];

    state.maps[name] = map;

    if (!isValidView(state.lastViews[name]) || previous !== map) {
        state.lastViews[name] = readView(map);
    }
}


function syncMap(name, map) {
    if (!map) {
        return;
    }

    const state = ensureState();

    // Always register from the event itself, so synchronisation does not
    // depend on the load/mouseover registration having happened earlier.
    if (state.maps[name] !== map) {
        registerMap(name, map);
    }

    // This map is currently being changed by the synchroniser.
    if (map._gcpSyncTarget) {
        return;
    }

    const sourceView = readView(map);
    if (!isValidView(sourceView)) {
        return;
    }

    state.lastViews[name] = cloneView(sourceView);

    const targetName = name === "reference" ? "historical" : "reference";
    const target = state.maps[targetName];

    if (!target) {
        return;
    }

    const targetView = readView(target);

    if (isValidView(targetView) && sameView(sourceView, targetView)) {
        state.lastViews[targetName] = cloneView(targetView);
        return;
    }

    setTargetView(target, sourceView, targetName);
}


function setTargetView(target, view, targetName) {
    if (!target || !isValidView(view)) {
        return;
    }

    const state = ensureState();
    const current = readView(target);

    if (isValidView(current) && sameView(current, view)) {
        state.lastViews[targetName] = cloneView(current);
        return;
    }

    /*
     * Mark the target before setView(). Leaflet emits zoom/move events
     * while setView() is executing, so those events are ignored as part
     * of this same synchronisation operation instead of bouncing back.
     */
    target._gcpSyncTarget = true;

    try {
        target.setView(
            view.center,
            view.zoom,
            {
                animate: false
            }
        );
    } finally {
        target._gcpSyncTarget = false;
    }

    state.lastViews[targetName] = cloneView(view);
}


function readView(map) {
    if (!map) {
        return null;
    }

    const center = map.getCenter();

    return {
        center: [
            Number(center.lat),
            Number(center.lng)
        ],
        zoom: Number(map.getZoom())
    };
}


function cloneView(view) {
    return {
        center: [
            Number(view.center[0]),
            Number(view.center[1])
        ],
        zoom: Number(view.zoom)
    };
}


function isValidView(view) {
    return Boolean(
        view &&
        Array.isArray(view.center) &&
        view.center.length === 2 &&
        Number.isFinite(Number(view.center[0])) &&
        Number.isFinite(Number(view.center[1])) &&
        Number.isFinite(Number(view.zoom))
    );
}


function sameView(a, b) {
    if (!isValidView(a) || !isValidView(b)) {
        return false;
    }

    return (
        Math.abs(Number(a.center[0]) - Number(b.center[0])) < 1e-7 &&
        Math.abs(Number(a.center[1]) - Number(b.center[1])) < 1e-7 &&
        Math.abs(Number(a.zoom) - Number(b.zoom)) < 1e-6
    );
}


/* Compatibility helper for deliberate browser-side coordinated moves. */
window.gcpMapSync.setSynchronizedView = function(center, zoom) {
    const view = {
        center: [Number(center[0]), Number(center[1])],
        zoom: Number(zoom)
    };

    if (!isValidView(view)) {
        return;
    }

    const state = ensureState();

    ["reference", "historical"].forEach(function(name) {
        const map = state.maps[name];
        if (map) {
            setTargetView(map, view, name);
        }
    });
};
