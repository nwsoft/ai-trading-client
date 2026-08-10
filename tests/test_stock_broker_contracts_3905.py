from __future__ import annotations

from typing import Any, Dict

from config.settings import migrate_stock_broker_api_contracts
from trading.exchanges.adapters.korea_investment_stock_adapter import KoreaInvestmentStockAdapter
from trading.exchanges.adapters.shinhan_stock_adapter import ShinhanStockAdapter
from trading.exchanges.exchange_factory import ExchangeFactory, SUPPORTED_API_VERSIONS


class Response:
    def __init__(self, data: Dict[str, Any], status_code: int = 200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data


class CaptureHttp:
    def __init__(self):
        self.calls = []
        self.next_get = Response({'rt_cd': '0', 'output': {'stck_prpr': '70000'}})
        self.next_post = Response({'rt_cd': '0', 'output': {'ODNO': '12345'}})

    def get(self, url, **kwargs):
        self.calls.append(('GET', url, kwargs))
        return self.next_get

    def post(self, url, **kwargs):
        self.calls.append(('POST', url, kwargs))
        return self.next_post


def make_kis(http: CaptureHttp, *, sandbox: bool = False) -> KoreaInvestmentStockAdapter:
    adapter = KoreaInvestmentStockAdapter(
        '', '', account_no='1234567801', app_key='app', app_secret='secret',
        backend_client=http, sandbox=sandbox,
    )
    adapter._access_token = 'token'
    adapter._token_expires_at = 99999999999
    adapter.is_connected = True
    return adapter


def test_official_contract_choices_do_not_mix_brokers():
    assert SUPPORTED_API_VERSIONS['kiwoom'] == {
        'openapi_plus': {'pykiwoom': '키움 OpenAPI+ (pykiwoom 드라이버, Windows 전용)'},
        'mock': {'mock': '테스트/데모용 Mock (API 없이 동작)'},
    }
    assert 'xingapi' not in str(SUPPORTED_API_VERSIONS['shinhan']).lower()
    assert 'kis' not in str(SUPPORTED_API_VERSIONS['miraeAsset']).lower()


def test_legacy_settings_are_migrated_without_losing_credentials():
    settings = {
        'stock_broker_configs': {
            'kiwoom': {'api_type': 'openapi', 'api_version': 'kiwoom_api', 'id': 'u'},
            'shinhan': {'api_type': 'openapi', 'api_version': 'xingapi', 'app_key': 'keep'},
            'miraeAsset': {'api_type': 'rest', 'api_version': 'kis', 'account_no': 'keep'},
            'koreaInvestment': {'api_type': 'rest', 'api_version': 'kis', 'app_secret': 'keep'},
        }
    }
    migrated, changed = migrate_stock_broker_api_contracts(settings)
    assert changed
    assert migrated['stock_broker_configs']['kiwoom']['api_type'] == 'openapi_plus'
    assert migrated['stock_broker_configs']['kiwoom']['id'] == 'u'
    assert migrated['stock_broker_configs']['shinhan']['api_version'] == 'shinhan_openapi_v2'
    assert migrated['stock_broker_configs']['shinhan']['enabled'] is False
    assert migrated['stock_broker_configs']['shinhan']['app_key'] == 'keep'
    assert migrated['stock_broker_configs']['miraeAsset']['api_version'] == 'mirae_partner_profile'
    assert migrated['stock_broker_configs']['miraeAsset']['account_no'] == 'keep'
    assert migrated['stock_broker_configs']['koreaInvestment']['api_version'] == 'kis_openapi_v1'
    assert migrated['stock_broker_configs']['koreaInvestment']['app_secret'] == 'keep'


def test_live_permission_requires_global_and_broker_and_runtime():
    common = dict(broker='koreaInvestment', api_type='rest', api_version='kis_openapi_v1')
    assert not ExchangeFactory.evaluate_stock_live_order_permission(
        **common, global_live_flag=False, broker_live_flag=True,
    )[0]
    assert not ExchangeFactory.evaluate_stock_live_order_permission(
        **common, global_live_flag=True, broker_live_flag=False,
    )[0]
    assert not ExchangeFactory.evaluate_stock_live_order_permission(
        **common, global_live_flag=True, broker_live_flag=True,
        adapter_ready=False, adapter_ready_reason='계좌 연결 필요',
    )[0]
    assert ExchangeFactory.evaluate_stock_live_order_permission(
        **common, global_live_flag=True, broker_live_flag=True, adapter_ready=True,
    ) == (True, '')


def test_kis_price_uses_official_headers_and_tr_id():
    http = CaptureHttp()
    adapter = make_kis(http)
    result = adapter.get_realtime_price('005930')
    assert result['status'] == 'ok'
    method, url, kwargs = http.calls[-1]
    assert method == 'GET'
    assert url.endswith('/uapi/domestic-stock/v1/quotations/inquire-price')
    assert kwargs['headers']['tr_id'] == 'FHKST01010100'
    assert kwargs['headers']['appkey'] == 'app'
    assert kwargs['headers']['authorization'] == 'Bearer token'


def test_kis_order_uses_side_specific_real_and_vts_tr_ids():
    real_http = CaptureHttp()
    result = make_kis(real_http).place_order('005930', 'BUY', 1, order_type='MARKET')
    assert result['success'] is True
    _, _, real_kwargs = real_http.calls[-1]
    assert real_kwargs['headers']['tr_id'] == 'TTTC0012U'
    assert real_kwargs['json']['EXCG_ID_DVSN_CD'] == 'KRX'

    vts_http = CaptureHttp()
    result = make_kis(vts_http, sandbox=True).place_order('005930', 'SELL', 1, order_type='MARKET')
    assert result['success'] is True
    _, _, vts_kwargs = vts_http.calls[-1]
    assert vts_kwargs['headers']['tr_id'] == 'VTTC0011U'


def test_kis_missing_success_code_never_reports_order_success():
    http = CaptureHttp()
    http.next_post = Response({'output': {'ODNO': '12345'}})
    result = make_kis(http).place_order('005930', 'BUY', 1)
    assert result['success'] is False
    assert result['status'] == 'error'


def test_shinhan_partner_request_uses_official_hmac_envelope():
    http = CaptureHttp()
    http.next_post = Response({'dataBody': {'resultCode': '00', 'balance': 1}})
    profile = {
        'base_url': 'https://partner.example', 'token_path': '/oauth/token',
        'sub_channel': 'NOAHAI', 'endpoints': {'balance': '/v2/balance'},
    }
    adapter = ShinhanStockAdapter(
        '', '', app_key='client', app_secret='secret', backend_client=http,
        partner_profile=profile,
    )
    adapter._access_token = 'token'
    adapter._token_expires_at = 99999999999
    data = adapter._get('/v1/account/domestic/balance', {'accNo': '123'})
    assert data['balance'] == 1
    method, _, kwargs = http.calls[-1]
    assert method == 'POST'
    assert kwargs['json']['dataHeader']['subChannel'] == 'NOAHAI'
    assert kwargs['json']['dataBody']['accNo'] == '123'
    assert kwargs['headers']['apikey'] == 'client'
    assert kwargs['headers']['hsKey']
