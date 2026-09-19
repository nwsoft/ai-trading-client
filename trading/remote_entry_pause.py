"""Persistent per-account entry submission pause; exits do not use this gate."""
from contextlib import contextmanager
from functools import wraps
import json
import os
from pathlib import Path
import threading
import time

_instances = {}
_registry_lock = threading.Lock()
VENUES = {'binance','bybit','okx','bitget','upbit','bithumb','coinone','kiwoom','kis','mirae','shinhan'}


class EntryPause:
    def __init__(self, directory):
        self.path=Path(directory)/'remote_entry_pause.json'
        self.lock=threading.RLock();self.active={};self.paused=set();self.receipts={}
        try:
            data=json.loads(self.path.read_text())
            if isinstance(data,dict):
                self.receipts={key:float(value) for key,value in data.get('receipts',{}).items() if float(value)>time.time()}
                data=data.get('paused')
            if not isinstance(data,list) or not all(v in VENUES for v in data):
                raise ValueError('invalid_pause_state')
            self.paused=set(data)
        except FileNotFoundError:
            pass
        except (OSError,ValueError,TypeError):
            self.paused=set(VENUES)

    def set(self, source, paused, command_id=None, expires=0):
        if source not in VENUES or not isinstance(paused,bool):
            raise ValueError('invalid_pause_source')
        with self.lock:
            receipts={key:value for key,value in self.receipts.items() if value>time.time()}
            if command_id in receipts:
                return {**self.state(source),'already_applied':True}
            if command_id:
                if not paused or not isinstance(command_id,str) or len(command_id)>80 or not time.time()<expires<=time.time()+180:
                    raise ValueError('invalid_or_expired_pause_command')
                receipts[command_id]=expires+300
            changed=set(self.paused)
            if paused: changed.add(source)
            else: changed.discard(source)
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.path.with_suffix('.tmp')
            with os.fdopen(os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as stream:
                json.dump({'paused':sorted(changed),'receipts':receipts},stream);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,self.path)
            self.paused=changed
            self.receipts=receipts
            return self.state(source)

    def state(self, source):
        with self.lock:
            active=self.active.get(source,0)
            return {'paused':source in self.paused,'in_flight':active,
                    'status':'draining' if source in self.paused and active else 'paused' if source in self.paused else 'enabled',
                    'existing_orders':'unchanged_may_fill','protective_management':'unchanged'}

    @contextmanager
    def permit(self, source):
        with self.lock:
            allowed=source not in self.paused
            if allowed:self.active[source]=self.active.get(source,0)+1
        try: yield allowed
        finally:
            if allowed:
                with self.lock:self.active[source]-=1


def gate(directory=None):
    if directory is None:
        from path_utils import get_app_data_dir
        directory=get_app_data_dir()
    key=str(Path(directory).resolve())
    with _registry_lock:
        if key not in _instances:_instances[key]=EntryPause(key)
        return _instances[key]


def entry_submission(source, *, stock=False):
    """Stock SELL is an exit; both crypto BUY and SELL can be new exposure."""
    def decorate(fn):
        @wraps(fn)
        def execute(self,*args,**kwargs):
            if stock and str(kwargs.get('side','')).upper()=='SELL':
                return fn(self,*args,**kwargs)
            venue=str(getattr(self,'broker_name','')).lower() if stock else source
            venue={'miraeasset':'mirae','koreainvestment':'kis'}.get(venue,venue)
            with gate().permit(venue) as allowed:
                if not allowed:
                    return (False,{},['remote_entries_paused']) if stock else False
                return fn(self,*args,**kwargs)
        return execute
    return decorate
