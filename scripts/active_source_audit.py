#!/usr/bin/env python3
"""활성 소스·격리·증권 계약·문서 경계를 반복 검증한다."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EXCLUDED_PARTS = {".venv", "build", "dist", "data", "__pycache__", ".pytest_cache"}
FORBIDDEN_SOURCE_MARKERS = ("_Conflict.py", ".broken.py")
FORBIDDEN_SOURCE_NAMES = {
    "ai_learning_widget_fixed.py",
    "ai_learning_widget_safe.py",
    "ai_report_widget_real.py",
    "chart_screenshot_widget_fixed.py",
    "dashboard_fix.py",
    "demo_mode_widget.py",
}


def _active_python_files() -> Iterable[Path]:
    for path in ROOT.rglob("*.py"):
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        if "docs" in path.parts or "legacy" in path.parts:
            continue
        yield path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dashboard_dead_methods(files: List[Path]) -> List[str]:
    dashboard_path = ROOT / "ui" / "dashboard_modern.py"
    dashboard_tree = ast.parse(dashboard_path.read_text(encoding="utf-8"))
    dashboard_class = next(
        node for node in dashboard_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ModernDashboard"
    )
    methods = {
        node.name
        for node in dashboard_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    references: Set[str] = set()
    string_references: Set[str] = set()
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in methods:
                references.add(node.attr)
            elif isinstance(node, ast.Name) and node.id in methods:
                references.add(node.id)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in methods:
                string_references.add(node.value)
    return sorted(methods - references - string_references)


def _silent_except_count(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler)
        and len(node.body) == 1
        and isinstance(node.body[0], ast.Pass)
    )


def _validate_quarantine() -> Dict[str, Any]:
    manifest_path = ROOT / "config" / "source_quarantine_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    quarantine_root = (ROOT / manifest["quarantine_root"]).resolve()
    failures = []
    for artifact in manifest.get("artifacts", []):
        path = quarantine_root / artifact["path"]
        if not path.is_file():
            failures.append(f"missing:{artifact['path']}")
            continue
        actual = _sha256(path)
        if actual != artifact.get("sha256"):
            failures.append(f"hash_mismatch:{artifact['path']}")
    return {
        "root": str(quarantine_root),
        "artifact_count": len(manifest.get("artifacts", [])),
        "failures": failures,
    }


def main() -> int:
    files = list(_active_python_files())
    syntax_failures = []
    for path in files:
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            syntax_failures.append(f"{path.relative_to(ROOT)}:{exc.lineno}")

    forbidden = [
        str(path.relative_to(ROOT))
        for path in files
        if any(marker in path.name for marker in FORBIDDEN_SOURCE_MARKERS)
        or path.name in FORBIDDEN_SOURCE_NAMES
    ]
    dead_methods = _dashboard_dead_methods(files) if not syntax_failures else []
    quarantine = _validate_quarantine()

    from trading.exchanges.exchange_factory import SUPPORTED_API_VERSIONS

    expected_brokers = {
        "kiwoom": {"openapi_plus": {"pykiwoom"}, "mock": {"mock"}},
        "shinhan": {"partner_rest": {"shinhan_openapi_v2"}, "mock": {"mock"}},
        "miraeAsset": {"partner_rest": {"mirae_partner_profile"}, "mock": {"mock"}},
        "koreaInvestment": {"rest": {"kis_openapi_v1"}, "mock": {"mock"}},
    }
    actual_brokers = {
        broker: {api_type: set(versions) for api_type, versions in types.items()}
        for broker, types in SUPPORTED_API_VERSIONS.items()
    }
    broker_contract_ok = actual_brokers == expected_brokers

    required_docs = [
        "docs/ARCHITECTURE_AUDIT_2026-08-01.md",
        "docs/STOCK_BROKER_CONTRACTS_v3.9.0.5.md",
        "docs/SOURCE_QUARANTINE_MANIFEST_20260801.md",
        "docs/TEST_STATUS.md",
        "docs/MASTER_DOCUMENTATION.md",
    ]
    missing_docs = [path for path in required_docs if not (ROOT / path).is_file()]

    result = {
        "status": "PASS",
        "active_python_files": len(files),
        "syntax_failures": syntax_failures,
        "forbidden_active_sources": forbidden,
        "dashboard_definition_only_methods": dead_methods,
        "silent_except_baseline": {
            "ui/dashboard_modern.py": _silent_except_count(ROOT / "ui" / "dashboard_modern.py"),
            "trading/unified_trader.py": _silent_except_count(ROOT / "trading" / "unified_trader.py"),
        },
        "quarantine": quarantine,
        "broker_contract_ok": broker_contract_ok,
        "missing_required_docs": missing_docs,
    }
    blockers = (
        syntax_failures
        or forbidden
        or dead_methods
        or quarantine["failures"]
        or not broker_contract_ok
        or missing_docs
    )
    if blockers:
        result["status"] = "FAIL"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
