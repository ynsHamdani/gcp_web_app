/* Student saved-GCP rendering. Pending markers remain separate Leaflet markers. */
(function () {
    window.studentGcp = window.studentGcp || {};
    window.studentGcp.handlers = Object.assign({}, window.studentGcp.handlers || {}, {
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
            const props = (feature && feature.properties) || {};
            if (props.gcp_id) {
                layer.bindTooltip(String(props.gcp_id), { sticky: true, direction: "top" });
            }
        }
    });
})();
