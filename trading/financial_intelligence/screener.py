from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping


class QuantScreener:
    """주식·ETF·코인에서 같은 조건 문법을 사용하는 스크리너."""

    OPERATORS = {
        "eq": lambda a, b: a == b,
        "ne": lambda a, b: a != b,
        "gt": lambda a, b: a is not None and a > b,
        "gte": lambda a, b: a is not None and a >= b,
        "lt": lambda a, b: a is not None and a < b,
        "lte": lambda a, b: a is not None and a <= b,
        "in": lambda a, b: a in b,
        "contains": lambda a, b: b in a if a is not None else False,
        "between": lambda a, b: a is not None and b[0] <= a <= b[1],
    }

    @staticmethod
    def _get(row: Mapping[str, Any], path: str) -> Any:
        value: Any = row
        for part in str(path).split("."):
            if not isinstance(value, Mapping):
                return None
            value = value.get(part)
        return value

    def matches(self, row: Mapping[str, Any], conditions: Iterable[Mapping[str, Any]]) -> tuple[bool, List[str]]:
        reasons: List[str] = []
        for condition in conditions:
            field = str(condition.get("field") or "")
            operator = str(condition.get("op") or "eq")
            target = condition.get("value")
            actual = self._get(row, field)
            fn = self.OPERATORS.get(operator)
            try:
                passed = bool(fn(actual, target)) if fn else False
            except Exception:
                passed = False
            if not passed:
                return False, reasons
            reasons.append(f"{field} {operator} {target}")
        return True, reasons

    def screen(
        self,
        universe: Iterable[Mapping[str, Any]],
        conditions: Iterable[Mapping[str, Any]],
        score_weights: Mapping[str, float] | None = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        condition_rows = list(conditions)
        for source in universe:
            row = dict(source)
            matched, reasons = self.matches(row, condition_rows)
            if not matched:
                continue
            components: Dict[str, float] = {}
            weighted_sum = 0.0
            total_weight = 0.0
            for field, weight in (score_weights or {}).items():
                try:
                    value = float(self._get(row, field) or 0.0)
                    components[field] = value
                    weighted_sum += value * float(weight)
                    total_weight += abs(float(weight))
                except Exception:
                    continue
            row["screen_reasons"] = reasons
            row["score_components"] = components
            row["screen_score"] = weighted_sum / total_weight if total_weight else 0.0
            row["data_sufficient"] = not bool(row.get("quality_flags"))
            results.append(row)
        results.sort(key=lambda item: float(item.get("screen_score", 0.0)), reverse=True)
        return results[: max(1, int(limit))]

    def account_eligibility(
        self,
        row: Mapping[str, Any],
        available_cash: float,
        risk_budget: float,
    ) -> Dict[str, Any]:
        price = float(row.get("price", 0.0) or 0.0)
        min_quantity = float(row.get("min_quantity", 1.0) or 1.0)
        min_notional = max(float(row.get("min_notional", 0.0) or 0.0), price * min_quantity)
        estimated_slippage_bps = abs(float(row.get("estimated_slippage_bps", 0.0) or 0.0))
        required = min_notional * (1.0 + estimated_slippage_bps / 10000.0)
        allowed = required <= float(available_cash) and required <= float(risk_budget)
        return {
            "eligible": allowed,
            "required_amount": required,
            "available_cash": available_cash,
            "risk_budget": risk_budget,
            "reason": "진입 가능" if allowed else "현금 또는 위험예산 부족",
        }
