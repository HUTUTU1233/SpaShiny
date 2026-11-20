# Original feature imports, constants and direct helper functions; no duplicate UI/server bodies.
from __future__ import annotations
from pathlib import Path as _ExportPath

LEGACY_ENTRYPOINT_FILE = str(
    _ExportPath(__file__).resolve().parents[3] / "spatialmeta_workbench_ui.py"
)
"""Shiny UI for single-sample orchestration and native network/report downloads.

Background work uses ExtendedTask: awaiting a long coroutine inside an ordinary
reactive effect can still hold Shiny's reactive flush. Business actions are
provided by the existing application's exact-scope adapter, never internal HTTP
endpoints, synthetic analysis ids or browser-injected button clicks.
"""
import asyncio
import inspect
import json
from pathlib import Path
from shiny import reactive, render, ui
from shiny.types import SilentException
from single_sample_pipeline import Run, Scope, PipelineError, load_run, save_run, bounded_child


def upload_controls():
    fields = []
    for role, label in (
        ("st", "ST H5AD"),
        ("sm", "SM H5AD"),
        ("joint", "Joint H5AD (integration start only)"),
    ):
        fields.append(
            ui.div(
                ui.tags.label(label),
                ui.tags.input(
                    type="file",
                    accept=".h5ad",
                    class_="form-control",
                    **{"data-one-stop-upload": role},
                ),
                ui.tags.div("No upload selected.", **{"data-one-stop-status": role}),
            )
        )
    return ui.div(
        *fields,
        ui.tags.script(
            """
    (function () {
      document.querySelectorAll('input[data-one-stop-upload]').forEach(function (node) {
        if (node.dataset.bound === '1') return;
        node.dataset.bound = '1';
        var role = node.dataset.oneStopUpload;
        var status = document.querySelector('[data-one-stop-status="' + role + '"]');
        function emit(payload) {
          if (window.Shiny) Shiny.setInputValue('one_stop_canonical_upload',
            Object.assign({role: role, nonce: Date.now()}, payload), {priority: 'event'});
        }
        node.addEventListener('change', function () {
          var file = node.files && node.files[0];
          if (!file) return;
          emit({status: 'SELECTED', filename: file.name});
          if (!window.SpaShinyMultipartUpload) {
            status.textContent = 'Upload service is not ready; select the file again after it loads.';
            emit({status:'FAILED', message:status.textContent}); return;
          }
          window.SpaShinyMultipartUpload.uploadFile(file, {
            onProgress: function (d) {
              var total = Number(d.total_bytes || file.size);
              status.textContent = String(d.status || 'UPLOADING') + ' ' +
                Math.min(100, Math.round(100 * Number(d.uploaded_bytes || 0) / total)) + '%';
            },
            onComplete: function (r) {
              status.textContent = 'READY: ' + file.name;
              emit({status:'READY', upload_id:String(r.upload_id || ''), filename:file.name});
              node.value = '';
            },
            onError: function (e) {
              status.textContent = String(e.userMessage || e.message || e.code || 'UPLOAD_FAILED');
              emit({status:'FAILED', message:status.textContent});
            }
          });
        });
      });
    })();
    """
        ),
        style="display:grid;gap:14px;",
    )


def one_stop_ui():
    from spashiny.features.one_stop.ui import one_stop_ui as _entry

    return _entry()


def network_panel_ui():
    from spashiny.features.network.ui import network_panel_ui as _entry

    return _entry()


def register_workbench(input, output, session, api):
    from spashiny.features.workbench.server import register_workbench as _entry

    return _entry(input, output, session, api)
