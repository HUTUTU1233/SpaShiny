# Original feature imports, constants and direct helper functions; no duplicate UI/server bodies.
from __future__ import annotations
from pathlib import Path as _ExportPath

LEGACY_ENTRYPOINT_FILE = str(_ExportPath(__file__).resolve().parents[3] / "sm_tic_roi_module.py")
"Analysis-scoped imzML TIC/ROI UI; spectral work stays in CPU jobs."
import json
from pathlib import Path
from shiny import reactive, render, ui

WORKFLOWS = {"sm_tic_preview", "sm_roi_export", "sm_pos_neg_merge"}


def validate_uploads(database, owner_id, analysis_id, upload_ids):
    if not owner_id or not analysis_id:
        raise ValueError("The current analysis is not ready. Wait for the live session connection.")
    if (
        not isinstance(upload_ids, (list, tuple))
        or not 2 <= len(upload_ids) <= 16
        or any((not isinstance(v, str) or not v for v in upload_ids))
        or (len(set(upload_ids)) != len(upload_ids))
    ):
        raise ValueError("Select 1–8 complete imzML/IBD pairs.")
    names = {}
    for upload_id in upload_ids:
        upload = database.get_upload(
            str(upload_id), session_id=owner_id, analysis_session_id=analysis_id
        )
        if upload.status != "COMPLETED":
            raise ValueError("Wait until every file upload has completed.")
        name = str(upload.safe_filename)
        suffix = Path(name).suffix.casefold()
        if suffix not in {".imzml", ".ibd"}:
            raise ValueError("Only .imzML and .ibd files are accepted.")
        key = Path(name).stem.casefold()
        pair = names.setdefault(key, set())
        if suffix in pair:
            raise ValueError(f"Duplicate file: {name}")
        pair.add(suffix)
    if any((pair != {".imzml", ".ibd"} for pair in names.values())):
        raise ValueError("Each imzML requires an IBD with the same filename stem.")
    return list(upload_ids)


def validate_selection(preview, payload):
    supplied = payload.get("selections")
    datasets = preview.get("datasets") or []
    if not isinstance(supplied, dict) or set(supplied) != {d["id"] for d in datasets}:
        raise ValueError("ROI selection does not match the current TIC preview.")
    result = {}
    for dataset in datasets:
        value = supplied[dataset["id"]]
        if (
            not isinstance(value, dict)
            or type(value.get("z")) not in (int, float)
            or value.get("z") not in dataset["z_values"]
        ):
            raise ValueError("Choose a valid z plane for each dataset.")
        ids = value.get("pixel_ids")
        valid_ids = {p["pixel_id"] for p in dataset["pixels"] if p["z"] == value["z"]}
        if (
            not isinstance(ids, (list, tuple))
            or len(ids) > len(valid_ids)
            or any((type(v) is not int or v not in valid_ids for v in ids))
            or (len(ids) != len(set(ids)))
        ):
            raise ValueError("ROI contains invalid pixels or pixels from another z plane.")
        result[dataset["id"]] = {
            "z": value["z"],
            "pixel_ids": list(ids),
            "source_sha256": dataset["source_sha256"],
        }
    return result


def validate_csv_uploads(database, owner_id, analysis_id, roles):
    if not owner_id or not analysis_id:
        raise ValueError("The current tab analysis is not ready.")
    if not isinstance(roles, dict) or set(roles) != {"pos", "neg"}:
        raise ValueError("Upload one POS and one NEG spectrum CSV using their labeled controls.")
    ids = [roles["pos"], roles["neg"]]
    if any((not isinstance(v, str) or not v for v in ids)) or ids[0] == ids[1]:
        raise ValueError("POS and NEG must be different completed uploads.")
    names = {}
    for role, upload_id in zip(("pos", "neg"), ids):
        upload = database.get_upload(
            upload_id, session_id=owner_id, analysis_session_id=analysis_id
        )
        name = str(upload.safe_filename)
        if (
            upload.status != "COMPLETED"
            or Path(name).suffix.casefold() != ".csv"
            or Path(name).name != name
            or ("\\" in name)
        ):
            raise ValueError(
                "Wait for both spectrum CSV uploads to complete. Only .csv is accepted."
            )
        names[role + "_filename"] = name
    if names["pos_filename"] == names["neg_filename"]:
        raise ValueError("Give POS and NEG different filenames before upload.")
    return (ids, names)


def sm_tic_roi_module_ui():
    from spashiny.features.sm_tic_roi.ui import sm_tic_roi_module_ui as _entry

    return _entry()


def sm_tic_roi_module_server(
    input,
    output,
    session,
    *,
    session_record_provider,
    analysis_session_id_provider,
    result_json_reader,
    download_url_builder,
):
    from spashiny.features.sm_tic_roi.server import sm_tic_roi_module_server as _entry

    return _entry(
        input,
        output,
        session,
        session_record_provider=session_record_provider,
        analysis_session_id_provider=analysis_session_id_provider,
        result_json_reader=result_json_reader,
        download_url_builder=download_url_builder,
    )
