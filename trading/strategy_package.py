"""민감정보를 제외한 .noahstrategy 로컬 공유/감사 계약."""

from __future__ import annotations

import hashlib
import hmac
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .noah_strategy_ir import NoahStrategyIR


FORMAT = "noahstrategy"
SCHEMA_VERSION = 1
PROHIBITED_FRAGMENTS = (
    "api_key", "secret", "passphrase", "password", "token", "credential",
    "account_no", "withdraw", "private_key", "source_path", "absolute_path",
    "live_confirmation", "approved_by",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _contains_prohibited(value: Any, path: str = "") -> Optional[str]:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).lower()
            current = f"{path}.{key}" if path else str(key)
            if any(fragment in normalized for fragment in PROHIBITED_FRAGMENTS):
                return current
            found = _contains_prohibited(nested, current)
            if found:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = _contains_prohibited(item, f"{path}[{index}]")
            if found:
                return found
    return None


def build_strategy_package(
    version: Mapping[str, Any], *, passport: Optional[Mapping[str, Any]] = None,
    access_policy: Optional[Mapping[str, Any]] = None, signing_key: str = "",
) -> Dict[str, Any]:
    ir = deepcopy(dict(version.get("strategy_ir") or {}))
    ir_validation = NoahStrategyIR.validate(ir)
    if not ir_validation.get("valid"):
        raise ValueError("유효한 Noah Strategy IR이 필요합니다.")
    policy = dict(access_policy or {})
    visibility = str(policy.get("visibility") or "private").lower()
    if visibility not in {"private", "team", "unlisted"}:
        raise ValueError("지원하지 않는 공유 범위입니다.")
    permissions = list(dict.fromkeys(str(item).lower() for item in (policy.get("permissions") or ["view", "use"])))
    if not permissions or any(item not in {"view", "use", "fork", "manage"} for item in permissions):
        raise ValueError("지원하지 않는 공유 권한입니다.")
    source_name = Path(str(version.get("source_reference") or "").replace("\\", "/")).name
    payload = {
        "format": FORMAT,
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "strategy": {
            "strategy_key": str(version.get("strategy_key") or ""),
            "version_id": str(version.get("version_id") or ""),
            "version": int(version.get("version", 1) or 1),
            "name": str(version.get("name") or "사용자 전략"),
            "source_kind": str(version.get("source_kind") or "text"),
            "source_reference_name": source_name,
            "strategy_ir": ir,
        },
        "passport": deepcopy(dict(passport or {})),
        "access_policy": {
            "visibility": visibility,
            "permissions": permissions,
            "updates_require_manual_approval": True,
        },
        "import_contract": {
            "initial_status": "review_only",
            "active": False,
            "approval": None,
            "paper_required": True,
            "auto_applied": False,
        },
    }
    prohibited = _contains_prohibited(payload)
    if prohibited:
        raise ValueError(f"패키지 금지 필드: {prohibited}")
    payload["content_sha256"] = _hash(payload)
    if signing_key:
        payload["signature"] = {
            "algorithm": "hmac-sha256-local",
            "value": hmac.new(signing_key.encode(), payload["content_sha256"].encode(), hashlib.sha256).hexdigest(),
        }
    else:
        payload["signature"] = {"algorithm": "unsigned-local", "value": ""}
    return payload


def verify_strategy_package(package: Mapping[str, Any], *, signing_key: str = "", allow_unsigned_local: bool = True) -> Dict[str, Any]:
    payload = deepcopy(dict(package or {}))
    errors = []
    if payload.get("format") != FORMAT or payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported_package_format")
    signature = dict(payload.pop("signature", {}) or {})
    claimed_hash = str(payload.pop("content_sha256", "") or "")
    if not claimed_hash or claimed_hash != _hash(payload):
        errors.append("content_hash_mismatch")
    prohibited = _contains_prohibited(payload)
    if prohibited:
        errors.append(f"prohibited_field:{prohibited}")
    algorithm = str(signature.get("algorithm") or "")
    if algorithm == "hmac-sha256-local":
        if not signing_key:
            errors.append("signature_key_required")
        else:
            expected = hmac.new(signing_key.encode(), claimed_hash.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, str(signature.get("value") or "")):
                errors.append("signature_mismatch")
    elif algorithm == "unsigned-local":
        if not allow_unsigned_local:
            errors.append("unsigned_package_blocked")
    else:
        errors.append("unsupported_signature")
    policy = dict(payload.get("access_policy") or {})
    if str(policy.get("visibility") or "") not in {"private", "team", "unlisted"}:
        errors.append("invalid_access_visibility")
    permissions = list(policy.get("permissions") or [])
    if not permissions or any(str(item) not in {"view", "use", "fork", "manage"} for item in permissions):
        errors.append("invalid_access_permissions")
    if policy.get("updates_require_manual_approval") is not True:
        errors.append("manual_update_approval_required")
    ir = dict(((payload.get("strategy") or {}).get("strategy_ir") or {}))
    if not NoahStrategyIR.validate(ir).get("valid"):
        errors.append("invalid_strategy_ir")
    return {"valid": not errors, "errors": sorted(set(errors)), "review_only": True, "auto_applied": False}


def export_strategy_package(path: str, package: Mapping[str, Any]) -> str:
    target = Path(path)
    if target.suffix.lower() != ".noahstrategy":
        target = target.with_suffix(".noahstrategy")
    verification = verify_strategy_package(package)
    if not verification["valid"]:
        raise ValueError("패키지 검증 실패: " + ", ".join(verification["errors"]))
    target.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target)


def import_strategy_package(path: str, *, signing_key: str = "", allow_unsigned_local: bool = True) -> Dict[str, Any]:
    target = Path(path)
    if target.suffix.lower() != ".noahstrategy":
        raise ValueError(".noahstrategy 파일만 가져올 수 있습니다.")
    package = json.loads(target.read_text(encoding="utf-8"))
    verification = verify_strategy_package(package, signing_key=signing_key, allow_unsigned_local=allow_unsigned_local)
    if not verification["valid"]:
        raise ValueError("패키지 검증 실패: " + ", ".join(verification["errors"]))
    strategy = deepcopy(dict(package.get("strategy") or {}))
    return {
        "name": strategy.get("name"),
        "source_kind": "noahstrategy",
        "source_reference": target.name,
        "rules": NoahStrategyIR.to_rules(dict(strategy.get("strategy_ir") or {})),
        "strategy_ir": deepcopy(strategy.get("strategy_ir")),
        "passport": deepcopy(package.get("passport") or {}),
        "access_policy": deepcopy(package.get("access_policy") or {}),
        "status": "review_only",
        "active": False,
        "approval": None,
        "auto_applied": False,
    }


def build_strategy_audit_bundle(version: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "strategy_key": version.get("strategy_key"),
        "version_id": version.get("version_id"),
        "correlation_id": version.get("correlation_id"),
        "ir_hash": version.get("ir_hash"),
        "status": version.get("status"),
        "validation": {
            "historical": deepcopy(version.get("execution_validation")),
            "lab": deepcopy(version.get("validation_lab")),
            "paper": deepcopy(version.get("paper_validation")),
        },
        "promotion_history": deepcopy(version.get("promotion_history") or []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "performance_claim": "evidence_only_not_future_guarantee",
    }
