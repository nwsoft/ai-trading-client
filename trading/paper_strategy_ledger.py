"""Account-scoped append-only outcomes for AI Custom PAPER positions."""

from __future__ import annotations

import json
import hashlib
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from path_utils import get_app_data_dir


_LOCK = threading.RLock()
_READ_CHUNK_SIZE = 64 * 1024


def ledger_path() -> Path:
    return Path(get_app_data_dir()) / "strategy_paper_outcomes.jsonl"


def paper_position_execution_evidence(
    position: Any,
    *,
    exit_reason: str = "",
    entry_reason: str = "",
) -> dict[str, Any]:
    """Extract a bounded, non-secret execution snapshot from a PAPER position.

    The full strategy source, account balance and exchange order identifiers do
    not belong in the validation ledger.  Only values that explain this fill
    are copied; missing legacy values remain missing instead of becoming zero.
    """
    if isinstance(position, dict):
        get = position.get
    else:
        get = lambda key, default=None: getattr(position, key, default)
    policy = dict(get("exit_policy", {}) or {})
    effective = dict(policy.get("effective") or {})
    last_exit = dict(policy.get("last_exit_decision") or {})
    entry_evidence = dict(get("entry_evidence", {}) or {})
    candidate = dict(entry_evidence.get("trade_candidate") or {})
    sizing = dict(entry_evidence.get("position_sizing") or {})
    contract_hash = str(entry_evidence.get("strategy_contract_hash") or "")
    if not contract_hash:
        rules = dict(get("custom_strategy_rules", {}) or {})
        if rules:
            canonical = json.dumps(rules, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            contract_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "leverage": get("leverage"),
        "entry_reason": str(
            entry_reason
            or entry_evidence.get("reason")
            or candidate.get("reason")
            or ""
        ),
        "entry_market_regime": str(candidate.get("market_regime") or ""),
        "entry_regime_scope": str(candidate.get("regime_scope") or ""),
        "entry_signal_source": str(
            entry_evidence.get("signal_source") or candidate.get("signal_source") or ""
        ),
        "sizing_policy_reason": str(sizing.get("reason") or ""),
        "sizing_target_notional": sizing.get("target_notional"),
        "sizing_final_notional": sizing.get("final_notional"),
        "sizing_limiting_reasons": list(sizing.get("limiting_reasons") or [])[:20],
        "exit_reason": str(exit_reason or last_exit.get("reason") or ""),
        "tp_price": get("tp_price"),
        "sl_price": get("sl_price"),
        "effective_tp_fraction": effective.get("tp_fraction"),
        "effective_sl_fraction": effective.get("sl_fraction"),
        "exit_policy_source": str(effective.get("source") or ""),
        "exit_policy_reason": str(effective.get("reason") or ""),
        "smart_exit_source": str(last_exit.get("source") or ""),
        "smart_exit_reason": str(last_exit.get("reason") or ""),
        "strategy_contract_hash": contract_hash,
    }


