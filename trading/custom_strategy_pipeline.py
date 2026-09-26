#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 커스텀 전략의 구조화/XAI/승인/실행검증/롤백 상태머신."""

from __future__ import annotations

import json
import logging
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from .custom_strategy_advisor import build_improvement_advice, build_strategy_guidance
from .custom_strategy_mentor import build_version_diff
from .custom_strategy_runtime import (
    ExitRateContractError,
    normalize_engine_settings,
    validate_stored_exit_rates,
)
from .declarative_strategy_engine import DeclarativeStrategyEngine
from .noah_strategy_ir import NoahStrategyIR


MARKET_REGIME_ALIASES = {
    "all": "all",
    "any": "all",
    "모든 시장상황": "all",
    "모든 시장 상황": "all",
    "잘 모르겠어요": "all",
    "noahai 판단": "all",
    "bull": "bull",
    "bullish": "bull",
    "uptrend": "bull",
    "상승": "bull",
    "상승장": "bull",
    "상승 추세": "bull",
    "bear": "bear",
    "bearish": "bear",
    "downtrend": "bear",
    "하락": "bear",
    "하락장": "bear",
    "하락 추세": "bear",
    "range": "range",
    "sideways": "range",
    "normal": "range",
    "횡보": "range",
    "횡보장": "range",
    "volatile": "volatile",
    "high_vol": "volatile",
    "high_volatility": "volatile",
    "고변동": "volatile",
    "고변동성": "volatile",
    "calm": "calm",
    "low_vol": "calm",
    "low_volatility": "calm",
    "저변동": "calm",
    "저변동성": "calm",
}

REGIME_SCOPE_ALIASES = {
    "market": "market",
    "전체 시장": "market",
    "전체 시장 기준": "market",
    "전체 시장 기준 (권장)": "market",
    "symbol": "symbol",
    "종목": "symbol",
    "종목별 기준": "symbol",
    "both": "both",
    "전체+종목 모두": "both",
    "전체 시장과 종목 모두": "both",
    "none": "none",
    "사용 안 함": "none",
}


def normalize_declared_market_regimes(
    value: Any,
    *,
    fallback_conditions: Any = None,
) -> List[str]:
    """Convert UI/legacy market labels into the runtime regime contract.

    Unknown prose is never guessed from LONG/SHORT direction. When no explicit
    supported regime exists, NoahAI's current market judgement remains active
    through the unrestricted ``all`` value.
    """
    raw = value
    if raw in (None, "", [], {}):
        raw = fallback_conditions
    values = raw if isinstance(raw, (list, tuple, set)) else [raw]
    normalized: List[str] = []
    for item in values:
        key = str(item or "").strip().lower()
        mapped = MARKET_REGIME_ALIASES.get(key)
        if mapped and mapped not in normalized:
            normalized.append(mapped)
    if not normalized or "all" in normalized:
        return ["all"]
    return normalized


