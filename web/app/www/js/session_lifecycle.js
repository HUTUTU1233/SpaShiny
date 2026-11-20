(function () {
  "use strict";

  var BROWSER_CLIENT_KEY = "spashiny.browser.client.id";
  var TAB_INSTANCE_KEY = "spashiny.tab.instance.id";
  var TOKEN_KEY = "spashiny.session.token";
  var SESSION_ID_KEY = "spashiny.session.id";
  var ANALYSIS_SESSION_KEY = "spashiny.analysis.session.id";
  var STATUS_KEY = "spashiny.session.status";
  var heartbeatMs = 30000;
  var idleTimeoutSeconds = 43200;
  var lastHeartbeatAt = 0;
  var lastUserActivityAt = Date.now();
  var idleDeadlineAt = 0;
  var idleWorkActive = false;
  var idleEnded = false;
  var activeUploads = new Set();
  var boundActivityDocuments = new WeakSet();
  var shinyBusySince = 0;
  var heartbeatTimer = null;
  var idleTimer = null;
  var disconnectSent = false;
  var lifecycleInFlight = false;
  var lifecycleLastStartedAt = 0;
  var shinyConnectedDuringLifecycle = false;
  // Shiny emits `shiny:connected` before it sends its protocol `init` frame.
  // Lifecycle inputs must therefore wait for `shiny:sessioninitialized`, when
  // the server has accepted init and transitioned to the Running state.
  var shinySessionInitialized = false;
  var shinyConnectionGeneration = 0;
  var shinyLastReplayGeneration = -1;
  var shinyLastReplaySignature = "";
  var fallbackStore = {};
  var pageInstanceId = "pending";
  var realtimeDisconnected = false;
  var disconnectProbeGeneration = 0;
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
  function showDisconnectNotice(title, body, recovered, hideAfterMs) {
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
    if (recovered || hideAfterMs) {
      disconnectNoticeHideTimer = window.setTimeout(function () {
        node.classList.remove("spashiny-visible");
      }, hideAfterMs || 3500);
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
    if (idleEnded) return showIdleEndedNotice();
    var wasDisconnected = realtimeDisconnected;
    realtimeDisconnected = true;
    hideDefaultShinyDisconnectOverlay();
    var browserOffline = reason === "browser_offline" || navigator.onLine === false;
    showDisconnectNotice(
      browserOffline ? "Browser network is offline" : "Shiny connection interrupted; cause not yet confirmed",
      browserOffline
        ? "Check your network. This tab will try to reconnect when it returns. A long interruption can end this analysis and cancel its active jobs."
        : "The browser has lost its live page connection. This alone does not distinguish a network interruption, a suspended tab, or a server disconnect. Brief interruptions may recover. Running and queued work is protected from inactivity expiry; an explicit tab close still uses the close-grace policy.",
      false
    );
    // A successful HTTP readiness probe distinguishes a WebSocket-only break
    // from a wholly unreachable Web service. It cannot identify the physical
    // network fault or prove that an idle timeout happened.
    if (!browserOffline && !wasDisconnected && typeof window.fetch === "function") {
      var probeGeneration = ++disconnectProbeGeneration;
      window.fetch("/healthz", { method: "GET", cache: "no-store", credentials: "same-origin" })
        .then(function (response) {
          if (!realtimeDisconnected || probeGeneration !== disconnectProbeGeneration) return;
          if (response.ok) {
            var close = window.__spashinyLastSocketClose || {};
            var keepaliveTimeout = Number(close.code) === 1011 && /keepalive ping timeout/i.test(String(close.reason || ""));
            showDisconnectNotice(
              keepaliveTimeout ? "Shiny keepalive timed out (WebSocket 1011)" : "Shiny connection interrupted; Web server is reachable",
              keepaliveTimeout
                ? "The WebSocket closed with code 1011: keepalive ping timeout. Its keepalive response did not arrive in time; this is not the 30-minute no-work inactivity policy. Long blocking server work, browser suspension or a network interruption can cause this. Saved worker results are not deleted; the server has not identified a more specific cause for this connection."
                : "The Web health endpoint responds, but this page's live WebSocket is disconnected. The precise trigger is not available yet. Keep this tab open while it reconnects. The separate inactivity policy ends an analysis only after 12 hours without work or user activity.",
              false
            );
          } else {
            showDisconnectNotice(
              "Web service returned an error",
              "The browser is online, but the Web health endpoint returned HTTP " + response.status + ". This may be a server or network-path problem; retry is in progress.",
              false
            );
          }
        }).catch(function () {
          if (!realtimeDisconnected || probeGeneration !== disconnectProbeGeneration) return;
          showDisconnectNotice(
            "Web service cannot be reached",
            "The browser reports that it is online, but a same-origin health check failed. The server or network path may be unavailable; the exact cause is not yet confirmed.",
            false
          );
        });
    }
    postClientDiagnostic("SHINY_WEBSOCKET_DISCONNECTED", {
      error_name: "shiny_disconnected",
      error_message: String(reason || "unknown").slice(0, 120)
    });
  }
  function markRealtimeConnected() {
    hideDefaultShinyDisconnectOverlay();
    if (!realtimeDisconnected) return;
    realtimeDisconnected = false;
    disconnectProbeGeneration += 1;
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
          var overlayAdded = false;
          for (var i = 0; i < mutations.length; i += 1) {
            var added = mutations[i].addedNodes || [];
            for (var j = 0; j < added.length; j += 1) {
              if (isDisconnectOverlayNode(added[j])) {
                overlayAdded = true;
              } else if (added[j] && added[j].querySelector && added[j].querySelector("#shiny-disconnected-overlay, .shiny-disconnected-overlay")) {
                overlayAdded = true;
              }
            }
          }
          // DOM updates from Shiny outputs are not a transport failure.  In
          // particular, hiding the overlay mutates style and used to trigger
          // this observer again, producing false reconnect cycles.
          if (overlayAdded) hideDefaultShinyDisconnectOverlay();
        });
        observer.observe(document.documentElement, {
          childList: true,
          subtree: true
        });
      }
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
  function tabInstanceId() {
    var value = storageGet("sessionStorage", TAB_INSTANCE_KEY);
    if (!value) { value = uuid(); storageSet("sessionStorage", TAB_INSTANCE_KEY, value); }
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
    if (shinySessionInitialized && window.Shiny && typeof window.Shiny.setInputValue === "function") {
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
    var status = storageGet("sessionStorage", STATUS_KEY) || "INITIALIZING";
    var signature = [sessionId, token, analysisSessionId, browserClientId(), tabInstanceId(), pageInstanceId, status].join("\u001f");
    // Calls from lifecycle HTTP completion are allowed to happen before the
    // Shiny protocol is initialized, but must not emit an update frame then.
    if (!shinySessionInitialized) return false;
    // A single Shiny connection can receive both a sessioninitialized event
    // and late lifecycle HTTP completion. Send identical scope inputs once.
    if (shinyLastReplayGeneration === shinyConnectionGeneration && shinyLastReplaySignature === signature) return false;
    shinyLastReplayGeneration = shinyConnectionGeneration;
    shinyLastReplaySignature = signature;
    if (sessionId) sendShinyInput("spashiny_session_id", sessionId);
    if (token) sendShinyInput("spashiny_session_token", token);
    if (analysisSessionId) sendShinyInput("spashiny_analysis_session_id", analysisSessionId);
    sendShinyInput("spashiny_browser_client_id", browserClientId());
    sendShinyInput("spashiny_tab_instance_id", tabInstanceId());
    sendShinyInput("spashiny_page_instance_id", pageInstanceId);
    setStatus(status);
    return true;
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
      tab_instance_id: tabInstanceId(),
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
    // Analysis identity is tab-scoped. Never ask the server to discover a
    // current or latest analysis from profile-wide cookies or telemetry.
    var current = storageGet("sessionStorage", ANALYSIS_SESSION_KEY);
    var request = current
      ? authedFetch("/api/analysis-sessions/" + encodeURIComponent(current), { method: "GET" })
      : authedFetch("/api/analysis-sessions/start", { method: "POST" });
    return request.then(function (response) {
      if (response.ok) return response.json();
      if (current && response.status === 409) {
        return response.json().catch(function () { return {}; }).then(function (payload) {
          var detail = payload && payload.detail || {};
          if (detail.code !== "ANALYSIS_SESSION_ENDED") throw new Error("analysis session unavailable");
          var reason = String(detail.reason || "");
          storageRemove("sessionStorage", ANALYSIS_SESSION_KEY);
          return authedFetch("/api/analysis-sessions/start", { method: "POST" }).then(function (created) {
            if (!created.ok) throw new Error("analysis session start failed");
            return created.json();
          }).then(function (data) {
            var explanation = "The server confirmed that this tab's previous analysis ended. A new analysis was created; earlier active jobs are not resumed automatically.";
            if (reason === "heartbeat_lease_expired") {
              explanation = "The server stopped receiving this tab's heartbeat long enough for the lease to expire, then ended the analysis and requested cancellation of its active jobs. The server cannot tell whether the missed heartbeats came from network loss, browser suspension, or a closed tab.";
            } else if (reason === "grace_expired") {
              explanation = "The tab did not reconnect within the close grace period. The server ended its previous analysis and requested cancellation of active jobs.";
            }
            showDisconnectNotice("Previous analysis ended; new analysis started", explanation, false, 15000);
            return data;
          });
        });
      }
      if (current && (response.status === 404 || response.status === 410 || response.status === 403)) {
        storageRemove("sessionStorage", ANALYSIS_SESSION_KEY);
        return authedFetch("/api/analysis-sessions/start", { method: "POST" }).then(function (created) {
          if (!created.ok) throw new Error("analysis session start failed");
          return created.json();
        });
      }
      throw new Error("analysis session unavailable");
    }).then(function (data) {
      if (!data || !data.analysis_session_id) throw new Error("invalid analysis session response");
      storageSet("sessionStorage", ANALYSIS_SESSION_KEY, data.analysis_session_id);
      replayShinyInputs();
      return data;
    });
  }
  function startSession(eventType, event) {
    setStatus("INITIALIZING");
    return apiFetch("/api/session/start", { method: "POST" })
      .then(function (response) { if (!response.ok) throw new Error("session start failed"); return response.json(); })
      .then(function (data) {
        storageSet("sessionStorage", TOKEN_KEY, data.session_token);
        heartbeatMs = Math.max(5000, Number(data.heartbeat_interval_seconds || 30) * 1000);
        idleTimeoutSeconds = Math.max(30, Number(data.idle_timeout_seconds || 43200));
        lastHeartbeatAt = Date.now();
        updateSessionInputs(data.session_id, data.session_token, data.status || "ACTIVE", data.anonymous_workspace_id);
        return ensureAnalysisSession();
      })
      .then(function () { return connectBrowserPage(eventType || "SESSION_STARTED", event); })
      .then(function () {
        // The session API commonly finishes before Shiny exposes setInputValue.
        // If the websocket connected while that request was in flight, the
        // earlier replay was a harmless no-op. Replay once more here, after
        // lifecycle recovery, so the new Shiny server session receives the
        // owner and analysis scope without creating a second lifecycle call.
        if (shinyConnectedDuringLifecycle) replayShinyInputs();
        scheduleHeartbeat(); scheduleIdleCountdown();
      });
  }
  function refreshStatusOrStart(eventType, event) {
    var now = Date.now();
    if (lifecycleInFlight || now - lifecycleLastStartedAt < 2000) return;
    lifecycleLastStartedAt = now;
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
          heartbeatMs = Math.max(5000, Number(data.heartbeat_interval_seconds || 30) * 1000);
          idleTimeoutSeconds = Math.max(30, Number(data.idle_timeout_seconds || 43200));
          lastHeartbeatAt = Date.now();
          updateSessionInputs(data.session_id, data.session_token || token, data.status || "ACTIVE", data.anonymous_workspace_id);
          return ensureAnalysisSession();
        });
      })
      .then(function () { return connectBrowserPage(eventType || "SESSION_REFRESH", event); })
      .then(function () {
        // See startSession(): this closes the API-before-Shiny input replay
        // race without multiplying browser lifecycle connect requests.
        if (shinyConnectedDuringLifecycle) replayShinyInputs();
        scheduleHeartbeat(); scheduleIdleCountdown();
      });
    return Promise.resolve(request)
      .catch(function () {
        // A transport error or temporary API 5xx does not revoke ownership.
        // Clearing tab credentials here stranded already completed results
        // after a tunnel outage. Only confirmed auth/expiry responses above
        // may clear them; retry heartbeats against the same exact scope.
        setStatus("API_UNAVAILABLE");
        scheduleHeartbeat(); scheduleIdleCountdown();
      })
      .finally(function () { lifecycleInFlight = false; });
  }
  function heartbeat() {
    if (idleEnded) return;
    var token = storageGet("sessionStorage", TOKEN_KEY); if (!token) return;
    var context = lifecyclePayload("HEARTBEAT_SUCCESS", "heartbeat", null);
    context.idle_seconds = Math.min(604800, Math.max(0, Math.floor((Date.now() - lastUserActivityAt) / 1000)));
    // Transient reactive polling must not continually reset inactivity.
    context.client_busy = activeUploads.size > 0 || (shinyBusySince > 0 && Date.now() - shinyBusySince > 1000);
    authedFetch("/api/session/heartbeat", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(context)
    }).then(function (response) {
      if (response.status === 410 || response.status === 401 || response.status === 404) { clearSession(); return null; }
      if (!response.ok) throw new Error("heartbeat failed");
      return response.json();
    }).then(function (data) {
      if (!data) return;
      lastHeartbeatAt = Date.now();
      if (data.idle_policy && data.idle_policy.analysis_session_id === storageGet("sessionStorage", ANALYSIS_SESSION_KEY)) {
        var policy = data.idle_policy;
        idleWorkActive = !!policy.active_work;
        idleDeadlineAt = Date.now() + Number(policy.remaining_seconds || 0) * 1000;
        if (policy.expired) {
          idleEnded = true;
          window.clearInterval(heartbeatTimer);
          setStatus("ANALYSIS_IDLE_ENDED");
          showIdleEndedNotice();
          sendShinyInput("spashiny_idle_timeout", { analysis_session_id: policy.analysis_session_id, reason: policy.reason, timestamp: Date.now() });
          return;
        }
      }
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
      if (idleEnded) return setText("spashiny-session-idle", "ended: 12 h idle");
      if (idleWorkActive || activeUploads.size > 0) return setText("spashiny-session-idle", "working: idle timer paused");
      var deadline = Math.max(idleDeadlineAt, lastUserActivityAt + idleTimeoutSeconds * 1000);
      setText("spashiny-session-idle", String(Math.max(0, Math.ceil((deadline - Date.now()) / 1000))) + "s without work/activity");
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
        headers: { "X-SpaShiny-Session": token, "X-SpaShiny-Analysis-Session": storageGet("sessionStorage", ANALYSIS_SESSION_KEY) || "", "Content-Type": "application/json", Accept: "application/json" },
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
  function cleanupTerminalTaskModalLock() {
    // The server invokes this only after its modal-owner check. Do not touch
    // an active dialog; remove only Bootstrap/Shiny lock values.
    try {
      if (document.querySelector(".modal.show,[aria-modal='true']")) return false;
      var backdrops = document.querySelectorAll(".modal-backdrop");
      for (var i = 0; i < backdrops.length; i += 1) backdrops[i].remove();
      var body = document.body;
      var html = document.documentElement;
      if (body) {
        body.classList.remove("modal-open");
        if (/^(hidden|clip)$/i.test(body.style.overflow || "")) body.style.removeProperty("overflow");
        if (/^fixed$/i.test(body.style.position || "")) body.style.removeProperty("position");
        if (/^(100vh|100%)$/i.test(body.style.height || "")) body.style.removeProperty("height");
        if (body.style.paddingRight) body.style.removeProperty("padding-right");
        if (body.style.touchAction === "none") body.style.removeProperty("touch-action");
      }
      if (html) {
        if (/^(hidden|clip)$/i.test(html.style.overflow || "")) html.style.removeProperty("overflow");
        if (/^fixed$/i.test(html.style.position || "")) html.style.removeProperty("position");
        if (/^(100vh|100%)$/i.test(html.style.height || "")) html.style.removeProperty("height");
        if (html.style.touchAction === "none") html.style.removeProperty("touch-action");
      }
      return true;
    } catch (_) { return false; }
  }
  function cleanupTaskModalAfterTransition(message) {
    // Shiny validates handler.length === 1, even when the payload is not used.
    if (window.console) window.console.info("SPASHINY_TASK_MODAL_CLEANUP_RECEIVED");
    // The remove-modal message can arrive while Bootstrap is still fading.
    // Bootstrap can restore a stale scroll-lock snapshot after an earlier
    // successful cleanup. Recheck through the settling window, even after
    // success, and never unlock a different dialog that opens meanwhile.
    var attempts = 0;
    function afterTransition() {
      cleanupTerminalTaskModalLock();
      if (++attempts >= 20) return;
      window.setTimeout(afterTransition, 100);
    }
    window.setTimeout(afterTransition, 0);
  }
  function installTaskModalCleanupHandler() {
    try {
      if (!window.Shiny || typeof window.Shiny.addCustomMessageHandler !== "function" || window.__spashinyTaskModalCleanupInstalled) return;
      window.Shiny.addCustomMessageHandler("spashiny_cleanup_task_modal", cleanupTaskModalAfterTransition);
      window.__spashinyTaskModalCleanupInstalled = true;
    } catch (error) {
      if (window.console) window.console.error("SPASHINY_TASK_MODAL_CLEANUP_REGISTRATION_FAILED", String(error));
    }
  }
  function onShinyConnected() {
    if (idleEnded) return showIdleEndedNotice();
    window.__spashinyLastSocketClose = null;
    markRealtimeConnected();
    installTaskModalCleanupHandler();
    disconnectSent = false;
    shinyConnectedDuringLifecycle = true;
    shinySessionInitialized = false;
    shinyConnectionGeneration += 1;
    shinyLastReplayGeneration = -1;
    shinyLastReplaySignature = "";
    // A real websocket connection needs at most one lifecycle recovery.
    // Scheduling a second handler after the first request completes created
    // duplicate connect calls and avoidable reactive reinitialization.
    if (lifecycleInFlight) return;
    refreshStatusOrStart("SHINY_CONNECTED", null);
  }
  function onShinySessionInitialized() {
    // This event is emitted only after Shiny receives its `config` response,
    // which follows the client's `init` protocol frame. Replaying lifecycle
    // inputs here prevents an `update` frame from preceding `init`.
    shinySessionInitialized = true;
    replayShinyInputs();
  }
  function onShinyDisconnected() {
    shinySessionInitialized = false;
    shinyBusySince = 0;
    markRealtimeDisconnected("shiny:disconnected");
  }
  function onPageShow(event) {
    if (idleEnded) return showIdleEndedNotice();
    disconnectSent = false;
    refreshStatusOrStart("PAGESHOW", event);
  }
  // Shiny's jQuery event bridge and native events represent the same
  // connection. Register exactly one transport to prevent duplicate recovery.
  if (window.jQuery) {
    window.jQuery(document).on("shiny:connected", onShinyConnected);
    window.jQuery(document).on("shiny:disconnected", onShinyDisconnected);
    window.jQuery(document).on("shiny:sessioninitialized", onShinySessionInitialized);
    window.jQuery(document).on("shiny:busy", function () { if (!shinyBusySince) shinyBusySince = Date.now(); });
    window.jQuery(document).on("shiny:idle", function () { shinyBusySince = 0; });
  } else {
    document.addEventListener("shiny:connected", onShinyConnected);
    document.addEventListener("shiny:disconnected", onShinyDisconnected);
    document.addEventListener("shiny:sessioninitialized", onShinySessionInitialized);
    document.addEventListener("shiny:busy", function () { if (!shinyBusySince) shinyBusySince = Date.now(); });
    document.addEventListener("shiny:idle", function () { shinyBusySince = 0; });
  }
  window.addEventListener("offline", function () { markRealtimeDisconnected("browser_offline"); });
  window.addEventListener("online", function () {
    if (idleEnded) return showIdleEndedNotice();
    showDisconnectNotice("Network restored; waiting for Shiny to reconnect", "The browser network is back. The page connection will reconnect automatically.", false);
  });
  window.addEventListener("pageshow", onPageShow);
  window.addEventListener("pagehide", function (event) { disconnect("pagehide", event); });
  window.addEventListener("beforeunload", function (event) { disconnect("beforeunload", event); });
  document.addEventListener("visibilitychange", function () { postLifecycleEvent("VISIBILITYCHANGE", "visibilitychange", null); });
  function showIdleEndedNotice() {
    showDisconnectNotice("Analysis ended after 12 hours without work or activity", "No running/queued job, upload or user activity was detected for 12 hours. This is an inactivity timeout, not a diagnosed network fault. Saved result files are not deleted. Choose New Analysis to start a new analysis; the ended analysis will not be revived.", false);
  }
  function bindActivityDocument(doc) {
    if (!doc || boundActivityDocuments.has(doc)) return;
    boundActivityDocuments.add(doc);
    ["pointerdown", "keydown", "input", "change", "wheel", "touchstart"].forEach(function (name) {
      doc.addEventListener(name, function (event) {
        if (event.isTrusted) lastUserActivityAt = Date.now();
      }, { capture: true, passive: true });
    });
    function bindFrame(frame) {
      if (frame.dataset.spashinyActivityBound) return;
      frame.dataset.spashinyActivityBound = "1";
      var bind = function () { try { bindActivityDocument(frame.contentDocument); } catch (_) { /* Cross-origin frames cannot be inspected. */ } };
      frame.addEventListener("load", bind); bind();
    }
    Array.prototype.forEach.call(doc.querySelectorAll("iframe"), bindFrame);
    new MutationObserver(function (records) {
      records.forEach(function (record) { Array.prototype.forEach.call(record.addedNodes, function (node) {
        if (node.nodeType !== 1) return;
        if (node.tagName === "IFRAME") bindFrame(node);
        Array.prototype.forEach.call(node.querySelectorAll("iframe"), bindFrame);
      }); });
    }).observe(doc.documentElement, { childList: true, subtree: true });
  }
  window.addEventListener("spashiny-upload-progress", function (event) {
    var data = event.detail || {}; if (!data.upload_id) return;
    if (["UPLOADING", "COMPLETING"].indexOf(String(data.status || "").toUpperCase()) >= 0) activeUploads.add(data.upload_id);
    else { activeUploads.delete(data.upload_id); lastUserActivityAt = Date.now(); }
  });
  window.addEventListener("spashiny-upload-error", function (event) { activeUploads.delete((event.detail || {}).upload_id); lastUserActivityAt = Date.now(); });
  function initializePage() { bindActivityDocument(document); startDisconnectOverlayObserver(); refreshStatusOrStart("DOM_READY", null); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initializePage);
  else initializePage();
})();
