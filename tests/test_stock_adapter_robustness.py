#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""증권사 어댑터 로버스트니스 단위테스트.

커버 대상:
- ShinhanStockAdapter / MiraeAssetStockAdapter:
  - GET/POST 요청 전 _ensure_token() 호출 여부
  - 401 응답 시 _refresh_token() 후 재시도
  - health_check() 정상/실패 경로
  - 토큰 만료 감지 후 자동 갱신
- StockAnalysisService.run_auto_trade_cycle():
  - api_type/api_version 조합 오류 시 실행 차단
  - 유효 조합 시 정상 실행
"""
from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from trading.exchanges.adapters.shinhan_stock_adapter import ShinhanStockAdapter
from trading.exchanges.adapters.mirae_asset_stock_adapter import MiraeAssetStockAdapter
from trading.exchanges.adapters.stock_mock_adapter import StockMockAdapter
from trading.stock_analysis_service import StockAnalysisService


def test_stock_connect_success_logs_never_embed_full_account_number():
    for relative_path in (
        "trading/exchanges/adapters/shinhan_stock_adapter.py",
        "trading/exchanges/adapters/mirae_asset_stock_adapter.py",
    ):
        source = Path(relative_path).read_text(encoding="utf-8")
        assert '연결 성공 (account: {self.account_no' not in source


# ──────────────────────────────────────────────────────────────────────────────
# 공통 헬퍼
# ──────────────────────────────────────────────────────────────────────────────

def _make_mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """requests.Response 모의 객체 생성."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


def _make_token_response(token: str = "tok_abc", expires_in: int = 86400) -> MagicMock:
    return _make_mock_response({'access_token': token, 'expires_in': expires_in})


SHINHAN_PROFILE = {
    'base_url': 'https://partner.test',
    'token_path': '/oauth/token',
    'sub_channel': 'NOAHAI_TEST',
    'endpoints': {
        'balance': '/balance', 'positions': '/positions', 'price': '/price',
        'buy': '/buy', 'sell': '/sell', 'cancel': '/cancel',
        'open_orders': '/open-orders', 'trade_history': '/trades',
        '/some/path': '/some', '/v1/some': '/some-v1', '/fail': '/fail',
    },
}