def normalize_declared_regime_scope(value: Any, *, default: str = "market") -> str:
    key = str(value or default).strip().lower()
    return REGIME_SCOPE_ALIASES.get(key, default)


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
        "user_approval_and_live_permission",
        "daily_loss_stop",
        "position_and_concentration_limit",
        "exchange_order_constraints",
        "tp_sl_protection",
        "duplicate_order_prevention",
        "position_reconciliation",
        "emergency_stop",
    )
    RISK_POLICY_PRESETS = {"conservative", "standard", "active", "custom"}
    FORBIDDEN_GUARDRAIL_CONTROLS = {
        "disable_guardrails", "guardrails_off", "disable_stop_loss",
        "disable_daily_loss_stop", "ignore_order_constraints",
        "skip_position_reconciliation", "disable_emergency_stop",
    }

    @classmethod
    def _find_forbidden_guardrail_control(cls, value: Any) -> Optional[str]:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = str(key or "").strip().lower()
                if normalized in cls.FORBIDDEN_GUARDRAIL_CONTROLS:
                    return normalized
                found = cls._find_forbidden_guardrail_control(nested)
                if found:
                    return found
        elif isinstance(value, (list, tuple)):
            for nested in value:
                found = cls._find_forbidden_guardrail_control(nested)
                if found:
                    return found
        return None

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
        # PAPER 전진검증은 LIVE 활성화와 다른 상태다. 과거에는 검증을
        # 통과해야만 active_versions에 들어가는데, PAPER 결과를 만들려면
        # active pool에 먼저 들어가야 하는 순환 의존이 있었다.
        self.paper_versions: Dict[str, str] = {}
        self.deletion_history: List[Dict[str, Any]] = []
        self.archived_versions: Dict[str, List[Dict[str, Any]]] = {}
        self._load()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _paper_time(value: Any) -> Optional[datetime]:
        try:
            parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def paper_observation_windows(cls, version: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return normalized active-time windows for one PAPER attempt.

        v3.9.1.22 and older stored only one start/stop pair. Keep that pair as
        the first compatible window so an upgrade never drops prior evidence.
        """
        windows: List[Dict[str, Any]] = []
        for raw in list(version.get("paper_observation_windows") or []):
            if not isinstance(raw, dict) or cls._paper_time(raw.get("started_at")) is None:
                continue
            windows.append({
                "started_at": str(raw.get("started_at")),
                "stopped_at": str(raw.get("stopped_at") or "") or None,
            })
        if windows:
            # The single start/stop fields were the v3.9.1.22 public
            # contract. During migration they remain authoritative for the
            # first window, including stores written by an older runtime just
            # before this client starts.
            legacy_started = str(version.get("paper_observation_started_at") or "")
            if cls._paper_time(legacy_started) is not None:
                windows[0]["started_at"] = legacy_started
            return windows
        started = str(version.get("paper_observation_started_at") or "")
        if not started or cls._paper_time(started) is None:
            return []
        stopped = str(version.get("paper_observation_stopped_at") or "")
        return [{"started_at": started, "stopped_at": stopped or None}]

    @classmethod
    def paper_observation_elapsed_seconds(
        cls, version: Dict[str, Any], *, now: Optional[datetime] = None,
    ) -> float:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        elapsed = 0.0
        for window in cls.paper_observation_windows(version):
            started = cls._paper_time(window.get("started_at"))
            stopped = cls._paper_time(window.get("stopped_at")) or current
            if started is not None and stopped >= started:
                elapsed += (stopped - started).total_seconds()
        return max(0.0, elapsed)

    @classmethod
    def paper_observation_contains(cls, version: Dict[str, Any], value: Any) -> bool:
        target = cls._paper_time(value)
        windows = cls.paper_observation_windows(version)
        if target is None:
            return False
        if not windows:
            return True
        for window in windows:
            started = cls._paper_time(window.get("started_at"))
            stopped = cls._paper_time(window.get("stopped_at"))
            if started is not None and target >= started and (stopped is None or target <= stopped):
                return True
        return False

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

    @classmethod
    def _normalize_strategy_rules(cls, rules: Dict[str, Any]) -> Dict[str, Any]:
        """Level 4 운용 정책을 실행 위험 계약으로 정규화한다.

        Level 4는 위험예산·최대비중·레버리지 상한·국면 이탈 대응만
        조절한다. 실행 권한과 하드 가드레일을 끄는 필드는 저장 자체를
        차단한다. 3.9.1.15 이전 Web UI의 risk_budget 필드는 새 버전
        저장 시 risk_model로 명시적 정규화한다.
        """
        normalized = deepcopy(dict(rules or {}))
        forbidden_control = cls._find_forbidden_guardrail_control(normalized)
        if forbidden_control:
            raise ValueError(
                f"하드 가드레일 해제 설정은 허용하지 않습니다: {forbidden_control}"
            )

        legacy = dict(normalized.get("risk_budget") or {})
        model = dict(normalized.get("risk_model") or {})
        if not model and legacy:
            model = {
                "risk_per_trade_percent": legacy.get("risk_per_trade_percent"),
                "max_margin_usage_percent": legacy.get(
                    "max_margin_usage_percent", legacy.get("max_margin_percent")
                ),
                "max_leverage": legacy.get("max_leverage", legacy.get("leverage_cap")),
            }
        if model:
            limits = {
                "risk_per_trade_percent": (0.05, 2.0),
                "max_margin_usage_percent": (1.0, 30.0),
                "max_leverage": (1.0, 5.0),
                "max_notional_percent": (1.0, 100.0),
                "max_concurrent_positions": (1.0, 10.0),
            }
            checked: Dict[str, Any] = {}
            for key, value in model.items():
                if key not in limits and key not in {"stop_mode", "volatility_multiplier"}:
                    continue
                if key in limits:
                    try:
                        number = float(value)
                    except (TypeError, ValueError) as exc:
                        raise ValueError(f"위험 정책 값은 숫자여야 합니다: {key}") from exc
                    lower, upper = limits[key]
                    if not lower <= number <= upper:
                        raise ValueError(
                            f"위험 정책 허용 범위 위반: {key}={number} "
                            f"(허용 {lower}~{upper})"
                        )
                    checked[key] = int(number) if key in {"max_leverage", "max_concurrent_positions"} else number
                else:
                    checked[key] = value
            normalized["risk_model"] = checked
        normalized.pop("risk_budget", None)

        preset = str(normalized.get("risk_policy_preset") or "custom").strip().lower()
        if preset not in cls.RISK_POLICY_PRESETS:
            raise ValueError("전문가 운용 정책은 안정형·표준형·적극형 또는 사용자 조정값만 허용합니다.")
        normalized["risk_policy_preset"] = preset

        transition = str(normalized.get("regime_transition") or "").strip().lower()
        if not transition:
            transition = (
                "pause"
                if str(normalized.get("conflict_fallback") or "") == "커스텀 신규 진입 일시정지"
                else "delegate_to_noah"
            )
        if transition not in {"delegate_to_noah", "pause"}:
            raise ValueError("국면 이탈 대응은 기본 NoahAI 위임 또는 커스텀 신규 진입 일시정지만 허용합니다.")
        normalized["regime_transition"] = transition
        normalized["market_regimes"] = normalize_declared_market_regimes(
            normalized.get("market_regimes"),
            fallback_conditions=normalized.get("market_conditions"),
        )
        normalized["regime_scope"] = normalize_declared_regime_scope(
            normalized.get("regime_scope")
        )
        signal_mode = str(normalized.get("signal_mode") or "confirm").strip().lower()
        if signal_mode not in {"confirm", "independent"}:
            raise ValueError("전략 역할은 NoahAI 후보 확인(confirm) 또는 독립 신호(independent)만 허용합니다.")
        normalized["signal_mode"] = signal_mode
        engine_settings = dict(normalized.get("engine_settings") or {})

        def _explicit_percent_point(value: Any) -> float | None:
            matched = re.fullmatch(
                r"\s*(\d+(?:\.\d+)?)\s*%\s*",
                str(value or ""),
            )
            return float(matched.group(1)) if matched else None

        # 구형/직접 입력 전략의 사람이 읽는 `1%`·`2%`는 단위까지
        # 명시돼 있으므로 손실 없이 실행 계약으로 승격할 수 있다. 숫자만
        # 있거나 한쪽만 있으면 추정하지 않고 readiness 단계에서 차단한다.
        if not any(key in engine_settings for key in ("tp_percent", "sl_percent")):
            explicit_tp = _explicit_percent_point(normalized.get("take_profit"))
            explicit_sl = _explicit_percent_point(normalized.get("stop_loss"))
            if explicit_tp is not None and explicit_sl is not None:
                engine_settings.update({
                    "_unit": "percent_points",
                    "tp_percent": explicit_tp,
                    "sl_percent": explicit_sl,
                })
                normalized["engine_settings"] = engine_settings

        raw_exit_policy = normalized.get("exit_policy")
        if isinstance(raw_exit_policy, dict):
            exit_policy_mode = str(raw_exit_policy.get("mode") or "").strip().lower()
        else:
            exit_policy_mode = str(raw_exit_policy or "").strip().lower()
        has_declared_exit_rates = any(
            engine_settings.get(key) is not None for key in ("tp_percent", "sl_percent")
        )
        if not exit_policy_mode:
            exit_policy_mode = (
                "strategy_owned"
                if has_declared_exit_rates or signal_mode == "independent"
                else "inherit_noah_base"
            )
        if exit_policy_mode not in {"strategy_owned", "inherit_noah_base"}:
            raise ValueError("청산 정책은 전략 자체 TP/SL 또는 NoahAI 기본 청산정책 상속만 허용합니다.")
        if signal_mode == "independent" and exit_policy_mode != "strategy_owned":
            raise ValueError("독립 전략은 자체 TP/SL 청산정책이 필요합니다.")
        normalized["exit_policy"] = {"mode": exit_policy_mode}
        return normalized

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
            self.paper_versions = dict(payload.get("paper_versions", {}) or {})
            self.deletion_history = list(payload.get("deletion_history", []) or [])[-100:]
            self.archived_versions = dict(payload.get('archived_versions', {}) or {})
            if self._reconcile_runtime_version_maps():
                self._save()
            try:
                os.chmod(self.storage_path, 0o600)
            except OSError:
                pass
        except Exception as exc:
            self.logger.warning(f"커스텀 전략 저장소 로드 실패: {exc}")

    def _reconcile_runtime_version_maps(self) -> bool:
        """Repair legacy split-brain lifecycle state using maps as truth.

        A version status is descriptive.  The active/paper maps are the actual
        execution grants.  Older auto-sync code could set a stopped version
        back to ``paper_observing`` even though its map entry had been removed.
        Such a version must never re-enter the runtime pool on restart.
        """
        changed = False
        known_versions = {
            (str(key), str(item.get("version_id") or "")): item
            for key, versions in self.strategies.items()
            for item in list(versions or [])
            if isinstance(item, dict) and item.get("version_id")
        }
        for mapping_name, mapping in (
            ("active_versions", self.active_versions),
            ("paper_versions", self.paper_versions),
        ):
            for key, version_id in list(mapping.items()):
                if (str(key), str(version_id)) not in known_versions:
                    mapping.pop(key, None)
                    changed = True
                    self.logger.warning(
                        "존재하지 않는 전략 실행 권한을 제거했습니다: %s %s/%s",
                        mapping_name, key, version_id,
                    )

        repaired_at = self._now()
        for (key, version_id), version in known_versions.items():
            status = str(version.get("status") or "")
            paper_granted = self.paper_versions.get(key) == version_id
            active_granted = self.active_versions.get(key) == version_id
            legacy_paused = bool(
                not paper_granted
                and not active_granted
                and version.get("paper_observation_started_at")
                and version.get("paper_observation_stopped_at")
                and not bool((version.get("paper_validation") or {}).get("passed", False))
                and status in {
                    "approved", "execution_rejected", "execution_validated", "paper_rejected",
                }
            )
            if active_granted and paper_granted:
                self.paper_versions.pop(key, None)
                paper_granted = False
                changed = True
            if legacy_paused:
                version["status"] = "paper_paused"
                version["paper_observation_windows"] = self.paper_observation_windows(version)
                version.setdefault("paper_observation_previous_status", status or "approved")
                version["updated_at"] = repaired_at
                changed = True
            elif active_granted and status != "active":
                version["pre_activation_status"] = status or "execution_validated"
                version["status"] = "active"
                version["updated_at"] = repaired_at
                changed = True
            elif paper_granted and status != "paper_observing":
                # PAPER grant가 남아 있으면 해당 grant가 설명용 status보다
                # 우선한다. 구형 저장본이 active status와 PAPER map을 함께
                # 가진 경우에도 한 번의 로드로 올바르게 복구한다.
                version["paper_observation_previous_status"] = (
                    str(version.get("pre_activation_status") or status or "approved")
                )
                version["status"] = "paper_observing"
                version.setdefault("paper_observation_started_at", repaired_at)
                version["updated_at"] = repaired_at
                changed = True
            elif status == "active" and not active_granted:
                previous_status = str(version.get("pre_activation_status") or "")
                version["status"] = previous_status if previous_status in {
                    "paper_validated", "execution_validated", "execution_rejected",
                } else "execution_validated"
                version.setdefault("promotion_history", []).append({
                    "event": "active_version_split_brain_repaired",
                    "at": repaired_at,
                    "auto_promoted": False,
                })
                version["updated_at"] = repaired_at
                changed = True
            elif status == "paper_observing" and not paper_granted:
                previous_status = str(version.get("paper_observation_previous_status") or "")
                version["status"] = "paper_paused"
                version.setdefault("paper_observation_stopped_at", repaired_at)
                windows = self.paper_observation_windows(version)
                if windows and not windows[-1].get("stopped_at"):
                    windows[-1]["stopped_at"] = version["paper_observation_stopped_at"]
                version["paper_observation_windows"] = windows
                version.setdefault("paper_observation_previous_status", previous_status or "approved")
                version.setdefault("promotion_history", []).append({
                    "event": "paper_observation_split_brain_repaired",
                    "at": repaired_at,
                    "auto_promoted": False,
                })
                version["updated_at"] = repaired_at
                changed = True
        return changed

    def _save(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.storage_path.with_suffix(self.storage_path.suffix + ".tmp")
        payload = {
            # v6 adds resumable PAPER observation windows and non-destructive
            # attempt history. Older stores remain readable through _load().
            "schema_version": 6,
            "strategies": self.strategies,
            "active_versions": self.active_versions,
            "paper_versions": self.paper_versions,
            "deletion_history": self.deletion_history[-100:],
            "archived_versions": self.archived_versions,
            "updated_at": self._now(),
        }
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(temp_path, 0o600)
        except OSError:
            pass
        temp_path.replace(self.storage_path)
        try:
            os.chmod(self.storage_path, 0o600)
        except OSError:
            pass

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
    def _compile_ir(
        rules: Dict[str, Any],
        *,
        source_kind: str,
        source_reference: str,
        missing_conditions: List[Any],
    ) -> Dict[str, Any]:
        return NoahStrategyIR.compile(
            rules,
            source_kind=source_kind,
            source_reference=source_reference,
            missing_conditions=missing_conditions,
        )

    def _ensure_ir(self, version: Dict[str, Any]) -> Dict[str, Any]:
        """기존 저장 버전도 승인/적용 전에 IR v1 계약으로 승격한다."""
        ir = version.get("strategy_ir")
        if not isinstance(ir, dict):
            ir = self._compile_ir(
                dict(version.get("rules") or {}),
                source_kind=str(version.get("source_kind") or "text"),
                source_reference=str(version.get("source_reference") or ""),
                missing_conditions=list(version.get("missing_conditions") or []),
            )
            version["strategy_ir"] = ir
            version["ir_validation"] = NoahStrategyIR.validate(ir)
            version["ir_hash"] = ir.get("integrity_sha256")
        return dict(ir or {})

    def _assert_ir_ready(self, version: Dict[str, Any], *, allow_clarification: bool = False) -> None:
        ir = self._ensure_ir(version)
        validation = NoahStrategyIR.validate(ir)
        if not validation.get("valid"):
            raise ValueError(
                "Noah Strategy IR 무결성 검증에 실패했습니다: "
                + ", ".join(validation.get("errors") or [])
            )
        support_status = str((ir.get("support") or {}).get("status") or "unsupported")
        if support_status == "unsupported":
            reasons = list((ir.get("support") or {}).get("unsupported_reasons") or [])
            raise ValueError(
                "현재 실행 엔진이 지원하지 않는 전략 노드가 있습니다: "
                + ", ".join(reasons)
            )
        if support_status == "needs_clarification" and not allow_clarification:
            raise ValueError("사용자 확인이 필요한 전략 조건을 먼저 완성해야 합니다.")

    @staticmethod
    def paper_execution_readiness(version: Dict[str, Any]) -> Dict[str, Any]:
        """Return whether a version can create attributable PAPER entries.

        A text strategy can be preserved as a valid Noah Strategy IR document
        without yet being executable.  PAPER forward validation is stricter:
        an independent strategy needs one explicit direction and at least one
        declarative entry condition.  Otherwise it can never produce a trade
        attributable to that version and must not be presented as validating.
        """
        rules = dict(version.get("rules") or {})
        signal_mode = str(
            version.get("signal_mode") or rules.get("signal_mode") or "confirm"
        ).strip().lower()
        entry_signal = str(
            version.get("entry_signal") or rules.get("entry_signal") or ""
        ).strip().upper()
        raw_entry = rules.get("executable_entry") or {}
        entry_spec = dict(raw_entry) if isinstance(raw_entry, dict) else {}
        has_expression = isinstance(entry_spec.get("expression"), dict)
        has_conditions = any(
            isinstance(condition, dict)
            for group in ("all", "any")
            for condition in (entry_spec.get(group) or [])
        )
        independent_entries = dict(rules.get("independent_entries") or {})

        def _has_entry_spec(value: Any) -> bool:
            if not isinstance(value, dict):
                return False
            return isinstance(value.get("expression"), dict) or any(
                isinstance(condition, dict)
                for group in ("all", "any")
                for condition in (value.get(group) or [])
            )

        branch_directions = [
            direction
            for direction in ("LONG", "SHORT")
            if _has_entry_spec(
                independent_entries.get(direction) or independent_entries.get(direction.lower())
            )
        ]
        reasons: List[str] = []
        entry_contract = rules.get('entry_contract')
        if entry_contract is not None:
            if not DeclarativeStrategyEngine.noah_base_entry_confirmed(rules):
                reasons.append('entry_contract_invalid')
        has_executable_entry = bool(branch_directions or has_expression or has_conditions)
        grounding_status = str(
            dict(rules.get("source_grounding") or {}).get("status") or ""
        ).strip().lower()
        if version.get("missing_conditions"):
            reasons.append("document_conditions_missing")
        if signal_mode == "independent":
            if not branch_directions and entry_signal not in {"LONG", "SHORT"}:
                reasons.append("independent_entry_signal_missing")
            if not branch_directions and not (has_expression or has_conditions):
                reasons.append("independent_executable_entry_missing")
        elif not has_executable_entry and DeclarativeStrategyEngine.requires_source_entry(rules):
            # Do not present an uncompiled Pine/document entry as if its source
            # logic were being forward-tested. A user may explicitly replace
            # it with a declared Noah-base overlay in a new version.
            reasons.append("confirm_executable_entry_missing")
        exit_blocks = [dict(rules.get("engine_settings") or {})]
        exit_blocks.extend(
            dict(value)
            for value in dict(
                rules.get("regime_parameters", rules.get("market_condition_parameters", {}))
                or {}
            ).values()
            if isinstance(value, dict) and value
        )
        exit_blocks.extend(
            dict(item.get("set") or {})
            for item in list(rules.get("performance_adjustments") or [])
            if isinstance(item, dict) and isinstance(item.get("set"), dict) and item.get("set")
        )
        raw_exit_policy = rules.get("exit_policy")
        if isinstance(raw_exit_policy, dict):
            exit_policy_mode = str(raw_exit_policy.get("mode") or "").strip().lower()
        else:
            exit_policy_mode = str(raw_exit_policy or "").strip().lower()
        has_any_exit_rate = any(
            "tp_percent" in block or "sl_percent" in block for block in exit_blocks
        )
        has_complete_exit_rate = any(
            block.get("tp_percent") is not None and block.get("sl_percent") is not None
            for block in exit_blocks
        )
        if not exit_policy_mode:
            exit_policy_mode = (
                "inherit_noah_base_legacy"
                if signal_mode == "confirm" and not has_any_exit_rate
                else "strategy_owned"
            )
        inherits_noah = exit_policy_mode in {"inherit_noah_base", "inherit_noah_base_legacy"}
        if inherits_noah and signal_mode != "confirm":
            reasons.append("independent_exit_policy_cannot_inherit_noah")
        if inherits_noah and has_any_exit_rate:
            reasons.append("inherited_exit_policy_conflicts_with_strategy_rates")
        if not inherits_noah and not has_complete_exit_rate:
            reasons.append("strategy_exit_rates_missing")
        for block in exit_blocks:
            try:
                validate_stored_exit_rates(block)
            except (ExitRateContractError, TypeError, ValueError, OverflowError):
                reasons.append("exit_rate_contract_missing_or_invalid")
                continue
            try:
                # 저장·PAPER·실주문이 같은 단위와 범위를 사용한다. 사용자가
                # 입력한 값을 조용히 상한으로 보정하지 않고 준비 단계에서 차단한다.
                normalize_engine_settings(block)
            except (ExitRateContractError, TypeError, ValueError, OverflowError):
                reasons.append("engine_settings_contract_invalid")
        validation_subject = (
            "custom_entry_logic"
            if has_executable_entry
            else "noah_base_with_custom_risk_exit"
        )
        historical_validation_applicable = validation_subject == "custom_entry_logic"
        return {
            "ready": not reasons,
            "document_ready": not bool(version.get("missing_conditions")),
            "signal_mode": signal_mode,
            "entry_signal": "DYNAMIC" if branch_directions else entry_signal,
            "entry_directions": branch_directions or ([entry_signal] if entry_signal in {"LONG", "SHORT"} else []),
            "has_executable_entry": has_executable_entry,
            "validation_subject": validation_subject,
            "source_strategy_logic_executed": validation_subject == "custom_entry_logic",
            # Historical replay can create entry decisions only when this
            # version owns executable entry logic.  A confirm/Noah-base
            # overlay is still valid for forward PAPER validation, but it must
            # not be forced through a replay that cannot reproduce NoahAI's
            # upstream candidate stream.
            "historical_validation_applicable": historical_validation_applicable,
            "historical_validation_reason": (
                "custom_entry_rules_available"
                if historical_validation_applicable
                else "noah_base_entry_requires_forward_paper"
            ),
            "exit_policy_mode": exit_policy_mode,
            "has_explicit_exit_rates": has_complete_exit_rate,
            "reasons": list(dict.fromkeys(reasons)),
        }

    def _refresh_execution_readiness(self, version: Dict[str, Any]) -> Dict[str, Any]:
        readiness = self.paper_execution_readiness(version)
        version["execution_readiness"] = deepcopy(readiness)
        # Compatibility field used by existing Web/legacy clients.
        version["paper_execution_readiness"] = deepcopy(readiness)
        return readiness

    def _assert_execution_ready(self, version: Dict[str, Any], *, action: str) -> None:
        readiness = self._refresh_execution_readiness(version)
        if readiness["ready"]:
            return
        raise ValueError(
            f"{action}할 수 없습니다. 실행 규칙을 먼저 완성하세요: "
            + ", ".join(readiness["reasons"])
        )

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
        rules = self._normalize_strategy_rules(rules)

        key = strategy_key or f"strategy_{uuid4().hex[:10]}"
        guidance = build_strategy_guidance(rules, self.REQUIRED_RULES)
        missing = list(guidance["missing_conditions"])
        missing.extend(str(item) for item in list(rules.get("compiler_issues") or []) if item)
        executable_validation = DeclarativeStrategyEngine.validate_rule_spec(rules)
        if not executable_validation["valid"]:
            missing.append("unsupported_executable_conditions")
            guidance["missing_conditions"] = list(missing)
            guidance["complete"] = False
            guidance["unsupported_conditions"] = list(executable_validation["errors"])
        missing = list(dict.fromkeys(missing))
        previous = self._previous(key)
        status = "needs_clarification" if missing else "analyzed"
        ir = self._compile_ir(
            rules,
            source_kind=str(source_kind or "text").strip().lower(),
            source_reference=str(source_reference or "").strip(),
            missing_conditions=missing,
        )
        version = {
            "strategy_key": key,
            "version_id": f"{key}_v{self._version_number(key)}_{uuid4().hex[:6]}",
            "version": self._version_number(key),
            "name": str(name or "이름 없는 전략").strip(),
            "source_kind": str(source_kind or "text").strip().lower(),
            "source_reference": str(source_reference or "").strip(),
            "rules": deepcopy(rules),
            "strategy_ir": ir,
            "ir_validation": NoahStrategyIR.validate(ir),
            "ir_hash": ir.get("integrity_sha256"),
            "correlation_id": f"strategy_event_{uuid4().hex}",
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
            "version_diff": build_version_diff(
                (previous or {}).get("rules", {}), rules,
            ) if previous else {"changes": [], "kind": "initial_version"},
            "approval": None,
            "paper_validation": None,
            "execution_validation": None,
            "validation_lab": None,
            "promotion_history": [],
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        readiness = self._refresh_execution_readiness(version)
        if not missing and not readiness["ready"]:
            version["xai"]["summary"] = (
                "전략 문서 구조화는 완료됐지만 실행 규칙이 부족합니다. "
                "방향·선언형 진입조건·청산정책을 보완한 뒤 승인하세요."
            )
        self.strategies.setdefault(key, []).append(version)
        self._trim(key)
        self._save()
        return deepcopy(version)

    def clarify(self, strategy_key: str, version_id: str, answers: Dict[str, Any]) -> Dict[str, Any]:
        version = self._find(strategy_key, version_id)
        if version.get("status") != "needs_clarification":
            raise ValueError("재확인이 필요한 버전이 아닙니다.")
        version["rules"].update(deepcopy(answers or {}))
        version["rules"] = self._normalize_strategy_rules(version["rules"])
        guidance = build_strategy_guidance(version["rules"], self.REQUIRED_RULES)
        missing = list(guidance["missing_conditions"])
        missing.extend(str(item) for item in list(version["rules"].get("compiler_issues") or []) if item)
        executable_validation = DeclarativeStrategyEngine.validate_rule_spec(version["rules"])
        if not executable_validation["valid"]:
            missing.append("unsupported_executable_conditions")
            guidance["missing_conditions"] = list(missing)
            guidance["complete"] = False
            guidance["unsupported_conditions"] = list(executable_validation["errors"])
        missing = list(dict.fromkeys(missing))
        version["missing_conditions"] = missing
        version["guidance"] = guidance
        ir = self._compile_ir(
            dict(version.get("rules") or {}),
            source_kind=str(version.get("source_kind") or "text"),
            source_reference=str(version.get("source_reference") or ""),
            missing_conditions=missing,
        )
        version["strategy_ir"] = ir
        version["ir_validation"] = NoahStrategyIR.validate(ir)
        version["ir_hash"] = ir.get("integrity_sha256")
        version.setdefault("xai", {})["summary"] = (
            f"AI가 아직 누락 조건 {len(missing)}개를 확인했습니다."
            if missing else
            "사용자 답변으로 전략 조건이 완성됐으며 승인 전에는 실행되지 않습니다."
        )
        version["status"] = "needs_clarification" if missing else "analyzed"
        self._refresh_execution_readiness(version)
        version["updated_at"] = self._now()
        self._save()
        return deepcopy(version)

    def approve(self, strategy_key: str, version_id: str, *, approved_by: str) -> Dict[str, Any]:
        version = self._find(strategy_key, version_id)
        self._assert_ir_ready(version)
        if version.get("status") != "analyzed":
            raise ValueError("누락 조건 확인과 XAI 분석 완료 후에만 승인할 수 있습니다.")
        self._assert_execution_ready(version, action="전략을 승인")
        if not str(approved_by or "").strip():
            raise ValueError("승인 주체가 필요합니다.")
        readiness = self.paper_execution_readiness(version)
        version["approval"] = {
            "approved_by": str(approved_by).strip(), "approved_at": self._now(),
            "validation_subject": readiness["validation_subject"],
            "source_strategy_logic_executed": readiness["source_strategy_logic_executed"],
        }
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
        update_observation_status: bool = True,
    ) -> Dict[str, Any]:
        version = self._find(strategy_key, version_id)
        self._assert_ir_ready(version)
        self._assert_execution_ready(version, action="PAPER 검증 결과를 기록")
        if version.get("status") not in {
            "approved", "paper_rejected", "paper_validated",
            "execution_rejected", "execution_validated", "paper_observing", "paper_paused",
        }:
            raise ValueError("사용자 승인 후에만 모의거래 검증을 기록할 수 있습니다.")
        raw_metrics = dict(metrics or {})
        forward_days_required = bool(raw_metrics.get("require_forward_days", False))
        observation_days = float(raw_metrics.get("observation_days", 0.0) or 0.0)
        passed = (
            int(trades) >= self.min_paper_trades
            and int(guardrail_violations) == 0
            and (not forward_days_required or observation_days >= 7.0)
        )
        requirements_complete = (
            int(trades) >= self.min_paper_trades
            and (not forward_days_required or observation_days >= 7.0)
        )
        completion_status = (
            "passed" if passed else "failed" if requirements_complete else "in_progress"
        )
        recorded_at = self._now()
        version["paper_validation"] = {
            "passed": passed,
            "completion_status": completion_status,
            "trades": int(trades),
            "guardrail_violations": int(guardrail_violations),
            "metrics": deepcopy(raw_metrics),
            "recorded_at": recorded_at,
            "note": "백테스트는 보조 검증이며 모의거래 통과를 대체하지 않음",
        }
        lab = dict(version.get("validation_lab") or {})
        if lab:
            raw_metrics = dict(metrics or {})
            paper_pnl_by_currency = dict(raw_metrics.get("pnl_by_currency") or {})
            paper_net_pnl: float | None
            if len(paper_pnl_by_currency) == 1:
                paper_net_pnl = float(next(iter(paper_pnl_by_currency.values())) or 0.0)
            elif paper_pnl_by_currency:
                paper_net_pnl = None
            else:
                raw_net_pnl = raw_metrics.get("net_pnl", raw_metrics.get("realized_pnl"))
                try:
                    paper_net_pnl = None if raw_net_pnl is None else float(raw_net_pnl)
                except (TypeError, ValueError):
                    paper_net_pnl = None
            lab["paper_forward"] = {
                "trades": int(trades),
                "net_pnl": paper_net_pnl,
                "pnl_by_currency": paper_pnl_by_currency,
                "currencies_comparable": len(paper_pnl_by_currency) <= 1,
                "passed": passed,
                "guardrail_violations": int(guardrail_violations),
                "recorded_at": recorded_at,
            }
            sample = dict(lab.get("sample") or {})
            walkforward = dict(lab.get("walkforward") or {})
            overfit = dict(lab.get("overfit_risk") or {})
            minimum_gate = dict(lab.get("minimum_quality_gate") or {})
            lab["promotion_ready"] = bool(
                passed
                and int(sample.get("out_of_sample", 0) or 0) >= 3
                and float(walkforward.get("pass_rate", 0.0) or 0.0) >= 0.5
                and not bool(overfit.get("flagged", False))
                and bool(minimum_gate.get("passed", True))
            )
            lab["auto_promoted"] = False
            version["validation_lab"] = lab
        version.setdefault("promotion_history", []).append({
            "event": "paper_validation_recorded",
            "passed": passed,
            "trades": int(trades),
            "promotion_ready": bool(lab.get("promotion_ready", False)) if lab else False,
            "at": recorded_at,
            "auto_promoted": False,
        })
        # 자동 원장 합산은 첫 체결부터 호출된다. 7일/최소 체결 수가 아직
        # 부족한 정상 진행 상태를 실패로 바꾸지 않는다.
        observation_is_active = (
            self.paper_versions.get(strategy_key) == version_id
            and str(version.get("status") or "") == "paper_observing"
        )
        if update_observation_status and observation_is_active:
            version["status"] = (
                "paper_validated" if passed
                else "paper_rejected" if completion_status == "failed"
                else "paper_observing"
            )
            if passed:
                self.paper_versions.pop(strategy_key, None)
            elif completion_status == "failed":
                self.paper_versions.pop(strategy_key, None)
        elif update_observation_status and not forward_days_required:
            version["status"] = "paper_validated" if passed else "paper_rejected"
        # Historical/late ledger synchronization updates evidence only.  It
        # must not recreate an execution grant after the user pressed stop.
        version["updated_at"] = self._now()
        self._save()
        return deepcopy(version)

    def start_paper_observation(self, strategy_key: str, version_id: str) -> Dict[str, Any]:
        """Put one user-approved version in the PAPER-only pool.

        Historical replay is useful but must not become a circular prerequisite
        for forward PAPER data.  PAPER cannot place external orders, so a newly
        approved or historically rejected version may gather forward evidence
        here while LIVE activation remains gated by completed validation.
        """
        version = self._find(strategy_key, version_id)
        self._assert_ir_ready(version)
        self._assert_execution_ready(version, action="PAPER 전진검증을 시작")
        execution = dict(version.get("execution_validation") or {})
        status = str(version.get("status") or "")
        historical_passed = bool(
            str(execution.get("mode") or "") == "historical_replay"
            and bool(execution.get("passed", False))
        )
        if status not in {"approved", "execution_rejected", "execution_validated", "paper_rejected", "paper_paused"}:
            raise ValueError("사용자 승인 후 PAPER 전진검증을 시작하세요.")
        if status == "execution_validated" and not historical_passed:
            raise ValueError("현재 실행검증 상태를 확인한 뒤 PAPER 전진검증을 시작하세요.")
        if self.active_versions.get(strategy_key):
            raise ValueError("이미 일반 운용에 적용된 전략은 PAPER 검증 대상으로 중복 등록할 수 없습니다.")
        previous_id = self.paper_versions.get(strategy_key)
        if previous_id and previous_id != version_id:
            # One strategy key has one execution grant.  Silently replacing
            # the grant used to leave the displaced version with an open
            # observation window and made its evidence appear reset.  The
            # user must pause the running sibling explicitly so its attempt,
            # elapsed time and ledger attribution remain intact.
            previous_label = previous_id
            try:
                previous = self._find(strategy_key, previous_id)
                previous_label = f"v{previous.get('version', '?')} ({previous_id})"
            except ValueError:
                pass
            raise ValueError(
                f"같은 전략의 {previous_label}가 PAPER 검증 중입니다. "
                "해당 버전을 PAPER 일시정지한 뒤 이 버전을 시작하세요. "
                "기존 거래·손익·활성 검증일수는 보존됩니다."
            )
        if status == "paper_paused":
            now = self._now()
            windows = self.paper_observation_windows(version)
            windows.append({"started_at": now, "stopped_at": None})
            self.paper_versions[strategy_key] = version_id
            version["paper_observation_windows"] = windows[-500:]
            version["status"] = "paper_observing"
            version.pop("paper_observation_stopped_at", None)
            version.setdefault("promotion_history", []).append({
                "event": "paper_observation_resumed",
                "at": now,
                "auto_promoted": False,
            })
            version["updated_at"] = now
            self._save()
            return deepcopy(version)
        self.paper_versions[strategy_key] = version_id
        previous_validation = deepcopy(version.get("paper_validation"))
        if previous_validation:
            validation_history = list(version.get("paper_validation_history") or [])[-49:]
            validation_history.append(previous_validation)
            version["paper_validation_history"] = validation_history
        version["paper_validation"] = None
        version["paper_observation_previous_status"] = status
        version["status"] = "paper_observing"
        started_at = self._now()
        version["paper_observation_started_at"] = started_at
        version["paper_observation_windows"] = [{"started_at": started_at, "stopped_at": None}]
        version["paper_observation_attempt_id"] = f"paper_attempt_{uuid4().hex}"
        version.pop("paper_observation_stopped_at", None)
        version.setdefault("promotion_history", []).append({
            "event": "paper_observation_started",
            "at": self._now(),
            "auto_promoted": False,
        })
        version["updated_at"] = self._now()
        self._save()
        return deepcopy(version)

    def stop_paper_observation(self, strategy_key: str, version_id: str) -> Dict[str, Any]:
        version = self._find(strategy_key, version_id)
        if self.paper_versions.get(strategy_key) != version_id or version.get("status") != "paper_observing":
            raise ValueError("현재 PAPER 전진검증 중인 전략만 중지할 수 있습니다.")
        self.paper_versions.pop(strategy_key, None)
        stopped_at = self._now()
        version["status"] = "paper_paused"
        version["paper_observation_stopped_at"] = stopped_at
        windows = self.paper_observation_windows(version)
        if windows and not windows[-1].get("stopped_at"):
            windows[-1]["stopped_at"] = stopped_at
        version["paper_observation_windows"] = windows[-500:]
        version.setdefault("promotion_history", []).append({
            "event": "paper_observation_paused",
            "at": stopped_at,
            "auto_promoted": False,
        })
        version["updated_at"] = self._now()
        self._save()
        return deepcopy(version)

    def restart_paper_observation(self, strategy_key: str, version_id: str) -> Dict[str, Any]:
        """Start a new attempt while preserving the complete previous attempt."""
        version = self._find(strategy_key, version_id)
        if str(version.get("status") or "") != "paper_paused":
            raise ValueError("일시정지된 PAPER 검증만 새 시도로 시작할 수 있습니다.")
        archived_at = self._now()
        attempt_history = list(version.get("paper_validation_attempt_history") or [])[-49:]
        attempt_history.append({
            "attempt_id": str(version.get("paper_observation_attempt_id") or "legacy_attempt"),
            "started_at": version.get("paper_observation_started_at"),
            "stopped_at": version.get("paper_observation_stopped_at"),
            "active_seconds": self.paper_observation_elapsed_seconds(version),
            "windows": deepcopy(self.paper_observation_windows(version)),
            "paper_validation": deepcopy(version.get("paper_validation")),
            "archived_at": archived_at,
            "reason": "user_started_new_attempt",
        })
        version["paper_validation_attempt_history"] = attempt_history
        previous_validation = deepcopy(version.get("paper_validation"))
        if previous_validation:
            validation_history = list(version.get("paper_validation_history") or [])[-49:]
            validation_history.append(previous_validation)
            version["paper_validation_history"] = validation_history
        version["paper_validation"] = None
        version["paper_observation_windows"] = []
        version.pop("paper_observation_started_at", None)
        version.pop("paper_observation_stopped_at", None)
        previous_status = str(version.get("paper_observation_previous_status") or "approved")
        version["status"] = previous_status if previous_status in {
            "approved", "execution_rejected", "execution_validated", "paper_rejected",
        } else "approved"
        return self.start_paper_observation(strategy_key, version_id)

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
        self._assert_ir_ready(version)
        self._assert_execution_ready(version, action="자동 실행검증을 기록")
        if version.get("status") not in {"approved", "execution_rejected", "execution_validated"}:
            raise ValueError("사용자 승인 후에만 실행 검증을 기록할 수 있습니다.")
        allowed_modes = {"historical_replay", "live_observation", "limited_live"}
        normalized_mode = str(mode or "live_observation").lower()
        if normalized_mode not in allowed_modes:
            raise ValueError(f"지원하지 않는 실행 검증 방식입니다: {normalized_mode}")
        passed = int(decisions) >= self.min_paper_trades and int(guardrail_violations) == 0
        if normalized_mode == "historical_replay" and "quality_passed" in (metrics or {}):
            # Keep the stored status contract, without fabricating risk violations.
            # Legacy records without this field retain their original interpretation.
            passed = passed and (metrics or {}).get("quality_passed") is True
        version["execution_validation"] = {
            "passed": passed,
            "decisions": int(decisions),
            "guardrail_violations": int(guardrail_violations),
            "metrics": deepcopy(metrics or {}),
            "mode": normalized_mode,
            "recorded_at": self._now(),
            "note": (
                "과거 시세 백테스트의 성과 평가입니다. 성과 기준 미달은 안전 위반이 아니며, 실행 조건이 유효하면 PAPER를 선택할 수 있습니다."
                if normalized_mode == "historical_replay"
                else "관찰/제한운용의 체결·비용·PnL 품질을 포함"
            ),
        }
        version["improvement_advice"] = build_improvement_advice(metrics)
        chart = version["execution_validation"]["metrics"].get("replay_visualization")
        if isinstance(chart, dict):
            chart["binding"] = {
                "strategy_key": strategy_key, "version_id": version_id,
                "ir_hash": version.get("ir_hash"),
                "recorded_at": version["execution_validation"]["recorded_at"],
            }
        version["status"] = "execution_validated" if passed else "execution_rejected"
        version["updated_at"] = self._now()
        self._save()
        return deepcopy(version)

    def record_validation_lab(
        self,
        strategy_key: str,
        version_id: str,
        report: Dict[str, Any],
    ) -> Dict[str, Any]:
        version = self._find(strategy_key, version_id)
        self._assert_ir_ready(version)
        self._assert_execution_ready(version, action="검증 연구소 결과를 기록")
        if version.get("status") not in {
            "approved", "paper_validated", "paper_rejected",
            "execution_validated", "execution_rejected",
        }:
            raise ValueError("사용자 승인 후에만 검증 연구소 결과를 기록할 수 있습니다.")
        version["validation_lab"] = deepcopy(report or {})
        version.setdefault("promotion_history", []).append({
            "event": "validation_lab_recorded",
            "promotion_ready": bool((report or {}).get("promotion_ready", False)),
            "at": self._now(),
            "auto_promoted": False,
        })
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
        self._assert_ir_ready(version)
        self._assert_execution_ready(version, action="전략을 적용")
        mode = str(operation_mode or "standard").strip().lower()
        if mode not in {"standard", "limited_live"}:
            raise ValueError(f"지원하지 않는 전략 운용 방식입니다: {mode}")
        previous_status = str(version.get("status") or "")
        if mode == "standard":
            if previous_status not in {"paper_validated", "execution_validated"}:
                raise ValueError("일반 운용은 실행 검증 통과 후에만 적용할 수 있습니다.")
            paper_passed = bool((version.get("paper_validation") or {}).get("passed", False))
            execution = dict(version.get("execution_validation") or {})
            forward_execution_passed = bool(
                execution.get("passed", False)
                and str(execution.get("mode") or "") in {"live_observation", "limited_live"}
            )
            if not paper_passed and not forward_execution_passed:
                raise ValueError(
                    "과거 재생만으로 일반 운용에 적용할 수 없습니다. PAPER 전진검증을 먼저 통과하세요."
                )
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
        version.setdefault("promotion_history", []).append({
            "event": "user_activated",
            "operation_mode": mode,
            "at": self._now(),
            "approved_by_user": True,
        })
        version["updated_at"] = self._now()
        self.active_versions[strategy_key] = version_id
        self.paper_versions.pop(strategy_key, None)
        self._save()
        return deepcopy(version)

    def rollback(self, strategy_key: str, target_version_id: str, *, approved_by: str) -> Dict[str, Any]:
        target = self._find(strategy_key, target_version_id)
        self._assert_ir_ready(target)
        self._assert_execution_ready(target, action="전략 버전으로 롤백")
        paper_validation = target.get("paper_validation") or {}
        execution_validation = target.get("execution_validation") or {}
        forward_execution_passed = bool(
            execution_validation.get("passed", False)
            and str(execution_validation.get("mode") or "") in {"live_observation", "limited_live"}
        )
        if not paper_validation.get("passed", False) and not forward_execution_passed:
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
        self.paper_versions.pop(strategy_key, None)
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

    def get_version(self, strategy_key: str, version_id: str) -> Dict[str, Any]:
        """편집 화면에 전달할 저장 버전의 독립 복사본을 반환한다."""
        return deepcopy(self._find(strategy_key, version_id))

    def _record_deletion(
        self,
        *,
        strategy_key: str,
        version_ids: List[str],
        deleted_by: str,
        scope: str,
    ) -> None:
        self.deletion_history.append({
            "event": "private_strategy_deleted",
            "scope": str(scope),
            "strategy_key": str(strategy_key),
            "version_ids": [str(item) for item in version_ids],
            "deleted_by": str(deleted_by),
            "deleted_at": self._now(),
        })
        self.deletion_history = self.deletion_history[-100:]

    def delete_version(
        self,
        strategy_key: str,
        version_id: str,
        *,
        deleted_by: str,
    ) -> Dict[str, Any]:
        """비활성 프라이빗 버전 하나를 삭제한다.

        적용 중 버전은 먼저 명시적으로 해제해야 한다. 삭제 기록에는 규칙이나
        자격증명을 남기지 않고 식별자와 행위자만 보존한다.
        """
        actor = str(deleted_by or '').strip()
        if not actor:
            raise ValueError("삭제 주체가 필요합니다.")
        version = self._find(strategy_key, version_id)
        if (
            str(version.get("status") or "") == "active"
            or self.active_versions.get(strategy_key) == version_id
            or self.paper_versions.get(strategy_key) == version_id
        ):
            raise ValueError("적용 중인 전략은 적용 해제하고, PAPER 검증 중인 전략은 검증 중지한 뒤 삭제하세요.")
        versions = self.strategies.get(strategy_key, [])
        self.strategies[strategy_key] = [
            item for item in versions if item.get("version_id") != version_id
        ]
        if not self.strategies[strategy_key]:
            self.strategies.pop(strategy_key, None)
            self.active_versions.pop(strategy_key, None)
            self.paper_versions.pop(strategy_key, None)
        self._record_deletion(
            strategy_key=strategy_key,
            version_ids=[version_id],
            deleted_by=actor,
            scope="version",
        )
        self._save()
        return deepcopy(version)

    def delete_strategy(self, strategy_key: str, *, deleted_by: str) -> Dict[str, Any]:
        """적용 중이 아닌 프라이빗 전략과 모든 버전을 삭제한다."""
        actor = str(deleted_by or '').strip()
        if not actor:
            raise ValueError("삭제 주체가 필요합니다.")
        versions = list(self.strategies.get(strategy_key, []) or [])
        if not versions:
            raise ValueError(f"전략을 찾을 수 없습니다: {strategy_key}")
        if self.active_versions.get(strategy_key) or self.paper_versions.get(strategy_key) or any(
            str(item.get("status") or "") in {"active", "paper_observing"} for item in versions
        ):
            raise ValueError("적용 중인 전략은 적용 해제하고, PAPER 검증 중인 전략은 검증 중지한 뒤 삭제하세요.")
        version_ids = [str(item.get("version_id") or "") for item in versions]
        self.strategies.pop(strategy_key, None)
        self.active_versions.pop(strategy_key, None)
        self.paper_versions.pop(strategy_key, None)
        self._record_deletion(
            strategy_key=strategy_key,
            version_ids=version_ids,
            deleted_by=actor,
            scope="strategy",
        )
        self._save()
        return {
            "strategy_key": strategy_key,
            "deleted_versions": len(version_ids),
            "version_ids": version_ids,
        }

    def _trim(self, strategy_key: str) -> None:
        versions = self.strategies.get(strategy_key, [])
        while len(versions) > self.max_versions:
            active_id = self.active_versions.get(strategy_key)
            paper_id = self.paper_versions.get(strategy_key)
            removable = next((idx for idx, item in enumerate(versions) if item.get("version_id") not in {active_id, paper_id}), None)
            if removable is None:
                break
            self.archived_versions.setdefault(strategy_key, []).append(versions.pop(removable))
