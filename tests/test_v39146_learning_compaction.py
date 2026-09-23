import gzip
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

import pytest

from trading.event_contract import canonical_json
from trading.learning_storage import LearningStore, iter_legacy
from trading.learning_archive_compaction import compact_one, candidates


def entry(i):
    rules = {'source_evidence':'exact source paragraph '*3000, 'entry':{'rsi':30}}
    return {'_learning_event_id':str(i), 'exchange':'okx', 'symbol':'BTC/USDT:USDT',
            'timestamp':'2026-09-01T00:00:00+00:00', 'execution_mode':'paper',
            'trade_candidate':{'selected_rules':rules, 'evaluation':{'selected_rules':rules, 'score':i}},
            'reserved_test':{'ref':'not-a-reference', '_xai_refs':{'dict':['value',4]}}}


def archive_file(root, content):
    path = root/'ai_learning_data_okx_archive_20260901.jsonl'
    path.write_bytes(content)
    os.utime(path,(time.time()-3600,time.time()-3600))
    return path


def test_nested_rules_are_stored_once_and_every_event_roundtrips(tmp_path):
    store = LearningStore(tmp_path)
    rows = [entry(i) for i in range(50)]
    for row in rows: store.append('okx', row)
    assert store.recent('okx') == rows
    with store.connect() as conn:
        size = conn.execute('SELECT sum(length(CAST(body AS BLOB))) FROM evidence').fetchone()[0]
        digest = hashlib.sha256(canonical_json(rows[0]['trade_candidate']['selected_rules']).encode()).hexdigest()
        assert conn.execute('SELECT count(*) FROM evidence WHERE hash=?',(digest,)).fetchone()[0] == 1
    raw = sum(len(canonical_json(r).encode()) for r in rows)
    assert size < raw/20
    while store.archive(keep=0): pass
    with store.connect() as conn: names=[r[0] for r in conn.execute('SELECT name FROM segments')]
    restored = [r for n in names for r in store.read_segment(n)]
    assert sorted(restored,key=lambda r:r['_learning_event_id']) == sorted(rows,key=lambda r:r['_learning_event_id'])
    for row in rows: store.append('okx',row)
    assert store.count() == 0


def test_existing_text_evidence_migrates_without_changing_hash_or_old_archive(tmp_path):
    store = LearningStore(tmp_path)
    row = entry(1)
    store.append('okx', row)
    candidate = row['trade_candidate']
    digest = hashlib.sha256(canonical_json(candidate).encode()).hexdigest()
    with store.connect() as conn:
        conn.execute('UPDATE evidence SET body=? WHERE hash=?',(canonical_json(candidate),digest))
    store.archive(keep=0)
    with store.connect() as conn: name=conn.execute('SELECT name FROM segments').fetchone()[0]
    assert store.compact_evidence(batch=1) == 1
    assert store.compact_evidence(batch=1) == 0
    assert LearningStore(tmp_path).read_segment(name) == [row]


def test_corrupt_evidence_migration_rolls_back(tmp_path):
    store = LearningStore(tmp_path)
    with store.connect() as conn: conn.execute('INSERT INTO evidence VALUES (?,?)',('invalid','x'*2000))
    with pytest.raises(ValueError): store.compact_evidence()
    with store.connect() as conn:
        assert conn.execute('SELECT body FROM evidence').fetchone()[0]=='x'*2000


def test_archive_lossless_idempotent_and_readable(tmp_path):
    content = b''.join((json.dumps(entry(i),ensure_ascii=False)+'\n').encode() for i in range(20))
    source = archive_file(tmp_path,content)
    before = hashlib.sha256(content).hexdigest()
    result = compact_one(source)
    packed = Path(str(source)+'.gz')
    assert result['sha256']==before and result['saved_bytes']>0
    assert not source.exists() and gzip.decompress(packed.read_bytes())==content
    assert list(iter_legacy(packed))==[entry(i) for i in range(20)]
    assert candidates(tmp_path)==[]
    # Simulate crash after archive commit but before the plain source removal.
    source = archive_file(tmp_path,content)
    assert compact_one(source)['sha256']==before


