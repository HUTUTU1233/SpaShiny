(function () {
  "use strict";
  if (window.__spashinyNativeSocketAudit) return;
  window.__spashinyNativeSocketAudit = true;
  function install() {
    var app = window.Shiny && window.Shiny.shinyapp;
    var socket = app && app.$socket;
    if (!socket || !socket.addEventListener || socket.__spashinyCloseAudited) return;
    socket.__spashinyCloseAudited = true;
    socket.addEventListener("close", function (event) {
      var reason = String(event.reason || "").replace(/((?:token|secret|sig)=)[^&\s]+/gi, "$1[redacted]").slice(0, 300);
      var detail = {code: event.code, reason: reason, wasClean: event.wasClean,
                    browserOnline: navigator.onLine, visibility: document.visibilityState};
      window.__spashinyLastSocketClose = detail;
      console.warn("SpaShiny WebSocket closed", detail);
      fetch("/api/session/client-diagnostic", {
        method: "POST", credentials: "same-origin", keepalive: true,
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({event_type: "WEBSOCKET_CLOSE_DETAILS",
          page_instance_id: (window.sessionStorage.getItem("spashiny_page_instance_id") || "").slice(0, 100),
          ready_state: document.readyState, has_shiny: !!window.Shiny,
          error_name: "websocket_close_" + event.code, error_message: JSON.stringify(detail)})
      }).catch(function () {});
    });
  }
  if (window.jQuery) window.jQuery(document).on("shiny:connected.spashinyNativeAudit", install);
  document.addEventListener("shiny:connected", install);
  // Also handles a cached page where Shiny connected before this asset loaded.
  var attempts = 0;
  var timer = window.setInterval(function () { install(); if (++attempts >= 30) clearInterval(timer); }, 1000);
})();
