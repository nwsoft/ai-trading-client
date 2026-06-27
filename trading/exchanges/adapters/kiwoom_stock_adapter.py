#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
키움증권 주식/ETF 어댑터
키움 OpenAPI+를 통한 주식 및 ETF 거래 지원
"""

import importlib
import logging
import platform
import threading
import time
from datetime import datetime, time as dtime
from typing import Dict, List, Optional, Any
from ..interfaces.stock_exchange import StockExchange

# 키움 에러 코드 분류
_KIWOOM_SESSION_ERRORS = frozenset([
    -100, -101, -102,  # 로그인/통신 실패
])
_KIWOOM_MARKET_CLOSED_ERRORS = frozenset([
    -304,  # 장 마감
])
_KIWOOM_ACCOUNT_ERRORS = frozenset([
    -200, -201, -202,  # 계좌/비밀번호 오류
])


def _is_market_hours() -> bool:
    """한국 장중 여부 (주말/휴장 무시, 시간만 기준)"""
    now = datetime.now().time()
    return dtime(9, 0) <= now <= dtime(15, 30)


def _kiwoom_order_error_message(code: Any) -> str:
    """키움 주문 에러코드를 사용자 친화 메시지로 변환."""
    mapping = {
        -100: '사용자 정보교환 실패(세션 재로그인 필요)',
        -101: '서버 접속 실패',
        -102: '버전 처리 실패',
        -200: '시세 조회 과부하/요청 제한',
        -201: '주문 파라미터 오류',
        -202: '요청 전문 작성 실패',
        -300: '주문 전송 실패',
        -301: '계좌비밀번호 미설정/오류',
        -302: '타인 계좌 사용 오류',
        -303: '주문가격이 허용 범위를 초과함',
        -304: '주문가격이 허용 범위를 초과함(장 상태 확인 필요)',
        -305: '주문수량이 발행주수의 1% 초과',
        -306: '주문수량이 발행주수의 3% 초과',
        -307: '주문 전송 실패(전송량 제한)',
        -308: '주문 전송 과부하',
        -309: '주문 전송 실패(요청 제한)',
        -310: '주문수량 500계약 초과',
        -340: '계좌정보 없음',
        -500: '종목코드 없음/유효하지 않음',
    }
    try:
        parsed = int(code)
    except Exception:
        parsed = None
    if parsed is None:
        return f'주문 실패(원인코드: {code})'
    return mapping.get(parsed, f'주문 실패(에러코드: {parsed})')


class KiwoomStockAdapter(StockExchange):
    """키움증권 주식/ETF 어댑터"""
    
    def __init__(self, user_id: str, password: str, cert_password: str, account_no: str = "", **kwargs):
        super().__init__("kiwoom")
        self.user_id = user_id
        self.password = password
        self.cert_password = cert_password
        self.account_no = account_no
        self.api_type = kwargs.get('api_type', 'openapi')
        self.api_version = kwargs.get('api_version', 'pykiwoom')
        self.kiwoom: Any = kwargs.get('backend_client')
        self.request_timeout = int(kwargs.get('request_timeout', 10) or 10)
        self.connection_backend = None
        self.logger = logging.getLogger(__name__)
        # 연결 실패 시 같은 오류가 폭주하지 않도록 재시도/경고를 제어한다.
        self._connect_retry_cooldown_sec = int(kwargs.get('connect_retry_cooldown_sec', 10) or 10)
        # ActiveX/QAx 계열 실패는 환경 원인일 가능성이 높아 재시도 간격을 크게 둔다.
        self._fatal_connect_retry_cooldown_sec = int(kwargs.get('fatal_connect_retry_cooldown_sec', 600) or 600)
        self._last_connect_failure_ts = 0.0
        self._last_connect_failure_reason = ''
        self._last_connect_cooldown_log_ts = 0.0
        self._disconnected_warning_ts: Dict[str, float] = {}
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level='INFO': log_event(category, msg, exchange='kiwoom', level=level)
        
        # ETF 코드 범위 (한국거래소 기준)
        # 범위 기반 판별이 prefix 기반보다 정확함
        self.etf_code_ranges = [
            (69500, 69599),    # KODEX, KINDEX 등
            (102000, 102999),  # 일반 ETF
            (105000, 115999),  # ETF (KODEX 인버스/레버리지 등 포함: 114800 등)
            (117000, 117999),  # 채권 ETF
            (122000, 122999),  # 해외 ETF
            (143000, 143999),  # 레버리지/인버스 ETF
            (261000, 261999),  # 채권 ETF
            (292000, 292999),  # 커머디티 ETF
            (295000, 295999),  # 리스크관리 ETF
        ]

    def _normalize_symbol(self, symbol: Any) -> str:
        return str(symbol or '').strip().zfill(6)

    def _to_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value in (None, ''):
                return default
            text = str(value).replace(',', '').replace('%', '').strip()
            if not text:
                return default
            return float(text)
        except Exception:
            return default

    def _to_int(self, value: Any, default: int = 0) -> int:
        try:
            if value in (None, ''):
                return default
            text = str(value).replace(',', '').strip()
            if not text:
                return default
            return int(float(text))
        except Exception:
            return default

    def _extract_records(self, raw: Any) -> List[Dict[str, Any]]:
        if raw is None:
            return []
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        if isinstance(raw, dict):
            list_like_keys = ['data', 'items', 'rows', 'output', 'result', 'positions', 'orders']
            for key in list_like_keys:
                value = raw.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [raw]
        if hasattr(raw, 'to_dict'):
            try:
                records = raw.to_dict('records')
                return [item for item in records if isinstance(item, dict)]
            except Exception:
                try:
                    as_dict = raw.to_dict()
                    if isinstance(as_dict, dict):
                        return [as_dict]
                except Exception:
                    return []
        return []

    def _extract_first_record(self, raw: Any) -> Dict[str, Any]:
        records = self._extract_records(raw)
        return records[0] if records else {}

    def _get_field(self, record: Dict[str, Any], *names: str, default: Any = None) -> Any:
        for name in names:
            if name in record and record[name] not in (None, ''):
                return record[name]
        lowered = {str(key).lower(): value for key, value in record.items()}
        for name in names:
            value = lowered.get(str(name).lower())
            if value not in (None, ''):
                return value
        return default

    def _ensure_backend(self) -> bool:
        if self.kiwoom is not None:
            return True
        if self.api_version not in ('pykiwoom', 'kiwoom_api'):
            return False
        if threading.current_thread() is not threading.main_thread():
            self.log_event(
                'system',
                '[키움증권 연결 불가] 키움 OpenAPI+ COM 객체는 메인 스레드에서 초기화해야 합니다. '
                f'현재 스레드: {threading.current_thread().name}. '
                '설정 화면의 연결 테스트처럼 메인(UI) 스레드에서 먼저 연결을 완료한 뒤 사용하세요.',
                level='ERROR',
            )
            self._last_connect_failure_reason = 'non_main_thread_init'
            return False
        if platform.system() != 'Windows':
            self.log_event(
                'system',
                '[키움증권 연결 불가] 키움 OpenAPI+는 Windows 전용 프로그램입니다. '
                '현재 실행 중인 OS: {} — '
                '환경설정에서 API 버전을 "mock"으로 변경하거나, '
                'Windows PC에서 실행하세요.'.format(platform.system()),
                level='ERROR',
            )
            return False
        try:
            # pykiwoom은 PyQt5.QAxWidget 기반 → QApplication이 없으면 Kiwoom() 초기화 실패
            # tkinter 이벤트 루프와 별도로 QApplication 인스턴스만 생성 (exec_()는 호출하지 않음)
            try:
                from PyQt5.QtWidgets import QApplication
                from PyQt5.QAxContainer import QAxWidget
                import sys as _sys
                if QApplication.instance() is None:
                    self._qt_app = QApplication(_sys.argv)
            except ImportError:
                self.log_event(
                    'system',
                    '[키움증권 연결 불가] PyQt5가 설치되어 있지 않습니다. '
                    'pip install PyQt5 후 재시도하거나, requirements_windows.txt를 확인하세요.',
                    level='ERROR',
                )
                return False

            # KHOpenAPI ActiveX 로딩 가능 여부를 먼저 점검해 근본 원인을 분리한다.
            try:
                probe = QAxWidget()
                control_ok = bool(probe.setControl('KHOPENAPI.KHOpenAPICtrl.1'))
                has_event = hasattr(probe, 'OnReceiveTrData')
                if not control_ok or not has_event:
                    py_bits = 64 if (8 * __import__('struct').calcsize('P')) == 64 else 32
                    self.log_event(
                        'system',
                        '[키움증권 연결 불가] KHOpenAPI ActiveX 로딩 실패 또는 이벤트 바인딩 실패. '
                        f'setControl={control_ok}, OnReceiveTrData={has_event}, '
                        f'python_bits={py_bits}, python={platform.python_version()}. '
                        'OpenAPI+ 재설치(관리자 권한) 후 KOA Studio 연결 성공 여부를 먼저 확인하세요.',
                        level='ERROR',
                    )
                    self._last_connect_failure_reason = (
                        f'activex_control_probe_failed:py{py_bits}:control{int(control_ok)}:event{int(has_event)}'
                    )
                    return False
            except Exception as probe_exc:
                self.log_event(
                    'system',
                    f'[키움증권 연결 불가] ActiveX 사전 점검 실패: {probe_exc}',
                    level='ERROR',
                )
                self._last_connect_failure_reason = 'activex_probe_exception'
                return False

            kiwoom_module = importlib.import_module('pykiwoom.kiwoom')
            Kiwoom = getattr(kiwoom_module, 'Kiwoom')
            self.kiwoom = Kiwoom()
            self.connection_backend = 'pykiwoom'
            return True
        except ImportError as exc:
            self.log_event(
                'system',
                f'[키움증권 연결 불가] pykiwoom 라이브러리를 찾을 수 없습니다: {exc} — '
                'pip install pykiwoom 후 재시도하거나, 환경설정에서 API 버전을 "mock"으로 변경하세요.',
                level='ERROR',
            )
            return False
        except Exception as exc:
            err_msg = str(exc)
            if 'QAxWidget' in err_msg and 'has no attribute' in err_msg:
                py_bits = 64 if (8 * __import__('struct').calcsize('P')) == 64 else 32
                self.log_event(
                    'system',
                    '[키움증권 연결 불가] 키움 OpenAPI+ OCX 이벤트를 찾을 수 없습니다. '
                    '아래 항목을 순서대로 확인하세요: '
                    '① 키움증권 OpenAPI+ 미설치 — 키움증권 홈페이지(www1.kiwoom.com > 다운로드 > Open API)에서 설치 후 재시도. '
                    '② 설치됐으나 OCX가 등록되지 않음 — 키움증권 OpenAPI+를 "관리자 권한으로 실행"하여 재설치. '
                    '③ Python 비트(32/64bit)와 설치된 OpenAPI+ 비트가 다른 경우 — '
                    'KOA Studio를 실행하여 정상 연결되는지 먼저 확인하고, '
                    '안 된다면 Python과 동일한 비트의 OpenAPI+를 재설치하세요. '
                    f'④ 현재 앱 Python 비트: {py_bits}bit / Python 버전: {platform.python_version()}. '
                    f'(원본 오류: {err_msg})',
                    level='ERROR',
                )
                self._last_connect_failure_reason = 'qax_event_missing'
            else:
                self.log_event('system', f'pykiwoom 초기화 실패: {exc}', level='ERROR')
                self._last_connect_failure_reason = f'backend_init_failed:{err_msg}'
            return False

    def _is_fatal_connect_failure_reason(self) -> bool:
        """환경/런타임 문제로 즉시 재시도해도 성공 가능성이 낮은 실패인지 판별한다."""
        reason = str(self._last_connect_failure_reason or '')
        return reason.startswith((
            'activex_control_probe_failed',
            'qax_event_missing',
            'activex_probe_exception',
            'non_main_thread_init',
        ))

    def _log_disconnected_warning_once(self, action_label: str) -> None:
        """미연결 경고를 짧은 시간에 반복 출력하지 않도록 제한한다."""
        now_ts = time.time()
        last_ts = float(self._disconnected_warning_ts.get(action_label, 0.0) or 0.0)
        if now_ts - last_ts < 5.0:
            return
        self._disconnected_warning_ts[action_label] = now_ts
        reason = f" (최근 연결 실패 사유: {self._last_connect_failure_reason})" if self._last_connect_failure_reason else ''
        self.log_event('system', f"키움증권 미연결 - {action_label} 불가{reason}", level='WARNING')

    def _call_block_request(self, tr_code: str, **kwargs) -> Any:
        if not self.kiwoom or not hasattr(self.kiwoom, 'block_request'):
            raise RuntimeError('kiwoom_block_request_unavailable')
        try:
            result = self.kiwoom.block_request(tr_code, **kwargs)
        except Exception as exc:
            msg = str(exc)
            # 세션 만료 감지 → is_connected 리셋
            if any(str(code) in msg for code in _KIWOOM_SESSION_ERRORS) or 'connect' in msg.lower():
                self.is_connected = False
                self.log_event('system', f'키움 세션 만료 감지 (TR: {tr_code}): {msg}', level='WARNING')
                raise RuntimeError(f'session_expired:{msg}') from exc
            raise
        # 정수 에러 코드 반환 시 분류
        if isinstance(result, int) and result < 0:
            if result in _KIWOOM_SESSION_ERRORS:
                self.is_connected = False
                self.log_event('system', f'키움 세션 에러 {result} (TR: {tr_code})', level='WARNING')
                raise RuntimeError(f'session_error:{result}')
            if result in _KIWOOM_MARKET_CLOSED_ERRORS:
                self.log_event('system', f'장 마감 시간대 TR 요청: {tr_code}', level='WARNING')
                return None
            if result in _KIWOOM_ACCOUNT_ERRORS:
                self.log_event('system', f'계좌/비밀번호 오류 {result} (TR: {tr_code})', level='ERROR')
                raise RuntimeError(f'account_error:{result}')
        return result

    def _parse_trade_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        code = self._normalize_symbol(self._get_field(record, '종목코드', '종목번호', 'code'))
        side_raw = self._get_field(record, '매매구분', '주문구분', 'side', default='')
        side = 'BUY' if '매수' in str(side_raw) else ('SELL' if '매도' in str(side_raw) else str(side_raw))
        filled_price = abs(self._to_float(self._get_field(record, '체결단가', '체결가', '주문가격', 'price')))
        filled_qty = self._to_int(self._get_field(record, '체결수량', 'filled_quantity'))
        order_amount = self._to_float(self._get_field(record, '체결금액', '주문금액', 'amount'))
        # 체결금액이 없으면 단가 × 수량으로 계산
        if not order_amount and filled_price and filled_qty:
            order_amount = filled_price * filled_qty
        return {
            'order_id': str(self._get_field(record, '주문번호', 'order_id', default='')).strip(),
            'symbol': code,
            'name': self._get_field(record, '종목명', 'name', default=code),
            'side': side,
            'filled_price': filled_price,
            'quantity': filled_qty,
            'amount': order_amount,
            'pnl': self._to_float(self._get_field(record, '실현손익', '손익', 'pnl')),
            'timestamp': self._get_field(record, '체결시간', '주문시간', 'timestamp', default=''),
            'status': 'filled',
        }

    def _parse_stock_record(self, code: str, record: Dict[str, Any], market: str) -> Dict[str, Any]:
        symbol = self._normalize_symbol(self._get_field(record, '종목코드', 'code', default=code))
        current_price = abs(self._to_float(self._get_field(record, '현재가', '현재가 ', 'current_price')))
        return {
            'code': symbol,
            'name': self._get_field(record, '종목명', 'name', default=symbol),
            'market': market,
            'current_price': current_price,
            'change_rate': self._to_float(self._get_field(record, '등락율', '등락률', 'change_rate')),
            'volume': self._to_int(self._get_field(record, '거래량', 'volume')),
            'market_cap': self._to_float(self._get_field(record, '시가총액', 'market_cap')),
            'is_etf': self.is_etf(symbol),
            'status': 'ok',
        }

    def _parse_balance_summary(self, record: Dict[str, Any]) -> Dict[str, Any]:
        cash = self._to_float(self._get_field(record, '예수금', '주문가능현금', 'd+2추정예수금', 'cash'))
        stock_eval = self._to_float(self._get_field(record, '총평가금액', '유가잔고평가액', 'stock_eval'))
        total_assets = self._to_float(self._get_field(record, '총자산', '추정예탁자산', 'total_assets'))
        profit_loss = self._to_float(self._get_field(record, '총평가손익금액', '평가손익', 'profit_loss'))
        profit_rate = self._to_float(self._get_field(record, '총수익률(%)', '수익률(%)', 'profit_rate'))
        return {
            'account_no': self.account_no,
            'user_id': self.user_id,
            'broker': 'kiwoom',
            'api_type': self.api_type,
            'api_version': self.api_version,
            'cash': cash,
            'stock_eval': stock_eval,
            'total_assets': total_assets if total_assets else cash + stock_eval,
            'profit_loss': profit_loss,
            'profit_rate': profit_rate,
            'status': 'ok',
        }

    def _parse_position_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        code = self._normalize_symbol(self._get_field(record, '종목번호', '종목코드', 'code'))
        current_price = abs(self._to_float(self._get_field(record, '현재가', 'current_price')))
        avg_price = abs(self._to_float(self._get_field(record, '매입가', '평균단가', 'avg_price')))
        quantity = self._to_int(self._get_field(record, '보유수량', '매매가능수량', 'quantity'))
        eval_amount = self._to_float(self._get_field(record, '평가금액', '평가금액합계', 'eval_amount'))
        pnl = self._to_float(self._get_field(record, '평가손익', '손익금액', 'pnl'))
        pnl_rate = self._to_float(self._get_field(record, '수익률(%)', '손익율', 'pnl_rate'))
        return {
            'code': code,
            'name': self._get_field(record, '종목명', 'name', default=code),
            'quantity': quantity,
            'avg_price': avg_price,
            'current_price': current_price,
            'eval_amount': eval_amount if eval_amount else current_price * quantity,
            'pnl': pnl,
            'pnl_rate': pnl_rate,
            'is_etf': self.is_etf(code),
            'status': 'ok',
        }

    def _parse_order_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        code = self._normalize_symbol(self._get_field(record, '종목코드', '종목번호', 'code'))
        return {
            'order_id': str(self._get_field(record, '주문번호', 'order_id', default='')).strip(),
            'symbol': code,
            'name': self._get_field(record, '종목명', 'name', default=code),
            'side': self._get_field(record, '주문구분', 'side', default=''),
            'quantity': self._to_int(self._get_field(record, '주문수량', 'quantity')),
            'filled_quantity': self._to_int(self._get_field(record, '체결량', 'filled_quantity')),
            'unfilled_quantity': self._to_int(self._get_field(record, '미체결수량', 'unfilled_quantity')),
            'price': abs(self._to_float(self._get_field(record, '주문가격', 'price'))),
            'status': self._get_field(record, '주문상태', 'status', default='unknown'),
            'timestamp': self._get_field(record, '주문시간', 'timestamp', default=''),
        }

    def _parse_trade_timestamp(self, raw_ts: Any) -> Optional[datetime]:
        """키움 체결시간 문자열을 datetime으로 변환.

        지원 포맷 예시:
        - 2026-04-24T10:30:11
        - 2026-04-24 10:30:11
        - 20260424103011
        - 103011 (당일 시각)
        """
        text = str(raw_ts or '').strip()
        if not text:
            return None

        # ISO 포맷 우선
        try:
            return datetime.fromisoformat(text.replace('Z', '+00:00'))
        except Exception:
            pass

        # 숫자만 남겨 포맷 추론
        digits = ''.join(ch for ch in text if ch.isdigit())
        now = datetime.now()

        for fmt, value in (
            ('%Y%m%d%H%M%S', digits),
            ('%Y%m%d%H%M', digits),
            ('%H%M%S', digits),
            ('%H%M', digits),
        ):
            try:
                parsed = datetime.strptime(value, fmt)
                if fmt in ('%H%M%S', '%H%M'):
                    parsed = parsed.replace(year=now.year, month=now.month, day=now.day)
                return parsed
            except Exception:
                continue

        return None

    def _lookup_recent_order_id(self, symbol: str, side: str, quantity: int) -> str:
        """최근 주문/미체결 내역에서 주문번호를 최대한 추정하여 반환."""
        normalized = self._normalize_symbol(symbol)
        side_hint = '매수' if str(side).upper() == 'BUY' else '매도'

        # 1) 미체결에서 우선 탐색
        try:
            for order in self.get_open_orders(symbol=normalized):
                order_id = str(order.get('order_id') or '').strip()
                if order_id:
                    return order_id
        except Exception:
            pass

        # 2) 당일 체결내역에서 탐색
        try:
            trades = self.get_trade_history(symbol=normalized, limit=10)
            for trade in trades:
                order_id = str(trade.get('order_id') or '').strip()
                trade_side = str(trade.get('side') or '')
                trade_qty = self._to_int(trade.get('quantity'))
                if not order_id:
                    continue
                if side_hint and side_hint not in trade_side and str(side).upper() not in trade_side.upper():
                    continue
                if quantity > 0 and trade_qty > 0 and trade_qty != quantity:
                    continue
                return order_id
        except Exception:
            pass

        return ''
    
    def connect(self) -> bool:
        """
        키움증권 OpenAPI+ 연결
        
        Returns:
            bool: 연결 성공 여부
        """
        try:
            now_ts = time.time()
            if self.is_connected:
                return True

            # 실패 직후 짧은 시간 동안은 재시도를 제한해 로그 폭주를 막는다.
            if self._last_connect_failure_ts > 0:
                elapsed = now_ts - self._last_connect_failure_ts
                cooldown_sec = (
                    self._fatal_connect_retry_cooldown_sec
                    if self._is_fatal_connect_failure_reason()
                    else self._connect_retry_cooldown_sec
                )
                if elapsed < cooldown_sec:
                    if now_ts - self._last_connect_cooldown_log_ts >= 3.0:
                        wait_sec = max(1, int(cooldown_sec - elapsed))
                        self.log_event(
                            'system',
                            f'키움증권 재연결 대기 중... {wait_sec}초 후 자동 재시도 (최근 실패: {self._last_connect_failure_reason or "unknown"})',
                            level='INFO',
                        )
                        self._last_connect_cooldown_log_ts = now_ts
                    return False

            self.log_event('system', f"키움증권 연결 시도 중... (type={self.api_type}, version={self.api_version})")

            if not self.user_id or not self.password:
                self.log_event(
                    'system',
                    '[키움증권 연결 불가] 계정 ID 또는 비밀번호가 설정되지 않았습니다. '
                    '환경설정 > 키움증권 항목에서 ID와 비밀번호를 입력하세요.',
                    level='ERROR',
                )
                self._last_connect_failure_ts = now_ts
                self._last_connect_failure_reason = 'missing_credentials'
                return False

            if not self._ensure_backend():
                self._last_connect_failure_ts = now_ts
                if not self._last_connect_failure_reason:
                    self._last_connect_failure_reason = 'backend_unavailable'
                return False

            login_result = None
            if hasattr(self.kiwoom, 'CommConnect'):
                try:
                    login_result = self.kiwoom.CommConnect(block=True)
                except TypeError:
                    login_result = self.kiwoom.CommConnect()

            connected = False
            if hasattr(self.kiwoom, 'GetConnectState'):
                try:
                    connected = bool(self.kiwoom.GetConnectState())
                except Exception:
                    connected = False

            if not connected and login_result in (0, None, True):
                connected = True

            if connected:
                self.is_connected = True
                self.connection_backend = self.connection_backend or self.api_version
                self._last_connect_failure_ts = 0.0
                self._last_connect_failure_reason = ''
                self._disconnected_warning_ts.clear()
                if hasattr(self.kiwoom, 'GetLoginInfo') and not self.account_no:
                    try:
                        accounts = str(self.kiwoom.GetLoginInfo('ACCNO') or '').split(';')
                        self.account_no = next((acc.strip() for acc in accounts if acc.strip()), self.account_no)
                    except Exception:
                        pass
                if hasattr(self.kiwoom, 'GetLoginInfo'):
                    try:
                        backend_user_id = str(self.kiwoom.GetLoginInfo('USER_ID') or '').strip()
                        if backend_user_id:
                            self.user_id = backend_user_id
                    except Exception:
                        pass
                self.log_event('system', f"키움증권 연결 성공 ({self.connection_backend})")
                return True

            self.log_event('system', f"키움증권 연결 실패: login_result={login_result}", level='ERROR')
            self._last_connect_failure_ts = now_ts
            self._last_connect_failure_reason = f'login_failed:{login_result}'
            return False
            
        except Exception as e:
            self.log_event('system', f"키움증권 연결 실패: {e}", level='ERROR')
            self._last_connect_failure_ts = time.time()
            self._last_connect_failure_reason = f'connect_exception:{e}'
            return False
    
    def get_stock_list(self, market: str = "KOSPI") -> List[Dict[str, Any]]:
        """
        주식 목록 조회
        
        Args:
            market: 시장 구분 ("KOSPI", "KOSDAQ", "ALL")
        
        Returns:
            List[Dict]: 주식 정보 리스트
        """
        try:
            if not self.is_connected:
                self._log_disconnected_warning_once('주식 목록 조회')
                return []

            if not self.kiwoom or not hasattr(self.kiwoom, 'GetCodeListByMarket'):
                self.log_event('system', 'GetCodeListByMarket 지원 백엔드가 없어 주식 목록 조회 불가', level='WARNING')
                return []

            market_map = {
                'KOSPI': ['0'],
                'KOSDAQ': ['10'],
                'ETF': ['8', '3'],
                'ALL': ['0', '10'],
            }
            market_codes = market_map.get((market or 'KOSPI').upper(), ['0'])
            results: List[Dict[str, Any]] = []
            seen_codes = set()
            for market_code in market_codes:
                raw_codes = self.kiwoom.GetCodeListByMarket(market_code)
                if isinstance(raw_codes, str):
                    codes = [code.strip() for code in raw_codes.split(';') if code.strip()]
                elif isinstance(raw_codes, list):
                    codes = [str(code).strip() for code in raw_codes if str(code).strip()]
                else:
                    codes = []

                for code in codes:
                    symbol = self._normalize_symbol(code)
                    if symbol in seen_codes or self.is_etf(symbol):
                        continue
                    seen_codes.add(symbol)
                    name = symbol
                    if hasattr(self.kiwoom, 'GetMasterCodeName'):
                        try:
                            name = self.kiwoom.GetMasterCodeName(symbol) or symbol
                        except Exception:
                            name = symbol
                    results.append({
                        'code': symbol,
                        'name': name,
                        'market': 'KOSDAQ' if market_code == '10' else 'KOSPI',
                        'current_price': 0.0,
                        'volume': 0,
                        'is_etf': False,
                        'status': 'ok',
                    })
            return results
            
        except Exception as e:
            self.log_event('system', f"주식 목록 조회 실패: {e}", level='ERROR')
            return []
    
    def get_etf_list(self) -> List[Dict[str, Any]]:
        """
        ETF 목록 조회
        
        Returns:
            List[Dict]: ETF 정보 리스트
        """
        try:
            if not self.is_connected:
                self._log_disconnected_warning_once('ETF 목록 조회')
                return []

            if self.kiwoom and hasattr(self.kiwoom, 'GetCodeListByMarket'):
                raw_codes = []
                for market_code in ('8', '3'):
                    result = self.kiwoom.GetCodeListByMarket(market_code)
                    if isinstance(result, str):
                        raw_codes.extend([code.strip() for code in result.split(';') if code.strip()])
                etf_codes = []
                seen_codes = set()
                for code in raw_codes:
                    symbol = self._normalize_symbol(code)
                    if symbol not in seen_codes and self.is_etf(symbol):
                        etf_codes.append(symbol)
                        seen_codes.add(symbol)

                etfs = []
                for symbol in etf_codes:
                    name = symbol
                    if hasattr(self.kiwoom, 'GetMasterCodeName'):
                        try:
                            name = self.kiwoom.GetMasterCodeName(symbol) or symbol
                        except Exception:
                            name = symbol

                    # ETF 실시간 지표(NAV/추적오차/거래대금) 통합 조회 시도
                    nav = 0.0
                    tracking_error = None
                    trade_value = 0.0
                    current_price = 0.0
                    expense_ratio = None
                    base_index = ''
                    try:
                        rt = self.get_etf_realtime_metrics(symbol)
                        if rt.get('status') == 'ok':
                            current_price = float(rt.get('current_price') or 0.0)
                            nav = float(rt.get('nav') or 0.0)
                            tracking_error = rt.get('tracking_error')
                            trade_value = float(rt.get('trade_value') or 0.0)
                            expense_ratio = rt.get('expense_ratio')
                            base_index = rt.get('base_index', '')
                    except Exception:
                        pass

                    etfs.append({
                        'code': symbol,
                        'name': name,
                        'market': 'ETF',
                        'current_price': current_price,
                        'nav': nav,
                        'tracking_error': tracking_error,
                        'trade_value': trade_value,
                        'expense_ratio': expense_ratio,
                        'base_index': base_index,
                        'is_etf': True,
                        'status': 'ok',
                    })
                return etfs

            return []
            
        except Exception as e:
            self.log_event('system', f"ETF 목록 조회 실패: {e}", level='ERROR')
            return []
    
    def is_etf(self, symbol: str) -> bool:
        """
        ETF 여부 확인
        
        Args:
            symbol: 종목코드 (예: "069500")
        
        Returns:
            bool: ETF 여부
            
        설명:
            - 방법 1: 코드 범위 확인 (신뢰도 높음)
            - 방법 2: 키움 API의 장구분 필드 확인 (향후 구현)
        """
        try:
            # 종목코드를 정수로 변환
            code_int = int(symbol)
            
            # 범위 기반 판별 (정확도 높음)
            for start, end in self.etf_code_ranges:
                if start <= code_int <= end:
                    return True
            
            return False
            
        except (ValueError, TypeError):
            # 숫자가 아닌 경우
            return False
    
    def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """
        주식/ETF 상세 정보 조회
        
        Args:
            symbol: 종목코드
        
        Returns:
            Dict: 종목 상세 정보
        """
        try:
            if not self.is_connected:
                return {"status": "error", "error": "not_connected"}

            symbol = self._normalize_symbol(symbol)
            record = {}
            if self.kiwoom and hasattr(self.kiwoom, 'GetMasterCodeName'):
                record['종목명'] = self.kiwoom.GetMasterCodeName(symbol)
            if self.kiwoom and hasattr(self.kiwoom, 'block_request'):
                try:
                    raw = self._call_block_request('opt10001', 종목코드=symbol, output='주식기본정보', next=0)
                    record.update(self._extract_first_record(raw))
                except Exception as exc:
                    self.log_event('system', f'주식기본정보 조회 경고: {symbol} - {exc}', level='WARNING')

            if not record:
                return {"status": "error", "error": "not_available"}

            info = self._parse_stock_record(symbol, record, 'ETF' if self.is_etf(symbol) else 'KOSPI')
            info.update({
                'bid_price': abs(self._to_float(self._get_field(record, '매수호가', 'bid_price'))),
                'ask_price': abs(self._to_float(self._get_field(record, '매도호가', 'ask_price'))),
                'prev_close': abs(self._to_float(self._get_field(record, '전일종가', 'prev_close'))),
                'status': 'ok',
            })
            return info
            
        except Exception as e:
            self.log_event('system', f"종목 정보 조회 실패: {symbol} - {e}", level='ERROR')
            return {"status": "error", "error": str(e)}
    
    def get_realtime_price(self, symbol: str) -> Dict[str, Any]:
        """
        실시간 시세 조회
        
        Args:
            symbol: 종목코드
        
        Returns:
            Dict: 실시간 시세 정보
        """
        try:
            if not self.is_connected:
                return {"status": "error", "error": "not_connected"}

            symbol = self._normalize_symbol(symbol)
            raw = self._call_block_request('opt10001', 종목코드=symbol, output='주식기본정보', next=0)
            record = self._extract_first_record(raw)
            if not record:
                return {"status": "error", "error": "no_price_data"}

            current_price = abs(self._to_float(self._get_field(record, '현재가', 'current_price')))
            return {
                'code': symbol,
                'current_price': current_price,
                'bid_price': abs(self._to_float(self._get_field(record, '매수호가', 'bid_price'))),
                'ask_price': abs(self._to_float(self._get_field(record, '매도호가', 'ask_price'))),
                'volume': self._to_int(self._get_field(record, '거래량', 'volume')),
                'change_rate': self._to_float(self._get_field(record, '등락율', '등락률', 'change_rate')),
                'timestamp': self._get_field(record, '체결시간', 'timestamp', default=''),
                'status': 'ok',
            }
            
        except Exception as e:
            self.log_event('system', f"실시간 시세 조회 실패: {symbol} - {e}", level='ERROR')
            return {"status": "error", "error": str(e)}

    def get_etf_realtime_metrics(self, symbol: str) -> Dict[str, Any]:
        """ETF 실시간 지표 조회 (현재가 + NAV + 추적오차 + 거래대금 통합).
        
        키움 KOA TR opt10079(ETF 현재가 조회) 사용.
        API 키 없는 경우 get_realtime_price() 기반으로 부분 반환.
        """
        try:
            price_data = self.get_realtime_price(symbol)
            if price_data.get('status') != 'ok':
                return price_data
            # KOA ETF 전용 TR (opt10079) 시도 - NAV/추적오차/거래대금
            etf_detail: Dict[str, Any] = {}
            try:
                raw = self._call_block_request(
                    'opt10079', 종목코드=self._normalize_symbol(symbol), output='ETF현재가', next=0
                )
                record = self._extract_first_record(raw) or {}
                etf_detail = {
                    'nav': abs(self._to_float(self._get_field(record, 'NAV', 'nav', default=0))),
                    'tracking_error': self._to_float_or_none(
                        self._get_field(record, '추적오차율', 'trcErrRt', default=None)
                    ),
                    'trade_value': self._to_float(
                        self._get_field(record, '거래대금', 'trade_value', default=0)
                    ),
                    'expense_ratio': self._to_float_or_none(
                        self._get_field(record, '총보수율', 'expense_ratio', default=None)
                    ),
                    'base_index': self._get_field(record, '기준지수', 'base_index', default=''),
                }
            except Exception:
                pass  # ETF TR 실패 시 기본 가격 데이터만 반환
            return {
                'code': symbol,
                'current_price': price_data.get('current_price', 0),
                'change_rate': price_data.get('change_rate', 0),
                'volume': price_data.get('volume', 0),
                'trade_value': etf_detail.get('trade_value') or price_data.get('trade_value', 0),
                'nav': etf_detail.get('nav', 0),
                'tracking_error': etf_detail.get('tracking_error'),
                'expense_ratio': etf_detail.get('expense_ratio'),
                'base_index': etf_detail.get('base_index', ''),
                'timestamp': price_data.get('timestamp', ''),
                'status': 'ok',
            }
        except Exception as e:
            self.log_event('system', f"ETF 실시간 지표 조회 실패: {symbol} - {e}", level='ERROR')
            return {"status": "error", "error": str(e)}

    def _to_float_or_none(self, value) -> 'Optional[float]':
        """None 허용 float 변환."""
        if value is None or value == '':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    # ===== ExchangeInterface 구현 =====
    
    def get_account_info(self) -> Dict[str, Any]:
        """계정 정보 조회 (주식 계좌 정보)"""
        try:
            if not self.is_connected:
                return {"status": "error", "error": "not_connected"}

            account_no = self.account_no
            if self.kiwoom and hasattr(self.kiwoom, 'GetLoginInfo'):
                try:
                    accounts = str(self.kiwoom.GetLoginInfo('ACCNO') or '')
                    if accounts and not account_no:
                        account_no = next((acc.strip() for acc in accounts.split(';') if acc.strip()), account_no)
                    user_id = str(self.kiwoom.GetLoginInfo('USER_ID') or self.user_id)
                except Exception:
                    user_id = self.user_id
                else:
                    self.account_no = account_no
                    self.user_id = user_id
            return {
                'status': 'ok',
                'account_no': account_no,
                'user_id': self.user_id,
                'broker': 'kiwoom',
                'api_type': self.api_type,
                'api_version': self.api_version,
            }
            
        except Exception as e:
            self.log_event('system', f"계정 정보 조회 실패: {e}", level='ERROR')
            return {"status": "error", "error": str(e)}
    
    def get_balance(self) -> Dict[str, Any]:
        """잔고 조회 (주식 계좌 잔고)"""
        try:
            if not self.is_connected:
                return {
                    "status": "error", 
                    "error": "거래소 연결 안 됨 - 키움 연결 확인 필요"
                }

            if not self.account_no:
                return {
                    "status": "error", 
                    "error": "계좌번호 미설정 - 설정에서 계좌번호를 입력하세요"
                }

            raw = self._call_block_request(
                'opw00018',
                계좌번호=self.account_no,
                비밀번호=self.password,
                비밀번호입력매체구분='00',
                조회구분='2',
                output='계좌평가잔고내역요청',
                next=0,
            )
            record = {}
            if isinstance(raw, dict):
                single = raw.get('single')
                if isinstance(single, dict):
                    record = single
            if not record:
                record = self._extract_first_record(raw)
            if not record:
                return {
                    "status": "error", 
                    "error": "잔고 조회 실패 - 계좌번호 또는 비밀번호 확인 필요"
                }
            return self._parse_balance_summary(record)
            
        except Exception as e:
            self.log_event('system', f"잔고 조회 실패: {e}", level='ERROR')
            return {
                "status": "error", 
                "error": f"잔고 조회 중 오류 발생: {str(e)}"
            }
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """보유 종목 조회 (주식 포지션)"""
        try:
            if not self.is_connected:
                return []

            if not self.account_no:
                return []

            raw = self._call_block_request(
                'opw00018',
                계좌번호=self.account_no,
                비밀번호=self.password,
                비밀번호입력매체구분='00',
                조회구분='2',
                output='계좌평가잔고내역요청',
                next=0,
            )
            records = self._extract_records(raw)
            if isinstance(raw, dict):
                multi = raw.get('multi')
                if isinstance(multi, list):
                    records = [item for item in multi if isinstance(item, dict)]

            positions = []
            for record in records:
                position = self._parse_position_record(record)
                if position.get('code') and position.get('quantity', 0) > 0:
                    positions.append(position)
            return positions
            
        except Exception as e:
            self.log_event('system', f"보유 종목 조회 실패: {e}", level='ERROR')
            return []
    
    def place_order(self, symbol: str, side: str, quantity: float, 
                   price: Optional[float] = None, order_type: str = "MARKET") -> Dict[str, Any]:
        """
        주문 실행 (주식/ETF 매수/매도)
        
        Args:
            symbol: 종목코드
            side: "BUY" 또는 "SELL"
            quantity: 수량
            price: 지정가 가격 (지정가 주문인 경우)
            order_type: "MARKET" (시장가) 또는 "LIMIT" (지정가)
        
        Returns:
            Dict: 주문 결과
        """
        try:
            if not self.is_connected:
                return {
                    "status": "error", 
                    "error": "거래소 연결 안 됨 - API 키, 계좌번호, Windows+pykiwoom 확인 필요"
                }

            if not self.account_no:
                return {
                    "status": "error", 
                    "error": "계좌번호 미설정 - 설정에서 계좌번호를 입력하세요"
                }

            if not self.kiwoom or not hasattr(self.kiwoom, 'SendOrder'):
                return {
                    "status": "error", 
                    "error": "주문 기능 불가 - Windows 환경 또는 pykiwoom 패키지 필요"
                }

            symbol = self._normalize_symbol(symbol)
            order_type_upper = str(order_type or 'MARKET').upper()
            side_upper = str(side or '').upper()
            qty = int(quantity)
            if qty <= 0:
                return {
                    "status": "error", 
                    "error": "주문 수량 오류 - 0보다 큰 수를 입력하세요"
                }

            order_code = 1 if side_upper == 'BUY' else 2
            hoga = '03' if order_type_upper == 'MARKET' else '00'
            order_price = 0 if hoga == '03' else int(price or 0)
            if hoga == '00' and order_price <= 0:
                return {
                    "status": "error", 
                    "error": "지정가 주문 시 가격 필요 - 0보다 큰 가격을 입력하세요"
                }

            result = self.kiwoom.SendOrder(
                '노아AI주문',
                '0101',
                self.account_no,
                order_code,
                symbol,
                qty,
                order_price,
                hoga,
                '',
            )

            # 키움은 보통 0이면 접수 성공이며, 그 외 음수 코드는 실패
            success = result in (0, '0', None)
            if not success:
                error_msg = _kiwoom_order_error_message(result)
                if not _is_market_hours():
                    error_msg = f"{error_msg} / 현재 장중이 아님"
                self.log_event('system', f"주문 접수 실패: {symbol} {side_upper} {qty}주 - {error_msg}", level='ERROR')
                return {
                    'status': 'error',
                    'order_id': None,
                    'symbol': symbol,
                    'side': side_upper,
                    'quantity': qty,
                    'price': float(order_price or 0),
                    'order_type': order_type_upper,
                    'broker': 'kiwoom',
                    'api_type': self.api_type,
                    'api_version': self.api_version,
                    'execution_mode': 'live_api',
                    'success': False,
                    'raw_result': result,
                    'error': error_msg,
                }

            order_id = self._lookup_recent_order_id(symbol=symbol, side=side_upper, quantity=qty)
            if order_id:
                order_status = 'accepted'
                order_msg = '주문 접수 성공 (주문번호 확인)'
            else:
                order_status = 'pending'
                order_msg = '주문 접수 성공 (주문번호 미확인, 미체결/체결 조회 필요)'

            self.log_event('system', f"주문 접수 성공: {symbol} {side_upper} {qty}주 / 상태={order_status} / id={order_id or 'N/A'}")
            return {
                'status': 'success',
                'order_id': order_id,
                'order_status': order_status,
                'message': order_msg,
                'symbol': symbol,
                'side': side_upper,
                'quantity': qty,
                'price': float(order_price or 0),
                'order_type': order_type_upper,
                'broker': 'kiwoom',
                'api_type': self.api_type,
                'api_version': self.api_version,
                'execution_mode': 'live_api',
                'success': True,
                'raw_result': result,
                'error': None,
            }
            
        except Exception as e:
            self.log_event('system', f"주문 실행 실패: {symbol} - {e}", level='ERROR')
            return {
                "status": "error",
                "error": str(e),
                "broker": "kiwoom",
                "api_type": self.api_type,
                "api_version": self.api_version,
                "execution_mode": "live_api",
                "success": False,
            }
    
    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        """주문 취소

        Args:
            order_id: 취소할 주문번호
            symbol: 종목코드. None이면 미체결 목록에서 자동 탐색.
        """
        try:
            if not self.is_connected:
                return False

            if not self.account_no or not self.kiwoom or not hasattr(self.kiwoom, 'SendOrder'):
                return False

            # symbol 없을 때 미체결에서 탐색
            resolved_symbol = symbol
            if not resolved_symbol:
                try:
                    open_orders = self.get_open_orders()
                    matched = next(
                        (o for o in open_orders if str(o.get('order_id', '')).strip() == str(order_id).strip()),
                        None,
                    )
                    if matched:
                        resolved_symbol = matched.get('symbol')
                except Exception:
                    pass

            if not resolved_symbol:
                self.log_event('system', f'취소 종목코드 미확인 — order_id={order_id}', level='WARNING')
                return False

            result = self.kiwoom.SendOrder(
                '노아AI취소',
                '0101',
                self.account_no,
                3,
                self._normalize_symbol(resolved_symbol),
                0,
                0,
                '00',
                str(order_id),
            )
            return result in (0, '0', None)

        except Exception as e:
            self.log_event('system', f'주문 취소 실패: {order_id} - {e}', level='ERROR')
            return False
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """오픈 주문 조회"""
        try:
            if not self.is_connected:
                return []

            if not self.account_no:
                return []

            raw = self._call_block_request(
                'opt10075',
                계좌번호=self.account_no,
                전체종목구분='0',
                매매구분='0',
                종목코드=self._normalize_symbol(symbol) if symbol else '',
                체결구분='1',
                output='미체결요청',
                next=0,
            )
            records = self._extract_records(raw)
            if isinstance(raw, dict):
                multi = raw.get('multi')
                if isinstance(multi, list):
                    records = [item for item in multi if isinstance(item, dict)]
            return [self._parse_order_record(record) for record in records]
            
        except Exception as e:
            self.log_event('system', f"오픈 주문 조회 실패: {e}", level='ERROR')
            return []
    
    def get_trade_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        거래 내역 조회 (opw00007 — 계좌별 주문체결내역)

        Args:
            symbol: 종목코드 (None이면 전 종목)
            limit: 최대 조회 건수

        Returns:
            List[Dict]: 체결된 주문 내역
        """
        try:
            if not self.is_connected:
                return []

            if not self.account_no:
                return []

            today = datetime.now().strftime('%Y%m%d')
            raw = self._call_block_request(
                'opw00007',
                계좌번호=self.account_no,
                비밀번호=self.password,
                조회구분='1',          # 1: 체결 기준
                주식채권구분='1',       # 1: 주식
                매도수구분='0',         # 0: 전체
                시작일=today,
                종료일=today,
                종목코드=self._normalize_symbol(symbol) if symbol else '',
                output='계좌별주문체결내역상세',
                next=0,
            )
            if raw is None:
                # 장 마감 또는 데이터 없음
                return []

            records = self._extract_records(raw)
            if isinstance(raw, dict):
                multi = raw.get('multi')
                if isinstance(multi, list):
                    records = [item for item in multi if isinstance(item, dict)]

            trades = [self._parse_trade_record(rec) for rec in records]
            # 수량 0 항목 제거 후 limit 적용
            trades = [t for t in trades if t.get('quantity', 0) > 0]
            return trades[:limit]

        except RuntimeError as e:
            msg = str(e)
            if msg.startswith('session_expired') or msg.startswith('session_error'):
                self.log_event('system', f'거래 내역 조회 중 세션 오류, 재연결 필요: {msg}', level='WARNING')
            else:
                self.log_event('system', f'거래 내역 조회 실패: {e}', level='ERROR')
            return []
        except Exception as e:
            self.log_event('system', f'거래 내역 조회 실패: {e}', level='ERROR')
            return []
    
    def get_24h_ticker(self, symbol: str) -> Dict[str, Any]:
        """24시간 티커 데이터 조회"""
        try:
            if not self.is_connected:
                return {"status": "error", "error": "not_connected"}

            price = self.get_realtime_price(symbol)
            if price.get('status') == 'ok':
                return price
            return {"status": "error", "error": price.get('error', 'ticker_not_available')}
            
        except Exception as e:
            self.log_event('system', f"티커 데이터 조회 실패: {symbol} - {e}", level='ERROR')
            return {"status": "error", "error": str(e)}

    def get_today_trades(self) -> List[Dict[str, Any]]:
        """오늘 거래 내역 조회"""
        trades = self.get_trade_history(limit=200)
        today = datetime.now().date()
        results = []
        for trade in trades:
            timestamp = str(trade.get('timestamp') or trade.get('filled_at') or '').strip()
            if not timestamp:
                continue
            try:
                parsed = self._parse_trade_timestamp(timestamp)
                if parsed is None:
                    continue
                trade_date = parsed.date()
            except Exception:
                continue
            if trade_date == today:
                results.append(trade)
        return results

    def get_trading_stats(self) -> Dict[str, Any]:
        """거래 통계 조회"""
        history = self.get_trade_history(limit=500)
        buy_count = 0
        sell_count = 0
        realized_pnl = 0.0
        for trade in history:
            side = str(trade.get('side') or '').upper()
            if 'BUY' in side or '매수' in side:
                buy_count += 1
            if 'SELL' in side or '매도' in side:
                sell_count += 1
            realized_pnl += self._to_float(trade.get('pnl'))
        return {
            'broker': 'kiwoom',
            'total_trades': len(history),
            'buy_count': buy_count,
            'sell_count': sell_count,
            'today_trades': len(self.get_today_trades()),
            'open_orders': len(self.get_open_orders()),
            'realized_pnl': realized_pnl,
            'status': 'ok',
        }
