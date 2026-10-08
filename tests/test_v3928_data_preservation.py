import json,sqlite3,hashlib,shutil
from pathlib import Path
from unittest.mock import patch
import pytest
from scripts.paper_data_snapshot import snapshot,database_evidence
from trading.paper_position_store import load_positions,save_positions
from trading.paper_strategy_ledger import read_paper_strategy_outcomes
from test_v3928_close_recovery import fixture


def test_wal_backup_preserves_rows_and_never_opens_original_database(tmp_path):
    source=tmp_path/'account';source.mkdir();db=source/'trading.db'
    conn=sqlite3.connect(db);conn.execute('PRAGMA journal_mode=WAL');conn.execute('CREATE TABLE trades(id PRIMARY KEY,pnl)');conn.execute('INSERT INTO trades VALUES(1,20)');conn.commit()
    (source/'credentials.json').write_text('{"key":"synthetic-only"}')
    before={p.name:p.read_bytes() for p in source.iterdir()}
    result=snapshot(source,tmp_path/'backup',stopped=True)
    assert result['databases']['trading.db']['tables']['trades']['count']==1
    assert result['databases']['trading.db']['integrity_check']=='ok'
    assert before=={p.name:p.read_bytes() for p in source.iterdir()}
    assert (tmp_path/'backup/data/credentials.json').read_bytes()==before['credentials.json']
    assert set(result['backup_files'])=={'trading.db','credentials.json'}
    assert not any((tmp_path/'backup/data').glob('*.snapshot*'))
    conn.close()


def test_backup_requires_stopped_engine_and_rejects_changed_source(tmp_path):
    source=tmp_path/'account';source.mkdir();file=source/'settings.json';file.write_text('{}')
    with pytest.raises(ValueError,match='stop_required'):snapshot(source,tmp_path/'no-stop',stopped=False)
    real=shutil.copytree
    def concurrent_write(src,dst,*a,**kw):
        result=real(src,dst,*a,**kw)
        if Path(src)==source:file.write_text('{"changed":true}')
        return result
    with patch('scripts.paper_data_snapshot.shutil.copytree',side_effect=concurrent_write),pytest.raises(ValueError,match='source_changed'):
        snapshot(source,tmp_path/'changed',stopped=True)
    assert (tmp_path/'changed/SNAPSHOT_FAILED.txt').exists()


