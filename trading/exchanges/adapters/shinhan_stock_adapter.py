#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
신한증권 주식/ETF 어댑터
신한금융투자 SOL Trading Open API (REST) 연동

인증 방식:
  - app_key + app_secret → POST /oauth/token → access_token
  - 이후 모든 요청 헤더에 Authorization: Bearer {access_token}

api_type 값:
  'rest'    : SOL Trading REST API (권장, 웹/macOS/Windows 공용)
  'openapi' : 내부 통일 표기, 실제로는 rest 동일 처리

주요 공식 문서:
  https://open.shinhangroup.com/sol-trading-api
"""

import importlib
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from ..interfaces.stock_exchange import StockExchange

# 신한 REST API 기본 URL (실제 엔드포인트는 공식 문서 기준으로 추후 확정)
_SHINHAN_BASE_URL = 'https://openapi.shinhan.com'
_SHINHAN_SANDBOX_URL = 'https://sandbox-openapi.shinhan.com'


class ShinhanStockAdapter(StockExchange):
    """신한증권 주식/ETF 어댑터 — REST 기반"""

    def __init__(self, user_id: str, password: str, cert_password: str = '', account_no: str = '', **kwargs):
        super().__init__('shinhan')
        self.user_id = user_id
        self.password = password
        self.cert_password = cert_password
        self.account_no = account_no
        self.api_type = kwargs.get('api_type', 'rest')
        self.api_version = kwargs.get('api_version', 'solapi')
        self.app_key: str = kwargs.get('app_key', '') or ''
        self.app_secret: str = kwargs.get('app_secret', '') or ''
        # 테스트/확장용 backend 주입 지원
        self._http: Any = kwargs.get('backend_client')
        self._access_token: str = ''
        self._token_expires_at: float = 0.0
        self.request_timeout: int = int(kwargs.get('request_timeout', 10) or 10)
        self.sandbox: bool = bool(kwargs.get('sandbox', False))
        self.logger = logging.getLogger(__name__)
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level='INFO': log_event(category, msg, exchange='shinhan', level=level)

        # ETF 코드 범위 (한국거래소 기준 — 키움과 동일 범위 공유)
        self.etf_code_ranges = [
            (69500, 69599),
            (102000, 102999),
            (105000, 115999),
            (117000, 117999),
            (122000, 122999),
            (143000, 143999),
            (261000, 261999),
            (292000, 292999),
            (295000, 295999),
        ]

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _base_url(self) -> str:
        return _SHINHAN_SANDBOX_URL if self.sandbox else _SHINHAN_BASE_URL

    def _normalize_symbol(self, symbol: Any) -> str:
        return str(symbol or '').strip().zfill(6)

    def _to_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value in (None, ''):
                return default
            return float(str(value).replace(',', '').replace('%', '').strip() or default)
        except Exception:
            return default

    def _to_int(self, value: Any, default: int = 0) -> int:
        try:
            if value in (None, ''):
                return default
            return int(float(str(value).replace(',', '').strip() or default))
        except Exception:
            return default

    def _get_http(self):
        """requests 세션 반환 (backend 주입 우선)"""
        if self._http is not None:
            return self._http
        try:
            requests = importlib.import_module('requests')
            session = requests.Session()
            session.headers.update({
                'Content-Type': 'application/json;charset=UTF-8',
                'Accept': 'application/json',
            })
            self._http = session
            return session
        except ImportError:
            self.log_event('system', 'requests 라이브러리가 없습니다. pip install requests', level='ERROR')
            return None

    def _ensure_token(self) -> bool:
        """액세스 토큰 유효 여부 확인 및 갱신."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return True
        return self._refresh_token()

    def _refresh_token(self) -> bool:
        """OAuth 토큰 발급 (신한 SOL API 방식)."""
        http = self._get_http()
        if not http:
            return False
        try:
            resp = http.post(
                f'{self._base_url()}/oauth/token',
                json={
                    'grant_type': 'client_credentials',
                    'appkey': self.app_key,
                    'secretkey': self.app_secret,
                },
                timeout=self.request_timeout,
            )
            data = resp.json() if hasattr(resp, 'json') else (resp if isinstance(resp, dict) else {})
            token = data.get('access_token') or data.get('token')
            expires_in = int(data.get('expires_in', 86400) or 86400)
            if token:
                self._access_token = str(token)
                self._token_expires_at = time.time() + expires_in
                if hasattr(http, 'headers'):
                    http.headers.update({'Authorization': f'Bearer {self._access_token}'})
                return True
            self.log_event('system', f'신한 토큰 발급 실패: {data}', level='ERROR')
            return False
        except Exception as exc:
            self.log_event('system', f'신한 토큰 요청 오류: {exc}', level='ERROR')
            return False

    def _get(self, path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """GET 요청 공통 래퍼 (토큰 유효성 확인 + 401 자동 갱신)."""
        http = self._get_http()
        if not http:
            return {}
        # 요청 전 토큰 유효성 확인
        self._ensure_token()
        try:
            resp = http.get(
                f'{self._base_url()}{path}',
                params=params or {},
                timeout=self.request_timeout,
            )
            # 401 Unauthorized → 토큰 갱신 후 1회 재시도
            status = getattr(resp, 'status_code', None)
            if status == 401:
                self.log_event('system', f'신한 GET {path} 401 → 토큰 갱신 후 재시도', level='WARNING')
                if self._refresh_token():
                    resp = http.get(
                        f'{self._base_url()}{path}',
                        params=params or {},
                        timeout=self.request_timeout,
                    )
            return resp.json() if hasattr(resp, 'json') else (resp if isinstance(resp, dict) else {})
        except Exception as exc:
            self.log_event('system', f'신한 GET {path} 오류: {exc}', level='ERROR')
            return {}

    def _post(self, path: str, body: Optional[Dict] = None) -> Dict[str, Any]:
        """POST 요청 공통 래퍼 (토큰 유효성 확인 + 401 자동 갱신)."""
        http = self._get_http()
        if not http:
            return {}
        # 요청 전 토큰 유효성 확인 (토큰 갱신 경로 자신은 제외)
        if path != '/oauth/token':
            self._ensure_token()
        try:
            resp = http.post(
                f'{self._base_url()}{path}',
                json=body or {},
                timeout=self.request_timeout,
            )
            status = getattr(resp, 'status_code', None)
            if status == 401 and path != '/oauth/token':
                self.log_event('system', f'신한 POST {path} 401 → 토큰 갱신 후 재시도', level='WARNING')
                if self._refresh_token():
                    resp = http.post(
                        f'{self._base_url()}{path}',
                        json=body or {},
                        timeout=self.request_timeout,
                    )
            return resp.json() if hasattr(resp, 'json') else (resp if isinstance(resp, dict) else {})
        except Exception as exc:
            self.log_event('system', f'신한 POST {path} 오류: {exc}', level='ERROR')
            return {}

    def _parse_position(self, item: Dict[str, Any]) -> Dict[str, Any]:
        code = self._normalize_symbol(
            item.get('isuSrtCd') or item.get('종목코드') or item.get('code', '')
        )
        current_price = abs(self._to_float(item.get('prcsBf') or item.get('현재가') or item.get('current_price')))
        avg_price = abs(self._to_float(item.get('buyAvrPrc') or item.get('매입단가') or item.get('avg_price')))
        quantity = self._to_int(item.get('holdCnt') or item.get('보유수량') or item.get('quantity'))
        eval_amount = self._to_float(item.get('evluAmt') or item.get('평가금액') or item.get('eval_amount'))
        pnl = self._to_float(item.get('evluPfls') or item.get('평가손익') or item.get('pnl'))
        pnl_rate = self._to_float(item.get('evluPflsRt') or item.get('수익률') or item.get('pnl_rate'))
        return {
            'code': code,
            'name': item.get('isuNm') or item.get('종목명') or item.get('name', code),
            'quantity': quantity,
            'avg_price': avg_price,
            'current_price': current_price,
            'eval_amount': eval_amount or current_price * quantity,
            'pnl': pnl,
            'pnl_rate': pnl_rate,
            'is_etf': self.is_etf(code),
            'status': 'ok',
        }

    def _parse_order(self, item: Dict[str, Any]) -> Dict[str, Any]:
        code = self._normalize_symbol(
            item.get('isuSrtCd') or item.get('종목코드') or item.get('code', '')
        )
        side_raw = item.get('buySellDvCd') or item.get('매매구분') or item.get('side', '')
        side = 'BUY' if str(side_raw) in ('1', 'buy', 'BUY', '매수') else 'SELL'
        return {
            'order_id': str(item.get('ordNo') or item.get('주문번호') or item.get('order_id', '')).strip(),
            'symbol': code,
            'name': item.get('isuNm') or item.get('종목명') or item.get('name', code),
            'side': side,
            'quantity': self._to_int(item.get('ordQty') or item.get('주문수량') or item.get('quantity')),
            'filled_quantity': self._to_int(item.get('execQty') or item.get('체결수량') or item.get('filled_quantity')),
            'unfilled_quantity': self._to_int(item.get('unexecQty') or item.get('미체결수량') or item.get('unfilled_quantity')),
            'price': abs(self._to_float(item.get('ordPrc') or item.get('주문단가') or item.get('price'))),
            'status': item.get('ordStatCd') or item.get('주문상태') or item.get('status', 'unknown'),
            'timestamp': item.get('ordDt') or item.get('주문일시') or item.get('timestamp', ''),
        }
    
    # ------------------------------------------------------------------
    # StockExchange 인터페이스 구현
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """신한 SOL Trading API 토큰 발급 및 계좌 확인."""
        try:
            self.log_event('system', f'신한증권 연결 시도 중... (type={self.api_type}, version={self.api_version})')

            # app_key/secret 우선, 없으면 user_id/password fallback
            if not (self.app_key and self.app_secret) and not (self.user_id and self.password):
                self.log_event('system', '신한증권 인증 정보가 설정되지 않음 — 연결 건너뜀')
                return False

            # backend 주입 시 (테스트용)
            if self._http is not None and hasattr(self._http, '_mock_token'):
                self._access_token = self._http._mock_token
                self._token_expires_at = time.time() + 86400
                self.is_connected = True
                self.log_event('system', '신한증권 연결 성공 (주입 backend)')
                return True

            if not self._ensure_token():
                self.log_event('system', '신한증권 토큰 발급 실패', level='ERROR')
                return False

            # 계좌번호 자동 조회
            if not self.account_no:
                try:
                    data = self._get('/v1/account/domestic/list')
                    accounts = data.get('accounts') or data.get('accList') or []
                    if accounts and isinstance(accounts, list):
                        self.account_no = str(accounts[0].get('accNo') or accounts[0].get('accountNo') or '').strip()
                except Exception:
                    pass

            self.is_connected = True
            account_state = 'configured' if self.account_no else 'unavailable'
            self.log_event('system', f'신한증권 연결 성공 (account: {account_state})')
            return True

        except Exception as e:
            self.log_event('system', f'신한증권 연결 실패: {e}', level='ERROR')
            return False

    def health_check(self) -> Dict[str, Any]:
        """연결 상태 경량 확인 (토큰 유효 여부 + 실제 API 호출).

        Returns:
            {'ok': bool, 'latency_ms': float, 'reason': str}
        """
        import time as _time
        start = _time.monotonic()
        try:
            token_ok = self._ensure_token()
            if not token_ok:
                return {'ok': False, 'latency_ms': 0.0, 'reason': '토큰 갱신 실패'}
            # 경량 API 호출: 잔고 조회 (계좌 없으면 계좌목록 조회)
            path = '/v1/account/domestic/balance'
            data = self._get(path, params={'accountNo': self.account_no} if self.account_no else {})
            elapsed_ms = (_time.monotonic() - start) * 1000
            ok = isinstance(data, dict) and bool(data)
            reason = 'ok' if ok else f'빈 응답 (path={path})'
            return {'ok': ok, 'latency_ms': round(elapsed_ms, 1), 'reason': reason}
        except Exception as exc:
            elapsed_ms = (_time.monotonic() - start) * 1000
            return {'ok': False, 'latency_ms': round(elapsed_ms, 1), 'reason': str(exc)}

    def get_stock_list(self, market: str = 'KOSPI') -> List[Dict[str, Any]]:
        """주식 목록 조회."""
        try:
            if not self.is_connected:
                return []
            market_cd = {'KOSPI': '1', 'KOSDAQ': '2'}.get((market or 'KOSPI').upper(), '1')
            data = self._get('/v1/market/domestic/stock-list', params={'marketCd': market_cd})
            items = data.get('stocks') or data.get('isuList') or []
            results = []
            for item in items:
                code = self._normalize_symbol(item.get('isuSrtCd') or item.get('code', ''))
                if not code or self.is_etf(code):
                    continue
                results.append({
                    'code': code,
                    'name': item.get('isuNm') or item.get('name', code),
                    'market': market,
                    'current_price': abs(self._to_float(item.get('clsprc') or item.get('current_price'))),
                    'volume': self._to_int(item.get('acmlVol') or item.get('volume')),
                    'is_etf': False,
                    'status': 'ok',
                })
            return results
        except Exception as e:
            self.log_event('system', f'신한 주식 목록 조회 실패: {e}', level='ERROR')
            return []

    def get_etf_list(self) -> List[Dict[str, Any]]:
        """ETF 목록 조회."""
        try:
            if not self.is_connected:
                return []
            data = self._get('/v1/market/domestic/etf-list')
            items = data.get('etfs') or data.get('etfList') or []
            results = []
            for item in items:
                code = self._normalize_symbol(item.get('isuSrtCd') or item.get('code', ''))
                if not code:
                    continue
                results.append({
                    'code': code,
                    'name': item.get('isuNm') or item.get('name', code),
                    'market': 'ETF',
                    'current_price': abs(self._to_float(item.get('clsprc') or item.get('current_price'))),
                    'nav': self._to_float(item.get('nav')),
                    'tracking_error': self._to_float_or_none(item.get('trcErrRt') or item.get('tracking_error')),
                    'base_index': item.get('bchidxNm') or item.get('base_index', ''),
                    'trade_value': self._to_float(item.get('acmlTrPbmn') or item.get('trade_value') or 0),
                    'expense_ratio': self._to_float(item.get('totFeeRt') or item.get('expense_ratio') or 0) or None,
                    'is_etf': True,
                    'status': 'ok',
                })
            return results
        except Exception as e:
            self.log_event('system', f'신한 ETF 목록 조회 실패: {e}', level='ERROR')
            return []

    def is_etf(self, symbol: str) -> bool:
        """ETF 여부 확인."""
        try:
            code_int = int(symbol)
            for start, end in self.etf_code_ranges:
                if start <= code_int <= end:
                    return True
            return False
        except (ValueError, TypeError):
            return False

    def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """주식/ETF 종목 정보 조회."""
        try:
            if not self.is_connected:
                return {'status': 'error', 'error': 'not_connected'}
            symbol = self._normalize_symbol(symbol)
            data = self._get('/v1/market/domestic/stock-info', params={'isuSrtCd': symbol})
            if not data:
                return {'status': 'error', 'error': 'no_data'}
            current_price = abs(self._to_float(data.get('clsprc') or data.get('current_price')))
            return {
                'code': symbol,
                'name': data.get('isuNm') or data.get('name', symbol),
                'market': data.get('mktNm') or data.get('market', ''),
                'current_price': current_price,
                'prev_close': abs(self._to_float(data.get('prevClsprc') or data.get('prev_close'))),
                'change_rate': self._to_float(data.get('flucRt') or data.get('change_rate')),
                'volume': self._to_int(data.get('acmlVol') or data.get('volume')),
                'is_etf': self.is_etf(symbol),
                'status': 'ok',
            }
        except Exception as e:
            self.log_event('system', f'신한 종목정보 조회 실패: {symbol} - {e}', level='ERROR')
            return {'status': 'error', 'error': str(e)}

    def get_realtime_price(self, symbol: str) -> Dict[str, Any]:
        """실시간 시세 조회."""
        try:
            if not self.is_connected:
                return {'status': 'error', 'error': 'not_connected'}
            symbol = self._normalize_symbol(symbol)
            data = self._get('/v1/market/domestic/price', params={'isuSrtCd': symbol})
            if not data:
                return {'status': 'error', 'error': 'no_data'}
            return {
                'code': symbol,
                'current_price': abs(self._to_float(data.get('stckPrpr') or data.get('current_price'))),
                'change_rate': self._to_float(data.get('prdy_ctrt') or data.get('change_rate')),
                'volume': self._to_int(data.get('acmlVol') or data.get('volume')),
                'bid_price': abs(self._to_float(data.get('bidPrc') or data.get('bid_price'))),
                'ask_price': abs(self._to_float(data.get('askPrc') or data.get('ask_price'))),
                'trade_value': self._to_float(data.get('acmlTrPbmn') or data.get('trade_value') or 0),
                'timestamp': data.get('stckBsopDt') or data.get('timestamp', ''),
                'status': 'ok',
            }
        except Exception as e:
            self.log_event('system', f'신한 시세 조회 실패: {symbol} - {e}', level='ERROR')
            return {'status': 'error', 'error': str(e)}

    def get_etf_realtime_metrics(self, symbol: str) -> Dict[str, Any]:
        """ETF 실시간 지표 조회 (현재가 + NAV + 추적오차 + 거래대금 통합)."""
        try:
            price_data = self.get_realtime_price(symbol)
            if price_data.get('status') != 'ok':
                return price_data
            # ETF 전용 지표: NAV·추적오차·거래대금은 상세 조회로 보완
            detail = self._get(
                '/v1/market/domestic/etf-info',
                params={'isuSrtCd': self._normalize_symbol(symbol)},
            ) or {}
            return {
                'code': symbol,
                'current_price': price_data.get('current_price', 0),
                'change_rate': price_data.get('change_rate', 0),
                'volume': price_data.get('volume', 0),
                'trade_value': price_data.get('trade_value') or self._to_float(
                    detail.get('acmlTrPbmn') or detail.get('trade_value') or 0
                ),
                'nav': self._to_float(detail.get('nav') or 0),
                'tracking_error': self._to_float_or_none(
                    detail.get('trcErrRt') or detail.get('tracking_error')
                ),
                'expense_ratio': self._to_float_or_none(
                    detail.get('totFeeRt') or detail.get('expense_ratio')
                ),
                'base_index': detail.get('bchidxNm') or detail.get('base_index', ''),
                'timestamp': price_data.get('timestamp', ''),
                'status': 'ok',
            }
        except Exception as e:
            self.log_event('system', f'신한 ETF 실시간 지표 조회 실패: {symbol} - {e}', level='ERROR')
            return {'status': 'error', 'error': str(e)}

    def _to_float_or_none(self, value) -> Optional[float]:
        """None 허용 float 변환."""
        if value is None or value == '':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def get_account_info(self) -> Dict[str, Any]:
        """계정 정보 조회."""
        return {
            'status': 'ok',
            'account_no': self.account_no,
            'user_id': self.user_id,
            'broker': 'shinhan',
            'api_type': self.api_type,
            'api_version': self.api_version,
        }

    def get_balance(self) -> Dict[str, Any]:
        """잔고 조회."""
        try:
            if not self.is_connected:
                return {'status': 'error', 'error': 'not_connected'}
            if not self.account_no:
                return {'status': 'error', 'error': 'account_no_not_set'}
            data = self._get('/v1/account/domestic/balance', params={'accNo': self.account_no})
            if not data:
                return {'status': 'error', 'error': 'balance_not_available'}
            cash = self._to_float(data.get('dncaBlnc') or data.get('ordAblAmt') or data.get('cash'))
            stock_eval = self._to_float(data.get('scts_evlu_amt') or data.get('evluAmt') or data.get('stock_eval'))
            total_assets = self._to_float(data.get('tot_evlu_amt') or data.get('totEvluAmt') or data.get('total_assets'))
            profit_loss = self._to_float(data.get('evlu_pfls_smtl_amt') or data.get('pfls') or data.get('profit_loss'))
            return {
                'account_no': self.account_no,
                'user_id': self.user_id,
                'broker': 'shinhan',
                'api_type': self.api_type,
                'api_version': self.api_version,
                'cash': cash,
                'stock_eval': stock_eval,
                'total_assets': total_assets or cash + stock_eval,
                'profit_loss': profit_loss,
                'profit_rate': self._to_float(data.get('evluPflsRt') or data.get('profit_rate')),
                'status': 'ok',
            }
        except Exception as e:
            self.log_event('system', f'신한 잔고 조회 실패: {e}', level='ERROR')
            return {'status': 'error', 'error': str(e)}

    def get_positions(self) -> List[Dict[str, Any]]:
        """보유 종목 조회."""
        try:
            if not self.is_connected:
                return []
            if not self.account_no:
                return []
            data = self._get('/v1/account/domestic/holdings', params={'accNo': self.account_no})
            items = data.get('holdings') or data.get('hldsList') or []
            return [
                self._parse_position(item)
                for item in items
                if self._to_int(item.get('holdCnt') or item.get('quantity')) > 0
            ]
        except Exception as e:
            self.log_event('system', f'신한 보유종목 조회 실패: {e}', level='ERROR')
            return []

    def place_order(self, symbol: str, side: str, quantity: float,
                   price: Optional[float] = None, order_type: str = 'MARKET') -> Dict[str, Any]:
        """주문 실행."""
        try:
            if not self.is_connected:
                return {'status': 'error', 'error': 'not_connected'}
            if not self.account_no:
                return {'status': 'error', 'error': 'account_no_not_set'}

            symbol = self._normalize_symbol(symbol)
            side_upper = str(side or '').upper()
            order_type_upper = str(order_type or 'MARKET').upper()
            qty = int(quantity)
            if qty <= 0:
                return {'status': 'error', 'error': 'invalid_quantity'}

            order_path = '/v1/order/domestic/buy' if side_upper == 'BUY' else '/v1/order/domestic/sell'
            hoga_tp = '01' if order_type_upper == 'MARKET' else '00'
            order_price = 0 if hoga_tp == '01' else int(price or 0)
            if hoga_tp == '00' and order_price <= 0:
                return {'status': 'error', 'error': 'limit_price_required'}

            body = {
                'accNo': self.account_no,
                'isuSrtCd': symbol,
                'ordQty': qty,
                'ordPrc': order_price,
                'hogaTpCd': hoga_tp,
            }
            resp = self._post(order_path, body)
            order_id = str(resp.get('ordNo') or resp.get('order_id') or '').strip()
            rt_cd = str(resp.get('rt_cd') or resp.get('resultCode') or '0')
            success = rt_cd in ('0', '00', '') or bool(order_id)
            return {
                'status': 'success' if success else 'error',
                'order_id': order_id,
                'symbol': symbol,
                'side': side_upper,
                'quantity': qty,
                'price': float(order_price),
                'order_type': order_type_upper,
                'broker': 'shinhan',
                'api_type': self.api_type,
                'api_version': self.api_version,
                'execution_mode': 'live_api',
                'success': success,
                'raw': resp,
                'error': None if success else resp.get('msg') or 'order_failed',
            }
        except Exception as e:
            self.log_event('system', f'신한 주문 실패: {symbol} - {e}', level='ERROR')
            return {
                'status': 'error',
                'error': str(e),
                'broker': 'shinhan',
                'api_type': self.api_type,
                'api_version': self.api_version,
                'execution_mode': 'live_api',
                'success': False,
            }

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        """주문 취소."""
        try:
            if not self.is_connected or not self.account_no:
                return False
            if not symbol:
                open_orders = self.get_open_orders()
                matched = next(
                    (o for o in open_orders if str(o.get('order_id', '')).strip() == str(order_id).strip()),
                    None,
                )
                if matched:
                    symbol = matched.get('symbol', '')
            if not symbol:
                return False
            resp = self._post('/v1/order/domestic/cancel', {
                'accNo': self.account_no,
                'orgOrdNo': str(order_id),
                'isuSrtCd': self._normalize_symbol(symbol),
            })
            rt_cd = str(resp.get('rt_cd') or resp.get('resultCode') or '0')
            return rt_cd in ('0', '00', '')
        except Exception as e:
            self.log_event('system', f'신한 주문 취소 실패: {order_id} - {e}', level='ERROR')
            return False

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """미체결 주문 조회."""
        try:
            if not self.is_connected or not self.account_no:
                return []
            params: Dict[str, Any] = {'accNo': self.account_no, 'execTpCd': '2'}  # 미체결
            if symbol:
                params['isuSrtCd'] = self._normalize_symbol(symbol)
            data = self._get('/v1/order/domestic/open-orders', params=params)
            items = data.get('orders') or data.get('ordList') or []
            return [self._parse_order(item) for item in items]
        except Exception as e:
            self.log_event('system', f'신한 미체결 조회 실패: {e}', level='ERROR')
            return []

    def get_trade_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """체결 내역 조회."""
        try:
            if not self.is_connected or not self.account_no:
                return []
            today = datetime.now().strftime('%Y%m%d')
            params: Dict[str, Any] = {
                'accNo': self.account_no,
                'strtDt': today,
                'endDt': today,
            }
            if symbol:
                params['isuSrtCd'] = self._normalize_symbol(symbol)
            data = self._get('/v1/order/domestic/history', params=params)
            items = data.get('orders') or data.get('ordList') or []
            trades = [
                self._parse_order(item) for item in items
                if self._to_int(item.get('execQty') or item.get('filled_quantity')) > 0
            ]
            return trades[:limit]
        except Exception as e:
            self.log_event('system', f'신한 거래내역 조회 실패: {e}', level='ERROR')
            return []

    def get_24h_ticker(self, symbol: str) -> Dict[str, Any]:
        """24시간 티커."""
        return self.get_realtime_price(symbol)

    def get_today_trades(self) -> List[Dict[str, Any]]:
        """오늘 체결 내역."""
        return self.get_trade_history(limit=200)

    def get_trading_stats(self) -> Dict[str, Any]:
        """거래 통계 요약."""
        history = self.get_trade_history(limit=500)
        buy_count = sum(1 for t in history if 'BUY' in str(t.get('side', '')).upper())
        sell_count = sum(1 for t in history if 'SELL' in str(t.get('side', '')).upper())
        return {
            'broker': 'shinhan',
            'total_trades': len(history),
            'buy_count': buy_count,
            'sell_count': sell_count,
            'today_trades': len(self.get_today_trades()),
            'open_orders': len(self.get_open_orders()),
            'realized_pnl': 0.0,
            'status': 'ok',
        }
