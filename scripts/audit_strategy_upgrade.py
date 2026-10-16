#!/usr/bin/env python3
"""Explicit, offline strategy-copy audit. Aggregate output contains no strategy text/IDs.

Never pass original stores to runtime loaders (which may reconcile/chmod files).
No account settings, keys, order/ledger data or provider clients are loaded.
"""
import argparse
from collections import Counter
import contextlib
from copy import deepcopy
import hashlib
import io
import json
import logging
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def worker(root, stores):
    sys.path.insert(0,str(root))
    logging.disable(logging.CRITICAL)
    scratch=Path(stores)/'.isolated-app-data';scratch.mkdir(exist_ok=True)
    import path_utils
    path_utils.get_app_data_dir=lambda:str(scratch)
    path_utils.get_config_dir=lambda:str(scratch/'config')
    path_utils.get_log_dir=lambda:str(scratch/'logs')
    for name in ['config','logs']:(scratch/name).mkdir(exist_ok=True)
    network=[]
    def blocked(*args,**kwargs):
        network.append('blocked');raise OSError('offline_strategy_audit')
    socket.socket.connect=blocked
    from trading.custom_strategy_pipeline import CustomStrategyPipeline
    from trading.strategy_source_ingestor import StrategySourceIngestor, ExtractedStrategySource
    from web_platform.application_services import ApplicationServices
    rows=[];counts=Counter();reasons=Counter();reanalysis_reasons=Counter();maps=[]
    service=ApplicationServices.__new__(ApplicationServices)
    for source in sorted(Path(stores).glob('*_private.json')):
        original=json.loads(source.read_text(encoding='utf-8-sig'))
        pipeline=CustomStrategyPipeline(storage_path=source)
        maps.append(digest({'active':pipeline.active_versions,'paper':pipeline.paper_versions}))
        for key, versions in original.get('strategies',{}).items():
            for old in versions:
                loaded=pipeline.get_version(key,old['version_id'])
                counts['versions']+=1
                # Lifecycle maps may reconcile stale descriptive status in both versions;
                # intent, grants, source, approval and all historical evidence must survive.
                before=deepcopy(old);after=deepcopy(loaded)
                before.pop('status',None);after.pop('status',None)
                preserved=digest(before)==digest(after)
                counts['all_nonstatus_fields_preserved']+=int(preserved)
                ready=pipeline.paper_execution_readiness(loaded)
                final=service.validate_strategy_draft(rules=loaded.get('rules') or {})
                counts['stored_paper_ready']+=int(ready['ready'])
                counts['stored_final_draft_ready']+=int(final['ready'])
                reasons.update(str(code).split(':',1)[0] for code in final.get('reasons',[]))
                source_data=(loaded.get('rules') or {}).get('source_evidence') or {}
                text=source_data.get('text') or ''
                recompiled=None
                if text:
                    counts['recorded_source_texts']+=1
                    extracted=ExtractedStrategySource(kind='pine' if source_data.get('kind')=='pine' else 'text',
                        reference='private-copy',title='private-copy',text=text,warnings=[],evidence={})
                    result=StrategySourceIngestor().analyze('',kind='text',extracted_source=extracted)
                    counts['reanalyzed_source_ready']+=int(result['ready_for_execution'])
                    if not result['ready_for_execution']:
                        reanalysis_reasons.update(str(code).split(':',1)[0] for code in result.get('missing_conditions',[]))
                    recompiled={'ready':result['ready_for_execution'],
                        'missing_codes':sorted(set(str(c).split(':',1)[0] for c in result.get('missing_conditions',[]))),
                        'execution_digest':StrategySourceIngestor._execution_contract_digest(result['rules'])}
                rows.append({'stored_preserved':preserved,'loaded_digest':digest(loaded),
                    'stored_ready':bool(ready['ready']),'final_ready':bool(final['ready']),
                    'grounding_valid':bool(final.get('source_grounding',{}).get('valid')),
                    'recompiled':recompiled})
        counts['stores']+=1
        counts['active_grants']+=len(pipeline.active_versions)
        counts['paper_grants']+=len(pipeline.paper_versions)
    for key in ['versions','all_nonstatus_fields_preserved','stored_paper_ready','stored_final_draft_ready','recorded_source_texts','reanalyzed_source_ready','active_grants','paper_grants']:
        counts.setdefault(key,0)
    return {'counts':dict(counts),'reasons':dict(reasons),'reanalysis_reasons':dict(reanalysis_reasons),'rows':rows,'maps':maps,'network_attempts':len(network)}


