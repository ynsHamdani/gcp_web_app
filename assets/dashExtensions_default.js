window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(e, ctx) {
            if (window.gcpHandleMapMove) {
                window.gcpHandleMapMove(e, ctx);
            }
        }

    }
});