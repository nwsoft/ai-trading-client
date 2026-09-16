"""Missing market data is not a normal market. Keep trading health separate."""
from functools import wraps


def observation_problem(owner, venue, reason, rows=None, error=None, **details):
    from .market_data_utils import failed_candles
    failure = failed_candles(reason, error) if error is not None else rows
    states = getattr(owner, '_market_observation_detail', None)
    if not isinstance(states, dict):
        states = {}
        owner._market_observation_detail = states
    states[venue] = {'reason': getattr(failure, 'reason', '') or reason,
                     'error_type': getattr(failure, 'error_type', ''),
                     'status_code': getattr(failure, 'status_code', None), **details}


def track_market_observation(fixed_venue=None):
    def decorate(method):
        @wraps(method)
        def observe(owner, *args, **kwargs):
            venue = fixed_venue or (args[0] if args else kwargs['exchange_name'])
            regime = method(owner, *args, **kwargs)
            states = getattr(owner, '_market_data_unavailable', None)
            if not isinstance(states, dict):
                states = {}
                owner._market_data_unavailable = states
            missing = regime == 'unknown'
            if missing and getattr(owner, '_regime_stabilizer', None) is not None:
                owner._regime_stabilizer.observe(venue, 'unknown')
            changed = states.get(venue) != missing
            states[venue] = missing
            detail = getattr(owner, '_market_observation_detail', {}).get(venue, {})
            reason = str(detail.get('reason') or 'observation_unavailable')
            cause = f"원인={reason} · 오류유형={detail.get('error_type') or '-'} · HTTP={detail.get('status_code') or '-'}"
            if missing or changed:
                from trading.runtime_observability import emit_runtime_status
                emit_runtime_status(owner, venue, 'market_data_missing' if missing else 'market_data_ready',
                    f'시장국면 확인 불가 · {cause} · 신규 진입 보류. 기존 포지션 관리 시도는 계속하나 시세/주문 API 장애 시 청산을 보장하지 않습니다.' if missing else '시장국면 시세 데이터 확인 완료',
                    level='WARNING' if missing else 'INFO')
            return regime
        return observe
    return decorate
