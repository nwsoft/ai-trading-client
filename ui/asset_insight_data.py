#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Asset-insight data normalization.

The asset dashboard must not treat accumulated trade notional as current
wealth.  Current balances are normalized by quote currency here; the trade DB
is used only for realised PnL and correlation samples.  Legacy databases that
do not have ``asset_type`` or ``entry_amount`` remain readable.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


CRYPTO_EXCHANGES = {
    "binance", "upbit", "bithumb", "bybit", "okx", "bitget",
}
STOCK_EXCHANGES = {
    "kiwoom", "shinhan", "miraasset", "miraeasset", "mirae_asset",
    "koreainvestment", "korea_investment", "korea-investment", "kis",
}


class AssetSnapshotStore:
    """Thread-safe SSOT for validated current account balance snapshots."""

    def __init__(self) -> None:
        self._crypto: Dict[str, Dict[str, Any]] = {}
        self._stock: Dict[str, Dict[str, Any]] = {}
        self._updated_at: Optional[str] = None
        self._lock = threading.RLock()

    @staticmethod
    def classify_source(source: str) -> str:
        normalized = str(source or "").strip().lower().replace("-", "").replace("_", "")
        stock = {name.replace("-", "").replace("_", "") for name in STOCK_EXCHANGES}
        return "stock" if normalized in stock else "crypto"

    def update(self, source: str, balance: Any, *, kind: Optional[str] = None) -> bool:
        if not isinstance(balance, dict) or not balance:
            return False
        status = str(balance.get("status", "ok") or "ok").strip().lower()
        if status in {"error", "failed", "disabled"}:
            return False
        source_key = str(source or "").strip()
        if not source_key:
            return False
        target_kind = str(kind or self.classify_source(source_key)).lower()
        with self._lock:
            target = self._stock if target_kind == "stock" else self._crypto
            target[source_key] = dict(balance)
            self._updated_at = datetime.now().isoformat(timespec="seconds")
        return True

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "crypto": {key: dict(value) for key, value in self._crypto.items()},
                "stock": {key: dict(value) for key, value in self._stock.items()},
                "updated_at": self._updated_at,
            }


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _unwrap_balance(balance: Any) -> Dict[str, Any]:
    if not isinstance(balance, dict):
        return {}
    nested = balance.get("balance")
    if isinstance(nested, dict):
        return nested
    return balance


def _first_number(data: Dict[str, Any], keys: Iterable[str]) -> float:
    normalized = {str(key).lower(): value for key, value in data.items()}
    for key in keys:
        if str(key).lower() in normalized:
            value = _number(normalized[str(key).lower()])
            if value != 0.0:
                return value
    return 0.0


