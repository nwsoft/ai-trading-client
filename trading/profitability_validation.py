#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""수익성 검증 계층.

목표:
- 전략의 "작동"이 아니라 "수익성"을 수치 KPI로 판정
- 백테스트/워크포워드/거래비용/슬리피지 반영 결과를 단일 리포트로 제공
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ProfitabilityReport:
    total_trades: int
    gross_pnl: float
    net_pnl: float
    win_rate: float
    sharpe: float
    mdd: float
    expectancy: float
    walkforward_pass_rate: float
    enabled: bool
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "gross_pnl": round(self.gross_pnl, 4),
            "net_pnl": round(self.net_pnl, 4),
            "win_rate": round(self.win_rate, 4),
            "sharpe": round(self.sharpe, 4),
            "mdd": round(self.mdd, 4),
            "expectancy": round(self.expectancy, 4),
            "walkforward_pass_rate": round(self.walkforward_pass_rate, 4),
            "enabled": self.enabled,
            "reasons": list(self.reasons),
        }


class ProfitabilityValidator:
    """자동매매 ON/OFF를 수익성 KPI로 판정한다."""

    DEFAULT_POLICY: Dict[str, Any] = {
        # enabled=True: 거래 데이터가 쌓인 뒤 KPI가 크게 흔들릴 때만 차단
        # 거래 데이터가 min_trades 미만이면 bypassed=True로 통과(초기 학습 기간 보호)
        "enabled": True,
        "min_trades": 10,
        "min_win_rate": 0.42,
        "min_sharpe": 0.20,
        "max_mdd": 0.30,
        "min_expectancy": 0.0,
        "walkforward_splits": 4,
        "min_walkforward_pass_rate": 0.40,
        # 신규 사용자는 영구 HOLD가 아니라 거래소 최소 주문 단위의 제한 운용으로 학습한다.
        "cold_start_enabled": True,
        "cold_start_max_positions": 1,
        "cold_start_max_leverage": 1,
        "cold_start_initial_risk_multiplier": 0.10,
        # strict_stop은 기존 동작. limited_learning은 손실 구간에도 최소 위험으로
        # 계속 표본을 쌓되 hard_stop_mdd를 넘으면 즉시 차단한다.
        "underperformance_mode": "strict_stop",
        "recovery_risk_multiplier": 0.15,
        "recovery_max_positions": 1,
        "recovery_max_leverage": 1,
        "recovery_review_interval_trades": 20,
        "hard_stop_mdd": 0.45,
    }

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    def _extract_trade_return(self, trade: Dict[str, Any]) -> Optional[float]:
        """Return one closed trade as a unitless net return fraction.

        Recovery decisions must not compare KRW and USDT cash PnL as if they
        were returns.  Prefer the recorder's already-normalized percentage and
        only derive a return from cash PnL when entry notional is available.
        A cash-only row without an entry capital base is excluded; a KRW or
        USDT amount cannot safely be interpreted as a percentage return.
        """
        for key in ("net_pnl_fraction", "pnl_fraction", "return_fraction"):
            if trade.get(key) is not None:
                return self._to_float(trade.get(key), 0.0)
        for key in ("net_pnl_percent", "pnl_percent", "return_percent"):
            if trade.get(key) is not None:
                return self._to_float(trade.get(key), 0.0) / 100.0

        pnl = self._to_float(
            trade.get("net_pnl", trade.get("pnl", trade.get("realized_pnl", trade.get("profit", 0.0)))),
            0.0,
        )
        # NoahAI trade_log의 pnl은 log_trade_exit 단계에서 이미 수수료와
        # 슬리피지를 뺀 순손익이다. 이 표본에 비용을 다시 빼면 성과회복
        # 판단이 거래소별로 과도하게 나빠진다. 외부/raw 표본은 기존처럼
        # 비용을 계산한다.
        fee = self._to_float(trade.get("fee", trade.get("fees", 0.0)), 0.0)
        slippage_bps = self._to_float(trade.get("slippage_bps", 0.0), 0.0)
        qty = self._to_float(trade.get("quantity", trade.get("filled_quantity", 0.0)), 0.0)
        price = self._to_float(
            trade.get(
                "entry_price",
                trade.get("filled_price", trade.get("price", trade.get("exit_price", 0.0))),
            ),
            0.0,
        )

        explicit_notional = self._to_float(
            trade.get("entry_notional", trade.get("notional", 0.0)), 0.0
        )
        notional = explicit_notional if explicit_notional > 0 else qty * price
        if notional <= 0:
            return None
        slippage_cost = notional * (abs(slippage_bps) / 10000.0)
        net = (
            pnl
            if bool(trade.get("pnl_is_net", False)) or trade.get("net_pnl") is not None
            else pnl - fee - slippage_cost
        )
        return net / notional

    def _extract_net_pnl_ccy(self, trade: Dict[str, Any]) -> float:
        """Return cash PnL once, preserving the row's quote currency."""
        pnl = self._to_float(
            trade.get("net_pnl", trade.get("pnl", trade.get("realized_pnl", trade.get("profit", 0.0)))),
            0.0,
        )
        if bool(trade.get("pnl_is_net", False)) or trade.get("net_pnl") is not None:
            return pnl
        fee = self._to_float(trade.get("fee", trade.get("fees", 0.0)), 0.0)
        slippage_bps = self._to_float(trade.get("slippage_bps", 0.0), 0.0)
        qty = max(self._to_float(trade.get("quantity", trade.get("filled_quantity", 1.0)), 1.0), 1e-8)
        price = max(
            self._to_float(trade.get("filled_price", trade.get("entry_price", trade.get("price", 1.0))), 1.0),
            1e-8,
        )
        notional = self._to_float(trade.get("entry_notional", trade.get("notional", 0.0)), 0.0)
        if notional <= 0:
            notional = qty * price
        return pnl - fee - (notional * abs(slippage_bps) / 10000.0)

    @staticmethod
    def _return_basis(trades: List[Dict[str, Any]]) -> str:
        if all(
            any((trade or {}).get(key) is not None for key in (
                "net_pnl_fraction", "pnl_fraction", "return_fraction",
                "net_pnl_percent", "pnl_percent", "return_percent",
            ))
            for trade in trades
        ):
            return "normalized_return"
        if all(
            self_notional > 0
            for self_notional in (
                ProfitabilityValidator._to_float(
                    (trade or {}).get("entry_notional", (trade or {}).get("notional", 0.0)), 0.0
                ) or (
                    ProfitabilityValidator._to_float((trade or {}).get("quantity", 0.0), 0.0)
                    * ProfitabilityValidator._to_float(
                        (trade or {}).get(
                            "entry_price",
                            (trade or {}).get("price", (trade or {}).get("exit_price", 0.0)),
                        ),
                        0.0,
                    )
                )
                for trade in trades
            )
        ):
            return "cash_pnl_divided_by_entry_notional"
        return "legacy_cash_fallback"

    @staticmethod
    def _max_drawdown_from_equity(equity_curve: List[float]) -> float:
        if not equity_curve:
            return 0.0
        peak = equity_curve[0]
        max_dd = 0.0
        for v in equity_curve:
            peak = max(peak, v)
            if peak <= 0:
                continue
            dd = (peak - v) / peak
            max_dd = max(max_dd, dd)
        return max_dd

    @staticmethod
    def _safe_sharpe(returns: List[float]) -> float:
        if len(returns) < 2:
            return 0.0
        mean_r = statistics.mean(returns)
        std_r = statistics.pstdev(returns)
        if std_r <= 1e-12:
            return 0.0
        return mean_r / std_r * math.sqrt(len(returns))

    def _walkforward_pass_rate(self, returns: List[float], splits: int) -> float:
        if not returns:
            return 0.0
        safe_splits = max(1, int(splits or 1))
        chunk = max(1, len(returns) // safe_splits)
        passed = 0
        windows = 0
        for i in range(0, len(returns), chunk):
            window = returns[i:i + chunk]
            if not window:
                continue
            windows += 1
            if statistics.mean(window) > 0:
                passed += 1
        if windows == 0:
            return 0.0
        return passed / windows

    def evaluate_strategy(self, recent_trades: List[Dict[str, Any]], policy: Dict[str, Any] | None = None) -> Dict[str, Any]:
        effective = dict(self.DEFAULT_POLICY)
        effective.update(policy or {})

        if not bool(effective.get("enabled", False)):
            return {
                "enabled": True,
                "bypassed": True,
                "reason": "profitability_validation_disabled",
            }

        trade_rows = [dict(t or {}) for t in (recent_trades or [])]
        unresolved = sum(t.get('performance_evidence_ready') is False for t in trade_rows)
        if unresolved:
            # Missing losses must not turn a confirmed positive subset into a
            # successful strategy, nor be reclassified as a cold start.
            return {
                'enabled': False, 'bypassed': False,
                'reason': 'pnl_reconciliation_required',
                'reasons': ['pnl_reconciliation_required'],
                'unresolved_trades': unresolved,
                'total_trades': len(trade_rows),
            }
        extracted_returns = [self._extract_trade_return(t) for t in trade_rows]
        returns = [value for value in extracted_returns if value is not None]
        total_trades = len(returns)
        excluded_return_rows = len(trade_rows) - total_trades
        gross_pnl = sum(self._to_float(t.get("pnl", t.get("realized_pnl", t.get("profit", 0.0))), 0.0) for t in trade_rows)
        net_pnl = sum(self._extract_net_pnl_ccy(t) for t in trade_rows)
        return_basis = self._return_basis(trade_rows)

        wins = sum(1 for r in returns if r > 0)
        win_rate = (wins / total_trades) if total_trades > 0 else 0.0
        expectancy = statistics.mean(returns) if returns else 0.0

        # Unitless compounded equity curve.  A KRW row and a USDT row now have
        # the same meaning when their net percentage return is the same.
        equity = [1.0]
        running = 1.0
        for r in returns:
            running *= max(1e-9, 1.0 + r)
            equity.append(running)

        sharpe = self._safe_sharpe(returns)
        mdd = self._max_drawdown_from_equity(equity)
        walkforward = self._walkforward_pass_rate(returns, int(effective.get("walkforward_splits", 4) or 4))

        reasons: List[str] = []
        if total_trades < int(effective.get("min_trades", 20) or 20):
            # 거래 데이터가 부족해도 영구 차단하지 않는다. 시장 데이터/가드레일이 통과하면
            # 거래소 최소 주문 단위의 제한 운용으로 체결·비용·PnL을 학습한다.
            min_trades = max(1, int(effective.get("min_trades", 20) or 20))
            progress = total_trades / min_trades
            initial = max(0.01, min(float(effective.get("cold_start_initial_risk_multiplier", 0.10) or 0.10), 1.0))
            risk_multiplier = min(0.50, initial + (0.40 * progress))
            return {
                "enabled": True,
                "bypassed": True,
                "reason": "insufficient_trades",
                "total_trades": total_trades,
                "gross_pnl": round(gross_pnl, 4),
                "net_pnl": round(net_pnl, 4),
                "win_rate": round(win_rate, 4),
                "sharpe": round(sharpe, 4),
                "mdd": round(mdd, 4),
                "expectancy": round(expectancy, 6),
                "walkforward_pass_rate": round(walkforward, 4),
                "stage": "limited_live_learning" if bool(effective.get("cold_start_enabled", True)) else "legacy_bypass",
                "learning_progress": round(progress, 4),
                "risk_multiplier": round(risk_multiplier, 4),
                "max_positions": max(1, int(effective.get("cold_start_max_positions", 1) or 1)),
                "max_leverage": max(1, int(effective.get("cold_start_max_leverage", 1) or 1)),
                "next_review_at_trades": min_trades,
                "recheck_policy": "each_closed_trade",
                "note": "시장데이터와 공통 가드레일 통과 시 최소 단위 제한 운용 후 거래소별 PnL로 재평가",
                "return_basis": return_basis,
                "expectancy_percent": round(expectancy * 100.0, 6),
                "window_stability_rate": round(walkforward, 4),
                "walkforward_method": "closed_trade_window_stability_not_retrained_oos",
                "raw_trade_rows": len(trade_rows),
                "excluded_return_rows": excluded_return_rows,
            }
        if win_rate < self._to_float(effective.get("min_win_rate", 0.48), 0.48):
            reasons.append("win_rate_below_threshold")
        if sharpe < self._to_float(effective.get("min_sharpe", 0.60), 0.60):
            reasons.append("sharpe_below_threshold")
        if mdd > self._to_float(effective.get("max_mdd", 0.25), 0.25):
            reasons.append("mdd_above_threshold")
        if expectancy < self._to_float(effective.get("min_expectancy", 0.0), 0.0):
            reasons.append("expectancy_below_threshold")
        if walkforward < self._to_float(effective.get("min_walkforward_pass_rate", 0.50), 0.50):
            reasons.append("walkforward_below_threshold")

        underperformance_mode = str(
            effective.get("underperformance_mode", "strict_stop") or "strict_stop"
        ).strip().lower()
        hard_stop_mdd = self._to_float(effective.get("hard_stop_mdd", 0.45), 0.45)
        if reasons and underperformance_mode == "limited_learning" and mdd <= hard_stop_mdd:
            review_interval = max(
                1, int(effective.get("recovery_review_interval_trades", 20) or 20)
            )
            recent_window = returns[-min(len(returns), review_interval):]
            recent_expectancy = statistics.mean(recent_window) if recent_window else expectancy
            base_risk = max(
                0.01,
                min(
                    self._to_float(effective.get("recovery_risk_multiplier", 0.15), 0.15),
                    0.50,
                ),
            )
            # 최근 기대값이 전체 기대값보다 회복 중이면 위험을 조금만 늘린다.
            recovery_bonus = 0.05 if recent_expectancy > expectancy else 0.0
            return {
                "total_trades": total_trades,
                "gross_pnl": round(gross_pnl, 4),
                "net_pnl": round(net_pnl, 4),
                "win_rate": round(win_rate, 4),
                "sharpe": round(sharpe, 4),
                "mdd": round(mdd, 4),
                "expectancy": round(expectancy, 4),
                "walkforward_pass_rate": round(walkforward, 4),
                "enabled": True,
                "bypassed": False,
                "stage": "recovery_learning",
                "reasons": reasons,
                "risk_multiplier": round(min(0.50, base_risk + recovery_bonus), 4),
                "max_positions": max(1, int(effective.get("recovery_max_positions", 1) or 1)),
                "max_leverage": max(1, int(effective.get("recovery_max_leverage", 1) or 1)),
                "next_review_at_trades": total_trades + review_interval,
                "recheck_policy": "each_closed_trade",
                "recent_expectancy": round(recent_expectancy, 4),
                "note": "수수료 차감 후 성과 회복 표본을 최소 위험으로 계속 수집",
                "return_basis": return_basis,
                "expectancy_percent": round(expectancy * 100.0, 6),
                "window_stability_rate": round(walkforward, 4),
                "walkforward_method": "closed_trade_window_stability_not_retrained_oos",
                "raw_trade_rows": len(trade_rows),
                "excluded_return_rows": excluded_return_rows,
            }

        report = ProfitabilityReport(
            total_trades=total_trades,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            win_rate=win_rate,
            sharpe=sharpe,
            mdd=mdd,
            expectancy=expectancy,
            walkforward_pass_rate=walkforward,
            enabled=(len(reasons) == 0),
            reasons=reasons,
        )
        result = report.to_dict()
        if not reasons:
            # Crossing a KPI threshold is not permission to jump from recovery
            # sizing directly to 100%.  The distance from all KPI boundaries
            # becomes one continuous, auditable recovery factor.
            min_win = self._to_float(effective.get("min_win_rate", 0.42), 0.42)
            min_sharpe = self._to_float(effective.get("min_sharpe", 0.20), 0.20)
            max_mdd = max(1e-9, self._to_float(effective.get("max_mdd", 0.30), 0.30))
            min_walk = self._to_float(effective.get("min_walkforward_pass_rate", 0.40), 0.40)
            quality_parts = [
                max(0.0, min(1.0, (win_rate - min_win) / max(1e-9, 0.70 - min_win))),
                max(0.0, min(1.0, (sharpe - min_sharpe) / max(1.0, abs(min_sharpe)))),
                max(0.0, min(1.0, (max_mdd - mdd) / max_mdd)),
                max(0.0, min(1.0, (walkforward - min_walk) / max(1e-9, 1.0 - min_walk))),
            ]
            quality = sum(quality_parts) / len(quality_parts)
            adaptive_multiplier = min(1.0, 0.50 + (0.50 * quality))
            if adaptive_multiplier < 0.60:
                adaptive_positions, adaptive_leverage = 1, 1
            elif adaptive_multiplier < 0.80:
                adaptive_positions, adaptive_leverage = 3, 3
            elif adaptive_multiplier < 0.90:
                adaptive_positions, adaptive_leverage = 5, 5
            else:
                adaptive_positions, adaptive_leverage = 10, 10
            result.update({
                "stage": "validated_adaptive",
                "risk_multiplier": round(adaptive_multiplier, 4),
                "performance_quality": round(quality, 4),
                "max_positions": adaptive_positions,
                "max_leverage": adaptive_leverage,
                "recheck_policy": "each_closed_trade",
                "note": "KPI 통과 폭에 따라 위험을 점진 복구하며 계좌 마스터 한도를 넘지 않음",
            })
        result.update({
            "return_basis": return_basis,
            "expectancy_percent": round(expectancy * 100.0, 6),
            "window_stability_rate": round(walkforward, 4),
            "walkforward_method": "closed_trade_window_stability_not_retrained_oos",
            "raw_trade_rows": len(trade_rows),
            "excluded_return_rows": excluded_return_rows,
        })
        return result
