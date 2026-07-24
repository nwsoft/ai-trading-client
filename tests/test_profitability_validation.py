#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ProfitabilityValidator / 워크포워드 자동화 테스트."""

from __future__ import annotations

import pytest
from trading.profitability_validation import ProfitabilityReport, ProfitabilityValidator


# ──────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────

def _make_trade(pnl: float, fee: float = 0.0, slippage_bps: float = 0.0,
                quantity: float = 1.0, price: float = 10000.0) -> dict:
    return {
        "pnl": pnl,
        "fee": fee,
        "slippage_bps": slippage_bps,
        "quantity": quantity,
        "price": price,
    }


def _good_trades(n: int = 25) -> list:
    """win_rate=0.75, MDD 낮음 → 모든 KPI 통과."""
    trades = []
    for i in range(n):
        # i+1 기준으로 4의 배수만 손실 → 첫 거래는 반드시 이익
        pnl = 200.0 if (i + 1) % 4 != 0 else -30.0   # ~75% 승률, 손실 소액
        trades.append(_make_trade(pnl=pnl))
    return trades


def _bad_trades_low_winrate(n: int = 25) -> list:
    """win_rate < 0.48 → 차단."""
    trades = []
    for i in range(n):
        pnl = 100.0 if i % 3 == 0 else -200.0   # ~33% 승률
        trades.append(_make_trade(pnl=pnl))
    return trades


# ──────────────────────────────────────────────────────────────
# 1. 기본 동작
# ──────────────────────────────────────────────────────────────

class TestProfitabilityValidatorBasic:

    def test_disabled_policy_returns_bypassed(self):
        v = ProfitabilityValidator()
        result = v.evaluate_strategy([], policy={"enabled": False})
        assert result["bypassed"] is True
        assert result["enabled"] is True

    def test_insufficient_trades_bypassed(self):
        """min_trades 미달 → 차단 아닌 bypass (초기 학습 기간 보호)."""
        v = ProfitabilityValidator()
        trades = [_make_trade(100.0) for _ in range(5)]  # min_trades=20
        result = v.evaluate_strategy(trades, policy={"enabled": True})
        assert result["bypassed"] is True
        assert result["enabled"] is True
        assert result["reason"] == "insufficient_trades"

    def test_sufficient_good_trades_enabled(self):
        v = ProfitabilityValidator()
        result = v.evaluate_strategy(_good_trades(30), policy={"enabled": True})
        assert result["enabled"] is True
        assert result["reasons"] == []

    def test_returns_all_required_keys(self):
        v = ProfitabilityValidator()
        result = v.evaluate_strategy(_good_trades(30), policy={"enabled": True})
        for key in ("total_trades", "gross_pnl", "net_pnl", "win_rate",
                    "sharpe", "mdd", "expectancy", "walkforward_pass_rate",
                    "enabled", "reasons"):
            assert key in result, f"missing key: {key}"

    def test_empty_trades_bypassed_due_to_insufficient(self):
        """거래 0건 → bypass (차단 없음)."""
        v = ProfitabilityValidator()
        result = v.evaluate_strategy([], policy={"enabled": True})
        assert result["bypassed"] is True
        assert result["enabled"] is True


# ──────────────────────────────────────────────────────────────
# 2. KPI 임계값별 차단 테스트
# ──────────────────────────────────────────────────────────────

