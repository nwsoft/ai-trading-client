#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
미래에셋증권 주식/ETF 어댑터
미래에셋증권 Open Trading API (REST) 연동

인증 방식:
  - app_key + app_secret → POST /oauth2/token → access_token
  - 이후 모든 요청 헤더에 Authorization: Bearer {access_token}

api_type 값:
  'rest'    : Open Trading REST API (권장)
  'openapi' : 내부 통일 표기, 실제로는 rest 동일 처리

주요 공식 문서:
  https://tradingopen.miraeasset.com (API 등록 후 제공)
"""

import importlib
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from ..interfaces.stock_exchange import StockExchange

_MIRAEASSET_BASE_URL = 'https://openapi.miraeasset.com'
_MIRAEASSET_SANDBOX_URL = 'https://sandbox-openapi.miraeasset.com'


class MiraeAssetStockAdapter(StockExchange):
    """미래에셋증권 주식/ETF 어댑터 — REST 기반"""

    def __init__(self, user_id: str, password: str, cert_password: str = '', account_no: str = '', **kwargs):
        super().__init__('miraeAsset')
        self.user_id = user_id
        self.password = password
        self.cert_password = cert_password
        self.account_no = account_no
        self.api_type = kwargs.get('api_type', 'rest')
        self.api_version = kwargs.get('api_version', 'openapi_v1')
        self.app_key: str = kwargs.get('app_key', '') or ''
        self.app_secret: str = kwargs.get('app_secret', '') or ''
        self._http: Any = kwargs.get('backend_client')
        self._access_token: str = ''
        self._token_expires_at: float = 0.0
        self.request_timeout: int = int(kwargs.get('request_timeout', 10) or 10)
        self.sandbox: bool = bool(kwargs.get('sandbox', False))
        self.logger = logging.getLogger(__name__)
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level='INFO': log_event(category, msg, exchange='miraeAsset', level=level)

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

    def _broker_label(self) -> str:
        return '한국투자증권' if self.exchange_name == 'koreaInvestment' else '미래에셋증권'

    def _broker_key(self) -> str:
        return 'koreaInvestment' if self.exchange_name == 'koreaInvestment' else 'miraeAsset'

    def _response_to_dict(self, resp: Any, method: str, path: str) -> Dict[str, Any]:
        """HTTP 응답을 안전하게 dict로 변환한다.

        일부 게이트웨이는 200이어도 빈 본문/HTML을 반환할 수 있어 json() 예외를 방어한다.
        """
        if isinstance(resp, dict):
            return resp
        if not hasattr(resp, 'json'):
            return {}
        try:
            data = resp.json()
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            status_code = getattr(resp, 'status_code', 'unknown')
            content_type = ''
            try:
                headers = getattr(resp, 'headers', {}) or {}
                content_type = str(headers.get('Content-Type') or headers.get('content-type') or '')
            except Exception:
                content_type = ''
            body_snippet = ''
            try:
                body_snippet = (getattr(resp, 'text', '') or '').strip()[:180]
            except Exception:
                body_snippet = ''
            self.log_event(
                'system',
                (
                    f"{self._broker_label()} {method} {path} 응답 파싱 실패: {exc} "
                    f"(status={status_code}, content_type={content_type or 'unknown'}, body={body_snippet or '(empty)'})"
                ),
                level='WARNING',
            )
            return {}

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _base_url(self) -> str:
        return _MIRAEASSET_SANDBOX_URL if self.sandbox else _MIRAEASSET_BASE_URL

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
            self.log_event('system', 'requests 라이브러리가 없습니다.', level='ERROR')
            return None

    def _ensure_token(self) -> bool:
        if self._access_token and time.time() < self._token_expires_at - 60:
            return True
        return self._refresh_token()

    def _refresh_token(self) -> bool:
        http = self._get_http()
        if not http:
            return False
        try:
            token_url = f'{self._base_url()}/oauth2/token'
            payloads = [
                {
                    'grant_type': 'client_credentials',
                    'appkey': self.app_key,
                    'appsecret': self.app_secret,
                },
                {
                    'grant_type': 'client_credentials',
                    'appKey': self.app_key,
                    'appSecret': self.app_secret,
                },
            ]

            last_data: Dict[str, Any] = {}
            for payload in payloads:
                for mode in ('json', 'form'):
                    try:
                        if mode == 'json':
                            resp = http.post(token_url, json=payload, timeout=self.request_timeout)
                        else:
                            try:
                                resp = http.post(
                                    token_url,
                                    data=payload,
                                    headers={'Content-Type': 'application/x-www-form-urlencoded'},
                                    timeout=self.request_timeout,
                                )
                            except TypeError:
                                # 테스트용 fake backend 호환: data 인자를 지원하지 않으면 json으로 폴백
                                resp = http.post(token_url, json=payload, timeout=self.request_timeout)

                        data = resp.json() if hasattr(resp, 'json') else (resp if isinstance(resp, dict) else {})
                        last_data = data if isinstance(data, dict) else {}
                        token = last_data.get('access_token') or last_data.get('token')
                        expires_in = int(last_data.get('expires_in', 86400) or 86400)
                        if token:
                            self._access_token = str(token)
                            self._token_expires_at = time.time() + expires_in
                            if hasattr(http, 'headers'):
                                http.headers.update({'Authorization': f'Bearer {self._access_token}'})
                            return True
                    except Exception:
                        continue

            self.log_event('system', f'{self._broker_label()} 토큰 발급 실패: {last_data}', level='ERROR')
            return False
        except Exception as exc:
            self.log_event('system', f'{self._broker_label()} 토큰 요청 오류: {exc}', level='ERROR')
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
                self.log_event('system', f'{self._broker_label()} GET {path} 401 → 토큰 갱신 후 재시도', level='WARNING')
                if self._refresh_token():
                    resp = http.get(
                        f'{self._base_url()}{path}',
                        params=params or {},
                        timeout=self.request_timeout,
                    )
            return self._response_to_dict(resp, method='GET', path=path)
        except Exception as exc:
            self.log_event('system', f'{self._broker_label()} GET {path} 오류: {exc}', level='ERROR')
            return {}

    def _post(self, path: str, body: Optional[Dict] = None) -> Dict[str, Any]:
        """POST 요청 공통 래퍼 (토큰 유효성 확인 + 401 자동 갱신)."""
        http = self._get_http()
        if not http:
            return {}
        # 요청 전 토큰 유효성 확인 (토큰 갱신 경로 자신은 제외)
        if path not in ('/oauth2/token', '/oauth/token'):
            self._ensure_token()
        try:
            resp = http.post(
                f'{self._base_url()}{path}',
                json=body or {},
                timeout=self.request_timeout,
            )
            status = getattr(resp, 'status_code', None)
            if status == 401 and path not in ('/oauth2/token', '/oauth/token'):
                self.log_event('system', f'{self._broker_label()} POST {path} 401 → 토큰 갱신 후 재시도', level='WARNING')
                if self._refresh_token():
                    resp = http.post(
                        f'{self._base_url()}{path}',
                        json=body or {},
                        timeout=self.request_timeout,
                    )
            return self._response_to_dict(resp, method='POST', path=path)
        except Exception as exc:
            self.log_event('system', f'{self._broker_label()} POST {path} 오류: {exc}', level='ERROR')
            return {}

    def _parse_position(self, item: Dict[str, Any]) -> Dict[str, Any]:
        # 미래에셋 Open API 응답 필드명 기준
        code = self._normalize_symbol(
            item.get('pdno') or item.get('stck_shrt_cd') or item.get('종목코드') or item.get('code', '')
        )
        current_price = abs(self._to_float(item.get('prpr') or item.get('현재가') or item.get('current_price')))
        avg_price = abs(self._to_float(item.get('pchs_avg_pric') or item.get('매입단가') or item.get('avg_price')))
        quantity = self._to_int(item.get('hldg_qty') or item.get('보유수량') or item.get('quantity'))
        eval_amount = self._to_float(item.get('evlu_amt') or item.get('평가금액') or item.get('eval_amount'))
        pnl = self._to_float(item.get('evlu_pfls_amt') or item.get('평가손익') or item.get('pnl'))
        pnl_rate = self._to_float(item.get('evlu_pfls_rt') or item.get('수익률') or item.get('pnl_rate'))
        return {
            'code': code,
            'name': item.get('prdt_name') or item.get('종목명') or item.get('name', code),
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
            item.get('pdno') or item.get('stck_shrt_cd') or item.get('종목코드') or item.get('code', '')
        )
        side_raw = item.get('sll_buy_dvsn_cd') or item.get('매도매수') or item.get('side', '')
        side = 'BUY' if str(side_raw) in ('02', 'buy', 'BUY', '매수') else 'SELL'
        return {
            'order_id': str(item.get('odno') or item.get('주문번호') or item.get('order_id', '')).strip(),
            'symbol': code,
            'name': item.get('prdt_name') or item.get('종목명') or item.get('name', code),
            'side': side,
            'quantity': self._to_int(item.get('ord_qty') or item.get('주문수량') or item.get('quantity')),
            'filled_quantity': self._to_int(item.get('tot_ccld_qty') or item.get('체결수량') or item.get('filled_quantity')),
            'unfilled_quantity': self._to_int(item.get('psbl_qty') or item.get('미체결수량') or item.get('unfilled_quantity')),
            'price': abs(self._to_float(item.get('ord_unpr') or item.get('주문단가') or item.get('price'))),
            'status': item.get('ord_dvsn_name') or item.get('주문상태') or item.get('status', 'unknown'),
            'timestamp': item.get('ord_dt') or item.get('주문일시') or item.get('timestamp', ''),
        }
    
    # ------------------------------------------------------------------
    # StockExchange 인터페이스 구현
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """미래에셋 Open Trading API 토큰 발급 및 연결."""
        try:
            self.log_event('system', f'{self._broker_label()} 연결 시도 중... (type={self.api_type}, version={self.api_version})')

            if not (self.app_key and self.app_secret) and not (self.user_id and self.password):
                self.log_event('system', f'{self._broker_label()} 인증 정보가 설정되지 않음 — 연결 건너뜀')
                return False

            if self._http is not None and hasattr(self._http, '_mock_token'):
                self._access_token = self._http._mock_token
                self._token_expires_at = time.time() + 86400
                self.is_connected = True
                self.log_event('system', f'{self._broker_label()} 연결 성공 (주입 backend)')
                return True

            if not self._ensure_token():
                self.log_event('system', f'{self._broker_label()} 토큰 발급 실패', level='ERROR')
                return False

            if not self.account_no:
                try:
                    data = self._get('/uapi/domestic-stock/v1/trading/inquire-account-balance',
                                     params={'CANO': '', 'ACNT_PRDT_CD': '01'})
                    acnts = data.get('output') or []
                    if isinstance(acnts, list) and acnts:
                        self.account_no = str(acnts[0].get('cano') or '').strip()
                    elif isinstance(data, dict):
                        self.account_no = str(data.get('cano') or data.get('CANO') or '').strip()
                except Exception:
                    pass

            self.is_connected = True
            self.log_event('system', f'{self._broker_label()} 연결 성공 (account: {self.account_no or "unknown"})')
            return True

        except Exception as e:
            self.log_event('system', f'{self._broker_label()} 연결 실패: {e}', level='ERROR')
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
            # 경량 API 호출: 잔고 조회
            path = '/uapi/domestic-stock/v1/trading/inquire-balance'
            data = self._get(path, params={
                'CANO': self.account_no,
                'ACNT_PRDT_CD': '01',
                'AFHR_FLPR_YN': 'N',
                'OFL_YN': '',
                'INQR_DVSN': '02',
                'UNPR_DVSN': '01',
                'FUND_STTL_ICLD_YN': 'N',
                'FNCG_AMT_AUTO_RDPT_YN': 'N',
                'PRCS_DVSN': '00',
                'CTX_AREA_FK100': '',
                'CTX_AREA_NK100': '',
            } if self.account_no else {})
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
            market_cd = {'KOSPI': 'J', 'KOSDAQ': 'Q'}.get((market or 'KOSPI').upper(), 'J')
            data = self._get(
                '/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice',
                params={'MRKT_DIV_CD': market_cd},
            )
            items = data.get('output') or data.get('output2') or []
            if isinstance(items, dict):
                items = [items]
            results = []
            for item in items:
                code = self._normalize_symbol(item.get('stck_shrt_cd') or item.get('pdno') or item.get('code', ''))
                if not code or self.is_etf(code):
                    continue
                results.append({
                    'code': code,
                    'name': item.get('prdt_name') or item.get('name', code),
                    'market': market,
                    'current_price': abs(self._to_float(item.get('stck_prpr') or item.get('current_price'))),
                    'volume': self._to_int(item.get('acml_vol') or item.get('volume')),
                    'is_etf': False,
                    'status': 'ok',
                })
            return results
        except Exception as e:
            self.log_event('system', f'{self._broker_label()} 주식목록 조회 실패: {e}', level='ERROR')
            return []

    def get_etf_list(self) -> List[Dict[str, Any]]:
        """ETF 목록 조회."""
        try:
            if not self.is_connected:
                return []
            data = self._get('/uapi/domestic-stock/v1/quotations/inquire-etf-daily')
            items = data.get('output') or data.get('etfList') or []
            if isinstance(items, dict):
                items = [items]
            results = []
            for item in items:
                code = self._normalize_symbol(item.get('stck_shrt_cd') or item.get('pdno') or item.get('code', ''))
                if not code:
                    continue
                results.append({
                    'code': code,
                    'name': item.get('prdt_name') or item.get('name', code),
                    'market': 'ETF',
                    'current_price': abs(self._to_float(item.get('stck_prpr') or item.get('current_price'))),
                    'nav': self._to_float(item.get('nav') or item.get('etf_nav')),
                    'tracking_error': self._to_float_or_none(item.get('trc_errt') or item.get('tracking_error')),
                    'base_index': item.get('bchm_nm') or item.get('base_index', ''),
                    'trade_value': self._to_float(item.get('acml_tr_pbmn') or item.get('trade_value') or 0),
                    'expense_ratio': self._to_float_or_none(item.get('etf_fee_rt') or item.get('expense_ratio')),
                    'is_etf': True,
                    'status': 'ok',
                })
            return results
        except Exception as e:
            self.log_event('system', f'{self._broker_label()} ETF목록 조회 실패: {e}', level='ERROR')
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
        """종목 상세 조회."""
        try:
            if not self.is_connected:
                return {'status': 'error', 'error': 'not_connected'}
            symbol = self._normalize_symbol(symbol)
            data = self._get(
                '/uapi/domestic-stock/v1/quotations/inquire-price',
                params={'FID_COND_MRKT_DIV_CODE': 'J', 'FID_INPUT_ISCD': symbol},
            )
            item = data.get('output') or data
            if isinstance(item, list):
                item = item[0] if item else {}
            if not item:
                return {'status': 'error', 'error': 'no_data'}
            return {
                'code': symbol,
                'name': item.get('prdt_name') or item.get('name', symbol),
                'market': item.get('rprs_mrkt_kor_name') or item.get('market', ''),
                'current_price': abs(self._to_float(item.get('stck_prpr') or item.get('current_price'))),
                'prev_close': abs(self._to_float(item.get('stck_sdpr') or item.get('prev_close'))),
                'change_rate': self._to_float(item.get('prdy_ctrt') or item.get('change_rate')),
                'volume': self._to_int(item.get('acml_vol') or item.get('volume')),
                'is_etf': self.is_etf(symbol),
                'status': 'ok',
            }
        except Exception as e:
            self.log_event('system', f'{self._broker_label()} 종목정보 조회 실패: {symbol} - {e}', level='ERROR')
            return {'status': 'error', 'error': str(e)}

    def get_realtime_price(self, symbol: str) -> Dict[str, Any]:
        """실시간 시세 조회."""
        try:
            if not self.is_connected:
                return {'status': 'error', 'error': 'not_connected'}
            symbol = self._normalize_symbol(symbol)
            data = self._get(
                '/uapi/domestic-stock/v1/quotations/inquire-price',
                params={'FID_COND_MRKT_DIV_CODE': 'J', 'FID_INPUT_ISCD': symbol},
            )
            item = data.get('output') or data
            if isinstance(item, list):
                item = item[0] if item else {}
            if not item:
                return {'status': 'error', 'error': 'no_data'}
            return {
                'code': symbol,
                'current_price': abs(self._to_float(item.get('stck_prpr') or item.get('current_price'))),
                'change_rate': self._to_float(item.get('prdy_ctrt') or item.get('change_rate')),
                'volume': self._to_int(item.get('acml_vol') or item.get('volume')),
                'bid_price': abs(self._to_float(item.get('stck_shpr') or item.get('bid_price'))),
                'ask_price': abs(self._to_float(item.get('stck_mxpr') or item.get('ask_price'))),
                'trade_value': self._to_float(item.get('acml_tr_pbmn') or item.get('trade_value') or 0),
                'timestamp': item.get('stck_bsop_date') or item.get('timestamp', ''),
                'status': 'ok',
            }
        except Exception as e:
            self.log_event('system', f'{self._broker_label()} 시세 조회 실패: {symbol} - {e}', level='ERROR')
            return {'status': 'error', 'error': str(e)}

    def get_etf_realtime_metrics(self, symbol: str) -> Dict[str, Any]:
        """ETF 실시간 지표 조회 (현재가 + NAV + 추적오차 + 거래대금 통합)."""
        try:
            price_data = self.get_realtime_price(symbol)
            if price_data.get('status') != 'ok':
                return price_data
            detail_data = self._get(
                '/uapi/domestic-stock/v1/quotations/inquire-etf-daily',
                params={'FID_COND_MRKT_DIV_CODE': 'J', 'FID_INPUT_ISCD': self._normalize_symbol(symbol)},
            ) or {}
            detail = detail_data.get('output') or detail_data
            if isinstance(detail, list):
                detail = detail[0] if detail else {}
            return {
                'code': symbol,
                'current_price': price_data.get('current_price', 0),
                'change_rate': price_data.get('change_rate', 0),
                'volume': price_data.get('volume', 0),
                'trade_value': price_data.get('trade_value') or self._to_float(
                    detail.get('acml_tr_pbmn') or detail.get('trade_value') or 0
                ),
                'nav': self._to_float(detail.get('nav') or detail.get('etf_nav') or 0),
                'tracking_error': self._to_float_or_none(
                    detail.get('trc_errt') or detail.get('tracking_error')
                ),
                'expense_ratio': self._to_float_or_none(
                    detail.get('etf_fee_rt') or detail.get('expense_ratio')
                ),
                'base_index': detail.get('bchm_nm') or detail.get('base_index', ''),
                'timestamp': price_data.get('timestamp', ''),
                'status': 'ok',
            }
        except Exception as e:
            self.log_event('system', f'{self._broker_label()} ETF 실시간 지표 조회 실패: {symbol} - {e}', level='ERROR')
            return {'status': 'error', 'error': str(e)}

    def _to_float_or_none(self, value) -> 'Optional[float]':
        """None 허용 float 변환."""
        if value is None or value == '':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def get_account_info(self) -> Dict[str, Any]:
        return {
            'status': 'ok',
            'account_no': self.account_no,
            'user_id': self.user_id,
            'broker': self._broker_key(),
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
            data = self._get(
                '/uapi/domestic-stock/v1/trading/inquire-account-balance',
                params={'CANO': self.account_no[:8],
                        'ACNT_PRDT_CD': self.account_no[8:] if len(self.account_no) > 8 else '01'},
            )
            item = data.get('output2') or data.get('output') or data
            if isinstance(item, list):
                item = item[0] if item else {}
            if not item:
                return {'status': 'error', 'error': 'balance_not_available'}
            cash = self._to_float(item.get('dnca_tot_amt') or item.get('cash'))
            stock_eval = self._to_float(item.get('scts_evlu_amt') or item.get('stock_eval'))
            total_assets = self._to_float(item.get('tot_evlu_amt') or item.get('total_assets'))
            profit_loss = self._to_float(item.get('evlu_pfls_smtl_amt') or item.get('profit_loss'))
            return {
                'account_no': self.account_no,
                'user_id': self.user_id,
                'broker': 'miraeAsset',
                'api_type': self.api_type,
                'api_version': self.api_version,
                'cash': cash,
                'stock_eval': stock_eval,
                'total_assets': total_assets or cash + stock_eval,
                'profit_loss': profit_loss,
                'profit_rate': self._to_float(item.get('asst_icdc_erng_rt') or item.get('profit_rate')),
                'status': 'ok',
            }
        except Exception as e:
            self.log_event('system', f'{self._broker_label()} 잔고 조회 실패: {e}', level='ERROR')
            return {'status': 'error', 'error': str(e)}

    def get_positions(self) -> List[Dict[str, Any]]:
        """보유 종목 조회."""
        try:
            if not self.is_connected or not self.account_no:
                return []
            data = self._get(
                '/uapi/domestic-stock/v1/trading/inquire-balance',
                params={
                    'CANO': self.account_no[:8],
                    'ACNT_PRDT_CD': self.account_no[8:] if len(self.account_no) > 8 else '01',
                    'AFHR_FLPR_YN': 'N', 'OFL_YN': '', 'INQR_DVSN': '02', 'UNPR_DVSN': '01',
                    'FUND_STTL_ICLD_YN': 'N', 'FNCG_AMT_AUTO_RDPT_YN': 'N', 'PRCS_DVSN': '00',
                },
            )
            items = data.get('output1') or data.get('holdings') or []
            return [
                self._parse_position(item)
                for item in items
                if self._to_int(item.get('hldg_qty') or item.get('quantity')) > 0
            ]
        except Exception as e:
            self.log_event('system', f'{self._broker_label()} 보유종목 조회 실패: {e}', level='ERROR')
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

            sll_buy_dvsn_cd = '02' if side_upper == 'BUY' else '01'
            ord_dvsn = '00' if order_type_upper == 'LIMIT' else '01'
            order_price = int(price or 0) if ord_dvsn == '00' else 0
            if ord_dvsn == '00' and order_price <= 0:
                return {'status': 'error', 'error': 'limit_price_required'}

            resp = self._post('/uapi/domestic-stock/v1/trading/order-cash', {
                'CANO': self.account_no[:8],
                'ACNT_PRDT_CD': self.account_no[8:] if len(self.account_no) > 8 else '01',
                'PDNO': symbol,
                'ORD_DVSN': ord_dvsn,
                'ORD_QTY': str(qty),
                'ORD_UNPR': str(order_price),
                'SLL_BUY_DVSN_CD': sll_buy_dvsn_cd,
            })
            output = resp.get('output') or resp
            order_id = str(output.get('odno') or output.get('order_id') or '').strip()
            rt_cd = str(resp.get('rt_cd') or '0')
            success = rt_cd in ('0', '00', '') or bool(order_id)
            return {
                'status': 'success' if success else 'error',
                'order_id': order_id,
                'symbol': symbol,
                'side': side_upper,
                'quantity': qty,
                'price': float(order_price),
                'order_type': order_type_upper,
                'broker': self._broker_key(),
                'api_type': self.api_type,
                'api_version': self.api_version,
                'execution_mode': 'live_api',
                'success': success,
                'raw': resp,
                'error': None if success else resp.get('msg1') or 'order_failed',
            }
        except Exception as e:
            self.log_event('system', f'{self._broker_label()} 주문 실패: {symbol} - {e}', level='ERROR')
            return {
                'status': 'error',
                'error': str(e),
                'broker': self._broker_key(),
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
            resp = self._post('/uapi/domestic-stock/v1/trading/order-rvsecncl', {
                'CANO': self.account_no[:8],
                'ACNT_PRDT_CD': self.account_no[8:] if len(self.account_no) > 8 else '01',
                'KRX_FWDG_ORD_ORGNO': '',
                'ORGN_ODNO': str(order_id),
                'ORD_DVSN': '00',
                'RVSE_CNCL_DVSN_CD': '02',
                'ORD_QTY': '0',
                'ORD_UNPR': '0',
                'QTY_ALL_ORD_YN': 'Y',
            })
            rt_cd = str(resp.get('rt_cd') or '0')
            return rt_cd in ('0', '00', '')
        except Exception as e:
            self.log_event('system', f'{self._broker_label()} 주문 취소 실패: {order_id} - {e}', level='ERROR')
            return False

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """미체결 주문 조회."""
        try:
            if not self.is_connected or not self.account_no:
                return []
            params: Dict[str, Any] = {
                'CANO': self.account_no[:8],
                'ACNT_PRDT_CD': self.account_no[8:] if len(self.account_no) > 8 else '01',
                'INQR_STRT_DT': datetime.now().strftime('%Y%m%d'),
                'INQR_END_DT': datetime.now().strftime('%Y%m%d'),
                'SLL_BUY_DVSN_CD': '00',
                'INQR_DVSN_3': '00',
                'PDNO': self._normalize_symbol(symbol) if symbol else '',
                'ORD_DVSN': '',
            }
            data = self._get('/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl', params=params)
            items = data.get('output') or []
            return [self._parse_order(item) for item in items]
        except Exception as e:
            self.log_event('system', f'{self._broker_label()} 미체결 조회 실패: {e}', level='ERROR')
            return []

    def get_trade_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """체결 내역 조회."""
        try:
            if not self.is_connected or not self.account_no:
                return []
            today = datetime.now().strftime('%Y%m%d')
            params: Dict[str, Any] = {
                'CANO': self.account_no[:8],
                'ACNT_PRDT_CD': self.account_no[8:] if len(self.account_no) > 8 else '01',
                'INQR_STRT_DT': today,
                'INQR_END_DT': today,
                'SLL_BUY_DVSN_CD': '00',
                'INQR_DVSN': '00',
                'PDNO': self._normalize_symbol(symbol) if symbol else '',
            }
            data = self._get('/uapi/domestic-stock/v1/trading/inquire-daily-ccld', params=params)
            items = data.get('output1') or []
            trades = [
                self._parse_order(item) for item in items
                if self._to_int(item.get('tot_ccld_qty') or item.get('filled_quantity')) > 0
            ]
            return trades[:limit]
        except Exception as e:
            self.log_event('system', f'{self._broker_label()} 거래내역 조회 실패: {e}', level='ERROR')
            return []

    def get_24h_ticker(self, symbol: str) -> Dict[str, Any]:
        return self.get_realtime_price(symbol)

    def get_today_trades(self) -> List[Dict[str, Any]]:
        return self.get_trade_history(limit=200)

    def get_trading_stats(self) -> Dict[str, Any]:
        history = self.get_trade_history(limit=500)
        buy_count = sum(1 for t in history if 'BUY' in str(t.get('side', '')).upper())
        sell_count = sum(1 for t in history if 'SELL' in str(t.get('side', '')).upper())
        return {
            'broker': self._broker_key(),
            'total_trades': len(history),
            'buy_count': buy_count,
            'sell_count': sell_count,
            'today_trades': len(self.get_today_trades()),
            'open_orders': len(self.get_open_orders()),
            'realized_pnl': 0.0,
            'status': 'ok',
        }
