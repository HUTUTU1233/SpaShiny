(function () {
  "use strict";

  var TOKEN_KEY = "spashiny.session.token";
  var ANALYSIS_SESSION_KEY = "spashiny.analysis.session.id";
  var MAX_BROWSER_FILE_BYTES = 5368709120;
  var activeUploads = new Map();

  function sessionToken() {
    return sessionStorage.getItem(TOKEN_KEY) || "";
  }

  function analysisSessionId() {
    return sessionStorage.getItem(ANALYSIS_SESSION_KEY) || "";
  }

  function apiFetch(path, options) {
    options = options || {};
    options.headers = options.headers || {};
    options.headers["Accept"] = "application/json";
    options.headers["X-SpaShiny-Session"] = sessionToken();
    options.headers["X-SpaShiny-Analysis-Session"] = analysisSessionId();
    return fetch(path, options);
  }

  function emitUploadEvent(name, detail) {
    window.dispatchEvent(new CustomEvent(name, { detail: detail || {} }));
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      window.setTimeout(resolve, ms);
    });
  }

  // Keep upload failures actionable instead of exposing only the generic
  // PART_UPLOAD_FAILED code.  The server remains authoritative; this is a
  // presentation/diagnostic layer and does not change retry or authorization.
  function describeError(code, status, details, fallbackMessage) {
    details = details && typeof details === "object" ? details : {};
    var errorCode = String(code || "UPLOAD_FAILED");
    var detailMessage = String(
      details.message || details.error_message || details.detail || fallbackMessage || "The upload did not complete."
    ).trim();
    var haystack = (errorCode + " " + detailMessage + " " + String(details.error_type || "")).toUpperCase();
    var category = "internal";
    var label = "Upload error";
    var guidance = "Keep the upload ID and retry. If it repeats, contact support with the diagnostic details.";
    if (Number(status || 0) === 0 || /NETWORK|TIMEOUT|CONNECTION|CONNECT|DNS|DISCONNECT|PROXY|BROKEN_PIPE|PART_UPLOAD/.test(haystack)) {
      category = "network";
      label = "Network / connectivity error";
      guidance = "Check the network or SSH tunnel, then retry. The source file was not modified.";
    } else if (/CUDA|GPU|NVIDIA|CUDNN|ROCM|DEVICE|DRIVER|HARDWARE/.test(haystack)) {
      category = "hardware";
      label = "GPU / hardware error";
      guidance = "The compute device or driver reported an error. Retry or choose CPU when available.";
    } else if (Number(status) === 429 || /MEMORY|OOM|NO_SPACE|DISK|QUEUE_FULL|RESOURCE|CAPACITY|LIMIT|CONCURRENCY_EXCEEDED/.test(haystack)) {
      category = "resource";
      label = "Memory / resource error";
      guidance = Number(status) === 429 || /CONCURRENCY_EXCEEDED/.test(haystack)
        ? "The upload capacity or request rate limit is reached. Wait for an active upload to finish, then retry; this does not mean your session has expired."
        : "The service is out of memory, disk, or queue capacity. Reduce the workload or retry later.";
    } else if (/AUTH|FORBIDDEN|UNAUTHORIZED|PERMISSION|SESSION|OWNER|ANALYSIS/.test(haystack)) {
      category = "permission";
      label = "Permission / session error";
      guidance = "The current analysis session is not authorized or has expired. Refresh the session and retry.";
    } else if (/INPUT|H5AD|ANNDATA|FORMAT|VALIDATION|MANIFEST|FILE/.test(haystack)) {
      category = "input";
      label = "Input / file validation error";
      guidance = "Check the selected file, format, and size before retrying.";
    }
    return {
      category: category,
      label: label,
      code: errorCode,
      message: detailMessage,
      userMessage: label + ": " + detailMessage + " (" + errorCode + "). " + guidance
    };
  }

  function decorateError(error, fallbackCode) {
    error = error || new Error(fallbackCode || "UPLOAD_FAILED");
    var code = String(error.code || fallbackCode || error.message || "UPLOAD_FAILED");
    var description = describeError(code, error.status, error.details, error.message);
    error.code = code;
    error.category = description.category;
    error.userMessage = description.userMessage;
    error.errorDetails = description.message;
    return error;
  }

  function retry(fn, attempts) {
    var remaining = attempts || 3;
    function run() {
      return fn().catch(function (error) {
        remaining -= 1;
        if (remaining <= 0) {
          throw error;
        }
        return sleep((attempts - remaining) * 500).then(run);
      });
    }
    return run();
  }

  function uploadErrorFromResponse(response, fallbackCode) {
    return response.json().catch(function () {
      return {};
    }).then(function (payload) {
      var detail = payload.detail || payload || {};
      var code = detail.code || fallbackCode;
      var error = new Error(code);
      error.code = code;
      error.status = response.status;
      error.details = detail;
      throw decorateError(error, fallbackCode);
    });
  }

  function initiate(file, totalParts) {
    return apiFetch("/api/uploads/initiate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: file.name,
        size_bytes: file.size,
        content_type: file.type || "application/octet-stream",
        total_parts: totalParts
      })
    }).then(function (response) {
      if (response.status === 401 || response.status === 410) {
        throw new Error("SESSION_EXPIRED");
      }
      if (!response.ok) {
        return uploadErrorFromResponse(response, "UPLOAD_INIT_FAILED");
      }
      return response.json();
    });
  }

  function presign(uploadId, partNumber) {
    return apiFetch("/api/uploads/" + encodeURIComponent(uploadId) + "/parts/" + partNumber + "/presign", {
      method: "POST"
    }).then(function (response) {
      if (response.status === 401 || response.status === 410) {
        throw new Error("SESSION_EXPIRED");
      }
      if (!response.ok) {
        return uploadErrorFromResponse(response, "UPLOAD_PRESIGN_FAILED");
      }
      return response.json();
    });
  }

  function complete(uploadId, parts) {
    return apiFetch("/api/uploads/" + encodeURIComponent(uploadId) + "/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ parts: parts })
    }).then(function (response) {
      if (response.status === 401 || response.status === 410) {
        throw new Error("SESSION_EXPIRED");
      }
      if (!response.ok) {
        return uploadErrorFromResponse(response, "UPLOAD_COMPLETE_FAILED");
      }
      return response.json();
    });
  }

  function abort(uploadId) {
    if (!uploadId) {
      return Promise.resolve();
    }
    return apiFetch("/api/uploads/" + encodeURIComponent(uploadId) + "/abort", {
      method: "POST",
      keepalive: true
    }).catch(function () {
      return null;
    });
  }

  function putPart(url, blob, controller, descriptor, onUploadProgress) {
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      var settled = false;

      function finish(callback, value) {
        if (settled) return;
        settled = true;
        controller.signal.removeEventListener("abort", abortRequest);
        callback(value);
      }

      function uploadError(code) {
        var error = new Error(code || "PART_UPLOAD_FAILED");
        error.code = code || "PART_UPLOAD_FAILED";
        error.status = Number(xhr.status || 0);
        try {
          var payload = JSON.parse(xhr.responseText || "{}");
          error.details = payload.detail || payload || {};
          error.code = error.details.code || error.code;
        } catch (_ignored) {
          error.details = {};
        }
        return decorateError(error, code || "PART_UPLOAD_FAILED");
      }

      function abortRequest() {
        xhr.abort();
      }

      xhr.open("PUT", url, true);
      xhr.setRequestHeader("Accept", "application/json");
      if (descriptor && descriptor.authenticated) {
        xhr.setRequestHeader("X-SpaShiny-Session", sessionToken());
        xhr.setRequestHeader("X-SpaShiny-Analysis-Session", analysisSessionId());
      }
      xhr.upload.onprogress = function (event) {
        if (onUploadProgress) {
          onUploadProgress(Number(event.loaded || 0), Number(event.total || blob.size || 0));
        }
      };
      xhr.onload = function () {
        if (xhr.status < 200 || xhr.status >= 300) {
          finish(reject, uploadError("PART_UPLOAD_FAILED"));
          return;
        }
        var headerEtag = xhr.getResponseHeader("ETag") || xhr.getResponseHeader("etag") || "";
        if (headerEtag) {
          finish(resolve, headerEtag);
          return;
        }
        try {
          var payload = JSON.parse(xhr.responseText || "{}");
          finish(resolve, String((payload && payload.etag) || ""));
        } catch (_ignored) {
          finish(resolve, "");
        }
      };
      xhr.onerror = function () {
        finish(reject, uploadError("PART_UPLOAD_NETWORK_ERROR"));
      };
      xhr.onabort = function () {
        finish(reject, uploadError("UPLOAD_ABORTED"));
      };
      controller.signal.addEventListener("abort", abortRequest, { once: true });
      xhr.send(blob);
    });
  }

  function uploadFile(file, callbacks) {
    callbacks = callbacks || {};
    if (!file) {
      return Promise.reject(decorateError(new Error("NO_FILE"), "NO_FILE"));
    }
    if (file.size > MAX_BROWSER_FILE_BYTES) {
      return Promise.reject(decorateError(new Error("FILE_TOO_LARGE"), "FILE_TOO_LARGE"));
    }
    if (!sessionToken()) {
      return Promise.reject(decorateError(new Error("SESSION_NOT_READY"), "SESSION_NOT_READY"));
    }
    if (!analysisSessionId()) {
      return Promise.reject(decorateError(new Error("ANALYSIS_SESSION_NOT_READY"), "ANALYSIS_SESSION_NOT_READY"));
    }

    // Keep browser estimates aligned with the production LocalTemp transport.
    // Small sequential parts complete within reverse-proxy request lifetimes and
    // make retries resume from the failed part rather than a 64 MiB boundary.
    var estimatedPartSize = 5242880;
    var estimatedParts = Math.max(1, Math.ceil(file.size / estimatedPartSize));
    var controller = new AbortController();
    var uploadState = {
      uploadId: "",
      uploadedBytes: 0,
      aborted: false,
      controller: controller
    };

    function report(status) {
      var detail = {
        upload_id: uploadState.uploadId,
        status: status,
        uploaded_bytes: uploadState.uploadedBytes,
        total_bytes: file.size
      };
      if (callbacks.onProgress) {
        callbacks.onProgress(detail);
      }
      emitUploadEvent("spashiny-upload-progress", detail);
    }

    return initiate(file, estimatedParts).then(function (init) {
      uploadState.uploadId = init.upload_id;
      activeUploads.set(uploadState.uploadId, uploadState);
      var partSize = Number(init.part_size || estimatedPartSize);
      var totalParts = Number(init.total_parts || Math.max(1, Math.ceil(file.size / partSize)));
      var maxParallel = Math.max(1, Number(init.max_parallel_parts || 4));
      var nextPart = 1;
      var completedParts = [];
      var partProgress = {};
      var lastProgressReportAt = 0;

      function reportPartProgress(partNumber, loaded, partBytes) {
        partProgress[partNumber] = Math.min(partBytes, Math.max(0, Number(loaded || 0)));
        var now = Date.now();
        if (now - lastProgressReportAt >= 100 || partProgress[partNumber] >= partBytes) {
          lastProgressReportAt = now;
          report("UPLOADING");
        }
      }

      function worker() {
        if (uploadState.aborted) {
          return Promise.resolve();
        }
        var partNumber = nextPart;
        nextPart += 1;
        if (partNumber > totalParts) {
          return Promise.resolve();
        }
        var start = (partNumber - 1) * partSize;
        var end = Math.min(file.size, start + partSize);
        var blob = file.slice(start, end);
        return retry(function () {
          partProgress[partNumber] = 0;
          return presign(uploadState.uploadId, partNumber).then(function (signed) {
            return putPart(signed.url, blob, controller, signed, function (loaded) {
              reportPartProgress(partNumber, loaded, blob.size);
            });
          });
        }, 3).then(function (etag) {
          delete partProgress[partNumber];
          uploadState.uploadedBytes += blob.size;
          completedParts.push({ part_number: partNumber, etag: etag });
          report("UPLOADING");
          return worker();
        });
      }

      var originalReport = report;
      report = function (status) {
        var inFlightBytes = Object.keys(partProgress).reduce(function (total, key) {
          return total + Number(partProgress[key] || 0);
        }, 0);
        var committedBytes = uploadState.uploadedBytes;
        uploadState.uploadedBytes = Math.min(file.size, committedBytes + inFlightBytes);
        originalReport(status);
        uploadState.uploadedBytes = committedBytes;
      };
      report("UPLOADING");
      var workers = [];
      for (var i = 0; i < Math.min(maxParallel, totalParts); i += 1) {
        workers.push(worker());
      }
      return Promise.all(workers).then(function () {
        if (uploadState.aborted) {
          throw new Error("UPLOAD_ABORTED");
        }
        completedParts.sort(function (a, b) {
          return a.part_number - b.part_number;
        });
        report("COMPLETING");
        return complete(uploadState.uploadId, completedParts);
      }).then(function (result) {
        activeUploads.delete(uploadState.uploadId);
        report("COMPLETED");
        if (callbacks.onComplete) {
          callbacks.onComplete(result);
        }
        return result;
      });
    }).catch(function (error) {
      if (uploadState.uploadId) {
        uploadState.aborted = true;
        controller.abort();
        abort(uploadState.uploadId);
        activeUploads.delete(uploadState.uploadId);
      }
      error = decorateError(error, error.code || error.message || "UPLOAD_FAILED");
      var diagnostic = describeError(error.code, error.status, error.details, error.message);
      report(error.code || error.message || "FAILED");
      emitUploadEvent("spashiny-upload-error", {
        upload_id: uploadState.uploadId,
        code: error.code,
        category: diagnostic.category,
        message: diagnostic.userMessage,
        details: diagnostic.message,
        status: Number(error.status || 0),
        filename: file.name,
        size_bytes: file.size
      });
      if (callbacks.onError) {
        callbacks.onError(error);
      }
      throw error;
    });
  }

  function abortActiveUploads() {
    activeUploads.forEach(function (state, uploadId) {
      state.aborted = true;
      state.controller.abort();
      abort(uploadId);
    });
    activeUploads.clear();
  }

  window.addEventListener("pagehide", abortActiveUploads);
  window.SpaShinyMultipartUpload = {
    uploadFile: uploadFile,
    abortActiveUploads: abortActiveUploads,
    describeError: describeError
  };
})();
