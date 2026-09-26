#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국투자증권 KIS Developers Open API 국내주식 어댑터.

공식 KIS REST 계약의 URL, 인증 헤더, TR ID, 계좌 형식을 이 클래스에서
소유한다. 미래에셋 식별자나 미래에셋 URL은 사용하지 않는다.
"""

import hashlib
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from .mirae_asset_stock_adapter import MiraeAssetStockAdapter

_KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"
_KIS_VTS_URL = "https://openapivts.koreainvestment.com:29443"


class KoreaInvestmentStockAdapter(MiraeAssetStockAdapter):
    """KIS 공식 REST 계약 구현 (실전/모의 서버 지원)."""

    # KIS rejects repeated access-token issuance (EGW00133).  Dashboard reads,
    # settings checks and a worker can otherwise construct adjacent adapters
    # and each request a token.  Keep the valid token and issuance cooldown in
    # process memory only; never persist or log the token/secret.
    _token_issue_lock = threading.Lock()
    _shared_token_cache: Dict[str, tuple[str, float]] = {}
    _shared_next_issue_at: Dict[str, float] = {}

    def __init__(self, user_id: str, password: str, cert_password: str = "", account_no: str = "", **kwargs):
        kwargs.setdefault("api_type", "rest")
        kwargs.setdefault("api_version", "kis_openapi_v1")
        super().__init__(user_id, password, cert_password, account_no, **kwargs)
        self.exchange_name = "koreaInvestment"
        self._token_retry_at: float = 0.0
        self._token_limit_notice_at: float = 0.0
        self._configured_etf_symbols = [
            self._normalize_symbol(symbol)
            for symbol in list(kwargs.get("configured_etf_symbols", []) or [])
            if str(symbol or '').strip().isdigit()
            and 5 <= len(str(symbol or '').strip()) <= 8
        ]
        from log_system.log_adapter import log_event
        self._noah_execution_mode = 'unknown'
        self.log_event = lambda category, msg, level="INFO": log_event(
            category, msg, exchange="koreaInvestment", level=level,
            execution_mode=self._noah_execution_mode,
            details={'asset_class':'securities','instrument_type':'stock_or_etf'},
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

    def _token_cache_key(self) -> str:
        # Include both credential halves in the non-reversible cache identity so
        # replacing a secret cannot reuse a token issued for the previous pair.
        material = f"{self._base_url()}|{self.app_key}|{self.app_secret}|{int(self.sandbox)}"
        return hashlib.sha256(material.encode('utf-8')).hexdigest()

    def _apply_shared_token(self, key: str, now: float) -> bool:
        cached = self._shared_token_cache.get(key)
        if not cached:
            return False
        token, expires_at = cached
        if not token or now >= float(expires_at or 0.0) - 60:
            self._shared_token_cache.pop(key, None)
            return False
        self._access_token = token
        self._token_expires_at = float(expires_at)
        return True

    def _refresh_token(self) -> bool:
        http = self._get_http()
        if not http or not self.app_key or not self.app_secret:
            return False
        key = self._token_cache_key()
        with self._token_issue_lock:
            now = time.time()
            if self._apply_shared_token(key, now):
                return True
            next_allowed = max(
                float(self._shared_next_issue_at.get(key, 0.0) or 0.0),
                float(self._token_retry_at or 0.0),
            )
            if now < next_allowed:
                self._token_retry_at = next_allowed
                if now >= self._token_limit_notice_at:
                    wait_seconds = max(1, int(next_allowed - now + 0.999))
                    self.log_event(
                        'system',
                        f'KIS 토큰 발급 제한 대기 중 - {wait_seconds}초 뒤 자동 재시도 (API 키 오류 아님)',
                        level='WARNING',
                    )
                    self._token_limit_notice_at = now + 30.0
                return False

            # Reserve the one-minute issuance window before the network call so
            # concurrent account refreshes cannot issue a second request.
            self._shared_next_issue_at[key] = now + 60.0
            self._token_retry_at = now + 60.0
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
                    error_code = str(data.get('error_code') or data.get('error') or '').strip()
                    description = str(data.get('error_description') or data.get('message') or '').strip()
                    if error_code == 'EGW00133' or '1분당 1회' in description:
                        self.log_event(
                            'system',
                            'KIS 토큰 발급 제한(EGW00133) - 기존 요청의 60초 창이 끝난 뒤 자동 재시도합니다. API 키 오류가 아닙니다.',
                            level='WARNING',
                        )
                    else:
                        # Do not include request credentials; the provider data
                        # contains only its sanitized error contract here.
                        self.log_event(
                            'system',
                            f'KIS 토큰 발급 실패: code={error_code or "unknown"}, description={description or "응답 없음"}',
                            level='ERROR',
                        )
                    return False
                expires_at = time.time() + int(data.get('expires_in') or 86400)
                self._access_token = token
                self._token_expires_at = expires_at
                self._shared_token_cache[key] = (token, expires_at)
                return True
            except Exception as exc:
                self.log_event('system', f'KIS 토큰 요청 오류: {exc}', level='ERROR')
                return False

    def _tr_id(self, path: str, *, method: str, body: Optional[Dict[str, Any]] = None) -> str:
        real_ids = {
            '/uapi/domestic-stock/v1/quotations/inquire-price': 'FHKST01010100',
            '/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice': 'FHKST03010100',
            '/uapi/etfetn/v1/quotations/inquire-price': 'FHPST02400000',
            '/uapi/etfetn/v1/quotations/nav-comparison-trend': 'FHPST02440000',
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
        history = path == '/uapi/domestic-stock/v1/trading/inquire-daily-ccld'
        headers = self._request_headers(tr_id) if tr_id else {}
        if history:
            if (params or {}).get('CTX_AREA_NK100'):
                headers['tr_cont'] = 'N'
            # Historical and recent queries use different official TR IDs.
            import calendar
            from zoneinfo import ZoneInfo
            today = datetime.now(ZoneInfo('Asia/Seoul')).date()
            month = today.year * 12 + today.month - 1 - 3
            year, zero_month = divmod(month,12)
            cutoff = today.replace(year=year,month=zero_month+1,
                                   day=min(today.day,calendar.monthrange(year,zero_month+1)[1]))
            if str((params or {}).get('INQR_END_DT') or '') < cutoff.strftime('%Y%m%d'):
                headers['tr_id'] = 'VTSC9215R' if str(tr_id).startswith('V') else 'CTSC9215R'
        if not http or not tr_id or not self._ensure_token():
            return {}
        headers['authorization'] = f'Bearer {self._access_token}'
        try:
            response = http.get(
                f'{self._base_url()}{path}', params=params or {},
                headers=headers, timeout=self.request_timeout,
            )
            if getattr(response, 'status_code', None) == 401 and self._refresh_token():
                headers['authorization'] = f'Bearer {self._access_token}'
                response = http.get(
                    f'{self._base_url()}{path}', params=params or {},
                    headers=headers, timeout=self.request_timeout,
                )
            data = self._response_to_dict(response, method='GET', path=path)
            if history and isinstance(data,dict):
                continuation = (getattr(response,'headers',{}) or {}).get('tr_cont')
                if continuation is not None: data['_tr_cont'] = continuation
            return data
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
        self.last_error = ""
        cano, product = self._account_parts()
        if not self.app_key or not self.app_secret:
            self.is_connected = False
            self.last_error = "kis_credentials_missing"
            self.log_event('system', 'KIS 연결 설정 오류: 앱키와 앱시크릿이 필요합니다.', level='ERROR')
            return False
        if len(cano) != 8 or len(product) != 2:
            self.is_connected = False
            self.last_error = "kis_account_format_invalid"
            self.log_event('system', 'KIS 연결 설정 오류: 계좌번호는 8+2자리 형식이어야 합니다.', level='ERROR')
            return False
        self.is_connected = bool(self._ensure_token())
        if self.is_connected:
            self.log_event('system', f'KIS 인증 연결 확인 · {"모의 서버" if self.sandbox else "실전 서버"} · 계좌 조회와 주문 권한은 별도 확인')
        else:
            self.last_error = "kis_token_unavailable"
            self.log_event('system', 'KIS 인증 실패 · API 키·서버 선택·토큰 발급 제한을 확인하세요.', level='ERROR')
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

    def get_etf_list(self) -> List[Dict[str, Any]]:
        """Use the public master also for automatic ETF selection."""
        if self._configured_etf_symbols:
            return [
                {"code": code, "symbol": code, "name": code, "is_etf": True,
                 "source": "configured_watchlist"}
                for code in list(dict.fromkeys(self._configured_etf_symbols))
            ]
        return super().get_etf_list()

    def get_etf_realtime_metrics(self, symbol: str) -> Dict[str, Any]:
        if not self.is_connected:
            return {'status': 'error', 'error': 'not_connected'}
        code = self._normalize_symbol(symbol)
        response = self._get('/uapi/etfetn/v1/quotations/inquire-price', params={
            'FID_COND_MRKT_DIV_CODE': 'J',
            'FID_INPUT_ISCD': code,
        })
        if not self._kis_success(response):
            return {'status': 'error', 'error': response.get('msg1') or 'etf_quote_not_available'}
        item = response.get('output') or {}
        if isinstance(item, list):
            item = item[0] if item else {}
        return {
            'code': code,
            'current_price': abs(self._to_float(item.get('stck_prpr'))),
            'change_rate': self._to_float(item.get('prdy_ctrt')),
            'volume': self._to_int(item.get('acml_vol')),
            'trade_value': self._to_float(item.get('acml_tr_pbmn')),
            'nav': self._to_float(item.get('nav') or item.get('prdy_last_nav')),
            'tracking_error': self._to_float_or_none(item.get('trc_errt')),
            'nav_gap': self._to_float_or_none(item.get('dprt')),
            'base_index': item.get('etf_rprs_bstp_kor_isnm') or '',
            'timestamp': datetime.now().isoformat(),
            'status': 'ok',
        }

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