def run(stores,baseline_root=None):
    folder=Path(stores)
    files=sorted(folder.glob('*_private.json'))
    if not files:raise ValueError('no_strategy_stores')
    if any(path.is_symlink() for path in files):raise ValueError('symlink_store_not_allowed')
    identities={path:(hashlib.sha256(path.read_bytes()).hexdigest(),path.stat().st_mtime_ns,path.stat().st_mode) for path in files}
    def execute(code_root,copy_root):
        copy_root.mkdir()
        for path in files:shutil.copy2(path,copy_root/path.name)
        process=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',str(code_root),str(copy_root)],
                               capture_output=True,text=True,encoding='utf-8')
        if process.returncode:raise RuntimeError('isolated_audit_worker_failed')
        return json.loads(process.stdout)
    with tempfile.TemporaryDirectory(prefix='noah-strategy-upgrade-') as directory:
        temp=Path(directory)
        current=execute(ROOT,temp/'candidate')
        baseline=execute(Path(baseline_root),temp/'baseline') if baseline_root else None
    unchanged=all(identities[path]==(hashlib.sha256(path.read_bytes()).hexdigest(),path.stat().st_mtime_ns,path.stat().st_mode) for path in files)
    result={'status':'PASS','scope':'offline temporary copies; no customer source/IDs/keys/settings/ledger output; no orders or provider calls',
            'counts':current['counts'],'original_bytes_mtime_permissions_unchanged':unchanged,
            'current_stored_blocking_code_counts':current['reasons'],'source_reanalysis_blocking_code_counts':current['reanalysis_reasons'],'network_attempts':current['network_attempts']}
    if baseline:
        assert len(current['rows'])==len(baseline['rows'])
        transitions=Counter();changes=Counter()
        for old,new in zip(baseline['rows'],current['rows']):
            transitions[f"{int(old['final_ready'])}->{int(new['final_ready'])}"]+=1
            for field in ['loaded_digest','stored_ready','final_ready','grounding_valid']:
                changes[field]+=int(old[field]!=new[field])
            if old['recompiled'] is not None and new['recompiled'] is not None:
                changes['source_reanalysis_readiness']+=int(old['recompiled']['ready']!=new['recompiled']['ready'])
                changes['source_reanalysis_execution']+=int(old['recompiled']['execution_digest']!=new['recompiled']['execution_digest'])
        result.update(baseline_counts=baseline['counts'],stored_readiness_transitions=dict(transitions),
                      differences=dict(changes),execution_grants_equal=current['maps']==baseline['maps'])
        if any(changes[k] for k in ['loaded_digest','stored_ready','final_ready','grounding_valid']) or current['maps']!=baseline['maps']:
            result['status']='REGRESSION_REVIEW_REQUIRED'
    if not unchanged or current['network_attempts'] or current['counts']['all_nonstatus_fields_preserved']!=current['counts']['versions']:
        result['status']='FAIL'
    return result


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--worker':
        # Prevent application/module debug messages or private tracebacks from reaching callers.
        try:
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                result=worker(Path(sys.argv[2]),Path(sys.argv[3]))
            print(json.dumps(result,ensure_ascii=False));return
        except Exception:
            print('{"error":"isolated_worker_failed"}');raise SystemExit(1)
    parser=argparse.ArgumentParser();parser.add_argument('--stores',required=True,type=Path)
    parser.add_argument('--baseline-root',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.output and args.output.resolve().is_relative_to(args.stores.resolve()):
        parser.error('audit output must be outside the source store directory')
    result=run(args.stores,args.baseline_root)
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text,encoding='utf-8')
    print(text);raise SystemExit(0 if result['status']=='PASS' else 1)
if __name__=='__main__':main()
