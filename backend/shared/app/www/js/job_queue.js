(function () {
  "use strict";

  var TOKEN_KEY = "spashiny.session.token";

  function token() {
    return sessionStorage.getItem(TOKEN_KEY) || "";
  }

  function cancelJob(jobId) {
    if (!jobId || !token()) {
      return;
    }
    fetch("/api/jobs/" + encodeURIComponent(jobId) + "/cancel", {
      method: "POST",
      headers: {
        "Accept": "application/json",
        "X-SpaShiny-Session": token()
      }
    }).finally(function () {
      window.location.reload();
    });
  }

  function showStatus(message, isError) {
    var status = document.getElementById("cloud-example-reference-status");
    if (!status) {
      status = document.createElement("div");
      status.id = "cloud-example-reference-status";
      status.className = "cloud-muted";
      var anchor = document.querySelector(".cloud-use-example");
      if (anchor && anchor.parentNode) {
        anchor.parentNode.insertBefore(status, anchor);
      } else if (document.body) {
        document.body.appendChild(status);
      }
    }
    status.textContent = message || "";
    status.classList.toggle("cloud-error", !!isError);
  }

  function showActionStatus(button, message, isError) {
    var targetId = button && button.getAttribute("data-status-target");
    var status = targetId ? document.getElementById(targetId) : null;
    if (!status && button && button.parentNode) {
      status = button.parentNode.querySelector(".cloud-example-status");
    }
    if (!status) {
      showStatus(message, isError);
      return;
    }
    status.textContent = message || "";
    status.classList.toggle("cloud-error", !!isError);
    status.classList.toggle("ready", !isError && !!message);
  }

  function errorMessage(code) {
    var messages = {
      INVALID_SESSION: "Your cloud session is not ready. Please refresh and try again.",
      SESSION_EXPIRED: "Your cloud session has expired. Please refresh and start a new session.",
      ASSET_NOT_ALLOWLISTED: "This example asset is not available in the current manifest.",
      ASSET_REFERENCE_NOT_FOUND: "The selected example reference was not found.",
      ASSET_REFERENCE_FORBIDDEN: "This example reference belongs to another session.",
      ASSET_WORKFLOW_NOT_ALLOWED: "This workflow is not available for the selected example asset.",
      INVALID_ASSET_REFERENCE: "The selected example reference is not valid.",
      DUPLICATE_ASSET_REFERENCE: "This example asset is already in My Files.",
      EXAMPLE_ACTION_NOT_FOUND: "This built-in example action is not available.",
      EXAMPLE_ACTION_PAGE_MISMATCH: "This built-in example is not available on the current page.",
      INVALID_REQUEST_PAYLOAD: "The request could not be understood. Please refresh and try again."
    };
    return messages[code] || "Example data reference could not be created.";
  }

  function extractErrorCode(payload) {
    var detail = payload && payload.detail;
    if (detail && typeof detail === "object" && detail.code) {
      return detail.code;
    }
    if (payload && payload.code) {
      return payload.code;
    }
    return "";
  }

  function useExampleData(button) {
    if (!button || button.getAttribute("data-submitting") === "1") {
      return;
    }
    var assetId = button.getAttribute("data-asset-id") || "";
    var objectKey = button.getAttribute("data-object-key") || "";
    if ((!assetId && !objectKey) || !token()) {
      return;
    }
    button.setAttribute("data-submitting", "1");
    button.disabled = true;
    var originalText = button.textContent;
    button.textContent = "Adding...";
    showStatus("Creating example data reference...", false);
    var body = assetId ? { asset_id: assetId } : { asset_object_key: objectKey };
    fetch("/api/example-asset-references", {
      method: "POST",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-SpaShiny-Session": token()
      },
      body: JSON.stringify(body)
    }).then(function (response) {
      return response.json().catch(function () {
        return {};
      }).then(function (payload) {
        if (!response.ok) {
          throw new Error(errorMessage(extractErrorCode(payload)));
        }
        return payload;
      });
    }).then(function (payload) {
      showStatus((payload && payload.display_name ? payload.display_name : "Example data") + " added to My Files.", false);
      window.location.reload();
    }).catch(function (error) {
      showStatus(error && error.message ? error.message : "Example data reference could not be created.", true);
    }).finally(function () {
      button.removeAttribute("data-submitting");
      button.disabled = false;
      button.textContent = originalText;
    });
  }

  function activateExampleAction(button) {
    if (!button || button.getAttribute("data-submitting") === "1") {
      return;
    }
    var actionId = button.getAttribute("data-action-id") || "";
    var pageName = button.getAttribute("data-page-name") || "";
    if (!actionId || !token()) {
      return;
    }
    button.setAttribute("data-submitting", "1");
    button.disabled = true;
    var originalText = button.textContent;
    button.textContent = "Loading...";
    showActionStatus(button, "Binding example inputs to this page...", false);
    fetch("/api/example-actions/" + encodeURIComponent(actionId) + "/activate", {
      method: "POST",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-SpaShiny-Session": token()
      },
      body: JSON.stringify({ page_name: pageName })
    }).then(function (response) {
      return response.json().catch(function () {
        return {};
      }).then(function (payload) {
        if (!response.ok) {
          throw new Error(errorMessage(extractErrorCode(payload)));
        }
        return payload;
      });
    }).then(function (payload) {
      var samples = payload && payload.sample_ids && payload.sample_ids.length ? " Samples: " + payload.sample_ids.join(", ") + "." : "";
      var message = (payload && (payload.user_message || payload.message) ? (payload.user_message || payload.message) : "Example inputs are ready.") + samples;
      showActionStatus(button, message, !(payload && payload.ready));
      if (window.Shiny && typeof window.Shiny.setInputValue === "function") {
        window.Shiny.setInputValue("cloud_example_action_activated", {
          action_id: payload.action_id,
          page_name: payload.page_name || pageName,
          ready: !!payload.ready,
          sample_ids: payload.sample_ids || [],
          bound_roles: payload.bound_roles || [],
          missing_roles: payload.missing_roles || [],
          available_workflows: payload.available_workflows || []
        }, { priority: "event" });
      }
    }).catch(function (error) {
      showActionStatus(button, error && error.message ? error.message : "Example inputs could not be bound.", true);
    }).finally(function () {
      button.removeAttribute("data-submitting");
      button.disabled = false;
      button.textContent = originalText;
    });
  }

  if (window.__spaShinyJobQueueHandlerInstalled) {
    return;
  }
  window.__spaShinyJobQueueHandlerInstalled = true;

  document.addEventListener("click", function (event) {
    var target = event.target && event.target.closest ? event.target.closest(".cloud-cancel-job, .cloud-use-example, .cloud-example-action") : event.target;
    if (target && target.classList && target.classList.contains("cloud-cancel-job")) {
      event.preventDefault();
      event.stopPropagation();
      cancelJob(target.getAttribute("data-job-id"));
    }
    if (target && target.classList && target.classList.contains("cloud-use-example")) {
      event.preventDefault();
      event.stopPropagation();
      useExampleData(target);
    }
    if (target && target.classList && target.classList.contains("cloud-example-action")) {
      event.preventDefault();
      event.stopPropagation();
      activateExampleAction(target);
    }
  }, true);
})();
