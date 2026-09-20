"""Lazy bridge from the Web gateway to the UI-neutral trading runtime."""

from __future__ import annotations

import threading
import time
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Callable

from config.settings import load_settings
from path_utils import set_current_user_account
from trading.account_state_contract import classify_spot_holdings
from trading.execution_mode import ExecutionMode, resolve_crypto_execution_mode
from trading.position_ownership import managed_trade_map
from trading.position_limit_policy import effective_crypto_position_limit, normalize_position_mode
from trading.selection_policy import candidate_execution_eligible
from trading.strategy_scope import scoped_pool
from trading.spot_position_policy import balance_quantity, safe_managed_close_quantity, spot_base_asset
from trading.exchanges.venue_capabilities import (
    CRYPTO_VENUES,
    KRW_SPOT_VENUES,
    STOCK_VENUES,
    venue_supports_execution,
)

from .credential_contract import all_credentials_present, stock_credentials_present


CRYPTO_SOURCES = set(CRYPTO_VENUES)
STOCK_SOURCES = set(STOCK_VENUES)
STOCK_CONFIG_KEYS = {"kiwoom": "kiwoom", "shinhan": "shinhan", "mirae": "miraeAsset", "kis": "koreaInvestment"}
RUNTIME_PUBLIC_FIELDS = (
    "symbol", "side", "quantity", "size", "contracts", "entry_price",
    "entryPrice", "mark_price", "markPrice", "current_price", "price",
    "unrealized_pnl", "unrealizedPnl", "leverage", "status", "currency",
    "asset", "available", "free", "used", "total", "order_id", "id",
    "type", "amount", "filled", "remaining", "average", "timestamp",
    "signal", "confidence", "trend", "volatility", "reasoning",
    "support_level", "resistance_level",
    "tp_price", "sl_price", "entry_time", "execution_mode", "position_id",
    "custom_strategy_id", "custom_strategy_name", "custom_strategy_key",
    "custom_strategy_version_id", "exit_policy", "custom_strategy_rules",
)


def _public_source(value: Any) -> str:
    normalized = str(value or "").replace("_", "").strip().lower()
    return {"miraeasset": "mirae", "koreainvestment": "kis"}.get(normalized, normalized)


def _credential_status(settings: dict[str, Any]) -> dict[str, bool]:
    status = {
        "binance": all_credentials_present(settings.get("binance_api_key"), settings.get("binance_secret_key")),
        "upbit": all_credentials_present(settings.get("upbit_api_key"), settings.get("upbit_secret_key")),
        "bithumb": all_credentials_present(settings.get("bithumb_api_key"), settings.get("bithumb_secret_key")),
        "coinone": all_credentials_present(settings.get("coinone_api_key"), settings.get("coinone_secret_key")),
        "bybit": all_credentials_present(settings.get("bybit_api_key"), settings.get("bybit_secret_key")),
        "okx": all_credentials_present(settings.get("okx_api_key"), settings.get("okx_secret_key"), settings.get("okx_passphrase")),
        "bitget": all_credentials_present(settings.get("bitget_api_key"), settings.get("bitget_secret_key"), settings.get("bitget_password")),
    }
    configs = settings.get("stock_broker_configs") or {}
    for source, config_key in STOCK_CONFIG_KEYS.items():
        config = configs.get(config_key) if isinstance(configs, dict) else {}
        config = config if isinstance(config, dict) else {}
        status[source] = stock_credentials_present(source, config)
    return status


def _credential_required_result(source: str) -> dict[str, Any]:
    noun = "증권사" if source in STOCK_SOURCES else "거래소"
    return {
        "source": source,
        "status": "credential_required",
        "message": f"{source.upper()} {noun} API 키를 설정한 뒤 연결을 확인하세요.",
        "balance": {},
        "positions": [],
        "open_orders": [],
    }


def _runtime_safe(value: Any, *, depth: int = 0) -> Any:
    """Convert adapter output to a bounded, secret-free JSON value."""
    if depth > 8:
        return "[depth-limited]"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return _runtime_safe(value.value, depth=depth + 1)
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in list(value.items())[:500]:
            lowered = str(key).lower()
            if any(token in lowered for token in ("api_key", "secret", "password", "passphrase", "token", "credential", "account_no")):
                continue
            output[str(key)] = _runtime_safe(item, depth=depth + 1)
        return output
    if isinstance(value, (list, tuple, set)):
        return [_runtime_safe(item, depth=depth + 1) for item in list(value)[:500]]
    public = {
        field: getattr(value, field)
        for field in RUNTIME_PUBLIC_FIELDS
        if hasattr(value, field) and not callable(getattr(value, field))
    }
    return _runtime_safe(public, depth=depth + 1) if public else str(type(value).__name__)


def build_headless_runtime(account: str) -> Any:
    """Create the engine without importing ``main`` or any desktop UI module."""
    from .headless_runtime import HeadlessTradingRuntime

    return HeadlessTradingRuntime(account)


