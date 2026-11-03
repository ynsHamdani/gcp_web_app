/* Admin-only GCP GeoJSON marker styling, tooltips, and safe popups. */
(function () {
    window.adminGcp = window.adminGcp || {};
    window.adminGcp.handlers = Object.assign({}, window.adminGcp.handlers || {}, {
        pointToLayer: function (feature, latlng, context) {
            const props = (feature && feature.properties) || {};
            const hideout = (context && context.hideout) || {};
            const selected = String(hideout.selected_gcp_id || "") === String(props.gcp_id || "");
            return L.circleMarker(latlng, {
                radius: selected ? 9 : 6,
                color: selected ? "#991b1b" : "#1d4ed8",
                weight: selected ? 3 : 1.5,
                fillColor: selected ? "#ef4444" : "#3b82f6",
                fillOpacity: 0.9
            });
        },
        onEachFeature: function (feature, layer) {
            const p = (feature && feature.properties) || {};
            const tooltip = [p.gcp_id || "GCP", p.contributor || "Unknown contributor", p.historical_layer || ""].filter(Boolean).join(" · ");
            layer.bindTooltip(tooltip, { sticky: true, direction: "top" });

            layer.on("click", function () {
                // Build popup content with textContent, never interpolated HTML.
                const root = document.createElement("div");
                const title = document.createElement("strong");
                title.textContent = p.gcp_id || "GCP";
                root.appendChild(title);
                [
                    ["Contributor", p.contributor],
                    ["Role", p.contributor_role],
                    ["Historical layer", p.historical_layer],
                    ["Reference layer", p.reference_layer],
                    ["Offset", p.offset_m == null ? "" : `${p.offset_m} m`],
                    ["Status", p.status],
                    ["Recorded", p.recorded_at]
                ].forEach(function (item) {
                    if (item[1] === undefined || item[1] === null || item[1] === "") return;
                    const line = document.createElement("div");
                    line.textContent = `${item[0]}: ${item[1]}`;
                    root.appendChild(line);
                });
                layer.bindPopup(root).openPopup();
            });
        }
    });
})();
