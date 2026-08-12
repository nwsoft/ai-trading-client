#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""모든 자동 AI 역할 호출에 적용되는 영속 비용 거버너.

시장 분석기의 개별 캐시를 우회하는 패턴/진입/포지션 크기 호출까지 같은
예산 원장에 기록한다. 사용자 질문은 interactive 경로이므로 자동매매 예산과
분리한다.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class AIRequestGovernor:
    _PROCESS_BUDGET_LOCK = threading.RLock()
    DEFAULT_ROLE_LIMITS = {
        "signal_analysis": 240,
        "pattern_similarity": 40,
        "pre_entry": 40,
        "position_sizing": 40,
        "loss_analysis": 50,
        "profit_analysis": 50,
        "daily_report": 5,
        "diagnosis": 10,
        "parameter_optimization": 10,
    }

    def __init__(
        self,
        settings: Optional[Dict[str, Any]] = None,
        *,
        state_path: Optional[str] = None,
        clock=time.time,
    ) -> None:
        self.settings = settings or {}
        self.clock = clock
        self.state_path = state_path or self._default_state_path()
        self._lock = threading.RLock()
        self._state = self._load()

    @staticmethod
    def _default_state_path() -> str:
        try:
            from path_utils import get_app_data_dir

            return os.path.join(get_app_data_dir(), "ai_provider_call_budget.json")
        except Exception:
            return ""

    def _config(self) -> Dict[str, Any]:
        cost = self.settings.get("ai_cost_control", {})
        return dict(cost) if isinstance(cost, dict) else {}

    def _load(self) -> Dict[str, Any]:
        empty = {"daily": {}, "monthly": {}, "role_daily": {}, "denied_daily": {}}
        if not self.state_path or not os.path.exists(self.state_path):
            return empty
        try:
            with open(self.state_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            if isinstance(data, dict):
                return {key: dict(data.get(key, {}) or {}) for key in empty}
        except Exception:
            pass
        return empty

    def _persist(self) -> None:
        if not self.state_path:
            return
        try:
            directory = os.path.dirname(self.state_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            temporary = f"{self.state_path}.tmp"
            with open(temporary, "w", encoding="utf-8") as file:
                json.dump(self._state, file, ensure_ascii=False, indent=2)
            os.replace(temporary, self.state_path)
        except Exception:
            pass

    def reserve(self, role: str) -> Dict[str, Any]:
        """자동 호출 1회를 원자적으로 예약한다. 차단 시 제공사를 호출하지 않는다."""
        now = float(self.clock())
        stamp = datetime.fromtimestamp(now, tz=timezone.utc)
        day = stamp.strftime("%Y-%m-%d")
        month = stamp.strftime("%Y-%m")
        normalized_role = str(role or "unknown").strip().lower()
        role_key = f"{day}:{normalized_role}"
        cfg = self._config()
        enabled = bool(cfg.get("provider_budget_enabled", True))
        if not enabled:
            return {"allowed": True, "reason": "provider_budget_disabled"}

        daily_limit = max(1, int(cfg.get("max_daily_automatic_ai_calls", 360) or 360))
        monthly_limit = max(1, int(cfg.get("max_monthly_automatic_ai_calls", 9000) or 9000))
        configured_roles = cfg.get("max_daily_ai_calls_by_role", {})
        role_limits = dict(self.DEFAULT_ROLE_LIMITS)
        if isinstance(configured_roles, dict):
            role_limits.update(configured_roles)
        role_limit = max(1, int(role_limits.get(normalized_role, 60) or 60))

        with self._lock, self._PROCESS_BUDGET_LOCK:
            # 역할별 client가 여러 개여도 같은 사용자 원장을 예약 직전에
            # 다시 읽어 lost update와 한도 초과를 막는다.
            self._state = self._load()
            daily = int(self._state["daily"].get(day, 0) or 0)
            monthly = int(self._state["monthly"].get(month, 0) or 0)
            role_daily = int(self._state["role_daily"].get(role_key, 0) or 0)
            reason = ""
            if daily >= daily_limit:
                reason = "automatic_daily_budget"
            elif monthly >= monthly_limit:
                reason = "automatic_monthly_budget"
            elif role_daily >= role_limit:
                reason = "role_daily_budget"
            if reason:
                denied_key = f"{day}:{normalized_role}:{reason}"
                self._state["denied_daily"][denied_key] = int(
                    self._state["denied_daily"].get(denied_key, 0) or 0
                ) + 1
                self._persist()
                return {
                    "allowed": False,
                    "reason": reason,
                    "role": normalized_role,
                    "daily": daily,
                    "role_daily": role_daily,
                }

            self._state["daily"][day] = daily + 1
            self._state["monthly"][month] = monthly + 1
            self._state["role_daily"][role_key] = role_daily + 1
            self._persist()
            return {
                "allowed": True,
                "reason": "reserved",
                "role": normalized_role,
                "daily": daily + 1,
                "role_daily": role_daily + 1,
            }
