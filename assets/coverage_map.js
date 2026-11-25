/* Polygon/GCP styling and safe popups for the Coverage & Statistics map. */
(function () {
    window.coverageMap = window.coverageMap || {};
    window.coverageMap.handlers = Object.assign({}, window.coverageMap.handlers || {}, {
        polygonStyle: function (feature) {
            const p = (feature && feature.properties) || {};
            const count = Number(p.assigned_count || 0);
            let fill = "#e2e8f0";
            if (count > 0 && count <= 5) fill = "#bfdbfe";
            else if (count <= 20 && count > 5) fill = "#60a5fa";
            else if (count > 20) fill = "#2563eb";
            return { color: "#334155", weight: 1, fillColor: fill, fillOpacity: 0.35 };
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
            layer.bindTooltip(String(label), { sticky: true, direction: "top" });
            layer.on("click", function () {
                const root = document.createElement("div");
                const title = document.createElement("strong");
                title.textContent = String(label);
                root.appendChild(title);
                [["Feature ID", p.coverage_feature_id], ["Source key", p.source_feature_key], ["Uniquely assigned GCPs", p.assigned_count]].forEach(function (entry) {
                    const line = document.createElement("div");
                    line.textContent = `${entry[0]}: ${entry[1] == null ? "" : entry[1]}`;
                    root.appendChild(line);
                });
                const context = p.context_breakdown || {};
                const contextLine = document.createElement("div");
                contextLine.textContent = "GCP context: " + (Object.keys(context).length
                    ? Object.entries(context).map(([label, count]) => `${label}: ${count}`).join("; ")
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
