"""One reviewed editorial feed, delivered independently of client releases.

Configuration is operator-owned. Full replacement uses tombstones; unsuccessful
or replayed payloads preserve the last reviewed content and its original dates.
"""
from pathlib import Path
from contextlib import closing
from datetime import datetime, timezone
import json
import sqlite3
import time
from filelock import FileLock, Timeout
from trading.finance_connections import digest, https_url
from trading.finance_source_connector import fetch_snapshot
from trading.insurance_reference_directory import validate, snapshot


def config(directory):
    path=Path(directory)/'finance_reference_source.json'
    if not path.exists():return None
    raw=path.read_bytes()
    if len(raw)>16384:raise ValueError('reference_config_limit')
    row=json.loads(raw)
    keys={'id','api_url','enabled','interval_seconds','owner','contact_url','editorial_rights_reference','ai_processing_allowed'}
    if not isinstance(row,dict) or set(row)!=keys:raise ValueError('reference_config_invalid')
    for k in ('id','owner','editorial_rights_reference'):
        if not isinstance(row[k],str) or not row[k].strip() or len(row[k])>300:raise ValueError('reference_review_required')
    if type(row['enabled']) is not bool or type(row['ai_processing_allowed']) is not bool:raise ValueError('reference_config_invalid')
    if type(row['interval_seconds']) is not int or not 900<=row['interval_seconds']<=86400:raise ValueError('reference_config_invalid')
    https_url(row['api_url']);https_url(row['contact_url'])
    return row


def setup(path):
    snapshot(path)
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('CREATE TABLE IF NOT EXISTS reference_feed_state (id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS reference_feed_revisions (revision TEXT PRIMARY KEY,payload TEXT NOT NULL)')


def status(path):
    setup(path)
    with closing(sqlite3.connect(path)) as db:
        rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM reference_feed_state')]
    return rows or [{'status':'not_configured','owner':None,'next_attempt':None,'failures':0}]


def apply(path,cfg,payload,stamp=None):
    setup(path);stamp=time.time() if stamp is None else stamp
    if not isinstance(payload,dict) or set(payload)!={'schema','source_id','sequence','published_at','products'} or payload['schema']!='noah-insurance-reference-v1' or payload['source_id']!=cfg['id']:
        raise ValueError('reference_feed_schema')
    from trading.finance_product_intelligence import instant
    if instant(payload['published_at'])>datetime.now(timezone.utc) or type(payload['sequence']) is not int or payload['sequence']<1:raise ValueError('reference_feed_sequence')
    products=validate(payload['products']);revision=digest(payload)
    with closing(sqlite3.connect(path)) as db,db:
        previous=db.execute('SELECT payload FROM reference_feed_state WHERE id=?',(cfg['id'],)).fetchone()
        previous=json.loads(previous[0]) if previous else {}
        if payload['sequence']<previous.get('sequence',0) or (payload['sequence']==previous.get('sequence') and revision!=previous.get('revision')):raise ValueError('reference_feed_replay')
        # Previously managed IDs absent from a full snapshot become withdrawals.
        managed=set(previous.get('managed_ids',[]));new={p['id'] for p in products}
        for id in managed-new:
            row=db.execute('SELECT payload FROM insurance_references WHERE id=?',(id,)).fetchone()
            if row:
                record=json.loads(row[0]);record['status']='withdrawn'
                db.execute('UPDATE insurance_references SET payload=? WHERE id=?',(json.dumps(record,ensure_ascii=False),id))
        origin=('owned-feed:' if cfg['ai_processing_allowed'] else 'feed:')+cfg['id']
        for row in products:
            db.execute('INSERT INTO insurance_references VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET origin=excluded.origin,payload=excluded.payload',(row['id'],origin,json.dumps(row,ensure_ascii=False)))
        state={'id':cfg['id'],'owner':cfg['owner'],'contact_url':cfg['contact_url'],'status':'current','failures':0,'last_attempt':stamp,'next_attempt':stamp+cfg['interval_seconds'],'revision':revision,'sequence':payload['sequence'],'published_at':payload['published_at'],'managed_ids':sorted(managed|new)}
        db.execute('INSERT OR REPLACE INTO reference_feed_state VALUES (?,?)',(cfg['id'],json.dumps(state)))
        db.execute('INSERT OR IGNORE INTO reference_feed_revisions VALUES (?,?)',(revision,json.dumps(payload,ensure_ascii=False)))
    return state


def refresh(path,directory,force=False,transport=None,stamp=None):
    stamp=time.time() if stamp is None else stamp;setup(path)
    try:cfg=config(directory)
    except (ValueError,TypeError,OSError):return [{'status':'configuration_error','failures':1}]
    if not cfg:return status(path)
    if not cfg['enabled']:return [{'status':'disabled','owner':cfg['owner'],'contact_url':cfg['contact_url'],'failures':0}]
    try:
        with FileLock(str(path)+'.reference-refresh.lock',timeout=0):
            prior=next((s for s in status(path) if s.get('id')==cfg['id']),{})
            if prior.get('status')=='paused_after_rollback' or (prior.get('last_attempt') is not None and stamp-prior['last_attempt']<5) or (not force and stamp<prior.get('next_attempt',0)):return status(path)
            try:apply(path,cfg,(transport or fetch_snapshot)(cfg),stamp)
            except Exception:
                failures=prior.get('failures',0)+1
                prior.update(id=cfg['id'],owner=cfg['owner'],contact_url=cfg['contact_url'],status='refresh_failed',failures=failures,last_attempt=stamp,next_attempt=stamp+min(3600,60*2**min(failures,6)))
                with closing(sqlite3.connect(path)) as db,db:db.execute('INSERT OR REPLACE INTO reference_feed_state VALUES (?,?)',(cfg['id'],json.dumps(prior)))
    except Timeout:pass
    return status(path)


def rollback(path,revision):
    setup(path)
    with FileLock(str(path)+'.reference-refresh.lock',timeout=2),closing(sqlite3.connect(path)) as db,db:
        raw=db.execute('SELECT payload FROM reference_feed_revisions WHERE revision=?',(revision,)).fetchone()
        if not raw:raise ValueError('reference_revision_missing')
        payload=json.loads(raw[0]);state=json.loads(db.execute('SELECT payload FROM reference_feed_state WHERE id=?',(payload['source_id'],)).fetchone()[0])
        products={r['id']:r for r in payload['products']}
        for id in state['managed_ids']:
            if id in products:record=products[id]
            else:
                row=db.execute('SELECT payload FROM insurance_references WHERE id=?',(id,)).fetchone()
                if not row:continue
                record=json.loads(row[0]);record['status']='withdrawn'
            # Conservative after rollback: reviewed text remains local until republished.
            db.execute('INSERT OR REPLACE INTO insurance_references VALUES (?,?,?)',(id,'feed:'+payload['source_id'],json.dumps(record,ensure_ascii=False)))
        state.update(status='paused_after_rollback',rollback_revision=revision)
        db.execute('UPDATE reference_feed_state SET payload=? WHERE id=?',(json.dumps(state),payload['source_id']))
    return state
