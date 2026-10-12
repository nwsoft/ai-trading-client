"""Finite user-facing entry diagnostics from existing owner/mode evidence only."""

MESSAGES = {
    'trading_candidate_catalogue_unavailable': ('현재 종목 목록 조회 실패', '공개 시세 연결을 확인하세요. 엔진은 다음 선정 주기에 재조회합니다. 시작 실패로 정지했다면 연결 확인 후 시작을 다시 누르세요.'),
    'trading_candidate_markets_unavailable': ('지원되는 거래 종목 없음', '해당 기관의 상품·USDT 결제통화와 거래지원 상태를 확인하세요.'),
    'trading_candidate_tickers_unavailable': ('현재 종목 시세 조회 실패', '공개 시세 연결을 확인하세요. 다음 선정 주기에 자동 재조회합니다.'),
    'trading_candidate_filters_excluded': ('종목 선정 필터 통과 없음', '설정에서 해당 기관의 최소 거래대금·최대 변동성과 현재 시장을 비교하세요.'),
    'paper_ledger_currency_unverified': ('과거 PAPER 결제통화 근거 누락', '전략 삭제 불필요. 거래소 자동매매를 정지한 뒤 ‘운용 요약 → 가상자금 복구 안내’ 순서로 확인하세요. 전략 검증 OFF와 거래소 정지는 다릅니다.'),
    'paper_ledger_pnl_unverified': ('과거 PAPER 손익·비용 근거 부족', '전략 삭제 불필요. 거래소 자동매매를 정지한 뒤 ‘운용 요약 → 가상자금 복구 안내’ 순서로 확인하세요. 전략 검증 OFF와 거래소 정지는 다릅니다.'),
    'paper_funds_unverified': ('가상 자금 대조 필요', '운용 요약의 자금 배분 근거와 거래 기록 점검에서 원장·보유량을 대조하세요.'),
    'paper_session_ready': ('새 PAPER 평가 준비됨', '과거 기록은 보존되었습니다. 시작 버튼을 누르면 현재 시세·전략·위험 조건을 다시 검사합니다.'),
    'available_balance_unverified': ('주문 가능금액 확인 필요', '해당 기관의 API 연결·주문 가능금액 조회 권한을 확인하세요.'),
    'risk_blocked': ('위험 평가로 신규 진입 보류', '운용 요약의 위험 평가와 해당 기관의 위험 설정·거래 기록을 확인하세요.'),
    'pre_entry_confidence_low': ('진입 신뢰도 기준 미충족', '운용 요약에서 실제 신뢰도와 적용 기준을 비교하세요. 설정의 신호 기준과 전략 조건을 검토할 수 있습니다.'),
    'pre_entry_loss_rate_high': ('완료 거래 손실률 기준 미충족', '거래 통계와 적용 전략의 완료 거래 근거를 확인하세요. 손실 기록을 삭제해 해제하지 마세요.'),
    'pre_entry_history_required': ('설정된 완료 거래 표본 부족', '적용 전략·학습 설정의 필요 표본을 확인하세요.'),
    'pre_entry_volatility_unsuitable': ('변동성 조건 미충족', '현재 시장과 전략의 변동성 범위를 확인하세요. 다음 주기에 재평가합니다.'),
    'strategy_consensus_low': ('전략 합의 기준 미충족', '전략 스튜디오에서 기본·confirm 전략의 합의 조건을 확인하세요.'),
    'strategy_guardrail_blocked': ('전략 가드레일로 진입 보류', '전략 스튜디오와 거래 통계에서 실제 가드레일 근거를 확인하세요.'),
    'candidate_blocked': ('전략 진입 조건 대기', '운용 요약의 최근 후보 조건을 확인하세요. 다음 분석 주기에 재평가합니다.'),
    'hold': ('거래 신호 대기', '현재 전략의 진입 조건이 충족되면 다시 평가합니다. 운용 요약에서 조건과 관찰 시각을 확인하세요.'),
    'position_managed': ('동일 종목 보유 중', '보유 PAPER 포지션 또는 해당 기관의 관리 포지션을 확인하세요.'),
    'entry_recorded': ('최근 주문 처리 기록 있음', 'PAPER는 가상 거래입니다. 실제 접수·체결 여부는 거래 기록에서 확인하세요.'),
    'entry_skipped': ('신규 진입 미실행', '상세 로그의 최근 거래 판단과 자금·포지션·주문 예약을 확인하세요.'),
    'execution_failed': ('주문 처리 실패 또는 상태 미확인', '상세 로그와 기관 주문 내역을 대조하세요. 미확정 주문을 반복 제출하지 마세요.'),
    'paper_funds_reconciliation_required': ('가상 자금 대조 필요', '자금 배분 근거에서 PAPER 원장·보유량을 확인하세요.'),
    'available_capital_or_notional_unverified': ('주문 가능금액·주문 규모 미확인', '자금 배분 근거와 해당 기관의 주문 가능금액 조회를 확인하세요.'),
    'available_capital_insufficient': ('주문 가능금액 부족', '자금 배분 근거와 주문 규모·보유 증거금을 비교하세요.'),
    'available_capital_reserved_by_other_orders': ('다른 주문에 자금 예약 중', '주문 예약과 해당 기관의 미확정 주문을 대조하세요.'),
    'previous_order_reconciliation_required': ('이전 주문 상태 대조 필요', '미확정 주문과 기관 주문 내역을 대조하세요. 반복 제출하지 마세요.'),
    'reservation_capacity_reconciliation_required': ('주문 예약 상태 대조 필요', '주문 예약 내역과 기관 주문 상태를 확인하세요.'),
    'duplicate_order_same_target_account_signal': ('동일 신호 주문 중복 방지', '같은 기관·계정의 기존 주문 처리 상태를 확인하세요.'),
    'max_parallel_targets_exceeded': ('동시 운용 기관 제한 도달', '다중 거래소 설정의 동시 운용 수와 보유·예약을 확인하세요.'),
    'aggregate_loss_cap_exceeded': ('기관 합산 손실 한도 도달', '다중 거래소 위험 한도와 해당 통화의 손실 근거를 확인하세요.'),
    'target_not_authorized': ('해당 기관 신규 주문 미허용', '기관별 실행 모드와 거래 허용 범위를 확인하세요.'),
    'profitability_blocked': ('수익성 검증 조건 미충족', '거래 통계와 적용 전략의 수익성 검증 근거를 확인하세요.'),
    'pre_entry_error': ('진입 전 분석 오류', '최근 분석 로그와 시세 수신 상태를 확인하세요.'),
    'dynamic_confidence_error': ('신뢰도 기준 계산 오류', '최근 분석 로그와 전략·학습 설정을 확인하세요.'),
    'order_spec_or_final_safety_blocked': ('최종 주문 규격·안전 검사 미통과', '주문 수량·최소 주문금액·위험 평가와 최근 실행 로그를 확인하세요.'),
    'remote_entries_paused': ('원격 제어로 신규 진입 일시 정지', '원격 관리의 진입 일시 정지 상태를 확인하세요.'),
    'instrument_catalogue_unavailable': ('현재 주문 종목 목록 조회 실패', '공개 시세 연결과 종목 선정 상태를 확인하세요.'),
    'instrument_not_listed': ('현재 목록에서 주문 종목 미확인', '상장·거래지원 상태와 선정된 종목을 확인하세요.'),
    'instrument_halted': ('주문 종목 거래 중단·점검 중', '해당 기관의 종목 거래 상태를 확인하세요.'),
    'instrument_delisted': ('주문 종목 거래지원 종료·만기', '해당 기관의 종목 거래지원 상태를 확인하세요.'),
    'instrument_close_only': ('해당 종목 청산만 허용', '기관의 종목 제한을 확인하세요. 신규 진입은 허용되지 않습니다.'),
    'instrument_sell_disabled': ('해당 종목 매도 제한', '기관의 종목 제한을 확인하세요.'),
    'instrument_wrong_product': ('주문 상품·결제통화 불일치', '기관별 지원 상품과 결제통화를 확인하세요.'),
    'instrument_unknown': ('주문 종목 거래 가능 상태 미확인', '현재 종목 목록의 거래 가능 상태를 확인하세요.'),
    'unavailable': ('거래 판단 근거 미수신', '기관 실행 상태와 연결을 확인하세요. 근거 없음은 정상 거래나 거래 0건의 확인이 아닙니다.'),
}


