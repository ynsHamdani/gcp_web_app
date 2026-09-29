/* =========================================================
 * Historical Map GCP Collection
 * Robust synchronized Leaflet map handling
 *
 * Design goals:
 *   1. Normal user pan/zoom on either map is synchronized.
 *   2. The latest user view is kept in browser-side state.
 *   3. Dash/React re-renders must NOT restore an old center/zoom.
 *   4. Only the explicit "Zoom to layer" buttons may perform
 *      an intentional programmatic navigation.
 *   5. Programmatic synchronization must not bounce between maps.
 *
 * No Dash viewport property is used.
 * ========================================================= */


window.gcpMapSync = Object.assign({}, window.gcpMapSync, {
    handlers: {

        // =====================================================
        // REGISTER MAPS
        // =====================================================

        registerReference: function(e, ctx) {
            registerMap("reference", ctx.map);
        },


        registerHistorical: function(e, ctx) {
            registerMap("historical", ctx.map);
        },


        // =====================================================
        // REFERENCE -> HISTORICAL
        // =====================================================

        syncReference: function(e, ctx) {
            handleMapMovement(
                "reference",
                ctx.map
            );
        },


        // =====================================================
        // HISTORICAL -> REFERENCE
        // =====================================================

        syncHistorical: function(e, ctx) {
            handleMapMovement(
                "historical",
                ctx.map
            );
        }
    }
});


// =========================================================
// GLOBAL STATE
// =========================================================

function ensureState() {

    window.gcpMapSyncState =
        window.gcpMapSyncState || {};

    const state =
        window.gcpMapSyncState;

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

    if (!state.userInteractionUntil) {
        state.userInteractionUntil = {
            reference: 0,
            historical: 0
        };
    }

    if (!state.syncTimers) {
        state.syncTimers = {
            reference: null,
            historical: null
        };
    }

    if (!state.restoreTimers) {
        state.restoreTimers = {
            reference: null,
            historical: null
        };
    }

    if (typeof state.syncingUntil !== "number") {
        state.syncingUntil = 0;
    }

    if (typeof state.programmaticNavigationUntil !== "number") {
        state.programmaticNavigationUntil = 0;
    }

    if (typeof state.listenersInstalled !== "boolean") {
        state.listenersInstalled = false;
    }

    return state;
}


// =========================================================
// MAP REGISTRATION
// =========================================================

function registerMap(
    name,
    map
) {

    if (!map) {
        return;
    }

    const state = ensureState();
    const previousMap = state.maps[name];

    state.maps[name] = map;

    installUserInteractionListeners(
        map,
        name
    );

    installNavigationButtonListener();

    /*
     * If Dash/React created a new Leaflet map instance, restore
     * the last browser-side user view. This prevents the new map
     * instance from falling back to the stale Dash center/zoom.
     */
    if (
        previousMap &&
        previousMap !== map &&
        isValidView(state.lastViews[name])
    ) {
        scheduleSafeRestore(
            name,
            map,
            state.lastViews[name]
        );
        return;
    }

    /*
     * First registration: the current Leaflet view is authoritative.
     */
    if (!isValidView(state.lastViews[name])) {
        state.lastViews[name] = readView(map);
    }
}


// =========================================================
// USER INTERACTION DETECTION
// =========================================================
//
// Leaflet's moveend/zoomend events do not tell us whether a
// movement came from the user or from Dash/React setting the
// component's center/zoom props.
//
// We therefore mark genuine browser interaction at the DOM
// level. This is critical because a later Dash re-render may
// otherwise look exactly like a user's map movement.
// =========================================================

function installUserInteractionListeners(
    map,
    name
) {

    if (!map || map._gcpInteractionListenersInstalled) {
        return;
    }

    const container = map.getContainer();

    if (!container) {
        return;
    }

    const markUserInteraction = function() {
        const state = ensureState();

        /*
         * Keep the flag alive long enough to cover the corresponding
         * moveend/zoomend generated by the user's action.
         */
        state.userInteractionUntil[name] =
            Date.now() + 1200;
    };

    container.addEventListener(
        "pointerdown",
        markUserInteraction,
        true
    );

    container.addEventListener(
        "mousedown",
        markUserInteraction,
        true
    );

    container.addEventListener(
        "touchstart",
        markUserInteraction,
        true
    );

    container.addEventListener(
        "wheel",
        markUserInteraction,
        true
    );

    container.addEventListener(
        "keydown",
        markUserInteraction,
        true
    );

    map._gcpInteractionListenersInstalled = true;
}