def test_changed_source_is_never_removed(tmp_path):
    content = b'x'*2_000_000
    source = archive_file(tmp_path,content)
    changed = []
    def progress(size):
        if not changed:
            with source.open('ab') as out:out.write(b'new append')
            changed.append(True)
    with pytest.raises(ValueError,match='changed'): compact_one(source,progress)
    assert source.exists() and source.read_bytes()==content+b'new append'


def test_conflicting_destination_and_disk_failure_preserve_source(tmp_path,monkeypatch):
    source=archive_file(tmp_path,b'original'*1000)
    destination=Path(str(source)+'.gz')
    destination.write_bytes(gzip.compress(b'other'))
    with pytest.raises(ValueError,match='conflict'): compact_one(source)
    assert source.exists() and gzip.decompress(destination.read_bytes())==b'other'
    destination.unlink()
    monkeypatch.setattr('trading.learning_archive_compaction.os.fsync',lambda *_: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError): compact_one(source)
    assert source.exists() and not destination.exists()
    assert not list(tmp_path.glob('.learning-pack-*'))


def test_active_and_unrelated_files_are_never_compacted(tmp_path):
    from datetime import datetime
    names=['trading.db','ai_learning_data_okx.json','ai_learning_data_okx.json.journal.jsonl',
           f'ai_learning_data_okx_archive_{datetime.now():%Y%m%d}.jsonl']
    for name in names:
        p=tmp_path/name;p.write_bytes(b'keep')
        os.utime(p,(0,0))
        with pytest.raises(ValueError): compact_one(p)
    assert all((tmp_path/n).read_bytes()==b'keep' for n in names)


def test_abandoned_temp_reclaimed_without_touching_other_files(tmp_path):
    source=archive_file(tmp_path,b'original'*1000)
    orphan=tmp_path/'.learning-pack-abcd1234'
    orphan.write_bytes(b'incomplete')
    unrelated=tmp_path/'.learning-pack-user-backup'
    unrelated.write_bytes(b'keep')
    compact_one(source)
    assert not orphan.exists() and unrelated.read_bytes()==b'keep'


def test_compressed_legacy_import_keeps_identity_without_event_ids(tmp_path):
    row=entry(1);row.pop('_learning_event_id')
    source=archive_file(tmp_path,(json.dumps(row)+'\n').encode())
    store=LearningStore(tmp_path)
    store.import_legacy(source,'okx')
    compact_one(source)
    store.import_legacy(Path(str(source)+'.gz'),'okx')
    assert store.count()==1


def test_recent_history_tail_does_not_expand_ten_thousand_rows(tmp_path, monkeypatch):
    from trading.learning_storage import RecentHistory
    store=LearningStore(tmp_path)
    for i in range(100): store.append('okx',entry(i))
    history=RecentHistory(store,'okx',80)
    expected=store.recent('okx',80)
    original=store.recent
    reads=[]
    def recent(venue,limit,**kw):
        reads.append(limit)
        return original(venue,limit,**kw)
    monkeypatch.setattr(store,'recent',recent)
    assert history[-10:]==expected[-10:] and reads==[10]
    assert history[-1]==expected[-1] and reads[-1]==1
    assert history[3:7]==expected[3:7] and reads[-1]==4
    assert history[7:3:-1]==expected[7:3:-1]
    assert history[:0]==[]
    with pytest.raises(IndexError): _=history[80]


def test_maintenance_reduces_actual_bytes_not_only_counter(tmp_path):
    from trading.storage_maintenance import StorageMaintenance
    source=archive_file(tmp_path,b''.join((json.dumps(entry(i))+'\n').encode() for i in range(20)))
    job=StorageMaintenance(tmp_path)
    before=job.status()['learning_bytes']
    job.run()
    status=job.status()
    assert status['state']=='complete',status
    assert status['legacy_archives_compressed']==1 and status['legacy_archives_pending']==0
    assert status['learning_bytes'] < before/4
    assert not source.exists() and Path(str(source)+'.gz').exists()
    assert status['trade_records_deleted'] is False
