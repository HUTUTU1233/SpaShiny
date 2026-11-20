(function () {
  "use strict";

  var TOKEN_KEY = "spashiny.session.token";
  var SESSION_ID_KEY = "spashiny.session.id";
  var STATUS_KEY = "spashiny.session.status";
  var heartbeatMs = 30000;
  var idleTimeoutSeconds = 300;
  var lastHeartbeatAt = 0;
  var heartbeatTimer = null;
  var idleTimer = null;
  var disconnectSent = false;

  function setText(id, value) {
    var node = document.getElementById(id);
    if (node) {
      node.textContent = value;
    }
  }

  function setStatus(status) {
    sessionStorage.setItem(STATUS_KEY, status || "UNKNOWN");
    setText("spashiny-session-status", status || "UNKNOWN");
    sendShinyInput("spashiny_session_status", status || "UNKNOWN");
  }

  function sendShinyInput(name, value) {
    if (window.Shiny && typeof window.Shiny.setInputValue === "function") {
      window.Shiny.setInputValue(name, value, { priority: "event" });
    }
  }

  function sessionLabel(sessionId) {
    if (!sessionId) {
      return "not ready";
    }
    return sessionId.length > 16 ? sessionId.slice(0, 16) + "..." : sessionId;
  }

  function updateSessionInputs(sessionId, token, status, workspaceId) {
    if (sessionId) {
      sessionStorage.setItem(SESSION_ID_KEY, sessionId);
      setText("spashiny-session-id", sessionLabel(workspaceId || sessionId));
      sendShinyInput("spashiny_session_id", sessionId);
    }
    if (token) {
      sendShinyInput("spashiny_session_token", token);
    }
    setStatus(status || sessionStorage.getItem(STATUS_KEY) || "INITIALIZING");
  }

  function apiFetch(path, options) {
    options = options || {};
    options.headers = options.headers || {};
    options.headers["Accept"] = "application/json";
    options.credentials = options.credentials || "same-origin";
    return fetch(path, options);
  }

  function authedFetch(path, options) {
    var token = sessionStorage.getItem(TOKEN_KEY);
    options = options || {};
    options.headers = options.headers || {};
    options.headers["X-SpaShiny-Session"] = token || "";
    return apiFetch(path, options);
  }

  function clearSession() {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(SESSION_ID_KEY);
    sessionStorage.removeItem(STATUS_KEY);
    sendShinyInput("spashiny_session_token", "");
    sendShinyInput("spashiny_session_id", "");
    setText("spashiny-session-id", "not ready");
    setStatus("NOT_READY");
  }

  function startSession() {
    setStatus("INITIALIZING");
    return apiFetch("/api/session/start", { method: "POST" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("session start failed");
        }
        return response.json();
      })
      .then(function (data) {
        sessionStorage.setItem(TOKEN_KEY, data.session_token);
        heartbeatMs = Math.max(5000, Number(data.heartbeat_interval_seconds || 30) * 1000);
        idleTimeoutSeconds = Math.max(30, Number(data.idle_timeout_seconds || 300));
        lastHeartbeatAt = Date.now();
        updateSessionInputs(data.session_id, data.session_token, data.status || "ACTIVE", data.anonymous_workspace_id);
        scheduleHeartbeat();
        scheduleIdleCountdown();
      })
      .catch(function () {
        clearSession();
        setStatus("API_UNAVAILABLE");
      });
  }

  function refreshStatusOrStart() {
    var token = sessionStorage.getItem(TOKEN_KEY);
    if (!token) {
      return startSession();
    }
    return authedFetch("/api/session/status", { method: "GET" })
      .then(function (response) {
        if (response.status === 401 || response.status === 410 || response.status === 404) {
          clearSession();
          return startSession();
        }
        if (!response.ok) {
          throw new Error("session status failed");
        }
        return response.json();
      })
      .then(function (data) {
        if (!data) {
          return;
        }
        lastHeartbeatAt = Date.now();
        updateSessionInputs(data.session_id, token, data.status || "ACTIVE", data.anonymous_workspace_id);
        scheduleHeartbeat();
        scheduleIdleCountdown();
      })
      .catch(function () {
        clearSession();
        setStatus("API_UNAVAILABLE");
      });
  }

  function heartbeat() {
    var token = sessionStorage.getItem(TOKEN_KEY);
    if (!token) {
      return;
    }
    authedFetch("/api/session/heartbeat", { method: "POST" })
      .then(function (response) {
        if (response.status === 410 || response.status === 401 || response.status === 404) {
          clearSession();
          return null;
        }
        if (!response.ok) {
          throw new Error("heartbeat failed");
        }
        return response.json();
      })
      .then(function (data) {
        if (!data) {
          return;
        }
        lastHeartbeatAt = Date.now();
        updateSessionInputs(data.session_id, token, data.status || "ACTIVE", data.anonymous_workspace_id);
      })
      .catch(function () {
        setStatus("HEARTBEAT_RETRYING");
      });
  }

  function scheduleHeartbeat() {
    if (heartbeatTimer) {
      window.clearInterval(heartbeatTimer);
    }
    heartbeatTimer = window.setInterval(heartbeat, heartbeatMs);
  }

  function scheduleIdleCountdown() {
    if (idleTimer) {
      window.clearInterval(idleTimer);
    }
    idleTimer = window.setInterval(function () {
      if (!lastHeartbeatAt) {
        setText("spashiny-session-idle", "not ready");
        return;
      }
      var elapsed = Math.floor((Date.now() - lastHeartbeatAt) / 1000);
      var remaining = Math.max(0, idleTimeoutSeconds - elapsed);
      setText("spashiny-session-idle", String(remaining) + "s");
    }, 1000);
  }

  function disconnect() {
    var token = sessionStorage.getItem(TOKEN_KEY);
    if (!token || disconnectSent) {
      return;
    }
    disconnectSent = true;
    try {
      if (navigator.sendBeacon) {
        var payload = JSON.stringify({ session_token: token });
        var blob = new Blob([payload], { type: "application/json" });
        if (navigator.sendBeacon("/api/session/disconnect-beacon", blob)) {
          return;
        }
      }
      fetch("/api/session/disconnect", {
        method: "POST",
        headers: {
          "X-SpaShiny-Session": token,
          "Accept": "application/json"
        },
        keepalive: true
      });
    } catch (_) {
      return;
    }
  }

  function endSession() {
    var token = sessionStorage.getItem(TOKEN_KEY);
    if (!token) {
      clearSession();
      return;
    }
    authedFetch("/api/session/end", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "user_end" })
    }).finally(function () {
      clearSession();
      window.location.reload();
    });
  }

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (target && target.id === "spashiny-session-end") {
      event.preventDefault();
      endSession();
    }
  });

  window.addEventListener("pagehide", disconnect);
  window.addEventListener("beforeunload", disconnect);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", refreshStatusOrStart);
  } else {
    refreshStatusOrStart();
  }
})();
