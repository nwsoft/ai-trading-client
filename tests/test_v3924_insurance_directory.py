from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
import json
import sqlite3
import pytest
from trading.insurance_reference_directory import BUNDLED, import_rows, snapshot, validate
from trading.finance_product_intelligence import ProductCatalog, compare_scenario
from trading.finance_discovery import discover
from trading.finance_handoff import FinanceHandoff


def test_novice_browses_real_names_without_turning_references_into_quotes(tmp_path):
    catalog=ProductCatalog(tmp_path/'products.sqlite3').snapshot()
    r=discover({'kind':'insurance'},catalog)
    assert len(r['reference_products'])==7
    assert len({p['provider'] for p in r['reference_products']})==4
    assert not r['products'] and catalog['current_count']==0
    assert all(p['quote_available'] is False and p['ai_processing_allowed'] is True for p in r['reference_products'])
    compared=compare_scenario({'kind':'insurance','profile':{'insurance_kind':'driver','reference_product_ids':['samsung-driver']}},catalog)
    assert compared['best'] is None and compared['candidates']==[]
    assert compared['reference_products'][0]['name']==BUNDLED[0]['name']
    assert any(BUNDLED[0]['name'] in q for q in compared['questions'])
    assert not discover({'kind':'loan'},catalog)['reference_products']


def test_editorial_updates_persist_and_withdrawal_is_not_reseeded(tmp_path):
    path=tmp_path/'catalog.sqlite3'
    row={**BUNDLED[0],'status':'withdrawn','version':'operator-2'}
    import_rows(path,[row])
    for _ in range(2):
        rows=snapshot(path)
        assert next(r for r in rows if r['id']==row['id'])['evidence_status']=='withdrawn'
    r=discover({'kind':'insurance'},{'reference_products':rows})
    assert row['id'] not in [p['id'] for p in r['reference_products']]
    db=sqlite3.connect(path)
    assert db.execute('SELECT origin FROM insurance_references WHERE id=?',(row['id'],)).fetchone()[0]=='operator'
    db.close()


def test_expiry_does_not_invent_freshness_or_personal_premium(tmp_path):
    rows=snapshot(tmp_path/'catalog.sqlite3',now=datetime(2027,1,1,tzinfo=timezone.utc))
    assert all(r['evidence_status']=='review_due' for r in rows)
    assert all('monthly_premium' not in r for r in rows)
    assert rows[0]['observed_at'].startswith('2026-10-04')


@pytest.mark.parametrize('change',[{'monthly_premium':10000},{'review_due':'2030-01-01T00:00:00Z'},{'source_url':'javascript:alert(1)'},{'category':'fake'},{'status':'active'},{'observed_at':'2099-01-01T00:00:00Z'}])
def test_import_rejects_quotes_unreviewed_windows_and_invalid_metadata(change):
    with pytest.raises(ValueError):validate([{**BUNDLED[0],**change}])


def test_import_is_atomic_on_invalid_record(tmp_path):
    path=tmp_path/'catalog.sqlite3'; before=snapshot(path)
    with pytest.raises(ValueError):import_rows(path,[{**BUNDLED[0],'status':'withdrawn'},{**BUNDLED[1],'source_url':'http://invalid'}])
    assert snapshot(path)==before


@pytest.mark.parametrize('ids',['samsung-driver',['samsung-driver']*2,[{}],['x']*21])
def test_invalid_selection_rejected(ids):
    with pytest.raises(ValueError,match='reference_selection'):
        compare_scenario({'kind':'insurance','profile':{'reference_product_ids':ids}})


def test_handoff_resolves_ids_and_respects_scopes(tmp_path):
    directory=tmp_path/'insurance'/'synthetic'
    handoff=FinanceHandoff(SimpleNamespace(directory=directory))
    scenario={'kind':'insurance','profile':{'insurance_kind':'driver','reference_product_ids':['samsung-driver'],'reference_products':[{'name':'INJECTED'}]}}
    packet=handoff._packet(scenario,['comparison'],{},'')
    assert packet['comparison']['reference_products'][0]['name']==BUNDLED[0]['name']
    assert 'INJECTED' not in json.dumps(packet)
    assert packet['comparison']['best'] is None and not packet['comparison']['candidates']
    assert 'reference_products' not in json.dumps(handoff._packet(scenario,['profile'],{},''))


def test_unknown_reference_preserves_explicit_missing_status():
    result=compare_scenario({'kind':'insurance','profile':{'reference_product_ids':['removed']}})
    assert result['reference_products']==[{'id':'removed','name':'이전에 선택한 상품','evidence_status':'unavailable'}]
