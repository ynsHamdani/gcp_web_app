/* Polygon/GCP styling and safe popups for the Coverage & Statistics map.
   Selection is kept outside GeoJSON props so dropdown interaction cannot
   re-render the polygon layer and close its popup. */
(function () {
    window.coverageMap = window.coverageMap || {};

    function basePolygonStyle(feature) {
        const p = (feature && feature.properties) || {};
        const count = Number(p.assigned_count || 0);
        let fill = "#e2e8f0";
        if (count > 0 && count <= 5) fill = "#bfdbfe";
        else if (count <= 20 && count > 5) fill = "#60a5fa";
        else if (count > 20) fill = "#2563eb";
        return { color: "#334155", weight: 1, fillColor: fill, fillOpacity: 0.35 };
    }

    window.coverageMap.clearSelectedPolygon = function () {
        const previous = window.coverageMap._selectedPolygon;
        if (previous && typeof previous.setStyle === "function") {
            previous.setStyle(window.coverageMap._selectedPolygonBaseStyle || {});
        }
        window.coverageMap._selectedPolygon = null;
        window.coverageMap._selectedPolygonBaseStyle = null;
    };

    window.coverageMap.handlers = Object.assign({}, window.coverageMap.handlers || {}, {
        polygonStyle: function (feature) {
            return basePolygonStyle(feature);
        },
        pointToLayer: function (feature, latlng) {
            const p = (feature && feature.properties) || {};
            let color = "#15803d";
            if (p.assignment_reason === "UNCOVERED") color = "#d97706";
            if (p.assignment_reason === "MULTIPLE_MATCHES") color = "#dc2626";
            return L.circleMarker(latlng, { radius: 5, color: "#ffffff", weight: 1, fillColor: color, fillOpacity: 0.95 });
        },
        onEachPolygon: function (feature, layer) {
            const p = (feature && feature.properties) || {};
            const label = p.feature_label || p.source_feature_key || "Coverage feature";
            const featureId = Number(p.coverage_feature_id || feature.id);
            const layerId = Number(p.coverage_layer_id);
            const normalStyle = basePolygonStyle(feature);

            // Polygon information is intentionally click-only; hovering stays quiet.
            layer.on("click", function (event) {
                if (event && event.originalEvent) L.DomEvent.stopPropagation(event.originalEvent);

                // Highlight the selected polygon directly in Leaflet. Do not
                // update GeoJSON.hideout: changing that prop rebuilds the
                // layer and can dismiss its popup/lose the click state.
                window.coverageMap.clearSelectedPolygon();
                window.coverageMap._selectedPolygon = layer;
                window.coverageMap._selectedPolygonBaseStyle = normalStyle;
                layer.setStyle({
                    color: "#c2410c", weight: 3,
                    fillColor: "#fb923c", fillOpacity: 0.58
                });

                // The stable Dash Store is the assignment workflow's source
                // of truth. The student dropdown does not participate in map
                // selection and therefore cannot clear the selected feature.
                if (featureId > 0 && layerId > 0 && window.dash_clientside
                    && typeof window.dash_clientside.set_props === "function") {
                    window.dash_clientside.set_props("coverage-selected-feature", {
                        data: {
                            coverage_feature_id: featureId,
                            coverage_layer_id: layerId,
                            click_nonce: Date.now()
                        }
                    });
                } else {
                    console.warn("Coverage polygon selection could not be sent to Dash: missing feature/layer ID or set_props API.");
                }

                // Build popup content with textContent, never interpolated HTML.
                const root = document.createElement("div");
                const title = document.createElement("strong");
                title.textContent = String(label);
                root.appendChild(title);
                [
                    ["Feature ID", featureId],
                    ["Source key", p.source_feature_key],
                    ["Uniquely assigned GCPs", p.assigned_count]
                ].forEach(function (entry) {
                    const line = document.createElement("div");
                    line.textContent = `${entry[0]}: ${entry[1] == null ? "" : entry[1]}`;
                    root.appendChild(line);
                });
                const contextBreakdown = p.context_breakdown || {};
                const contextLine = document.createElement("div");
                contextLine.textContent = "GCP context: " + (Object.keys(contextBreakdown).length
                    ? Object.entries(contextBreakdown).map(([name, count]) => `${name}: ${count}`).join("; ")
                    : "—");
                root.appendChild(contextLine);
                const attrs = p.attributes || {};
                Object.entries(attrs).slice(0, 12).forEach(function (entry) {
                    const line = document.createElement("div");
                    let value = entry[1];
                    if (value && typeof value === "object") value = JSON.stringify(value);
                    line.textContent = `${entry[0]}: ${String(value == null ? "" : value).slice(0, 240)}`;
                    root.appendChild(line);
                });
                layer.bindPopup(root).openPopup();
            });
        },
        onEachGcp: function (feature, layer) {
            const p = (feature && feature.properties) || {};
            layer.on("click", function () {
                const root = document.createElement("div");
                const title = document.createElement("strong");
                title.textContent = String(p.gcp_id || "GCP");
                root.appendChild(title);
                [["Assignment", p.assignment_status], ["Reason", p.assignment_reason], ["Match count", p.match_count], ["Context", p.context_category], ["GCP status", p.gcp_status]].forEach(function (entry) {
                    if (entry[1] == null || entry[1] === "") return;
                    const line = document.createElement("div");
                    line.textContent = `${entry[0]}: ${entry[1]}`;
                    root.appendChild(line);
                });
                layer.bindPopup(root).openPopup();
            });
        }
    });
})();

/* Dismissible Coverage notifications: remove only the clicked alert. */
(function () {
    if (window.__coverageDismissHandlerInstalled) return;
    window.__coverageDismissHandlerInstalled = true;
    document.addEventListener("click", function (event) {
        const button = event.target && event.target.closest ? event.target.closest(".coverage-alert-close") : null;
        if (!button) return;
        const alert = button.closest(".coverage-dismissible-alert");
        if (alert) alert.remove();
    });
})();

/* Freeze background scrolling while the permanent-delete modal is open.
   Observe only the modal's style after it is mounted; do not watch every page
   mutation or every style change in the Coverage workspace. */
(function () {
    if (window.__coverageModalObserverInstalled) return;
    // The shared assets folder is also loaded by the student and other admin
    // Dash apps. The modal exists only on this page, so do not observe those pages.
    if (!String(window.location.pathname || "").startsWith("/admin/coverage/")) return;
    window.__coverageModalObserverInstalled = true;

    let previousOverflow = null;
    let modalObserver = null;
    let mountObserver = null;

    const sync = function () {
        const modal = document.getElementById("coverage-delete-dialog");
        const open = !!(modal && modal.style.display === "flex");
        if (open) {
            if (previousOverflow === null) previousOverflow = document.body.style.overflow;
            document.body.style.overflow = "hidden";
        } else if (previousOverflow !== null) {
            document.body.style.overflow = previousOverflow;
            previousOverflow = null;
        }
    };

    const attach = function () {
        const modal = document.getElementById("coverage-delete-dialog");
        if (modal) {
            if (mountObserver) mountObserver.disconnect();
            modalObserver = new MutationObserver(sync);
            modalObserver.observe(modal, { attributes: true, attributeFilter: ["style"] });
            sync();
            return true;
        }
        return false;
    };

    const start = function () {
        if (attach()) return;
        mountObserver = new MutationObserver(function () {
            attach();
        });
        mountObserver.observe(document.body, { childList: true, subtree: true });
    };

    if (document.body) start();
    else document.addEventListener("DOMContentLoaded", start, { once: true });
})();