function isUserMovement(name) {

    const state = ensureState();

    return (
        Date.now() <=
        state.userInteractionUntil[name]
    );
}


// =========================================================
// NAVIGATION BUTTON DETECTION
// =========================================================
//
// The existing navigation.py callback performs Zoom-to-layer
// through Dash outputs. We cannot directly observe that callback
// from Python here, but we can observe the actual button click.
// This gives the browser-side synchronizer permission to accept
// the following programmatic center/zoom change.
// =========================================================

function installNavigationButtonListener() {

    const state = ensureState();

    if (state.listenersInstalled) {
        return;
    }

    document.addEventListener(
        "click",
        function(event) {

            const target =
                event.target instanceof Element
                    ? event.target.closest(
                        "#reference-layer-zoom-button, #historical-layer-zoom-button"
                    )
                    : null;

            if (!target) {
                return;
            }

            const currentState = ensureState();

            /*
             * Dash normally applies the center/zoom a moment after
             * the button click. Give that change a reasonable window
             * in which it is considered intentional.
             */
            currentState.programmaticNavigationUntil =
                Date.now() + 1800;
        },
        true
    );

    state.listenersInstalled = true;
}


// =========================================================
// MOVEMENT HANDLING
// =========================================================

function handleMapMovement(
    name,
    map
) {

    const state = ensureState();

    /*
     * Ignore move/zoom events generated by our own synchronized
     * setView(). The target view has already been recorded.
     */
    if (Date.now() <= state.syncingUntil) {
        return;
    }

    if (!map) {
        return;
    }

    /*
     * Genuine user pan/zoom:
     * this is the authoritative new view and must be synchronized.
     */
    if (isUserMovement(name)) {

        const view = readView(map);

        if (!isValidView(view)) {
            return;
        }

        state.lastViews[name] = view;

        scheduleSynchronization(
            name,
            map,
            view
        );

        return;
    }

    /*
     * Intentional programmatic navigation from the existing
     * "Zoom to layer" controls.
     */
    if (
        Date.now() <=
        state.programmaticNavigationUntil
    ) {
        scheduleProgrammaticAcceptance(
            name,
            map
        );
        return;
    }

    /*
     * Any other programmatic movement is presumed to be a Dash/React
     * reconciliation of stale center/zoom properties. Restore the
     * last browser-side user view instead of accepting the stale one.
     */
    restoreLastView(
        name,
        map
    );
}


// =========================================================
// USER VIEW SYNCHRONIZATION
// =========================================================

function scheduleSynchronization(
    name,
    source,
    view
) {

    const state = ensureState();

    if (state.syncTimers[name]) {
        clearTimeout(
            state.syncTimers[name]
        );
    }

    state.syncTimers[name] =
        setTimeout(function() {

            state.syncTimers[name] = null;

            if (!source) {
                return;
            }

            if (!isValidView(view)) {
                return;
            }

            if (
                !state.maps.reference ||
                !state.maps.historical
            ) {
                return;
            }

            const targetName =
                name === "reference"
                    ? "historical"
                    : "reference";

            const target =
                state.maps[targetName];

            if (!target) {
                return;
            }

            const targetView =
                readView(target);

            if (
                isValidView(targetView) &&
                sameView(view, targetView)
            ) {
                state.lastViews[targetName] =
                    targetView;
                return;
            }

            /*
             * Programmatically update only the opposite map.
             * Its moveend/zoomend events will be ignored by the
             * short synchronization lock below.
             */
            state.syncingUntil =
                Date.now() + 350;

            target.setView(
                view.center,
                view.zoom,
                {
                    animate: false
                }
            );

            state.lastViews[targetName] = {
                center: [
                    view.center[0],
                    view.center[1]
                ],
                zoom: view.zoom
            };

        }, 60);
}


// =========================================================
// PROGRAMMATIC NAVIGATION ACCEPTANCE
// =========================================================
//
// Zoom-to-layer changes both maps through Dash. We wait briefly
// so both maps can receive the new center/zoom before accepting
// the view as intentional.
// =========================================================