MIRAE_PROFILE = {
    'base_url': 'https://partner.test',
    'token_path': '/oauth2/token',
    'endpoints': {
        'positions': '/positions', 'price': '/price', 'order': '/order',
        'cancel': '/cancel', 'open_orders': '/open-orders', 'trade_history': '/trades',
        '/some/path': '/some', '/uapi/test': '/test',
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# ShinhanStockAdapter — 토큰 자동 갱신
# ──────────────────────────────────────────────────────────────────────────────

class TestShinhanAdapterTokenRefresh:
    """신한 어댑터 401 자동 갱신 로직 검증."""

    def _make_adapter(self, mock_http: MagicMock) -> ShinhanStockAdapter:
        adapter = ShinhanStockAdapter(
            user_id='u', password='p',
            app_key='key', app_secret='sec',
            backend_client=mock_http,
            partner_profile=SHINHAN_PROFILE,
        )
        # 미리 유효 토큰 설정
        adapter._access_token = 'old_token'
        adapter._token_expires_at = time.time() + 3600
        if hasattr(mock_http, 'headers'):
            mock_http.headers = {}
        return adapter

    def test_get_ensures_token_before_request(self):
        """_get() 호출 시 _ensure_token()이 먼저 실행되는지."""
        http = MagicMock()
        http.headers = {}
        http.post.return_value = _make_mock_response({'result': 'ok'})
        adapter = self._make_adapter(http)
        with patch.object(adapter, '_ensure_token', return_value=True) as mock_et:
            adapter._get('/some/path')
            mock_et.assert_called_once()

    def test_post_ensures_token_before_request(self):
        """_post() 호출 시 _ensure_token()이 먼저 실행되는지."""
        http = MagicMock()
        http.headers = {}
        http.post.return_value = _make_mock_response({'result': 'ok'})
        adapter = self._make_adapter(http)
        with patch.object(adapter, '_ensure_token', return_value=True) as mock_et:
            adapter._post('/some/path', {})
            mock_et.assert_called_once()

    def test_get_retries_on_401(self):
        """GET 401 응답 시 토큰 갱신 후 재시도한다."""
        http = MagicMock()
        http.headers = {}
        # 첫 요청: 401, 재시도: 200
        http.post.side_effect = [
            _make_mock_response({}, 401),
            _make_mock_response({'data': 'ok'}, 200),
        ]
        adapter = self._make_adapter(http)
        with patch.object(adapter, '_refresh_token', return_value=True) as mock_rt:
            result = adapter._get('/v1/some')
            mock_rt.assert_called_once()
        # 두 번 GET 호출됐어야 함 (첫 시도 + 재시도)
        assert http.post.call_count == 2

    def test_post_retries_on_401(self):
        """POST 401 응답 시 토큰 갱신 후 재시도한다."""
        http = MagicMock()
        http.headers = {}
        http.post.side_effect = [
            _make_mock_response({}, 401),
            _make_mock_response({'data': 'ok'}, 200),
        ]
        adapter = self._make_adapter(http)
        with patch.object(adapter, '_refresh_token', return_value=True) as mock_rt:
            result = adapter._post('/v1/some', {})
            mock_rt.assert_called_once()
        assert http.post.call_count == 2

    def test_unknown_operation_fails_closed(self):
        """계약 프로필에 없는 작업은 외부로 전송하지 않는다."""
        http = MagicMock()
        http.headers = {}
        http.post.return_value = _make_mock_response({}, 401)
        adapter = self._make_adapter(http)
        assert adapter._post('/not-in-contract', {}) == {}
        assert http.post.call_count == 0

    def test_get_returns_empty_on_exception(self):
        """GET 예외 시 빈 dict 반환."""
        http = MagicMock()
        http.headers = {}
        http.post.side_effect = ConnectionError("timeout")
        adapter = self._make_adapter(http)
        result = adapter._get('/fail')
        assert result == {}


# ──────────────────────────────────────────────────────────────────────────────
# ShinhanStockAdapter — health_check
# ──────────────────────────────────────────────────────────────────────────────

class TestShinhanHealthCheck:
    def test_health_check_ok(self):
        """토큰 유효 + API 응답 정상 → ok=True."""
        http = MagicMock()
        http.headers = {}
        http.post.return_value = _make_mock_response({'balance': 1000000})
        adapter = ShinhanStockAdapter(
            user_id='u', password='p',
            app_key='key', app_secret='sec',
            backend_client=http,
            partner_profile=SHINHAN_PROFILE,
        )
        adapter._access_token = 'tok'
        adapter._token_expires_at = time.time() + 3600
        result = adapter.health_check()
        assert result['ok'] is True
        assert 'latency_ms' in result

    def test_health_check_fails_when_no_token(self):
        """토큰 갱신 실패 → ok=False."""
        http = MagicMock()
        http.headers = {}
        # _refresh_token 내부 POST 실패 시뮬레이션
        http.post.return_value = _make_mock_response({}, 200)  # token 필드 없음
        adapter = ShinhanStockAdapter(
            user_id='u', password='p',
            app_key='key', app_secret='sec',
            backend_client=http,
            partner_profile=SHINHAN_PROFILE,
        )
        # 만료된 토큰
        adapter._access_token = ''
        adapter._token_expires_at = 0.0
        result = adapter.health_check()
        assert result['ok'] is False
        assert 'reason' in result

    def test_health_check_empty_response(self):
        """API가 빈 dict 반환 → ok=False."""
        http = MagicMock()
        http.headers = {}
        http.post.return_value = _make_mock_response({})
        adapter = ShinhanStockAdapter(
            user_id='u', password='p',
            app_key='key', app_secret='sec',
            backend_client=http,
            partner_profile=SHINHAN_PROFILE,
        )
        adapter._access_token = 'tok'
        adapter._token_expires_at = time.time() + 3600
        result = adapter.health_check()
        assert result['ok'] is False

    def test_health_check_returns_latency(self):
        """health_check 결과에는 항상 latency_ms가 있어야 한다."""
        http = MagicMock()
        http.headers = {}
        http.post.return_value = _make_mock_response({'data': 1})
        adapter = ShinhanStockAdapter(
            user_id='u', password='p',
            app_key='key', app_secret='sec',
            backend_client=http,
            partner_profile=SHINHAN_PROFILE,
        )
        adapter._access_token = 'tok'
        adapter._token_expires_at = time.time() + 3600
        result = adapter.health_check()
        assert isinstance(result.get('latency_ms'), float)


# ──────────────────────────────────────────────────────────────────────────────
# MiraeAssetStockAdapter — 토큰 자동 갱신
# ──────────────────────────────────────────────────────────────────────────────

class TestMiraeAssetAdapterTokenRefresh:
    def _make_adapter(self, mock_http: MagicMock) -> MiraeAssetStockAdapter:
        adapter = MiraeAssetStockAdapter(
            user_id='u', password='p',
            app_key='key', app_secret='sec',
            backend_client=mock_http,
            partner_profile=MIRAE_PROFILE,
        )
        adapter._access_token = 'old_token'
        adapter._token_expires_at = time.time() + 3600
        if not hasattr(mock_http, 'headers') or mock_http.headers is None:
            mock_http.headers = {}
        return adapter

    def test_get_ensures_token_before_request(self):
        http = MagicMock()
        http.headers = {}
        http.get.return_value = _make_mock_response({'output': []})
        adapter = self._make_adapter(http)
        with patch.object(adapter, '_ensure_token', return_value=True) as mock_et:
            adapter._get('/some/path')
            mock_et.assert_called_once()

    def test_get_retries_on_401(self):
        http = MagicMock()
        http.headers = {}
        http.get.side_effect = [
            _make_mock_response({}, 401),
            _make_mock_response({'output': [{'balance': 500}]}, 200),
        ]
        adapter = self._make_adapter(http)
        with patch.object(adapter, '_refresh_token', return_value=True) as mock_rt:
            result = adapter._get('/uapi/test')
            mock_rt.assert_called_once()
        assert http.get.call_count == 2

    def test_post_retries_on_401(self):
        http = MagicMock()
        http.headers = {}
        http.post.side_effect = [
            _make_mock_response({}, 401),
            _make_mock_response({'rt_cd': '0'}, 200),
        ]
        adapter = self._make_adapter(http)
        with patch.object(adapter, '_refresh_token', return_value=True) as mock_rt:
            adapter._post('/uapi/domestic-stock/v1/trading/order-cash', {})
            mock_rt.assert_called_once()
        assert http.post.call_count == 2

    def test_unknown_operation_fails_closed(self):
        """계약 프로필에 없는 작업은 외부로 전송하지 않는다."""
        http = MagicMock()
        http.headers = {}
        http.post.return_value = _make_mock_response({}, 401)
        adapter = self._make_adapter(http)
        assert adapter._post('/not-in-contract', {}) == {}
        assert http.post.call_count == 0


# ──────────────────────────────────────────────────────────────────────────────
# MiraeAssetStockAdapter — health_check
# ──────────────────────────────────────────────────────────────────────────────

class TestMiraeAssetHealthCheck:
    def test_health_check_ok(self):
        http = MagicMock()
        http.headers = {}
        http.get.return_value = _make_mock_response({'output1': {'dnca_tot_amt': '1000000'}})
        adapter = MiraeAssetStockAdapter(
            user_id='u', password='p',
            app_key='key', app_secret='sec',
            backend_client=http,
            partner_profile=MIRAE_PROFILE,
        )
        adapter._access_token = 'tok'
        adapter._token_expires_at = time.time() + 3600
        result = adapter.health_check()
        assert result['ok'] is True
        assert isinstance(result['latency_ms'], float)

    def test_health_check_no_token(self):
        http = MagicMock()
        http.headers = {}
        http.post.return_value = _make_mock_response({})  # token 없음
        adapter = MiraeAssetStockAdapter(
            user_id='u', password='p',
            app_key='key', app_secret='sec',
            backend_client=http,
            partner_profile=MIRAE_PROFILE,
        )
        adapter._access_token = ''
        adapter._token_expires_at = 0.0
        result = adapter.health_check()
        assert result['ok'] is False

    def test_health_check_exception(self):
        http = MagicMock()
        http.headers = {}
        http.get.side_effect = RuntimeError("connection refused")
        adapter = MiraeAssetStockAdapter(
            user_id='u', password='p',
            app_key='key', app_secret='sec',
            backend_client=http,
            partner_profile=MIRAE_PROFILE,
        )
        adapter._access_token = 'tok'
        adapter._token_expires_at = time.time() + 3600
        result = adapter.health_check()
        assert result['ok'] is False
        # _get()이 예외를 흡수하므로 reason은 '빈 응답' 형태
        assert isinstance(result['reason'], str) and len(result['reason']) > 0


# ──────────────────────────────────────────────────────────────────────────────
# StockAnalysisService — api_type/api_version 실행 경로 검증
# ──────────────────────────────────────────────────────────────────────────────

class TestRunAutoTradeCycleApiComboValidation:
    """run_auto_trade_cycle()의 api_type/api_version 방어 검증 테스트."""

    def _make_service(self, api_type: str = 'rest', api_version: str = 'solapi',
                      exchange_name: str = 'shinhan') -> StockAnalysisService:
        adapter = StockMockAdapter(broker_name='shinhan', latency_ms=0)
        adapter.api_type = api_type
        adapter.api_version = api_version
        adapter.exchange_name = exchange_name
        svc = StockAnalysisService(adapter=adapter)
        return svc

    def test_valid_combo_does_not_block(self):
        """유효 조합(shinhan/partner_rest)은 실행 차단하지 않는다."""
        svc = self._make_service(api_type='partner_rest', api_version='shinhan_openapi_v2', exchange_name='shinhan')
        result = svc.run_auto_trade_cycle(
            symbols=['005930'],
            quantity=1,
            allow_live_order=False,
        )
        # 실행 차단 없이 decisions 키가 있어야 함
        assert 'decisions' in result
        assert result.get('execution_mode') != 'blocked'

    def test_invalid_api_version_blocks_execution(self):
        """존재하지 않는 api_version은 실행을 차단한다."""
        svc = self._make_service(api_type='rest', api_version='INVALID_VERSION', exchange_name='shinhan')
        result = svc.run_auto_trade_cycle(
            symbols=['005930'],
            quantity=1,
            allow_live_order=False,
        )
        assert result.get('execution_mode') == 'blocked'
        assert 'api_combo_invalid' in result.get('blocked_reason', '')

    def test_invalid_api_type_blocks_execution(self):
        """존재하지 않는 api_type은 실행을 차단한다."""
        svc = self._make_service(api_type='INVALID_TYPE', api_version='solapi', exchange_name='shinhan')
        result = svc.run_auto_trade_cycle(
            symbols=['005930'],
            quantity=1,
            allow_live_order=False,
        )
        assert result.get('execution_mode') == 'blocked'

    def test_mock_api_type_skips_validation(self):
        """mock api_type은 검증을 건너뛴다."""
        svc = self._make_service(api_type='mock', api_version='', exchange_name='kiwoom')
        result = svc.run_auto_trade_cycle(
            symbols=['005930'],
            quantity=1,
            allow_live_order=False,
        )
        assert result.get('execution_mode') != 'blocked'

    def test_blocked_result_has_required_keys(self):
        """차단 결과에는 decisions, executed_orders, blocked_reason이 있어야 한다."""
        svc = self._make_service(api_type='rest', api_version='BAD_VER', exchange_name='shinhan')
        result = svc.run_auto_trade_cycle(symbols=['005930'])
        assert 'decisions' in result
        assert 'executed_orders' in result
        assert 'blocked_reason' in result
        assert result['executed_orders'] == 0
        assert result['decisions'] == []

    def test_unknown_exchange_skips_validation(self):
        """exchange_name이 없으면 검증을 건너뛰고 정상 실행."""
        # StockMockAdapter는 super().__init__(broker_name)으로 exchange_name을 설정하므로
        # exchange_name을 직접 덮어써서 빈 값으로 만든다.
        adapter = StockMockAdapter(broker_name='mock', latency_ms=0)
        adapter.exchange_name = ''  # 검증 스킵 조건
        adapter.api_type = 'rest'
        adapter.api_version = 'solapi'
        svc = StockAnalysisService(adapter=adapter)
        result = svc.run_auto_trade_cycle(symbols=['005930'])
        # 빈 exchange_name은 검증 대상 아님 → 차단되지 않아야 함
        assert result.get('execution_mode') != 'blocked'
