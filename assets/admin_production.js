/* Keep Leaflet map canvases correctly sized when accordion sections open/close. */
(function installAdminProductionMapSizing() {
    if (window.adminProductionMapSizingInstalled) return;
    window.adminProductionMapSizingInstalled = true;

    function invalidateMaps() {
        const syncMaps = window.gcpMapSyncState && window.gcpMapSyncState.maps;
        ["reference", "historical"].forEach(function (kind) {
            const map = syncMaps && syncMaps[kind];
            if (map && typeof map.invalidateSize === "function") {
                map.invalidateSize({ pan: false, debounceMoveend: true });
                return;
            }
            // Defensive fallback for Dash Leaflet versions exposing the map
            // instance directly on the container.
            const root = document.getElementById(kind + "-map");
            const fallback = root && (root._leaflet_map || root._leaflet);
            if (fallback && typeof fallback.invalidateSize === "function") {
                fallback.invalidateSize({ pan: false, debounceMoveend: true });
            }
        });
    }

    function scheduleInvalidate() {
        window.requestAnimationFrame(function () {
            invalidateMaps();
            window.setTimeout(invalidateMaps, 120);
            window.setTimeout(invalidateMaps, 320);
        });
    }

    document.addEventListener("toggle", function (event) {
        if (event.target && event.target.tagName === "DETAILS") {
            scheduleInvalidate();
        }
    }, true);

    document.addEventListener("click", function (event) {
        const nav = event.target.closest("[data-admin-nav]");
        if (nav) scheduleInvalidate();
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", scheduleInvalidate, { once: true });
    } else {
        scheduleInvalidate();
    }
})();