def decision_code(status, reason):
    text = str(reason or '')
    # Preserve coordinator's finite reason codes; never export its raw message.
    import re
    tokens = set(re.findall(r'[a-z][a-z0-9_]+', text))
    for code in MESSAGES:
        if code in tokens:
            return code
    for fragment, code in (
        ('AI 신뢰도 부족', 'pre_entry_confidence_low'), ('동적 신뢰도 부족', 'pre_entry_confidence_low'),
        ('수익성 검증 차단', 'profitability_blocked'),
        ('최종 주문 규격 또는 안전 게이트 미통과', 'order_spec_or_final_safety_blocked'),
        ('높은 손실률', 'pre_entry_loss_rate_high'),
        ('거래 이력 부족', 'pre_entry_history_required'), ('변동성 부적절', 'pre_entry_volatility_unsuitable'),
        ('consensus_low', 'strategy_consensus_low'), ('전략 가드레일', 'strategy_guardrail_blocked'),
        ('동일 종목 포지션', 'position_managed'), ('PAPER 청산 기록', 'paper_funds_unverified'),
    ):
        if fragment in text:
            return code
    if status in MESSAGES:
        return status
    if status in {'success', 'executed'}:
        return 'entry_recorded'
    if status in {'hold', 'candidate_blocked'}:
        return status
    if status in {'failed', 'error', 'unknown', 'pre_entry_error'}:
        return 'execution_failed'
    return 'entry_skipped'


