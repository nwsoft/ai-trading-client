#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""거래 기회를 보존하면서 반복 LLM 호출을 줄이는 런타임 정책."""

from __future__ import annotations

import json
import math
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class OpportunityAwareInferencePolicy:
    """시장 이벤트 기반 호출, 상태 캐시, 호출 예산을 한 곳에서 관리한다.

    비용 한도는 LLM 호출만 제한한다. 로컬 기술 신호 생성과 주문 경로는
    계속 동작하므로 비용 제어가 거래 중단 스위치로 사용되지 않는다.
    """

    DEFAULTS: Dict[str, Any] = {
        "enabled": True,
        "stable_state_cache_sec": 1800,
        "exploration_interval_sec": 1800,
        "minimum_event_interval_sec": 300,
        "price_change_bps": 15.0,
        "rsi_event_low": 35.0,
        "rsi_event_high": 65.0,
        "max_daily_market_calls": 240,
        "max_daily_calls_per_exchange": 40,
        "max_monthly_market_calls": 6000,
        # 이전 버전의 1,200회/일 설정이 사용자 설정 파일에 남아 있어도
        # 명시적인 고비용 허용 없이는 안전 상한을 넘지 않는다.
        "hard_max_daily_market_calls": 240,
        "hard_max_daily_calls_per_exchange": 40,
        "hard_max_monthly_market_calls": 6000,
        "allow_high_cost_limits": False,
        "max_cache_entries": 1000,
    }
    BUDGET_POLICY_VERSION = "fix4-v1"
    _PROCESS_BUDGET_LOCK = threading.RLock()

    def __init__(
        self,
        settings: Optional[Dict[str, Any]] = None,
        *,
        state_path: Optional[str] = None,
        clock=time.time,
    ):
        self._lock = threading.RLock()
        self._clock = clock
        self._settings: Dict[str, Any] = settings or {}
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        self._last_ai_call: Dict[str, float] = {}
        self._state_path = state_path or self._default_state_path()
        self._counters = self._load_counters()

    @staticmethod
    def _default_state_path() -> str:
        try:
            from path_utils import get_app_data_dir

            return os.path.join(get_app_data_dir(), "ai_market_call_budget.json")
        except Exception:
            return ""

    def update_settings(self, settings: Optional[Dict[str, Any]]) -> None:
        with self._lock:
            self._settings = settings or {}

    def _config(self) -> Dict[str, Any]:
        configured = self._settings.get("ai_cost_control", {})
        merged = dict(self.DEFAULTS)
        if isinstance(configured, dict):
            merged.update(configured)
        return merged

    @staticmethod
    def _period_keys(timestamp: float) -> tuple[str, str]:
        now = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")

    def _load_counters(self) -> Dict[str, Any]:
        if not self._state_path or not os.path.exists(self._state_path):
            return {
                "policy_version": self.BUDGET_POLICY_VERSION,
                "daily": {}, "monthly": {}, "exchange_daily": {},
            }
        try:
            with open(self._state_path, "r", encoding="utf-8") as file:
                loaded = json.load(file)
            if isinstance(loaded, dict):
                if loaded.get("policy_version") != self.BUDGET_POLICY_VERSION:
                    # Fix 4 이전 1,200/300/30,000 예산 누적을 새 240/40/6,000
                    # 정책에 그대로 대입하면 월말까지 AI가 전부 막힌다. 과거 값은
                    # 증거로 보존하고 새 정책 카운터만 한 번 초기화한다.
                    return {
                        "policy_version": self.BUDGET_POLICY_VERSION,
                        "daily": {},
                        "monthly": {},
                        "exchange_daily": {},
                        "legacy_snapshot": {
                            "daily": dict(loaded.get("daily", {}) or {}),
                            "monthly": dict(loaded.get("monthly", {}) or {}),
                            "exchange_daily": dict(loaded.get("exchange_daily", {}) or {}),
                        },
                    }
                return {
                    "policy_version": self.BUDGET_POLICY_VERSION,
                    "daily": dict(loaded.get("daily", {}) or {}),
                    "monthly": dict(loaded.get("monthly", {}) or {}),
                    "exchange_daily": dict(loaded.get("exchange_daily", {}) or {}),
                    "legacy_snapshot": dict(loaded.get("legacy_snapshot", {}) or {}),
                }
        except Exception:
            pass
        return {
            "policy_version": self.BUDGET_POLICY_VERSION,
            "daily": {}, "monthly": {}, "exchange_daily": {},
        }

    def _persist_counters(self) -> None:
        if not self._state_path:
            return
        try:
            directory = os.path.dirname(self._state_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            temporary = f"{self._state_path}.tmp"
            with open(temporary, "w", encoding="utf-8") as file:
                json.dump(self._counters, file, ensure_ascii=False, indent=2)
            os.replace(temporary, self._state_path)
        except Exception:
            pass

    @staticmethod
    def _candle_key(market_data: List[Any]) -> str:
        if not market_data:
            return ""
        timestamp = getattr(market_data[-1], "timestamp", "")
        if hasattr(timestamp, "isoformat"):
            return str(timestamp.isoformat())
        return str(timestamp or "")

    def _snapshot(
        self,
        market_data: List[Any],
        indicators: Any,
        market_state: Any,
        basic_signal: Dict[str, Any],
    ) -> Dict[str, Any]:
        close = _float(getattr(market_data[-1], "close", 0.0)) if market_data else 0.0
        rsi = _float(getattr(indicators, "rsi", 50.0), 50.0)
        macd_histogram = _float(getattr(indicators, "macd_histogram", 0.0))
        bb_position = _float(getattr(indicators, "bb_position", 0.5), 0.5)
        trend_data = getattr(market_state, "trend_data", None)
        trend = str(getattr(trend_data, "direction", "UNKNOWN") or "UNKNOWN")
        volatility = _float(getattr(market_state, "volatility", 0.0))
        return {
            "candle": self._candle_key(market_data),
            "close": close,
            "rsi": rsi,
            "rsi_bucket": int(rsi // 3),
            "macd_sign": 1 if macd_histogram > 0 else (-1 if macd_histogram < 0 else 0),
            "bb_bucket": int(max(0.0, min(1.0, bb_position)) * 10),
            "trend": trend,
            "volatility_bucket": round(volatility, 4),
            "signal": str(basic_signal.get("signal", "HOLD") or "HOLD").upper(),
        }

    @staticmethod
    def _fingerprint(snapshot: Dict[str, Any], price_change_bps: float) -> str:
        close = _float(snapshot.get("close"))
        ratio = max(price_change_bps, 0.1) / 10000.0
        price_bucket = (
            int(math.log(max(abs(close), 1e-12)) / math.log1p(ratio))
            if close
            else 0
        )
        parts = (
            price_bucket,
            snapshot.get("rsi_bucket"),
            snapshot.get("macd_sign"),
            snapshot.get("bb_bucket"),
            snapshot.get("trend"),
            snapshot.get("volatility_bucket"),
            snapshot.get("signal"),
        )
        return "|".join(str(part) for part in parts)

    def _budget_reason(self, exchange: str, timestamp: float, config: Dict[str, Any]) -> str:
        day_key, month_key = self._period_keys(timestamp)
        daily = int(self._counters["daily"].get(day_key, 0) or 0)
        monthly = int(self._counters["monthly"].get(month_key, 0) or 0)
        exchange_key = f"{day_key}:{exchange}"
        exchange_daily = int(self._counters["exchange_daily"].get(exchange_key, 0) or 0)
        daily_limit = max(1, int(config.get("max_daily_market_calls", 240) or 240))
        monthly_limit = max(1, int(config.get("max_monthly_market_calls", 6000) or 6000))
        exchange_limit = max(1, int(config.get("max_daily_calls_per_exchange", 40) or 40))
        if not bool(config.get("allow_high_cost_limits", False)):
            daily_limit = min(daily_limit, max(1, int(config.get("hard_max_daily_market_calls", 240) or 240)))
            monthly_limit = min(monthly_limit, max(1, int(config.get("hard_max_monthly_market_calls", 6000) or 6000)))
            exchange_limit = min(exchange_limit, max(1, int(config.get("hard_max_daily_calls_per_exchange", 40) or 40)))
        if daily >= daily_limit:
            return "daily_budget"
        if monthly >= monthly_limit:
            return "monthly_budget"
        if exchange_daily >= exchange_limit:
            return "exchange_daily_budget"
        return ""

    def _reserve_call(self, exchange: str, timestamp: float) -> None:
        day_key, month_key = self._period_keys(timestamp)
        exchange_key = f"{day_key}:{exchange}"
        self._counters["daily"][day_key] = int(self._counters["daily"].get(day_key, 0) or 0) + 1
        self._counters["monthly"][month_key] = int(self._counters["monthly"].get(month_key, 0) or 0) + 1
        self._counters["exchange_daily"][exchange_key] = (
            int(self._counters["exchange_daily"].get(exchange_key, 0) or 0) + 1
        )
        self._persist_counters()

    def decide(
        self,
        *,
        exchange: str,
        symbol: str,
        market_data: List[Any],
        indicators: Any,
        market_state: Any,
        basic_signal: Dict[str, Any],
    ) -> Dict[str, Any]:
        now = float(self._clock())
        normalized_exchange = str(exchange or "binance").strip().lower()
        normalized_symbol = str(symbol or "UNKNOWN").strip().upper()
        state_key = f"{normalized_exchange}:{normalized_symbol}"
        config = self._config()
        snapshot = self._snapshot(market_data, indicators, market_state, basic_signal)
        fingerprint = self._fingerprint(snapshot, _float(config.get("price_change_bps"), 15.0))

        with self._lock:
            if not bool(config.get("enabled", True)):
                return {"mode": "call", "reason": "cost_control_disabled", "fingerprint": fingerprint}

            cached = self._cache.get(state_key)
            cache_sec = max(0.0, _float(config.get("stable_state_cache_sec"), 900.0))
            if (
                cached
                and cached.get("fingerprint") == fingerprint
                and now - _float(cached.get("timestamp")) <= cache_sec
                and isinstance(cached.get("analysis"), dict)
            ):
                return {
                    "mode": "cache",
                    "reason": "same_market_state",
                    "fingerprint": fingerprint,
                    "analysis": dict(cached["analysis"]),
                }

            previous = self._snapshots.get(state_key)
            reasons: List[str] = []
            signal = str(snapshot.get("signal", "HOLD")).upper()
            if previous is None:
                reasons.append("initial_analysis")
            # LONG/SHORT 상태가 유지되는 동안 매 루프마다 호출하지 않고
            # 실제 후보 전환(HOLD->LONG, LONG->SHORT)만 이벤트로 취급한다.
            if signal in {"LONG", "SHORT"} and (
                previous is None or signal != str(previous.get("signal", "HOLD")).upper()
            ):
                reasons.append("local_trade_candidate")
            if previous:
                previous_close = _float(previous.get("close"))
                current_close = _float(snapshot.get("close"))
                price_bps = (
                    abs(current_close - previous_close) / abs(previous_close) * 10000.0
                    if previous_close
                    else 0.0
                )
                if price_bps >= _float(config.get("price_change_bps"), 15.0):
                    reasons.append("price_move")
                if snapshot.get("rsi_bucket") != previous.get("rsi_bucket"):
                    reasons.append("rsi_change")
                if snapshot.get("macd_sign") != previous.get("macd_sign"):
                    reasons.append("macd_cross")
                if snapshot.get("trend") != previous.get("trend"):
                    reasons.append("regime_change")

            rsi = _float(snapshot.get("rsi"), 50.0)
            low = _float(config.get("rsi_event_low"), 35.0)
            high = _float(config.get("rsi_event_high"), 65.0)
            previous_rsi = _float(previous.get("rsi"), 50.0) if previous else 50.0
            if (rsi <= low < previous_rsi) or (rsi >= high > previous_rsi):
                reasons.append("rsi_opportunity")

            last_call = _float(self._last_ai_call.get(state_key))
            exploration_sec = max(1.0, _float(config.get("exploration_interval_sec"), 900.0))
            if not last_call or now - last_call >= exploration_sec:
                reasons.append("exploration")

            # 미세 RSI/가격 버킷 변화가 10초 분석 루프마다 새 호출을 만들지
            # 않도록 하되, 후보 전환·MACD 교차·국면 전환은 즉시 보존한다.
            immediate = {"initial_analysis", "local_trade_candidate", "macd_cross", "regime_change", "rsi_opportunity"}
            minimum_interval = max(1.0, _float(config.get("minimum_event_interval_sec"), 300.0))
            if last_call and now - last_call < minimum_interval and not immediate.intersection(reasons):
                reasons = []

            self._snapshots[state_key] = snapshot
            if not reasons:
                return {
                    "mode": "local",
                    "reason": "stable_non_candidate",
                    "fingerprint": fingerprint,
                }

            # 거래소별 Analyzer/AIManager가 여러 인스턴스로 생성되어도 같은
            # 사용자 예산 파일을 예약 직전에 다시 읽어 전역 상한을 초과하지 않는다.
            with self._PROCESS_BUDGET_LOCK:
                self._counters = self._load_counters()
                budget_reason = self._budget_reason(normalized_exchange, now, config)
                if budget_reason:
                    return {
                        "mode": "local",
                        "reason": budget_reason,
                        "fingerprint": fingerprint,
                        "opportunity_reasons": reasons,
                    }
                self._reserve_call(normalized_exchange, now)
            self._last_ai_call[state_key] = now
            return {
                "mode": "call",
                "reason": ",".join(dict.fromkeys(reasons)),
                "fingerprint": fingerprint,
            }

    def store(
        self,
        *,
        exchange: str,
        symbol: str,
        fingerprint: str,
        analysis: Optional[Dict[str, Any]],
    ) -> None:
        if not isinstance(analysis, dict) or not analysis:
            return
        state_key = f"{str(exchange or 'binance').strip().lower()}:{str(symbol).strip().upper()}"
        with self._lock:
            self._cache[state_key] = {
                "fingerprint": fingerprint,
                "timestamp": float(self._clock()),
                "analysis": dict(analysis),
            }
            max_entries = max(10, int(self._config().get("max_cache_entries", 1000) or 1000))
            if len(self._cache) > max_entries:
                oldest = min(self._cache, key=lambda key: _float(self._cache[key].get("timestamp")))
                self._cache.pop(oldest, None)
