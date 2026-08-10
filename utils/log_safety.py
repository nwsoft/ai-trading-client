"""Authentication and membership summaries that are safe to write to logs.

Raw login responses can contain an email address, session identifier, bearer
token, referral URL/code, masked UID, and verification details.  Log only the
small operational summary needed to diagnose membership gates.
"""

from __future__ import annotations

import os
from collections import Counter
from typing import Any, Dict, Mapping


LOG_MAX_BYTES = 25 * 1024 * 1024
LOG_BACKUP_COUNT = 7
LOG_ROTATION_SIZE = "25 MB"
LOG_RETENTION = "14 days"


def _policy_from(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    policy = payload.get("membership_policy")
    if isinstance(policy, Mapping):
        return policy
    return payload


def membership_log_summary(payload: Any) -> Dict[str, Any]:
    """Return an allowlisted membership summary with no account identifiers."""
    raw = payload if isinstance(payload, Mapping) else {}
    policy = _policy_from(raw)
    programs = policy.get("referral_programs", [])
    status_counts: Counter[str] = Counter()
    if isinstance(programs, list):
        for item in programs:
            if not isinstance(item, Mapping):
                continue
            status = str(item.get("attribution_status") or "required").strip().lower()
            status_counts[status[:32] or "required"] += 1

    allowed = policy.get("allowed_exchanges", [])
    allowed_count = len(allowed) if isinstance(allowed, list) else 0
    return {
        "user_grade": str(raw.get("user_grade") or policy.get("user_grade") or "unknown")[:32],
        "policy_version": str(policy.get("policy_version") or "missing")[:64],
        "allowed_exchange_count": allowed_count,
        "referral_status_counts": dict(sorted(status_counts.items())),
    }


def status_response_log_summary(payload: Any) -> Dict[str, Any]:
    """Return a safe status-check response summary without token or session data."""
    raw = payload if isinstance(payload, Mapping) else {}
    summary = membership_log_summary(raw)
    summary.update({
        "is_active": bool(raw.get("is_active", False)),
        "force_quit": bool(raw.get("force_quit", False)),
        "access_token_refreshed": bool(str(raw.get("access_token") or "").strip()),
    })
    return summary


def log_file_label(path: Any) -> str:
    """Keep local account and home-directory names out of log messages."""
    return os.path.basename(str(path or "")) or "log-file"
