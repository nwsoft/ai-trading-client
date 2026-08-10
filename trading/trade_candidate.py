#!/usr/bin/env python3
"""기본 AI와 AI 커스텀의 진입 후보를 하나의 런타임 계약으로 통합한다."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Sequence

from .declarative_strategy_engine import DeclarativeStrategyEngine
from .selection_policy import resolve_effective_market_regime


TRADE_SIGNALS = {"LONG", "SHORT"}


def normalize_trade_signal(value: Any) -> str:
    normalized = str(value or "HOLD").strip().upper()
    if normalized == "BUY":
        return "LONG"
    if normalized == "SELL":
        return "SHORT"
    return normalized if normalized in TRADE_SIGNALS else "HOLD"


@dataclass(frozen=True)
class ExitPlan:
    """전략 청산값과 동적/보험 주문 책임을 후보 단계에서 고정한다."""

    source: str = "noah_dynamic"
    strategy_owned: bool = False
    requested_tp_fraction: float = 0.0
    requested_sl_fraction: float = 0.0
    allow_noah_dynamic_adjustment: bool = True
    insurance_order_policy: str = "dynamic_backup"
    executable_exit: Dict[str, Any] = field(default_factory=dict)
    advanced_order_plan: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TradeCandidate:
    """후보 출처와 선택 전략을 거래 엔진 사이에서 동일하게 전달한다."""

    symbol: str
    asset_class: str
    target: str
    market_regime: str
    base_signal: str
    final_signal: str
    signal_source: str
    allowed: bool
    reason: str
    custom_evaluated: bool
    overall_market_regime: str = ""
    symbol_market_regime: str = ""
    regime_scope: str = "market"
    strategy_role: str = "none"
    operation_mode: str = "standard"
    strategy_id: str = ""
    strategy_key: str = ""
    strategy_version_id: str = ""
    strategy_name: str = ""
    engine_settings: Dict[str, Any] = field(default_factory=dict)
    selected_rules: Dict[str, Any] = field(default_factory=dict)
    exit_plan: ExitPlan = field(default_factory=ExitPlan)
    runtime_indicator_values: List[Dict[str, Any]] = field(default_factory=list)
    evaluation: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_independent(self) -> bool:
        return self.strategy_role == "independent" and bool(self.strategy_name)

    @property
    def requires_noah_strategy_policy(self) -> bool:
        """기본 전략 합의·성과 정책은 기본/confirm 후보에만 적용한다."""
        return not self.is_independent

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["is_independent"] = self.is_independent
        result["requires_noah_strategy_policy"] = self.requires_noah_strategy_policy
        return result


def _build_exit_plan(
    *,
    selected_name: str,
    engine_settings: Mapping[str, Any] | None,
    selected_rules: Mapping[str, Any] | None,
) -> ExitPlan:
    settings = dict(engine_settings or {})
    rules = dict(selected_rules or {})
    if not selected_name:
        return ExitPlan()
    try:
        tp_fraction = float(settings.get("tp_percent", 0.0) or 0.0)
    except (TypeError, ValueError):
        tp_fraction = 0.0
    try:
        sl_fraction = float(settings.get("sl_percent", 0.0) or 0.0)
    except (TypeError, ValueError):
        sl_fraction = 0.0
    return ExitPlan(
        source="custom_strategy",
        strategy_owned=True,
        requested_tp_fraction=tp_fraction,
        requested_sl_fraction=sl_fraction,
        allow_noah_dynamic_adjustment=False,
        insurance_order_policy="strategy_exact",
        executable_exit=dict(rules.get("executable_exit") or {}),
        advanced_order_plan=dict(rules.get("advanced_order_plan") or {}),
    )


def evaluate_trade_candidate(
    *,
    symbol: str,
    context: Mapping[str, Any] | None,
    strategy_pool: Sequence[Mapping[str, Any]] | None,
    asset_class: str,
    target: str,
    market_regime: str,
) -> TradeCandidate:
    """활성 전략 풀을 후보당 정확히 한 번 평가해 표준 후보를 만든다."""

    runtime_context = dict(context or {})
    base_signal = normalize_trade_signal(runtime_context.get("signal"))
    runtime_context["signal"] = base_signal
    # 전략별 regime_scope는 선언형 엔진이 평가한다. 후보의 기본 표시값은
    # 전체 시장국면이며, 종목 국면이 존재해도 암묵적으로 우선하지 않는다.
    effective_regime, regime_source = resolve_effective_market_regime(
        runtime_context,
        market_regime,
        "market",
    )
    runtime_context["_market_regime"] = effective_regime
    runtime_context["market_regime"] = effective_regime
    runtime_context["_market_regime_source"] = regime_source
    pool = [dict(item) for item in (strategy_pool or []) if isinstance(item, Mapping)]

    if not pool:
        return TradeCandidate(
            symbol=str(symbol or ""),
            asset_class=str(asset_class or ""),
            target=str(target or ""),
            market_regime=effective_regime,
            base_signal=base_signal,
            final_signal=base_signal,
            signal_source="noah_base",
            allowed=True,
            reason="no_active_custom_strategy",
            custom_evaluated=False,
            overall_market_regime=effective_regime,
            symbol_market_regime=str(
                runtime_context.get("_symbol_market_regime")
                or runtime_context.get("symbol_market_regime")
                or ""
            ),
            regime_scope="market",
        )

    custom_result = DeclarativeStrategyEngine.evaluate_strategy_pool(
        pool,
        runtime_context,
        asset_class=asset_class,
        target=target,
        market_regime=effective_regime,
    )
    selected_name = str(custom_result.get("selected_strategy_name") or "")
    role = str(custom_result.get("signal_mode") or "none").strip().lower()
    allowed = bool(custom_result.get("allowed", False))
    engine_settings = dict(custom_result.get("engine_settings") or {})
    selected_rules = dict(custom_result.get("selected_rules") or {})
    if not allowed:
        final_signal = "HOLD"
        signal_source = "custom_blocked"
    elif selected_name and role == "independent":
        final_signal = normalize_trade_signal(custom_result.get("entry_signal"))
        signal_source = "custom_independent"
    elif selected_name:
        final_signal = base_signal
        signal_source = "custom_confirm"
    else:
        final_signal = base_signal
        signal_source = "noah_base"

    selected_regime_source = str(
        custom_result.get("market_regime_source") or regime_source
    )
    return TradeCandidate(
        symbol=str(symbol or ""),
        asset_class=str(asset_class or ""),
        target=str(target or ""),
        market_regime=str(custom_result.get("market_regime") or effective_regime),
        base_signal=base_signal,
        final_signal=final_signal,
        signal_source=signal_source,
        allowed=allowed,
        reason=str(custom_result.get("reason") or ""),
        custom_evaluated=True,
        overall_market_regime=str(
            custom_result.get("overall_market_regime") or effective_regime
        ),
        symbol_market_regime=str(
            custom_result.get("symbol_market_regime") or ""
        ),
        regime_scope=str(custom_result.get("regime_scope") or "market"),
        strategy_role=role,
        operation_mode=str(custom_result.get("operation_mode") or "standard"),
        strategy_id=str(custom_result.get("selected_strategy_id") or ""),
        strategy_key=str(custom_result.get("selected_strategy_key") or ""),
        strategy_version_id=str(custom_result.get("selected_version_id") or ""),
        strategy_name=selected_name,
        engine_settings=engine_settings,
        selected_rules=selected_rules,
        exit_plan=_build_exit_plan(
            selected_name=selected_name,
            engine_settings=engine_settings,
            selected_rules=selected_rules,
        ),
        runtime_indicator_values=list(custom_result.get("runtime_indicator_values") or []),
        evaluation={
            **dict(custom_result),
            "market_regime_source": selected_regime_source,
        },
    )


def apply_trade_candidate(
    context: Mapping[str, Any] | None,
    candidate: TradeCandidate,
) -> Dict[str, Any]:
    """기존 분석 dict에 표준 후보 메타데이터를 손실 없이 반영한다."""

    result = dict(context or {})
    result["signal"] = candidate.final_signal
    result["_trade_candidate"] = candidate.to_dict()
    result["_signal_source"] = candidate.signal_source
    result["_custom_signal_mode"] = candidate.strategy_role
    result["_custom_operation_mode"] = candidate.operation_mode
    result["_exit_plan"] = asdict(candidate.exit_plan)
    if candidate.strategy_name:
        result["_selected_custom_strategy"] = candidate.strategy_name
        result["_selected_custom_strategy_id"] = candidate.strategy_id
        result["_selected_custom_strategy_key"] = candidate.strategy_key
        result["_selected_custom_strategy_version_id"] = candidate.strategy_version_id
        result["_custom_engine_settings"] = dict(candidate.engine_settings)
        result["_custom_strategy_rules"] = dict(candidate.selected_rules)
        result["_custom_runtime_indicator_values"] = list(candidate.runtime_indicator_values)
    return result
