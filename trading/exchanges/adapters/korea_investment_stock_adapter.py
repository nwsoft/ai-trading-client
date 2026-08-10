#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국투자증권 KIS Developers Open API 국내주식 어댑터.

공식 KIS REST 계약의 URL, 인증 헤더, TR ID, 계좌 형식을 이 클래스에서
소유한다. 미래에셋 식별자나 미래에셋 URL은 사용하지 않는다.
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from .mirae_asset_stock_adapter import MiraeAssetStockAdapter

_KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"
_KIS_VTS_URL = "https://openapivts.koreainvestment.com:29443"


class KoreaInvestmentStockAdapter(MiraeAssetStockAdapter):
    """KIS 공식 REST 계약 구현 (실전/모의 서버 지원)."""

    def __init__(self, user_id: str, password: str, cert_password: str = "", account_no: str = "", **kwargs):
        kwargs.setdefault("api_type", "rest")
        kwargs.setdefault("api_version", "kis_openapi_v1")
        super().__init__(user_id, password, cert_password, account_no, **kwargs)
        self.exchange_name = "koreaInvestment"
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level="INFO": log_event(
            category, msg, exchange="koreaInvestment", level=level
        )

    def _base_url(self) -> str:
        return _KIS_VTS_URL if self.sandbox else _KIS_BASE_URL

    def _account_parts(self) -> tuple[str, str]:
        digits = ''.join(ch for ch in str(self.account_no or '') if ch.isdigit())
        return digits[:8], (digits[8:10] or '01')

    def get_live_readiness(self) -> tuple[bool, str]:
        cano, product = self._account_parts()
        if not self.app_key or not self.app_secret:
            return False, 'KIS 앱키와 앱시크릿을 입력해야 합니다.'
        if len(cano) != 8 or len(product) != 2:
            return False, 'KIS 계좌번호를 8자리 계좌 + 2자리 상품코드 형식으로 입력해야 합니다.'
        if not self.is_connected:
            return False, 'KIS API 연결이 완료되지 않았습니다.'
        return True, ''

    def _refresh_token(self) -> bool:
        http = self._get_http()
        if not http or not self.app_key or not self.app_secret:
            return False
        try:
            response = http.post(
                f'{self._base_url()}/oauth2/tokenP',
                json={
                    'grant_type': 'client_credentials',
                    'appkey': self.app_key,
                    'appsecret': self.app_secret,
                },
                headers={'Content-Type': 'application/json; charset=UTF-8'},
                timeout=self.request_timeout,
            )
            data = self._response_to_dict(response, method='POST', path='/oauth2/tokenP')
            token = str(data.get('access_token') or '').strip()
            if not token:
                self.log_event('system', f'KIS 토큰 발급 실패: {data}', level='ERROR')
                return False
            self._access_token = token
            self._token_expires_at = time.time() + int(data.get('expires_in') or 86400)
            return True
        except Exception as exc:
            self.log_event('system', f'KIS 토큰 요청 오류: {exc}', level='ERROR')
            return False

    def _tr_id(self, path: str, *, method: str, body: Optional[Dict[str, Any]] = None) -> str:
        real_ids = {
            '/uapi/domestic-stock/v1/quotations/inquire-price': 'FHKST01010100',
            '/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice': 'FHKST03010100',
            '/uapi/domestic-stock/v1/quotations/inquire-etf-daily': 'FHKST03040100',
            '/uapi/domestic-stock/v1/trading/inquire-balance': 'TTTC8434R',
            '/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl': 'TTTC0084R',
            '/uapi/domestic-stock/v1/trading/inquire-daily-ccld': 'TTTC0081R',
            '/uapi/domestic-stock/v1/trading/order-rvsecncl': 'TTTC0013U',
        }
        if path == '/uapi/domestic-stock/v1/trading/order-cash':
            side = str((body or {}).get('_NOAHAI_SIDE') or '').upper()
            tr_id = 'TTTC0012U' if side == 'BUY' else 'TTTC0011U'
        else:
            tr_id = real_ids.get(path, '')
        if self.sandbox and tr_id and tr_id[0] in {'T', 'C', 'J'}:
            tr_id = 'V' + tr_id[1:]
        return tr_id

    def _request_headers(self, tr_id: str) -> Dict[str, str]:
        return {
            'Content-Type': 'application/json; charset=UTF-8',
            'Accept': 'application/json',
            'authorization': f'Bearer {self._access_token}',
            'appkey': self.app_key,
            'appsecret': self.app_secret,
            'tr_id': tr_id,
            'custtype': 'P',
        }

    def _get(self, path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        http = self._get_http()
        tr_id = self._tr_id(path, method='GET')
        if not http or not tr_id or not self._ensure_token():
            return {}
        try:
            response = http.get(
                f'{self._base_url()}{path}', params=params or {},
                headers=self._request_headers(tr_id), timeout=self.request_timeout,
            )
            if getattr(response, 'status_code', None) == 401 and self._refresh_token():
                response = http.get(
                    f'{self._base_url()}{path}', params=params or {},
                    headers=self._request_headers(tr_id), timeout=self.request_timeout,
                )
            return self._response_to_dict(response, method='GET', path=path)
        except Exception as exc:
            self.log_event('system', f'KIS GET {path} 오류: {exc}', level='ERROR')
            return {}

    def _post(self, path: str, body: Optional[Dict] = None) -> Dict[str, Any]:
        http = self._get_http()
        internal_body = dict(body or {})
        tr_id = self._tr_id(path, method='POST', body=internal_body)
        internal_body.pop('_NOAHAI_SIDE', None)
        if not http or not tr_id or not self._ensure_token():
            return {}
        try:
            response = http.post(
                f'{self._base_url()}{path}', json=internal_body,
                headers=self._request_headers(tr_id), timeout=self.request_timeout,
            )
            if getattr(response, 'status_code', None) == 401 and self._refresh_token():
                response = http.post(
                    f'{self._base_url()}{path}', json=internal_body,
                    headers=self._request_headers(tr_id), timeout=self.request_timeout,
                )
            return self._response_to_dict(response, method='POST', path=path)
        except Exception as exc:
            self.log_event('system', f'KIS POST {path} 오류: {exc}', level='ERROR')
            return {}

    @staticmethod
    def _kis_success(response: Dict[str, Any]) -> bool:
        return isinstance(response, dict) and str(response.get('rt_cd', '')).strip() == '0'

    def connect(self) -> bool:
        cano, product = self._account_parts()
        if not self.app_key or not self.app_secret:
            self.log_event('system', 'KIS 연결 설정 오류: 앱키와 앱시크릿이 필요합니다.', level='ERROR')
            return False
        if len(cano) != 8 or len(product) != 2:
            self.log_event('system', 'KIS 연결 설정 오류: 계좌번호는 8+2자리 형식이어야 합니다.', level='ERROR')
            return False
        self.is_connected = bool(self._ensure_token())
        return self.is_connected

    def get_balance(self) -> Dict[str, Any]:
        if not self.is_connected:
            return {'status': 'error', 'error': 'not_connected'}
        cano, product = self._account_parts()
        data = self._get('/uapi/domestic-stock/v1/trading/inquire-balance', params={
            'CANO': cano, 'ACNT_PRDT_CD': product, 'AFHR_FLPR_YN': 'N', 'OFL_YN': '',
            'INQR_DVSN': '02', 'UNPR_DVSN': '01', 'FUND_STTL_ICLD_YN': 'N',
            'FNCG_AMT_AUTO_RDPT_YN': 'N', 'PRCS_DVSN': '00',
            'CTX_AREA_FK100': '', 'CTX_AREA_NK100': '',
        })
        if not self._kis_success(data):
            return {'status': 'error', 'error': data.get('msg1') or 'balance_not_available'}
        summary = data.get('output2') or []
        item = summary[0] if isinstance(summary, list) and summary else (summary if isinstance(summary, dict) else {})
        cash = self._to_float(item.get('dnca_tot_amt'))
        stock_eval = self._to_float(item.get('scts_evlu_amt'))
        total_assets = self._to_float(item.get('tot_evlu_amt')) or cash + stock_eval
        return {
            'status': 'ok', 'broker': 'koreaInvestment', 'account_no': self.account_no,
            'cash': cash, 'stock_eval': stock_eval, 'total_assets': total_assets,
            'profit_loss': self._to_float(item.get('evlu_pfls_smtl_amt')),
            'profit_rate': self._to_float(item.get('asst_icdc_erng_rt')),
        }

    def place_order(self, symbol: str, side: str, quantity: float,
                    price: Optional[float] = None, order_type: str = 'MARKET') -> Dict[str, Any]:
        if not self.is_connected:
            return {'status': 'error', 'success': False, 'error': 'not_connected'}
        side_upper = str(side or '').upper()
        if side_upper not in {'BUY', 'SELL'}:
            return {'status': 'error', 'success': False, 'error': 'invalid_side'}
        qty = int(quantity)
        if qty <= 0:
            return {'status': 'error', 'success': False, 'error': 'invalid_quantity'}
        order_type_upper = str(order_type or 'MARKET').upper()
        ord_dvsn = '01' if order_type_upper == 'MARKET' else '00'
        order_price = 0 if ord_dvsn == '01' else int(price or 0)
        if ord_dvsn == '00' and order_price <= 0:
            return {'status': 'error', 'success': False, 'error': 'limit_price_required'}
        cano, product = self._account_parts()
        response = self._post('/uapi/domestic-stock/v1/trading/order-cash', {
            '_NOAHAI_SIDE': side_upper, 'CANO': cano, 'ACNT_PRDT_CD': product,
            'PDNO': self._normalize_symbol(symbol), 'ORD_DVSN': ord_dvsn,
            'ORD_QTY': str(qty), 'ORD_UNPR': str(order_price),
            'EXCG_ID_DVSN_CD': 'KRX', 'SLL_TYPE': '01' if side_upper == 'SELL' else '',
            'CNDT_PRIC': '',
        })
        output = response.get('output') if isinstance(response.get('output'), dict) else {}
        success = self._kis_success(response) and bool(output.get('ODNO') or output.get('odno'))
        return {
            'status': 'success' if success else 'error', 'success': success,
            'order_id': str(output.get('ODNO') or output.get('odno') or ''),
            'symbol': self._normalize_symbol(symbol), 'side': side_upper, 'quantity': qty,
            'price': float(order_price), 'order_type': order_type_upper,
            'broker': 'koreaInvestment', 'api_type': self.api_type,
            'api_version': self.api_version, 'execution_mode': 'live_api',
            'raw': response, 'error': None if success else response.get('msg1') or 'order_failed',
        }

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        if not self.is_connected or not str(order_id or '').strip():
            return False
        cano, product = self._account_parts()
        response = self._post('/uapi/domestic-stock/v1/trading/order-rvsecncl', {
            'CANO': cano, 'ACNT_PRDT_CD': product, 'KRX_FWDG_ORD_ORGNO': '',
            'ORGN_ODNO': str(order_id), 'ORD_DVSN': '00', 'RVSE_CNCL_DVSN_CD': '02',
            'ORD_QTY': '0', 'ORD_UNPR': '0', 'QTY_ALL_ORD_YN': 'Y',
            'EXCG_ID_DVSN_CD': 'KRX', 'CNDT_PRIC': '',
        })
        return self._kis_success(response)

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        cano, product = self._account_parts()
        data = self._get('/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl', params={
            'CANO': cano, 'ACNT_PRDT_CD': product, 'INQR_DVSN_1': '1' if symbol else '0',
            'INQR_DVSN_2': '0', 'CTX_AREA_FK100': '', 'CTX_AREA_NK100': '',
        })
        if not self._kis_success(data):
            return []
        items = data.get('output') or []
        parsed = [self._parse_order(item) for item in items if isinstance(item, dict)]
        if symbol:
            wanted = self._normalize_symbol(symbol)
            parsed = [item for item in parsed if item.get('symbol') == wanted]
        return parsed

    def get_trade_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        cano, product = self._account_parts()
        today = datetime.now().strftime('%Y%m%d')
        data = self._get('/uapi/domestic-stock/v1/trading/inquire-daily-ccld', params={
            'CANO': cano, 'ACNT_PRDT_CD': product, 'INQR_STRT_DT': today, 'INQR_END_DT': today,
            'SLL_BUY_DVSN_CD': '00', 'INQR_DVSN': '00', 'PDNO': self._normalize_symbol(symbol) if symbol else '',
            'CCLD_DVSN': '01', 'ORD_GNO_BRNO': '', 'ODNO': '', 'INQR_DVSN_3': '00',
            'INQR_DVSN_1': '', 'CTX_AREA_FK100': '', 'CTX_AREA_NK100': '',
        })
        if not self._kis_success(data):
            return []
        items = data.get('output1') or []
        return [self._parse_order(item) for item in items if isinstance(item, dict)][:max(0, int(limit))]
