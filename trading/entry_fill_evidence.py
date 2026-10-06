"""Read provider-reported entry fills; requested size/market price are not fills."""
import math


def owned_entry_fill(receipt):
    if not isinstance(receipt, dict): return None
    raw = receipt.get('order') if isinstance(receipt.get('order'), dict) else receipt
    order_id = raw.get('orderId') or raw.get('id') or receipt.get('order_id')
    quantity = raw.get('executedQty', receipt.get('executed_qty'))
    price = raw.get('avgPrice', receipt.get('avg_price'))
    try:
        q, p = float(quantity), float(price)
        if not order_id or not all(math.isfinite(v) and v > 0 for v in (q,p)):
            return None
    except (TypeError, ValueError): return None
    return {'order_id': str(order_id), 'quantity': q, 'price': p,
            'complete': str(raw.get('status') or receipt.get('status') or '').upper() == 'FILLED',
            'terminal': str(raw.get('status') or receipt.get('status') or '').upper() in {'FILLED', 'CANCELED', 'CANCELLED', 'REJECTED', 'EXPIRED', 'EXPIRED_IN_MATCH'}}


def reconcile_owned_pending_entries(owner):
    """At most three read-only lookups per 30s; absence never proves rejection."""
    import time
    from .opportunity_coordinator import get_opportunity_coordinator, account_scope_for, finish_submission
    now = time.monotonic()
    if now - getattr(owner, '_pending_entry_lookup_at', -31.) < 30.:
        return
    owner._pending_entry_lookup_at = now
    coordinator = get_opportunity_coordinator(owner)
    offset = getattr(owner, '_pending_entry_lookup_offset', 0)
    pending = coordinator.pending_submissions(account_scope=account_scope_for(owner,'live'),target='binance',offset=offset)
    owner._pending_entry_lookup_offset = offset + len(pending)
    for row in pending:
        symbol = row.get('symbol')
        if not symbol:
            continue
        try:
            lookup = {'orderId':row['order_id']} if row.get('order_id') else {'origClientOrderId':row['client_order_id']}
            receipt = owner.binance_client.client.futures_get_order(symbol=symbol,**lookup)
            if not isinstance(receipt,dict) or receipt.get('symbol') != symbol:
                continue
            if not ((row.get('order_id') and str(receipt.get('orderId')) == str(row['order_id']))
                    or receipt.get('clientOrderId') == row['client_order_id']):
                continue
            status = str(receipt.get('status') or '').upper()
            terminal = status in {'CANCELED','CANCELLED','REJECTED','EXPIRED','EXPIRED_IN_MATCH'} or (status=='FILLED' and owned_entry_fill(receipt) is not None)
            finish_submission(owner,row,{'order':receipt,'status':status},confirmed=terminal)
        except Exception:
            # Lookup errors/not-found retain the reservation. No retry order,
            # balance adoption, key mutation or automatic LIVE resume.
            continue


def binance_submission_error(error, *, submission_attempted=True):
    """Separate documented request/filter rejection from uncertain execution.

    https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code
    Timeout (-1007), unexpected response (-1006), and duplicate client IDs stay
    uncertain: the original order must be looked up, never blindly retried.
    """
    try:
        code = int(getattr(error,'code',0))
    except (TypeError,ValueError):
        code = 0
    rejection_codes = {
        -1021,-1022,-1100,-1101,-1102,-1103,-1104,-1105,-1106,
        -1111,-1114,-1115,-1116,-1117,-1118,-1121,-1122,-1128,-1130,
        -2014,-2015,-2018,-2019,-2021,-2022,-2025,-2026,-2027,-2028,
        -4001,-4002,-4003,-4004,-4005,-4006,-4007,-4013,-4014,-4023,-4164,
    }
    rejected = not submission_attempted or code in rejection_codes
    explanations = {
        -4164:'최소 주문금액 미달 — 종목 주문 규격과 가용금액을 확인하세요.',
        -2018:'주문 가능 잔고 부족 — 기관 가용잔고와 다른 주문을 확인하세요.',
        -2019:'주문 가능 증거금 부족 — 기관 가용잔고와 예약 주문을 확인하세요.',
        -1111:'수량·가격 정밀도 초과 — 최신 종목 주문 규격을 다시 확인하세요.',
        -1121:'지원하지 않는 종목 — 선택 종목과 현물·선물 시장을 확인하세요.',
        -1122:'거래 불가 종목 — 기관의 현재 종목 상태를 확인하세요.',
        -1021:'요청 시간 범위 오류 — PC 시각과 기관 시간 동기화를 확인하세요.',
        -1022:'API 서명 오류 — 설정의 API 연결 정보를 확인하세요.',
        -2014:'API 키 형식 오류 — 설정의 API 연결 정보를 확인하세요.',
        -2015:'API 권한·IP 제한 오류 — 기관의 API 권한과 허용 IP를 확인하세요.',
    }
    return {'status':'REJECTED' if rejected else 'UNKNOWN',
            'provider_error_code':code or None,
            'submission_attempted':bool(submission_attempted),
            'error':('주문 제출 전 확인 실패 — API 연결·시세·종목 규격 자료를 다시 확인하세요.' if not submission_attempted else explanations.get(code,f'기관이 주문 요청을 거절했습니다 ({code}). 주문 규격·잔고·기관 상태를 확인하세요.')) if rejected else type(error).__name__,
            'reconciliation_required':not rejected}