def record_paper_strategy_outcome(
    *, scope: str, exchange: str, symbol: str, strategy_key: str,
    version_id: str, opened_at: Any, closed_at: Any,
    net_pnl: float, fees: float = 0.0, guardrail_violations: int = 0,
    position_id: str = "", gross_pnl: float | None = None,
    net_pnl_percent: float | None = None, entry_price: float | None = None,
    exit_price: float | None = None, quantity: float | None = None,
    side: str = "", quote_currency: str = "",
    estimated_slippage: float | None = None,
    estimated_taxes: float | None = None,
    fee_rate: float | None = None, tax_rate: float | None = None,
    slippage_rate: float | None = None,
    calculation_status: str = "valid",
    cost_calculation_status: str = "recorded_contract",
    cost_policy_issues: list[str] | None = None,
    strategy_scope: str = "",
    leverage: int | None = None,
    entry_reason: str = "",
    entry_market_regime: str = "",
    entry_regime_scope: str = "",
    entry_signal_source: str = "",
    sizing_policy_reason: str = "",
    sizing_target_notional: float | None = None,
    sizing_final_notional: float | None = None,
    sizing_limiting_reasons: list[str] | None = None,
    exit_reason: str = "",
    tp_price: float | None = None,
    sl_price: float | None = None,
    effective_tp_fraction: float | None = None,
    effective_sl_fraction: float | None = None,
    exit_policy_source: str = "",
    exit_policy_reason: str = "",
    smart_exit_source: str = "",
    smart_exit_reason: str = "",
    strategy_contract_hash: str = "",
) -> dict[str, Any]:
    # Every simulated close belongs in the user-visible PAPER history. Empty
    # strategy identifiers mean the default NoahAI strategy; only rows carrying
    # both identifiers are eligible for AI Custom version validation.
    execution_scope = "binance" if str(scope).lower() == "binance" else "unified"
    normalized_strategy_scope = str(strategy_scope or "").strip().lower()
    if normalized_strategy_scope not in {"binance", "unified"}:
        normalized_strategy_scope = execution_scope
    normalized_position_id = str(position_id or "").strip()
    if normalized_position_id:
        identity = "|".join((execution_scope, str(exchange or "").lower(), normalized_position_id))
        event_id = f"paper_outcome_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]}"
    else:
        event_id = f"paper_outcome_{uuid4().hex}"
    row = {
        "event_id": event_id,
        "scope": execution_scope,
        "execution_scope": execution_scope,
        "strategy_scope": normalized_strategy_scope,
        "exchange": str(exchange or "").lower(),
        "symbol": str(symbol or ""),
        "strategy_key": str(strategy_key),
        "version_id": str(version_id),
        "position_id": normalized_position_id,
        "opened_at": opened_at.isoformat() if hasattr(opened_at, "isoformat") else str(opened_at or ""),
        "closed_at": closed_at.isoformat() if hasattr(closed_at, "isoformat") else str(closed_at or datetime.now(timezone.utc).isoformat()),
        "net_pnl": float(net_pnl or 0.0),
        "fees": max(0.0, float(fees or 0.0)),
        "gross_pnl": None if gross_pnl is None else float(gross_pnl),
        "net_pnl_percent": None if net_pnl_percent is None else float(net_pnl_percent),
        "entry_price": None if entry_price is None else float(entry_price),
        "exit_price": None if exit_price is None else float(exit_price),
        "quantity": None if quantity is None else float(quantity),
        "leverage": None if leverage is None else max(1, int(leverage)),
        "side": str(side or "").upper(),
        "quote_currency": str(quote_currency or "").upper(),
        "entry_reason": str(entry_reason or "")[:500],
        "entry_market_regime": str(entry_market_regime or "")[:80],
        "entry_regime_scope": str(entry_regime_scope or "")[:80],
        "entry_signal_source": str(entry_signal_source or "")[:160],
        "sizing_policy_reason": str(sizing_policy_reason or "")[:160],
        "sizing_target_notional": (
            None if sizing_target_notional is None else max(0.0, float(sizing_target_notional))
        ),
        "sizing_final_notional": (
            None if sizing_final_notional is None else max(0.0, float(sizing_final_notional))
        ),
        "sizing_limiting_reasons": [
            str(item)[:160]
            for item in list(sizing_limiting_reasons or [])[:20]
            if str(item).strip()
        ],
        "exit_reason": str(exit_reason or "")[:500],
        "tp_price": None if tp_price is None else float(tp_price),
        "sl_price": None if sl_price is None else float(sl_price),
        "effective_tp_fraction": (
            None if effective_tp_fraction is None else max(0.0, float(effective_tp_fraction))
        ),
        "effective_sl_fraction": (
            None if effective_sl_fraction is None else max(0.0, float(effective_sl_fraction))
        ),
        "exit_policy_source": str(exit_policy_source or "")[:160],
        "exit_policy_reason": str(exit_policy_reason or "")[:500],
        "smart_exit_source": str(smart_exit_source or "")[:160],
        "smart_exit_reason": str(smart_exit_reason or "")[:500],
        "strategy_contract_hash": str(strategy_contract_hash or "")[:128],
        "estimated_slippage": None if estimated_slippage is None else max(0.0, float(estimated_slippage)),
        "estimated_taxes": None if estimated_taxes is None else max(0.0, float(estimated_taxes)),
        "fee_rate": None if fee_rate is None else max(0.0, float(fee_rate)),
        "tax_rate": None if tax_rate is None else max(0.0, float(tax_rate)),
        "slippage_rate": None if slippage_rate is None else max(0.0, float(slippage_rate)),
        "cost_schema_version": 2,
        "cost_calculation_status": str(cost_calculation_status or "unavailable"),
        "cost_policy_issues": [
            str(item)[:160]
            for item in list(cost_policy_issues or [])[:10]
            if str(item).strip()
        ],
        "calculation_status": str(calculation_status or "invalid").lower(),
        "calculation_schema_version": 3,
        "guardrail_violations": max(0, int(guardrail_violations or 0)),
        "execution_mode": "paper",
    }
    path = ledger_path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    return row


