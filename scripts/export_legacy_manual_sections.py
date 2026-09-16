#!/usr/bin/env python3
"""Export the reachable legacy in-app manual as a UI-neutral JSON snapshot.

The v3.9.0.10 manual is embedded in ``UserManualWidget``.  During the Web UI
migration it remains the behavioural/content reference, so the Web client must
not maintain an abbreviated second manual.  This build-time exporter reads the
Python AST without importing CustomTkinter and serializes only the eleven tabs
that ``show_manual`` actually creates.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.app_version import (
    RELEASE_BUILD_LABEL,
    RELEASE_DISPLAY_LABEL,
    RELEASE_DISPLAY_PATCH,
    RELEASE_PATCH,
    RELEASE_VERSION,
)
from ui.ai_custom_guidance import build_ai_custom_provider_guide, build_ai_custom_safe_flow
from ui.live_trading_guidance import build_live_trading_guide


SOURCE = ROOT / "ui" / "widgets" / "user_manual_widget.py"
OUTPUT = ROOT / "docs" / "USER_MANUAL_SECTIONS.json"

# This is the order used by UserManualWidget.show_manual().  Defined-but-hidden
# legacy methods are deliberately excluded; a source string is not a visible tab.
REACHABLE_METHODS = (
    "create_intro_tab",
    "create_live_trading_guide_tab",
    "create_dashboard_guide_tab",
    "create_financial_intelligence_guide_tab",
    "create_how_ai_works_tab",
    "create_multi_exchange_tab",
    "create_stock_etf_tab",
    "create_assistant_guide_tab",
    "create_custom_strategy_guide_tab",
    "create_alpha_arena_tab",
    "create_updates_tab",
)

SECTION_IDS = {
    "create_intro_tab": "intro",
    "create_live_trading_guide_tab": "live",
    "create_dashboard_guide_tab": "settings",
    "create_financial_intelligence_guide_tab": "intelligence",
    "create_how_ai_works_tab": "runtime",
    "create_multi_exchange_tab": "assets",
    "create_stock_etf_tab": "stocks",
    "create_assistant_guide_tab": "assistant",
    "create_custom_strategy_guide_tab": "custom",
    "create_alpha_arena_tab": "arena",
    "create_updates_tab": "updates",
}

SAFE_NAMES: dict[str, Any] = {
    "RELEASE_BUILD_LABEL": RELEASE_BUILD_LABEL,
    "RELEASE_DISPLAY_LABEL": RELEASE_DISPLAY_LABEL,
    "RELEASE_DISPLAY_PATCH": RELEASE_DISPLAY_PATCH,
    "RELEASE_PATCH": RELEASE_PATCH,
    "RELEASE_VERSION": RELEASE_VERSION,
}


def _evaluate(node: ast.AST, values: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in values:
            return values[node.id]
        if node.id in SAFE_NAMES:
            return SAFE_NAMES[node.id]
        raise ValueError(f"unsupported manual name: {node.id}")
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for item in node.values:
            if isinstance(item, ast.Constant):
                parts.append(str(item.value))
            elif isinstance(item, ast.FormattedValue):
                value = _evaluate(item.value, values)
                if item.format_spec is not None:
                    value = format(value, str(_evaluate(item.format_spec, values)))
                parts.append(str(value))
            else:
                raise ValueError(f"unsupported f-string item: {type(item).__name__}")
        return "".join(parts)
    if isinstance(node, ast.Call):
        args = [_evaluate(arg, values) for arg in node.args]
        if isinstance(node.func, ast.Name):
            builders = {
                "build_live_trading_guide": build_live_trading_guide,
                "build_ai_custom_safe_flow": build_ai_custom_safe_flow,
                "build_ai_custom_provider_guide": build_ai_custom_provider_guide,
            }
            if node.func.id not in builders:
                raise ValueError(f"unsupported manual builder: {node.func.id}")
            return builders[node.func.id](*args)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "replace":
            return str(_evaluate(node.func.value, values)).replace(*map(str, args))
        raise ValueError("unsupported manual call")
    raise ValueError(f"unsupported manual expression: {type(node).__name__}")


def _extract_method(method: ast.FunctionDef) -> tuple[str, str]:
    values: dict[str, Any] = {}
    tab_label = ""
    inserted: str | None = None
    for statement in method.body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name) and target.id == "tab" and isinstance(statement.value, ast.Call):
                    call = statement.value
                    if isinstance(call.func, ast.Attribute) and call.func.attr == "add" and call.args:
                        tab_label = str(_evaluate(call.args[0], values))
                elif isinstance(target, ast.Name) and target.id == "content":
                    values["content"] = _evaluate(statement.value, values)
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            call = statement.value
            if isinstance(call.func, ast.Attribute) and call.func.attr == "insert" and len(call.args) >= 2:
                inserted = str(_evaluate(call.args[1], values))
    if not tab_label or inserted is None:
        raise ValueError(f"manual method is not exportable: {method.name}")
    return tab_label, inserted.strip()


def _render_placeholders(content: str) -> str:
    """Apply the same shared guidance substitutions as the legacy widget.

    The legacy widget performs these replacements after the individual tab
    builder returns.  The AST exporter deliberately does not execute the
    CustomTkinter widget, so it must reproduce that final, user-visible step
    before serializing the Web UI manual snapshot.
    """
    return (
        content
        .replace("{{AI_CUSTOM_SAFE_FLOW}}", build_ai_custom_safe_flow())
        .replace("{{AI_CUSTOM_PROVIDER_GUIDE}}", build_ai_custom_provider_guide())
    )


def _render_release_boundary(section_id: str, content: str) -> str:
    """Keep the exported product boundary deterministic for this source version."""
    if section_id != "custom":
        return content

    marker = f"[v{RELEASE_VERSION} 제품 범위 / 운영 게이트 / 향후 생태계]"
    line = f"• v{RELEASE_VERSION} Windows stable/latest 공개 제품"
    content = re.sub(
        r"\[v\d+\.\d+\.\d+\.\d+ 소스 후보 수준 / 운영 게이트 / 향후 생태계\]",
        marker,
        content,
        count=1,
    )
    content = re.sub(
        r"^• v\d+\.\d+\.\d+\.\d+ 소스 후보, Windows 공개 v\d+\.\d+\.\d+\.\d+$",
        line,
        content,
        count=1,
        flags=re.MULTILINE,
    )
    content = re.sub(
        r"• v\d+\.\d+\.\d+\.\d+ 현재 앱 소스 후보에서 제공:",
        f"• v{RELEASE_VERSION} 현재 앱에서 제공:",
        content,
        count=1,
    )
    if line in content:
        return content
    if marker in content:
        return content.replace(marker, f"{marker}\n{line}", 1)
    return f"{content.rstrip()}\n\n{marker}\n{line}\n"


def build_snapshot() -> dict[str, Any]:
    source_text = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source_text, filename=str(SOURCE))
    widget = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "UserManualWidget"
    )
    methods = {
        node.name: node for node in widget.body
        if isinstance(node, ast.FunctionDef)
    }
    sections = []
    for method_name in REACHABLE_METHODS:
        label, content = _extract_method(methods[method_name])
        content = _render_placeholders(content)
        section_id = SECTION_IDS[method_name]
        content = _render_release_boundary(section_id, content)
        sections.append({
            "id": section_id,
            "label": label,
            "content": content,
            "legacy_method": method_name,
        })
    return {
        "schema_version": "1.0.0",
        "release_version": RELEASE_VERSION,
        "source": "ui/widgets/user_manual_widget.py",
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "sections": sections,
    }


def main() -> int:
    payload = build_snapshot()
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"[MANUAL_EXPORT] {len(payload['sections'])} sections -> {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
