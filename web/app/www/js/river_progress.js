(function () {
  "use strict";

  var overlay = null;
  var titleNode = null;
  var detailNode = null;
  var buttonNode = null;
  var dismissed = false;
  var registered = false;

  function ensureOverlay() {
    if (overlay && overlay.isConnected) return;
    overlay = document.createElement("div");
    overlay.id = "river-st-progress-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-labelledby", "river-st-progress-title");
    overlay.style.cssText = "display:none;position:fixed;inset:0;z-index:2000;background:rgba(17,24,39,.55);align-items:center;justify-content:center;padding:20px;";

    var card = document.createElement("div");
    card.style.cssText = "width:min(460px,100%);background:#fff;border-radius:14px;box-shadow:0 24px 64px rgba(0,0,0,.25);padding:24px;color:#111827;";
    titleNode = document.createElement("h3");
    titleNode.id = "river-st-progress-title";
    titleNode.style.cssText = "margin:0 0 12px;font-size:20px;";
    detailNode = document.createElement("p");
    detailNode.setAttribute("aria-live", "polite");
    detailNode.style.cssText = "margin:0 0 18px;white-space:pre-wrap;line-height:1.5;";
    buttonNode = document.createElement("button");
    buttonNode.type = "button";
    buttonNode.className = "btn btn-outline-secondary";
    buttonNode.textContent = "Continue in background";
    buttonNode.addEventListener("click", function () {
      dismissed = true;
      overlay.style.display = "none";
    });
    card.appendChild(titleNode);
    card.appendChild(detailNode);
    card.appendChild(buttonNode);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
  }

  function show(title, detail) {
    dismissed = false;
    ensureOverlay();
    titleNode.textContent = String(title || "River is working");
    detailNode.textContent = String(detail || "Please wait.");
    buttonNode.textContent = "Continue in background";
    overlay.style.display = "flex";
  }

  function showError(title, detail) {
    show(title, detail);
    buttonNode.textContent = "Close";
  }

  function update(title, detail) {
    ensureOverlay();
    titleNode.textContent = String(title || "River is working");
    detailNode.textContent = String(detail || "Please wait.");
    if (!dismissed) overlay.style.display = "flex";
  }

  function hide() {
    if (overlay) overlay.style.display = "none";
    dismissed = false;
  }

  window.SpaShinyRiverProgress = { show: show, update: update, hide: hide };

  document.addEventListener("click", function (event) {
    var button = event.target.closest("#river_st_load_example, #river_st_preview, #river_st_submit");
    if (!button || button.disabled) return;
    if (button.id === "river_st_load_example") {
      show("Loading River example", "Binding the published package to this analysis session.");
    } else if (button.id === "river_st_preview") {
      show("Inspecting River package", "Reading the H5AD metadata and shared genes. Large archives may take a moment.");
    } else {
      show("Submitting River analysis", "Validating the sample order and preparing a GPU job.");
    }
  });

  document.addEventListener("click", function (event) {
    // All River artifacts need the requesting tab's exact analysis headers.
    // Cookies alone are shared by tabs and can point at another analysis.
    // Retain the old PDF selector for historical/replot controls.
    var link = event.target.closest("a[data-spashiny-river-artifact-download='1'], a[data-spashiny-river-pdf-download='1']");
    if (!link) return;
    event.preventDefault();
    var token = sessionStorage.getItem("spashiny.session.token") || "";
    var analysis = sessionStorage.getItem("spashiny.analysis.session.id") || "";
    if (!token || !analysis) {
      showError("River download unavailable", "The current tab analysis session is not ready. Please reconnect and try again.");
      return;
    }
    var filename = link.getAttribute("download") || "river-result";
    show("Preparing River download", filename);
    fetch(link.href, {
      credentials: "same-origin",
      headers: {
        "X-SpaShiny-Session": token,
        "X-SpaShiny-Analysis-Session": analysis
      }
    }).then(async function (response) {
      if (!response.ok) {
        var code = "HTTP_" + response.status;
        try {
          var payload = await response.json();
          code = String((payload.detail && payload.detail.code) || code);
        } catch (_) {}
        throw new Error(code);
      }
      return response.blob();
    }).then(function (blob) {
      if (!blob.size) throw new Error("EMPTY_ARTIFACT");
      var objectUrl = URL.createObjectURL(blob);
      var download = document.createElement("a");
      download.href = objectUrl;
      download.download = filename;
      document.body.appendChild(download);
      download.click();
      download.remove();
      setTimeout(function () { URL.revokeObjectURL(objectUrl); }, 60000);
      hide();
    }).catch(function (error) {
      showError("River download failed", String((error && error.message) || "Unknown download error"));
    });
  });

  // River figures are already generated by the worker. An <img> request cannot
  // send the tab-scoped analysis header, so preview them through an authorized
  // fetch and a page-local Blob URL. Cache the Blob across Shiny's status polls.
  var figureCache = new Map();
  var figureScanTimer = null;

  function showFigure(slot, objectUrl, key) {
    if (
      !slot.isConnected ||
      key !== (sessionStorage.getItem("spashiny.analysis.session.id") || "") + ":" +
        (slot.getAttribute("data-spashiny-river-preview-key") || "")
    ) return;
    var existing = slot.querySelector("img[data-spashiny-river-figure-key]");
    if (existing && existing.getAttribute("data-spashiny-river-figure-key") === key) return;
    var image = document.createElement("img");
    image.src = objectUrl;
    image.alt = slot.getAttribute("data-spashiny-river-preview-alt") || "River result figure";
    image.loading = "lazy";
    image.setAttribute("data-spashiny-river-figure-key", key);
    image.style.cssText = "display:block;width:100%;height:auto;max-height:600px;object-fit:contain;background:#fff;";
    image.addEventListener("error", function () {
      slot.textContent = "Figure preview could not be decoded. The PDF download remains available.";
      var cached = figureCache.get(key);
      if (cached && cached.url === objectUrl) {
        URL.revokeObjectURL(objectUrl);
        figureCache.delete(key);
      }
    }, {once: true});
    slot.style.display = "block";
    slot.style.minHeight = "0";
    slot.replaceChildren(image);
  }

  function loadFigure(slot, analysis, token) {
    var pathKey = slot.getAttribute("data-spashiny-river-preview-key") || "";
    var sourceUrl = slot.getAttribute("data-spashiny-river-preview-url") || "";
    if (!pathKey || !sourceUrl) return;
    var key = analysis + ":" + pathKey;
    var cached = figureCache.get(key);
    if (cached && cached.url) {
      showFigure(slot, cached.url, key);
      return;
    }
    if (!cached) {
      cached = {url: "", promise: null};
      figureCache.set(key, cached);
      cached.promise = fetch(sourceUrl, {
        credentials: "same-origin",
        headers: {
          "X-SpaShiny-Session": token,
          "X-SpaShiny-Analysis-Session": analysis
        }
      }).then(async function (response) {
        if (!response.ok) throw new Error("artifact authorization failed (HTTP " + response.status + ")");
        var blob = await response.blob();
        if (!blob.size) throw new Error("empty figure");
        return URL.createObjectURL(blob);
      }).then(function (objectUrl) {
        cached.url = objectUrl;
        return objectUrl;
      }).catch(function (error) {
        figureCache.delete(key);
        throw error;
      });
    }
    cached.promise.then(function (objectUrl) {
      if (sessionStorage.getItem("spashiny.analysis.session.id") !== analysis) return;
      showFigure(slot, objectUrl, key);
    }).catch(function (error) {
      if (slot.isConnected) slot.textContent = "Figure preview unavailable: " + String((error && error.message) || "unknown error");
    });
  }

  function scanFigures() {
    var token = sessionStorage.getItem("spashiny.session.token") || "";
    var analysis = sessionStorage.getItem("spashiny.analysis.session.id") || "";
    if (!token || !analysis) return;
    document.querySelectorAll("[data-spashiny-river-preview='1']").forEach(function (slot) {
      loadFigure(slot, analysis, token);
    });
  }

  function scheduleFigureScan() {
    if (figureScanTimer !== null) return;
    figureScanTimer = setTimeout(function () {
      figureScanTimer = null;
      scanFigures();
    }, 40);
  }

  new MutationObserver(scheduleFigureScan).observe(document.documentElement, {childList: true, subtree: true});
  document.addEventListener("DOMContentLoaded", scheduleFigureScan);
  document.addEventListener("shiny:connected", scheduleFigureScan);
  scheduleFigureScan();
  window.addEventListener("pagehide", function () {
    figureCache.forEach(function (entry) {
      if (entry.url) URL.revokeObjectURL(entry.url);
    });
    figureCache.clear();
  });

  function registerShinyHandler() {
    if (registered || !window.Shiny || typeof window.Shiny.addCustomMessageHandler !== "function") return;
    window.Shiny.addCustomMessageHandler("river_st_progress", function (message) {
      var action = String((message && message.action) || "");
      if (action === "done" || action === "failed") {
        hide();
      } else if (action === "update") {
        update(message.title, message.detail);
      }
    });
    registered = true;
  }
  document.addEventListener("DOMContentLoaded", registerShinyHandler);
  document.addEventListener("shiny:connected", registerShinyHandler);
  registerShinyHandler();

  document.addEventListener("shiny:disconnected", function () {
    if (overlay && overlay.style.display !== "none") {
      update(
        navigator.onLine === false ? "Browser network is offline" : "Connection interrupted; cause not yet confirmed",
        "Waiting for this tab to reconnect. The job may continue during a brief interruption, but the server can cancel it if the analysis heartbeat lease expires."
      );
    }
  });
})();