def paper_outcome_calculation_status(row: dict[str, Any] | None) -> str:
    """Return whether a PAPER row can safely participate in PnL statistics."""
    value = dict(row or {})
    explicit = str(value.get("calculation_status") or "").strip().lower()
    if explicit in {"valid", "invalid", "legacy_unverified"}:
        return explicit
    # Unified rows before schema v2 silently wrote missing field names as zero.
    # The ledger alone cannot reconstruct them, so never count them as losses.
    if str(value.get("scope") or "").strip().lower() == "unified":
        return "legacy_unverified"
    # Legacy Binance used a separate, correct pnl_usdt write path.
    return "valid"


def normalize_paper_outcome_costs(row: dict[str, Any] | None) -> dict[str, Any]:
    """Expose an honest cost estimate for v3.9.1.19 Binance PAPER rows.

    That release stored entry/exit/quantity and gross PnL but wrote fee and
    slippage as literal zero.  The historical per-account override was not
    recorded, so the exact value cannot be claimed.  Reconstruct only rows
    that match that precise signature and label the result as an estimate
    under the then-documented default contract (0.04% round-trip fee and
    0.03% slippage).  The append-only source file is never rewritten.
    """
    value = dict(row or {})
    if str(value.get("cost_calculation_status") or "").strip():
        return value
    execution_scope = str(value.get("execution_scope") or value.get("scope") or "").lower()
    exchange = str(value.get("exchange") or "").lower()
    try:
        recorded_fees = float(value.get("fees") or 0.0)
        recorded_slippage = float(value.get("estimated_slippage") or 0.0)
        recorded_taxes = float(value.get("estimated_taxes") or 0.0)
    except (TypeError, ValueError):
        recorded_fees = recorded_slippage = recorded_taxes = 0.0
    if recorded_fees > 0.0 or recorded_slippage > 0.0 or recorded_taxes > 0.0:
        # 이미 비용이 기록된 구형 행은 gross/entry 정보가 없더라도 비용을
        # 다시 추정하지 않는다.
        value["cost_calculation_status"] = "recorded_legacy"
        return value
    try:
        entry_price = float(value.get("entry_price") or 0.0)
        quantity = float(value.get("quantity") or 0.0)
        gross = float(value.get("gross_pnl"))
        net = float(value.get("net_pnl"))
        fees = recorded_fees
        slippage = recorded_slippage
    except (TypeError, ValueError):
        value["cost_calculation_status"] = "unavailable"
        # 비용을 차감한 net PnL을 재구성할 근거가 없으므로 전략 승패·순손익
        # 통계에 확정값처럼 포함하지 않는다. 원본 값은 보존하고 조회 결과만
        # 과거 미확정으로 분리한다.
        if execution_scope == "binance" and exchange == "binance":
            value["calculation_status"] = "legacy_unverified"
        return value
    reconstructable = (
        execution_scope == "binance"
        and exchange == "binance"
        and paper_outcome_calculation_status(value) == "valid"
        and entry_price > 0.0 and quantity > 0.0
        and fees == 0.0 and slippage == 0.0
        and abs(net - gross) <= max(1e-10, abs(gross) * 1e-10)
    )
    if not reconstructable:
        value["cost_calculation_status"] = "recorded_legacy"
        return value
    notional = entry_price * quantity
    fee_rate = 0.0004
    slippage_rate = 0.0003
    estimated_fees = notional * fee_rate
    estimated_slippage = notional * slippage_rate
    reconstructed_net = gross - estimated_fees - estimated_slippage
    value.update({
        "fees": estimated_fees,
        "estimated_slippage": estimated_slippage,
        "net_pnl": reconstructed_net,
        "net_pnl_percent": (reconstructed_net / notional * 100.0) if notional else 0.0,
        "fee_rate": fee_rate,
        "slippage_rate": slippage_rate,
        "cost_schema_version": 1,
        "cost_calculation_status": "estimated_v39119_default_contract",
    })
    return value


def is_valid_paper_outcome(row: dict[str, Any] | None) -> bool:
    return paper_outcome_calculation_status(row) == "valid"


