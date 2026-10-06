"""Bounded explanation of selection, independent of entry/risk permission."""
from __future__ import annotations
import math
import time
from typing import Any, Iterable, Mapping
from .selection_policy import candidate_execution_eligible


def selection_evidence(source: str, rows: Iterable[Mapping[str, Any]], *,
                       observed_at: float | None = None, rejected=(), issues=(),
                       basis: str = 'scored_market_candidates') -> dict:
    selected = []
    for item in list(rows)[:60]:
        if not isinstance(item, Mapping):
            continue
        symbol = str(item.get('symbol') or item.get('code') or '').strip().upper()[:40]
        if not symbol:
            continue
        raw_score = item.get('overall_score', item.get('score'))
        try:
            score = float(raw_score) if raw_score is not None and not isinstance(raw_score, bool) else None
            if score is not None and not math.isfinite(score): score = None
        except (TypeError, ValueError): score = None
        selected.append({'symbol': symbol, 'score': score,
                         'reason': str(item.get('selection_reason') or item.get('reasoning')
                                       or item.get('reason') or basis)[:300],
                         'selection_status': str(item.get('selection_status') or 'scored')[:60],
                         'execution_eligible': candidate_execution_eligible(item),
                         'selection_source': str(item.get('selection_source') or 'automatic')[:60]})
    return {'source': source, 'observed_at': observed_at if observed_at is not None else time.time(),
            'selected': selected, 'eligible_count': sum(r['execution_eligible'] for r in selected),
            'excluded': [str(v)[:80] for v in list(rejected)[:60]],
            'issues': [str(v)[:120] for v in list(issues)[:12]], 'basis': basis,
            'status': 'candidates' if selected else 'unavailable',
            'market_data_freshness': 'not_certified_by_selection_snapshot',
            'entry_permission': 'requires_current_analysis_risk_and_order_checks'}
