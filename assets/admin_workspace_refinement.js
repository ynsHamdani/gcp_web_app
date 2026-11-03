/* Admin workspace navigation, synchronized viewport polish and collection cursor. */
(function installAdminWorkspaceRefinement() {
    if (window.adminWorkspaceRefinementInstalled) return;
    window.adminWorkspaceRefinementInstalled = true;

    function openContainingDetails(target) {
        if (!target) return;
        if (target.tagName === "DETAILS") target.open = true;
        let parent = target.parentElement;
        while (parent) {
            if (parent.tagName === "DETAILS") parent.open = true;
            parent = parent.parentElement;
        }
    }

    function setActiveNav(button) {
        document.querySelectorAll(".admin-nav-link").forEach(function (node) {
            node.classList.toggle("is-active", node === button);
        });
    }

    function navigateFromHash() {
        const targetId = (window.location.hash || "").replace(/^#/, "");
        if (!targetId) return;
        const target = document.getElementById(targetId);
        if (!target) return;
        openContainingDetails(target);
        const matchingButton = document.querySelector('[data-admin-nav="' + targetId + '"]');
        if (matchingButton) setActiveNav(matchingButton);
        window.setTimeout(function () { target.scrollIntoView({ behavior: "smooth", block: "start" }); }, 120);
    }

    document.addEventListener("click", function (event) {
        const button = event.target.closest("[data-admin-nav]");
        if (!button) return;
        event.preventDefault();
        const targetId = button.getAttribute("data-admin-nav");
        const target = targetId ? document.getElementById(targetId) : null;
        if (!target) return;
        openContainingDetails(target);
        setActiveNav(button);
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        if (window.history && window.history.replaceState) {
            window.history.replaceState(null, "", window.location.pathname + window.location.search + "#" + targetId);
        }
    });

    const style = document.createElement("style");
    style.id = "admin-workspace-refinement-style";
    style.textContent = `
        .admin-nav-link { color: #334155 !important; transition: background .15s ease, color .15s ease; }
        .admin-nav-link:hover { background: #e8eef8 !important; }
        .admin-nav-link.is-active { color: #1d4ed8 !important; background: #eaf1ff !important; border-color: #bfdbfe !important; font-weight: 700 !important; }
        #admin-add-gcp-panel, #admin-filter-panel, #admin-maps, #admin-records { scroll-margin-top: 78px; }
        #reference-map.admin-gcp-collection-active,
        #reference-map.admin-gcp-collection-active *,
        #historical-map.admin-gcp-collection-active,
        #historical-map.admin-gcp-collection-active * { cursor: crosshair !important; }
        #historical-map.admin-gcp-collection-active .leaflet-marker-draggable { cursor: grab !important; }
        #historical-map.admin-gcp-collection-active .leaflet-marker-draggable:active { cursor: grabbing !important; }
        @media (max-width: 900px) {
            .admin-container #admin-maps { grid-template-columns: minmax(0, 1fr) !important; }
            .admin-container #admin-add-gcp-panel > div:nth-of-type(2) { grid-template-columns: minmax(0, 1fr) !important; }
        }
    `;
    if (!document.getElementById(style.id)) document.head.appendChild(style);

    function isCollectionActive() {
        const button = document.getElementById("admin-add-gcp-button");
        return !!button && (button.textContent || "").toLowerCase().includes("stop gcp");
    }

    function updateCollectionCursor() {
        const active = isCollectionActive();
        ["reference-map", "historical-map"].forEach(function (id) {
            const map = document.getElementById(id);
            if (map) map.classList.toggle("admin-gcp-collection-active", active);
        });
    }

    function observeCollectionButton() {
        const button = document.getElementById("admin-add-gcp-button");
        if (!button || button._adminCollectionObserver) return;
        const observer = new MutationObserver(updateCollectionCursor);
        observer.observe(button, { childList: true, characterData: true, subtree: true });
        button.addEventListener("click", function () {
            window.setTimeout(updateCollectionCursor, 0);
            window.setTimeout(updateCollectionCursor, 80);
            window.setTimeout(updateCollectionCursor, 180);
        }, true);
        button._adminCollectionObserver = observer;
    }

    function install() {
        observeCollectionButton();
        updateCollectionCursor();
        navigateFromHash();
        if (document.body && !window.adminWorkspaceDomObserver) {
            window.adminWorkspaceDomObserver = new MutationObserver(function () {
                observeCollectionButton();
                updateCollectionCursor();
            });
            window.adminWorkspaceDomObserver.observe(document.body, { childList: true, subtree: true });
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", install, { once: true });
    } else {
        install();
    }
})();
