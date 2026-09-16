"""UI-neutral NoahAI trading runtime for the Web/Electron sidecar.

The desktop shell must never construct a Tk dashboard in order to read an
account or start a worker.  This module owns the existing trading-domain
objects directly and intentionally has no dependency on ``main`` or ``ui``.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from copy import deepcopy
from collections import deque
from datetime import datetime, timezone
from inspect import signature
from pathlib import Path
from typing import Any

from api.binance_client import BinanceClient, BinanceConfig
from config.settings import load_settings
from membership_policy import (
    membership_position_cap,
    membership_denial_code,
    membership_source_access,
    normalize_user_grade,
)
from path_utils import get_app_data_dir, set_current_user_account
from trading.ai.auto_optimizer import AIAutoOptimizer
from trading.ai.ai_manager import create_ai_manager_from_settings
from trading.analyzer import Analyzer
from trading.evaluator import Evaluator
from trading.exchange_manager import ExchangeManager
from trading.market_state import MarketStateAnalyzer
from trading.optimizer import Optimizer
from trading.parallel_strategy_paper import ParallelStrategyPaperEngine
from trading.recorder import Recorder
from trading.risk_manager import RiskManager
from trading.runtime_scope import requires_binance_runtime
from trading.selection_policy import SelectionPolicy, combine_selection_paths, select_advanced_strategy_universe
from trading.stock_runtime_controller import StockRuntimeController
from trading.trader import Trader
from trading.trading_worker import TradingWorker
from trading.unified_trader import UnifiedTrader
from trading.unified_trading_manager import UnifiedTradingManager
from trading.exchanges.venue_capabilities import CRYPTO_VENUES


CRYPTO_SOURCES = set(CRYPTO_VENUES)
CRYPTO_CREDENTIAL_FIELDS = {
    "binance": ("binance_api_key", "binance_secret_key"),
    "upbit": ("upbit_api_key", "upbit_secret_key"),
    "bithumb": ("bithumb_api_key", "bithumb_secret_key"),
    "coinone": ("coinone_api_key", "coinone_secret_key"),
    "bybit": ("bybit_api_key", "bybit_secret_key"),
    "okx": ("okx_api_key", "okx_secret_key", "okx_passphrase"),
    "bitget": ("bitget_api_key", "bitget_secret_key", "bitget_password"),
}
AI_CONNECTION_FIELDS = {
    "ai_provider", "openai_api_key", "openai_model", "assistant_ai_model",
    "ai_credentials", "ai_provider_profiles", "ai_model_roles", "ai_models",
}
STOCK_BROKER_CONFIG_KEYS = {
    "kiwoom": "kiwoom", "shinhan": "shinhan",
    "mirae": "miraeAsset", "kis": "koreaInvestment",
}


class HeadlessTradingRuntime:
    """Own trading workers without importing any desktop UI toolkit."""

    def __init__(self, account: str):
        normalized = str(account or "").strip()
        if not normalized or normalized == "local":
            raise RuntimeError("authenticated_account_required")
        set_current_user_account(normalized)
        self.account = normalized
        self.logger = logging.getLogger("noahai.headless_runtime")
        self.settings: dict[str, Any] = dict(load_settings(persist_migrations=False) or {})
        self._configure_account_logging(self.settings)
        self.selected_coins: list[Any] = []
        self.selected_coins_by_exchange: dict[str, list[Any]] = {}
        self.trading_thread: threading.Thread | None = None
        self.trading_worker: TradingWorker | None = None
        self._accepting_commands = True
        self._shutdown_lock = threading.RLock()
        self._shutdown_complete = False
        self.alpha_arena_runner = None
        self._alpha_arena_events: deque[dict[str, Any]] = deque(maxlen=200)
        self.current_user_grade, self.current_membership_policy = self._load_membership()
        self.membership_position_limit = membership_position_cap(
            self.current_user_grade, self.current_membership_policy
        )
        self._initialize()

    @staticmethod
    def _configure_account_logging(settings: dict[str, Any]) -> None:
        """Mirror the legacy post-login main/per-source log routing."""
        try:
            from log_system.log_adapter import configure_account_logging

            sources = list(settings.get("enabled_exchanges") or []) + list(settings.get("enabled_stock_brokers") or [])
            configure_account_logging(sources=sources, level=str(settings.get("log_level") or "INFO"))
        except Exception:
            pass

    def _load_membership(self) -> tuple[str, dict[str, Any]]:
        token_path = Path(get_app_data_dir()) / "token.json"
        user_info: dict[str, Any] = {}
        try:
            if token_path.exists():
                user_info = dict(json.loads(token_path.read_text(encoding="utf-8")).get("user_info") or {})
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return (
            normalize_user_grade(str(user_info.get("user_grade") or "pro_coin")),
            dict(user_info.get("membership_policy") or {}),
        )

    def _get_main_logger(self) -> logging.Logger:
        return self.logger

    def _initialize(self) -> None:
        self.binance_client = None
        if requires_binance_runtime(self.settings):
            self.binance_client = BinanceClient(BinanceConfig(
                api_key=str(self.settings.get("binance_api_key") or ""),
                secret_key=str(self.settings.get("binance_secret_key") or ""),
                testnet=False,
            ))
        self.unified_manager = UnifiedTradingManager(self.settings)
        self.exchange_manager = ExchangeManager(
            self.settings,
            self.binance_client,
            unified_manager=self.unified_manager,
        )
        from trading.api_signal_manager import APISignalManager
        self.api_signal_manager = APISignalManager(self.exchange_manager, self.settings)
        self.api_signal_manager.start_signal_collection()

        self.recorder = Recorder(binance_client=self.binance_client)
        self.recorder.migrate_database_schema()
        self.analyzer = Analyzer(self.binance_client, exchange_manager=self.exchange_manager)
        optimizer_parameters = signature(Optimizer.__init__).parameters
        optimizer_values = {
            "settings": self.settings,
            "recorder": self.recorder,
            "binance_client": self.binance_client,
            "logger": self.logger,
        }
        self.optimizer = Optimizer(**{
            key: value for key, value in optimizer_values.items() if key in optimizer_parameters
        })
        self.evaluator = Evaluator(self.analyzer, self.recorder, self.settings)
        self.ai_manager = create_ai_manager_from_settings(self.settings, workload="analyst")
        if self.ai_manager is not None:
            self.optimizer.ai_manager = self.ai_manager
        self.risk_manager = RiskManager(
            self.binance_client,
            self.recorder,
            settings=self.settings,
            exchange_manager=self.exchange_manager,
        )
        self.unified_trader = UnifiedTrader(
            settings=self.settings,
            exchange_manager=self.exchange_manager,
            unified_manager=self.unified_manager,
            analyzer=self.analyzer,
            optimizer=self.optimizer,
            recorder=self.recorder,
            ai_manager=self.ai_manager,
            risk_manager=self.risk_manager,
            logger=self.logger,
            dashboard=None,
        )
        self.unified_trader.set_main_app(self)
        self.unified_trader.set_evaluator(self.evaluator)
        self.trader = None
        if self.binance_client is not None:
            self.trader = Trader(
                binance_client=self.binance_client,
                analyzer=self.analyzer,
                optimizer=self.optimizer,
                recorder=self.recorder,
                ai_manager=self.ai_manager,
                logger=self.logger,
                settings=self.settings,
                main_app=self,
            )
        self.market_state_analyzer = MarketStateAnalyzer(self.binance_client) if self.binance_client else None
        if hasattr(self.analyzer, "ai_manager"):
            self.analyzer.ai_manager = self.ai_manager
        self.parallel_strategy_paper = ParallelStrategyPaperEngine(
            settings_provider=lambda: dict(self.settings),
            logger=self.logger,
        )
        self._initialize_strategy_runtime()
        self.auto_optimizer = AIAutoOptimizer(
            ai_manager=self.ai_manager,
            recorder=self.recorder,
            settings=self.settings,
            logger=self.logger,
        )
        self.auto_optimizer.start()
        self.stock_runtime_controller = StockRuntimeController(
            settings_provider=lambda: dict(self.settings),
            recorder=self.recorder,
            strategy_pool_provider=lambda: list(getattr(self, "active_custom_strategy_pool", []) or []),
            paper_strategy_pool_provider=lambda: list(getattr(self, "paper_validation_strategy_pool", []) or []),
            parallel_paper_observer=self.parallel_strategy_paper,
            web_runtime=True,
            logger=self.logger,
        )

    def _initialize_strategy_runtime(self) -> None:
        from ai_chat_strategy import AITradingChatbot
        from strategy_customizer import StrategyCustomizer

        strategy_dir = Path(get_app_data_dir()) / "custom_strategies"
        self.strategy_customizer = StrategyCustomizer(
            self.analyzer, self.trader, self.evaluator, self.risk_manager,
            storage_path=str(strategy_dir / "binance_private.json"),
        )
        self.strategy_customizer_unified = StrategyCustomizer(
            self.analyzer, self.unified_trader, self.evaluator, self.risk_manager,
            storage_path=str(strategy_dir / "unified_private.json"),
        )
        self.ai_trading_chatbot = AITradingChatbot(self.analyzer, self.trader, self.risk_manager)
        if self.trader is not None and hasattr(self.trader, "configure_strategy_runtime"):
            self.trader.configure_strategy_runtime(self.strategy_customizer, self.ai_trading_chatbot)
        if hasattr(self.unified_trader, "configure_strategy_runtime"):
            self.unified_trader.configure_strategy_runtime(self.strategy_customizer_unified, self.ai_trading_chatbot)
        self.sync_custom_strategy_runtime_pools()

    def refresh_settings(self, settings: dict[str, Any]) -> None:
        """Apply the persisted settings to every live settings holder.

        Several trading components intentionally keep their own settings
        dictionary.  Replacing only ``self.settings`` leaves those dictionaries
        stale; a later optimizer/trader save can then overwrite a successful
        Web settings save.  Update every known holder in place so background
        workers retain their object references while observing the canonical
        values.
        """
        canonical = deepcopy(dict(settings or {}))
        previous = deepcopy(dict(getattr(self, "settings", {}) or {}))
        previous_keys = set(self.settings) if isinstance(self.settings, dict) else set()
        holders = [
            self,
            getattr(self, "analyzer", None),
            getattr(self, "trader", None),
            getattr(self, "unified_trader", None),
            getattr(self, "unified_manager", None),
            getattr(self, "exchange_manager", None),
            getattr(self, "api_signal_manager", None),
            getattr(self, "optimizer", None),
            getattr(self, "evaluator", None),
            getattr(self, "risk_manager", None),
            getattr(self, "auto_optimizer", None),
            getattr(self, "alpha_arena_runner", None),
        ]
        trader = getattr(self, "trader", None)
        if trader is not None:
            holders.append(getattr(trader, "tp_sl_manager", None))
        arena = getattr(self, "alpha_arena_runner", None)
        if arena is not None:
            holders.extend([
                getattr(arena, "order_executor", None),
                getattr(arena, "prompt_builder", None),
            ])
        seen: set[int] = set()
        for holder in holders:
            target = getattr(holder, "settings", None) if holder is not None else None
            if not isinstance(target, dict) or id(target) in seen:
                continue
            seen.add(id(target))
            # Preserve component-only defaults that were never part of the
            # application settings contract, while removing deleted canonical
            # keys and replacing every persisted value.
            for key in list(target):
                if key in previous_keys and key not in canonical:
                    target.pop(key, None)
            target.update(deepcopy(canonical))

        if not isinstance(getattr(self, "settings", None), dict):
            self.settings = deepcopy(canonical)

        self._configure_account_logging(canonical)

        # A few legacy connector clients cache diagnostic flags separately
        # from their shared settings dictionary. Refresh those copies after a
        # verified save so log-level/detail controls do not require a restart.
        connector_clients = [getattr(self, "binance_client", None)]
        manager_clients = getattr(getattr(self, "exchange_manager", None), "exchange_clients", None)
        if isinstance(manager_clients, dict):
            connector_clients.extend(manager_clients.values())
        refreshed_clients: set[int] = set()
        for client in connector_clients:
            reload_debug = getattr(client, "_load_debug_settings", None) if client is not None else None
            if not callable(reload_debug) or id(client) in refreshed_clients:
                continue
            refreshed_clients.add(id(client))
            reload_debug()

        # Credential-bearing clients keep their own immutable key/config
        # values. Updating only the shared settings dictionaries leaves the
        # Web runtime authenticating with the old key until restart. Rebuild
        # just those clients after a verified credential save and atomically
        # repoint every live consumer to the new instances.
        self._refresh_connection_clients(previous, canonical)

        unified = getattr(self, "unified_trader", None)
        if unified is not None:
            for attribute, method_name in (
                ("enabled_exchanges", "_compute_enabled_exchanges"),
                ("trade_enabled_exchanges", "_compute_trade_enabled_exchanges"),
                ("learning_enabled_exchanges", "_compute_learning_enabled_exchanges"),
            ):
                compute = getattr(unified, method_name, None)
                if callable(compute):
                    setattr(unified, attribute, compute())

        if hasattr(self, "strategy_customizer"):
            self.sync_custom_strategy_runtime_pools()

    def _refresh_connection_clients(
        self,
        previous: dict[str, Any],
        canonical: dict[str, Any],
    ) -> None:
        scope_fields = (
            "selected_exchange", "enabled_exchanges", "trade_enabled_exchanges",
            "learning_enabled_exchanges",
        )
        scope_changed = any(previous.get(key) != canonical.get(key) for key in scope_fields)
        changed_sources = {
            source
            for source, fields in CRYPTO_CREDENTIAL_FIELDS.items()
            if scope_changed or any(previous.get(field) != canonical.get(field) for field in fields)
        }

        manager = getattr(self, "exchange_manager", None)
        unified_manager = getattr(self, "unified_manager", None)
        if changed_sources:
            reload_settings = getattr(unified_manager, "reload_settings", None)
            if callable(reload_settings):
                reload_settings(self.settings)

            if manager is not None:
                manager.unified_manager = unified_manager
                clients = getattr(manager, "exchange_clients", None)
                invalid = getattr(manager, "invalid_api_keys", None)
                for source in changed_sources:
                    if isinstance(clients, dict):
                        clients.pop(source, None)
                    if isinstance(invalid, set):
                        invalid.discard(source)
                clear_cache = getattr(manager, "clear_cache", None)
                if callable(clear_cache):
                    clear_cache()

        if "binance" in changed_sources:
            old_client = getattr(self, "binance_client", None)
            new_client = None
            if requires_binance_runtime(canonical):
                new_client = BinanceClient(BinanceConfig(
                    api_key=str(canonical.get("binance_api_key") or ""),
                    secret_key=str(canonical.get("binance_secret_key") or ""),
                    testnet=False,
                ))
            elif "binance" in self.running_crypto_exchanges():
                self.stop_trading_loop()
            self.binance_client = new_client
            if manager is not None:
                manager.binance_client = new_client
                if str(canonical.get("selected_exchange") or "").strip().lower() == "binance":
                    manager.current_exchange = new_client
                clients = getattr(manager, "exchange_clients", None)
                if isinstance(clients, dict) and new_client is not None:
                    clients["binance"] = new_client
            for holder_name in (
                "recorder", "analyzer", "optimizer", "evaluator", "risk_manager", "trader",
                "market_state_analyzer",
            ):
                holder = getattr(self, holder_name, None)
                if holder is not None and hasattr(holder, "binance_client"):
                    holder.binance_client = new_client
            evaluator = getattr(self, "evaluator", None)
            invalidate_selection = getattr(evaluator, "invalidate_selection_cache", None)
            if callable(invalidate_selection):
                invalidate_selection("binance")
            if new_client is not None and getattr(self, "trader", None) is None:
                self.trader = Trader(
                    binance_client=new_client,
                    analyzer=self.analyzer,
                    optimizer=self.optimizer,
                    recorder=self.recorder,
                    ai_manager=self.ai_manager,
                    logger=self.logger,
                    settings=self.settings,
                    main_app=self,
                )
                self._initialize_strategy_runtime()
            if old_client is not None and old_client is not new_client:
                stop = getattr(old_client, "stop_websocket_stream", None)
                if callable(stop):
                    try:
                        stop()
                    except Exception:
                        self.logger.debug("이전 Binance WebSocket 종료 실패", exc_info=True)

        if any(previous.get(key) != canonical.get(key) for key in AI_CONNECTION_FIELDS):
            self.ai_manager = create_ai_manager_from_settings(self.settings, workload="analyst")
            for holder_name in ("analyzer", "optimizer", "trader", "unified_trader", "auto_optimizer"):
                holder = getattr(self, holder_name, None)
                if holder is not None and hasattr(holder, "ai_manager"):
                    holder.ai_manager = self.ai_manager

        previous_stock = dict(previous.get("stock_broker_configs") or {})
        canonical_stock = dict(canonical.get("stock_broker_configs") or {})
        enabled_stock_changed = previous.get("enabled_stock_brokers") != canonical.get("enabled_stock_brokers")
        changed_brokers = {
            broker
            for broker, config_key in STOCK_BROKER_CONFIG_KEYS.items()
            if enabled_stock_changed or previous_stock.get(config_key) != canonical_stock.get(config_key)
        }
        stock_controller = getattr(self, "stock_runtime_controller", None)
        adapters = getattr(stock_controller, "_adapters", None)
        if isinstance(adapters, dict):
            for broker in changed_brokers:
                adapters.pop(STOCK_BROKER_CONFIG_KEYS[broker], None)

    def refresh_strategy_runtime(self) -> list[dict[str, Any]]:
        """Reload Web-mutated strategy files into the live execution pool."""
        self._initialize_strategy_runtime()
        return self.sync_custom_strategy_runtime_pools()

    def sync_custom_strategy_runtime_pools(self) -> list[dict[str, Any]]:
        active_combined: list[dict[str, Any]] = []
        paper_combined: list[dict[str, Any]] = []
        paper_mode = bool(self.settings.get("paper_trading", True))
        for customizer in (self.strategy_customizer, self.strategy_customizer_unified):
            active_combined.extend(customizer.get_active_strategy_pool())
            paper_combined.extend(
                getattr(customizer, "get_paper_strategy_pool", customizer.get_active_strategy_pool)()
            )
        active_deduplicated = {
            str(item.get("version_id") or item.get("id")): item
            for item in active_combined if item.get("version_id") or item.get("id")
        }
        paper_deduplicated = {
            str(item.get("version_id") or item.get("id")): item
            for item in paper_combined if item.get("version_id") or item.get("id")
        }
        enabled = bool(dict(self.settings.get("ai_custom_runtime") or {}).get("enabled", False))
        runtime_source = paper_deduplicated if paper_mode else active_deduplicated
        pool = sorted(
            runtime_source.values(), key=lambda item: int(item.get("priority", 5) or 5), reverse=True
        ) if enabled else []
        parallel_enabled = bool(
            dict(self.settings.get("parallel_strategy_paper_validation") or {}).get("enabled", False)
        ) and not paper_mode and enabled
        paper_pool = [
            item for item in sorted(
                paper_deduplicated.values(),
                key=lambda row: int(row.get("priority", 5) or 5),
                reverse=True,
            )
            if str(item.get("operation_mode") or "").lower() == "paper_validation"
        ] if parallel_enabled else []
        for engine in (self.trader, self.unified_trader):
            if engine is not None:
                engine.active_custom_strategy_pool = list(pool)
                engine.paper_validation_strategy_pool = list(paper_pool)
                engine.parallel_paper_observer = getattr(
                    self, "parallel_strategy_paper", None
                )
                engine.active_custom_strategy_rules = {}
                engine.active_custom_strategy_rules_by_exchange = {}
                engine.custom_engine_settings_by_exchange = {}
        self.active_custom_strategy_pool = list(pool)
        self.paper_validation_strategy_pool = list(paper_pool)
        return pool

    def _membership_allows(self, source: str) -> bool:
        return bool(membership_source_access(
            self.current_user_grade, source, self.current_membership_policy,
        ).get("allowed"))

    def apply_server_membership_policy(self, user_grade: Any, policy: dict[str, Any]) -> None:
        """Apply a refreshed server policy and stop newly-disallowed workers.

        Open positions are never force-closed by a membership refresh.  The
        legacy client uses the same fail-closed rule: stop new order loops and
        leave position ownership/exit handling explicit.
        """
        self.current_user_grade = normalize_user_grade(user_grade)
        self.current_membership_policy = dict(policy or {}) if isinstance(policy, dict) else {}
        self.membership_position_limit = membership_position_cap(
            self.current_user_grade, self.current_membership_policy
        )
        for source in list(self.running_crypto_exchanges()):
            if not self._membership_allows(source):
                self.stop_source(source, close_all=False)
        controller = getattr(self, "stock_runtime_controller", None)
        if controller is not None:
            for source in list(controller.running_sources() or []):
                if not self._membership_allows(source):
                    controller.stop(source, close_all=False)

    def assert_command_allowed(self, source: str) -> None:
        if not self._accepting_commands:
            raise RuntimeError("runtime_shutdown_in_progress")
        if not self._membership_allows(source):
            code = membership_denial_code(
                self.current_user_grade, source, self.current_membership_policy,
            )
            raise RuntimeError(f"{code}:{str(source or '').strip().lower()}")

    def running_crypto_exchanges(self) -> list[str]:
        running: list[str] = []
        worker = getattr(self, "trading_worker", None)
        thread = getattr(self, "trading_thread", None)
        if bool(getattr(worker, "running", False)) or bool(thread and thread.is_alive()):
            running.append("binance")
        unified = getattr(self, "unified_trader", None)
        for source, active in dict(getattr(unified, "monitoring_flags", {}) or {}).items():
            thread = dict(getattr(unified, "monitoring_threads", {}) or {}).get(source)
            if active and thread is not None and thread.is_alive() and str(source).lower() in CRYPTO_SOURCES - {"binance"}:
                running.append(str(source).lower())
        return list(dict.fromkeys(running))

    def live_crypto_workers(self) -> list[str]:
        """Return live threads even after their stop flags were cleared."""
        running: list[str] = []
        worker = getattr(self, "trading_worker", None)
        thread = getattr(self, "trading_thread", None)
        if (thread is not None and thread.is_alive()) or bool(getattr(worker, "running", False)):
            running.append("binance")
        unified = getattr(self, "unified_trader", None)
        thread_registry = getattr(unified, "monitoring_threads", None)
        for source, worker_thread in dict(thread_registry or {}).items():
            if worker_thread is not None and worker_thread.is_alive() and str(source).lower() in CRYPTO_SOURCES - {"binance"}:
                running.append(str(source).lower())
        # Compatibility for older test/runtime objects that do not expose the
        # lifecycle registry yet. New UnifiedTrader instances always do.
        if thread_registry is None:
            for source, active in dict(getattr(unified, "monitoring_flags", {}) or {}).items():
                if active and str(source).lower() in CRYPTO_SOURCES - {"binance"}:
                    running.append(str(source).lower())
        return list(dict.fromkeys(running))

    def start_source(self, source: str) -> bool:
        normalized = str(source or "").strip().lower()
        self.assert_command_allowed(normalized)
        configured_scope = {
            str(item or "").strip().lower()
            for key in ("enabled_exchanges", "learning_enabled_exchanges", "trade_enabled_exchanges")
            for item in (self.settings.get(key, []) or [])
        }
        if normalized not in configured_scope:
            raise RuntimeError(f"runtime_source_not_enabled:{normalized}")
        if normalized == "binance":
            if self.trader is None:
                raise RuntimeError("binance_runtime_not_ready")
            self.settings["selected_exchange"] = "binance"
            if not self.selected_coins:
                self.select_trading_coins()
            return self.start_trading_loop()
        return bool(self.unified_trader.start_trading(normalized))

    def stop_source(self, source: str, *, close_all: bool = False) -> bool:
        normalized = str(source or "").strip().lower()
        if normalized == "binance":
            if close_all:
                raise RuntimeError("account_wide_close_blocked:position_ownership_required")
            self.stop_trading_loop()
            return True
        self.unified_trader.stop_trading(normalized, close_all=close_all)
        return True

    def start_trading_loop(self) -> bool:
        daily_loss = self.risk_manager.evaluate_daily_loss_limit(
            source="binance",
        )
        if daily_loss.blocked:
            raise RuntimeError(
                "risk_data_unavailable"
                if daily_loss.status == "risk_data_unavailable"
                else "daily_loss_limit_exceeded"
            )
        if self.trading_thread and self.trading_thread.is_alive():
            return True
        self.trading_thread = threading.Thread(
            target=self._trading_loop_thread, daemon=True, name="noahai-binance-runtime"
        )
        self.trading_thread.start()
        return True

    def _trading_loop_thread(self) -> None:
        self.trading_worker = self.trading_worker or TradingWorker(self)
        self.trading_worker.start()
        self.trading_worker.run_trading_loop()

    def stop_trading_loop(self) -> None:
        self.request_trading_loop_stop()
        stopped = self.wait_for_trading_loop_stop(timeout=5.0)
        if not stopped:
            raise RuntimeError("binance_worker_shutdown_timeout")

    def request_trading_loop_stop(self) -> None:
        """Broadcast the native Binance stop without serially joining the worker."""
        if self.trading_worker is not None:
            # CCXT venues are independent Web runtime workers. Their stop
            # signals are broadcast by shutdown() and must not be joined in
            # series from inside the Binance worker. TradingWorker owns the
            # native Binance trader stop, so do not invoke it a second time.
            request_stop = getattr(self.trading_worker, "request_stop", None)
            if callable(request_stop):
                request_stop(stop_unified=False)
            else:
                self.trading_worker.stop(stop_unified=False)
        elif self.trader is not None:
            self.trader.stop_trading()

    def wait_for_trading_loop_stop(self, *, timeout: float) -> bool:
        deadline = time.monotonic() + max(0.0, float(timeout))
        thread = self.trading_thread
        if thread is not None and thread is not threading.current_thread() and thread.is_alive():
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        main_stopped = thread is None or thread is threading.current_thread() or not thread.is_alive()
        monitor_threads = dict(getattr(getattr(self, "trader", None), "monitoring_threads", {}) or {})
        alive_monitors: list[str] = []
        for symbol, monitor in monitor_threads.items():
            if monitor is None or monitor is threading.current_thread() or not monitor.is_alive():
                continue
            monitor.join(timeout=max(0.0, deadline - time.monotonic()))
            if monitor.is_alive():
                alive_monitors.append(str(symbol))
        return main_stopped and not alive_monitors

    def select_trading_coins(self) -> list[Any]:
        if self.trader is None:
            self.selected_coins = []
            return []
        try:
            regime = self.trader._analyze_market_regime_binance_fast()
        except Exception:
            regime = "normal"
        settings = self.settings
        regime_config = dict(dict(settings.get("market_regime_coins") or {}).get(regime) or {})
        total = max(1, int(regime_config.get("min", 15) or 15))
        ratios = dict(dict(settings.get("coin_selection_ratios") or {}).get(regime) or {})
        alt = int(total * float(ratios.get("altcoin_ratio", 0.7) or 0.7))
        major = max(0, total - alt)
        automatic = self.evaluator.select_trading_coins(alt, major, regime) or []
        pinned = list(dict(dict(settings.get("crypto_selection") or {}).get("manual_symbols_by_exchange") or {}).get("binance", []) or [])
        general = SelectionPolicy(target="binance", asset_class="crypto", limit=total).resolve(
            automatic_candidates=automatic, pinned_symbols=pinned
        )
        advanced = select_advanced_strategy_universe(
            strategy_pool=list(getattr(self.trader, "active_custom_strategy_pool", []) or []),
            market_candidates=automatic,
            pinned_symbols=pinned,
            asset_class="crypto",
            target="binance",
            default_limit=total,
        )
        self.selected_coins = combine_selection_paths(general, advanced)
        return list(self.selected_coins)

    def _record_alpha_event(self, kind: str, payload: Any) -> None:
        self._alpha_arena_events.append({
            "at": datetime.now(timezone.utc).isoformat(),
            "kind": str(kind),
            "payload": payload if isinstance(payload, (dict, list, str, int, float, bool)) or payload is None else str(payload),
        })

    def alpha_arena_snapshot(self) -> dict[str, Any]:
        arena_settings = dict(self.settings.get("alpha_arena") or {})
        runner_status = self.alpha_arena_runner.get_status() if self.alpha_arena_runner is not None else {
            "running": False,
            "session_id": None,
            "session_start_time": None,
            "tick_interval_sec": max(30, int(arena_settings.get("tick_interval_sec", 60) or 60)),
            "engine": str(arena_settings.get("engine") or "deepseek-v4-flash"),
            "metrics": None,
        }
        paper = bool(self.settings.get("paper_trading", True))
        return {
            **runner_status,
            "available": bool(arena_settings.get("enabled", False)),
            "paper_trading": paper,
            "execution_mode": "PAPER" if paper else "LIVE_BLOCKED_PENDING_EXTERNAL_GATE",
            "order_submission": False if paper else "blocked",
            "events": list(self._alpha_arena_events),
            "symbols": list(arena_settings.get("symbols") or []),
            "risk": {
                "max_concurrent_positions": int(arena_settings.get("max_concurrent_positions", 6) or 6),
                "max_risk_per_tick": float(arena_settings.get("max_risk_per_tick", 1500.0) or 1500.0),
                "cooldown_sec_per_symbol": int(arena_settings.get("cooldown_sec_per_symbol", 30) or 30),
                "require_tp_sl": True,
            },
            "reason": "ready" if arena_settings.get("enabled", False) else "alpha_arena_disabled_in_settings",
        }

    def alpha_arena_control(self, *, action: str, live_confirmation: bool = False) -> dict[str, Any]:
        normalized = str(action or "").strip().lower()
        if normalized not in {"start", "stop"}:
            raise ValueError("unsupported_alpha_arena_action")
        if normalized == "stop":
            if self.alpha_arena_runner is not None:
                self.alpha_arena_runner.stop()
                self._record_alpha_event("lifecycle", {"action": "stop"})
            return self.alpha_arena_snapshot()
        self.assert_command_allowed("binance")
        arena_settings = dict(self.settings.get("alpha_arena") or {})
        if not bool(arena_settings.get("enabled", False)):
            raise RuntimeError("alpha_arena_disabled_in_settings")
        if not bool(self.settings.get("paper_trading", True)):
            # The existing arena owns a direct Binance futures executor.  It is
            # intentionally held behind the Windows/PAPER external gate until
            # order ownership and rollback have been proven in the packaged app.
            raise RuntimeError("alpha_arena_live_blocked_pending_external_gate")
        if self.binance_client is None:
            raise RuntimeError("alpha_arena_binance_runtime_not_ready")
        if self.ai_manager is None or not callable(getattr(self.ai_manager, "enabled", None)) or not self.ai_manager.enabled():
            raise RuntimeError("alpha_arena_ai_provider_not_ready")
        if self.alpha_arena_runner is None:
            from trading.alpha_arena.runner import AlphaArenaRunner

            self.alpha_arena_runner = AlphaArenaRunner(
                binance_client=self.binance_client,
                ai_manager=self.ai_manager,
                settings=self.settings,
                recorder=self.recorder,
            )
            self.alpha_arena_runner.set_callbacks(
                on_model_chat=lambda value: self._record_alpha_event("model_chat", value),
                on_trading_decisions=lambda value: self._record_alpha_event("decision", value),
                on_order_result=lambda symbol, value: self._record_alpha_event("paper_result", {"symbol": symbol, "result": value}),
                on_error=lambda value: self._record_alpha_event("error", value),
            )
        if not self.alpha_arena_runner.running:
            if not self.alpha_arena_runner.start():
                raise RuntimeError("alpha_arena_start_rejected")
            self._record_alpha_event("lifecycle", {"action": "start", "mode": "PAPER"})
        return self.alpha_arena_snapshot()

    def shutdown(self) -> dict[str, Any]:
        """Stop entry producers and flush durable state without closing manual positions."""
        with self._shutdown_lock:
            if self._shutdown_complete:
                return {"safe_to_exit": True, "already_complete": True, "running_sources": []}
            self._accepting_commands = False
            errors: list[str] = []
            if self.alpha_arena_runner is not None:
                try:
                    self.alpha_arena_runner.stop()
                except Exception as exc:
                    errors.append(f"alpha_arena:{exc}")
            stock_controller = self.stock_runtime_controller
            stock_lifecycle_getter = getattr(stock_controller, "lifecycle_sources", None)
            stock_live_getter = getattr(stock_controller, "live_worker_sources", None)
            stock_sources = list(
                stock_lifecycle_getter()
                if callable(stock_lifecycle_getter)
                else stock_live_getter()
                if callable(stock_live_getter)
                else stock_controller.running_sources()
            )
            stock_request_stop = getattr(stock_controller, "request_stop", None)
            stock_wait_stops = getattr(stock_controller, "wait_for_stops", None)
            if callable(stock_request_stop) and callable(stock_wait_stops):
                for source in stock_sources:
                    try:
                        stock_request_stop(source)
                    except Exception as exc:
                        errors.append(f"{source}:{exc}")
            else:
                for source in stock_sources:
                    try:
                        if stock_controller.stop(source) is False:
                            errors.append(f"{source}:worker_shutdown_timeout")
                    except Exception as exc:
                        errors.append(f"{source}:{exc}")
            live_crypto_getter = getattr(self, "live_crypto_workers", None)
            crypto_sources = list(dict.fromkeys(
                list(self.running_crypto_exchanges())
                + list(live_crypto_getter() if callable(live_crypto_getter) else [])
            ))
            unified_sources = [source for source in crypto_sources if source != "binance"]
            unified = getattr(self, "unified_trader", None)
            request_stop = getattr(unified, "request_trading_stop", None)
            wait_stops = getattr(unified, "wait_for_trading_stops", None)
            shutdown_deadline = time.monotonic() + 45.0
            if callable(request_stop) and callable(wait_stops):
                # Broadcast first so every exchange can leave its current
                # analysis/network boundary concurrently.
                for source in unified_sources:
                    request_stop(source)
                if "binance" in crypto_sources:
                    try:
                        self.request_trading_loop_stop()
                    except Exception as exc:
                        errors.append(f"binance:{exc}")
                # A Binance cycle may already be inside one final provider call.
                # Give every pre-signalled worker one shared deadline instead of
                # declaring failure after the old five-second serial join.
                if "binance" in crypto_sources:
                    remaining = max(0.0, shutdown_deadline - time.monotonic())
                    if not self.wait_for_trading_loop_stop(timeout=remaining):
                        errors.append("binance:worker_shutdown_timeout")
                remaining = max(0.0, shutdown_deadline - time.monotonic())
                stopped = wait_stops(unified_sources, timeout=remaining) or {}
                for source in list(stopped.get("alive") or []):
                    errors.append(f"{source}:worker_shutdown_timeout")
            else:
                for source in crypto_sources:
                    try:
                        self.stop_source(source, close_all=False)
                    except Exception as exc:
                        errors.append(f"{source}:{exc}")
            if callable(stock_request_stop) and callable(stock_wait_stops):
                remaining = max(0.0, shutdown_deadline - time.monotonic())
                stopped = stock_wait_stops(stock_sources, timeout=remaining) or {}
                for source in list(stopped.get("alive") or []):
                    errors.append(f"{source}:worker_shutdown_timeout")
            for component, method_name in (
                (self.api_signal_manager, "stop_signal_collection"),
                (self.auto_optimizer, "stop"),
            ):
                method = getattr(component, method_name, None)
                if callable(method):
                    try:
                        method()
                    except Exception as exc:
                        errors.append(f"{method_name}:{exc}")
            try:
                if self.recorder.flush_to_db(timeout=10) is False:
                    errors.append("recorder_flush_failed")
            except Exception as exc:
                errors.append(f"recorder_flush:{exc}")
            remaining_crypto = list(self.live_crypto_workers())
            stock_live_getter = getattr(stock_controller, "live_worker_sources", None)
            remaining_stock = list(stock_live_getter() if callable(stock_live_getter) else stock_controller.running_sources())
            child_getter = getattr(stock_controller, "live_child_sources", None)
            remaining_children = list(child_getter() if callable(child_getter) else [])
            for source in remaining_crypto + remaining_stock + remaining_children:
                error = f"{source}:runtime_still_alive"
                if error not in errors:
                    errors.append(error)
            if not errors:
                try:
                    from log_system.log_adapter import flush_pending_logs
                    flush_pending_logs()
                    from utils.runtime_stability import mark_clean_shutdown
                    mark_clean_shutdown("web_engine_shutdown")
                except Exception as exc:
                    errors.append(f"final_flush:{exc}")
            self._shutdown_complete = not errors
            return {
                "safe_to_exit": not errors,
                "already_complete": False,
                "running_sources": list(dict.fromkeys(remaining_crypto + remaining_stock + remaining_children)),
                "errors": errors,
            }
