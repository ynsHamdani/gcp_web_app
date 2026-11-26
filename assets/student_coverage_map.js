/* Assigned work polygons: transparent outline, no hover tooltip, click-only task popup. */
(function () {
    window.studentCoverage = window.studentCoverage || {};
    window.studentCoverage.handlers = Object.assign({}, window.studentCoverage.handlers || {}, {
        polygonStyle: function () {
            return {
                color: "#0f766e",
                weight: 2,
                opacity: 0.95,
                fill: true,
                fillOpacity: 0
            };
        },
        onEachFeature: function (feature, layer) {
            const props = (feature && feature.properties) || {};
            const label = props.feature_label || props.source_feature_key || "Assigned work area";
            layer.on("click", function (event) {
                if (event && event.originalEvent) L.DomEvent.stopPropagation(event.originalEvent);

                const root = document.createElement("div");
                root.className = "student-coverage-task-popup";

                const heading = document.createElement("strong");
                heading.textContent = String(label);
                root.appendChild(heading);

                const objective = String(props.objective || "").trim();
                const instructions = String(props.instructions || "").trim();
                if (objective) {
                    const objectiveLine = document.createElement("p");
                    objectiveLine.className = "student-coverage-objective";
                    objectiveLine.textContent = objective;
                    root.appendChild(objectiveLine);
                }

                if (instructions) {
                    const details = document.createElement("details");
                    details.className = "student-coverage-instructions";
                    const summary = document.createElement("summary");
                    summary.textContent = "Read full instructions";
                    const content = document.createElement("div");
                    content.className = "student-coverage-instructions-text";
                    content.textContent = instructions;
                    details.appendChild(summary);
                    details.appendChild(content);
                    root.appendChild(details);
                } else if (!objective) {
                    const empty = document.createElement("p");
                    empty.textContent = "No specific objective or instructions have been provided for this polygon.";
                    root.appendChild(empty);
                }

                layer.bindPopup(root, { maxWidth: 340, minWidth: 210 }).openPopup();
            });
        }
    });
})();