def monitored_cycle(source=None):
    """Observe worker return/heartbeat without changing any order or exception."""
    from functools import wraps
    def decorate(function):
        @wraps(function)
        def wrapped(owner, *args, **kwargs):
            from .operation_evidence import generation, mode_for, publish
            venue = source or (args[0] if args else kwargs.get('exchange_name', ''))
            epoch, mode = generation(owner, venue), mode_for(owner, venue)
            publish(owner, venue, 'cycle', mode=mode, phase='started', expected_generation=epoch)
            try:
                return function(owner, *args, **kwargs)
            finally:
                publish(owner, venue, 'cycle', mode=mode, phase='returned', expected_generation=epoch)
        return wrapped
    return decorate


def entry_activity(evidence, *, running, now=None):
    """Session-only inactivity notice, never a claim about historical fills.

    Thirty minutes and three returned cycles trigger an attention notice even
    for legitimate HOLD. Fifteen minutes without a worker heartbeat is separate.
    Snapshot reads are pure: opening a page cannot advance timers or counters.
    """
    import time
    from collections import Counter
    now = time.time() if now is None else now
    activity = evidence.get('activity') or {}
    started = activity.get('observed_since')
    baseline = activity.get('last_entry_at') or started
    elapsed = max(0, now-baseline) if baseline else None
    heartbeat = max(activity.get('last_cycle_started_at') or 0,
                    activity.get('last_cycle_returned_at') or 0)
    counts = Counter(activity.get('recent_reasons') or [])
    reasons = [dict(code=code, label=MESSAGES[code][0], count=count)
               for code,count in counts.most_common(3) if code in MESSAGES]
    status, label, attention = 'observing', '신규 주문 처리 관찰 중', False
    if not running:
        status, label = 'stopped', '기관 정지 · 무거래 감시 중단'
    elif evidence.get('mode') == 'learning':
        status, label = 'learning', '관찰 모드 · 주문 실행 대상 아님'
    elif evidence.get('source') and evidence['source'] not in {'binance','bybit','bitget','okx','upbit','bithumb','coinone'}:
        status, label = 'unsupported', '해당 기관의 무거래 감시 근거 미제공'
    elif not started:
        status, label, attention = 'unobserved', '실행 엔진 관찰 근거 미수신', True
    elif not heartbeat or now-heartbeat >= 900:
        status, label, attention = 'heartbeat_stale', '실행 주기 갱신 확인 필요', True
    elif elapsed >= 1800 and activity.get('returned_cycles', 0) >= 3:
        status, label, attention = 'no_recent_entry', '30분 이상 신규 주문 처리 기록 없음', True
    action = ('기관의 실행 상태·최근 로그와 연결을 확인하세요.' if status in {'heartbeat_stale', 'unobserved'}
              else '아래 최근 판단 분포와 보류 사유를 확인하세요. 신호 대기는 정상일 수 있으며 거래 빈도를 보장하지 않습니다.')
    return dict(status=status, label=label, attention=attention, action=action,
                observed_since=started, no_entry_seconds=elapsed,
                last_entry_at=activity.get('last_entry_at'), last_cycle_at=heartbeat or None,
                returned_cycles=activity.get('returned_cycles', 0), recent_reasons=reasons,
                scope='current_runtime_session', reason_window=128)


