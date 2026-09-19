"""Account-local, opt-in outbound monitoring. Device tokens stay in memory."""
from __future__ import annotations
import json
import os
from pathlib import Path
import secrets
import hashlib
import threading
import time
import requests
from config.app_version import RELEASE_VERSION

PORTAL = 'https://daltrading.net'
VENUES = {'binance','bybit','okx','bitget','upbit','bithumb','coinone','kiwoom','kis','mirae','shinhan'}


def public_snapshot(runtime):
    enabled = list(dict.fromkeys(runtime.get('enabled_sources') or []))
    running = set(runtime.get('running_sources') or [])
    modes = runtime.get('execution_modes') or {}
    return {'version':RELEASE_VERSION,'sources':[
        {'source':source,'running':source in running,
         'mode':modes.get(source) if modes.get(source) in {'paper','live','learning'} else 'unknown'}
        for source in enabled if source in VENUES]}


class RemoteMonitor:
    def __init__(self, *, account, data_dir, snapshot, transport=None, control_context=None, control_execute=None):
        self.account=account; self.data_dir=Path(data_dir); self.snapshot=snapshot
        self.transport=transport or requests.Session()
        self.control_context = control_context
        self.control = None
        if control_context and control_execute:
            from web_platform.remote_control import RemoteControl
            self.control = RemoteControl(data_dir, self.approval_context, control_execute)
        self.control_acks = {}
        self.path=self.data_dir/'remote_monitor.json'
        self.lock=threading.RLock(); self.stop_event=threading.Event(); self.thread=None
        self.send_lock=threading.Lock();self.generation=0;self.pending={}
        self.token=''; self.sequence=0; self.last_sent=None; self.error=None
        self.config={'enabled':False,'allow_pause':False,'allow_control':False,'share_details':False,'approved':{},'approval_id':'','install_id':secrets.token_urlsafe(24),'name':'내 NoahAI PC'}
        try:
            saved=json.loads(self.path.read_text(encoding='utf-8'))
            if saved.get('account')==account:
                self.config.update({k:saved[k] for k in self.config if k in saved})
        except (OSError,ValueError,TypeError):
            pass

    def status(self):
        with self.lock:
            return {'enabled':bool(self.config['enabled']),'name':self.config['name'],
                    'last_sent':self.last_sent,'error':self.error,
                    'capabilities':['status','pause_entries'] if self.config['allow_pause'] else ['status'],
                    'portal_url':PORTAL+'/remote','heartbeat_seconds':60,'allow_pause':self.config['allow_pause'],
                    'allow_control':self.config['allow_control'],'share_details':self.config['share_details'],
                    'approved':self.config['approved'],
                    'entry_pauses':self.pause_states()}

    def approval_context(self, approval_id=None):
        context = dict(self.control_context())
        epoch = self.config['approval_id'] if approval_id is None else approval_id
        context['revision'] = hashlib.sha256((context['revision'] + epoch).encode()).hexdigest()
        return context

    def save(self):
        self.data_dir.mkdir(parents=True,exist_ok=True)
        temporary=self.path.with_suffix('.tmp')
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump({**self.config,'account':self.account},stream,ensure_ascii=False)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary,self.path)

    def configure(self,enabled,name,allow_pause=False,allow_control=False,share_details=False):
        if self.account=='local':
            raise ValueError('로그인 후 연결할 수 있습니다.')
        if not all(isinstance(v,bool) for v in (enabled,allow_pause,allow_control,share_details)) or not isinstance(name,str) or not 1<=len(name.strip())<=60:
            raise ValueError('PC 이름과 연결 설정을 확인하세요.')
        approved = {}
        approval_id = secrets.token_urlsafe(24)
        if enabled and allow_control:
            if not self.control_context: raise ValueError('remote_control_unavailable')
            context = self.approval_context(approval_id)
            approved = {row['source']:{'revision':context['revision'],'mode':row['mode']}
                        for row in context['sources'] if row['mode'] in ('paper','live')}
            if not approved: raise ValueError('paper_or_live_source_required')
        with self.lock:
            self.generation+=1
            if name.strip()!=self.config['name']:
                self.token=''
            self.config.update(enabled=enabled,name=name.strip(),allow_pause=allow_pause,allow_control=allow_control,share_details=share_details,approved=approved,approval_id=approval_id);self.error=None
            self.save()
            if not enabled:
                self.token=''
        if enabled:
            self.start()
        return self.status()

    def start(self):
        with self.lock:
            if os.environ.get('PYTEST_CURRENT_TEST') or self.stop_event.is_set() or not self.config['enabled']:
                return
            if self.thread is None or not self.thread.is_alive():
                self.thread=threading.Thread(target=self.run,daemon=True,name='noahai-remote-status')
                self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=9)

    def run(self):
        while not self.stop_event.is_set():
            self.tick()
            self.stop_event.wait(60)

    def pause_states(self):
        from trading.remote_entry_pause import gate
        state=gate(self.data_dir)
        return {source:state.state(source) for source in VENUES if state.state(source)['paused']}

    def tick(self):
        if not self.send_lock.acquire(blocking=False):return
        try:self._tick()
        finally:self.send_lock.release()

    def _tick(self):
        with self.lock:
            if not self.config['enabled'] or self.stop_event.is_set():return
            generation=self.generation;config=dict(self.config);token=self.token
        try:
            if not token:
                credentials=json.loads((self.data_dir/'token.json').read_text(encoding='utf-8'))
                info=credentials.get('user_info') or {}
                if str(info.get('id') or info.get('username') or '')!=self.account:
                    raise ValueError('account_mismatch')
                session=str(credentials.get('session_id') or info.get('session_id') or '')
                if not session or not credentials.get('access_token'):raise ValueError('desktop_login_required')
                response=self.transport.post(PORTAL+'/remote/device/register',
                    headers={'Authorization':'Bearer '+credentials['access_token']},
                    json={'install_id':config['install_id'],'name':config['name'],'session_id':session},
                    timeout=8,allow_redirects=False)
                self.check(response,generation)
                with self.lock:
                    if generation!=self.generation or self.stop_event.is_set():return
                    token=self.token=response.json()['device_token'];self.sequence=0
            from trading.remote_entry_pause import gate
            pauses=gate(self.data_dir)
            with self.lock:
                if generation!=self.generation or self.stop_event.is_set():return
                self.sequence+=1;sequence=self.sequence
                acks=[{'id':key,'status':'draining' if pauses.state(source)['in_flight'] else 'paused'} for key,source in self.pending.items()]
                acks += [{'id':key,'status':value} for key,value in self.control_acks.items()]
            snapshot=public_snapshot(self.snapshot());snapshot['allow_pause']=config['allow_pause']
            for row in snapshot['sources']:row['entry_pause']=pauses.state(row['source'])
            snapshot['protocol']=2
            if self.control_context:
                context=self.approval_context()
                for row in snapshot['sources']:
                    details=next((r for r in context['sources'] if r['source']==row['source']),{})
                    row['mode']=details.get('mode',row['mode'])
                    row['control_ready']=bool(config['allow_control'] and config['approved'].get(row['source']) == {'revision':context['revision'],'mode':row['mode']})
                    row['revision']=context['revision'] if row['control_ready'] else ''
                    if config['share_details']:row['details']=details.get('details',{})
            snapshot['allow_control']=config['allow_control']
            with self.lock:
                if generation!=self.generation or self.stop_event.is_set():return
            response=self.transport.post(PORTAL+'/remote/device/sync',headers={'Authorization':'Bearer '+token},
                json={'sequence':sequence,'snapshot':snapshot,'acknowledgements':acks},timeout=8,allow_redirects=False)
            self.check(response,generation)
            result=response.json()
            if result.get('accepted') is not True:raise ValueError('snapshot_not_accepted')
            with self.lock:
                if generation!=self.generation or self.stop_event.is_set():return
                self.last_sent=time.time();self.error=None
                for ack in acks:
                    if ack['status']=='paused':self.pending.pop(ack['id'],None)
                    self.control_acks.pop(ack['id'],None)
            for cmd in result.get('commands',[])[:20]:
                with self.lock:
                    if generation!=self.generation or self.stop_event.is_set():return
                    if config['allow_pause'] and cmd.get('action')=='pause_entries' and cmd.get('source') in VENUES and time.time()<float(cmd.get('expires',0)):
                        pauses.set(cmd['source'],True,command_id=str(cmd['id']),expires=float(cmd['expires']))
                        self.pending[str(cmd['id'])]=cmd['source']
                        continue
                if config['allow_control'] and self.control and cmd.get('action') in ('start','resume'):
                    try:
                        status=self.control.run(cmd,config['approved'])
                    except Exception:
                        status='rejected'
                    with self.lock:self.control_acks[str(cmd.get('id',''))]=status
        except Exception:
            with self.lock:
                if generation==self.generation and not self.error:
                    self.error='전송하지 못했습니다. 네트워크와 서버 베타 활성화 상태를 확인하세요.'

    def check(self,response,generation):
        if response.status_code in (401,403):
            with self.lock:
                if generation==self.generation:
                    self.config['enabled']=False;self.token='';self.save()
                    self.error='연결 권한이 해제되었거나 베타가 미활성 상태입니다. PC 로그인과 서버 상태를 확인한 뒤 다시 연결하세요.'
        if response.status_code!=200:raise ValueError('remote_unavailable')
