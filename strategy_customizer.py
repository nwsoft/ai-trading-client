#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
사용자 맞춤형 전략 커스터마이저
다양한 전략 조합과 실시간 적용 시스템
"""

import json
import logging
from datetime import datetime, time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from uuid import uuid4

from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.custom_strategy_runtime import (
    derive_strategy_risk_settings,
    limited_live_engine_settings,
    normalize_engine_settings,
)

class StrategyType(Enum):
    """전략 타입"""
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    SCALPING = "scalping"
    SWING = "swing"
    CUSTOM = "custom"

class MarketCondition(Enum):
    """시장 조건"""
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    VOLATILE = "volatile"
    CALM = "calm"

@dataclass
class TimeBasedStrategy:
    """시간 기반 전략"""
    active_hours: List[tuple]  # [(start_hour, end_hour), ...]
    timezone: str
    weekend_trading: bool
    holiday_trading: bool
    time_specific_params: Dict[str, Dict]

@dataclass
class CoinFilterStrategy:
    """코인 필터 전략"""
    categories: List[str]  # ["defi", "metaverse", "ai", etc.]
    market_cap_min: float
    volume_min: float
    price_range: tuple  # (min_price, max_price)
    excluded_coins: List[str]
    preferred_coins: List[str]

@dataclass
class RiskAdaptiveStrategy:
    """리스크 적응형 전략"""
    base_risk_level: float  # 0.0 ~ 1.0
    emotion_factor: float   # 사용자 감정 상태 반영
    performance_adjustment: bool  # 성과에 따른 자동 조절
    max_consecutive_losses: int
    cooldown_after_loss: int  # 손실 후 대기시간(분)

class StrategyCustomizer:
    """전략 커스터마이저"""
    
    def __init__(
        self,
        analyzer,
        trader,
        evaluator,
        risk_manager,
        *,
        storage_path: Optional[str] = None,
        min_paper_trades: int = 3,
    ):
        self.analyzer = analyzer
        self.trader = trader
        self.evaluator = evaluator
        self.risk_manager = risk_manager
        self.logger = logging.getLogger(__name__)
        
        # 사용자 전략 저장소
        self.user_strategies: Dict[str, Dict] = {}
        self.active_strategy_id: Optional[str] = None
        
        # 전략 실행 이력
        self.strategy_performance: Dict[str, Dict] = {}

        # 사용자 전략은 최대 10개 버전으로 보관하며, 승인과 모의거래를
        # 통과하기 전에는 실거래 설정에 반영하지 않는다.
        self.custom_pipeline = CustomStrategyPipeline(
            storage_path=storage_path,
            max_versions=10,
            min_paper_trades=min_paper_trades,
            logger=self.logger,
        )
        self._hydrate_persisted_strategies()
        self._refresh_runtime_strategy_pool()
        
        # 동적 조절 함수들
        self.dynamic_adjusters: Dict[str, Callable] = {
            "market_condition": self._adjust_for_market_condition,
            "time_based": self._adjust_for_time,
            "performance_based": self._adjust_for_performance,
            "emotion_based": self._adjust_for_emotion
        }
        
        self.logger.info("Strategy Customizer 초기화 완료")
    
    def create_custom_strategy(self, strategy_config: Dict) -> str:
        """맞춤형 전략 생성"""
        try:
            strategy_id = f"custom_{uuid4().hex[:12]}"
            trusted_system = bool(strategy_config.get("trusted_system", False))
            source_kind = str(strategy_config.get("source_kind", "text") or "text").strip().lower()
            
            rules = dict(strategy_config.get("rules", {}) or {})
            base_params = dict(strategy_config.get("base_params", {}) or {})
            if base_params and "engine_settings" not in rules:
                rules["engine_settings"] = dict(base_params)
            # 기존 내부 프리셋/테스트는 빈 범위로 직접 trader에 적용하고,
            # 대시보드 AI 커스텀은 항상 명시적 target_scope를 전달한다.
            target_scope = str(strategy_config.get("target_scope", "") or "").lower()
            rules["target_scope"] = target_scope
            rules["target_exchange"] = str(strategy_config.get("target_exchange", "") or "").lower()
            rules["market_regimes"] = list(strategy_config.get("market_regimes", ["all"]) or ["all"])
            rules["regime_scope"] = str(
                strategy_config.get("regime_scope", rules.get("regime_scope", "market"))
                or "market"
            ).strip().lower()
            rules["universe_policy"] = dict(
                strategy_config.get("universe_policy", rules.get("universe_policy", {}))
                or {}
            )
            rules["priority"] = max(1, min(int(strategy_config.get("priority", 5) or 5), 10))
            rules["signal_mode"] = str(
                strategy_config.get("signal_mode", rules.get("signal_mode", "confirm")) or "confirm"
            ).strip().lower()
            rules["entry_signal"] = str(
                strategy_config.get("entry_signal", rules.get("entry_signal", "")) or ""
            ).strip().upper()

            # 기본 전략 구조
            custom_strategy = {
                "id": strategy_id,
                "name": strategy_config.get("name", f"Custom Strategy {strategy_id[-6:]}"),
                "created_at": datetime.now().isoformat(),
                "base_params": base_params,
                "filters": strategy_config.get("filters", {}),
                "time_rules": strategy_config.get("time_rules", {}),
                "risk_rules": strategy_config.get("risk_rules", {}),
                "dynamic_adjustments": strategy_config.get("dynamic_adjustments", []),
                "rules": rules,
                "source_kind": source_kind,
                "source_reference": str(strategy_config.get("source_reference", "") or ""),
                "target_exchange": str(strategy_config.get("target_exchange", "") or "").lower(),
                "target_scope": target_scope,
                "market_regimes": list(strategy_config.get("market_regimes", ["all"]) or ["all"]),
                "regime_scope": rules["regime_scope"],
                "universe_policy": dict(rules["universe_policy"]),
                "priority": max(1, min(int(strategy_config.get("priority", 5) or 5), 10)),
                "signal_mode": rules["signal_mode"],
                "entry_signal": rules["entry_signal"],
                "trusted_system": trusted_system,
                "backtesting_results": None,
                "live_performance": {
                    "total_trades": 0,
                    "win_rate": 0.0,
                    "avg_profit": 0.0,
                    "max_drawdown": 0.0,
                    "sharpe_ratio": 0.0
                }
            }
            
            # 전략 검증
            validation_result = self._validate_strategy(custom_strategy)
            if not validation_result["valid"]:
                raise ValueError(f"전략 검증 실패: {validation_result['reason']}")

            if trusted_system:
                custom_strategy["status"] = "trusted_system"
                custom_strategy["pipeline_strategy_key"] = None
                custom_strategy["pipeline_version_id"] = None
            else:
                version = self.custom_pipeline.submit(
                    name=custom_strategy["name"],
                    rules=custom_strategy["rules"],
                    source_kind=source_kind,
                    source_reference=custom_strategy["source_reference"],
                    strategy_key=strategy_config.get("strategy_key"),
                )
                custom_strategy["status"] = version["status"]
                custom_strategy["pipeline_strategy_key"] = version["strategy_key"]
                custom_strategy["pipeline_version_id"] = version["version_id"]
                custom_strategy["version"] = version["version"]
                custom_strategy["xai"] = version["xai"]
                custom_strategy["guidance"] = version.get("guidance", {})
                custom_strategy["missing_conditions"] = version["missing_conditions"]
                self._prune_unpersisted_strategy_records(version["strategy_key"])
            
            # 전략 저장
            self.user_strategies[strategy_id] = custom_strategy
            
            self.logger.info(f"맞춤형 전략 생성 완료: {strategy_id}")
            return strategy_id
            
        except Exception as e:
            self.logger.error(f"맞춤형 전략 생성 오류: {e}")
            raise

    def _hydrate_persisted_strategies(self) -> None:
        """계정별 저장소의 전략 버전을 대시보드/롤백에서 다시 사용할 수 있게 복원한다."""
        for strategy_key, versions in self.custom_pipeline.strategies.items():
            for version in versions:
                version_id = str(version.get("version_id", "") or "")
                if not version_id:
                    continue
                rules = dict(version.get("rules", {}) or {})
                engine_settings = dict(rules.get("engine_settings", {}) or {})
                strategy_id = f"persisted_{version_id}"
                self.user_strategies[strategy_id] = {
                    "id": strategy_id,
                    "name": version.get("name", "저장된 사용자 전략"),
                    "created_at": version.get("created_at", datetime.now().isoformat()),
                    "base_params": engine_settings,
                    "filters": dict(rules.get("filters", {}) or {}),
                    "time_rules": dict(rules.get("time_rules", {}) or {}),
                    "risk_rules": dict(rules.get("risk_rules", {}) or {}),
                    "dynamic_adjustments": list(rules.get("dynamic_adjustments", []) or []),
                    "rules": rules,
                    "source_kind": version.get("source_kind", "text"),
                    "source_reference": version.get("source_reference", ""),
                    "target_exchange": str(rules.get("target_exchange", "") or "").lower(),
                    "target_scope": str(rules.get("target_scope", "asset:crypto") or "asset:crypto").lower(),
                    "market_regimes": list(rules.get("market_regimes", ["all"]) or ["all"]),
                    "regime_scope": str(rules.get("regime_scope", "market") or "market"),
                    "universe_policy": dict(rules.get("universe_policy", {}) or {}),
                    "priority": max(1, min(int(rules.get("priority", 5) or 5), 10)),
                    "signal_mode": str(rules.get("signal_mode", "confirm") or "confirm").lower(),
                    "entry_signal": str(rules.get("entry_signal", "") or "").upper(),
                    "operation_mode": str(version.get("operation_mode", "standard") or "standard"),
                    "trusted_system": False,
                    "status": version.get("status", "unknown"),
                    "pipeline_strategy_key": strategy_key,
                    "pipeline_version_id": version_id,
                    "version": version.get("version"),
                    "xai": dict(version.get("xai", {}) or {}),
                    "guidance": dict(version.get("guidance", {}) or {}),
                    "improvement_advice": dict(version.get("improvement_advice", {}) or {}),
                    "missing_conditions": list(version.get("missing_conditions", []) or []),
                    "paper_validation": version.get("paper_validation"),
                    "execution_validation": version.get("execution_validation"),
                    "backtesting_results": None,
                    "live_performance": {},
                }
                if version.get("status") == "active":
                    self.active_strategy_id = strategy_id

    def _prune_unpersisted_strategy_records(self, strategy_key: str) -> None:
        """10개 제한으로 저장소에서 제거된 버전을 메모리 목록에서도 제거한다."""
        valid_ids = {
            item.get("version_id")
            for item in self.custom_pipeline.list_versions(strategy_key)
        }
        for strategy_id, strategy in list(self.user_strategies.items()):
            if strategy.get("pipeline_strategy_key") != strategy_key:
                continue
            if strategy.get("pipeline_version_id") not in valid_ids:
                self.user_strategies.pop(strategy_id, None)

    def _sync_pipeline_statuses(self, strategy_key: str) -> None:
        versions = {
            item.get("version_id"): item
            for item in self.custom_pipeline.list_versions(strategy_key)
        }
        for strategy_id, strategy in self.user_strategies.items():
            if strategy.get("pipeline_strategy_key") != strategy_key:
                continue
            version = versions.get(strategy.get("pipeline_version_id"), {})
            strategy["status"] = version.get("status", strategy.get("status", "unknown"))
            strategy["guidance"] = dict(version.get("guidance", strategy.get("guidance", {})) or {})
            strategy["improvement_advice"] = dict(
                version.get("improvement_advice", strategy.get("improvement_advice", {})) or {}
            )
            if strategy["status"] == "active":
                self.active_strategy_id = strategy_id

    @staticmethod
    def _has_executable_settings(strategy: Dict[str, Any]) -> bool:
        """자연어 규칙만 저장된 전략을 실행 완료로 오인하지 않게 한다."""
        declarative = dict((strategy.get("rules") or {}).get("executable_entry", {}) or {})
        has_declarative = bool(declarative.get("all") or declarative.get("any"))
        has_settings = has_declarative or any(
            bool(strategy.get(field))
            for field in ("base_params", "filters", "time_rules", "risk_rules")
        )
        rules = dict(strategy.get("rules", {}) or {})
        if str(rules.get("signal_mode", "confirm") or "confirm").lower() == "independent":
            return has_settings and str(rules.get("entry_signal", "") or "").upper() in {"LONG", "SHORT"}
        return has_settings
    
    def apply_strategy(self, strategy_id: str) -> bool:
        """전략 적용. 사용자 전략은 활성화 상태가 아니면 우회 적용을 차단한다."""
        try:
            if strategy_id not in self.user_strategies:
                raise ValueError(f"전략을 찾을 수 없습니다: {strategy_id}")
            
            strategy = self.user_strategies[strategy_id]

            if not strategy.get("trusted_system", False) and strategy.get("status") != "active":
                self.logger.warning(
                    "사용자 전략 적용 차단: XAI 승인·모의거래·소액 실거래 확인 필요 "
                    f"({strategy_id}, status={strategy.get('status')})"
                )
                return False

            return self._apply_strategy_values(strategy_id, strategy)

        except Exception as e:
            self.logger.error(f"전략 적용 오류: {e}")
            return False

    def _apply_strategy_values(self, strategy_id: str, strategy: Dict[str, Any]) -> bool:
        """승인 전략을 활성 풀에 반영하되 사용자 전략은 글로벌 기본값을 바꾸지 않는다."""
        try:
            operation_mode = str(strategy.get("operation_mode", "standard") or "standard").lower()
            base_params = (
                limited_live_engine_settings(strategy.get("base_params", {}))
                if operation_mode == "limited_live"
                else derive_strategy_risk_settings(
                    strategy.get("base_params", {}),
                    (strategy.get("rules", {}) or {}).get("risk_model", {}),
                )
            )

            # 내부 런타임 프로파일은 AI 커스텀 사용자 전략이 아니며, 사용자가
            # 명시적으로 선택한 경우에만 기존 전역 프로파일 경로를 유지한다.
            # 사용자 전략은 후보별 engine_settings로만 전달해 다른 전략과
            # 글로벌 TP/SL·레버리지·Analyzer 임계값을 오염시키지 않는다.
            if strategy.get("trusted_system", False) and self.trader:
                trader_settings = {}
                if "leverage" in base_params:
                    trader_settings["default_leverage"] = base_params["leverage"]
                if "tp_percent" in base_params:
                    trader_settings["default_tp"] = base_params["tp_percent"]
                if "sl_percent" in base_params:
                    trader_settings["default_sl"] = base_params["sl_percent"]
                if trader_settings:
                    self.trader.update_settings(trader_settings)
                    optimizer = getattr(self.trader, "optimizer", None)
                    if optimizer is not None:
                        updater = getattr(optimizer, "update_settings", None)
                        if callable(updater):
                            updater(trader_settings)

            self.active_strategy_id = strategy_id
            self._refresh_runtime_strategy_pool()
            self.logger.info(
                f"전략 활성 풀 반영 완료: {strategy['name']} ({strategy_id}, "
                f"role={strategy.get('signal_mode', 'confirm')}, mode={operation_mode})"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"전략 적용 오류: {e}")
            return False

    def _strategy_for_version(self, strategy_key: str, version_id: str) -> tuple[str, Dict[str, Any]]:
        for strategy_id, strategy in self.user_strategies.items():
            if (
                strategy.get("pipeline_strategy_key") == strategy_key
                and strategy.get("pipeline_version_id") == version_id
            ):
                return strategy_id, strategy
        raise ValueError(f"전략 버전 매핑을 찾을 수 없습니다: {strategy_key}/{version_id}")

    def clarify_custom_strategy(self, strategy_key: str, version_id: str, answers: Dict[str, Any]) -> Dict[str, Any]:
        """누락 조건을 사용자 답변으로만 보완한다."""
        version = self.custom_pipeline.clarify(strategy_key, version_id, answers)
        _, strategy = self._strategy_for_version(strategy_key, version_id)
        strategy["rules"] = dict(version["rules"])
        strategy["status"] = version["status"]
        strategy["missing_conditions"] = list(version["missing_conditions"])
        strategy["guidance"] = dict(version.get("guidance", {}) or {})
        self._sync_pipeline_statuses(strategy_key)
        return version

    def approve_custom_strategy(self, strategy_key: str, version_id: str, *, approved_by: str) -> Dict[str, Any]:
        """XAI 내용을 확인한 사용자 승인을 기록한다."""
        version = self.custom_pipeline.approve(strategy_key, version_id, approved_by=approved_by)
        _, strategy = self._strategy_for_version(strategy_key, version_id)
        strategy["status"] = version["status"]
        self._sync_pipeline_statuses(strategy_key)
        return version

    def record_paper_validation(
        self,
        strategy_key: str,
        version_id: str,
        *,
        trades: int,
        guardrail_violations: int = 0,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """백테스트가 아닌 필수 모의거래 결과를 기록한다."""
        version = self.custom_pipeline.record_paper_validation(
            strategy_key,
            version_id,
            trades=trades,
            guardrail_violations=guardrail_violations,
            metrics=metrics,
        )
        _, strategy = self._strategy_for_version(strategy_key, version_id)
        strategy["status"] = version["status"]
        strategy["paper_validation"] = version["paper_validation"]
        self._sync_pipeline_statuses(strategy_key)
        return version

    def record_execution_validation(
        self,
        strategy_key: str,
        version_id: str,
        *,
        decisions: int,
        guardrail_violations: int = 0,
        metrics: Optional[Dict[str, Any]] = None,
        mode: str = "live_observation",
    ) -> Dict[str, Any]:
        """거래 엔진의 관찰학습/제한운용 결과를 전략 버전에 연결한다."""
        version = self.custom_pipeline.record_execution_validation(
            strategy_key,
            version_id,
            decisions=decisions,
            guardrail_violations=guardrail_violations,
            metrics=metrics,
            mode=mode,
        )
        _, strategy = self._strategy_for_version(strategy_key, version_id)
        strategy["status"] = version["status"]
        strategy["execution_validation"] = version["execution_validation"]
        strategy["improvement_advice"] = dict(version.get("improvement_advice", {}) or {})
        self._sync_pipeline_statuses(strategy_key)
        return version

    def run_historical_validation(
        self,
        strategy_key: str,
        version_id: str,
        *,
        symbol: Optional[str] = None,
        limit: int = 500,
        historical_data: Optional[List[Any]] = None,
        validation_target: Optional[str] = None,
    ) -> Dict[str, Any]:
        """대시보드 숫자 수기 입력 없이 거래소 캔들로 실행 조건과 PnL을 재생한다."""
        from trading.custom_strategy_validator import (
            collect_advanced_indicator_references,
            run_historical_replay,
        )

        _, strategy = self._strategy_for_version(strategy_key, version_id)
        target = str(strategy.get("target_exchange", "") or "").lower()
        scope = str(strategy.get("target_scope", "") or "").lower()
        is_stock = scope.startswith("asset:stock") or scope.startswith("broker:")
        if is_stock and historical_data is None:
            raise ValueError("주식/ETF 자동 검증에는 연결된 증권사의 가격 이력이 필요합니다.")
        selected_symbol = symbol or {
            "upbit": "KRW-BTC", "bithumb": "BTC_KRW",
        }.get(target, "BTCUSDT")
        klines: List[Any] = list(historical_data or [])
        rules = dict(strategy.get("rules", {}) or {})
        requested_timeframes = sorted({
            str(item.get("timeframe") or "5m").lower()
            for item in collect_advanced_indicator_references(rules)
        })
        timeframe_klines: Dict[str, List[Any]] = {}
        if historical_data is not None:
            timeframe_klines["15m"] = klines
            unsupported_history = [item for item in requested_timeframes if item != "15m"]
            if unsupported_history:
                raise ValueError(
                    "외부 과거 데이터 검증에는 시간봉별 캔들이 필요합니다: "
                    + ", ".join(unsupported_history)
                )
        elif target in {"", "binance"} and getattr(self.trader, "binance_client", None) is not None:
            klines = self.trader.binance_client.get_klines(selected_symbol, "15m", int(limit))
            timeframe_klines["15m"] = klines
            for timeframe in requested_timeframes:
                if timeframe == "15m":
                    continue
                timeframe_klines[timeframe] = self.trader.binance_client.get_klines(
                    selected_symbol, timeframe, int(limit)
                )
        else:
            manager = getattr(self.trader, "exchange_manager", None)
            if manager is None:
                raise RuntimeError("대상 거래소의 과거 시세 연결이 준비되지 않았습니다.")
            klines = manager.get_klines(
                selected_symbol, interval="15m", limit=int(limit), exchange_name=target or None,
            )
            timeframe_klines["15m"] = klines
            for timeframe in requested_timeframes:
                if timeframe == "15m":
                    continue
                timeframe_klines[timeframe] = manager.get_klines(
                    selected_symbol,
                    interval=timeframe,
                    limit=int(limit),
                    exchange_name=target or None,
                )
        trader_settings = dict(getattr(self.trader, "settings", {}) or {}) if self.trader is not None else {}
        validation_costs = dict(trader_settings.get("ai_custom_validation_costs", {}) or {})
        venue_key = str(validation_target or target or ("stock" if is_stock else "binance")).lower()
        venue_costs = dict((validation_costs.get("venues", {}) or {}).get(venue_key, {}) or {})
        fee_rate = float(venue_costs.get(
            "fee_rate_per_side",
            validation_costs.get("fee_rate_per_side", 0.001),
        ) or 0.0)
        slippage_bps = float(venue_costs.get(
            "slippage_bps_per_side",
            validation_costs.get("slippage_bps_per_side", 2.0),
        ) or 0.0)
        spread_bps = float(venue_costs.get(
            "spread_bps_round_trip",
            validation_costs.get("spread_bps_round_trip", 1.0),
        ) or 0.0)
        metrics = run_historical_replay(
            rules,
            klines,
            timeframe_klines=timeframe_klines,
            fee_rate=fee_rate,
            slippage_bps=slippage_bps,
            spread_bps=spread_bps,
        )
        minimum = int(getattr(self.custom_pipeline, "min_paper_trades", 3) or 3)
        quality_pass = (
            int(metrics.get("decisions", 0) or 0) >= minimum
            and float(metrics.get("net_pnl_percent", 0.0) or 0.0) > 0.0
            and float(metrics.get("max_drawdown_percent", 0.0) or 0.0) <= 10.0
        )
        metrics.update({
            "symbol": selected_symbol,
            "exchange": validation_target or target or ("stock" if is_stock else "binance"),
            "quality_gate": "decisions>=minimum AND net_pnl>0 AND max_drawdown<=10%",
            "quality_passed": quality_pass,
        })
        return self.record_execution_validation(
            strategy_key,
            version_id,
            decisions=int(metrics.get("decisions", 0) or 0),
            guardrail_violations=0 if quality_pass else 1,
            metrics=metrics,
            mode="historical_replay",
        )

    def _guardrail_allows(self, version: Dict[str, Any]) -> bool:
        """전략 종류와 무관하게 공통 리스크 엔진을 마지막 우선순위로 강제한다."""
        rules = dict(version.get("rules", {}) or {})
        operation_mode = str(version.get("operation_mode", "standard") or "standard").lower()
        settings = (
            limited_live_engine_settings(rules.get("engine_settings", {}))
            if operation_mode == "limited_live"
            else derive_strategy_risk_settings(
                rules.get("engine_settings", {}),
                rules.get("risk_model", {}),
            )
        )
        trader_settings = dict(getattr(self.trader, "settings", {}) or {}) if self.trader is not None else {}
        max_leverage = max(1.0, float(trader_settings.get("max_leverage", 10.0) or 10.0))
        max_position = min(1.0, max(0.0, float(
            trader_settings.get("max_custom_position_size", 0.5) or 0.5
        )))
        if float(settings.get("leverage", 1.0) or 1.0) > max_leverage:
            return False
        if float(settings.get("position_size", 0.0) or 0.0) > max_position:
            return False
        if float(settings.get("sl_percent", 0.0) or 0.0) <= 0:
            return False
        if not rules.get("stop_loss"):
            return False
        if (
            str(rules.get("signal_mode", "confirm") or "confirm").lower() == "independent"
            and str(rules.get("entry_signal", "") or "").upper() not in {"LONG", "SHORT"}
        ):
            return False
        if self.risk_manager is None:
            return True
        validator = getattr(self.risk_manager, "validate_custom_strategy", None)
        if callable(validator):
            result = validator(version)
            return bool(result.get("allowed", False)) if isinstance(result, dict) else bool(result)
        return True

    def activate_custom_strategy(
        self,
        strategy_key: str,
        version_id: str,
        *,
        live_confirmation: bool,
        operation_mode: str = "standard",
    ) -> Dict[str, Any]:
        """실행 검증 통과 버전을 최종 확인 후 런타임에 적용한다."""
        strategy_id, strategy = self._strategy_for_version(strategy_key, version_id)
        active_ids = [
            sid for sid, item in self.user_strategies.items()
            if item.get("status") == "active" and sid != strategy_id
        ]
        if len(active_ids) >= 10:
            raise ValueError("활성 전략 풀은 최대 10개입니다. 기존 전략을 해제한 뒤 다시 적용하세요.")
        if not self._has_executable_settings(strategy):
            raise ValueError("전략은 분석됐지만 실행 엔진 설정으로 변환되지 않았습니다. 누락 조건을 확인해 주세요.")
        version = self.custom_pipeline.activate(
            strategy_key,
            version_id,
            live_confirmation=live_confirmation,
            operation_mode=operation_mode,
            guardrail_check=self._guardrail_allows,
        )
        strategy["status"] = "active"
        strategy["operation_mode"] = str(version.get("operation_mode", operation_mode) or operation_mode)
        if not self._apply_strategy_values(strategy_id, strategy):
            raise RuntimeError("승인된 전략의 런타임 적용에 실패했습니다.")
        self._sync_pipeline_statuses(strategy_key)
        return version

    def rollback_custom_strategy(
        self,
        strategy_key: str,
        target_version_id: str,
        *,
        approved_by: str,
    ) -> Dict[str, Any]:
        """모의거래 통과 이력이 있는 이전 버전으로만 롤백한다."""
        version = self.custom_pipeline.rollback(
            strategy_key,
            target_version_id,
            approved_by=approved_by,
        )
        strategy_id, strategy = self._strategy_for_version(strategy_key, target_version_id)
        strategy["status"] = "active"
        if not self._apply_strategy_values(strategy_id, strategy):
            raise RuntimeError("롤백 전략의 런타임 적용에 실패했습니다.")
        self._sync_pipeline_statuses(strategy_key)
        return version

    def deactivate_custom_strategy(self, strategy_key: str, version_id: str, *, approved_by: str) -> Dict[str, Any]:
        """사용자 확인으로 활성 전략을 풀에서 제거한다."""
        version = self.custom_pipeline.deactivate(strategy_key, version_id, approved_by=approved_by)
        strategy_id, strategy = self._strategy_for_version(strategy_key, version_id)
        strategy["status"] = version["status"]
        target_scope = str(strategy.get("target_scope", "") or "").lower()
        target_exchange = str(strategy.get("target_exchange", "") or "").lower()
        if self.trader is not None:
            if target_scope == "exchange:binance":
                setattr(self.trader, "active_custom_strategy_rules", {})
            elif target_scope.startswith("exchange:") and target_exchange:
                rules_by_exchange = getattr(self.trader, "active_custom_strategy_rules_by_exchange", {}) or {}
                rules_by_exchange.pop(target_exchange, None)
                setattr(self.trader, "active_custom_strategy_rules_by_exchange", rules_by_exchange)
        if self.active_strategy_id == strategy_id:
            self.active_strategy_id = None
        self._refresh_runtime_strategy_pool()
        self._sync_pipeline_statuses(strategy_key)
        return version
    
    def _validate_strategy(self, strategy: Dict) -> Dict[str, Any]:
        """전략 검증"""
        try:
            # 필수 필드 확인
            required_fields = ["name", "base_params"]
            for field in required_fields:
                if field not in strategy:
                    return {"valid": False, "reason": f"필수 필드 누락: {field}"}
            
            # 파라미터 범위 확인
            base_params = strategy["base_params"]
            
            # 레버리지 범위 (1x ~ 10x)
            if "leverage" in base_params:
                leverage = base_params["leverage"]
                if not (1 <= leverage <= 10):
                    return {"valid": False, "reason": f"레버리지 범위 초과: {leverage} (1~10x)"}
            
            # 포지션 크기 (1% ~ 50%)
            if "position_size" in base_params:
                position_size = base_params["position_size"]
                if not (0.01 <= position_size <= 0.5):
                    return {"valid": False, "reason": f"포지션 크기 범위 초과: {position_size*100}% (1~50%)"}
            
            # TP/SL 범위 (0.01% ~ 5%)
            for param in ["tp_percent", "sl_percent"]:
                if param in base_params:
                    value = base_params[param]
                    if not (0.01 <= value <= 5.0):
                        return {"valid": False, "reason": f"{param} 범위 초과: {value}% (0.01~5%)"}
            
            # 신호 임계값 (30 ~ 95)
            if "signal_threshold" in base_params:
                threshold = base_params["signal_threshold"]
                if not (30 <= threshold <= 95):
                    return {"valid": False, "reason": f"신호 임계값 범위 초과: {threshold} (30~95)"}
            
            return {"valid": True, "reason": "검증 통과"}
            
        except Exception as e:
            return {"valid": False, "reason": f"검증 오류: {str(e)}"}
    
    def _apply_coin_filters(self, filters: Dict):
        """코인 필터 적용"""
        try:
            # 카테고리 필터
            if "categories" in filters:
                categories = filters["categories"]
                self.logger.info(f"코인 카테고리 필터 적용: {categories}")
                if self.evaluator and hasattr(self.evaluator, 'set_category_filter'):
                    self.evaluator.set_category_filter(categories)
                elif self.evaluator and hasattr(self.evaluator, 'user_category_filter'):
                    self.evaluator.user_category_filter = list(categories)
            
            # 시가총액 필터
            if "market_cap_min" in filters:
                market_cap_min = float(filters["market_cap_min"])
                self.logger.info(f"최소 시가총액 필터: {market_cap_min}")
                if self.evaluator and hasattr(self.evaluator, 'set_market_cap_filter'):
                    self.evaluator.set_market_cap_filter(market_cap_min)
                elif self.evaluator and hasattr(self.evaluator, 'min_market_cap'):
                    self.evaluator.min_market_cap = market_cap_min
            
            # 거래량 필터
            if "volume_min" in filters:
                volume_min = float(filters["volume_min"])
                self.logger.info(f"최소 거래량 필터: {volume_min}")
                if self.evaluator and hasattr(self.evaluator, 'set_volume_filter'):
                    self.evaluator.set_volume_filter(volume_min)
                elif self.evaluator and hasattr(self.evaluator, 'min_volume_24h'):
                    self.evaluator.min_volume_24h = volume_min
            
            # 선호/제외 코인
            if "preferred_coins" in filters:
                preferred = filters["preferred_coins"]
                self.logger.info(f"선호 코인: {preferred}")
                if self.evaluator and hasattr(self.evaluator, 'preferred_symbols'):
                    self.evaluator.preferred_symbols = list(preferred)
            
            if "excluded_coins" in filters:
                excluded = filters["excluded_coins"]
                self.logger.info(f"제외 코인: {excluded}")
                if self.evaluator and hasattr(self.evaluator, 'excluded_symbols'):
                    self.evaluator.excluded_symbols = list(excluded)
                
        except Exception as e:
            self.logger.error(f"코인 필터 적용 오류: {e}")
    
    def _apply_risk_rules(self, risk_rules: Dict):
        """리스크 규칙 적용"""
        try:
            rm = self.risk_manager

            # 일일 손실 한도
            if "daily_loss_limit" in risk_rules:
                daily_limit = float(risk_rules["daily_loss_limit"])
                self.logger.info(f"일일 손실 한도 설정: {daily_limit}%")
                if rm is not None:
                    if hasattr(rm, 'set_daily_loss_limit'):
                        rm.set_daily_loss_limit(daily_limit)
                    elif hasattr(rm, 'daily_loss_limit'):
                        rm.daily_loss_limit = daily_limit

            # 연속 손실 제한
            if "max_consecutive_losses" in risk_rules:
                max_losses = int(risk_rules["max_consecutive_losses"])
                self.logger.info(f"최대 연속 손실: {max_losses}회")
                if rm is not None:
                    if hasattr(rm, 'set_max_consecutive_losses'):
                        rm.set_max_consecutive_losses(max_losses)
                    elif hasattr(rm, 'max_consecutive_losses'):
                        rm.max_consecutive_losses = max_losses

            # 최대 포지션 수
            if "max_positions" in risk_rules:
                max_pos = int(risk_rules["max_positions"])
                self.logger.info(f"최대 동시 포지션 수: {max_pos}")
                if rm is not None and hasattr(rm, 'max_positions'):
                    rm.max_positions = max_pos

            # 감정 기반 조절
            if "emotion_adjustment" in risk_rules:
                emotion_factor = risk_rules["emotion_adjustment"]
                self.logger.info(f"감정 기반 리스크 조절: {emotion_factor}")
                if rm is not None and hasattr(rm, 'emotion_factor'):
                    rm.emotion_factor = float(emotion_factor)

        except Exception as e:
            self.logger.error(f"리스크 규칙 적용 오류: {e}")
    
    def apply_dynamic_adjustment(self, adjustment_type: str, context: Dict) -> bool:
        """레거시 전역 동적 조절 진입점.

        사용자 AI 커스텀 전략의 조정은 후보 평가 시 전략별로 적용한다.
        이 공개 경로가 글로벌 Trader/Analyzer 설정을 바꾸지 않도록 차단한다.
        """
        try:
            if self.active_strategy_id:
                active = self.user_strategies.get(self.active_strategy_id, {})
                if active and not active.get("trusted_system", False):
                    self.logger.debug(
                        "사용자 전략 동적 조절은 후보별 선언형 평가에서 적용: %s",
                        adjustment_type,
                    )
                    return False
            if adjustment_type in self.dynamic_adjusters:
                adjuster_func = self.dynamic_adjusters[adjustment_type]
                result = adjuster_func(context)
                
                if result:
                    self.logger.info(f"동적 조절 적용 완료: {adjustment_type}")
                    return True
                else:
                    # 사용자 전략에 해당 조절 규칙이 없는 것은 오류가 아니라
                    # "원래 전략을 그대로 유지"한다는 뜻이다.
                    self.logger.debug(f"동적 조절 미적용: {adjustment_type}")
                    return False
            else:
                self.logger.warning(f"알 수 없는 조절 타입: {adjustment_type}")
                return False
                
        except Exception as e:
            self.logger.error(f"동적 조절 오류: {e}")
            return False
    
    def _adjust_for_market_condition(self, context: Dict) -> bool:
        """사용자가 선언한 시장상황별 파라미터만 적용한다.

        시스템이 임의로 레버리지나 포지션을 올리거나 낮추지 않는다.
        """
        try:
            if not self.active_strategy_id:
                return False
            
            strategy = self.user_strategies[self.active_strategy_id]
            aliases = {
                "BULL": "bull", "BULLISH": "bull", "UPTREND": "bull",
                "BEAR": "bear", "BEARISH": "bear", "DOWNTREND": "bear",
                "SIDEWAYS": "range", "NORMAL": "range", "RANGE": "range",
                "VOLATILE": "volatile", "HIGH_VOL": "volatile",
                "HIGH_VOLATILITY": "volatile",
                "CALM": "calm", "LOW_VOL": "calm", "LOW_VOLATILITY": "calm",
            }
            raw_condition = str(context.get("market_condition", "NORMAL") or "NORMAL").upper()
            market_condition = aliases.get(raw_condition, raw_condition.lower())
            rules = dict(strategy.get("rules", {}) or {})
            regime_parameters = dict(
                rules.get("regime_parameters", rules.get("market_condition_parameters", {})) or {}
            )
            explicit = regime_parameters.get(market_condition, {})
            if not isinstance(explicit, dict) or not explicit:
                return False

            base = dict(strategy.get("base_params", {}) or {})
            base.update(explicit)
            adjustments = derive_strategy_risk_settings(
                base,
                rules.get("risk_model", {}),
                context,
            )
            
            # 조절사항 적용
            if adjustments and self.trader:
                trader_settings = {}
                if "leverage" in adjustments:
                    trader_settings["default_leverage"] = adjustments["leverage"]
                if "tp_percent" in adjustments:
                    trader_settings["default_tp"] = adjustments["tp_percent"]
                if "sl_percent" in adjustments:
                    trader_settings["default_sl"] = adjustments["sl_percent"]
                if "position_size" in adjustments:
                    trader_settings["position_size"] = adjustments["position_size"]
                if trader_settings:
                    self.trader.update_settings(trader_settings)
                self.logger.info(
                    f"사용자 선언 시장상황 조절 적용: {market_condition} -> {adjustments}"
                )
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"시장 상황 조절 오류: {e}")
            return False
    
    def _adjust_for_time(self, context: Dict) -> bool:
        """시간 기반 조절"""
        try:
            if not self.active_strategy_id:
                return False
            
            strategy = self.user_strategies[self.active_strategy_id]
            time_rules = strategy.get("time_rules", {})
            
            current_time = datetime.now().time()
            current_hour = current_time.hour
            
            # 시간대별 활성화 체크
            active_hours = time_rules.get("active_hours", [(0, 23)])
            is_active_time = any(start <= current_hour <= end for start, end in active_hours)
            
            if not is_active_time:
                self.logger.info(f"비활성 시간대: {current_hour}시 — 거래 일시 중단")
                if self.trader and hasattr(self.trader, 'pause_trading'):
                    self.trader.pause_trading(reason=f'비활성 시간대({current_hour}시)')
                elif self.trader and hasattr(self.trader, 'set_monitoring_mode'):
                    self.trader.set_monitoring_mode(True)
                return True
            
            # 시간대별 파라미터 조절
            time_specific_params = time_rules.get("time_specific_params", {})
            
            if "morning" in time_specific_params and 6 <= current_hour <= 12:
                params = time_specific_params["morning"]
            elif "afternoon" in time_specific_params and 12 <= current_hour <= 18:
                params = time_specific_params["afternoon"]
            elif "evening" in time_specific_params and 18 <= current_hour <= 24:
                params = time_specific_params["evening"]
            else:
                return True  # 기본 설정 유지
            
            # 시간대별 설정 적용
            if params and self.trader:
                trader_settings = {}
                for key, value in params.items():
                    if key == "aggressiveness":
                        # 공격성 수준에 따른 파라미터 조절
                        if value == "high":
                            trader_settings["default_leverage"] = min(3, strategy["base_params"].get("leverage", 1) * 1.5)
                        elif value == "low":
                            trader_settings["default_leverage"] = max(1, strategy["base_params"].get("leverage", 1) * 0.8)
                
                if trader_settings:
                    self.trader.update_settings(trader_settings)
                    self.logger.info(f"시간대 조절 적용: {current_hour}시 -> {params}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"시간 기반 조절 오류: {e}")
            return False
    
    def _adjust_for_performance(self, context: Dict) -> bool:
        """사용자가 선언한 성과 조건만 적용한다.

        승률이나 연속 손실만 보고 시스템이 전략을 자동 변경하지 않는다.
        AI 개선안은 새 버전 제안으로만 남고, 이 경로는 명시 규칙만 실행한다.
        """
        try:
            if not self.active_strategy_id:
                return False
            
            performance_data = context.get("performance", {})
            recent_win_rate = performance_data.get("recent_win_rate", 0.5)
            consecutive_losses = performance_data.get("consecutive_losses", 0)
            
            strategy = self.user_strategies[self.active_strategy_id]
            rules = dict(strategy.get("rules", {}) or {})
            declared = list(rules.get("performance_adjustments", []) or [])
            adjustments = {}
            for item in declared:
                if not isinstance(item, dict):
                    continue
                when = dict(item.get("when", {}) or {})
                loss_min = int(when.get("consecutive_losses_gte", -1) or -1)
                win_min = float(when.get("recent_win_rate_gte", -1) or -1)
                if loss_min >= 0 and consecutive_losses >= loss_min:
                    adjustments.update(dict(item.get("set", {}) or {}))
                    break
                if win_min >= 0 and recent_win_rate >= win_min:
                    adjustments.update(dict(item.get("set", {}) or {}))
                    break
            if not adjustments:
                return False

            base = dict(strategy.get("base_params", {}) or {})
            base.update(adjustments)
            adjustments = derive_strategy_risk_settings(
                base,
                rules.get("risk_model", {}),
                context,
            )
            
            # 조절사항 적용
            if adjustments:
                if self.trader:
                    trader_settings = {}
                    if "leverage" in adjustments:
                        trader_settings["default_leverage"] = adjustments["leverage"]
                    if "tp_percent" in adjustments:
                        trader_settings["default_tp"] = adjustments["tp_percent"]
                    if "sl_percent" in adjustments:
                        trader_settings["default_sl"] = adjustments["sl_percent"]
                    if "position_size" in adjustments:
                        pos_size = float(adjustments["position_size"])
                        trader_settings["position_size"] = pos_size
                        # 직접 속성 지원 시 함께 갱신
                        if hasattr(self.trader, 'position_size'):
                            self.trader.position_size = pos_size
                        elif hasattr(self.trader, 'set_position_size'):
                            self.trader.set_position_size(pos_size)
                    
                    if trader_settings:
                        self.trader.update_settings(trader_settings)
                
                if self.analyzer and "signal_threshold" in adjustments:
                    self.analyzer.set_user_signal_threshold(adjustments["signal_threshold"])
                
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"성과 기반 조절 오류: {e}")
            return False
    
    def _adjust_for_emotion(self, context: Dict) -> bool:
        """감정 기반 조절"""
        try:
            emotion_state = context.get("emotion", "neutral")
            stress_level = context.get("stress_level", 0.5)  # 0.0 ~ 1.0
            
            if not self.active_strategy_id:
                return False
            
            strategy = self.user_strategies[self.active_strategy_id]
            
            # 스트레스 수준에 따른 조절
            if stress_level > 0.7 or emotion_state in ["stressed", "anxious"]:
                # 고스트레스: 매우 보수적
                adjustments = {
                    "leverage": 1,
                    "position_size": strategy["base_params"].get("position_size", 0.1) * 0.3,
                    "sl_percent": strategy["base_params"].get("sl_percent", 0.2) * 0.7,
                    "signal_threshold": min(90, strategy["base_params"].get("signal_threshold", 70) + 15)
                }
                self.logger.info(f"고스트레스 상태 감지 - 안전 모드 적용: {emotion_state}")
                
            elif stress_level < 0.3 and emotion_state in ["confident", "happy"]:
                # 저스트레스 + 긍정적: 약간 적극적
                adjustments = {
                    "leverage": min(2, strategy["base_params"].get("leverage", 1) + 0.5),
                    "position_size": min(0.15, strategy["base_params"].get("position_size", 0.1) * 1.1),
                }
                self.logger.info(f"긍정적 상태 감지 - 균형 모드 적용: {emotion_state}")
                
            else:
                return True  # 중립 상태, 변경 없음
            
            # 조절사항 적용
            if self.trader:
                trader_settings = {}
                if "leverage" in adjustments:
                    trader_settings["default_leverage"] = adjustments["leverage"]
                if "sl_percent" in adjustments:
                    trader_settings["default_sl"] = adjustments["sl_percent"]
                
                if trader_settings:
                    self.trader.update_settings(trader_settings)
            
            if self.analyzer and "signal_threshold" in adjustments:
                self.analyzer.set_user_signal_threshold(adjustments["signal_threshold"])
            
            return True
            
        except Exception as e:
            self.logger.error(f"감정 기반 조절 오류: {e}")
            return False
    
    def get_strategy_performance(self, strategy_id: str) -> Dict[str, Any]:
        """전략 성과 조회"""
        try:
            if strategy_id not in self.user_strategies:
                return {}
            
            strategy = self.user_strategies[strategy_id]
            return strategy.get("live_performance", {})
            
        except Exception as e:
            self.logger.error(f"전략 성과 조회 오류: {e}")
            return {}
    
    def list_strategies(self) -> List[Dict[str, Any]]:
        """전략 목록 조회"""
        try:
            return [
                {
                    "id": strategy_id,
                    "name": strategy["name"],
                    "created_at": strategy["created_at"],
                    "active": strategy_id == self.active_strategy_id,
                    "status": strategy.get("status", "unknown"),
                    "version": strategy.get("version"),
                    "strategy_key": strategy.get("pipeline_strategy_key"),
                    "version_id": strategy.get("pipeline_version_id"),
                    "missing_conditions": strategy.get("missing_conditions", []),
                    "guidance": dict(strategy.get("guidance", {}) or {}),
                    "improvement_advice": dict(strategy.get("improvement_advice", {}) or {}),
                    "target_exchange": strategy.get("target_exchange", ""),
                    "target_scope": strategy.get("target_scope", "asset:crypto"),
                    "market_regimes": list(strategy.get("market_regimes", ["all"]) or ["all"]),
                    "regime_scope": str(strategy.get("regime_scope", "market") or "market"),
                    "universe_policy": dict(strategy.get("universe_policy", {}) or {}),
                    "priority": int(strategy.get("priority", 5) or 5),
                    "signal_mode": str(strategy.get("signal_mode", "confirm") or "confirm"),
                    "entry_signal": str(strategy.get("entry_signal", "") or ""),
                    "operation_mode": str(strategy.get("operation_mode", "standard") or "standard"),
                    "performance": strategy.get("live_performance", {})
                }
                for strategy_id, strategy in self.user_strategies.items()
            ]
            
        except Exception as e:
            self.logger.error(f"전략 목록 조회 오류: {e}")
            return []

    def get_active_strategy_pool(self) -> List[Dict[str, Any]]:
        """거래 직전 상황 매칭에 사용할 활성 전략을 우선순위순 최대 10개 반환한다."""
        pool: List[Dict[str, Any]] = []
        for strategy_id, strategy in self.user_strategies.items():
            if strategy.get("status") != "active":
                continue
            operation_mode = str(strategy.get("operation_mode", "standard") or "standard").lower()
            engine_settings = (
                limited_live_engine_settings(strategy.get("base_params", {}))
                if operation_mode == "limited_live"
                else derive_strategy_risk_settings(
                    strategy.get("base_params", {}),
                    (strategy.get("rules", {}) or {}).get("risk_model", {}),
                )
            )
            pool.append({
                "id": strategy_id,
                "name": strategy.get("name", "사용자 전략"),
                "rules": dict(strategy.get("rules", {}) or {}),
                "engine_settings": engine_settings,
                "target_scope": strategy.get("target_scope", "asset:crypto"),
                "market_regimes": list(strategy.get("market_regimes", ["all"]) or ["all"]),
                "regime_scope": str(strategy.get("regime_scope", "market") or "market"),
                "universe_policy": dict(strategy.get("universe_policy", {}) or {}),
                "priority": int(strategy.get("priority", 5) or 5),
                "signal_mode": str(strategy.get("signal_mode", "confirm") or "confirm"),
                "entry_signal": str(strategy.get("entry_signal", "") or ""),
                "operation_mode": operation_mode,
                "strategy_key": strategy.get("pipeline_strategy_key"),
                "version_id": strategy.get("pipeline_version_id"),
            })
        return sorted(pool, key=lambda item: int(item.get("priority", 5)), reverse=True)[:10]

    def _refresh_runtime_strategy_pool(self) -> None:
        if self.trader is not None:
            setattr(self.trader, "active_custom_strategy_pool", self.get_active_strategy_pool())
            # v3.9.0.4부터 활성 전략 풀만 런타임 정본이다. 과거 단일 규칙과
            # 거래소별 글로벌 설정은 실행 경로에서 재사용하지 않는다.
            setattr(self.trader, "active_custom_strategy_rules", {})
            setattr(self.trader, "active_custom_strategy_rules_by_exchange", {})
            setattr(self.trader, "custom_engine_settings_by_exchange", {})
    
    def backup_strategy(self, strategy_id: str) -> bool:
        """전략 백업"""
        try:
            if strategy_id not in self.user_strategies:
                return False
            
            strategy = self.user_strategies[strategy_id]
            backup_data = {
                "strategy": strategy,
                "backup_time": datetime.now().isoformat(),
                "backup_reason": "user_request"
            }
            
            # 백업 파일 저장
            backup_filename = f"strategy_backup_{strategy_id}_{int(datetime.now().timestamp())}.json"
            with open(backup_filename, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"전략 백업 완료: {backup_filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"전략 백업 오류: {e}")
            return False