function scheduleProgrammaticAcceptance(
    name,
    map
) {

    const state = ensureState();

    if (state.restoreTimers[name]) {
        clearTimeout(
            state.restoreTimers[name]
        );
    }

    state.restoreTimers[name] =
        setTimeout(function() {

            state.restoreTimers[name] = null;

            if (!map) {
                return;
            }

            const currentView =
                readView(map);

            if (!isValidView(currentView)) {
                return;
            }

            const otherName =
                name === "reference"
                    ? "historical"
                    : "reference";

            const otherMap =
                state.maps[otherName];

            if (!otherMap) {
                state.lastViews[name] = currentView;
                return;
            }

            const otherView =
                readView(otherMap);

            /*
             * The existing navigation callback deliberately sends
             * the same view to both maps. Accept it only when the two
             * browser maps have converged to the same view.
             */
            if (
                isValidView(otherView) &&
                sameView(currentView, otherView)
            ) {
                state.lastViews.reference = {
                    center: [
                        currentView.center[0],
                        currentView.center[1]
                    ],
                    zoom: currentView.zoom
                };

                state.lastViews.historical = {
                    center: [
                        currentView.center[0],
                        currentView.center[1]
                    ],
                    zoom: currentView.zoom
                };

                return;
            }

            /*
             * If only one map moved, do not accept it. Restore its
             * previous browser-side view.
             */
            restoreLastView(
                name,
                map
            );

        }, 120);
}


// =========================================================
// SAFE RESTORATION
// =========================================================

function restoreLastView(
    name,
    map
) {

    const state = ensureState();
    const view = state.lastViews[name];

    if (
        !map ||
        !isValidView(view)
    ) {
        return;
    }

    const currentView =
        readView(map);

    if (
        isValidView(currentView) &&
        sameView(currentView, view)
    ) {
        return;
    }

    applyViewSafely(
        map,
        view
    );
}


function scheduleSafeRestore(
    name,
    map,
    view
) {

    const state = ensureState();

    if (state.restoreTimers[name]) {
        clearTimeout(
            state.restoreTimers[name]
        );
    }

    state.restoreTimers[name] =
        setTimeout(function() {

            state.restoreTimers[name] = null;

            if (
                map &&
                isValidView(view)
            ) {
                applyViewSafely(
                    map,
                    view
                );
            }

        }, 0);
}


function applyViewSafely(
    map,
    view
) {

    if (
        !map ||
        !isValidView(view)
    ) {
        return;
    }

    const state = ensureState();

    state.syncingUntil =
        Date.now() + 350;

    map.setView(
        view.center,
        view.zoom,
        {
            animate: false
        }
    );
}


// =========================================================
// VIEW HELPERS
// =========================================================

function readView(map) {

    if (!map) {
        return null;
    }

    const center = map.getCenter();
    const zoom = map.getZoom();

    return {
        center: [
            center.lat,
            center.lng
        ],
        zoom: zoom
    };
}


function isValidView(view) {

    return (
        view &&
        Array.isArray(view.center) &&
        view.center.length === 2 &&
        Number.isFinite(view.center[0]) &&
        Number.isFinite(view.center[1]) &&
        Number.isFinite(view.zoom)
    );
}


function sameView(
    a,
    b
) {

    if (
        !isValidView(a) ||
        !isValidView(b)
    ) {
        return false;
    }

    return (
        a.zoom === b.zoom &&
        Math.abs(
            a.center[0] - b.center[0]
        ) < 1e-10 &&
        Math.abs(
            a.center[1] - b.center[1]
        ) < 1e-10
    );
}


// =========================================================
// OPTIONAL PROGRAMMATIC HELPER
// =========================================================
//
// Existing/future code can use this helper for a deliberate
// coordinated view change. It is treated as intentional in the
// same way as the Zoom-to-layer buttons.
// =========================================================

window.gcpMapSync.setSynchronizedView =
    function(center, zoom) {

        const state = ensureState();

        if (
            !state.maps.reference ||
            !state.maps.historical
        ) {
            return;
        }

        const view = {
            center: [
                Number(center[0]),
                Number(center[1])
            ],
            zoom: Number(zoom)
        };

        if (!isValidView(view)) {
            return;
        }

        state.programmaticNavigationUntil =
            Date.now() + 1800;

        state.syncingUntil =
            Date.now() + 350;

        state.maps.reference.setView(
            view.center,
            view.zoom,
            {
                animate: false
            }
        );

        state.maps.historical.setView(
            view.center,
            view.zoom,
            {
                animate: false
            }
        );

        state.lastViews.reference = {
            center: [
                view.center[0],
                view.center[1]
            ],
            zoom: view.zoom
        };

        state.lastViews.historical = {
            center: [
                view.center[0],
                view.center[1]
            ],
            zoom: view.zoom
        };
    };
