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


def scoped_pool(strategies, *, asset_class: str, target: str, limit: int | None = None):
    eligible = scope_candidates(strategies, asset_class=asset_class, target=target)
    if limit is not None:
        return eligible[:max(0, int(limit))]
    cap = max([int(v.get('_runtime_paper_limit', 10)) for v in eligible
               if v.get('operation_mode') == 'paper_validation'] or [10])
    cap = max(1, min(30, cap))
    selected, applied = [], 0
    for item in eligible:
        if len(selected) >= cap:
            break
        if item.get('operation_mode') != 'paper_validation':
            if applied >= 10:
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