def source_format_rollback_evidence(tmp_path):
    # Source/data compatibility only: not NSIS installation acceptance.
    from trading.paper_funds_session import start_session,read_session
    from trading.paper_strategy_ledger import record_paper_strategy_outcome
    from trading.paper_capital import paper_available_funds
    source=tmp_path/'paper-copy';source.mkdir();ledger=source/'ledger.jsonl'
    ledger.write_text(json.dumps({'event_id':'legacy-before-session','position_id':'legacy-position','scope':'unified','exchange':'okx','execution_mode':'paper','calculation_status':'legacy_unverified','quote_currency':'USDT','net_pnl':20})+'\n')
    session=start_session(ledger,venue='okx',quote='USDT',initial_equity=1000,positions={},stopped=True,pending_orders=0)
    session_bytes=(source/'paper_funds_sessions.json').read_bytes()
    t,p,d=fixture(tmp_path);t._paper_position_path=lambda:source/'positions.json'
    save_positions(t._paper_position_path(),t.paper_positions)
    with sqlite3.connect(source/'trading.db') as conn:
        conn.execute('CREATE TABLE trades(id PRIMARY KEY,pnl)');conn.execute('INSERT INTO trades VALUES(1,0)')
    (source/'settings.json').write_text('{"paper_trading":true}')
    (source/'credentials.json').write_text('{"key":"synthetic"}')
    (source/'strategies.json').write_text('{"version":"fixture-v1"}')
    (source/'reservations.json').write_text('{"held":12}')
    old=snapshot(source,tmp_path/'pre-upgrade',stopped=True)
    with patch('trading.paper_strategy_ledger.ledger_path',return_value=ledger):
        assert t._execute_advanced_partial_close_unified('okx',p.symbol,p,110.,d)
    record_paper_strategy_outcome(scope='unified',exchange='okx',symbol='SECOND/USDT:USDT',strategy_key='',version_id='',opened_at=p.entry_time,closed_at=p.entry_time,net_pnl=-75,gross_pnl=-75,fees=0,entry_price=100,exit_price=25,quantity=1,side='LONG',quote_currency='USDT',contract_size=1,position_id='already-closed-new-loss',ledger_file=ledger)
    prefix=ledger.read_bytes()
    before_funds=paper_available_funds(1000,t.paper_positions['okx'],venue='okx',quote='USDT',ledger_file=ledger)
    assert before_funds['capital_basis']=='paper_reconciled_funds'
    with sqlite3.connect(source/'trading.db') as conn:conn.execute('INSERT INTO trades VALUES(2,-75)')
    latest=snapshot(source,tmp_path/'before-rollback',stopped=True)
    # Emulate .7's schema-1 loader/serializer roundtrip on a second copy.
    rollback=tmp_path/'rollback-copy';shutil.copytree(tmp_path/'before-rollback/data',rollback)
    import importlib.util
    from trading.trader import Position,PositionSide
    spec=importlib.util.spec_from_file_location('public_v3927_positions',Path(__file__).parent/'fixtures/paper_positions_v3927.py')
    old_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(old_module)
    old_positions=old_module.load_positions(rollback/'positions.json',Position,PositionSide)
    old_module.save_positions(rollback/'positions.json',old_positions)
    t._paper_position_path=lambda:rollback/'positions.json'
    with patch('trading.paper_strategy_ledger.ledger_path',return_value=rollback/'ledger.jsonl'):
        t._restore_paper_positions();assert not t._paper_recovery_error
    assert t.paper_positions['okx'][p.symbol].quantity==6
    assert (rollback/'ledger.jsonl').read_bytes().startswith(prefix)
    assert (rollback/'paper_funds_sessions.json').read_bytes()==session_bytes
    assert read_session(rollback/'ledger.jsonl',venue='okx',quote='USDT')['session_id']==session['session_id']
    db=database_evidence(rollback/'trading.db')['tables']['trades']
    original=old['databases']['trading.db']['tables']['trades']
    assert set(original['row_hashes']).issubset(db['row_hashes']) and db['count']==2
    for file in ['settings.json','credentials.json','strategies.json','reservations.json']:
        assert (rollback/file).read_bytes()==(source/file).read_bytes()
    assert latest['source_unchanged'] and old['source_unchanged']

    from trading.paper_capital import paper_available_funds
    funds=paper_available_funds(1000,t.paper_positions['okx'],venue='okx',quote='USDT',ledger_file=rollback/'ledger.jsonl')
    assert funds==before_funds
    assert funds['realized_net_pnl']<0 and funds['paper_session_id']==session['session_id']
    return {'synthetic_only':True,'windows_installation':False,'original_quantity':10,'post_close_quantity':6,'after_public7_loader_and8_restore_quantity':t.paper_positions['okx'][p.symbol].quantity,'ledger_prefix_sha256':hashlib.sha256(prefix).hexdigest(),'ledger_prefix_preserved':True,'close_events':sum(str(row.get('position_id','')).startswith('recovery-position') for row in read_paper_strategy_outcomes(path=rollback/'ledger.jsonl')),'all_outcome_rows':len(read_paper_strategy_outcomes(path=rollback/'ledger.jsonl')),'existing_db_rows':original['count'],'post_upgrade_db_rows':db['count'],'existing_rows_retained':True,'db_integrity_check':'ok','preserved_synthetic_session_id':session['session_id'],'valid_session_store_created_by_start_session':True,'verified_new_period_loss_retained':-75,'available_capital_before_rollback':before_funds['available_capital'],'available_capital_after_restore':funds['available_capital'],'capital_basis':funds['capital_basis'],'open_margin':funds['open_margin'],'latest_backup_used':True,'pre_upgrade_backup_restored_over_new_data':False,'settings_strategy_credentials_reservations_byte_equal':True}


def test_source_format_rollback_retains_post_upgrade_records(tmp_path):
    evidence=source_format_rollback_evidence(tmp_path)
    assert evidence['after_public7_loader_and8_restore_quantity']==6
    assert evidence['post_upgrade_db_rows']==2 and evidence['close_events']==1
