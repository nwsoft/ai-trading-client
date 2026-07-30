"""고급 매매 계층 설정의 안전한 병합/프리셋 비교 유틸리티."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


def deep_merge_policy(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """중첩 딕셔너리를 보존하며 override를 재귀 병합한다."""
    merged = deepcopy(base if isinstance(base, dict) else {})
    for key, value in (override if isinstance(override, dict) else {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_policy(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def policy_changes(before: Dict[str, Any], after: Dict[str, Any], prefix: str = '') -> List[Dict[str, Any]]:
    """화면 미리보기용 변경 목록을 평탄화한다."""
    changes: List[Dict[str, Any]] = []
    keys = set(before if isinstance(before, dict) else {}) | set(after if isinstance(after, dict) else {})
    for key in sorted(keys):
        path = f"{prefix}.{key}" if prefix else str(key)
        old_value = (before or {}).get(key)
        new_value = (after or {}).get(key)
        if isinstance(old_value, dict) and isinstance(new_value, dict):
            changes.extend(policy_changes(old_value, new_value, path))
        elif old_value != new_value:
            changes.append({'path': path, 'before': old_value, 'after': new_value})
    return changes
