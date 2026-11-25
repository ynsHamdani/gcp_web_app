/* Student-assigned polygons are visual-only and never capture map clicks. */
(function () {
    window.studentCoverage = window.studentCoverage || {};
    window.studentCoverage.handlers = Object.assign({}, window.studentCoverage.handlers || {}, {
        polygonStyle: function () {
            return {
                color: "#0f766e",
                weight: 2,
                fillColor: "#2dd4bf",
                fillOpacity: 0.22
            };
        },
        onEachFeature: function (feature, layer) {
            const props = (feature && feature.properties) || {};
            const label = props.feature_label || props.source_feature_key || "Assigned work area";
            layer.bindTooltip(String(label), {sticky: true, direction: "top"});
        }
    });
})();