def paper_quote_currency(exchange: str, symbol: str) -> str:
    target = str(exchange or "").strip().lower()
    market = str(symbol or "").upper()
    krw_venues = {
        "upbit", "bithumb", "coinone", "kiwoom", "shinhan", "mirae", "miraeasset",
        "kis", "koreainvestment",
    }
    return "KRW" if target in krw_venues or "KRW" in market else "USDT"


def summarize_paper_outcomes(
    rows: list[dict[str, Any]], *, default_currency: str,
) -> dict[str, Any]:
    normalized = [
        {**dict(row), "calculation_status": paper_outcome_calculation_status(row)}
        for row in rows
    ]
    valid = [row for row in normalized if row["calculation_status"] == "valid"]
    winning = sum(1 for row in valid if float(row.get("net_pnl", 0.0) or 0.0) > 0)
    pnl_by_currency: dict[str, float] = {}
    fees_by_currency: dict[str, float] = {}
    for row in valid:
        currency = str(row.get("quote_currency") or default_currency).upper()
        pnl_by_currency[currency] = pnl_by_currency.get(currency, 0.0) + float(row.get("net_pnl", 0.0) or 0.0)
        fees_by_currency[currency] = fees_by_currency.get(currency, 0.0) + float(row.get("fees", 0.0) or 0.0)
    return {
        "rows": normalized,
        "closed_count": len(valid),
        "recorded_count": len(normalized),
        "unverified_count": len(normalized) - len(valid),
        "winning_count": winning,
        "win_rate": (winning / len(valid) * 100.0) if valid else None,
        "net_pnl": sum(float(row.get("net_pnl", 0.0) or 0.0) for row in valid),
        "fees": sum(float(row.get("fees", 0.0) or 0.0) for row in valid),
        "pnl_by_currency": pnl_by_currency,
        "fees_by_currency": fees_by_currency,
    }


def read_paper_strategy_outcomes(
    *, limit: int = 100_000, path: Path | None = None,
    sources: set[str] | None = None, start_epoch: float | None = None,
    end_epoch: float | None = None,
) -> list[dict[str, Any]]:
    """Select account/venue/time scope BEFORE applying the display row limit.

    Scan backwards in bounded chunks, retaining only matching records. Other
    venues and malformed lines cannot evict this venue's history. File order
    is not assumed to be timestamp order (imports can arrive late).
    """
    path = Path(path) if path is not None else ledger_path()
    if not path.exists():
        return []
    bounded_limit = max(1, min(int(limit), 100_000))
    aliases = {"miraeasset": "mirae", "koreainvestment": "kis"}
    def venue(value: Any) -> str:
        key = str(value or "").lower().replace("_", "")
        return aliases.get(key, key)
    allowed = {venue(item) for item in sources} if sources is not None else None
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    def accept(line: bytes) -> None:
        try:
            row = json.loads(line)
            if not isinstance(row, dict) or row.get("execution_mode") != "paper":
                return
            if allowed is not None and venue(row.get("exchange")) not in allowed:
                return
            event_id = str(row.get("event_id") or "")
            if event_id and event_id in seen:
                return
            if start_epoch is not None or end_epoch is not None:
                date = datetime.fromisoformat(str(row.get("closed_at") or "").replace("Z", "+00:00"))
                # Same legacy local-time contract as the statistics service.
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
                epoch = date.timestamp()
                if start_epoch is not None and epoch < start_epoch:
                    return
                if end_epoch is not None and epoch > end_epoch:
                    return
            output.append(normalize_paper_outcome_costs(row))
            if event_id:
                seen.add(event_id)
        except (ValueError, TypeError, UnicodeDecodeError):
            return
    with _LOCK:
        try:
            with path.open("rb") as handle:
                handle.seek(0, 2)
                position = handle.tell()
                remainder = b""
                while position > 0 and len(output) < bounded_limit:
                    size = min(_READ_CHUNK_SIZE, position)
                    position -= size
                    handle.seek(position)
                    pieces = (handle.read(size) + remainder).split(b"\n")
                    remainder = pieces[0]
                    for line in reversed(pieces[1:]):
                        if len(output) >= bounded_limit:
                            break
                        accept(line)
                if position == 0 and len(output) < bounded_limit:
                    accept(remainder)
        except OSError:
            return []
    return list(reversed(output))
