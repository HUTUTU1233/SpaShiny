(function () {
  "use strict";

  // Presentation only: preserve the input, its FileList and upload listeners.
  // NEVER add id/name to id-less multipart inputs: Shiny would upload twice.
  if (window.SpaShinyEnglishFilePicker) {
    window.SpaShinyEnglishFilePicker.scan(document);
    return;
  }
  var controls = new WeakMap();
  var selector = 'input[type="file"]';

  function installStyle() {
    if (document.getElementById("spashiny-english-upload-style")) return;
    var style = document.createElement("style");
    style.id = "spashiny-english-upload-style";
    style.textContent =
      ".spashiny-native-file-input{position:absolute!important;width:1px!important;" +
      "height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;" +
      "clip:rect(0,0,0,0)!important;clip-path:inset(50%)!important;white-space:nowrap!important;border:0!important;}" +
      ".spashiny-english-file-picker{display:flex;align-items:center;gap:10px;width:100%;" +
      "min-height:38px;padding:6px 10px;border:1px solid #ced4da;border-radius:6px;background:#fff;box-sizing:border-box;}" +
      ".spashiny-english-file-picker button{flex:0 0 auto;white-space:nowrap;}" +
      ".spashiny-english-file-picker .spashiny-file-names{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#495057;}";
    (document.head || document.documentElement).appendChild(style);
  }

  function enhance(input) {
    var existing = controls.get(input);
    if (existing) { existing.sync(); return; }
    // Shiny already renders English Browse/No file selected controls. Leave
    // its nodes/bindings and other explicitly hidden custom inputs alone.
    if (input.classList.contains("shiny-input-file") || input.closest(".btn-file") ||
        input.hidden || input.style.display === "none") return;
    if (!input.parentNode) return;

    var wrapper = document.createElement("div");
    wrapper.className = "spashiny-english-file-picker";
    wrapper.lang = "en";
    wrapper.setAttribute("role", "group");
    wrapper.setAttribute("aria-label", "File upload");
    var button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-outline-primary btn-sm";
    var names = document.createElement("span");
    names.className = "spashiny-file-names";
    names.setAttribute("aria-live", "polite");
    names.setAttribute("aria-atomic", "true");
    wrapper.appendChild(button);
    wrapper.appendChild(names);
    // A sibling, not a replacement/reparenting of the upload input.
    input.parentNode.insertBefore(wrapper, input);
    input.classList.add("spashiny-native-file-input");
    input.setAttribute("tabindex", "-1");

    function sync() {
      var multiple = !!input.multiple;
      button.textContent = multiple ? "Choose files" : "Choose file";
      button.disabled = !!input.disabled;
      var files = Array.prototype.slice.call(input.files || []);
      var text = files.length ? files.map(function (file) { return file.name; }).join(", ") :
        (multiple ? "No files selected" : "No file selected");
      // Names are user data: retain non-English names and never interpolate HTML.
      if (names.textContent !== text) names.textContent = text;
      if (names.title !== text) names.title = text;
    }
    controls.set(input, { sync: sync, wrapper: wrapper });
    button.addEventListener("click", function () {
      sync();
      if (!input.disabled) input.click();
    });
    input.addEventListener("change", function () {
      sync();
      window.setTimeout(sync, 0); // Validators may clear the value synchronously.
    });
    wrapper.addEventListener("focusin", sync);
    if (input.form) input.form.addEventListener("reset", function () { window.setTimeout(sync, 0); });
    sync();
  }

  function scan(root) {
    if (!root) return;
    if (root.nodeType === 1 && root.matches(selector)) enhance(root);
    if (root.querySelectorAll) Array.prototype.forEach.call(root.querySelectorAll(selector), enhance);
  }

  window.SpaShinyEnglishFilePicker = { version: "20261109-v1", scan: scan };
  installStyle();
  scan(document);
  var observer = new MutationObserver(function (records) {
    records.forEach(function (record) {
      if (record.type === "attributes") {
        var control = controls.get(record.target);
        if (control) control.sync();
      } else {
        Array.prototype.forEach.call(record.addedNodes, scan);
      }
    });
  });
  observer.observe(document.documentElement, {
    childList: true, subtree: true, attributes: true, attributeFilter: ["disabled", "multiple"]
  });
  document.addEventListener("DOMContentLoaded", function () { scan(document); });
  document.addEventListener("shiny:connected", function () { scan(document); });
}());
