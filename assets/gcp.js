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


/* =========================================================
 * GCP collection cursor
 *
 * Important: do NOT observe the whole document's attributes here.
 * Changing a class/style on the map would otherwise trigger the same
 * MutationObserver again and create an endless browser-side loop.
 *
 * We only watch the Add GCP button's text/children, which is enough to
 * detect the existing "Add GCP" <-> "Stop GCP" state change.
 * ========================================================= */

(function installGcpCursor() {
    if (window.gcpGcpCursorInstalled) {
        return;
    }

    const STYLE_ID = "gcp-crosshair-style";

    function isCollectionActive() {
        const button = document.getElementById("add-gcp-button");
        if (!button) {
            return false;
        }

        return (button.textContent || "")
            .trim()
            .toLowerCase()
            .includes("stop gcp");
    }


    function ensureCursorStyle() {
        if (document.getElementById(STYLE_ID)) {
            return;
        }

        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            #reference-map.gcp-collection-active .leaflet-container,
            #reference-map.gcp-collection-active .leaflet-container *,
            #reference-map.leaflet-container.gcp-collection-active,
            #reference-map.leaflet-container.gcp-collection-active * {
                cursor: crosshair !important;
            }
        `;

        document.head.appendChild(style);
    }


    function updateCursor() {
        ensureCursorStyle();

        const root = document.getElementById("reference-map");
        if (!root) {
            return;
        }

        const active = isCollectionActive();
        root.classList.toggle("gcp-collection-active", active);

        const containers = [];
        if (root.classList.contains("leaflet-container")) {
            containers.push(root);
        }

        root.querySelectorAll(".leaflet-container").forEach(function(node) {
            if (!containers.includes(node)) {
                containers.push(node);
            }
        });

        containers.forEach(function(container) {
            if (active) {
                container.style.setProperty(
                    "cursor",
                    "crosshair",
                    "important"
                );
            } else {
                container.style.removeProperty("cursor");
            }
        });
    }


    function watchAddGcpButton() {
        const button = document.getElementById("add-gcp-button");
        if (!button || button._gcpCursorObserverInstalled) {
            return;
        }

        const observer = new MutationObserver(function() {
            updateCursor();
        });

        observer.observe(button, {
            childList: true,
            characterData: true,
            subtree: true
        });

        button.addEventListener("click", function() {
            // Dash changes the button label asynchronously.
            window.setTimeout(updateCursor, 0);
            window.setTimeout(updateCursor, 50);
            window.setTimeout(updateCursor, 150);
        }, true);

        button._gcpCursorObserverInstalled = true;
        updateCursor();
    }


    function install() {
        ensureCursorStyle();
        watchAddGcpButton();
        updateCursor();

        // Observe only DOM insertion, not attributes. This lets us recover
        // if Dash recreates the button/map without creating a feedback loop.
        if (document.body) {
            const bodyObserver = new MutationObserver(function() {
                watchAddGcpButton();
            });

            bodyObserver.observe(document.body, {
                childList: true,
                subtree: true
            });
        }
    }

    if (document.body) {
        install();
    } else {
        window.setTimeout(install, 100);
    }

    window.gcpGcpCursorInstalled = true;
})();
