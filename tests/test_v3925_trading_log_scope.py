"""Visible log ownership must be stronger than ambiguous finance vocabulary."""
from datetime import datetime

import pytest

from web_platform.application_services import ApplicationServices, DetachedRuntimeBridge


CRYPTO = ['binance', 'upbit', 'bithumb', 'coinone', 'bybit', 'okx', 'bitget']
STOCK = ['kiwoom', 'shinhan', 'mirae', 'kis']


@pytest.mark.parametrize('venue', CRYPTO)
def test_explicit_crypto_owner_keeps_symbol_selection_logs(tmp_path, monkeypatch, venue):
    path = tmp_path / 'trading.log'
    today = datetime.now().astimezone().date().isoformat()
    path.write_text(f'{today} 12:00:00 INFO - 거래 대상 종목 분석 완료 (ex={venue})\n'
                    f'{today} 12:00:01 INFO - 증권 주문 (ex=kiwoom)\n')
    monkeypatch.setattr('web_platform.application_services.get_log_file_path', lambda: str(path))
    services = ApplicationServices(account='scope-fixture', runtime_bridge=DetachedRuntimeBridge())
    rows = services.log_snapshot(service='blockchain', source='all')['lines']
    assert len(rows) == 1
    assert rows[0]['exchange'] == venue


@pytest.mark.parametrize('venue', STOCK)
def test_authoritative_broker_file_keeps_neutral_rows_and_rejects_crypto(tmp_path, monkeypatch, venue):
    path = tmp_path / 'broker.log'
    today = datetime.now().astimezone().date().isoformat()
    path.write_text(f'{today} 12:00:00 INFO - 분석 시작\n'
                    f'{today} 12:00:01 INFO - 연결 실패 (ex=global)\n'
                    f'{today} 12:00:02 INFO - 코인 분석 (ex=upbit)\n')
    monkeypatch.setattr('web_platform.application_services.get_exchange_log_file_path', lambda _: str(path))
    services = ApplicationServices(account='scope-fixture', runtime_bridge=DetachedRuntimeBridge())
    rows = services.log_snapshot(service='stock', source=venue)['lines']
    assert len(rows) == 2
    assert all('코인 분석' not in row['message'] for row in rows)


def test_shared_stock_log_still_rejects_neutral_and_explicit_crypto_rows(tmp_path, monkeypatch):
    path = tmp_path / 'trading.log'
    today = datetime.now().astimezone().date().isoformat()
    path.write_text(f'{today} 12:00:00 INFO - 연결 완료\n'
                    f'{today} 12:00:01 INFO - 거래 종목 분석 (ex=binance)\n'
                    f'{today} 12:00:02 INFO - 분석 시작 (ex=koreaInvestment)\n')
    monkeypatch.setattr('web_platform.application_services.get_log_file_path', lambda: str(path))
    services = ApplicationServices(account='scope-fixture', runtime_bridge=DetachedRuntimeBridge())
    rows = services.log_snapshot(service='stock', source='all')['lines']
    assert len(rows) == 1 and rows[0]['exchange'] == 'koreainvestment'
