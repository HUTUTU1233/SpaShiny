"""Session-scoped enrichment previews/downloads; no analysis or plot regeneration."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path


DOWNLOADS = (
    ('dotplot.pdf', 'Download Dot Plot PDF', 'application/pdf', 'btn-primary'),
    ('barplot.pdf', 'Download Bar Plot PDF', 'application/pdf', 'btn-primary'),
    ('enrichment_results.csv', 'Download Results CSV', 'text/csv', 'btn-outline-primary'),
    ('mapping_results.csv', 'Download Mapping CSV', 'text/csv', 'btn-outline-primary'),
    ('enrichment_summary.json', 'Download Summary JSON', 'application/json', 'btn-outline-secondary'),
    ('dotplot.png', 'Download Dot Plot PNG', 'image/png', 'btn-outline-success'),
    ('barplot.png', 'Download Bar Plot PNG', 'image/png', 'btn-outline-success'),
    ('results.zip', 'Download Result ZIP', 'application/zip', 'btn-success'),
    ('result_manifest.json', 'Download Manifest JSON', 'application/json', 'btn-outline-secondary'),
)
ARTIFACTS = frozenset(item[0] for item in DOWNLOADS)
WORKFLOWS = frozenset({'gene_enrichment', 'metabolite_enrichment', 'enrichment_analysis'})
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_PREVIEW_BYTES = 12 * 1024 * 1024
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024


def download_id(kind, relative):
    if kind not in {'gene', 'metabolite'} or relative not in ARTIFACTS:
        raise ValueError('Unknown enrichment download.')
    return f'download_{kind}_enrichment_{relative.replace(".", "_")}'


def read_artifact(*, owner, analysis, job_id, relative, expected_workflow=None,
                  database=None, config=None):
    """Authorize the exact tab/job and validate the immutable worker artifact.

    Browser-global analysis cookies are intentionally not a source of identity.
    The Shiny session supplies owner/analysis; no public endpoint is weakened.
    """
    if relative not in ARTIFACTS:
        raise ValueError('Unknown enrichment artifact.')
    if not all(isinstance(value, str) and value.strip() for value in (owner, analysis, job_id)):
        raise ValueError('The current owner, analysis and enrichment job are required.')
    if database is None:
        from cloud.database import CloudDatabase
        database = CloudDatabase(read_only=True)
    record = database.get_analysis_session(analysis, owner_session_id=owner)
    if str(record.get('status') or '').upper() != 'ACTIVE':
        raise ValueError('This analysis has ended.')
    job = database.get_job(job_id, session_id=owner, analysis_session_id=analysis)
    workflow = str(getattr(job, 'workflow', '') or getattr(job, 'workflow_name', ''))
    if (str(job.job_id) != job_id or str(job.session_id) != owner
            or str(job.analysis_session_id) != analysis or workflow not in WORKFLOWS
            or (expected_workflow is not None and workflow != expected_workflow)):
        raise ValueError('The enrichment artifact does not belong to this analysis and workflow.')
    if str(job.status).upper() not in {'SUCCEEDED', 'COMPLETED'}:
        raise ValueError('The current enrichment job has not completed successfully.')
    if not str(job.local_workspace or '').strip():
        raise ValueError('The enrichment result workspace is unavailable.')
    if config is None:
        from cloud.config import load_cloud_config
        config = load_cloud_config(require_storage=False)
    root = Path(job.local_workspace).resolve()
    managed = Path(config.lab_result_root).resolve()
    if managed not in root.parents:
        raise ValueError('The enrichment result is outside the managed results directory.')
    manifest_path = (root / 'result_manifest.json').resolve()
    if (root not in manifest_path.parents or not manifest_path.is_file()
            or not 0 < manifest_path.stat().st_size <= MAX_MANIFEST_BYTES):
        raise ValueError('The enrichment result manifest is missing or invalid.')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if (not isinstance(manifest, dict) or manifest.get('job_id') != job_id
            or manifest.get('session_id') != owner
            or manifest.get('analysis_session_id') not in (None, '', analysis)
            or not isinstance(manifest.get('files'), list)):
        raise ValueError('The enrichment result manifest identity is invalid.')
    # A manifest cannot truthfully contain its own final SHA256. Its identity
    # and bounded, contained path are checked above, not a self-referential hash.
    if relative == 'result_manifest.json':
        return manifest_path
    entries = []
    for item in manifest['files']:
        if not isinstance(item, dict):
            raise ValueError('The enrichment manifest contains an invalid entry.')
        aliases = [item[key] for key in ('path', 'relative_path') if key in item]
        if len(aliases) == 2 and aliases[0] != aliases[1]:
            raise ValueError('The enrichment manifest contains conflicting artifact paths.')
        if aliases and aliases[0] == relative:
            entries.append(item)
    target = (root / relative).resolve()
    if len(entries) != 1 or root not in target.parents or not target.is_file():
        raise ValueError('The exact enrichment artifact is missing or not uniquely registered.')
    size = target.stat().st_size
    sizes = [entries[0][key] for key in ('size', 'size_bytes') if key in entries[0]]
    if (not sizes or not 0 < size <= MAX_ARTIFACT_BYTES
            or any(type(value) is not int or value != size for value in sizes)):
        raise ValueError('The enrichment artifact size validation failed.')
    if target.suffix == '.png' and size > MAX_PREVIEW_BYTES:
        raise ValueError('The enrichment preview exceeds the safe preview size.')
    digest = hashlib.sha256()
    with target.open('rb') as handle:
        header = handle.read(8)
        digest.update(header)
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != str(entries[0].get('sha256') or '').lower():
        raise ValueError('The enrichment artifact failed SHA256 validation.')
    if target.suffix == '.png' and header != b'\x89PNG\r\n\x1a\n':
        raise ValueError('The enrichment preview is not a PNG file.')
    if target.suffix == '.pdf' and not header.startswith(b'%PDF-'):
        raise ValueError('The enrichment download is not a PDF file.')
    return target


def artifact_ui(*, owner, analysis, job, kind, database=None, config=None):
    """Verified PNG over Shiny plus real PDF downloads, no HTTP image fetch."""
    from shiny import ui
    cards, errors, paths = [], [], {}
    for relative, _label, _media, _css in DOWNLOADS:
        try:
            paths[relative] = read_artifact(owner=owner, analysis=analysis, job_id=str(job.job_id),
                relative=relative, expected_workflow=f'{kind}_enrichment', database=database, config=config)
        except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
            errors.append(f'{relative}: {exc}')
    for stem, label in (('dotplot', 'Dot Plot'), ('barplot', 'Bar Plot')):
        path = paths.get(stem+'.png')
        if path is not None:
            cards.append(ui.div(ui.h5(label), ui.tags.img(
                src='data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode('ascii'),
                alt=f'{kind.title()} enrichment {label.lower()}',
                style='display:block;max-width:100%;height:auto;border:1px solid #e5e5ea;border-radius:8px;'),
                class_='apple-card'))
    buttons = [ui.download_button(download_id(kind,relative), label, class_=css,
                                  style='margin:4px 6px 4px 0;')
               for relative,label,_media,css in DOWNLOADS if relative in paths]
    items = [ui.div(*cards, class_='cloud-list'), ui.div(*buttons, class_='cloud-result-downloads')]
    if errors:
        items.append(ui.div('Some result artifacts could not be verified: '+'; '.join(errors),
                            class_='alert alert-warning', role='alert'))
    if not cards:
        items.append(ui.div('No verified preview is available for this job.', class_='cloud-muted'))
    items.append(ui.div('PDF downloads use the original vector figure; PNG is for preview.', class_='cloud-muted'))
    return items


def register_downloads(output, *, owner_provider, analysis_provider, job_providers):
    """Register per-session Shiny download handlers; never choose a historical job."""
    from shiny import render

    def register_one(kind, relative, media_type):
        def download():
            job_id = str(job_providers[kind]() or '')
            path = read_artifact(owner=str(owner_provider() or ''), analysis=str(analysis_provider() or ''),
                                 job_id=job_id, relative=relative, expected_workflow=f'{kind}_enrichment')
            with path.open('rb') as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    yield chunk
        identifier = download_id(kind, relative)
        download.__name__ = identifier
        renderer = render.download(filename=f'{kind}_enrichment_{relative}', media_type=media_type)(download)
        output(id=identifier)(renderer)

    for kind in ('gene', 'metabolite'):
        if kind not in job_providers:
            raise ValueError('Both enrichment job providers are required.')
        for relative, _label, media_type, _css in DOWNLOADS:
            register_one(kind, relative, media_type)