class HeadlessRuntimeBridge:
    """Own one headless runtime and expose typed start/stop/shutdown operations."""

    def __init__(self, *, account: str = "local", factory: Callable[[str], Any] = build_headless_runtime):
        self.account = account
        self.factory = factory
        self._app: Any = None
        self._lock = threading.RLock()
        self._record_recovery = None

    def record_recovery(self, source: str, *, start: bool = False) -> dict[str, Any]:
        from trading.record_recovery import RecordRecovery
        from trading.record_recovery_adapters import RecoveryResolver
        source = RecordRecovery.venue(source)
        if self.account == 'local':
            raise RuntimeError('recovery_login_required')
        # GET status must not initialize brokers or open an authentication host.
        if self._record_recovery is None and not start:
            from path_utils import get_db_file_path
            return RecordRecovery.read_status(get_db_file_path(), source)
        if start:
            if not _credential_status(self._settings()).get(source, False):
                raise RuntimeError('recovery_credential_required')
            app = self._app
            if app is None:
                # Constructing the full runtime also starts its AI optimizer.
                # Maintenance must not initialize that as a hidden side effect.
                raise RuntimeError('recovery_engine_not_ready')
            recorder = getattr(app, 'recorder', None)
            if recorder is None:
                raise RuntimeError('recovery_ledger_unavailable')
            # Never reconnect a Kiwoom host from a maintenance worker. Existing
            # adapters only; connection setup remains the usual Settings path.
            if source in STOCK_SOURCES:
                controller = getattr(app, 'stock_runtime_controller', None)
                broker = controller._canonical(source) if controller else source
                client = getattr(controller, '_adapters', {}).get(broker)
            else:
                manager = getattr(app, 'exchange_manager', None)
                client = manager.get_exchange_client(source) if manager else None
            resolver = RecoveryResolver(recorder, client, source)
            recovery = RecordRecovery(recorder, resolver)
            result = recovery.start(source)
            self._record_recovery = recovery
            return result
        return self._record_recovery.status(source)

    def set_account(self, account: str) -> None:
        normalized = str(account or "").strip()
        with self._lock:
            if self._app is not None and normalized != self.account:
                raise RuntimeError("runtime_account_change_requires_restart")
            self.account = normalized or "local"

    def _settings(self) -> dict[str, Any]:
        return dict(load_settings(persist_migrations=False) or {}) if self.account != "local" else {}

    def _ensure_app(self) -> Any:
        with self._lock:
            if self._app is None:
                self._app = self.factory(self.account)
            return self._app

    def refresh_settings(self, settings: dict[str, Any]) -> None:
        """Keep an already-created headless runtime on the canonical settings.

        The legacy dashboard mutates the same in-memory settings object after a
        watchlist edit.  The Web shell persists through ApplicationServices, so
        explicitly refresh the runtime copy instead of waiting for a restart.
        """
        with self._lock:
            if self._app is not None:
                refresh = getattr(self._app, "refresh_settings", None)
                if callable(refresh):
                    refresh(deepcopy(settings))
                    return

                # Compatibility for test doubles and older runtime factories.
                # Mutate an existing dictionary in place so components holding
                # that same reference cannot later persist a stale snapshot.
                current = getattr(self._app, "settings", None)
                if isinstance(current, dict):
                    incoming = deepcopy(settings)
                    for key in list(current):
                        if key not in incoming:
                            current.pop(key, None)
                    current.update(incoming)
                else:
                    self._app.settings = deepcopy(settings)

    def refresh_strategies(self) -> dict[str, Any]:
        """Reload persisted AI Custom strategy state without starting a runtime."""
        with self._lock:
            if self._app is None:
                return {"ok": True, "runtime_attached": False, "active_count": 0}
            refresh = getattr(self._app, "refresh_strategy_runtime", None)
            if not callable(refresh):
                raise RuntimeError("strategy_runtime_refresh_unavailable")
            pool = list(refresh() or [])
            return {"ok": True, "runtime_attached": True, "active_count": len(pool)}

    def refresh_membership(self, user_grade: str, policy: dict[str, Any], *, active: bool = True) -> None:
        """Propagate server membership changes into an existing runtime."""
        with self._lock:
            if self._app is None:
                return
            if not active:
                for source in list(self._running(self._app)):
                    try:
                        self._app.stop_source(source, close_all=False)
                    except Exception:
                        pass
                self._app._accepting_commands = False
                return
            apply_policy = getattr(self._app, "apply_server_membership_policy", None)
            if callable(apply_policy):
                apply_policy(user_grade, policy)

    def stock_search_suggestions(self, *, source: str, query: str = "", asset_mode: str = "all", limit: int = 8) -> list[dict[str, Any]]:
        normalized = _public_source(source)
        if normalized not in STOCK_SOURCES:
            raise ValueError("unsupported_stock_source")
        if not _credential_status(self._settings()).get(normalized, False):
            return []
        app = self._ensure_app()
        controller = getattr(app, "stock_runtime_controller", None)
        suggest = getattr(controller, "symbol_suggestions", None)
        if not callable(suggest):
            return []
        return _runtime_safe(suggest(normalized, query=query, asset_mode=asset_mode, limit=limit))

    @staticmethod
    def _running(app: Any) -> list[str]:
        running: list[str] = []
        getter = getattr(app, "running_crypto_exchanges", None)
        if not callable(getter):
            getter = getattr(app, "_running_crypto_exchanges", None)
        if callable(getter):
            running.extend(str(item).lower() for item in (getter() or []))
        stock_controller = getattr(app, "stock_runtime_controller", None)
        if stock_controller is not None:
            running.extend(_public_source(item) for item in (stock_controller.running_sources() or []))
        return list(dict.fromkeys(running))

    def snapshot(self) -> dict[str, Any]:
        settings = self._settings()
        credentials = _credential_status(settings)
        enabled = [
            _public_source(item)
            for item in list(settings.get("enabled_exchanges") or []) + list(settings.get("enabled_stock_brokers") or [])
            if _public_source(item) in CRYPTO_SOURCES | STOCK_SOURCES
        ]
        running = self._running(self._app) if self._app is not None else []
        enabled_crypto = [item for item in enabled if item in CRYPTO_SOURCES]
        enabled_stock = [item for item in enabled if item in STOCK_SOURCES]
        running_crypto = [item for item in running if item in CRYPTO_SOURCES]
        running_stock = [item for item in running if item in STOCK_SOURCES]
        execution_modes = {
            source: resolve_crypto_execution_mode(settings, source).value
            for source in sorted(CRYPTO_SOURCES)
        }
        stock_mode = ExecutionMode.PAPER.value if bool(settings.get("paper_trading", True)) else ExecutionMode.LEARNING.value
        for source in sorted(STOCK_SOURCES):
            execution_modes[source] = stock_mode
        stock_controller = getattr(self._app, "stock_runtime_controller", None) if self._app is not None else None
        if stock_controller is not None:
            try:
                controller_snapshot = stock_controller.snapshot()
                for raw_source, result in dict(controller_snapshot.get("last_results") or {}).items():
                    public_source = _public_source(raw_source)
                    mode = str((result or {}).get("execution_mode") or "").strip().lower() if isinstance(result, dict) else ""
                    if public_source in STOCK_SOURCES and mode in {item.value for item in ExecutionMode}:
                        execution_modes[public_source] = mode
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
        selected_crypto = _public_source(settings.get("selected_exchange") or (enabled_crypto[0] if enabled_crypto else "binance"))
        selected_stock = _public_source(
            settings.get("selected_stock_broker")
            or settings.get("selected_broker")
            or (enabled_stock[0] if enabled_stock else "kiwoom")
        )
        if selected_stock not in STOCK_SOURCES:
            selected_stock = enabled_stock[0] if enabled_stock else "kiwoom"
        authenticated = self.account != "local"
        return {
            "status": "ready" if authenticated else "detached",
            "service": "runtime",
            # selected_source is retained for old clients. New UI surfaces must
            # use selected_sources so a crypto selection can never leak into a
            # stock workspace (or vice versa).
            "selected_source": selected_crypto,
            "selected_sources": {"blockchain": selected_crypto, "stock": selected_stock},
            "enabled_sources": list(dict.fromkeys(enabled)),
            "running_sources": running,
            "enabled_sources_by_service": {"blockchain": enabled_crypto, "stock": enabled_stock},
            "running_sources_by_service": {"blockchain": running_crypto, "stock": running_stock},
            "credential_status": credentials,
            "configured_sources_by_service": {
                "blockchain": [source for source in sorted(CRYPTO_SOURCES) if credentials.get(source)],
                "stock": [source for source in sorted(STOCK_SOURCES) if credentials.get(source)],
            },
            "execution_modes": execution_modes,
            "paper_trading": bool(settings.get("paper_trading", True)) if authenticated else None,
            "live_trading": (not bool(settings.get("paper_trading", True))) if authenticated else None,
            "reason": "engine_active" if self._app is not None else "engine_lazy_until_confirmed_start" if authenticated else "login_required",
        }

    def assistant_context_snapshot(self, *, service: str, source: str = "") -> dict[str, Any]:
        """Return bounded in-memory execution evidence without an exchange call."""
        runtime = self.snapshot()
        requested = _public_source(
            source or dict(runtime.get("selected_sources") or {}).get(service) or runtime.get("selected_source")
        )
        result: dict[str, Any] = {
            "service": str(service or ""),
            "source": requested,
            "execution_mode": str(
                dict(runtime.get("execution_modes") or {}).get(requested)
                or ("paper" if runtime.get("paper_trading") else "learning")
            ).upper(),
            "running": requested in list(runtime.get("running_sources") or []),
            "managed_positions": [],
            "active_custom_strategies": [],
            "cycle_execution_metrics": [],
            "engine_attached": self._app is not None,
        }
        if self._app is None:
            return result
        app = self._app
        positions: list[dict[str, Any]] = []
        if result["execution_mode"] == "PAPER" and (
            (str(service or "").strip().lower() == "blockchain" and requested in CRYPTO_SOURCES)
            or (str(service or "").strip().lower() == "stock" and requested in STOCK_SOURCES)
        ):
            paper_snapshot = self.paper_position_snapshot(service=service, source=requested)
            for position in list(paper_snapshot.get("positions") or []):
                row = dict(_runtime_safe(position))
                row.update({"symbol": str(row.get("symbol") or row.get("code") or ""), "source": requested})
                positions.append(row)
        elif requested == "binance" and getattr(app, "trader", None) is not None:
            trader = app.trader
            getter = getattr(trader, "get_active_positions", None)
            store = getter() if callable(getter) else getattr(trader, "active_positions", {})
            for symbol, position in dict(store or {}).items():
                row = dict(_runtime_safe(position))
                row.update({"symbol": str(row.get("symbol") or symbol), "source": "binance"})
                positions.append(row)
            metrics = dict(getattr(trader, "cycle_execution_metrics", {}) or {}).get("binance")
            if isinstance(metrics, dict):
                result["cycle_execution_metrics"].append(_runtime_safe({"source": "binance", **metrics}))
        elif requested in CRYPTO_SOURCES and getattr(app, "unified_trader", None) is not None:
            trader = app.unified_trader
            getter = getattr(trader, "get_active_positions", None)
            stores = getter(requested) if callable(getter) else {}
            source_store = dict(stores or {}).get(requested, {}) if isinstance(stores, dict) else {}
            for symbol, position in dict(source_store or {}).items():
                row = dict(_runtime_safe(position))
                row.update({"symbol": str(row.get("symbol") or symbol), "source": requested})
                positions.append(row)
            metrics = dict(getattr(trader, "cycle_execution_metrics", {}) or {}).get(requested)
            if isinstance(metrics, dict):
                result["cycle_execution_metrics"].append(_runtime_safe({"source": requested, **metrics}))
        if result["execution_mode"] == "PAPER" and requested in CRYPTO_SOURCES:
            trader = (
                getattr(app, "trader", None)
                if requested == "binance"
                else getattr(app, "unified_trader", None)
            )
            metrics = dict(getattr(trader, "cycle_execution_metrics", {}) or {}).get(requested)
            if isinstance(metrics, dict):
                result["cycle_execution_metrics"].append(_runtime_safe({"source": requested, **metrics}))
        if requested in STOCK_SOURCES:
            controller = getattr(app, "stock_runtime_controller", None)
            controller_snapshot = controller.snapshot() if controller is not None else {}
            canonical = {"mirae": "miraeAsset", "kis": "koreaInvestment"}.get(requested, requested)
            latest = dict(controller_snapshot.get("last_results") or {}).get(canonical)
            if isinstance(latest, dict):
                metrics = dict(latest.get("execution_metrics") or {})
                metrics.update({
                    "source": requested,
                    "candidate_count": len(list(latest.get("symbols") or [])),
                    "signal_count": len(list(latest.get("decisions") or [])),
                    "order_count": int(latest.get("orders_executed") or 0),
                    "blocked_count": sum(
                        1 for item in list(latest.get("decisions") or [])
                        if isinstance(item, dict) and not bool(item.get("success", False))
                    ),
                })
                result["cycle_execution_metrics"].append(_runtime_safe(metrics))
        result["managed_positions"] = positions[:100]
        result["active_custom_strategies"] = _runtime_safe(
scoped_pool(list(getattr(app, "active_custom_strategy_pool", []) or []), asset_class="stock" if requested in STOCK_SOURCES else "crypto", target=requested)
        )
        return result

    def paper_position_snapshot(self, *, service: str, source: str) -> dict[str, Any]:
        """Return PAPER positions from bounded runtime memory without an account API call."""
        normalized_service = str(service or "").strip().lower()
        normalized_source = _public_source(source)
        settings = self._settings()
        if normalized_service == "blockchain" and normalized_source in CRYPTO_SOURCES:
            plan_cap = getattr(self._app, "membership_position_limit", None) if self._app is not None else None
            try:
                hard_max = max(1, int(plan_cap)) if plan_cap is not None else 5
            except (TypeError, ValueError):
                hard_max = 5
            position_policy = {
                "mode": normalize_position_mode(settings.get("position_mode")),
                "limit": effective_crypto_position_limit(settings, normalized_source, hard_max=hard_max),
                "scope": "per_exchange_adapter",
            }
            mode = resolve_crypto_execution_mode(settings, normalized_source)
            if mode != ExecutionMode.PAPER:
                return {"source": normalized_source, "status": "not_paper", "positions": [], "position_policy": position_policy}
            if self._app is None:
                return {
                    "source": normalized_source, "status": "engine_inactive", "positions": [],
                    "position_policy": position_policy, "active_custom_strategies": [],
                }
            if normalized_source == "binance":
                store = getattr(getattr(self._app, "trader", None), "paper_active_positions", {})
            else:
                stores = getattr(getattr(self._app, "unified_trader", None), "paper_positions", {})
                store = stores.get(normalized_source, {}) if isinstance(stores, dict) else {}
            return {
                "source": normalized_source,
                "status": "success",
                "positions": _runtime_safe(list(dict(store or {}).values())),
                "position_policy": position_policy,
                "active_custom_strategies": _runtime_safe(
scoped_pool(list(getattr(self._app, "active_custom_strategy_pool", []) or []), asset_class="crypto", target=normalized_source)
                ),
            }
        if normalized_service == "stock" and normalized_source in STOCK_SOURCES:
            if not bool(settings.get("paper_trading", True)):
                return {"source": normalized_source, "status": "not_paper", "positions": []}
            if self._app is None:
                return {
                    "source": normalized_source, "status": "engine_inactive", "positions": [],
                    "active_custom_strategies": [],
                }
            controller = getattr(self._app, "stock_runtime_controller", None)
            getter = getattr(controller, "paper_position_snapshot", None)
            if callable(getter):
                result = dict(_runtime_safe(getter(normalized_source)) or {})
                result["active_custom_strategies"] = _runtime_safe(
scoped_pool(list(getattr(self._app, "active_custom_strategy_pool", []) or []), asset_class="stock", target=normalized_source)
                )
                return result
            return {"source": normalized_source, "status": "temporarily_unavailable", "positions": []}
        raise ValueError("unsupported_paper_position_source")

    def execution_quality_snapshot(self, *, service: str, source: str = "") -> dict[str, Any]:
        """Return the legacy cycle-quality metrics without creating an engine.

        ``exchange_execution_log`` is an actual-fill ledger; it is not the
        legacy AI Report's execution-quality source.  The desktop widget reads
        ``cycle_execution_metrics`` from the active Trader/UnifiedTrader.  Keep
        that semantic boundary in the Web UI and never start a trading runtime
        merely because a report page was opened.
        """
        service_key = str(service or "").strip().lower()
        requested = _public_source(source)
        if service_key not in {"blockchain", "stock"}:
            raise ValueError("unsupported_execution_quality_service")
        if requested:
            allowed = CRYPTO_SOURCES if service_key == "blockchain" else STOCK_SOURCES
            if requested not in allowed:
                raise ValueError("execution_quality_source_service_mismatch")
        if self._app is None:
            return {
                "status": "engine_inactive",
                "source": requested,
                "rows": [],
                "message": "실행 엔진이 아직 시작되지 않아 최근 사이클 품질 메트릭이 없습니다.",
                "read_only": True,
            }
        rows: list[dict[str, Any]] = []
        if service_key == "blockchain":
            engines = (
                ("Binance Trader", getattr(self._app, "trader", None)),
                ("Unified Trader", getattr(self._app, "unified_trader", None)),
            )
            for engine_name, engine in engines:
                metrics = getattr(engine, "cycle_execution_metrics", {}) if engine is not None else {}
                if not isinstance(metrics, dict):
                    continue
                for metric_source, metric in metrics.items():
                    normalized_source = _public_source(metric_source)
                    if requested and normalized_source != requested:
                        continue
                    if not isinstance(metric, dict):
                        continue
                    row = dict(_runtime_safe(metric))
                    row.update({"source": normalized_source, "engine": engine_name, "metric_scope": "latest_runtime_cycle"})
                    rows.append(row)
        return {
            "status": "available" if rows else "no_cycle_metrics",
            "source": requested,
            "rows": rows,
            "message": "최근 런타임 사이클 품질 메트릭" if rows else "아직 완료된 실행 사이클 품질 메트릭이 없습니다.",
            "read_only": True,
        }

    def account_snapshot(self, *, sources: list[str], force_refresh: bool = False) -> dict[str, Any]:
        requested = list(dict.fromkeys(_public_source(item) for item in sources))
        if not requested or any(item not in CRYPTO_SOURCES | STOCK_SOURCES for item in requested):
            raise ValueError("unsupported_account_snapshot_source")
        settings = self._settings()
        credentials = _credential_status(settings)
        results: dict[str, Any] = {}
        queryable = [source for source in requested if credentials.get(source, False)]
        app = self._ensure_app() if queryable else None
        for source in requested:
            if not credentials.get(source, False):
                results[source] = _credential_required_result(source)
                continue
            if source in STOCK_SOURCES:
                assert app is not None
                controller = getattr(app, "stock_runtime_controller", None)
                if controller is None:
                    results[source] = {"source": source, "status": "controller_unavailable"}
                else:
                    results[source] = _runtime_safe(controller.account_snapshot(source))
                continue
            assert app is not None
            results[source] = self._crypto_account_snapshot(app, source, force_refresh=force_refresh)
        return {
            "schema_version": "1.0.0",
            "sources": results,
            "requested_sources": requested,
            # A mixed request is never "fresh" when even one requested source
            # has no credentials or failed.  Treating only the queryable subset
            # as success made portfolio screens present a partially configured
            # account set as fully refreshed.
            "fresh": bool(requested) and all(results[source].get("status") == "success" for source in requested),
        }

    def stock_candles(self, *, source: str, symbol: str, limit: int = 300) -> list[dict[str, Any]]:
        normalized_source = _public_source(source)
        if normalized_source not in STOCK_SOURCES:
            raise ValueError("unsupported_stock_source")
        app = self._ensure_app()
        controller = getattr(app, "stock_runtime_controller", None)
        if controller is None:
            raise RuntimeError("stock_runtime_controller_not_attached")
        return _runtime_safe(controller.market_candles(normalized_source, symbol, limit=limit))

    def alpha_arena_snapshot(self) -> dict[str, Any]:
        settings = self._settings()
        arena_settings = dict(settings.get("alpha_arena") or {})
        if self._app is None:
            paper = bool(settings.get("paper_trading", True)) if settings else None
            return {
                "running": False,
                "available": bool(arena_settings.get("enabled", False)),
                "paper_trading": paper,
                "execution_mode": "PAPER" if paper else "LIVE_BLOCKED_PENDING_EXTERNAL_GATE" if paper is False else "DETACHED",
                "order_submission": False,
                "engine": str(arena_settings.get("engine") or "deepseek-v4-flash"),
                "paper_scope": "decision_guard_rehearsal_not_virtual_pnl",
                "events": [],
                "symbols": list(arena_settings.get("symbols") or []),
                "risk": {
                    "max_concurrent_positions": int(arena_settings.get("max_concurrent_positions", 6) or 6),
                    "max_risk_per_tick": float(arena_settings.get("max_risk_per_tick", 1500.0) or 1500.0),
                    "cooldown_sec_per_symbol": int(arena_settings.get("cooldown_sec_per_symbol", 30) or 30),
                    "require_tp_sl": True,
                },
                "reason": "engine_lazy_until_confirmed_start" if self.account != "local" else "login_required",
            }
        return _runtime_safe(self._app.alpha_arena_snapshot())

    def alpha_arena_control(self, *, action: str, live_confirmation: bool = False) -> dict[str, Any]:
        app = self._ensure_app()
        return _runtime_safe(app.alpha_arena_control(
            action=action,
            live_confirmation=bool(live_confirmation),
        ))

    @staticmethod
    def _crypto_account_snapshot(app: Any, source: str, *, force_refresh: bool) -> dict[str, Any]:
        manager = getattr(app, "exchange_manager", None)
        if manager is None:
            return {"source": source, "status": "exchange_manager_unavailable"}
        balance = manager.get_exchange_balance(source, force_refresh=force_refresh)
        result: dict[str, Any] = {
            "source": source,
            "status": str(balance.get("status") or "error") if isinstance(balance, dict) else "invalid_balance_response",
            "balance": _runtime_safe(balance),
            "positions": [],
            "open_orders": [],
        }
        settings = getattr(app, "settings", {})
        paper_mode = (
            resolve_crypto_execution_mode(settings, source) == ExecutionMode.PAPER
            if isinstance(settings, dict) else True
        )
        if paper_mode:
            try:
                if source == "binance":
                    store = getattr(getattr(app, "trader", None), "paper_active_positions", {})
                else:
                    stores = getattr(getattr(app, "unified_trader", None), "paper_positions", {})
                    store = stores.get(source, {}) if isinstance(stores, dict) else {}
                # Copy the values before serialization so the response remains
                # a bounded snapshot even while a worker closes a position.
                result["paper_positions"] = _runtime_safe(list(dict(store or {}).values()))
                result["paper_positions_status"] = "success"
            except (AttributeError, RuntimeError, TypeError, ValueError):
                result["paper_positions"] = []
                result["paper_positions_status"] = "temporarily_unavailable"
        else:
            result["paper_positions"] = []
            result["paper_positions_status"] = "not_paper"
        if source in {"upbit", "bithumb", "coinone"}:
            balance_payload = balance.get("balance", {}) if isinstance(balance, dict) else {}
            if result["status"] == "success":
                client = manager.get_exchange_client(source)
                raw_exchange = getattr(client, "exchange", None) if client is not None else None
                markets = getattr(raw_exchange, "markets", None)
                exchange_tradable_assets: set[str] | None = set() if isinstance(markets, dict) and markets else None
                noahai_eligible_assets: set[str] | None = set() if isinstance(markets, dict) and markets else None
                if isinstance(markets, dict):
                    for market_symbol, market in markets.items():
                        if not isinstance(market, dict) or market.get("active") is False:
                            continue
                        if market.get("swap") or market.get("future") or market.get("contract"):
                            continue
                        base = str(market.get("base") or spot_base_asset(str(market_symbol))).strip().upper()
                        quote = str(market.get("quote") or "").strip().upper()
                        if not base:
                            continue
                        if exchange_tradable_assets is not None:
                            exchange_tradable_assets.add(base)
                        if quote == "KRW" and noahai_eligible_assets is not None:
                            noahai_eligible_assets.add(base)

                managed_quantities: dict[str, float] = {}
                recorder = getattr(app, "recorder", None)
                getter = getattr(recorder, "get_open_managed_trades", None)
                if callable(getter):
                    for row in managed_trade_map(list(getter(source) or [])).values():
                        asset = spot_base_asset(str(row.get("symbol") or ""))
                        actual = balance_quantity(balance_payload, asset)
                        managed_quantities[asset] = safe_managed_close_quantity(
                            managed_quantity=float(row.get("quantity") or 0.0),
                            actual_quantity=actual,
                            baseline_quantity=float(row.get("spot_baseline_quantity") or 0.0),
                        )

                holdings = list(classify_spot_holdings(
                    balance_payload,
                    quote_asset="KRW",
                    managed_quantities=managed_quantities,
                    exchange_tradable_assets=exchange_tradable_assets,
                    noahai_eligible_assets=noahai_eligible_assets,
                ).values())
                price_cache = getattr(manager, "_account_valuation_prices", {})
                for holding in holdings:
                    key = (source, str(holding.get("asset") or ""))
                    observed, price = price_cache.get(key, (0.0, 0.0))
                    if force_refresh:
                        try:
                            price = float(manager.get_current_price(f"{holding['asset']}/KRW", source) or 0)
                        except Exception:
                            price = 0.0
                        observed = time.monotonic()
                        price_cache[key] = (observed, price)
                    if price > 0 and time.monotonic() - observed < 60:
                        holding.update(current_price=price, market_value=float(holding.get("quantity") or 0) * price, valuation_status="priced")
                    else:
                        holding["valuation_status"] = "price_unavailable"
                manager._account_valuation_prices = price_cache
                result["positions"] = holdings
                result["managed_positions"] = [row for row in holdings if row.get("auto_trade_managed")]
                result["external_holdings"] = [
                    row for row in holdings
                    if not row.get("auto_trade_managed") and row.get("display_group") == "external_tradable"
                ]
                result["reference_assets"] = [
                    row for row in holdings
                    if not row.get("auto_trade_managed") and row.get("display_group") != "external_tradable"
                ]
                result["spot_holding_summary"] = {
                    "account_total": len(holdings),
                    "noahai_managed": len(result["managed_positions"]),
                    "external_tradable": len(result["external_holdings"]),
                    "reference_only": len(result["reference_assets"]),
                }
                result["positions_status"] = "success"
            else:
                result["positions_status"] = result["status"]
        client = manager.get_exchange_client(source)
        if client is None:
            if source not in {"upbit", "bithumb", "coinone"}:
                result["positions_status"] = "client_unavailable"
            result["open_orders_status"] = "client_unavailable"
            return result
        methods = (("open_orders", "get_open_orders"),) if source in {"upbit", "bithumb", "coinone"} else (("positions", "get_positions"), ("open_orders", "get_open_orders"))
        for key, method_name in methods:
            method = getattr(client, method_name, None)
            if not callable(method):
                result[f"{key}_status"] = "unsupported"
                continue
            try:
                result[key] = _runtime_safe(method() or [])
                result[f"{key}_status"] = "success"
            except Exception as exc:
                result[f"{key}_status"] = "error"
                result[f"{key}_error"] = str(exc)
        return result

    def execute(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        source = str(payload.get("source") or "").strip().lower()
        if source not in CRYPTO_SOURCES | STOCK_SOURCES:
            raise ValueError("unsupported_runtime_source")
        settings = self._settings()
        has_credentials = _credential_status(settings).get(source, False)
        if command == "trading.start":
            execution_mode = "paper" if bool(settings.get("paper_trading", True)) else "live"
            if not venue_supports_execution(source, execution_mode):
                raise RuntimeError(f"venue_{execution_mode}_onboarding_required:{source}")
            # 국내 KRW 현물 PAPER는 공개 시세와 NoahAI 로컬 가상 원장만 사용한다.
            # 개인 잔고·주문 권한이 필요하지 않으므로 API 키를 강제하지 않는다.
            # 증권 PAPER는 현재 각 증권사 런타임의 시세/계약 연결을 사용하므로
            # 기존 인증 요구를 유지한다.
            if (execution_mode == "live" or source not in KRW_SPOT_VENUES) and not has_credentials:
                raise RuntimeError(f"credential_required:{source}")
            if execution_mode == "live" and payload.get("live_confirmation") is not True:
                raise RuntimeError("live_start_confirmation_required")
        elif (
            command in {"coins.select", "coins.analyze"}
            and source not in KRW_SPOT_VENUES
            and not has_credentials
        ):
            raise RuntimeError(f"credential_required:{source}")
        elif command in {"stocks.analyze", "trades.import"} and not has_credentials:
            raise RuntimeError(f"credential_required:{source}")
        app = self._ensure_app()
        if command == "stocks.analyze":
            if source not in STOCK_SOURCES:
                raise ValueError("stock_analysis_is_broker_only")
            symbol = str(payload.get("symbol") or "").strip().upper()
            controller = getattr(app, "stock_runtime_controller", None)
            analyze = getattr(controller, "analyze_symbol", None)
            if not callable(analyze):
                raise RuntimeError("stock_analyzer_unavailable")
            result = analyze(source, symbol)
            return {
                "source": source,
                "command": command,
                "symbol": symbol,
                "analysis": _runtime_safe(result),
                "read_only": True,
                "order_submitted": False,
            }
        if command == "coins.analyze":
            if source in STOCK_SOURCES:
                raise ValueError("coin_analysis_is_crypto_only")
            symbol = str(payload.get("symbol") or "").strip().upper().replace("/", "")
            if not symbol:
                raise ValueError("coin_symbol_required")
            if not symbol.endswith(("USDT", "KRW")):
                symbol = f"{symbol}{'KRW' if source in {'upbit', 'bithumb', 'coinone'} else 'USDT'}"
            analyzer = getattr(app, "analyzer", None)
            analyze = getattr(analyzer, "analyze_symbol", None)
            if not callable(analyze):
                raise RuntimeError("coin_analyzer_unavailable")
            result = analyze(symbol)
            if result is None:
                raise RuntimeError(f"coin_analysis_unavailable:{symbol}")
            return {
                "source": source,
                "command": command,
                "symbol": symbol,
                "analysis": _runtime_safe(result),
                "read_only": True,
                "order_submitted": False,
            }
        if command == "coins.select":
            if source in STOCK_SOURCES:
                raise ValueError("coin_selection_is_crypto_only")
            if source == "binance":
                selected = list(app.select_trading_coins() or [])
            else:
                selected = list(app.unified_trader.select_trading_coins_unified(source) or [])
            statuses = {
                str(item.get("selection_status") or "scored").strip().lower()
                for item in selected
                if isinstance(item, dict)
            }
            if "stale_unscored" in statuses:
                selection_status = "stale_data"
            elif "fallback_unscored" in statuses:
                selection_status = "data_unavailable"
            elif "scored_partial" in statuses:
                selection_status = "scored_partial"
            elif selected:
                selection_status = "scored"
            else:
                selection_status = "empty"
            execution_eligible_count = sum(
                1
                for item in selected
                if candidate_execution_eligible(item)
            )
            return {
                "source": source,
                "command": command,
                "selected_count": len(selected),
                "execution_eligible_count": execution_eligible_count,
                "selection_status": selection_status,
                "selected_symbols": [
                    str(item.get("symbol") or item.get("coin") or "") if isinstance(item, dict) else str(item)
                    for item in selected
                ],
                "running_sources": self._running(app),
            }
        if command == "trades.import":
            if source in STOCK_SOURCES:
                raise ValueError("trade_history_import_is_crypto_only")
            manager = getattr(app, "exchange_manager", None)
            client = manager.get_exchange_client(source) if manager is not None else None
            if client is None:
                raise RuntimeError(f"exchange_client_unavailable:{source}")
            history = getattr(client, "get_recent_trades", None) if source == "binance" else getattr(client, "get_trade_history", None)
            if not callable(history):
                raise RuntimeError(f"trade_history_unavailable:{source}")
            trades = history(symbol=None, limit=200) if source == "binance" else history(limit=500)
            saver = getattr(getattr(app, "recorder", None), "save_exchange_execution_history", None)
            if not callable(saver):
                raise RuntimeError("execution_history_store_unavailable")
            sync = dict(saver(
                source,
                [dict(item) for item in list(trades or []) if isinstance(item, dict)],
                source="web_dashboard_exchange_sync",
            ) or {})
            return {
                "source": source,
                "command": command,
                "received": int(sync.get("received", len(trades or [])) or 0),
                "inserted": int(sync.get("inserted", 0) or 0),
                "skipped": int(sync.get("skipped", 0) or 0),
                "running_sources": self._running(app),
            }
        if source in STOCK_SOURCES:
            controller = getattr(app, "stock_runtime_controller", None)
            if controller is None:
                raise RuntimeError("stock_runtime_controller_not_attached")
            assert_allowed = getattr(app, "assert_command_allowed", None)
            # A revoked/expired membership must block new work, but it must
            # never trap an already-running broker worker.  Stop remains an
            # unconditional safety command, matching the crypto path.
            if command != "trading.stop" and callable(assert_allowed):
                assert_allowed(source)
            ok = controller.start(source) if command == "trading.start" else controller.stop(source, close_all=bool(payload.get("close_all")))
        elif command == "trading.start":
            starter = getattr(app, "start_source", None)
            if callable(starter):
                ok = starter(source)
            elif source == "binance" and callable(getattr(app, "_start_binance_trading", None)):
                ok = app._start_binance_trading()
            elif callable(getattr(app, "_start_unified_trading", None)):
                ok = app._start_unified_trading(source)
            else:
                raise RuntimeError("headless_runtime_start_unavailable")
        elif command == "trading.stop":
            stopper = getattr(app, "stop_source", None)
            if callable(stopper):
                ok = stopper(source, close_all=bool(payload.get("close_all")))
            elif source == "binance" and callable(getattr(app, "stop_trading_loop", None)):
                app.stop_trading_loop()
                ok = True
            else:
                raise RuntimeError("headless_runtime_stop_unavailable")
        else:
            raise ValueError("unsupported_runtime_command")
        if ok is False:
            raise RuntimeError(f"runtime_command_rejected:{source}")
        return {"source": source, "command": command, "running_sources": self._running(app)}

    def shutdown(self) -> dict[str, Any]:
        """Prepare the sidecar for process exit. Safe and idempotent."""
        with self._lock:
            if self._app is None:
                return {"safe_to_exit": True, "already_complete": True, "running_sources": []}
            result = self._app.shutdown()
            if result.get("safe_to_exit"):
                self._app = None
            return result


# Compatibility import for local tests/extensions.  The implementation is no
# longer legacy and never imports main.py.
LazyLegacyRuntimeBridge = HeadlessRuntimeBridge
