#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 커스텀 전략의 구조화/XAI/승인/실행검증/롤백 상태머신."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from .custom_strategy_advisor import build_improvement_advice, build_strategy_guidance
from .declarative_strategy_engine import DeclarativeStrategyEngine


class CustomStrategyPipeline:
    """사용자 전략이 승인 없이 실거래에 반영되지 않도록 제어한다."""

    MAX_VERSIONS = 10
    REQUIRED_RULES = (
        "entry",
        "exit",
        "stop_loss",
        "take_profit",
        "position_size",
        "market_conditions",
    )
    FORBIDDEN_KEYS = {
        "withdraw",
        "withdrawal",
        "withdraw_address",
        "withdraw_api",
        "transfer_out",
        "출금",
    }
    IMMUTABLE_GUARDRAILS = (
        "max_loss",
        "position_limit",
        "concentration_limit",
        "market_risk",
    )

    def __init__(
        self,
        storage_path: Optional[str] = None,
        *,
        max_versions: int = MAX_VERSIONS,
        min_paper_trades: int = 3,
        logger: Optional[logging.Logger] = None,
    ):
        self.storage_path = Path(storage_path) if storage_path else None
        self.max_versions = max(1, min(int(max_versions), self.MAX_VERSIONS))
        self.min_paper_trades = max(1, int(min_paper_trades))
        self.logger = logger or logging.getLogger(__name__)
        self.strategies: Dict[str, List[Dict[str, Any]]] = {}
        self.active_versions: Dict[str, str] = {}
        self._load()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _contains_forbidden_key(cls, value: Any) -> bool:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = str(key or "").strip().lower()
                if normalized in cls.FORBIDDEN_KEYS or "withdraw" in normalized or "출금" in normalized:
                    return True
                if cls._contains_forbidden_key(nested):
                    return True
        elif isinstance(value, (list, tuple)):
            return any(cls._contains_forbidden_key(item) for item in value)
        return False

    @staticmethod
    def _is_missing(value: Any) -> bool:
        return value is None or value == "" or value == [] or value == {}

    def _load(self) -> None:
        if self.storage_path is None or not self.storage_path.exists():
            return
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
            self.strategies = dict(payload.get("strategies", {}) or {})
            self.active_versions = dict(payload.get("active_versions", {}) or {})
        except Exception as exc:
            self.logger.warning(f"커스텀 전략 저장소 로드 실패: {exc}")

    def _save(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.storage_path.with_suffix(self.storage_path.suffix + ".tmp")
        payload = {
            "schema_version": 1,
            "strategies": self.strategies,
            "active_versions": self.active_versions,
            "updated_at": self._now(),
        }
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.storage_path)

    def _version_number(self, strategy_key: str) -> int:
        versions = self.strategies.get(strategy_key, [])
        return max((int(item.get("version", 0) or 0) for item in versions), default=0) + 1

    def _find(self, strategy_key: str, version_id: str) -> Dict[str, Any]:
        for item in self.strategies.get(strategy_key, []):
            if item.get("version_id") == version_id:
                return item
        raise ValueError(f"전략 버전을 찾을 수 없습니다: {strategy_key}/{version_id}")

    def _previous(self, strategy_key: str) -> Optional[Dict[str, Any]]:
        versions = self.strategies.get(strategy_key, [])
        return versions[-1] if versions else None

    @staticmethod
    def _impact_summary(previous: Optional[Dict[str, Any]], rules: Dict[str, Any]) -> Dict[str, Any]:
        old_rules = dict((previous or {}).get("rules", {}) or {})
        changed = sorted({key for key in set(old_rules) | set(rules) if old_rules.get(key) != rules.get(key)})
        return {
            "changed_rules": changed,
            "entry_frequency": "변경 가능 - 모의거래에서 수치 확정",
            "stop_frequency": "변경 가능 - 모의거래에서 수치 확정",
            "holding_time": "변경 가능 - 모의거래에서 수치 확정",
            "expected_value": "백테스트만으로 확정 불가",
        }

    def submit(
        self,
        *,
        name: str,
        rules: Dict[str, Any],
        source_kind: str = "text",
        source_reference: str = "",
        strategy_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not isinstance(rules, dict):
            raise ValueError("전략 규칙은 dict 형식이어야 합니다.")
        if self._contains_forbidden_key(rules):
            raise ValueError("출금/외부송금 규칙은 보안·법률 정책상 지원하지 않습니다.")

        key = strategy_key or f"strategy_{uuid4().hex[:10]}"
        guidance = build_strategy_guidance(rules, self.REQUIRED_RULES)
        missing = list(guidance["missing_conditions"])
        executable_validation = DeclarativeStrategyEngine.validate_rule_spec(rules)
        if not executable_validation["valid"]:
            missing.append("unsupported_executable_conditions")
            guidance["missing_conditions"] = list(missing)
            guidance["complete"] = False
            guidance["unsupported_conditions"] = list(executable_validation["errors"])
        previous = self._previous(key)
        status = "needs_clarification" if missing else "analyzed"
        version = {
            "strategy_key": key,
            "version_id": f"{key}_v{self._version_number(key)}_{uuid4().hex[:6]}",
            "version": self._version_number(key),
            "name": str(name or "이름 없는 전략").strip(),
            "source_kind": str(source_kind or "text").strip().lower(),
            "source_reference": str(source_reference or "").strip(),
            "rules": deepcopy(rules),
            "status": status,
            "missing_conditions": missing,
            "guidance": guidance,
            "xai": {
                "summary": (
                    f"AI가 누락 조건 {len(missing)}개를 찾았습니다. 안내 질문에 답하면 다음 버전에서 분석을 완료할 수 있습니다."
                    if missing else
                    "전략 규칙 구조화와 위험 설계 검토가 완료됐으며 승인 전에는 실행되지 않습니다."
                ),
                "impact": self._impact_summary(previous, rules),
                "risks": [
                    "체결·수수료·펀딩비·슬리피지·유동성은 실시간 품질에 따라 달라집니다.",
                    "백테스트는 보조 검증이며 성과를 보장하지 않습니다.",
                ],
                "guardrails": list(self.IMMUTABLE_GUARDRAILS),
            },
            "approval": None,
            "paper_validation": None,
            "execution_validation": None,
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self.strategies.setdefault(key, []).append(version)
        self._trim(key)
        self._save()
        return deepcopy(version)

    def clarify(self, strategy_key: str, version_id: str, answers: Dict[str, Any]) -> Dict[str, Any]:
        version = self._find(strategy_key, version_id)
        if version.get("status") != "needs_clarification":
            raise ValueError("재확인이 필요한 버전이 아닙니다.")
        version["rules"].update(deepcopy(answers or {}))
        guidance = build_strategy_guidance(version["rules"], self.REQUIRED_RULES)
        missing = list(guidance["missing_conditions"])
        executable_validation = DeclarativeStrategyEngine.validate_rule_spec(version["rules"])
        if not executable_validation["valid"]:
            missing.append("unsupported_executable_conditions")
            guidance["missing_conditions"] = list(missing)
            guidance["complete"] = False
            guidance["unsupported_conditions"] = list(executable_validation["errors"])
        version["missing_conditions"] = missing
        version["guidance"] = guidance
        version.setdefault("xai", {})["summary"] = (
            f"AI가 아직 누락 조건 {len(missing)}개를 확인했습니다."
            if missing else
            "사용자 답변으로 전략 조건이 완성됐으며 승인 전에는 실행되지 않습니다."
        )
        version["status"] = "needs_clarification" if missing else "analyzed"
        version["updated_at"] = self._now()
        self._save()
        return deepcopy(version)

    def approve(self, strategy_key: str, version_id: str, *, approved_by: str) -> Dict[str, Any]:
        version = self._find(strategy_key, version_id)
        if version.get("status") != "analyzed":
            raise ValueError("누락 조건 확인과 XAI 분석 완료 후에만 승인할 수 있습니다.")
        if not str(approved_by or "").strip():
            raise ValueError("승인 주체가 필요합니다.")
        version["approval"] = {"approved_by": str(approved_by).strip(), "approved_at": self._now()}
        version["status"] = "approved"
        version["updated_at"] = self._now()
        self._save()
        return deepcopy(version)

    def record_paper_validation(
        self,
        strategy_key: str,
        version_id: str,
        *,
        trades: int,
        guardrail_violations: int = 0,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        version = self._find(strategy_key, version_id)
        if version.get("status") not in {"approved", "paper_rejected", "paper_validated"}:
            raise ValueError("사용자 승인 후에만 모의거래 검증을 기록할 수 있습니다.")
        passed = int(trades) >= self.min_paper_trades and int(guardrail_violations) == 0
        version["paper_validation"] = {
            "passed": passed,
            "trades": int(trades),
            "guardrail_violations": int(guardrail_violations),
            "metrics": deepcopy(metrics or {}),
            "recorded_at": self._now(),
            "note": "백테스트는 보조 검증이며 모의거래 통과를 대체하지 않음",
        }
        version["status"] = "paper_validated" if passed else "paper_rejected"
        version["updated_at"] = self._now()
        self._save()
        return deepcopy(version)

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
        """관찰학습/과거재생/제한운용의 실제 결과를 승인 버전에 연결한다."""
        version = self._find(strategy_key, version_id)
        if version.get("status") not in {"approved", "execution_rejected", "execution_validated"}:
            raise ValueError("사용자 승인 후에만 실행 검증을 기록할 수 있습니다.")
        allowed_modes = {"historical_replay", "live_observation", "limited_live"}
        normalized_mode = str(mode or "live_observation").lower()
        if normalized_mode not in allowed_modes:
            raise ValueError(f"지원하지 않는 실행 검증 방식입니다: {normalized_mode}")
        passed = int(decisions) >= self.min_paper_trades and int(guardrail_violations) == 0
        version["execution_validation"] = {
            "passed": passed,
            "decisions": int(decisions),
            "guardrail_violations": int(guardrail_violations),
            "metrics": deepcopy(metrics or {}),
            "mode": normalized_mode,
            "recorded_at": self._now(),
            "note": "백테스트 단독 근거가 아닌 관찰/제한운용의 체결·비용·PnL 품질을 포함",
        }
        version["improvement_advice"] = build_improvement_advice(metrics)
        version["status"] = "execution_validated" if passed else "execution_rejected"
        version["updated_at"] = self._now()
        self._save()
        return deepcopy(version)

    def activate(
        self,
        strategy_key: str,
        version_id: str,
        *,
        live_confirmation: bool,
        operation_mode: str = "standard",
        guardrail_check: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Dict[str, Any]:
        version = self._find(strategy_key, version_id)
        mode = str(operation_mode or "standard").strip().lower()
        if mode not in {"standard", "limited_live"}:
            raise ValueError(f"지원하지 않는 전략 운용 방식입니다: {mode}")
        previous_status = str(version.get("status") or "")
        if mode == "standard":
            if previous_status not in {"paper_validated", "execution_validated"}:
                raise ValueError("일반 운용은 실행 검증 통과 후에만 적용할 수 있습니다.")
        else:
            if previous_status not in {"execution_rejected", "execution_validated"}:
                raise ValueError("제한 운용은 자동 실행검증을 먼저 완료한 뒤 선택할 수 있습니다.")
            if not version.get("execution_validation"):
                raise ValueError("제한 운용 전에 자동 실행검증 결과가 필요합니다.")
        if live_confirmation is not True:
            raise ValueError("자동매매 전환에 대한 사용자의 최종 확인이 필요합니다.")
        if guardrail_check is not None:
            candidate = deepcopy(version)
            candidate["operation_mode"] = mode
            result = guardrail_check(candidate)
            allowed = bool(result.get("allowed", False)) if isinstance(result, dict) else bool(result)
            if not allowed:
                raise ValueError("공통 가드레일 검증에서 적용이 차단됐습니다.")
        previous_id = self.active_versions.get(strategy_key)
        if previous_id:
            try:
                previous = self._find(strategy_key, previous_id)
                if previous.get("status") == "active":
                    previous["status"] = "superseded"
            except ValueError:
                pass
        version["status"] = "active"
        version["operation_mode"] = mode
        version["pre_activation_status"] = previous_status
        version["activated_at"] = self._now()
        version["updated_at"] = self._now()
        self.active_versions[strategy_key] = version_id
        self._save()
        return deepcopy(version)

    def rollback(self, strategy_key: str, target_version_id: str, *, approved_by: str) -> Dict[str, Any]:
        target = self._find(strategy_key, target_version_id)
        paper_validation = target.get("paper_validation") or {}
        execution_validation = target.get("execution_validation") or {}
        if not paper_validation.get("passed", False) and not execution_validation.get("passed", False):
            raise ValueError("실행 검증 통과 이력이 있는 버전으로만 롤백할 수 있습니다.")
        current_id = self.active_versions.get(strategy_key)
        if current_id:
            try:
                current = self._find(strategy_key, current_id)
                current["status"] = "rolled_back"
                current["updated_at"] = self._now()
            except ValueError:
                pass
        target["status"] = "active"
        target["rollback"] = {"approved_by": str(approved_by or "").strip(), "at": self._now()}
        target["updated_at"] = self._now()
        self.active_versions[strategy_key] = target_version_id
        self._save()
        return deepcopy(target)

    def deactivate(self, strategy_key: str, version_id: str, *, approved_by: str) -> Dict[str, Any]:
        """활성 전략을 실행검증 완료 상태로 되돌려 전략 풀에서 제거한다."""
        version = self._find(strategy_key, version_id)
        if version.get("status") != "active":
            raise ValueError("현재 적용 중인 전략만 해제할 수 있습니다.")
        previous_status = str(version.get("pre_activation_status") or "execution_validated")
        version["status"] = previous_status if previous_status in {
            "paper_validated", "execution_validated", "execution_rejected"
        } else "execution_validated"
        version["last_operation_mode"] = str(version.get("operation_mode") or "standard")
        version["deactivated"] = {"approved_by": str(approved_by or "").strip(), "at": self._now()}
        version["updated_at"] = self._now()
        if self.active_versions.get(strategy_key) == version_id:
            self.active_versions.pop(strategy_key, None)
        self._save()
        return deepcopy(version)

    def list_versions(self, strategy_key: str) -> List[Dict[str, Any]]:
        return deepcopy(self.strategies.get(strategy_key, []))

    def _trim(self, strategy_key: str) -> None:
        versions = self.strategies.get(strategy_key, [])
        while len(versions) > self.max_versions:
            active_id = self.active_versions.get(strategy_key)
            removable = next((idx for idx, item in enumerate(versions) if item.get("version_id") != active_id), None)
            if removable is None:
                break
            versions.pop(removable)
