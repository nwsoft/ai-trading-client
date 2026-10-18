"""Shared asset/venue scope contract for selection, observation and display."""
from __future__ import annotations


def canonical_venue(value: str) -> str:
    value = str(value or "").strip().lower().replace("_", "")
    return {"koreainvestment": "kis", "miraeasset": "mirae"}.get(value, value)


def scope_matches(scope: str, *, asset_class: str, target: str) -> bool:
    scope = str(scope or "asset:crypto").strip().lower()
    asset = str(asset_class or "").strip().lower()
    family = "stock" if asset == "etf" else asset
    if scope == "asset:all" or scope == f"asset:{family}" or scope == f"asset:{asset}":
        return True
    kind, _, names = scope.partition(":")
    if kind not in {"broker", "exchange"}:
        return False
    if family != ("stock" if kind == "broker" else "crypto"):
        return False
    if names in {"connected", "unified"}:
        return True
    return canonical_venue(target) in {canonical_venue(name) for name in names.split(",") if name.strip()}


def scope_candidates(strategies, *, asset_class: str, target: str):
    eligible = [item for item in strategies if isinstance(item, dict) and scope_matches(
        item.get("target_scope") or (item.get("rules") or {}).get("target_scope"),
        asset_class=asset_class, target=target,
    )]
    return sorted(eligible, key=lambda item: int(item.get("priority", 5) or 5), reverse=True)


def runtime_paper_pool(strategies, owner):
    """Derive the PAPER entitlement from runtime membership, not strategy JSON."""
    from membership_policy import normalize_user_grade
    maximum = 30 if normalize_user_grade(getattr(owner, 'current_user_grade', '')) == 'premium' else 10
    try:
        requested = int((getattr(owner, 'settings', {}) or {}).get('paper_strategy_evaluation_limit', maximum))
    except (TypeError, ValueError):
        requested = maximum
    cap = max(1, min(maximum, requested))
    output = []
    for item in strategies:
        row = dict(item)
        row.pop('_runtime_paper_limit', None)
        if row.get('operation_mode') == 'paper_validation':
            row['_runtime_paper_limit'] = cap
        output.append(row)
    return output


def runtime_applied_pool(strategies, owner):
    """Only runtime membership may raise LIVE evaluation capacity. Default stays ten."""
    from membership_policy import normalize_user_grade
    maximum = 30 if normalize_user_grade(getattr(owner, "current_user_grade", "")) == "premium" else 10
    try: requested = int((getattr(owner, "settings", {}) or {}).get("live_strategy_evaluation_limit", 10))
    except (ValueError, TypeError): requested = 10
    cap = max(1, min(maximum, requested))
    return [{**row, "_runtime_applied_limit":cap} for row in strategies]


def scoped_pool(strategies, *, asset_class: str, target: str, limit: int | None = None):
    eligible = scope_candidates(strategies, asset_class=asset_class, target=target)
    if limit is not None:
        return eligible[:max(0, int(limit))]
    applied_cap = max(1, min(30, max([int(v.get("_runtime_applied_limit", 10)) for v in eligible] or [10])))
    cap = max([int(v.get('_runtime_paper_limit', 10)) for v in eligible
               if v.get('operation_mode') == 'paper_validation'] or [10])
    cap = max(applied_cap if any(v.get("operation_mode") != "paper_validation" and "_runtime_applied_limit" in v for v in eligible) else 1, max(1, min(30, cap)))
    selected, applied = [], 0
    for item in eligible:
        if len(selected) >= cap:
            break
        if item.get('operation_mode') != 'paper_validation':
            if applied >= applied_cap:
                continue
            applied += 1
        selected.append(item)
    return selected


def paper_pool_status(strategies, *, asset_class, target):
    candidates = scope_candidates(strategies, asset_class=asset_class, target=target)
    selected = scoped_pool(candidates, asset_class=asset_class, target=target)
    observing = [v for v in candidates if v.get('operation_mode') == 'paper_validation']
    chosen = [v for v in selected if v.get('operation_mode') == 'paper_validation']
    return {'scope_eligible': len(observing), 'selected': len(chosen),
            'waiting': len(observing)-len(chosen),
            'limit': int(observing[0].get('_runtime_paper_limit', 10)) if observing else 10,
            'applied_slots': len(selected)-len(chosen),
            'selection': 'priority_then_registration', 'independent_portfolios': False,
            'waiting_versions': [str(v.get('version_id') or v.get('id') or '')[:120]
                                 for v in observing if v not in chosen][:30]}


def strategy_runtime_support(rules):
    """Explain existing venue data support without granting or revoking execution."""
    from trading.exchanges.venue_capabilities import STOCK_VENUES
    scope = str(rules.get('target_scope') or 'asset:crypto')
    brokers = [v for v in sorted(STOCK_VENUES) if scope_matches(scope, asset_class='stock', target=v)]
    timeframe = str(rules.get('decision_timeframe') or '15m')
    from trading.stock_candles import STOCK_INTRADAY_MINUTES
    supported = [v for v in brokers if timeframe == '1d' or (v in {'kiwoom','kis','koreaInvestment'} and timeframe in STOCK_INTRADAY_MINUTES)]
    unsupported = [v for v in brokers if v not in supported]
    return {'status':'stock_timeframe_unsupported' if unsupported else 'scope_supported_data_required',
            'timeframe':timeframe,'affected_brokers':unsupported,
            'supported_brokers':supported,
            'message':(f'증권 {timeframe} 분봉: 키움·한국투자에서 완료봉을 조회해 PAPER·운용 평가합니다. 한국투자 모의 서버는 당일 자료만 제공하므로 장 초반·긴 시간봉의 표본이 부족할 수 있습니다. 자료 수집 중/부족은 진입 근거 미확보로 표시하며 일봉으로 대체하지 않습니다. 증권 과거 재생은 일봉 경로와 구분됩니다. '
                       + (f"미지원 기관: {', '.join(unsupported)}. 해당 기관에서는 평가할 수 없습니다." if unsupported else '')) if brokers and timeframe != '1d' else '',
            'grants_execution':False}
