(function () {
  "use strict";
  if (window.__spashinyKnnUploadInstalled) return;
  window.__spashinyKnnUploadInstalled = true;
  var queue = Promise.resolve();
  function analysis() { return sessionStorage.getItem("spashiny.analysis.session.id") || ""; }
  function emit(payload) {
    if (!window.Shiny || typeof window.Shiny.setInputValue !== "function") throw new Error("Shiny is not connected; wait for reconnect before uploading.");
    window.Shiny.setInputValue("knn_canonical_upload_event", payload, {priority: "event"});
  }
  document.addEventListener("change", function (event) {
    var input = event.target;
    if (!input || !input.matches || !input.matches("input[data-spashiny-knn-upload]")) return;
    event.stopImmediatePropagation();
    var file = input.files && input.files[0];
    if (!file) return;
    var kind = input.getAttribute("data-spashiny-knn-upload");
    var status = document.querySelector("[data-spashiny-knn-upload-status='" + kind + "']");
    var selectedAnalysis = analysis();
    var selectionId = (window.crypto && window.crypto.randomUUID) ? window.crypto.randomUUID() : Date.now() + "-" + Math.random();
    function show(text) { if (status && status.isConnected !== false) status.textContent = text; }
    function payload(state, extra) {
      return Object.assign({kind: kind, status: state, selection_id: selectionId,
        analysis_session_id: selectedAnalysis, filename: file.name}, extra || {});
    }
    if (!selectedAnalysis || !window.SpaShinyMultipartUpload) { show("Wait for this analysis and its upload service to connect."); return; }
    try { emit(payload("SELECTED")); } catch (error) { show(error.message); return; }
    show("Selected " + file.name + ". Waiting for the previous KNN upload, if any...");
    queue = queue.catch(function () {}).then(function () {
      if (analysis() !== selectedAnalysis) { show("Upload was not started: this tab changed analysis."); return; }
      return window.SpaShinyMultipartUpload.uploadFile(file, {
        onProgress: function (detail) {
          var total = Number(detail.total_bytes || file.size || 0);
          var percent = total ? Math.min(100, Math.round(Number(detail.uploaded_bytes || 0) * 100 / total)) : 0;
          show(detail.status === "COMPLETING" ? "Finalizing " + file.name + "..." : "Uploading " + file.name + ": " + percent + "%");
        },
        onComplete: function (result) {
          if (analysis() !== selectedAnalysis) { show("Upload completed in the previous analysis; it was not adopted here."); return; }
          show("Ready: " + file.name);
          emit(payload("READY", {upload_id: String(result.upload_id || "")}));
          input.value = "";
        },
        onError: function (error) {
          var message = String(error.userMessage || error.message || "Upload failed.");
          show(message);
          if (analysis() === selectedAnalysis) emit(payload("FAILED", {code: String(error.code || "UPLOAD_FAILED"), message: message}));
        }
      }).catch(function () {});
    });
  }, true);
})();
