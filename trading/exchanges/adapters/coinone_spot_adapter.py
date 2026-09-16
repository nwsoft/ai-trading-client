#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Coinone KRW spot adapter.

CCXT owns common public data, balance normalization and limit orders.  Coinone
V2.1 is used only for gaps that must be reconciled against the venue order
ledger.  LIVE submission stays fail-closed until an operator records a real
account E2E pass in settings; PAPER/public market data never needs that flag.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..balance_normalizer import normalize_ccxt_total_balances
from ..execution_history import build_execution_capabilities, fetch_ccxt_execution_history
from ..interfaces.spot_exchange import SpotExchange
from ..order_constraints import prepare_ccxt_order_quantity


class CoinoneSpotAdapter(SpotExchange):
    """Hybrid CCXT/Coinone V2.1 adapter with an explicit LIVE readiness gate."""

    API_BASE = "https://api.coinone.co.kr"

    def __init__(self, api_key: str, secret_key: str, **kwargs: Any):
        super().__init__("coinone")
        self.api_key = str(api_key or "")
        self.secret_key = str(secret_key or "")
        self.exchange: Any = None
        self.logger = logging.getLogger(__name__)
        self.last_error = ""
        self.last_auth_guidance = ""
        self.live_e2e_verified = bool(kwargs.get("live_e2e_verified", False))
        self._last_execution_capabilities: Dict[str, Any] = {}
        from log_system.log_adapter import log_event

        self.log_event = lambda category, msg, level="INFO": log_event(
            category, msg, exchange="coinone", level=level
        )

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        raw = str(symbol or "BTC/KRW").strip().upper()
        if raw.startswith("KRW-"):
            raw = raw.split("-", 1)[1]
        if "/" in raw:
            left, right = raw.split("/", 1)
            base = right if left == "KRW" else left
        elif raw.endswith("USDT"):
            base = raw[:-4]
        elif raw.endswith("KRW"):
            base = raw[:-3]
        else:
            base = raw
        return f"{base}/KRW"

    @classmethod
    def _symbol_parts(cls, symbol: str) -> tuple[str, str]:
        base, quote = cls._normalize_symbol(symbol).split("/", 1)
        return base.lower(), quote.lower()

    def _private_post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        import requests


        if not self.api_key or not self.secret_key:
            raise RuntimeError("코인원 API 키가 설정되지 않았습니다")
        body = {
            "access_token": self.api_key,
            "nonce": str(uuid.uuid4()),
            **payload,
        }
        encoded = base64.b64encode(
            json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        )
        signature = hmac.new(
            self.secret_key.encode("utf-8"), encoded, hashlib.sha512
        ).hexdigest()
        response = requests.post(
            f"{self.API_BASE}{path}",
            data=encoded,
            headers={
                "Content-Type": "application/json",
                "X-COINONE-PAYLOAD": encoded.decode("ascii"),
                "X-COINONE-SIGNATURE": signature,
            },
            timeout=12,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("코인원 응답 형식이 올바르지 않습니다")
        if str(data.get("result") or "success").lower() not in {"success", "true"}:
            raise RuntimeError(str(data.get("error_msg") or data.get("error_code") or "coinone_api_error"))
        return data

    def connect(self) -> bool:
        try:
            import importlib

            ccxt = importlib.import_module("ccxt")
            config: Dict[str, Any] = {"enableRateLimit": True, "timeout": 12000}
            if self.api_key and self.secret_key:
                config.update(apiKey=self.api_key, secret=self.secret_key)
            self.exchange = ccxt.coinone(config)
            self.exchange.load_markets()
            self.is_connected = True
            self.last_error = ""
            self.log_event("system", "코인원 연결 성공 (LIVE 주문은 실계좌 E2E 승인 후 활성화)")
            return True
        except Exception as exc:
            self.last_error = str(exc)
            self.is_connected = False
            self.log_event("system", f"코인원 연결 실패: {exc}", level="ERROR")
            return False

    def validate_credentials(self) -> bool:
        if not self.connect():
            return False
        if not self.api_key or not self.secret_key:
            return True
        try:
            self.exchange.fetch_balance()
            return True
        except Exception as exc:
            self.last_error = str(exc)
            self.last_auth_guidance = "코인원 API 조회 권한과 허용 IP를 확인하세요. 출금 권한은 사용하지 않습니다."
            return False

    def get_balance(self) -> Dict[str, float]:
        if not self.is_connected or self.exchange is None:
            return {}
        if not self.api_key or not self.secret_key:
            return {"KRW": 0.0}
        try:
            return normalize_ccxt_total_balances(self.exchange.fetch_balance(), quote_asset="KRW")
        except Exception as exc:
            self.last_error = str(exc)
            self.log_event("system", f"코인원 잔고 조회 실패: {exc}", level="ERROR")
            return {}

    def get_account_info(self) -> Dict[str, Any]:
        balances = self.get_balance()
        return {
            "available_balance": float(balances.get("KRW") or 0.0),
            "total_balance": float(balances.get("KRW") or 0.0),
            "balances": balances,
        } if balances else {}

    def get_current_price(self, symbol: str) -> float:
        if not self.is_connected or self.exchange is None:
            return 0.0
        try:
            ticker = self.exchange.fetch_ticker(self._normalize_symbol(symbol))
            return float(ticker.get("last") or ticker.get("close") or 0.0)
        except Exception as exc:
            self.last_error = str(exc)
            return 0.0

    def get_24h_ticker(self, symbol: str) -> Dict[str, Any]:
        if not self.is_connected or self.exchange is None:
            return {}
        try:
            return dict(self.exchange.fetch_ticker(self._normalize_symbol(symbol)) or {})
        except Exception as exc:
            self.last_error = str(exc)
            return {}

    def get_24h_tickers(self, symbols=None) -> Dict[str, Dict[str, Any]]:
        """CCXT Coinone with a symbols list queries only its first symbol.

        Fetch the public KRW snapshot once, then filter locally so a partial
        response cannot make an arbitrary first asset the entire universe.
        """
        if not self.is_connected or self.exchange is None:
            return {}
        rows = self.exchange.fetch_tickers() or {}
        wanted = {self._normalize_symbol(symbol) for symbol in (symbols or [])}
        return {key: row for key, row in rows.items() if not wanted or key in wanted}

    def get_exchange_info(self) -> Dict[str, Any]:
        if not self.is_connected or self.exchange is None:
            return {}
        try:
            markets = self.exchange.load_markets()
            return {"symbols": [
                {
                    "symbol": symbol,
                    "baseAsset": row.get("base"),
                    "quoteAsset": row.get("quote"),
                    # CCXT Coinone does not publish an active flag (None).
                    # Unknown is not an explicit suspension. Public ticker /
                    # candle scoring and execution guards still apply.
                    "status": "BREAK" if row.get("active") is False else "TRADING",
                }
                for symbol, row in dict(markets or {}).items()
                if str(symbol).upper().endswith("/KRW")
            ]}
        except Exception as exc:
            self.last_error = str(exc)
            return {}

    def place_order(
        self, symbol: str, side: str, quantity: float,
        price: Optional[float] = None, order_type: str = "MARKET",
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized = self._normalize_symbol(symbol)
        if not self.live_e2e_verified:
            return {
                "status": "error", "symbol": normalized, "side": side,
                "error": "코인원 LIVE는 시장가·부분체결·수수료 실계좌 E2E 승인 전까지 차단됩니다",
                "error_code": "coinone_live_e2e_required",
            }
        if not self.is_connected or self.exchange is None:
            return {"status": "error", "error": "코인원 거래소가 연결되지 않았습니다"}
        try:
            constraint = prepare_ccxt_order_quantity(
                self.exchange, normalized, quantity, reference_price=price,
            )
            if not constraint.get("allowed"):
                return {"status": "error", "error": str(constraint.get("reason") or "order_constraints_not_met")}
            order_kind = "LIMIT" if str(order_type).upper() == "LIMIT" else "MARKET"
            side_kind = "BUY" if str(side).lower() == "buy" else "SELL"
            base, quote = self._symbol_parts(normalized)
            payload: Dict[str, Any] = {
                "quote_currency": quote,
                "target_currency": base,
                "side": side_kind,
                "type": order_kind,
            }
            if client_order_id:
                payload["user_order_id"] = str(client_order_id)[:36]
            if order_kind == "LIMIT":
                if not price or float(price) <= 0:
                    return {"status": "error", "error": "코인원 지정가 주문에는 가격이 필요합니다"}
                payload.update(qty=str(constraint["quantity"]), price=str(float(price)))
            elif side_kind == "BUY":
                amount = float(constraint.get("notional") or 0.0)
                if amount <= 0:
                    return {"status": "error", "error": "코인원 시장가 매수 원화 총액을 계산하지 못했습니다"}
                payload["amount"] = str(amount)
            else:
                payload["qty"] = str(constraint["quantity"])
            data = self._private_post("/v2.1/order", payload)
            order_id = str(data.get("order_id") or "")
            if not order_id:
                raise RuntimeError("코인원 주문번호가 없는 응답입니다")
            return {
                "id": order_id, "order_id": order_id, "status": "open",
                "symbol": normalized, "side": side_kind.lower(), "type": order_kind.lower(),
                "amount": float(constraint["quantity"]), "price": price,
                "clientOrderId": client_order_id, "info": data,
            }
        except Exception as exc:
            self.last_error = str(exc)
            return {"status": "error", "error": str(exc), "symbol": normalized, "side": side}

    @staticmethod
    def _normalize_native_order(row: Dict[str, Any], symbol: str = "") -> Dict[str, Any]:
        executed_qty = float(row.get("executed_qty") or row.get("filled_qty") or 0.0)
        average = float(row.get("average_executed_price") or row.get("average_price") or 0.0)
        original_qty = float(row.get("original_qty") or row.get("qty") or executed_qty or 0.0)
        order_id = str(row.get("order_id") or row.get("id") or "")
        status = str(row.get("status") or "").lower()
        raw_timestamp = row.get("ordered_at") or row.get("timestamp") or 0
        try:
            timestamp = int(float(raw_timestamp))
        except (TypeError, ValueError):
            try:
                timestamp = int(datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00")).timestamp() * 1000)
            except (TypeError, ValueError):
                timestamp = 0
        return {
            "id": order_id, "order_id": order_id,
            "symbol": CoinoneSpotAdapter._normalize_symbol(symbol or str(row.get("symbol") or "BTC/KRW")),
            "side": str(row.get("side") or "").lower(), "status": status,
            "amount": original_qty, "filled": executed_qty,
            "remaining": max(0.0, original_qty - executed_qty),
            "average": average, "price": float(row.get("price") or average or 0.0),
            "cost": float(row.get("executed_amount") or (average * executed_qty)),
            "fee": {"cost": float(row.get("fee") or 0.0), "currency": str(row.get("fee_currency") or "KRW")},
            "timestamp": timestamp,
            "info": row,
        }

    def get_order_status(self, order_id: str, symbol: Optional[str] = None) -> Dict[str, Any]:
        if not symbol:
            self.last_error = "코인원 주문 조회에는 종목이 필요합니다"
            return {}
        try:
            base, quote = self._symbol_parts(symbol)
            data = self._private_post("/v2.1/order/detail", {
                "order_id": str(order_id), "quote_currency": quote, "target_currency": base,
            })
            row = dict(data.get("order") or data)
            return self._normalize_native_order(row, symbol)
        except Exception as exc:
            self.last_error = str(exc)
            return {}

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        if not symbol:
            self.last_error = "코인원 주문 취소에는 종목이 필요합니다"
            return False
        try:
            base, quote = self._symbol_parts(symbol)
            self._private_post("/v2.1/order/cancel", {
                "order_id": str(order_id), "quote_currency": quote, "target_currency": base,
            })
            return True
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        if not symbol:
            return []
        try:
            base, quote = self._symbol_parts(symbol)
            data = self._private_post("/v2.1/order/active_orders", {
                "quote_currency": quote, "target_currency": base,
            })
            return [self._normalize_native_order(dict(row), symbol) for row in list(data.get("active_orders") or [])]
        except Exception as exc:
            self.last_error = str(exc)
            return []

    def get_trade_history(
        self, symbol: Optional[str] = None, limit: int = 100,
        since_ms: Optional[int] = None, from_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not self.is_connected or self.exchange is None:
            return []
        try:
            rows, capabilities = fetch_ccxt_execution_history(
                self.exchange,
                symbol=self._normalize_symbol(symbol) if symbol else None,
                limit=max(1, min(int(limit), 500)), since_ms=since_ms,
                symbol_formatter=self._normalize_symbol,
            )
            self._last_execution_capabilities = capabilities
            return rows
        except Exception as exc:
            self.last_error = str(exc)
            return []

    def get_execution_capabilities(self) -> Dict[str, Any]:
        caps = build_execution_capabilities(self.exchange)
        caps.update(self._last_execution_capabilities)
        caps.update({
            "live_order_receipt": self.live_e2e_verified,
            "account_e2e_verified": self.live_e2e_verified,
            "history_reason": caps.get("history_reason") or "coinone_v2_1_reconciliation_required",
        })
        return caps

    def get_klines(self, symbol: str, interval: str = "1m", limit: int = 100) -> List[List[float]]:
        """Use Coinone public chart when the installed CCXT lacks fetchOHLCV."""
        import requests
        from trading.market_data_utils import failed_candles, chronological_candles

        normalized = self._normalize_symbol(symbol)
        try:
            if self.exchange is not None and bool(getattr(self.exchange, "has", {}).get("fetchOHLCV")):
                return chronological_candles(self.exchange.fetch_ohlcv(normalized, timeframe=interval, limit=limit) or [])[-max(1, int(limit)):]
            base, quote = self._symbol_parts(normalized)
            response = requests.get(
                f"{self.API_BASE}/public/v2/chart/{quote.upper()}/{base.upper()}",
                params={"interval": interval, "size": max(1, min(int(limit), 500))}, timeout=12,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                return failed_candles('coinone_chart_invalid_response')
            if data.get('result') not in (None, 'success') or str(data.get('error_code', '0')) != '0':
                return failed_candles('coinone_chart_api_rejected')
            chart = list(data.get("chart") or data.get("data") or []) if isinstance(data, dict) else []
            rows: List[List[float]] = []
            for item in chart:
                if not isinstance(item, dict):
                    continue
                rows.append([
                    float(item.get("timestamp") or item.get("time") or 0),
                    float(item.get("open") or 0), float(item.get("high") or 0),
                    float(item.get("low") or 0), float(item.get("close") or 0),
                    float(item.get("target_volume") or item.get("volume") or 0),
                ])
            return chronological_candles(rows)[-max(1, int(limit)):] if rows else failed_candles('empty_response')
        except Exception as exc:
            self.last_error = str(exc)
            return failed_candles('coinone_chart_query_failed', exc)