def record_entry(owner, source, status, reason, *, mode=None, symbol='', expected_generation=None):
    from .operation_evidence import publish
    publish(owner, source, 'entry', mode=mode, symbol=symbol,
            expected_generation=expected_generation, code=decision_code(status, reason))


def entry_health(evidence):
    """Priority: safety/data blockers, then final execution, then candidate stage.

    A later regime heartbeat cannot overwrite a downstream execution blocker.
    Raw provider errors/account fields are never projected into this contract.
    """
    row, code, blocked = {}, 'unavailable', False
    risk, capital = evidence.get('risk') or {}, evidence.get('capital') or {}
    selection = evidence.get('selection_failure') or {}
    entry, candidate = evidence.get('entry') or {}, evidence.get('candidate') or {}
    if risk.get('blocked'):
        row, code, blocked = risk, 'risk_blocked', True
    elif capital.get('capital_basis') in {'paper_funds_unverified', 'available_balance_unverified'}:
        row, code, blocked = capital, capital['capital_basis'], True
        if capital.get('reason') in MESSAGES:
            code = capital['reason']
    elif selection.get('reason') in MESSAGES:
        row, code, blocked = selection, selection['reason'], True
    elif (capital.get('paper_session_id') and capital.get('capital_basis') == 'paper_reconciled_funds'
          and (capital.get('observed_at') or 0) > (entry.get('observed_at') or 0)):
        row, code = capital, 'paper_session_ready'
    elif entry:
        row, code = entry, entry.get('code', 'unavailable')
        blocked = code not in {'hold', 'candidate_blocked', 'entry_recorded', 'position_managed', 'unavailable'}
    elif candidate:
        row = candidate
        code = 'candidate_blocked' if candidate.get('allowed') is False else 'hold'
    if code not in MESSAGES:
        code = 'unavailable'
    label, action = MESSAGES[code]
    return dict(code=code, label=label, action=action, blocked=blocked,
                observed_at=row.get('observed_at'), since=row.get('since') or row.get('observed_at'),
                consecutive_count=row.get('consecutive_count'), last_entry_at=entry.get('last_entry_at'))


def record_pre_entry(owner, source, *, symbol, proceed, confidence, threshold, pattern, limits):
    from .operation_evidence import publish
    observed = not pattern.get('used_defaults') and pattern.get('recent_trades', 0) > 0
    publish(owner, source, 'pre_entry', symbol=symbol, allowed=proceed,
            confidence=confidence, required_confidence=threshold, history_observed=observed,
            loss_rate=pattern.get('loss_rate') if observed else None,
            max_loss_rate=limits.get('max_loss_rate'), recent_trades=pattern.get('recent_trades'),
            min_trades_history=limits.get('min_trades_history'))
