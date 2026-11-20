# Original feature imports, constants and direct helper functions; no duplicate UI/server bodies.
from __future__ import annotations
from pathlib import Path as _ExportPath

LEGACY_ENTRYPOINT_FILE = str(_ExportPath(__file__).resolve().parents[3] / "river_st_module.py")
import asyncio
import base64
import csv
import hashlib
import io
import math
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from shiny import reactive, render, ui
from cloud.river_options import PALETTES, positive_integer
from cloud.river_inspection import inspect_async, entry_signature, request_entries
from river_result_tools import read_ranking, render_saved_gene, saved_result_context
from river_result_selection import RiverResultSelection
from river_full_spot_plot import FULL_SPOT_PALETTES, render_full_spot_gene
from cloud.river_unified_contract import normalize_unified, V3, MODE
from cloud.river_scale_evidence import confirmation_for

WORKFLOW = "river_spatial_transcriptomics"
RIVER_EXAMPLE_ACTION_ID = "river-slideseq-wt-diabetes-example"
RIVER_VISIUM_EXAMPLE_ACTION_ID = "river-ifnics-bz-mi-visium-spa5-qc0-20261030-example"
RIVER_VISIUM_SAMPLES = (
    ("V39", "Sham"),
    ("V28", "D1"),
    ("V38", "D3"),
    ("V44", "D7"),
    ("V27", "D28"),
)
RIVER_EXAMPLE_ROLE = "river_time_series_archive"
MAX_ARCHIVE_MEMBERS = 256
MAX_ARCHIVE_H5AD_FILES = 64
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 80 * 1024 * 1024 * 1024
MAX_SINGLE_H5AD_BYTES = 20 * 1024 * 1024 * 1024


def apply_example_sample_defaults(samples, action_id):
    """Only the explicit Visium action supplies published order/group defaults.

    Ordinary uploads and the existing Slide-seq example keep their original
    inspection behavior. Replicates are never merged or assigned fake days.
    """
    if action_id != RIVER_VISIUM_EXAMPLE_ACTION_ID:
        return samples
    by_name = {sample["file_name"]: sample for sample in samples}
    expected = {f"{sample}_{group}_spatialmeta_qc0.h5ad" for sample, group in RIVER_VISIUM_SAMPLES}
    if len(samples) != len(expected) or set(by_name) != expected:
        raise ValueError("The Visium example does not match its published five-sample manifest.")
    return [
        dict(
            by_name[f"{sample}_{group}_spatialmeta_qc0.h5ad"],
            group=group,
            time_label=f"{group} ({sample})",
        )
        for sample, group in RIVER_VISIUM_SAMPLES
    ]


def river_st_module_ui():
    from spashiny.features.river.ui import river_st_module_ui as _entry

    return _entry()


def river_st_module_server(
    input,
    output,
    session,
    *,
    session_record_provider,
    analysis_session_id_provider,
    result_links_builder,
    result_previews_builder,
):
    from spashiny.features.river.server import river_st_module_server as _entry

    return _entry(
        input,
        output,
        session,
        session_record_provider=session_record_provider,
        analysis_session_id_provider=analysis_session_id_provider,
        result_links_builder=result_links_builder,
        result_previews_builder=result_previews_builder,
    )