def normalize_current_balances(
    crypto_balances: Dict[str, Any] | None,
    stock_balances: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Return currency-safe current-asset metrics from cached account balances."""
    by_asset_currency: Dict[str, Dict[str, float]] = {
        "암호화폐": {},
        "주식": {},
        "기타": {},
    }
    received_sources: List[str] = []
    unvalued_assets: List[Dict[str, Any]] = []

    for source, raw in (crypto_balances or {}).items():
        data = _unwrap_balance(raw)
        if not data:
            continue
        source_key = str(source or "").lower()
        usdt = _first_number(data, ("USDT", "TOTAL_USDT", "TOTAL", "EQUITY", "WALLET_BALANCE"))
        krw = _first_number(data, ("KRW",))
        # Korean spot venues report their account base in KRW; a generic total
        # from those adapters is therefore KRW, not USDT.
        if any(name in source_key for name in ("upbit", "bithumb")) and not krw:
            krw = _first_number(data, ("TOTAL", "TOTAL_ASSETS", "EQUITY"))
            usdt = 0.0
        reserved = {
            "USDT", "TOTAL_USDT", "TOTAL", "TOTAL_ASSETS", "EQUITY",
            "WALLET_BALANCE", "KRW", "STATUS", "ERROR", "MESSAGE",
        }
        for asset, raw_amount in data.items():
            asset_key = str(asset or "").upper()
            amount = _number(raw_amount)
            if asset_key not in reserved and amount > 0:
                unvalued_assets.append({
                    "source": str(source),
                    "asset": asset_key,
                    "amount": amount,
                })
        if usdt > 0:
            bucket = by_asset_currency["암호화폐"]
            bucket["USDT"] = bucket.get("USDT", 0.0) + usdt
        if krw > 0:
            bucket = by_asset_currency["암호화폐"]
            bucket["KRW"] = bucket.get("KRW", 0.0) + krw
        if usdt > 0 or krw > 0 or any(item.get("source") == str(source) for item in unvalued_assets):
            received_sources.append(str(source))

    for source, raw in (stock_balances or {}).items():
        data = _unwrap_balance(raw)
        if not data or str(data.get("status", "ok")).lower() == "error":
            continue
        total = _first_number(
            data,
            ("total_assets", "total_asset", "tot_evlu_amt", "net_asset", "equity"),
        )
        if total <= 0:
            total = _first_number(data, ("cash", "available_balance")) + _first_number(
                data, ("stock_eval", "evaluation_amount", "scts_evlu_amt")
            )
        if total > 0:
            bucket = by_asset_currency["주식"]
            bucket["KRW"] = bucket.get("KRW", 0.0) + total
            received_sources.append(str(source))

    currency_totals: Dict[str, float] = {}
    for values in by_asset_currency.values():
        for currency, amount in values.items():
            if amount > 0:
                currency_totals[currency] = currency_totals.get(currency, 0.0) + amount

    positive_currencies = [currency for currency, amount in currency_totals.items() if amount > 0]
    comparable_currency = positive_currencies[0] if len(positive_currencies) == 1 else None
    comparable_breakdown = {
        asset: float(values.get(comparable_currency, 0.0) or 0.0) if comparable_currency else 0.0
        for asset, values in by_asset_currency.items()
    }

    return {
        "has_current_data": bool(received_sources),
        "received_sources": received_sources,
        "unvalued_assets": unvalued_assets,
        "valuation_complete": not unvalued_assets,
        "asset_breakdown_by_currency": by_asset_currency,
        "currency_totals": currency_totals,
        "comparable_currency": comparable_currency,
        "allocation_comparable": bool(comparable_currency),
        "asset_breakdown": comparable_breakdown,
        "total_assets": sum(comparable_breakdown.values()),
    }


def format_money(amount: float, currency: str | None) -> str:
    currency_key = str(currency or "").upper()
    if currency_key == "KRW":
        return f"{amount:,.0f}원"
    if currency_key:
        return f"{amount:,.4f} {currency_key}"
    return f"{amount:,.2f}"


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {str(row[1]).lower() for row in (cur.fetchall() or []) if len(row) > 1}


def _classify_trade(symbol: Any, exchange: Any, asset_type: Any) -> str:
    explicit = str(asset_type or "").strip().lower()
    if explicit in {"crypto", "stock"}:
        return explicit
    venue = str(exchange or "").strip().lower().replace(" ", "")
    if venue in STOCK_EXCHANGES:
        return "stock"
    if venue in CRYPTO_EXCHANGES:
        return "crypto"
    symbol_key = str(symbol or "").strip().upper().replace("/", "").replace("-", "")
    if symbol_key.endswith(("USDT", "USDC", "BTC", "KRW")):
        return "crypto"
    if symbol_key.isdigit() and len(symbol_key) == 6:
        return "stock"
    return "other"


def _trade_currency(symbol: Any, exchange: Any, asset_class: str) -> str:
    if asset_class == "stock":
        return "KRW"
    venue = str(exchange or "").strip().lower()
    symbol_key = str(symbol or "").strip().upper()
    if venue in {"upbit", "bithumb"} or symbol_key.startswith("KRW-"):
        return "KRW"
    return "USDT"


def load_closed_trade_records(
    db_path: str,
    *,
    asset_class: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Load one normalized closed-trade schema across old and new databases.

    UI consumers must use this adapter instead of composing SQL against
    optional columns.  ``notional`` is derived from entry price and quantity
    when an explicit entry amount is unavailable.
    """
    result: Dict[str, Any] = {
        "records": [],
        "schema_compatible": False,
        "error": "",
    }
    if not db_path or not os.path.exists(db_path):
        result["error"] = "database_missing"
        return result

    try:
        with sqlite3.connect(db_path) as conn:
            columns = _table_columns(conn, "trade_log")
            required = {"symbol", "pnl", "entry_time", "exit_time"}
            if not required.issubset(columns):
                result["error"] = "trade_log_schema_missing"
                return result

            asset_expr = "asset_type" if "asset_type" in columns else "NULL"
            exchange_expr = "exchange" if "exchange" in columns else "NULL"
            reason_filter = (
                "AND LOWER(COALESCE(reason, '')) != 'binance_import'"
                if "reason" in columns else ""
            )
            if "entry_amount" in columns:
                notional_expr = "COALESCE(entry_amount, 0)"
            elif {"entry_price", "quantity"}.issubset(columns):
                notional_expr = "ABS(COALESCE(entry_price, 0) * COALESCE(quantity, 0))"
            elif "amount" in columns:
                notional_expr = "ABS(COALESCE(amount, 0))"
            else:
                notional_expr = "0"
            rows = conn.execute(
                f"""
                SELECT symbol, {exchange_expr}, {asset_expr}, COALESCE(pnl, 0),
                       {notional_expr}, COALESCE(exit_time, entry_time),
                       DATE(COALESCE(exit_time, entry_time))
                FROM trade_log
                WHERE exit_time IS NOT NULL {reason_filter}
                ORDER BY COALESCE(exit_time, entry_time) DESC
                """
            ).fetchall()

        normalized = []
        requested_class = str(asset_class or "").strip().lower()
        for symbol, exchange, explicit_class, pnl, notional, timestamp, day in rows:
            normalized_class = _classify_trade(symbol, exchange, explicit_class)
            if requested_class and normalized_class != requested_class:
                continue
            normalized.append({
                "symbol": str(symbol or ""),
                "exchange": str(exchange or ""),
                "asset_class": normalized_class,
                "currency": _trade_currency(symbol, exchange, normalized_class),
                "pnl": _number(pnl),
                "notional": _number(notional),
                "timestamp": str(timestamp or ""),
                "day": str(day or ""),
            })
            if limit is not None and len(normalized) >= max(0, int(limit)):
                break
        result["records"] = normalized
        result["schema_compatible"] = True
        return result
    except Exception as exc:
        result["error"] = str(exc)
        return result


def load_trade_history_metrics(db_path: str) -> Dict[str, Any]:
    """Read realised PnL and daily class samples without assuming new columns."""
    result: Dict[str, Any] = {
        "closed_count": 0,
        "pnl_by_currency": {},
        "pnl_by_asset_currency": {"crypto": {}, "stock": {}, "other": {}},
        "daily_pnl": {},
        "schema_compatible": False,
        "error": "",
    }
    if not db_path or not os.path.exists(db_path):
        result["error"] = "database_missing"
        return result

    try:
        loaded = load_closed_trade_records(db_path)
        result["schema_compatible"] = bool(loaded.get("schema_compatible"))
        result["error"] = str(loaded.get("error", "") or "")
        for record in loaded.get("records", []) or []:
            asset_class = str(record.get("asset_class", "other") or "other")
            currency = str(record.get("currency", "") or "")
            pnl_value = _number(record.get("pnl"))
            day = str(record.get("day", "") or "")
            result["closed_count"] += 1
            result["pnl_by_currency"][currency] = result["pnl_by_currency"].get(currency, 0.0) + pnl_value
            class_bucket = result["pnl_by_asset_currency"].setdefault(asset_class, {})
            class_bucket[currency] = class_bucket.get(currency, 0.0) + pnl_value
            if day:
                day_bucket = result["daily_pnl"].setdefault(day, {})
                if asset_class in {"crypto", "stock"}:
                    day_bucket[asset_class] = day_bucket.get(asset_class, 0.0) + pnl_value
        return result
    except Exception as exc:
        result["error"] = str(exc)
        return result