class TestProfitabilityValidatorThresholds:

    def test_low_winrate_blocked(self):
        v = ProfitabilityValidator()
        result = v.evaluate_strategy(
            _bad_trades_low_winrate(30),
            policy={"enabled": True, "min_trades": 5}
        )
        assert "win_rate_below_threshold" in result["reasons"]
        assert result["enabled"] is False

    def test_high_mdd_blocked(self):
        """낙폭이 매우 큰 거래 → mdd_above_threshold."""
        v = ProfitabilityValidator()
        # 연속 큰 손실 → MDD 높음
        trades = [_make_trade(5000.0)] + [_make_trade(-2000.0) for _ in range(20)]
        result = v.evaluate_strategy(
            trades,
            policy={"enabled": True, "min_trades": 5, "max_mdd": 0.01}
        )
        assert "mdd_above_threshold" in result["reasons"]
        assert result["enabled"] is False

    def test_low_expectancy_blocked(self):
        """기대값 < 0 → expectancy_below_threshold."""
        v = ProfitabilityValidator()
        trades = [_make_trade(-50.0) for _ in range(25)]
        result = v.evaluate_strategy(
            trades,
            policy={"enabled": True, "min_trades": 5}
        )
        assert "expectancy_below_threshold" in result["reasons"]
        assert result["enabled"] is False

    def test_low_sharpe_blocked(self):
        """변동성 대비 수익이 낮아 샤프 비율 미달."""
        v = ProfitabilityValidator()
        # 수익이 거의 0에 수렴 → 샤프 낮음
        trades = [_make_trade(1.0) for _ in range(25)]
        result = v.evaluate_strategy(
            trades,
            policy={"enabled": True, "min_trades": 5, "min_sharpe": 100.0}
        )
        assert "sharpe_below_threshold" in result["reasons"]

    def test_low_walkforward_blocked(self):
        """절반 이상 구간에서 손실 → walkforward 미달."""
        v = ProfitabilityValidator()
        # 앞 절반 손실, 뒷 절반 이익
        trades = [_make_trade(-100.0) for _ in range(16)] + [_make_trade(200.0) for _ in range(4)]
        result = v.evaluate_strategy(
            trades,
            policy={"enabled": True, "min_trades": 5,
                    "walkforward_splits": 4, "min_walkforward_pass_rate": 0.90}
        )
        assert "walkforward_below_threshold" in result["reasons"]

    def test_limited_learning_keeps_sampling_with_reduced_risk(self):
        v = ProfitabilityValidator()
        result = v.evaluate_strategy(
            _bad_trades_low_winrate(30),
            policy={
                "enabled": True,
                "min_trades": 5,
                "underperformance_mode": "limited_learning",
                "hard_stop_mdd": 100.0,
            },
        )
        assert result["enabled"] is True
        assert result["stage"] == "recovery_learning"
        assert result["risk_multiplier"] <= 0.20
        assert result["max_positions"] == 1

    def test_limited_learning_still_hard_stops_extreme_mdd(self):
        v = ProfitabilityValidator()
        trades = [_make_trade(5000.0)] + [_make_trade(-2000.0) for _ in range(20)]
        result = v.evaluate_strategy(
            trades,
            policy={
                "enabled": True,
                "min_trades": 5,
                "underperformance_mode": "limited_learning",
                "hard_stop_mdd": 0.01,
            },
        )
        assert result["enabled"] is False


# ──────────────────────────────────────────────────────────────
# 3. 수치 계산 정확성
# ──────────────────────────────────────────────────────────────

class TestProfitabilityValidatorCalculations:

    def test_win_rate_calculation(self):
        v = ProfitabilityValidator()
        # 4승 1패 → win_rate=0.8
        trades = [_make_trade(100.0)] * 4 + [_make_trade(-50.0)]
        result = v.evaluate_strategy(trades, policy={"enabled": True, "min_trades": 1})
        assert abs(result["win_rate"] - 0.8) < 1e-6

    def test_net_pnl_subtracts_fee(self):
        v = ProfitabilityValidator()
        # pnl=100, fee=10 → net=-10*5 + 90*5 = 400
        trades = [_make_trade(pnl=100.0, fee=10.0) for _ in range(5)]
        result = v.evaluate_strategy(trades, policy={"enabled": True, "min_trades": 1})
        assert abs(result["net_pnl"] - 450.0) < 1e-4  # (100-10)*5

    def test_net_pnl_subtracts_slippage(self):
        v = ProfitabilityValidator()
        # slippage_bps=100(=1%), qty=1, price=10000 → slippage=100 per trade
        trades = [_make_trade(pnl=500.0, slippage_bps=100.0,
                               quantity=1.0, price=10000.0) for _ in range(5)]
        result = v.evaluate_strategy(trades, policy={"enabled": True, "min_trades": 1})
        # net per trade = 500 - 0 - 10000*0.01 = 400
        assert abs(result["net_pnl"] - 2000.0) < 1e-4

    def test_mdd_all_positive(self):
        """수익만 있는 경우 MDD=0."""
        v = ProfitabilityValidator()
        trades = [_make_trade(100.0) for _ in range(20)]
        result = v.evaluate_strategy(trades, policy={"enabled": True, "min_trades": 5})
        assert result["mdd"] == pytest.approx(0.0, abs=1e-6)

    def test_total_trades_count(self):
        v = ProfitabilityValidator()
        trades = _good_trades(27)
        result = v.evaluate_strategy(trades, policy={"enabled": True})
        assert result["total_trades"] == 27

    def test_walkforward_all_positive_windows(self):
        """모든 구간 양의 기대값 → walkforward_pass_rate=1.0."""
        v = ProfitabilityValidator()
        trades = [_make_trade(100.0) for _ in range(20)]
        result = v.evaluate_strategy(
            trades, policy={"enabled": True, "min_trades": 5, "walkforward_splits": 4}
        )
        assert result["walkforward_pass_rate"] == pytest.approx(1.0)

    def test_walkforward_all_negative_windows(self):
        """모든 구간 음의 기대값 → walkforward_pass_rate=0.0."""
        v = ProfitabilityValidator()
        trades = [_make_trade(-50.0) for _ in range(20)]
        result = v.evaluate_strategy(
            trades, policy={"enabled": True, "min_trades": 5, "walkforward_splits": 4}
        )
        assert result["walkforward_pass_rate"] == pytest.approx(0.0)


