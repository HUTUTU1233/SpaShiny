(function () {
  "use strict";

  var BROWSER_CLIENT_KEY = "spashiny.browser.client.id";
  var TOKEN_KEY = "spashiny.session.token";
  var SESSION_ID_KEY = "spashiny.session.id";
  var ANALYSIS_SESSION_KEY = "spashiny.analysis.session.id";
  var STATUS_KEY = "spashiny.session.status";
  var heartbeatMs = 30000;
  var idleTimeoutSeconds = 300;
  var lastHeartbeatAt = 0;
  var heartbeatTimer = null;
  var idleTimer = null;
  var disconnectSent = false;
  var lifecycleInFlight = false;
  var fallbackStore = {};
  var pageInstanceId = "pending";
  var realtimeDisconnected = false;
  var disconnectNoticeHideTimer = null;

  function storageGet(kind, key) {
    try { return window[kind].getItem(key); }
    catch (_) { return fallbackStore[kind + ":" + key] || null; }
  }
  function storageSet(kind, key, value) {
    try { window[kind].setItem(key, value); }
    catch (_) { fallbackStore[kind + ":" + key] = String(value); }
  }
  function storageRemove(kind, key) {
    try { window[kind].removeItem(key); }
    catch (_) { delete fallbackStore[kind + ":" + key]; }
  }
  function uuid() {
    var cryptoObj = window.crypto || window.msCrypto || null;
    if (cryptoObj && typeof cryptoObj.randomUUID === "function") return cryptoObj.randomUUID();
    var bytes = new Uint8Array(16);
    if (cryptoObj && cryptoObj.getRandomValues) cryptoObj.getRandomValues(bytes);
    else for (var i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
    bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
    return Array.prototype.map.call(bytes, function (b, i) {
      var h = b.toString(16).padStart(2, "0");
      return [4, 6, 8, 10].indexOf(i) >= 0 ? "-" + h : h;
    }).join("");
  }
  function postClientDiagnostic(eventType, details) {
    try {
      var body = JSON.stringify({
        event_type: eventType,
        page_instance_id: pageInstanceId,
        ready_state: document.readyState || "",
        has_shiny: !!window.Shiny,
        navigation_type: (performance && performance.getEntriesByType && performance.getEntriesByType("navigation")[0] || {}).type || "",
        error_name: (details && details.error_name) || "",
        error_message: (details && details.error_message) || "",
      });
      if (typeof window.fetch === "function") {
        window.fetch("/api/session/client-diagnostic", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: body,
          keepalive: true,
        }).catch(function () {});
        return;
      }
      if (typeof window.XMLHttpRequest === "function") {
        var xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/session/client-diagnostic", true);
        xhr.setRequestHeader("Content-Type", "application/json");
        xhr.setRequestHeader("Accept", "application/json");
        xhr.send(body);
      }
    } catch (_) {}
  }
  function installDisconnectNoticeUI() {
    try {
      if (!document.getElementById("spashiny-disconnect-notice-style")) {
        var style = document.createElement("style");
        style.id = "spashiny-disconnect-notice-style";
        style.textContent = [
          "#shiny-disconnected-overlay,",
          ".shiny-disconnected-overlay,",
          "body > .shiny-disconnected-overlay,",
          "html > .shiny-disconnected-overlay {",
          "  display: none !important;",
          "  opacity: 0 !important;",
          "  visibility: hidden !important;",
          "  pointer-events: none !important;",
          "}",
          "#spashiny-disconnect-notice {",
          "  position: fixed;",
          "  right: 18px;",
          "  bottom: 18px;",
          "  max-width: min(420px, calc(100vw - 36px));",
          "  z-index: 2147483647;",
          "  padding: 14px 16px;",
          "  border-radius: 14px;",
          "  border: 1px solid rgba(245, 158, 11, 0.55);",
          "  background: rgba(17, 24, 39, 0.94);",
          "  color: #fff;",
          "  box-shadow: 0 16px 48px rgba(15, 23, 42, 0.28);",
          "  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;",
          "  line-height: 1.42;",
          "  display: none;",
          "}",
          "#spashiny-disconnect-notice.spashiny-visible { display: block; }",
          "#spashiny-disconnect-notice.spashiny-reconnected {",
          "  border-color: rgba(34, 197, 94, 0.65);",
          "}",
          "#spashiny-disconnect-notice .spashiny-disconnect-title {",
          "  font-weight: 700;",
          "  margin-bottom: 4px;",
          "}",
          "#spashiny-disconnect-notice .spashiny-disconnect-body {",
          "  font-size: 13px;",
          "  color: rgba(255, 255, 255, 0.86);",
          "}"
        ].join("\n");
        (document.head || document.documentElement).appendChild(style);
      }
    } catch (_) {}
  }
  function ensureDisconnectNotice() {
    installDisconnectNoticeUI();
    var node = document.getElementById("spashiny-disconnect-notice");
    if (node || !document.body) return node;
    node = document.createElement("div");
    node.id = "spashiny-disconnect-notice";
    node.setAttribute("role", "status");
    node.setAttribute("aria-live", "polite");
    node.innerHTML = [
      "<div class=\"spashiny-disconnect-title\"></div>",
      "<div class=\"spashiny-disconnect-body\"></div>"
    ].join("");
    document.body.appendChild(node);
    return node;
  }
  function showDisconnectNotice(title, body, recovered) {
    var node = ensureDisconnectNotice();
    if (!node) return;
    if (disconnectNoticeHideTimer) {
      window.clearTimeout(disconnectNoticeHideTimer);
      disconnectNoticeHideTimer = null;
    }
    var titleNode = node.querySelector(".spashiny-disconnect-title");
    var bodyNode = node.querySelector(".spashiny-disconnect-body");
    if (titleNode) titleNode.textContent = title || "";
    if (bodyNode) bodyNode.textContent = body || "";
    node.classList.toggle("spashiny-reconnected", !!recovered);
    node.classList.add("spashiny-visible");
    if (recovered) {
      disconnectNoticeHideTimer = window.setTimeout(function () {
        node.classList.remove("spashiny-visible");
      }, 3500);
    }
  }
  function hideDefaultShinyDisconnectOverlay() {
    try {
      var nodes = document.querySelectorAll("#shiny-disconnected-overlay,.shiny-disconnected-overlay");
      for (var i = 0; i < nodes.length; i += 1) {
        nodes[i].style.setProperty("display", "none", "important");
        nodes[i].style.setProperty("opacity", "0", "important");
        nodes[i].style.setProperty("visibility", "hidden", "important");
        nodes[i].style.setProperty("pointer-events", "none", "important");
      }
    } catch (_) {}
  }
  function markRealtimeDisconnected(reason) {
    realtimeDisconnected = true;
    hideDefaultShinyDisconnectOverlay();
    showDisconnectNotice(
      "Connection interrupted. Reconnecting...",
      "The page will stay visible. Jobs already submitted to background workers will keep running; please wait for the connection to recover before continuing.",
      false
    );
    postClientDiagnostic("SHINY_WEBSOCKET_DISCONNECTED", {
      error_name: "shiny_disconnected",
      error_message: String(reason || "unknown").slice(0, 120)
    });
  }
  function markRealtimeConnected() {
    hideDefaultShinyDisconnectOverlay();
    if (!realtimeDisconnected) return;
    realtimeDisconnected = false;
    showDisconnectNotice("Connection restored", "The Shiny page connection has been restored. You can continue.", true);
    postClientDiagnostic("SHINY_WEBSOCKET_RECONNECTED", null);
  }
  function isDisconnectOverlayNode(node) {
    if (!node || node.nodeType !== 1) return false;
    var id = node.id || "";
    var cls = node.className || "";
    if (typeof cls !== "string") cls = "";
    return id === "shiny-disconnected-overlay" || cls.indexOf("shiny-disconnected-overlay") >= 0;
  }
  function startDisconnectOverlayObserver() {
    installDisconnectNoticeUI();
    hideDefaultShinyDisconnectOverlay();
    try {
      if (window.MutationObserver && document.documentElement) {
        var observer = new MutationObserver(function (mutations) {
          var touchedOverlay = false;
          for (var i = 0; i < mutations.length; i += 1) {
            if (isDisconnectOverlayNode(mutations[i].target)) touchedOverlay = true;
            var added = mutations[i].addedNodes || [];
            for (var j = 0; j < added.length; j += 1) {
              if (isDisconnectOverlayNode(added[j])) touchedOverlay = true;
            }
          }
          hideDefaultShinyDisconnectOverlay();
          if (touchedOverlay) markRealtimeDisconnected("shiny_disconnected_overlay");
        });
        observer.observe(document.documentElement, {
          childList: true,
          subtree: true,
          attributes: true,
          attributeFilter: ["id", "class", "style"]
        });
      }
      window.setInterval(hideDefaultShinyDisconnectOverlay, 1500);
    } catch (_) {}
  }
  try {
    pageInstanceId = uuid();
    postClientDiagnostic("SCRIPT_LOADED", null);
  } catch (err) {
    pageInstanceId = "uuid-error";
    postClientDiagnostic("UUID_ERROR", {
      error_name: err && err.name ? String(err.name) : "Error",
      error_message: err && err.message ? String(err.message).slice(0, 120) : "",
    });
  }
  function browserClientId() {
    var value = storageGet("localStorage", BROWSER_CLIENT_KEY);
    if (!value) { value = uuid(); storageSet("localStorage", BROWSER_CLIENT_KEY, value); }
    return value;
  }
  function navigationType() {
    try {
      var entries = performance.getEntriesByType && performance.getEntriesByType("navigation");
      if (entries && entries[0] && entries[0].type) return String(entries[0].type);
      if (performance.navigation) return ["navigate", "reload", "back_forward", "prerender"][performance.navigation.type] || "unknown";
    } catch (_) {}
    return "unknown";
  }
  function workflowId() {
    var node = document.querySelector("[data-spashiny-workflow-id].active, [data-spashiny-workflow-id][aria-selected='true']");
    if (!node) node = document.body;
    return node && node.getAttribute ? (node.getAttribute("data-spashiny-workflow-id") || "") : "";
  }
  function setText(id, value) {
    var node = document.getElementById(id); if (node) node.textContent = value;
  }
  function sendShinyInput(name, value) {
    if (window.Shiny && typeof window.Shiny.setInputValue === "function") {
      window.Shiny.setInputValue(name, value, { priority: "event" });
    }
  }
  function setStatus(status) {
    storageSet("sessionStorage", STATUS_KEY, status || "UNKNOWN");
    setText("spashiny-session-status", status || "UNKNOWN");
    sendShinyInput("spashiny_session_status", status || "UNKNOWN");
  }
  function sessionLabel(sessionId) {
    return !sessionId ? "not ready" : (sessionId.length > 16 ? sessionId.slice(0, 16) + "..." : sessionId);
  }
  function replayShinyInputs() {
    var sessionId = storageGet("sessionStorage", SESSION_ID_KEY) || "";
    var token = storageGet("sessionStorage", TOKEN_KEY) || "";
    var analysisSessionId = storageGet("sessionStorage", ANALYSIS_SESSION_KEY) || "";
    if (sessionId) sendShinyInput("spashiny_session_id", sessionId);
    if (token) sendShinyInput("spashiny_session_token", token);
    if (analysisSessionId) sendShinyInput("spashiny_analysis_session_id", analysisSessionId);
    sendShinyInput("spashiny_browser_client_id", browserClientId());
    sendShinyInput("spashiny_page_instance_id", pageInstanceId);
    setStatus(storageGet("sessionStorage", STATUS_KEY) || "INITIALIZING");
  }
  function updateSessionInputs(sessionId, token, status, workspaceId) {
    if (token) storageSet("sessionStorage", TOKEN_KEY, token);
    if (sessionId) {
      storageSet("sessionStorage", SESSION_ID_KEY, sessionId);
      setText("spashiny-session-id", sessionLabel(workspaceId || sessionId));
    }
    replayShinyInputs();
    setStatus(status || storageGet("sessionStorage", STATUS_KEY) || "INITIALIZING");
  }
  function apiFetch(path, options) {
    options = options || {}; options.headers = options.headers || {};
    options.headers.Accept = "application/json";
    options.headers["X-SpaShiny-Browser-Client"] = browserClientId();
    var activeAnalysis = storageGet("sessionStorage", ANALYSIS_SESSION_KEY);
    if (activeAnalysis) options.headers["X-SpaShiny-Analysis-Session"] = activeAnalysis;
    options.credentials = options.credentials || "same-origin";
    if (typeof window.fetch === "function") return window.fetch(path, options);
    if (typeof window.XMLHttpRequest !== "function") return Promise.reject(new Error("No browser HTTP client is available"));
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      xhr.open(options.method || "GET", path, true);
      xhr.withCredentials = options.credentials !== "omit";
      Object.keys(options.headers).forEach(function (key) { xhr.setRequestHeader(key, options.headers[key]); });
      xhr.onload = function () {
        var body = xhr.responseText || "";
        resolve({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, json: function () {
          try { return Promise.resolve(JSON.parse(body)); } catch (err) { return Promise.reject(err); }
        }});
      };
      xhr.onerror = function () { reject(new Error("Session API request failed")); };
      xhr.send(options.body || null);
    });
  }
  function authedFetch(path, options) {
    options = options || {}; options.headers = options.headers || {};
    var token = storageGet("sessionStorage", TOKEN_KEY);
    // With no sessionStorage token (for example a newly reopened tab), omit
    // the header entirely so the lab HttpOnly cookie middleware can restore
    // the same owner session without exposing that token to JavaScript.
    if (token) options.headers["X-SpaShiny-Session"] = token;
    return apiFetch(path, options);
  }
  function lifecyclePayload(eventType, reason, event) {
    return {
      browser_client_id: browserClientId(),
      page_instance_id: pageInstanceId,
      analysis_session_id: storageGet("sessionStorage", ANALYSIS_SESSION_KEY) || "",
      workflow_id: workflowId(),
      event_type: eventType || "LIFECYCLE_EVENT",
      reason: reason || "",
      persisted: event && typeof event.persisted === "boolean" ? event.persisted : null,
      visibility_state: document.visibilityState || "unknown",
      navigation_type: navigationType(),
      client_timestamp: new Date().toISOString()
    };
  }
  function postLifecycleEvent(eventType, reason, event) {
    var token = storageGet("sessionStorage", TOKEN_KEY);
    if (!token) return Promise.resolve(null);
    return authedFetch("/api/session/lifecycle/event", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(lifecyclePayload(eventType, reason, event))
    }).catch(function () { return null; });
  }
  function connectBrowserPage(eventType, event) {
    var token = storageGet("sessionStorage", TOKEN_KEY);
    if (!token) return Promise.resolve(null);
    return authedFetch("/api/session/lifecycle/connect", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(lifecyclePayload(eventType || "BROWSER_CONNECTED", "reconnect", event))
    }).then(function (response) {
      if (!response.ok) throw new Error("browser lifecycle connect failed");
      return response.json();
    });
  }
  function clearSession() {
    storageRemove("sessionStorage", TOKEN_KEY); storageRemove("sessionStorage", SESSION_ID_KEY);
    storageRemove("sessionStorage", ANALYSIS_SESSION_KEY); storageRemove("sessionStorage", STATUS_KEY);
    sendShinyInput("spashiny_session_token", ""); sendShinyInput("spashiny_session_id", "");
    sendShinyInput("spashiny_analysis_session_id", ""); setText("spashiny-session-id", "not ready"); setStatus("NOT_READY");
  }
  function ensureAnalysisSession() {
    var current = storageGet("sessionStorage", ANALYSIS_SESSION_KEY);
    var endpoint = current ? "/api/analysis-sessions/" + encodeURIComponent(current) : "/api/analysis-sessions/current";
    return authedFetch(endpoint, { method: "GET" })
      .then(function (response) {
        if (response.ok) return response.json();
        if (response.status === 404 || response.status === 410 || response.status === 403) {
          storageRemove("sessionStorage", ANALYSIS_SESSION_KEY);
          return authedFetch("/api/analysis-sessions/start", { method: "POST" })
            .then(function (created) {
              if (!created.ok) throw new Error("analysis session start failed");
              return created.json();
            });
        }
        throw new Error("analysis session unavailable");
      })
      .then(function (data) {
        if (!data || !data.analysis_session_id) throw new Error("invalid analysis session response");
        storageSet("sessionStorage", ANALYSIS_SESSION_KEY, data.analysis_session_id); replayShinyInputs(); return data;
      });
  }
  function startSession(eventType, event) {
    setStatus("INITIALIZING");
    return apiFetch("/api/session/start", { method: "POST" })
      .then(function (response) { if (!response.ok) throw new Error("session start failed"); return response.json(); })
      .then(function (data) {
        storageSet("sessionStorage", TOKEN_KEY, data.session_token);
        heartbeatMs = Math.max(5000, Number(data.heartbeat_interval_seconds || 30) * 1000);
        idleTimeoutSeconds = Math.max(30, Number(data.idle_timeout_seconds || 300));
        lastHeartbeatAt = Date.now();
        updateSessionInputs(data.session_id, data.session_token, data.status || "ACTIVE", data.anonymous_workspace_id);
        return ensureAnalysisSession();
      })
      .then(function () { return connectBrowserPage(eventType || "SESSION_STARTED", event); })
      .then(function () { scheduleHeartbeat(); scheduleIdleCountdown(); });
  }
  function refreshStatusOrStart(eventType, event) {
    if (lifecycleInFlight) return;
    lifecycleInFlight = true;
    var token = storageGet("sessionStorage", TOKEN_KEY);
    // First try the HttpOnly lab cookie. It restores the same owner after a
    // tab close without persisting the opaque session token in localStorage.
    var request = authedFetch("/api/session/status", { method: "GET" })
      .then(function (response) {
        if (response.status === 401 || response.status === 410 || response.status === 404) {
          clearSession(); return startSession(eventType, event);
        }
        if (!response.ok) throw new Error("session status failed");
        return response.json().then(function (data) {
          lastHeartbeatAt = Date.now();
          updateSessionInputs(data.session_id, data.session_token || token, data.status || "ACTIVE", data.anonymous_workspace_id);
          return ensureAnalysisSession();
        });
      })
      .then(function () { return connectBrowserPage(eventType || "SESSION_REFRESH", event); })
      .then(function () { scheduleHeartbeat(); scheduleIdleCountdown(); });
    return Promise.resolve(request)
      .catch(function () { clearSession(); setStatus("API_UNAVAILABLE"); })
      .finally(function () { lifecycleInFlight = false; });
  }
  function heartbeat() {
    var token = storageGet("sessionStorage", TOKEN_KEY); if (!token) return;
    var context = lifecyclePayload("HEARTBEAT_SUCCESS", "heartbeat", null);
    authedFetch("/api/session/heartbeat", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(context)
    }).then(function (response) {
      if (response.status === 410 || response.status === 401 || response.status === 404) { clearSession(); return null; }
      if (!response.ok) throw new Error("heartbeat failed");
      return response.json();
    }).then(function (data) {
      if (!data) return;
      lastHeartbeatAt = Date.now();
      updateSessionInputs(data.session_id, token, data.status || "ACTIVE", data.anonymous_workspace_id);
    }).catch(function () {
      setStatus("HEARTBEAT_RETRYING");
      postLifecycleEvent("HEARTBEAT_FAILURE", "heartbeat_request_failed", null);
    });
  }
  function scheduleHeartbeat() {
    if (heartbeatTimer) window.clearInterval(heartbeatTimer);
    heartbeatTimer = window.setInterval(heartbeat, heartbeatMs);
  }
  function scheduleIdleCountdown() {
    if (idleTimer) window.clearInterval(idleTimer);
    idleTimer = window.setInterval(function () {
      if (!lastHeartbeatAt) return setText("spashiny-session-idle", "not ready");
      setText("spashiny-session-idle", String(Math.max(0, idleTimeoutSeconds - Math.floor((Date.now() - lastHeartbeatAt) / 1000))) + "s");
    }, 1000);
  }
  function disconnect(reason, event) {
    var token = storageGet("sessionStorage", TOKEN_KEY);
    if (!token || disconnectSent) return;
    disconnectSent = true;
    try {
      var payload = lifecyclePayload(reason === "beforeunload" ? "BEFOREUNLOAD" : "PAGEHIDE", reason, event);
      payload.session_token = token;
      var body = JSON.stringify(payload);
      if (navigator.sendBeacon && navigator.sendBeacon("/api/session/disconnect-beacon", new Blob([body], { type: "application/json" }))) return;
      fetch("/api/session/disconnect", {
        method: "POST",
        headers: { "X-SpaShiny-Session": token, "Content-Type": "application/json", Accept: "application/json" },
        body: body, keepalive: true
      });
    } catch (_) { return; }
  }
  function endSession() {
    var token = storageGet("sessionStorage", TOKEN_KEY);
    if (!token) { clearSession(); return; }
    authedFetch("/api/session/end", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: "user_end" })
    }).finally(function () { clearSession(); window.location.reload(); });
  }
  function newAnalysis() {
    authedFetch("/api/analysis-sessions/start", { method: "POST" })
      .then(function (response) { if (!response.ok) throw new Error("new analysis session failed"); return response.json(); })
      .then(function (data) {
        storageSet("sessionStorage", ANALYSIS_SESSION_KEY, data.analysis_session_id); replayShinyInputs(); window.location.reload();
      }).catch(function () { setStatus("ANALYSIS_SESSION_ERROR"); });
  }
  document.addEventListener("click", function (event) {
    var target = event.target; if (!target) return;
    if (target.id === "spashiny-session-end") { event.preventDefault(); endSession(); }
    if (target.id === "spashiny-new-analysis") { event.preventDefault(); newAnalysis(); }
  });
  function onShinyConnected() {
    markRealtimeConnected();
    disconnectSent = false;
    // A real websocket connection needs at most one lifecycle recovery.
    // Scheduling a second handler after the first request completes created
    // duplicate connect calls and avoidable reactive reinitialization.
    if (lifecycleInFlight) return;
    refreshStatusOrStart("SHINY_CONNECTED", null);
  }
  function onShinyDisconnected() {
    markRealtimeDisconnected("shiny:disconnected");
  }
  function onPageShow(event) {
    disconnectSent = false;
    refreshStatusOrStart("PAGESHOW", event);
  }
  // Shiny's jQuery event bridge and native events represent the same
  // connection. Register exactly one transport to prevent duplicate recovery.
  if (window.jQuery) {
    window.jQuery(document).on("shiny:connected", onShinyConnected);
    window.jQuery(document).on("shiny:disconnected", onShinyDisconnected);
  } else {
    document.addEventListener("shiny:connected", onShinyConnected);
    document.addEventListener("shiny:disconnected", onShinyDisconnected);
  }
  window.addEventListener("offline", function () { markRealtimeDisconnected("browser_offline"); });
  window.addEventListener("online", function () {
    showDisconnectNotice("Network restored; waiting for Shiny to reconnect", "The browser network is back. The page connection will reconnect automatically.", false);
  });
  window.addEventListener("pageshow", onPageShow);
  window.addEventListener("pagehide", function (event) { disconnect("pagehide", event); });
  window.addEventListener("beforeunload", function (event) { disconnect("beforeunload", event); });
  document.addEventListener("visibilitychange", function () { postLifecycleEvent("VISIBILITYCHANGE", "visibilitychange", null); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { startDisconnectOverlayObserver(); refreshStatusOrStart("DOM_READY", null); });
  else { startDisconnectOverlayObserver(); refreshStatusOrStart("DOM_READY", null); }
})();
