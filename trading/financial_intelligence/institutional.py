from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, Mapping


class InstitutionalHoldingsAnalyzer:
    def changes(
        self,
        current: Iterable[Mapping[str, Any]],
        previous: Iterable[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        current_map = {str(row.get("symbol") or "").upper(): dict(row) for row in current}
        previous_map = {str(row.get("symbol") or "").upper(): dict(row) for row in previous}
        output = []
        for symbol in sorted(set(current_map) | set(previous_map)):
            now = current_map.get(symbol, {})
            before = previous_map.get(symbol, {})
            now_weight = float(now.get("weight", 0.0) or 0.0)
            before_weight = float(before.get("weight", 0.0) or 0.0)
            if not before and now:
                action = "신규 편입"
            elif before and not now:
                action = "청산 추정"
            elif now_weight > before_weight:
                action = "비중 확대"
            elif now_weight < before_weight:
                action = "비중 축소"
            else:
                action = "유지"
            output.append(
                {
                    "symbol": symbol,
                    "current_weight": now_weight,
                    "previous_weight": before_weight,
                    "weight_change": now_weight - before_weight,
                    "action": action,
                    "filing_date": now.get("filing_date") or before.get("filing_date"),
                    "report_period": now.get("report_period") or before.get("report_period"),
                    "data_delay_warning": True,
                }
            )
        return {"changes": output, "is_realtime_signal": False}

    def consensus(self, portfolios: Mapping[str, Iterable[Mapping[str, Any]]], min_holders: int = 2) -> list[Dict[str, Any]]:
        holders: Dict[str, list[str]] = defaultdict(list)
        weights: Dict[str, list[float]] = defaultdict(list)
        for institution, rows in portfolios.items():
            for row in rows:
                symbol = str(row.get("symbol") or "").upper()
                if not symbol:
                    continue
                holders[symbol].append(str(institution))
                weights[symbol].append(float(row.get("weight", 0.0) or 0.0))
        result = [
            {
                "symbol": symbol,
                "holder_count": len(names),
                "holders": sorted(names),
                "average_weight": sum(weights[symbol]) / len(weights[symbol]),
            }
            for symbol, names in holders.items()
            if len(names) >= max(1, int(min_holders))
        ]
        result.sort(key=lambda row: (row["holder_count"], row["average_weight"]), reverse=True)
        return result

    @staticmethod
    def overlap(user_positions: Iterable[Mapping[str, Any]], institution_positions: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        user = {str(row.get("symbol") or "").upper() for row in user_positions}
        institution = {str(row.get("symbol") or "").upper() for row in institution_positions}
        common = sorted((user & institution) - {""})
        union = (user | institution) - {""}
        return {
            "common_symbols": common,
            "overlap_ratio": len(common) / len(union) if union else 0.0,
        }
