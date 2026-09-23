#!/usr/bin/env python3
"""Build local, unapproved research packages; never start or register a strategy.

The supplied execution history describes outcomes, not the trader's entry rules.
All numeric conditions below are new research hypotheses, not recovered rules.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.noah_strategy_ir import NoahStrategyIR
from trading.strategy_package import build_strategy_package, export_strategy_package

CATALOG = {
    "01_pullback_5m": ("추세 눌림목", "5m", 0.5, 1.0),
    "02_momentum_15m": ("거래량 모멘텀", "15m", 0.8, 2.0),
    "03_trend_1h": ("추세 유지", "1h", 1.5, 4.0),
}


def condition(field, operator, value):
    return {"field": field, "operator": operator,
            "value_field" if operator.endswith("_field") or operator.startswith("crosses_") else "value": value}


def indicator(name, period, timeframe):
    return {"indicator": name, "period": period, "timeframe": timeframe, "source": "close"}


def make_rules(key):
    title, timeframe, sl, tp = CATALOG[key]
    ema20, ema50, ema200 = [indicator("ema", p, timeframe) for p in (20, 50, 200)]
    entries = {}
    for direction in ("LONG", "SHORT"):
        long = direction == "LONG"
        compare = "gt_field" if long else "lt_field"
        cross = "crosses_above" if long else "crosses_below"
        terms = [condition(ema50, compare, ema200)]
        if key == "01_pullback_5m":
            terms += [condition("close", cross, ema20),
                      condition("rsi", "gte", 45 if long else 35),
                      condition("rsi", "lte", 65 if long else 55),
                      condition("volume_ratio", "gte", 1.0)]
        elif key == "02_momentum_15m":
            terms += [condition("close", cross, ema20),
                      condition("rsi", "gte", 55 if long else 25),
                      condition("rsi", "lte", 75 if long else 45),
                      condition("volume_ratio", "gte", 1.5)]
        else:
            terms += [condition(ema20, cross, ema50),
                      condition("close", compare, ema20),
                      condition("rsi", "gte", 50 if long else 25),
                      condition("rsi", "lte", 75 if long else 50),
                      condition("volume_ratio", "gte", 1.0)]
        entries[direction] = {"all": terms, "any": []}

    # Direction-specific exit branches are expressed in the supported boolean tree.
    exit_expression = {"type": "group", "operator": "or", "children": [
        {"type": "group", "operator": "and", "children": [
            {"type": "condition", "condition": condition("signal", "eq", direction)},
            {"type": "condition", "condition": condition(
                "close", "lt_field" if direction == "LONG" else "gt_field", ema50)},
        ]} for direction in ("LONG", "SHORT")
    ]}
    return {
        "entry": f"{timeframe} 확정봉의 EMA·RSI·거래량으로 {title} 양방향 후보 생성. 수치는 신규 연구 가정.",
        "exit": f"전략 TP {tp}% / SL {sl}%, 또는 LONG 종가 EMA50 하회·SHORT 종가 EMA50 상회. 기본 안전 청산은 유지.",
        "stop_loss": f"{sl}%", "take_profit": f"{tp}%",
        "position_size": "연구 기본값: 증거금 5% 상한·1배, 손절거리 기반 위험예산 0.1%. 비용·갭 손실은 별도.",
        "market_conditions": ["전용 봉의 EMA 방향·가격·거래량 조건을 만족할 때만 진입"],
        "market_regimes": ["all"], "regime_scope": "symbol", "regime_transition": "pause",
        "target_scope": "exchange:binance",
        "signal_mode": "independent", "entry_signal": "",
        "decision_timeframe": timeframe, "execution_timeframe": timeframe,
        "independent_entries": entries,
        "executable_entry": {"all": [], "any": []},
        "executable_exit": {"expression": exit_expression},
        "exit_policy": {"mode": "strategy_owned"},
        "engine_settings": {"_unit": "percent_points", "tp_percent": tp,
                            "sl_percent": sl, "position_size": 0.05, "leverage": 1},
        "risk_model": {"risk_per_trade_percent": 0.1, "max_margin_usage_percent": 5.0,
                       "max_notional_percent": 5.0, "max_leverage": 1},
        "source_grounding": {
            "status": "research_hypothesis", "original_strategy_recovered": False,
            "summary": "공개자료에서 영감을 받은 독립 연구 모델. 워뇨띠 본인 작성·승인·공식 전략이 아님.",
        },
        "source_rule_trace": {
            "entry": {"status": "research_hypothesis", "evidence": [
                "90일 서한: 캔들·거래량·추세 해석. 2018~2021 진입식과 동일하다는 근거는 없음.",
                "3,537 BTC의 기록.pdf p6~8: 실제 판단 로직 복원이 아닌 제안임을 명시.",
                "EMA 기간·봉 주기·RSI 범위·거래량 배수는 NoahAI 연구 설계값이며 원문 추출값이 아님.",
            ]},
            "exit": {"status": "research_hypothesis", "evidence": [
                "고정 TP/SL과 EMA 이탈 청산은 신규 가정. PDF의 분할익절·트레일링 제안과 다른 기본형.",
            ]},
        },
        "research_notes": {
            "reference": "3,537 BTC의 기록.pdf; aoa_public_2021-12-31_with_letter",
            "original_market": "BitMEX inverse/quanto contracts (2018–2021)",
            "implementation_market": "Binance crypto research baseline; not an inverse-contract reproduction",
            "suggested_symbols": ["BTCUSDT", "ETHUSDT"],
            "symbol_allowlist_enforced_by_package": False,
            "symbol_scope_note": "현재 패키지는 기관 범위만 제한. BTC/ETH 전용은 기관 종목 선택에서 별도 확인해야 함.",
            "excluded": ["maker-first and timeout-to-market routing", "pyramiding",
                         "confidence-based size increases", "partial take profit and trailing exits",
                         "order-book signals", "macro timing", "account-growth frequency switching"],
            "historical_performance_inherited": False,
            "live_tested": False,
            "limitations": "원본의 정신적 절제·체결 기술·성과를 복제하지 않는다. PAPER 및 별도 실기관 검증 필요.",
        },
    }


def make_version(key):
    pipeline = CustomStrategyPipeline()  # No storage path, no user account.
    version = pipeline.submit(name=f"워뇨띠 공개자료 연구 · {CATALOG[key][0]} ({CATALOG[key][1]})",
                              rules=make_rules(key), source_kind="text",
                              source_reference="3,537 BTC의 기록.pdf",
                              strategy_key=f"aoa_research_{key}")
    if version["missing_conditions"] or not version["execution_readiness"]["ready"]:
        raise ValueError(f"Incomplete strategy: {key}: {version}")
    if NoahStrategyIR.validate(version["strategy_ir"])["status"] != "supported":
        raise ValueError(f"Unsupported strategy: {key}")
    # Browser JSON.parse/stringify turns 1.0 into 1. Build the signed IR using
    # the same representation, rather than weakening any hash check on import.
    def web_numbers(value):
        if isinstance(value, dict):
            return {k: web_numbers(v) for k, v in value.items()}
        if isinstance(value, list):
            return [web_numbers(v) for v in value]
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value
    version["rules"] = web_numbers(version["rules"])
    version["strategy_ir"] = NoahStrategyIR.compile(
        version["rules"], source_kind="text", source_reference="3,537 BTC의 기록.pdf")
    version["ir_hash"] = version["strategy_ir"]["integrity_sha256"]
    version["ir_validation"] = NoahStrategyIR.validate(version["strategy_ir"])
    return version


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def build(output, pdf=None, shared=None):
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"kind": "local_research_candidates", "author_affiliation": "unofficial",
                "approved": False, "paper_tested": False, "live_tested": False,
                "source_files": [], "strategies": []}
    for source in ([pdf] if pdf else []) + (sorted(shared.iterdir()) if shared else []):
        if source.is_file():
            manifest["source_files"].append({"name": source.name, "bytes": source.stat().st_size,
                                             "sha256": digest(source)})
    for key in CATALOG:
        version = make_version(key)
        package = build_strategy_package(version, passport={})
        target = output / f"{key}.noahstrategy"
        if target.exists():
            raise FileExistsError(f"Use a new output directory; existing package preserved: {target}")
        export_strategy_package(target, package)
        manifest["strategies"].append({"file": target.name, "name": version["name"],
                                      "rules_sha256": version["strategy_ir"]["canonical_rules_sha256"],
                                      "file_sha256": digest(target), "execution_ready": True,
                                      "performance_validated": False})
    write_json(output / "manifest.json", manifest)
    return manifest


def public_replay(output):
    """Optional read-only fixed-window smoke test, not validation/passport promotion."""
    from trading.custom_strategy_validator import run_historical_replay
    from trading.strategy_package import import_strategy_package
    records = []
    for key, (_, timeframe, _, _) in CATALOG.items():
        rules = import_strategy_package(output / f"{key}.noahstrategy")["rules"]
        for symbol in ("BTCUSDT", "ETHUSDT"):
            url = "https://fapi.binance.com/fapi/v1/klines?" + urlencode({
                "symbol": symbol, "interval": timeframe, "startTime": 1704067200000, "limit": 1000})
            with urlopen(url, timeout=25) as response:
                candles = json.load(response)
            if not isinstance(candles, list) or len(candles) != 1000:
                raise ValueError("Expected 1,000 public candles; no replacement data allowed")
            evidence_file = output / f"{key}_{symbol}_candles.json"
            write_json(evidence_file, candles)
            result = run_historical_replay(rules, candles, base_timeframe=timeframe,
                                           fee_rate=0.0005, slippage_bps=2, spread_bps=1, horizon=24)
            result["research_boundary"] = {
                "purpose": "real_candle_execution_smoke_only", "source": url,
                "candles_sha256": digest(evidence_file), "funding_modeled": False,
                "fills_observed": False, "passport_updated": False,
                "horizon_24_is_test_only_not_live_rule": True,
                "returns_are_unit_notional_not_account_returns": True,
                "fees_are_scenario_not_user_fee_schedule": True,
            }
            write_json(output / f"{key}_{symbol}_replay.json", result)
            records.append({"strategy": key, "symbol": symbol, "candles": result["candles"],
                            "decisions": result["decisions"], "warmup": result["warmup_candles"],
                            "chart_status": result["replay_visualization"]["status"]})
    write_json(output / "public_replay_summary.json", {"performance_validated": False, "runs": records})
    return records


def verify_artifacts(output):
    """Re-read delivered bytes, renderer conversion, candle and accounting evidence."""
    from trading.strategy_package import verify_strategy_package
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    checked = []
    for record in manifest["strategies"]:
        path = output / record["file"]
        assert digest(path) == record["file_sha256"]
        browser = subprocess.run([
            "node", "-e", "let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>process.stdout.write(JSON.stringify(JSON.parse(s))))",
        ], input=path.read_text(encoding="utf-8"), text=True, capture_output=True, check=True)
        package = json.loads(browser.stdout)
        assert verify_strategy_package(package)["valid"]
        assert package["passport"] == {} and not package["import_contract"]["active"]
        checked.append(path.name)
    replay_checks = []
    for path in sorted(output.glob("*_replay.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        evidence = output / path.name.replace("_replay.json", "_candles.json")
        candles = json.loads(evidence.read_text(encoding="utf-8"))
        assert digest(evidence) == result["research_boundary"]["candles_sha256"]
        assert len(candles) == result["candles"] == 1000
        assert all(candles[i][0] < candles[i + 1][0] for i in range(len(candles) - 1))
        assert result["warmup_candles"] == 200
        chart = result["replay_visualization"]
        assert chart["status"] == "available" and chart["simulation_only"]
        for trade in result["trades"]:
            assert 0 <= trade["entry_index"] < trade["exit_index"] < len(candles)
            assert abs(float(candles[trade["entry_index"]][4]) - trade["entry_price"]) < 1e-8
            assert abs(trade["gross_pnl_percent"] - trade["cost_percent"] - trade["net_pnl_percent"]) < 2e-6
            assert abs(trade["cost_percent"] - 0.15) < 1e-8
        assert len(result["trades"]) == result["decisions"]
        assert not result["research_boundary"]["passport_updated"]
        replay_checks.append({"file": path.name, "trades": result["decisions"], "passed": True})
    report = {"package_checks": checked, "replay_checks": replay_checks,
              "passed": True, "external_account_tested": False, "paper_tested": False,
              "live_tested": False, "performance_validated": False}
    write_json(output / "artifact_verification.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--shared", type=Path)
    parser.add_argument("--public-replay", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.pdf, args.shared), ensure_ascii=False, indent=2))
    if args.public_replay:
        print(json.dumps(public_replay(args.output), ensure_ascii=False, indent=2))
    print(json.dumps(verify_artifacts(args.output), ensure_ascii=False, indent=2))