# ──────────────────────────────────────────────────────────────
# 4. ProfitabilityReport 데이터클래스
# ──────────────────────────────────────────────────────────────

class TestProfitabilityReport:

    def test_to_dict_keys(self):
        report = ProfitabilityReport(
            total_trades=10,
            gross_pnl=1000.0,
            net_pnl=900.0,
            win_rate=0.7,
            sharpe=1.5,
            mdd=0.05,
            expectancy=90.0,
            walkforward_pass_rate=0.75,
            enabled=True,
            reasons=[],
        )
        d = report.to_dict()
        assert d["enabled"] is True
        assert d["total_trades"] == 10
        assert d["reasons"] == []

    def test_to_dict_rounding(self):
        report = ProfitabilityReport(
            total_trades=5,
            gross_pnl=1.123456789,
            net_pnl=1.0,
            win_rate=0.666666,
            sharpe=1.123456,
            mdd=0.049999,
            expectancy=10.1,
            walkforward_pass_rate=0.333333,
            enabled=False,
            reasons=["win_rate_below_threshold"],
        )
        d = report.to_dict()
        # 소수점 4자리로 반올림
        assert len(str(d["win_rate"]).split(".")[-1]) <= 5
        assert "win_rate_below_threshold" in d["reasons"]


# ──────────────────────────────────────────────────────────────
# 5. 정책 오버라이드 및 경계값
# ──────────────────────────────────────────────────────────────

class TestProfitabilityValidatorEdgeCases:

    def test_custom_min_trades_policy(self):
        """min_trades=3 커스텀 → 3건으로 통과 가능."""
        v = ProfitabilityValidator()
        trades = [_make_trade(100.0) for _ in range(3)]
        result = v.evaluate_strategy(
            trades,
            policy={"enabled": True, "min_trades": 3, "min_sharpe": 0.0,
                    "min_win_rate": 0.0, "min_expectancy": 0.0}
        )
        assert "insufficient_trades" not in result["reasons"]

    def test_none_policy_uses_defaults(self):
        """policy=None → DEFAULT_POLICY 사용."""
        v = ProfitabilityValidator()
        result = v.evaluate_strategy(_good_trades(30), policy=None)
        assert "enabled" in result

    def test_single_trade(self):
        """거래 1건 → bypass (차단 없음)."""
        v = ProfitabilityValidator()
        result = v.evaluate_strategy([_make_trade(100.0)], policy={"enabled": True})
        assert result["bypassed"] is True
        assert result["enabled"] is True

    def test_none_trades_in_list(self):
        """거래 목록에 None 포함 시 크래시 없이 처리."""
        v = ProfitabilityValidator()
        trades = [_make_trade(100.0), None, _make_trade(-50.0)]
        try:
            result = v.evaluate_strategy(trades, policy={"enabled": True, "min_trades": 1})
            assert "total_trades" in result
        except Exception as e:
            pytest.fail(f"None trade crashed: {e}")

    def test_zero_price_does_not_crash(self):
        """price=0 → ZeroDivision 방지."""
        v = ProfitabilityValidator()
        trades = [_make_trade(pnl=100.0, price=0.0) for _ in range(5)]
        result = v.evaluate_strategy(trades, policy={"enabled": True, "min_trades": 1})
        assert "net_pnl" in result

    def test_walkforward_single_split(self):
        """splits=1 → 전체가 하나의 윈도우."""
        v = ProfitabilityValidator()
        trades = [_make_trade(50.0) for _ in range(10)]
        result = v.evaluate_strategy(
            trades,
            policy={"enabled": True, "min_trades": 5, "walkforward_splits": 1}
        )
        assert result["walkforward_pass_rate"] == pytest.approx(1.0)
