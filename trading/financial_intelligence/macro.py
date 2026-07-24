from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping


class MacroRegimeEngine:
    """거시 지표를 버전 있는 규칙으로 분류한다."""

    VERSION = "macro-rule-1"

    def classify(self, indicators: Mapping[str, Any]) -> Dict[str, Any]:
        growth = float(indicators.get("growth_z", 0.0) or 0.0)
        inflation = float(indicators.get("inflation_z", 0.0) or 0.0)
        liquidity = float(indicators.get("liquidity_z", 0.0) or 0.0)
        credit = float(indicators.get("credit_stress_z", 0.0) or 0.0)
        rates = float(indicators.get("rates_change_z", 0.0) or 0.0)
        if growth >= 0.2 and inflation <= 0.5:
            cycle = "확장"
        elif growth < -0.5 and credit > 0.5:
            cycle = "침체"
        elif growth < 0:
            cycle = "둔화"
        else:
            cycle = "회복"
        inflation_regime = "인플레이션" if inflation > 0.5 else "디스인플레이션" if inflation < -0.2 else "중립"
        rate_regime = "금리상승" if rates > 0.2 else "금리하락" if rates < -0.2 else "금리중립"
        risk_score = min(100.0, max(0.0, 50.0 - growth * 15.0 + inflation * 12.0 - liquidity * 10.0 + credit * 18.0 + rates * 8.0))
        impacts = {
            "equity": "우호" if cycle in {"확장", "회복"} and credit < 0.5 else "불리",
            "bonds": "우호" if rate_regime == "금리하락" else "중립" if rate_regime == "금리중립" else "불리",
            "commodities": "우호" if inflation_regime == "인플레이션" else "중립",
            "usd": "우호" if rate_regime == "금리상승" or credit > 0.5 else "중립",
            "crypto": "우호" if liquidity > 0.3 and credit < 0.5 else "불리" if credit > 1.0 else "중립",
        }
        return {
            "cycle": cycle,
            "inflation_regime": inflation_regime,
            "rate_regime": rate_regime,
            "risk_score": risk_score,
            "asset_impacts": impacts,
            "rule_version": self.VERSION,
            "inputs": dict(indicators),
            "counter_scenario": "성장·물가·유동성 지표가 다음 발표에서 반전될 경우 현재 분류가 변경될 수 있음",
        }


class IndustryAnalyzer:
    def analyze(
        self,
        companies: Iterable[Mapping[str, Any]],
        value_chain: Iterable[Mapping[str, Any]] = (),
        fund_flows: Mapping[str, float] | None = None,
    ) -> Dict[str, Any]:
        rows = [dict(row) for row in companies]
        if not rows:
            return {"status": "no_data", "companies": [], "value_chain": list(value_chain)}
        growth_values = [float(row.get("revenue_growth", 0.0) or 0.0) for row in rows]
        margins = [float(row.get("operating_margin", 0.0) or 0.0) for row in rows]
        valuations = [float(row.get("valuation_multiple", 0.0) or 0.0) for row in rows if row.get("valuation_multiple") is not None]
        leaders = sorted(
            rows,
            key=lambda row: (
                float(row.get("revenue_growth", 0.0) or 0.0),
                float(row.get("operating_margin", 0.0) or 0.0),
            ),
            reverse=True,
        )
        return {
            "status": "ok",
            "company_count": len(rows),
            "average_growth": sum(growth_values) / len(growth_values),
            "average_margin": sum(margins) / len(margins),
            "median_valuation": sorted(valuations)[len(valuations) // 2] if valuations else None,
            "leaders": leaders[:10],
            "value_chain": list(value_chain),
            "fund_flows": dict(fund_flows or {}),
            "risk_signals": sorted({risk for row in rows for risk in (row.get("risk_signals") or [])}),
        }
