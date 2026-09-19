#!/usr/bin/env python3
"""Fail a Web sidecar build if a legacy desktop UI module was collected."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
from typing import Any


FORBIDDEN_ROOTS = {"main", "ui", "customtkinter", "tkinter", "PyQt5", "pykiwoom"}
REQUIRED_AI_RUNTIME_MODULES = {"openai", "httpx", "jiter"}
REQUIRED_EXACT_RUNTIME_MODULES = {"trading.notifications"}


def _walk_module_entries(value: Any):
    if (
        isinstance(value, (list, tuple))
        and len(value) >= 3
        and isinstance(value[0], str)
        and value[2] in {"PYMODULE", "PYSOURCE", "EXTENSION"}
    ):
        yield value[0]
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _walk_module_entries(item)
    elif isinstance(value, dict):
        for item in value.items():
            yield from _walk_module_entries(item)


def forbidden_modules(toc_path: Path) -> list[str]:
    payload = ast.literal_eval(toc_path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for value in _walk_module_entries(payload):
        normalized = value.replace("\\", "/")
        module = normalized[:-4].replace("/", ".") if normalized.endswith(".pyc") else normalized
        root = module.split(".", 1)[0]
        if root in FORBIDDEN_ROOTS:
            found.add(module)
    return sorted(found)


def _collected_runtime_modules(toc_path: Path) -> set[str]:
    payload = ast.literal_eval(toc_path.read_text(encoding="utf-8"))
    collected = set()
    for raw_module in _walk_module_entries(payload):
        normalized = raw_module.replace("\\", "/")
        module = normalized[:-4].replace("/", ".") if normalized.endswith(".pyc") else normalized.replace("/", ".")
        collected.add(module)
    return collected


def missing_required_ai_runtime_modules(toc_path: Path) -> list[str]:
    """Backward-compatible AI provider root check used by existing audits."""
    collected_roots = {module.split(".", 1)[0] for module in _collected_runtime_modules(toc_path)}
    return sorted(REQUIRED_AI_RUNTIME_MODULES.difference(collected_roots))


def missing_required_runtime_modules(toc_path: Path) -> list[str]:
    collected = _collected_runtime_modules(toc_path)
    return sorted(
        set(missing_required_ai_runtime_modules(toc_path))
        | REQUIRED_EXACT_RUNTIME_MODULES.difference(collected)
    )


def verify_spec(spec_path: Path) -> list[str]:
    text = spec_path.read_text(encoding="utf-8")
    errors = []
    if "aiautotrade.spec" in text or "exec(compile(" in text:
        errors.append("sidecar spec derives from legacy spec")
    for module in FORBIDDEN_ROOTS:
        if f'"{module}"' not in text and f"'{module}'" not in text:
            errors.append(f"missing explicit exclude: {module}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", default="noahai_web_engine.spec")
    parser.add_argument("--toc", default="build/noahai_web_engine/Analysis-00.toc")
    parser.add_argument("--spec-only", action="store_true")
    args = parser.parse_args()
    errors = verify_spec(Path(args.spec))
    toc_path = Path(args.toc)
    if not args.spec_only:
        if not toc_path.exists():
            errors.append(f"analysis TOC missing: {toc_path}")
        else:
            forbidden = forbidden_modules(toc_path)
            if forbidden:
                errors.append("forbidden modules collected: " + ", ".join(forbidden[:40]))
            missing_runtime = missing_required_runtime_modules(toc_path)
            if missing_runtime:
                errors.append("required runtime modules missing: " + ", ".join(missing_runtime))
    if errors:
        for error in errors:
            print(f"[WEB_ENGINE_AUDIT] FAIL: {error}")
        return 1
    print("[WEB_ENGINE_AUDIT] PASS: legacy desktop UI and Kiwoom x86-only modules=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
