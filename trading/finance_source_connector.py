"""Reviewed normalized-snapshot API connector; unconfigured sources do no IO."""
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import time
from contextlib import closing
from urllib.parse import urlsplit
from filelock import FileLock, Timeout
from trading.finance_connections import _PinnedHTTPS, https_url


def fetch_snapshot(config):
    parsed=urlsplit(https_url(config['api_url']))
    addresses=sorted({row[4][0] for row in socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)})
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):raise ValueError('finance_source_private_address')
    headers={'Accept':'application/json'}
    if config.get('token_env'):
        token=os.environ.get(config['token_env'])
        if not token or len(token)>8192 or '\n' in token or '\r' in token:raise ValueError('finance_source_credentials_missing')
        headers['Authorization']='Bearer '+token
    connection=_PinnedHTTPS(parsed.hostname,addresses[0])
    try:
        connection.request('GET',(parsed.path or '/')+('?' + parsed.query if parsed.query else ''),headers=headers)
        response=connection.getresponse();raw=response.read(30*1024*1024+1)
        if response.status!=200 or len(raw)>30*1024*1024:raise ValueError('finance_source_response_invalid')
        return json.loads(raw)
    finally:connection.close()


def read_sources(path):
    path=Path(path)
    if not path.exists():return []
    with path.open('rb') as stream:raw=stream.read(256*1024+1)
    if len(raw)>256*1024:raise ValueError('finance_source_config_limit')
    rows=json.loads(raw)
    if not isinstance(rows,list) or len(rows)>30:raise ValueError('finance_source_config_invalid')
    ids=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)-{'id','url','rights_verified','rights_reference','api_url','token_env','enabled','interval_seconds','ai_processing_allowed'}:raise ValueError('finance_source_config_invalid')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',str(row.get('id',''))) or row['id'] in ids:raise ValueError('finance_source_config_invalid')
        ids.add(row['id']);https_url(row.get('url'));https_url(row.get('api_url'))
        if row.get('rights_verified') is not True or not isinstance(row.get('rights_reference'),str) or not row['rights_reference'].strip():raise ValueError('finance_source_rights_required')
        if type(row.get('enabled')) is not bool or type(row.get('interval_seconds')) is not int or not 900<=row['interval_seconds']<=86400:raise ValueError('finance_source_interval_invalid')
        if row.get('token_env') and not re.fullmatch(r'NOAHAI_FINANCE_[A-Z0-9_]{1,100}',row['token_env']):raise ValueError('finance_source_token_reference_invalid')
    return rows


def refresh_sources(store, data_dir, force=False, transport=None, clock=None):
    stamp=time.time() if clock is None else clock
    try:
        configs=read_sources(Path(data_dir)/'finance_product_sources.json')
    except (ValueError,OSError,TypeError,KeyError):
        snapshot=store.snapshot()
        snapshot['feeds'].append({'source_id':'source_configuration','status':'refresh_failed','failures':1,'error_code':'review_source_configuration'})
        return snapshot
    if not configs:return store.snapshot()
    transport=transport or fetch_snapshot
    try:
        with FileLock(str(store.path)+'.remote-refresh.lock',timeout=0):
            with closing(sqlite3.connect(store.path)) as db,db:
                db.execute('CREATE TABLE IF NOT EXISTS remote_sources(source_id TEXT PRIMARY KEY,last_attempt REAL,next_attempt REAL,failures INTEGER,status TEXT,revision TEXT)')
                due=[]
                for config in configs:
                    if not config['enabled']:continue
                    prior=db.execute('SELECT last_attempt,next_attempt,failures,status FROM remote_sources WHERE source_id=?',(config['id'],)).fetchone()
                    # A deliberate local rollback pauses remote refresh as well.
                    paused=db.execute("SELECT status FROM source_feeds WHERE source_id=?",(config['id'],)).fetchone()
                    if paused and paused[0]=='paused_after_rollback':continue
                    if prior and prior[3]=='paused_after_rollback':continue
                    if prior and (stamp-prior[0]<5 or (not force and stamp<prior[1])):continue
                    due.append((config,prior[2] if prior else 0))
                for config,failures in due[:3]:
                    db.execute('INSERT INTO remote_sources VALUES (?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET last_attempt=excluded.last_attempt,next_attempt=excluded.next_attempt,failures=excluded.failures,status=excluded.status',(config['id'],stamp,stamp+config['interval_seconds'],failures,'refreshing',None))
                db.commit()
            for config,failures in due[:3]:
                revision=None
                try:
                    payload=transport(config)
                    if not isinstance(payload,dict) or payload.get('source_id')!=config['id']:raise ValueError('finance_source_identity_mismatch')
                    result=store.ingest({k:config[k] for k in ('id','url','rights_verified','rights_reference','ai_processing_allowed') if k in config},payload.get('products'))
                    revision=result['revision'];status='current';failures=0;next_attempt=stamp+config['interval_seconds']
                except Exception:
                    failures+=1;status='refresh_failed';next_attempt=stamp+min(3600,60*2**min(failures,6))
                with closing(sqlite3.connect(store.path)) as db,db:
                    db.execute('UPDATE remote_sources SET next_attempt=?,failures=?,status=?,revision=COALESCE(?,revision) WHERE source_id=?',(next_attempt,failures,status,revision,config['id']))
    except Timeout:
        pass
    return store.snapshot()
