#!/usr/bin/env python3
"""Audit the complete legacy-to-Web UI source contract.

This is intentionally a source gate, not a visual-parity certificate.  It
checks all five product services, every top-level feature, ten institution
sources, the nested life-finance contract, settings, manual, analyst cards and
the React surface map in one run.  macOS side-by-side and Windows E2E evidence
remain separate release gates.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.product_ui_contract import (  # noqa: E402
    AI_ANALYST_CARDS,
    LIFE_FINANCE_INNER_TABS,
    LIFE_FINANCE_QUICK_ACTIONS,
    MANUAL_SECTION_LABELS,
    PORTFOLIO_INSIGHT_SECTIONS,
    SERVICE_FEATURE_LABELS,
    SERVICE_ORDER,
    SERVICE_SOURCES,
    SETTINGS_SECTION_LABELS,
)
from web_platform.feature_inventory import load_feature_inventory  # noqa: E402


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def audit() -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    inventory = load_feature_inventory()
    services = {str(item["id"]): item for item in inventory["services"]}
    expected_feature_ids = {
        str(feature["id"])
        for service in inventory["services"]
        for feature in service["features"]
    }

    _require(tuple((item["id"], item["label"]) for item in inventory["services"]) == SERVICE_ORDER,
             "5개 메인 서비스 순서가 정본과 다릅니다.", errors)
    for service_id, _label in SERVICE_ORDER:
        service = services.get(service_id, {})
        _require(tuple(service.get("sources", [])) == SERVICE_SOURCES[service_id],
                 f"{service_id}: source 순서가 정본과 다릅니다.", errors)
        _require(tuple(item.get("label") for item in service.get("features", [])) == SERVICE_FEATURE_LABELS[service_id],
                 f"{service_id}: 기능 탭 순서가 정본과 다릅니다.", errors)
        for feature in service.get("features", []):
            migration = str(feature.get("migration") or "")
            _require(migration.startswith("source_connected"),
                     f"{feature.get('id')}: 소스 연결 상태가 완료 원장에 반영되지 않았습니다 ({migration}).", errors)

    surfaces_source = (ROOT / "webui" / "src" / "featureSurfaces.ts").read_text(encoding="utf-8")
    mapped_ids = re.findall(r'^\s+"([^"]+)":\s+"[^"]+",$', surfaces_source, flags=re.MULTILINE)
    _require(len(mapped_ids) == len(set(mapped_ids)), "React 화면 매핑에 중복 기능 ID가 있습니다.", errors)
    _require(set(mapped_ids) == expected_feature_ids, "React 전용 화면 매핑과 전체 기능 원장이 다릅니다.", errors)

    settings = (ROOT / "webui" / "src" / "components" / "SettingsCenter.tsx").read_text(encoding="utf-8")
    manual = json.loads((ROOT / "docs" / "USER_MANUAL_SECTIONS.json").read_text(encoding="utf-8"))
    operations = (ROOT / "webui" / "src" / "components" / "Operations.tsx").read_text(encoding="utf-8")
    portfolio = (ROOT / "webui" / "src" / "components" / "PortfolioWorkspace.tsx").read_text(encoding="utf-8")
    analyst = (ROOT / "webui" / "src" / "components" / "AIAnalystWorkspace.tsx").read_text(encoding="utf-8")

    for label in SETTINGS_SECTION_LABELS:
        _require(label in settings, f"설정 탭 누락: {label}", errors)
    _require(tuple(section.get("label") for section in manual.get("sections", [])) == MANUAL_SECTION_LABELS,
             "메뉴얼 11개 탭 이름 또는 순서가 정본과 다릅니다.", errors)
    for label in (*LIFE_FINANCE_INNER_TABS, *LIFE_FINANCE_QUICK_ACTIONS):
        _require(label in operations, f"생활금융 내부 기능 누락: {label}", errors)
    for label in PORTFOLIO_INSIGHT_SECTIONS:
        _require(label in portfolio, f"자산 통합 섹션 누락: {label}", errors)
    for label in AI_ANALYST_CARDS:
        _require(label in analyst, f"AI 애널리스트 카드 누락: {label}", errors)

    summary = {
        "services": len(SERVICE_ORDER),
        "top_level_features": len(expected_feature_ids),
        "institution_sources": sum(len(items) for items in SERVICE_SOURCES.values()),
        "life_finance_inner_routes": len(LIFE_FINANCE_INNER_TABS),
        "settings_sections": len(SETTINGS_SECTION_LABELS),
        "manual_sections": len(MANUAL_SECTION_LABELS),
        "ai_analyst_cards": len(AI_ANALYST_CARDS),
    }
    return errors, summary


def main() -> int:
    errors, summary = audit()
    print(json.dumps({"status": "FAIL" if errors else "PASS", "summary": summary, "errors": errors}, ensure_ascii=False, indent=2))
    if not errors:
        print("SOURCE CONTRACT PASS — 시각 1:1 및 Windows E2E 완료를 의미하지 않습니다.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
