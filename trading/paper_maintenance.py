"""Account-scoped, resumable sequential PAPER/LIVE maintenance, never orders."""
from __future__ import annotations
import json
import os
from pathlib import Path
import threading
import time
from filelock import FileLock,Timeout
from .exchanges.venue_capabilities import CRYPTO_VENUES,STOCK_VENUES


class MaintenanceQueue:
    def __init__(self,folder,runner):
        self.path=Path(folder)/'reconciliation_jobs.json'
        self.runner=runner
        self.lock=threading.RLock()
        self.cancelled=threading.Event()
        self.thread=None
        self.state={'state':'idle','mode':'paper','items':[],'orders_submitted':False}
        if self.path.exists():
            try:
                if self.path.stat().st_size>128*1024:raise ValueError('queue_status_limit')
                state=json.loads(self.path.read_text(encoding='utf-8'))
                if state.get('state') in {'running','queued'}:state['state']='interrupted'
                self.state=state
            except (ValueError,OSError):self.state['state']='status_unavailable'

    def status(self):
        with self.lock:return json.loads(json.dumps(self.state))

    def _save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.tmp')
        with tmp.open('w',encoding='utf-8') as out:
            json.dump(self.state,out,ensure_ascii=False,allow_nan=False);out.flush();os.fsync(out.fileno())
        try:os.chmod(tmp,0o600)
        except OSError:pass
        os.replace(tmp,self.path)

    def start(self,sources,mode,*,resume=False):
        allowed=set(CRYPTO_VENUES) if mode=='paper' else set(CRYPTO_VENUES)|set(STOCK_VENUES)
        if mode not in {'paper','live'} or not isinstance(sources,list) or not 1<=len(sources)<=11 or any(not isinstance(s,str) or s not in allowed for s in sources) or len(set(sources))!=len(sources):
            raise ValueError('invalid_reconciliation_request')
        with self.lock:
            if self.thread is not None and self.thread.is_alive():raise RuntimeError('recovery_already_running')
            if resume and (self.state.get('state') not in {'paused','interrupted','needs_evidence'}
                           or self.state.get('mode')!=mode
                           or [row.get('source') for row in self.state.get('items',[])]!=sources):
                raise ValueError('invalid_reconciliation_request')
            lease=FileLock(str(self.path)+'.lock',timeout=0,thread_local=False)
            try:lease.acquire()
            except Timeout as exc:raise RuntimeError('recovery_already_running') from exc
            self.cancelled.clear()
            previous=self.state if resume and self.state.get('mode')==mode else {}
            done={row['source']:row for row in previous.get('items',[]) if row.get('state')=='checked'}
            self.state={'state':'running','mode':mode,'items':[done.get(s,{'source':s,'state':'queued','reason':''}) for s in sources],
                        'started_at':time.time(),'updated_at':time.time(),'orders_submitted':False,'trading_started':False}
            try:
                self._save()
                self.thread=threading.Thread(target=self._run,args=(lease,),daemon=True,name='paper-live-reconciliation')
                self.thread.start()
            except Exception:lease.release();raise
            return self.status()

    def cancel(self):
        self.cancelled.set()
        with self.lock:return self.status()

    def progress(self,source,values):
        with self.lock:
            row=next((r for r in self.state['items'] if r['source']==source),None)
            if row is not None:row.update({k:v for k,v in values.items() if k in {'processed_bytes','total_bytes','phase'}})

    def _run(self,lease):
        try:
            for row in self.state['items']:
                if self.cancelled.is_set():break
                if row['state']=='checked':continue
                with self.lock:row['state']='running';self._save()
                try:
                    result=self.runner(row['source'],self.state['mode'],self.cancelled,lambda value:self.progress(row['source'],value))
                    with self.lock:row.update(result)
                except Exception as exc:
                    reason=str(exc)
                    # Only finite local error codes, never provider/server messages.
                    safe=reason if reason.startswith(('paper_','recovery_','invalid_reconciliation')) and len(reason)<90 and all(c.isalnum() or c=='_' for c in reason) else 'recovery_check_failed'
                    with self.lock:row.update(state='needs_evidence',reason=safe)
                with self.lock:self.state['updated_at']=time.time();self._save()
            with self.lock:
                self.state['state']='paused' if self.cancelled.is_set() else 'needs_evidence' if any(r['state']!='checked' for r in self.state['items']) else 'checked'
                self._save()
        finally:lease.release()


def reconcile_paper_files(folder,cancel,progress):
    """Warm/verify derived index; never trims, resets or rewrites the journal."""
    from .paper_ledger_index import index_for
    ledger=Path(folder)/'strategy_paper_outcomes.jsonl'
    index=index_for(ledger)
    index.sync(cancel=cancel,progress=progress)
    return index
