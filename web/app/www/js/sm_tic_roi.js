(function () {
  "use strict";
  if (window.SpaShinyTicRoi) { window.SpaShinyTicRoi.bind(); return; }
  var state = {data: null, selections: {}, current: "", uploading: false, plotly: null,
    csvRoles: {}, csvUploading: false, csvScope: ""};
  function el(id) { return document.getElementById(id); }
  function emit(name, value) {
    if (window.Shiny && window.Shiny.setInputValue) {
      window.Shiny.setInputValue(name, Object.assign({}, value, {nonce: Date.now()}), {priority: "event"});
    }
  }
  function show(id, message) {
    if (el(id)) el(id).textContent = message;
    if (id === "sm_tic_roi_status" && el("sm_pos_neg_status")) el("sm_pos_neg_status").textContent = message;
  }
  // Downloads use this tab's credentials, not a cookie another tab can replace.
  // The server still checks owner, exact analysis, signature, path and manifest.
  async function download(event) {
    var link = event.target.closest("a[data-sm-tic-roi-download='1']");
    if (!link) return;
    event.preventDefault();
    if (link.dataset.downloading === "1") return;
    var url = new URL(link.href, window.location.origin);
    var token = sessionStorage.getItem("spashiny.session.token") || "";
    var analysis = sessionStorage.getItem("spashiny.analysis.session.id") || "";
    if (url.origin !== window.location.origin || !url.pathname.startsWith("/lab-result-download/")) {
      show("sm_tic_roi_status", "Download failed: INVALID_DOWNLOAD_URL"); return;
    }
    if (!token || !analysis || url.searchParams.get("analysis_session_id") !== analysis) {
      show("sm_tic_roi_status", "Download failed: CURRENT_ANALYSIS_FORBIDDEN. Return to the analysis that created this result."); return;
    }
    link.dataset.downloading = "1";
    link.setAttribute("aria-disabled", "true");
    show("sm_tic_roi_status", "Downloading " + link.download + "…");
    try {
      var response = await fetch(url.href, {credentials: "same-origin", headers: {
        "X-SpaShiny-Session": token, "X-SpaShiny-Analysis-Session": analysis
      }});
      if (!response.ok) {
        var payload = await response.json().catch(function () { return {}; });
        var detail = payload.detail || payload;
        throw new Error("HTTP " + response.status + " — " + (detail.code || "DOWNLOAD_FAILED") +
          (detail.message ? ": " + detail.message : ""));
      }
      var blob = await response.blob();
      if (!blob.size) throw new Error("EMPTY_DOWNLOAD");
      var objectUrl = URL.createObjectURL(blob);
      var save = document.createElement("a");
      save.href = objectUrl; save.download = link.download; save.style.display = "none";
      document.body.appendChild(save); save.click(); save.remove();
      setTimeout(function () { URL.revokeObjectURL(objectUrl); }, 60000);
      show("sm_tic_roi_status", "Download ready: " + link.download);
    } catch (error) {
      show("sm_tic_roi_status", "Download failed: " + String(error.message || error));
    } finally {
      delete link.dataset.downloading; link.removeAttribute("aria-disabled");
    }
  }
  document.addEventListener("click", download);
  function sendSelection() {
    if (state.data) emit("sm_tic_roi_selection", {preview_job_id: state.data.preview_job_id, selections: state.selections});
  }
  function dataset() { return state.data && state.data.datasets.find(function (d) { return d.id === state.current; }); }
  function options(node, items, value) {
    if (!node) return;
    node.replaceChildren();
    items.forEach(function (item) {
      var option = document.createElement("option"); option.value = item[0]; option.textContent = item[1]; node.appendChild(option);
    });
    node.value = String(value);
  }
  function loadPlotly() {
    if (window.Plotly && window.Plotly.react) return Promise.resolve(window.Plotly);
    if (!state.plotly) state.plotly = new Promise(function (resolve, reject) {
      var script = document.createElement("script"); script.src = "/js/plotly-session.min.js?v=5.10.0";
      script.onload = function () { resolve(window.Plotly); };
      script.onerror = function () { state.plotly = null; reject(new Error("TIC plotting library failed to load. Check the connection and reopen this page.")); };
      document.head.appendChild(script);
    });
    return state.plotly;
  }
  function stats() {
    if (!state.data) return;
    var text = state.data.datasets.map(function (d) {
      var s = state.selections[d.id];
      return d.name + ": " + s.pixel_ids.length + " ROI pixels (z=" + s.z + ")" +
        (d.duplicate_mz_pixels ? "; repeated m/z in " + d.duplicate_mz_pixels + " pixels — choose an explicit CSV policy" : "");
    }).join(" · ");
    show("sm_tic_roi_selection_status", text);
  }
  function draw() {
    var d = dataset(), node = el("sm_tic_roi_plot");
    if (!d || !node) return;
    var selected = state.selections[d.id];
    var pixels = d.pixels.filter(function (p) { return p.z === selected.z; });
    var selectedSet = new Set(selected.pixel_ids);
    var marked = pixels.filter(function (p) { return selectedSet.has(p.pixel_id); });
    options(el("sm_tic_roi_z"), d.z_values.map(function (z) { return [z, z]; }), selected.z);
    stats();
    loadPlotly().then(function (Plotly) {
      if (node !== el("sm_tic_roi_plot") || d !== dataset()) return;
      var tic = pixels.map(function (p) { return p.logTIC; });
      var min = Math.min.apply(null, tic.slice(0, 10000)), max = Math.max.apply(null, tic.slice(0, 10000));
      for (var i = 10000; i < tic.length; i++) { min = Math.min(min, tic[i]); max = Math.max(max, tic[i]); }
      var traces = [{type: "scattergl", mode: "markers", name: "TIC", x: pixels.map(function (p) {return p.x;}),
        y: pixels.map(function (p) {return p.y;}), customdata: pixels.map(function (p) {return p.pixel_id;}),
        text: pixels.map(function (p) {return "Pixel " + p.pixel_id + "<br>TIC=" + p.TIC;}),
        marker: {symbol: "square", size: 5, color: tic, colorscale: "Viridis", cmin: min, cmax: max > min ? max : min + 1,
          colorbar: {title: "log10(TIC+1)"}}, hovertemplate: "%{text}<br>x=%{x}, y=%{y}<extra></extra>"},
        {type: "scattergl", mode: "markers", name: "Selected ROI", x: marked.map(function (p) {return p.x;}),
          y: marked.map(function (p) {return p.y;}), customdata: marked.map(function (p) {return p.pixel_id;}),
          marker: {symbol: "square-open", size: 7, color: "#ef4444", line: {width: 1}}, hoverinfo: "skip"}];
      var layout = {title: {text: d.name + " — TIC (z=" + selected.z + ")"}, dragmode: "lasso",
        clickmode: "event", hovermode: "closest", uirevision: d.id + ":" + selected.z,
        margin: {l: 60, r: 105, t: 55, b: 55}, xaxis: {title: "Original x", constrain: "domain"},
        yaxis: {title: "Original y", autorange: "reversed", scaleanchor: "x", scaleratio: 1},
        legend: {orientation: "h", y: -0.12}, paper_bgcolor: "#fff", plot_bgcolor: "#fff"};
      return Plotly.react(node, traces, layout, {responsive: true, displaylogo: false, modeBarButtonsToAdd: ["select2d", "lasso2d"]}).then(function () {
        node.removeAllListeners("plotly_click"); node.removeAllListeners("plotly_selected");
        node.on("plotly_click", function (event) {
          if (!event.points || !event.points.length) return;
          var id = event.points[0].customdata, s = state.selections[d.id], ids = new Set(s.pixel_ids);
          if (ids.has(id)) ids.delete(id); else ids.add(id);
          s.pixel_ids = Array.from(ids).sort(function (a, b) {return a-b;}); sendSelection(); draw();
        });
        node.on("plotly_selected", function (event) {
          if (!event || !event.points || !event.points.length) return;
          var s = state.selections[d.id], ids = new Set(s.pixel_ids), removing = el("sm_tic_roi_mode").value === "remove";
          event.points.forEach(function (p) { if (removing) ids.delete(p.customdata); else ids.add(p.customdata); });
          s.pixel_ids = Array.from(ids).sort(function (a, b) {return a-b;}); sendSelection(); draw();
        });
      });
    }).catch(function (error) {show("sm_tic_roi_selection_status", error.message);});
  }
  function receive(data) {
    state.data = data;
    state.selections = data.selections || {};
    data.datasets.forEach(function (d) {
      if (!state.selections[d.id]) state.selections[d.id] = {z: d.z_values[0], pixel_ids: []};
    });
    if (!data.datasets.some(function (d) {return d.id === state.current;})) state.current = data.datasets[0].id;
    options(el("sm_tic_roi_dataset"), data.datasets.map(function (d) {return [d.id, d.name];}), state.current);
    draw();
  }
  function bindCsvPickers() {
    if (!window.Shiny || !window.Shiny.setInputValue) return;
    var analysis = sessionStorage.getItem("spashiny.analysis.session.id") || "";
    if (state.csvScope !== analysis) {
      state.csvScope = analysis; state.csvRoles = {};
      ["pos", "neg"].forEach(function (role) {show("sm_pos_neg_" + role + "_upload_status", "No " + role.toUpperCase() + " CSV uploaded.");});
    }
    document.querySelectorAll("input[data-sm-pos-neg-csv]").forEach(function (picker) {
      if (picker.dataset.bound === "1") return;
      picker.dataset.bound = "1";
      picker.addEventListener("change", async function () {
        var role = picker.dataset.smPosNegCsv;
        var file = picker.files && picker.files[0];
        var statusId = "sm_pos_neg_" + role + "_upload_status";
        if (!file) return;
        if (state.csvUploading || state.uploading) {
          show(statusId, "Wait for the current upload to finish, then select this CSV again."); picker.value = ""; return;
        }
        if (!/\.csv$/i.test(file.name) || !file.size) {
          show(statusId, "Select one nonempty spectrum .csv file."); picker.value = ""; return;
        }
        if (!window.SpaShinyMultipartUpload) {
          show(statusId, "Secure upload service is not ready. Wait and reselect the CSV."); picker.value = ""; return;
        }
        var scopeAtStart = sessionStorage.getItem("spashiny.analysis.session.id") || "";
        state.csvUploading = true; picker.disabled = true;
        delete state.csvRoles[role];
        emit("sm_pos_neg_uploaded", {status: "UPLOADING", roles: state.csvRoles});
        try {
          var result = await window.SpaShinyMultipartUpload.uploadFile(file, {onProgress: function (progress) {
            var pct = Math.round(100 * (progress.uploaded_bytes || 0) / Math.max(1, file.size));
            show(statusId, role.toUpperCase() + ": " + file.name + " — " + pct + "% (" + (progress.status || "UPLOADING") + ")");
          }});
          if (!scopeAtStart || scopeAtStart !== sessionStorage.getItem("spashiny.analysis.session.id")) {
            throw new Error("ANALYSIS_CHANGED: upload is not adopted by a different analysis. Select the CSV in the intended analysis.");
          }
          state.csvRoles[role] = String(result.upload_id);
          show(statusId, role.toUpperCase() + " ready: " + file.name);
          emit("sm_pos_neg_uploaded", {status: state.csvRoles.pos && state.csvRoles.neg ? "READY" : "PARTIAL", roles: state.csvRoles});
        } catch (error) {
          var message = String(error.userMessage || error.message || error.code || "UPLOAD_FAILED");
          show(statusId, "Upload failed: " + message);
          emit("sm_pos_neg_uploaded", {status: "FAILED", roles: state.csvRoles, message: message, code: error.code || "UPLOAD_FAILED"});
        } finally {state.csvUploading = false; picker.disabled = false; picker.value = "";}
      });
    });
  }
  function bind() {
    bindCsvPickers();
    var picker = document.querySelector("input[data-sm-tic-roi-upload]");
    if (!picker || picker.dataset.bound === "1") return;
    if (!window.Shiny || !window.Shiny.addCustomMessageHandler) return;
    picker.dataset.bound = "1";
    if (!state.handler) { window.Shiny.addCustomMessageHandler("sm_tic_roi_preview", receive); state.handler = true; }
    picker.addEventListener("change", async function () {
      var files = Array.from(picker.files || []);
      if (!files.length) return;
      if (state.uploading || state.csvUploading) {
        show("sm_tic_roi_upload_status", "Wait for the current upload to finish, then reselect the files."); picker.value = ""; return;
      }
      if (files.length < 2 || files.length > 16 || files.some(function (f) {return !/\.(imzml|ibd)$/i.test(f.name);})) {
        show("sm_tic_roi_upload_status", "Select 1–8 matching imzML/IBD pairs."); picker.value = ""; return;
      }
      var pairs = new Map();
      files.forEach(function (f) {
        var dot = f.name.lastIndexOf("."), key = f.name.slice(0, dot).toLowerCase(), ext = f.name.slice(dot).toLowerCase();
        var suffixes = pairs.get(key) || []; suffixes.push(ext); pairs.set(key, suffixes);
      });
      if (Array.from(pairs.values()).some(function (p) {return p.length !== 2 || !p.includes(".imzml") || !p.includes(".ibd");})) {
        show("sm_tic_roi_upload_status", "Each imzML needs one IBD with exactly the same filename stem. No duplicate names."); picker.value = ""; return;
      }
      if (!window.SpaShinyMultipartUpload) {show("sm_tic_roi_upload_status", "Secure upload service is not ready. Wait and reselect the files."); return;}
      state.uploading = true; picker.disabled = true;
      state.data = null; state.selections = {};
      if (el("sm_tic_roi_plot")) { if (window.Plotly) window.Plotly.purge(el("sm_tic_roi_plot")); el("sm_tic_roi_plot").replaceChildren(); }
      emit("sm_tic_roi_uploaded", {status: "UPLOADING"});
      var ids = [];
      try {
        for (var i = 0; i < files.length; i++) {
          var file = files[i], position = i + 1;
          show("sm_tic_roi_upload_status", "Uploading " + position + "/" + files.length + ": " + file.name);
          var result = await window.SpaShinyMultipartUpload.uploadFile(file, {onProgress: function (progress) {
            var pct = Math.round(100 * (progress.uploaded_bytes || 0) / Math.max(1, file.size));
            show("sm_tic_roi_upload_status", "Uploading " + position + "/" + files.length + ": " + file.name + " — " + pct + "% (" + (progress.status || "UPLOADING") + ")");
          }});
          ids.push(String(result.upload_id));
        }
        show("sm_tic_roi_upload_status", files.length + " files uploaded. Click Compute TIC preview.");
        emit("sm_tic_roi_uploaded", {status: "READY", upload_ids: ids});
      } catch (error) {
        var message = String(error.userMessage || error.message || error.code || "UPLOAD_FAILED");
        show("sm_tic_roi_upload_status", "Upload failed: " + message);
        emit("sm_tic_roi_uploaded", {status: "FAILED", code: error.code || "UPLOAD_FAILED", message: message});
      } finally {state.uploading = false; picker.disabled = false; picker.value = "";}
    });
    el("sm_tic_roi_dataset").addEventListener("change", function (event) {state.current = event.target.value; draw();});
    el("sm_tic_roi_z").addEventListener("change", function (event) {
      if (!dataset()) return;
      state.selections[state.current] = {z: Number(event.target.value), pixel_ids: []}; sendSelection(); draw();
    });
    el("sm_tic_roi_clear").addEventListener("click", function () {
      if (dataset()) {state.selections[state.current].pixel_ids = []; sendSelection(); draw();}
    });
    if (state.data) receive(state.data);
    emit("sm_tic_roi_mount", {});
  }
  window.SpaShinyTicRoi = {bind: bind};
  new MutationObserver(bind).observe(document.documentElement, {childList: true, subtree: true});
  window.addEventListener("shiny:connected", bind);
  setInterval(function () {if (!state.handler) bind();}, 500);
  bind();
})();
