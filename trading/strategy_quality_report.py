"""과거·PAPER·LIVE 근거를 섞지 않는 전략 품질 리포트."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping


def build_strategy_quality_report(
    *, validation_lab: Mapping[str, Any] | None = None,
    paper_validation: Mapping[str, Any] | None = None,
    live_observation: Mapping[str, Any] | None = None,
    equivalence_report: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    lab = deepcopy(dict(validation_lab or {}))
    paper = deepcopy(dict(paper_validation or {}))
    live = deepcopy(dict(live_observation or {}))
    equivalence = deepcopy(dict(equivalence_report or {}))
    evidence = {
        "historical_replay": {"available": bool(lab), "data": lab},
        "paper_forward": {"available": bool(paper), "data": paper},
        "live_execution": {"available": bool(live), "data": live},
        "source_equivalence": {"available": bool(equivalence), "data": equivalence},
    }
    warnings = []
    if not paper or not paper.get("passed"):
        warnings.append("paper_forward_not_passed")
    if (lab.get("overfit_risk") or {}).get("flagged"):
        warnings.append("overfit_risk_flagged")
    if equivalence and not equivalence.get("equivalent"):
        warnings.append("source_replay_difference")
    return {
        "schema_version": 1,
        "evidence": evidence,
        "warnings": warnings,
        "historical_only": bool(lab) and not bool(paper) and not bool(live),
        "future_performance_guaranteed": False,
        "promotion_recommendation": "review" if warnings else "eligible_for_user_review",
        "auto_promoted": False,
    }


def compare_replay_trades(reference: list[Mapping[str, Any]], noah: list[Mapping[str, Any]]) -> Dict[str, Any]:
    differences = []
    total = max(len(reference), len(noah))
    for index in range(total):
        left = dict(reference[index]) if index < len(reference) else {}
        right = dict(noah[index]) if index < len(noah) else {}
        fields = {}
        for field in ("entry_time", "exit_time", "entry_price", "exit_price", "side", "cost_percent"):
            if left.get(field) != right.get(field):
                fields[field] = {"reference": left.get(field), "noah": right.get(field)}
        if fields:
            differences.append({"trade_index": index, "fields": fields})
    return {
        "schema_version": 1,
        "reference_trades": len(reference), "noah_trades": len(noah),
        "equivalent": not differences,
        "differences": differences,
        "comparison_dimensions": ["candle_time", "fill_price", "side", "cost_model"],
    }
