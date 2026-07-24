from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional


class ValuationEngine:
    @staticmethod
    def _safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
        if numerator is None or denominator in (None, 0):
            return None
        return float(numerator) / float(denominator)

    def relative_valuation(
        self,
        price: float,
        shares: float,
        revenue: Optional[float] = None,
        earnings: Optional[float] = None,
        book_value: Optional[float] = None,
        ebitda: Optional[float] = None,
        debt: float = 0.0,
        cash: float = 0.0,
        peer_multiples: Mapping[str, Iterable[float]] | None = None,
    ) -> Dict[str, Any]:
        market_cap = float(price) * float(shares)
        enterprise_value = market_cap + float(debt or 0.0) - float(cash or 0.0)
        multiples = {
            "PER": self._safe_div(market_cap, earnings),
            "PBR": self._safe_div(market_cap, book_value),
            "PSR": self._safe_div(market_cap, revenue),
            "EV_EBITDA": self._safe_div(enterprise_value, ebitda),
        }
        comparisons: Dict[str, Any] = {}
        for key, values in (peer_multiples or {}).items():
            valid = sorted(float(value) for value in values if value is not None and float(value) > 0)
            median = valid[len(valid) // 2] if valid else None
            current = multiples.get(key)
            comparisons[key] = {
                "current": current,
                "peer_median": median,
                "premium_discount_percent": (
                    ((float(current) / median) - 1.0) * 100.0
                    if current is not None and median not in (None, 0) else None
                ),
            }
        return {
            "market_cap": market_cap,
            "enterprise_value": enterprise_value,
            "multiples": multiples,
            "peer_comparison": comparisons,
            "assumptions": {
                "price": price,
                "shares": shares,
                "debt": debt,
                "cash": cash,
            },
        }

    def dcf(
        self,
        base_fcf: float,
        shares: float,
        net_debt: float = 0.0,
        growth_rates: Iterable[float] = (0.05, 0.04, 0.03, 0.03, 0.03),
        wacc: float = 0.09,
        terminal_growth: float = 0.02,
    ) -> Dict[str, Any]:
        rates = [float(rate) for rate in growth_rates]
        if shares <= 0:
            raise ValueError("shares must be positive")
        if wacc <= terminal_growth:
            raise ValueError("wacc must be greater than terminal_growth")
        projected = []
        fcf = float(base_fcf)
        pv_sum = 0.0
        for year, growth in enumerate(rates, start=1):
            fcf *= 1.0 + growth
            present_value = fcf / ((1.0 + wacc) ** year)
            projected.append({"year": year, "growth": growth, "fcf": fcf, "present_value": present_value})
            pv_sum += present_value
        terminal_value = fcf * (1.0 + terminal_growth) / (wacc - terminal_growth)
        terminal_pv = terminal_value / ((1.0 + wacc) ** len(rates))
        equity_value = pv_sum + terminal_pv - float(net_debt)
        return {
            "enterprise_value": pv_sum + terminal_pv,
            "equity_value": equity_value,
            "value_per_share": equity_value / float(shares),
            "projected": projected,
            "terminal_value": terminal_value,
            "terminal_present_value": terminal_pv,
            "assumptions": {
                "base_fcf": base_fcf,
                "growth_rates": rates,
                "wacc": wacc,
                "terminal_growth": terminal_growth,
                "shares": shares,
                "net_debt": net_debt,
            },
        }

    def scenario_dcf(
        self,
        base_fcf: float,
        shares: float,
        net_debt: float = 0.0,
        scenarios: Optional[Mapping[str, Mapping[str, Any]]] = None,
    ) -> Dict[str, Any]:
        default = {
            "bear": {"growth_rates": [0.0, 0.01, 0.01, 0.015, 0.015], "wacc": 0.11, "terminal_growth": 0.01},
            "base": {"growth_rates": [0.05, 0.04, 0.03, 0.03, 0.03], "wacc": 0.09, "terminal_growth": 0.02},
            "bull": {"growth_rates": [0.10, 0.08, 0.06, 0.05, 0.04], "wacc": 0.08, "terminal_growth": 0.025},
        }
        output: Dict[str, Any] = {}
        for name, assumptions in (scenarios or default).items():
            output[name] = self.dcf(
                base_fcf=base_fcf,
                shares=shares,
                net_debt=net_debt,
                growth_rates=assumptions.get("growth_rates", default["base"]["growth_rates"]),
                wacc=float(assumptions.get("wacc", 0.09)),
                terminal_growth=float(assumptions.get("terminal_growth", 0.02)),
            )
        return output

    def reverse_dcf_growth(
        self,
        market_price: float,
        base_fcf: float,
        shares: float,
        net_debt: float = 0.0,
        wacc: float = 0.09,
        terminal_growth: float = 0.02,
        years: int = 5,
    ) -> Dict[str, Any]:
        low, high = -0.50, 1.00
        target = float(market_price)
        for _ in range(80):
            mid = (low + high) / 2.0
            value = self.dcf(
                base_fcf,
                shares,
                net_debt,
                [mid] * max(1, int(years)),
                wacc,
                terminal_growth,
            )["value_per_share"]
            if value < target:
                low = mid
            else:
                high = mid
        implied = (low + high) / 2.0
        return {
            "implied_fcf_growth": implied,
            "market_price": market_price,
            "assumptions": {
                "wacc": wacc,
                "terminal_growth": terminal_growth,
                "years": years,
            },
        }

    def ddm(
        self,
        dividend_per_share: float,
        required_return: float,
        growth: float,
    ) -> Dict[str, Any]:
        if required_return <= growth:
            raise ValueError("required_return must be greater than growth")
        next_dividend = float(dividend_per_share) * (1.0 + growth)
        return {
            "value_per_share": next_dividend / (required_return - growth),
            "assumptions": {
                "dividend_per_share": dividend_per_share,
                "required_return": required_return,
                "growth": growth,
            },
        }

    def rim(
        self,
        book_value_per_share: float,
        roe: float,
        required_return: float,
        persistence: float = 0.8,
    ) -> Dict[str, Any]:
        if required_return <= 0 or not 0 <= persistence < 1:
            raise ValueError("invalid required_return or persistence")
        residual_income = float(book_value_per_share) * (float(roe) - required_return)
        value = float(book_value_per_share) + residual_income / (1.0 + required_return - persistence)
        return {
            "value_per_share": value,
            "residual_income": residual_income,
            "assumptions": {
                "book_value_per_share": book_value_per_share,
                "roe": roe,
                "required_return": required_return,
                "persistence": persistence,
            },
        }
