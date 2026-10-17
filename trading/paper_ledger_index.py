"""Rebuildable, private index of the immutable PAPER journal.

No lifetime byte/row cap. Input is streamed in bounded records/transactions.
Unknown file changes verify every indexed byte before any result is used;
appends through the journal writer extend the verified prefix under its lock.
The original JSONL, sessions and positions remain the source of truth.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
from collections.abc import Sequence
from functools import wraps
from filelock import FileLock

BATCH_BYTES=4*1024*1024
MAX_RECORD_BYTES=8*1024*1024
_GUARD=threading.RLock()
_LOCKS={}
_INDEXES={}


def ledger_lock(path):
    key=str(Path(path).resolve())
    with _GUARD:
        return _LOCKS.setdefault(key,FileLock(key+'.lock',timeout=10))


def _signature(path):
    if not path.exists():return None
    s=path.stat()
    return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns


def _database_errors(method):
    @wraps(method)
    def guarded(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except sqlite3.Error as exc:
            raise ValueError('paper_ledger_index_unavailable') from exc
    return guarded


class LedgerIndex:
    def __init__(self,path):
        self.path=Path(path).resolve()
        self.db_path=self.path.with_name(self.path.name+'.index.sqlite3')
        self.signature=None
        self.hasher=None
        self.prefixes={}
        self.db_signature=None
        self.progress={'state':'idle','processed_bytes':0,'total_bytes':0}

    @_database_errors
    def connect(self):
        db=sqlite3.connect(self.db_path,timeout=10)
        db.execute('PRAGMA busy_timeout=10000')
        db.executescript('''CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS chunks(start INTEGER PRIMARY KEY,stop INTEGER NOT NULL,digest TEXT NOT NULL,derived_digest TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events(key TEXT PRIMARY KEY,event_id TEXT,identity TEXT NOT NULL,
            start INTEGER NOT NULL,stop INTEGER NOT NULL,payload TEXT NOT NULL,
            venue TEXT,scope TEXT,symbol TEXT,position_key TEXT,quote TEXT,net REAL,
            fund_reason TEXT,parallel INTEGER NOT NULL);
          CREATE INDEX IF NOT EXISTS events_offset ON events(start);
          CREATE INDEX IF NOT EXISTS events_position ON events(scope,venue,symbol,position_key);
          CREATE INDEX IF NOT EXISTS events_wallet ON events(venue,start,parallel);
          CREATE INDEX IF NOT EXISTS events_identity ON events(event_id);''')
        db.execute("INSERT OR IGNORE INTO meta VALUES('offset','0')")
        db.commit()
        try:
            if os.name!='nt' and self.db_path.stat().st_mode&0o777!=0o600:os.chmod(self.db_path,0o600)
        except OSError:pass
        return db

    @_database_errors
    def sync(self,cancel=None,progress=None):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with ledger_lock(self.path):
            signature=_signature(self.path)
            db_signature=_signature(self.db_path)
            if signature==self.signature and self.hasher is not None and db_signature==self.db_signature:return
            if self.db_signature is not None and db_signature!=self.db_signature:
                # A missing/changed derived cache must be rebuilt, never treated as zero PnL.
                self.prefixes.clear()
                if self.db_path.exists():
                    os.replace(self.db_path,self.db_path.with_suffix('.rebuild'))
            self.signature=None
            db=self.connect()
            try:
                offset=int(db.execute("SELECT value FROM meta WHERE key='offset'").fetchone()[0])
                size=signature[2] if signature else 0
                if size<offset:raise ValueError('paper_close_recovery_ledger_changed')
                self.progress={'state':'verifying','processed_bytes':0,'total_bytes':size}
                hasher=hashlib.sha256()
                if self.path.exists():
                    with self.path.open('rb') as stream:
                        # A restart or external append cannot assume the old prefix is intact.
                        cursor=0
                        for start,stop,digest,derived in db.execute('SELECT start,stop,digest,derived_digest FROM chunks ORDER BY start'):
                            if cancel and cancel.is_set():raise ValueError('paper_reconciliation_cancelled')
                            if start!=cursor or stop<=start or stop>offset:raise ValueError('paper_ledger_index_invalid')
                            chunk=stream.read(stop-start)
                            if self._derived_digest(db,start,stop)!=derived:raise ValueError('paper_ledger_index_invalid')
                            if len(chunk)!=stop-start or hashlib.sha256(chunk).hexdigest()!=digest:
                                raise ValueError('paper_close_recovery_ledger_changed')
                            hasher.update(chunk);cursor=stop
                            self.progress['processed_bytes']=cursor
                            if progress:progress(dict(processed_bytes=cursor,total_bytes=size,phase='verifying'))
                        if cursor!=offset:raise ValueError('paper_ledger_index_invalid')
                        while offset<size:
                            if cancel and cancel.is_set():raise ValueError('paper_reconciliation_cancelled')
                            start=offset;batch=bytearray();records=[]
                            while len(batch)<BATCH_BYTES and offset<size:
                                raw=stream.readline(MAX_RECORD_BYTES+1)
                                if len(raw)>MAX_RECORD_BYTES:raise ValueError('paper_ledger_record_too_large')
                                if not raw.endswith(b'\n'):raise ValueError('paper_close_recovery_torn_ledger')
                                begin=offset;offset+=len(raw);batch.extend(raw)
                                if raw.strip():records.append((begin,offset,raw))
                            if _signature(self.path)!=signature:raise ValueError('paper_ledger_changed_during_read')
                            with db:
                                for begin,stop,raw in records:self._insert(db,begin,stop,raw)
                                db.execute('INSERT INTO chunks VALUES(?,?,?,?)',(start,offset,hashlib.sha256(batch).hexdigest(),self._derived_digest(db,start,offset)))
                                db.execute("UPDATE meta SET value=? WHERE key='offset'",(str(offset),))
                            hasher.update(batch)
                            self.progress['processed_bytes']=offset
                            if progress:progress(dict(processed_bytes=offset,total_bytes=size,phase='indexing'))
                if _signature(self.path)!=signature:raise ValueError('paper_ledger_changed_during_read')
                self.signature=signature;self.hasher=hasher
                self.progress.update(state='checked',processed_bytes=size)
            except ValueError as exc:
                self.signature=None;self.hasher=None
                if str(exc)=='paper_ledger_index_invalid':
                    # Rebuild only a damaged derived cache whose pinned source
                    # bytes are still intact. Never discard evidence of a journal rewrite.
                    verified=0
                    with self.path.open('rb') as source:
                        for begin,end,digest in db.execute('SELECT start,stop,digest FROM chunks ORDER BY start'):
                            raw=source.read(end-begin)
                            if begin!=verified or end<=begin or hashlib.sha256(raw).hexdigest()!=digest:
                                raise ValueError('paper_close_recovery_ledger_changed')
                            verified=end
                    if verified!=int(db.execute("SELECT value FROM meta WHERE key='offset'").fetchone()[0]):raise
                    db.close()
                    os.replace(self.db_path,self.db_path.with_suffix('.rebuild'))
                    self.db_signature=None;self.prefixes.clear()
                    return self.sync(cancel=cancel,progress=progress)
                self.progress['state']='needs_evidence'
                raise
            except Exception:
                self.signature=None;self.hasher=None
                self.progress['state']='needs_evidence'
                raise
            finally:
                db.close()
                self.db_signature=_signature(self.db_path)

    @staticmethod
    def _derived_digest(db,start,stop):
        digest=hashlib.sha256()
        for row in db.execute('SELECT * FROM events WHERE start>=? AND start<? ORDER BY start',(start,stop)):
            digest.update(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode())
        return digest.hexdigest()

    def _insert(self,db,start,stop,raw):
        from .paper_strategy_ledger import outcome_identity,normalize_paper_outcome_costs,paper_outcome_calculation_status
        from .strategy_scope import canonical_venue
        try:row=json.loads(raw)
        except (ValueError,UnicodeDecodeError) as exc:raise ValueError('paper_close_recovery_torn_ledger') from exc
        if not isinstance(row,dict):raise ValueError('paper_close_recovery_invalid_ledger')
        if row.get('execution_mode')!='paper':return
        event=str(row.get('event_id') or '')
        identity=hashlib.sha256(json.dumps(outcome_identity(row),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        prior=db.execute('SELECT identity FROM events WHERE key=?',(event or f'__line_{start}',)).fetchone()
        if prior:
            if prior[0]!=identity:raise ValueError('paper_ledger_event_conflict')
            return
        if row.get('close_recovery'):
            from .paper_position_store import validate_close_proof
            try:
                validate_close_proof(row)
            except (KeyError,TypeError,ValueError,AttributeError,OverflowError) as exc:
                raise ValueError('paper_close_recovery_evidence_invalid') from exc
        normalized=normalize_paper_outcome_costs(row)
        reason='' if event and paper_outcome_calculation_status(normalized)=='valid' else 'paper_ledger_pnl_unverified'
        net=normalized.get('net_pnl')
        try:
            import math
            if isinstance(net,bool) or not math.isfinite(float(net)):raise ValueError()
            net=float(net)
        except (TypeError,ValueError,OverflowError):net=None;reason='paper_ledger_pnl_unverified'
        proof=row.get('close_recovery') or {}
        parent=(proof.get('before') or {}).get('position_id') if isinstance(proof,dict) else None
        parent=parent or str(row.get('position_id') or '').split(':partial:')[0]
        db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(
            event or f'__line_{start}',event,identity,start,stop,json.dumps(row,ensure_ascii=False),
            canonical_venue(str(row.get('exchange') or '')),str(row.get('scope') or '').lower(),
            str(row.get('symbol') or ''),parent,str(normalized.get('quote_currency') or '').upper(),net,
            reason,int(row.get('cost_calculation_status')=='parallel_paper_recorded_contract')))

    @_database_errors
    def appended(self,raw,before_signature):
        """Called only by the fsynced journal writer, while ledger_lock is held."""
        if self.hasher is None or self.signature!=before_signature:
            self.signature=None;return
        start=before_signature[2] if before_signature else 0
        signature=_signature(self.path)
        if signature is None or signature[2]!=start+len(raw):
            self.signature=None;return
        db=self.connect()
        try:
            with db:
                self._insert(db,start,start+len(raw),raw)
                db.execute('INSERT INTO chunks VALUES(?,?,?,?)',(start,start+len(raw),hashlib.sha256(raw).hexdigest(),self._derived_digest(db,start,start+len(raw))))
                db.execute("UPDATE meta SET value=? WHERE key='offset'",(str(start+len(raw)),))
            self.hasher.update(raw);self.signature=signature
            self.db_signature=_signature(self.db_path)
            self.progress=dict(state='checked',processed_bytes=signature[2],total_bytes=signature[2])
        except Exception:
            self.signature=None;self.hasher=None
            raise
        finally:db.close()

    def prefix_hash(self,offset):
        with ledger_lock(self.path):
            self.sync()
            if type(offset) is not int or offset<0 or offset>(self.signature[2] if self.signature else 0):
                raise ValueError('paper_close_recovery_ledger_changed')
            if offset==(self.signature[2] if self.signature else 0):return self.hasher.hexdigest()
            if offset in self.prefixes:return self.prefixes[offset]
            digest=hashlib.sha256()
            with self.path.open('rb') as stream:
                left=offset
                while left:
                    chunk=stream.read(min(left,1024*1024))
                    if not chunk:raise ValueError('paper_close_recovery_ledger_changed')
                    digest.update(chunk);left-=len(chunk)
            self.prefixes[offset]=digest.hexdigest()
            while len(self.prefixes)>64:self.prefixes.pop(next(iter(self.prefixes)))
            return self.prefixes[offset]

    @_database_errors
    def event(self,event):
        self.sync();db=self.connect()
        try:
            row=db.execute('SELECT payload FROM events WHERE event_id=?',(event,)).fetchone()
            return json.loads(row[0]) if row else None
        finally:db.close()

    @_database_errors
    def wallet(self,venue,quote,offset):
        self.sync();db=self.connect()
        try:
            invalid=db.execute("SELECT quote,fund_reason FROM events WHERE venue=? AND start>=? AND parallel=0 AND (quote!=? OR fund_reason!='') LIMIT 1",(venue,offset,quote)).fetchone()
            if invalid:raise ValueError('paper_ledger_currency_unverified' if invalid[0]!=quote else invalid[1])
            return float(db.execute('SELECT COALESCE(SUM(net),0) FROM events WHERE venue=? AND start>=? AND parallel=0',(venue,offset)).fetchone()[0])
        finally:db.close()

    def position_rows(self,stores,scope):
        self.sync();db=self.connect()
        try:
            for venue,positions in list(stores.items()):
                for symbol,position in list(positions.items()):
                    for (payload,) in db.execute('SELECT payload FROM events WHERE scope=? AND venue=? AND symbol=? AND position_key=? ORDER BY start',(scope,venue,symbol,str(position.position_id or ''))):
                        yield json.loads(payload)
        finally:db.close()


class Rows(Sequence):
    def __init__(self,index):self.index=index
    def __len__(self):
        db=self.index.connect()
        try:return db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        finally:db.close()
    def __iter__(self):
        db=self.index.connect()
        try:
            for (payload,) in db.execute('SELECT payload FROM events ORDER BY start'):yield json.loads(payload)
        finally:db.close()
    def __getitem__(self,key):return list(self)[key]


def index_for(path):
    key=str(Path(path).resolve())
    with _GUARD:return _INDEXES.setdefault(key,LedgerIndex(Path(key)))
