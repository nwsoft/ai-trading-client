"""Read-only PAPER attribution. A trade notional is never an account capital base."""
from __future__ import annotations
import math


def cohort(row):
    parallel = row.get("validation_path") == "parallel_validation" or row.get("exit_policy_source") == "custom_strategy_parallel_paper"
    path = "parallel_validation" if parallel else "runtime_paper"
    basis = str(row.get("capital_basis") or ("independent_strategy_virtual_equity" if parallel else "runtime_virtual_account"))
    value = row.get("capital_reference")
    try: value = float(value) if value is not None and not isinstance(value, bool) else None
    except (ValueError, TypeError): value = None
    if value is not None and (not math.isfinite(value) or value <= 0): value = None
    label = "LIVE 병행 PAPER 검증" if parallel else "일반 PAPER"
    # Runtime equity changes with every fill; do not create one filter option per balance tick.
    key_reference = value if parallel else ("recorded" if value is not None else None)
    return {"validation_path":path, "capital_basis":basis, "capital_reference":value if parallel else None, "capital_observed_at_entry":value,
            "capital_label":("전략별 독립 가상자금" if parallel else "가상 계정 자금") +
                ((f" · 기준금액 {value:g}" if parallel else " · 진입 시점 관측자금(고정기준 아님)") if value is not None else " · 기준금액 미기록"),
            "validation_label":label, "cohort_key":f"{path}|{basis}|{key_reference}"}
