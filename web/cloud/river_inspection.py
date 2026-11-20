"""Bounded disposable input inspection. No database, job submission or training."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import zipfile

from .river_input_contract import validated_zip_members, extract_checked_member, validate_spatial, annotation_frame
from .river_trusted_inputs import FILES, recognize_hashes
from .river_scale_evidence import inspect_h5ad_contract, package_manifest

INSPECTION_TIMEOUT_SECONDS = 600
_SLOTS = asyncio.Semaphore(2)


def entry_signature(entries):
    result=[]
    for item in entries:
        path=Path(str(item.get('datapath') or ''))
        stat=path.stat() if path.is_file() else None
        result.append((str(item.get('name') or path.name),str(path),
                       stat.st_size if stat else -1,stat.st_mtime_ns if stat else -1))
    return tuple(result)


def request_entries(request):
    archive=request.get('archive')
    return ([archive] if archive else list(request.get('data_files') or []))+list(request.get('csv_files') or [])


def _natural(value):
    return [int(x) if x.isdigit() else x.casefold() for x in re.split(r'(\d+)',str(value))]


def _inspect_h5ad(path, name, declaration=None):
    import anndata as ad
    contract=inspect_h5ad_contract(path,name,package_declaration=declaration)
    data=ad.read_h5ad(path,backed='r')
    try:
        spatial=validate_spatial(data,sample=name)
        if data.n_vars<3 or not data.obs_names.is_unique:
            raise ValueError(f'{name}: at least three genes and unique spot barcodes are required.')
        columns=[];values={};missing={}
        for key in data.obs:
            if str(key).casefold() in {'x','y','umi','spatial','pxl_col_in_fullres','pxl_row_in_fullres','array_col','array_row'}:
                continue
            series=data.obs[key].astype('string')
            categories=list(map(str,series.dropna().unique()))
            if 0<len(categories)<=100:
                columns.append(str(key));values[str(key)]=categories;missing[str(key)]=int(series.isna().sum())
        content_sha=contract['file_sha256']
        return {'n_obs':int(data.n_obs),'n_vars':int(data.n_vars),'genes':list(map(str,data.var_names)),
                'content_sha256':content_sha,
                'scale_evidence':contract,
                'columns':columns,'values':values,'missing':missing,'spatial':spatial,
                'barcodes':data.obs_names.astype(str),'log1p_marker':'log1p' in data.uns}
    finally:data.file.close()


def inspect_request(request, progress=lambda *_args:None):
    files=list(request.get('data_files') or [])
    csv_files=list(request.get('csv_files') or [])
    archive=request.get('archive')
    entries=request_entries(request)
    signature=entry_signature(entries)
    records=[]
    with tempfile.TemporaryDirectory(prefix='river_inspect_') as tmp:
        if archive:
            path=Path(archive['datapath'])
            with zipfile.ZipFile(path) as bundle:
                members=validated_zip_members(bundle)
                declarations=package_manifest(bundle)
                # CSV limits and all-member expansion were checked before any extraction.
                for info in members:
                    member=PurePosixPath(info.filename.replace('\\','/'))
                    if member.suffix.lower()=='.csv':
                        target=Path(tmp)/member.name
                        extract_checked_member(bundle,info,target)
                        csv_files.append({'name':member.name,'datapath':str(target)})
                data_members=sorted([x for x in members if x.filename.lower().endswith('.h5ad')],key=lambda x:_natural(PurePosixPath(x.filename).name))
                if set(declarations)-{PurePosixPath(x.filename.replace('\\','/')).name.casefold() for x in data_members}:
                    raise ValueError('The input manifest refers to samples missing from the package.')
                for i,info in enumerate(data_members):
                    member=PurePosixPath(info.filename.replace('\\','/'))
                    target=Path(tmp)/member.name
                    extract_checked_member(bundle,info,target)
                    progress(i,len(data_members),member.name)
                    records.append((str(member),_inspect_h5ad(target,member.name,declarations.get(member.name.casefold()))))
                    target.unlink()
        else:
            if not 2<=len(files)<=64:
                raise ValueError('Select 2–64 H5AD samples.')
            for i,item in enumerate(sorted(files,key=lambda x:_natural(x['name']))):
                progress(i,len(files),item['name'])
                records.append((item['name'],_inspect_h5ad(Path(item['datapath']),item['name'])))
        common_genes=None;common_columns=None;common_csv=None
        common_values={};csv_values={};samples=[];seen=set();csv_summaries=[]
        by_csv={}
        for item in csv_files:
            stem=Path(item['name']).stem.casefold()
            if stem in by_csv:raise ValueError('Duplicate annotation CSV sample names.')
            by_csv[stem]=item
        for member,record in records:
            name=PurePosixPath(member).name;stem=Path(name).stem
            if stem.casefold() in seen:raise ValueError(f'Duplicate sample stem: {stem}')
            seen.add(stem.casefold())
            genes=set(record['genes']);cols=set(record['columns'])
            common_genes=genes if common_genes is None else common_genes&genes
            common_columns=cols if common_columns is None else common_columns&cols
            for col,values in record['values'].items():common_values.setdefault(col,set()).update(values)
            csv_item=next((by_csv[x] for x in (stem.casefold(),stem.casefold()+'_annotation',stem.casefold()+'_annotations') if x in by_csv),None)
            csv_columns=set()
            if csv_item:
                frame=annotation_frame(csv_item['datapath'])
                indexed=frame.reindex(record['barcodes'])
                for col in frame:
                    values=list(map(str,frame[col].dropna().unique()))
                    if len(values)<=100:
                        csv_columns.add(str(col));csv_values.setdefault(str(col),set()).update(values)
                csv_summaries.append({'sample':stem,'matched_barcodes':int(record['barcodes'].isin(frame.index).sum()),
                    'total_barcodes':record['n_obs'],'missing_by_column':{str(c):int(indexed[c].isna().sum()) for c in csv_columns}})
            common_csv=csv_columns if common_csv is None else common_csv&csv_columns
            samples.append({'member':member,'file_name':name,'sample_id':stem,
                'content_sha256':record.get('content_sha256'),
                'scale_evidence':record['scale_evidence'],
                'key':hashlib.sha256(member.encode()).hexdigest()[:12],'n_obs':record['n_obs'],'n_vars':record['n_vars'],
                'spatial_check':record['spatial'],'annotation_missing':record['missing'],'log1p_marker':record['log1p_marker']})
    if len(common_genes or [])<3:raise ValueError('River samples must share at least three genes.')
    if entry_signature(entries)!=signature:raise ValueError('The selected input changed during inspection; inspect the current selection again.')
    return {'source_mode':'ZIP_ARCHIVE' if archive else 'DIRECT_H5AD',
        'example_action_id':str(archive.get('action_id') or '') if archive else '',
        'upload_entries':[archive] if archive else files,'csv_entries':list(request.get('csv_files') or []),
        'input_signature':signature,'samples':samples,'common_genes':sorted(common_genes,key=str.casefold),
        'common_obs_columns':sorted(common_columns or [],key=str.casefold),
        'common_obs_values':{c:sorted(common_values[c],key=str.casefold) for c in common_columns or []},
        'common_csv_columns':sorted(common_csv or [],key=str.casefold),
        'common_csv_values':{c:sorted(csv_values[c],key=str.casefold) for c in common_csv or []},
        'csv_match_summary':csv_summaries,'annotation_required':False,
        'trusted_input_manifest':recognize_hashes(s.get('content_sha256') for s in samples)}


async def inspect_async(request, progress=lambda *_args:None):
    if _SLOTS.locked():raise ValueError('River inspection is busy. Wait for a free inspection slot and retry.')
    async with _SLOTS:
        environment=os.environ.copy()
        environment.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',
                           PYTHONDONTWRITEBYTECODE='1',NUMBA_NUM_THREADS='1')
        proc=await asyncio.create_subprocess_exec(sys.executable,'-B','-m','cloud.river_inspection',
            cwd=str(Path(__file__).resolve().parents[1]),env=environment,
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,
            limit=32*1024**2)
        try:
            proc.stdin.write(json.dumps(request).encode());await proc.stdin.drain();proc.stdin.close()
            result=None
            async with asyncio.timeout(INSPECTION_TIMEOUT_SECONDS):
                while line:=await proc.stdout.readline():
                    event=json.loads(line)
                    if event['type']=='progress':progress(event['index'],event['count'],event['sample'])
                    elif event['type']=='error':raise ValueError(event['message'])
                    elif event['type']=='result':result=event['value']
                code=await proc.wait()
            if code or result is None:
                raise ValueError(f'River inspection failed (exit {code}); possible memory/CPU resource limit. No analysis was submitted.')
            return result
        except TimeoutError as exc:
            raise ValueError(f'River inspection exceeded {INSPECTION_TIMEOUT_SECONDS} seconds; no analysis was submitted.') from exc
        finally:
            if proc.returncode is None:
                proc.kill();await proc.wait()


def main():
    try:
        if sys.platform!='win32':
            import resource
            resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
            resource.setrlimit(resource.RLIMIT_CPU,(120,120))
            resource.setrlimit(resource.RLIMIT_NOFILE,(128,128))
        request=json.loads(sys.stdin.read(2*1024**2))
        def progress(index,count,sample):print(json.dumps({'type':'progress','index':index,'count':count,'sample':sample}),flush=True)
        result=inspect_request(request,progress)
        print(json.dumps({'type':'result','value':result}),flush=True)
    except Exception as exc:
        print(json.dumps({'type':'error','message':f'{type(exc).__name__}: {exc}'}),flush=True)
        raise SystemExit(1)


if __name__=='__main__':main()
