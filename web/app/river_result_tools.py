"""Read and plot completed River artifacts only; never train or request uploads."""
from __future__ import annotations

import base64
import csv
import io
import math
import importlib.metadata
import json
from pathlib import Path
from threading import RLock

from cloud.river_options import positive_integer, validate_plot_options
_PLOT_LOCK = RLock()


def artifact_path(job, name):
    raw = str(getattr(job, 'local_workspace', '') or '').strip()
    if not raw or Path(name).name != name:
        raise ValueError('The completed River result workspace is unavailable.')
    root = Path(raw).resolve()
    path = (root / name).resolve()
    if root not in path.parents or not path.is_file():
        raise ValueError(f'The completed result does not contain {name}.')
    return path


def read_ranking(job, limit=None):
    limit = None if limit is None else positive_integer(limit, name='Top N')
    path = artifact_path(job, 'river_final_rank_temporal.csv')
    result = []
    with path.open('r', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        keys = {str(k or '').strip().casefold(): k for k in reader.fieldnames or []}
        key = next((keys[k] for k in ('feature', 'gene', 'genes') if k in keys), None)
        if key is None:raise ValueError('The saved River ranking has no gene column.')
        for item in reader:
            gene = str(item.get(key) or '').strip()
            if gene:
                result.append({'Rank': len(result)+1, 'Gene': gene})
                if limit is not None and len(result) >= limit:break
    return result


def saved_result_context(job):
    import anndata as ad
    path = artifact_path(job, 'river_plot_adata.h5ad')
    data = ad.read_h5ad(path, backed='r')
    try:
        cache=dict(data.uns.get('river_plot_cache',{}))
        if cache.get('job_id') and str(cache['job_id'])!=str(job.job_id):
            raise ValueError('Saved plot cache belongs to a different job; refusing stale results.')
        if 'spatial' not in data.obsm:
            raise ValueError('This saved River result has no spatial coordinates.')
        if 'river_panel' not in data.obs or 'river_panel_index' not in data.obs:
            raise ValueError('This saved River result lacks sample-panel metadata.')
        available = set(map(str, data.var_names))
        ranked = read_ranking(job)
        genes = list(dict.fromkeys([r['Gene'] for r in ranked if r['Gene'] in available] + list(map(str, data.var_names))))
        panels = data.obs[['river_panel_index', 'river_panel']].astype(str).drop_duplicates()
        panel_count = len(panels)
        if not genes or panel_count < 2:raise ValueError('The saved River plotting artifact is incomplete.')
        record={}
        try:
            summary=json.loads(artifact_path(job,'river_summary.json').read_text(encoding='utf-8'))
            record={key:summary.get(key) for key in ('execution_contract_version','input_profile','execution_mode','runtime_versions','method_version','wall_time_seconds')}
        except (OSError,ValueError):pass
        return {'job_id': str(job.job_id), 'genes': genes, 'sample_count': panel_count,'execution_record':record,
                'analysis_mode':data.uns.get('river_plot_cache',{}).get('analysis_mode','legacy_unrecorded'),
                'rank_count':len(ranked), 'cached_gene_count':len(genes),
                'partial_legacy_cache':len(available) < len({r['Gene'] for r in ranked})}
    finally:data.file.close()


def render_saved_gene(job, gene, options=None):
    with _PLOT_LOCK:
        return _render_saved_gene(job, gene, options)


def _render_saved_gene(job, gene, options=None):
    import anndata as ad
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    import scanpy as sc
    from scipy import sparse
    from cloud.figure_export import save_native_figure

    data = ad.read_h5ad(artifact_path(job, 'river_plot_adata.h5ad'), backed='r')
    try:
        gene = str(gene or '').strip()
        if gene not in data.var_names:
            raise ValueError('Choose a gene available in this completed result. No new upload is needed.')
        values = data[:, [gene]].X
        if sparse.issparse(values):values=values.toarray()
        values = np.asarray(values,dtype=float).reshape(-1)
        coordinates = np.asarray(data.obsm['spatial'],dtype=float)[:, :2]
        obs = data.obs[['river_panel_index','river_panel']].copy()
        cache=dict(data.uns.get('river_plot_cache',{}))
        if cache.get('job_id') and str(cache['job_id'])!=str(job.job_id):
            raise ValueError('Saved plot cache job identity mismatch.')
    finally:data.file.close()
    if not np.isfinite(values).all() or not np.isfinite(coordinates).all():
        raise ValueError('The saved result contains non-finite expression or spatial coordinates.')
    # Values are already normalized by the original River pipeline: never log,
    # normalize, resample or rerun matching/model training during redraw.
    panels = sorted(obs['river_panel_index'].astype(str).unique(),key=lambda value:int(value))
    settings = validate_plot_options(options,sample_count=len(panels))
    if settings['cmap']=='Balance_20':
        from palettable.cmocean.diverging import Balance_20
        cmap=Balance_20.mpl_colormap
    else:cmap=plt.get_cmap(settings['cmap'])
    low=float(values.min()) if settings['automatic_norm'] else settings['vmin']
    high=float(values.max()) if settings['automatic_norm'] else settings['vmax']
    norm=plt.Normalize(low,high)
    ncols=settings['ncols'];nrows=math.ceil(len(panels)/ncols)
    fig,axes=plt.subplots(nrows,ncols,figsize=(settings['width'],settings['height']),squeeze=False)
    try:
        try:import squidpy as sq
        except ImportError:sq=None
        for index,panel in enumerate(panels):
            mask=obs['river_panel_index'].astype(str).to_numpy()==panel
            sample=ad.AnnData(X=values[mask,None],obsm={'spatial':coordinates[mask]})
            sample.var_names=[gene]
            ax=axes.ravel()[index]
            if sq is not None:
                sq.pl.spatial_scatter(sample,shape=None,color=[gene],ncols=1,size=settings['size'],
                    colorbar=False,return_ax=True,cmap=cmap,norm=norm,show=False,ax=ax)
            else:
                sc.pl.embedding(sample,basis='spatial',color=[gene],size=settings['size'],
                    colorbar_loc=None,cmap=cmap,norm=norm,frameon=False,show=False,ax=ax,return_fig=False)
            label=str(obs.loc[mask,'river_panel'].iloc[0])
            ax.set_title(label,fontsize=10);ax.set_aspect('equal',adjustable='box');ax.set_box_aspect(1)
            ax.set_xticks([]);ax.set_yticks([]);ax.set_xlabel('');ax.set_ylabel('')
            for collection in ax.collections:collection.set_rasterized(False)
        for ax in axes.ravel()[len(panels):]:ax.set_visible(False)
        fig.suptitle('River spatial expression: '+gene)
        fig.subplots_adjust(top=0.86,bottom=0.10,left=0.03,right=0.88 if settings['colorbar'] else 0.98,hspace=0.32,wspace=0.15)
        if settings['colorbar']:
            # Reserve an independent axes after positioning the sample panels;
            # otherwise subplots_adjust can move a panel under its color bar.
            color_axes=fig.add_axes([0.92,0.18,0.015,0.60])
            bar=fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),cax=color_axes,label='Expression')
            if bar.solids is not None:bar.solids.set_edgecolor('face')
        png=io.BytesIO();pdf=io.BytesIO()
        fig.savefig(png,format='png',dpi=140)
        save_native_figure(fig,pdf,format='pdf',bbox_inches=None)
        return {'gene':gene,'job_id':str(job.job_id),'settings':settings,'value_min':float(values.min()),'value_max':float(values.max()),
            'renderer':'squidpy.pl.spatial_scatter' if sq is not None else 'scanpy.pl.embedding',
            'renderer_version':importlib.metadata.version('squidpy' if sq is not None else 'scanpy'),
            'renderer_fallback':sq is None,'normalization_repeated':False,
            'png':'data:image/png;base64,'+base64.b64encode(png.getvalue()).decode('ascii'),
            'pdf':'data:application/pdf;base64,'+base64.b64encode(pdf.getvalue()).decode('ascii')}
    finally:plt.close(fig)
