(function () {
  "use strict";

  var TOKEN_KEY = "spashiny.session.token";
  var MAX_BROWSER_FILE_BYTES = 5368709120;
  var activeUploads = new Map();

  function sessionToken() {
    return sessionStorage.getItem(TOKEN_KEY) || "";
  }

  function apiFetch(path, options) {
    options = options || {};
    options.headers = options.headers || {};
    options.headers["Accept"] = "application/json";
    options.headers["X-SpaShiny-Session"] = sessionToken();
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
      throw error;
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

  function putPart(url, blob, controller) {
    return fetch(url, {
      method: "PUT",
      body: blob,
      signal: controller.signal
    }).then(function (response) {
      if (!response.ok) {
        throw new Error("PART_UPLOAD_FAILED");
      }
      return response.headers.get("ETag") || response.headers.get("etag") || "";
    });
  }

  function uploadFile(file, callbacks) {
    callbacks = callbacks || {};
    if (!file) {
      return Promise.reject(new Error("NO_FILE"));
    }
    if (file.size > MAX_BROWSER_FILE_BYTES) {
      return Promise.reject(new Error("FILE_TOO_LARGE"));
    }
    if (!sessionToken()) {
      return Promise.reject(new Error("SESSION_NOT_READY"));
    }

    var estimatedPartSize = 67108864;
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
          return presign(uploadState.uploadId, partNumber).then(function (signed) {
            return putPart(signed.url, blob, controller);
          });
        }, 3).then(function (etag) {
          uploadState.uploadedBytes += blob.size;
          completedParts.push({ part_number: partNumber, etag: etag });
          report("UPLOADING");
          return worker();
        });
      }

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
      report(error.code || error.message || "FAILED");
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
    abortActiveUploads: abortActiveUploads
  };
})();
