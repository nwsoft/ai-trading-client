from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional


class FundamentalAnalyzer:
    """공급자별 재무 필드를 공통 지표로 정규화하고 품질을 표시한다."""

    ALIASES: Dict[str, List[str]] = {
        "revenue": ["revenue", "sales", "매출액", "total_revenue"],
        "operating_income": ["operating_income", "영업이익", "operating_profit"],
        "net_income": ["net_income", "당기순이익", "net_profit"],
        "assets": ["assets", "total_assets", "자산총계"],
        "liabilities": ["liabilities", "total_liabilities", "부채총계"],
        "equity": ["equity", "stockholders_equity", "자본총계"],
        "cash": ["cash", "cash_and_equivalents", "현금및현금성자산"],
        "debt": ["debt", "total_debt", "차입금"],
        "operating_cash_flow": ["operating_cash_flow", "영업활동현금흐름", "cfo"],
        "capital_expenditure": ["capital_expenditure", "capex", "유형자산취득"],
        "shares": ["shares", "shares_outstanding", "발행주식수"],
        "dividends": ["dividends", "cash_dividends", "현금배당"],
        "eps": ["eps", "basic_eps", "주당순이익"],
    }

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            if value in (None, "", "-", "N/A"):
                return None
            return float(str(value).replace(",", ""))
        except Exception:
            return None

    def normalize_period(self, row: Mapping[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {
            "period": str(row.get("period") or row.get("fiscal_period") or row.get("date") or ""),
            "currency": str(row.get("currency") or ""),
            "is_annual": bool(row.get("is_annual", True)),
            "source": str(row.get("source") or "unknown"),
            "as_of": str(row.get("as_of") or ""),
        }
        lowered = {str(key).lower(): value for key, value in row.items()}
        for target, aliases in self.ALIASES.items():
            value = None
            for alias in aliases:
                if alias in row:
                    value = row[alias]
                    break
                if alias.lower() in lowered:
                    value = lowered[alias.lower()]
                    break
            normalized[target] = self._number(value)
        normalized["quality_flags"] = self._quality_flags(normalized)
        return normalized

    @staticmethod
    def _quality_flags(row: Mapping[str, Any]) -> List[str]:
        flags: List[str] = []
        for required in ("revenue", "net_income", "assets", "equity"):
            if row.get(required) is None:
                flags.append(f"missing_{required}")
        if not row.get("currency"):
            flags.append("missing_currency")
        if not row.get("period"):
            flags.append("missing_period")
        return flags

    @staticmethod
    def _growth(current: Optional[float], previous: Optional[float]) -> Optional[float]:
        if current is None or previous in (None, 0):
            return None
        return ((current / previous) - 1.0) * 100.0

    @staticmethod
    def _ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
        if numerator is None or denominator in (None, 0):
            return None
        return numerator / denominator

    def analyze(self, periods: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        rows = [self.normalize_period(row) for row in periods]
        rows.sort(key=lambda row: str(row.get("period") or ""))
        if not rows:
            return {"status": "no_data", "periods": [], "metrics": {}, "risk_signals": ["재무 데이터 없음"]}
        current = rows[-1]
        previous = rows[-2] if len(rows) > 1 else {}
        revenue = current.get("revenue")
        operating_income = current.get("operating_income")
        net_income = current.get("net_income")
        equity = current.get("equity")
        debt = current.get("debt")
        cash = current.get("cash")
        cfo = current.get("operating_cash_flow")
        capex = current.get("capital_expenditure")
        free_cash_flow = None if cfo is None or capex is None else cfo - abs(capex)
        metrics = {
            "revenue_growth_percent": self._growth(revenue, previous.get("revenue")),
            "operating_income_growth_percent": self._growth(operating_income, previous.get("operating_income")),
            "net_income_growth_percent": self._growth(net_income, previous.get("net_income")),
            "operating_margin_percent": self._percent(self._ratio(operating_income, revenue)),
            "net_margin_percent": self._percent(self._ratio(net_income, revenue)),
            "roe_percent": self._percent(self._ratio(net_income, equity)),
            "debt_to_equity": self._ratio(debt, equity),
            "net_debt": None if debt is None or cash is None else debt - cash,
            "free_cash_flow": free_cash_flow,
            "fcf_margin_percent": self._percent(self._ratio(free_cash_flow, revenue)),
            "cash_conversion": self._ratio(cfo, net_income),
            "eps": current.get("eps"),
            "dividend_per_share": self._ratio(current.get("dividends"), current.get("shares")),
        }
        risks: List[str] = []
        if metrics["revenue_growth_percent"] is not None and metrics["revenue_growth_percent"] < -10:
            risks.append("매출 급감")
        if metrics["operating_margin_percent"] is not None and metrics["operating_margin_percent"] < 0:
            risks.append("영업손실")
        if metrics["debt_to_equity"] is not None and metrics["debt_to_equity"] > 2.0:
            risks.append("높은 부채비율")
        if free_cash_flow is not None and free_cash_flow < 0:
            risks.append("잉여현금흐름 음수")
        if metrics["cash_conversion"] is not None and metrics["cash_conversion"] < 0.6:
            risks.append("이익 대비 현금전환 낮음")
        quality_flags = sorted({flag for row in rows for flag in row.get("quality_flags", [])})
        return {
            "status": "ok",
            "periods": rows,
            "metrics": metrics,
            "risk_signals": risks,
            "quality_flags": quality_flags,
            "current_period": current.get("period"),
            "currency": current.get("currency"),
        }

    @staticmethod
    def _percent(value: Optional[float]) -> Optional[float]:
        return None if value is None else value * 100.0
