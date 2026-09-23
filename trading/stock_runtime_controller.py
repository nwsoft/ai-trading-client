"""UI-neutral stock/ETF runtime controller used by desktop shells.

The controller owns worker lifetime only.  It never reads or mutates widgets,
never closes an account-wide position set, and delegates every order candidate
to StockAnalysisService where execution mode and guardrails are rechecked.
"""

from __future__ import annotations

import logging
import threading
import time
from copy import deepcopy
from typing import Any, Callable

from trading.advanced_layer_config import deep_merge_policy
from trading.execution_mode import ExecutionMode, resolve_stock_execution_mode
from trading.exchanges.exchange_factory import ExchangeFactory
from trading.stock_analysis_service import StockAnalysisService, select_stock_universe
from trading.stock_order_guardrails import normalize_stock_order_guardrails


BROKER_ALIASES = {
    "kiwoom": "kiwoom",
    "shinhan": "shinhan",
    "mirae": "miraeAsset",
    "miraeasset": "miraeAsset",
    "kis": "koreaInvestment",
    "koreainvestment": "koreaInvestment",
}
PUBLIC_BROKER_IDS = {"miraeAsset": "mirae", "koreaInvestment": "kis"}


class StockRuntimeController:
    def __init__(
        self,
        *,
        settings_provider: Callable[[], dict[str, Any]],
        recorder: Any = None,
        strategy_pool_provider: Callable[[], list[dict[str, Any]]] | None = None,
        paper_strategy_pool_provider: Callable[[], list[dict[str, Any]]] | None = None,
        parallel_paper_observer: Any = None,
        adapter_factory: Callable[[str, dict[str, Any]], Any] = ExchangeFactory.create_stock_exchange,
        service_factory: Callable[..., Any] = StockAnalysisService,
        web_runtime: bool = False,
        logger: logging.Logger | None = None,
    ):
        self.settings_provider = settings_provider
        self.recorder = recorder
        self.strategy_pool_provider = strategy_pool_provider or (lambda: [])
        self.paper_strategy_pool_provider = paper_strategy_pool_provider or (lambda: [])
        self.parallel_paper_observer = parallel_paper_observer
        self.adapter_factory = adapter_factory
        self.service_factory = service_factory
        self.web_runtime = bool(web_runtime)
        self.logger = logger or logging.getLogger(__name__)
        self._events: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._adapters: dict[str, Any] = {}
        self._services: dict[str, Any] = {}
        self._universe_cache: dict[str, tuple[float, tuple[Any, ...], list[str]]] = {}
        self._errors: dict[str, str] = {}
        self._last_results: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def _settings_snapshot(self) -> dict[str, Any]:
        settings = deepcopy(self.settings_provider() or {})
        if self.web_runtime:
            # Explicit controller provenance is more reliable than inheriting
            # an environment variable through Electron/Python packaging.
            settings["_noahai_web_runtime"] = True
        return settings

    @staticmethod
    def _canonical(source: str) -> str:
        normalized = str(source or "").replace("_", "").strip().lower()
        if normalized not in BROKER_ALIASES:
            raise ValueError("unsupported_stock_source")
        return BROKER_ALIASES[normalized]

    def running_sources(self) -> list[str]:
        with self._lock:
            return [
                PUBLIC_BROKER_IDS.get(source, source) for source, thread in self._threads.items()
                if thread.is_alive() and not self._events[source].is_set()
            ]

    def live_worker_sources(self) -> list[str]:
        """Return every live worker, including workers already asked to stop.

        ``running_sources`` is a UI state (accepting another cycle).  Safe
        shutdown needs a lifecycle state and must not lose a thread merely
        because its stop event has already been set.
        """
        with self._lock:
            return [
                PUBLIC_BROKER_IDS.get(source, source)
                for source, thread in self._threads.items()
                if thread.is_alive()
            ]

    def live_child_sources(self) -> list[str]:
        """Return adapters that still own a live helper process."""
        with self._lock:
            result = []
            for source, adapter in self._adapters.items():
                process = getattr(adapter, "_process", None)
                if process is not None and callable(getattr(process, "is_alive", None)) and process.is_alive():
                    result.append(PUBLIC_BROKER_IDS.get(source, source))
            return result

    def lifecycle_sources(self) -> list[str]:
        """Return every runtime-owned broker resource that must be released.

        Account, symbol and candle reads may construct a broker adapter (and
        Kiwoom may start its COM helper process) without starting an automatic
        trading worker.  Safe shutdown therefore cannot use worker state alone.
        """
        return list(dict.fromkeys(self.live_worker_sources() + self._public_adapter_sources()))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running_sources": self.running_sources(),
                "last_results": deepcopy(self._last_results),
                "errors": dict(self._errors),
            }

    def account_snapshot(self, source: str) -> dict[str, Any]:
        """Read one broker account through the same adapter used by the worker.

        This is an explicit user-requested read.  It never submits or closes an
        order and returns component errors independently so one unsupported API
        cannot erase the remaining account state.
        """
        broker = self._canonical(source)
        settings = self._settings_snapshot()
        enabled = {self._canonical(item) for item in settings.get("enabled_stock_brokers", [])}
        if broker not in enabled:
            return {"source": PUBLIC_BROKER_IDS.get(broker, broker), "status": "disabled"}
        with self._lock:
            adapter = self._adapters.get(broker)
            if adapter is None:
                adapter = self.adapter_factory(broker, settings)
                if adapter is None:
                    return {"source": PUBLIC_BROKER_IDS.get(broker, broker), "status": "adapter_unavailable"}
                self._adapters[broker] = adapter
        try:
            if hasattr(adapter, "connect") and not bool(getattr(adapter, "is_connected", False)):
                connected = adapter.connect()
                if connected is False:
                    return {"source": PUBLIC_BROKER_IDS.get(broker, broker), "status": "connection_failed",
                            "error": str(getattr(adapter, "last_error", "") or getattr(adapter, "_last_connect_failure_reason", "") or "connection_rejected")}
        except Exception as exc:
            return {"source": PUBLIC_BROKER_IDS.get(broker, broker), "status": "connection_failed", "error": str(exc)}

        result: dict[str, Any] = {"source": PUBLIC_BROKER_IDS.get(broker, broker), "status": "success"}
        for key, method_name, empty in (
            ("balance", "get_balance", {}),
            ("positions", "get_positions", []),
            ("open_orders", "get_open_orders", []),
        ):
            method = getattr(adapter, method_name, None)
            if not callable(method):
                result[key] = empty
                result[f"{key}_status"] = "unsupported"
                continue
            try:
                if key == "positions" and callable(getattr(adapter, "get_positions_result", None)):
                    snapshot = adapter.get_positions_result()
                    if not isinstance(snapshot, dict) or snapshot.get("status") != "success" or not isinstance(snapshot.get("positions"), list):
                        result[key] = None
                        result[f"{key}_status"] = "error"
                        result[f"{key}_error"] = "positions_unavailable"
                        continue
                    result[key] = snapshot["positions"]
                    result[f"{key}_status"] = "success"
                    continue
                result[key] = method() or empty
                result[f"{key}_status"] = "success"
            except Exception as exc:
                result[key] = empty
                result[f"{key}_status"] = "error"
                result[f"{key}_error"] = str(exc)
        if bool(settings.get("paper_trading", False)):
            try:
                paper_store = StockAnalysisService._paper_positions_by_broker.get(
                    str(broker).lower(), {},
                )
                result["paper_positions"] = [
                    deepcopy(row) for row in dict(paper_store or {}).values()
                ]
                result["paper_positions_status"] = "success"
            except (AttributeError, RuntimeError, TypeError, ValueError):
                result["paper_positions"] = []
                result["paper_positions_status"] = "temporarily_unavailable"
        else:
            result["paper_positions"] = []
            result["paper_positions_status"] = "not_paper"
        return result

    def paper_position_snapshot(self, source: str) -> dict[str, Any]:
        """Return broker PAPER positions without connecting to the broker account."""
        broker = self._canonical(source)
        settings = self._settings_snapshot()
        public_source = PUBLIC_BROKER_IDS.get(broker, broker)
        if not bool(settings.get("paper_trading", False)):
            return {"source": public_source, "status": "not_paper", "positions": []}
        try:
            paper_store = StockAnalysisService._paper_positions_by_broker.get(
                str(broker).lower(), {},
            )
            return {
                "source": public_source,
                "status": "success",
                "positions": [deepcopy(row) for row in dict(paper_store or {}).values()],
            }
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return {"source": public_source, "status": "temporarily_unavailable", "positions": []}

    def market_candles(self, source: str, symbol: str, limit: int = 300) -> list[dict[str, Any]]:
        """Read broker daily candles without starting an order worker."""
        broker = self._canonical(source)
        settings = self._settings_snapshot()
        enabled = {self._canonical(item) for item in settings.get("enabled_stock_brokers", [])}
        if broker not in enabled:
            raise RuntimeError(f"stock_source_not_enabled:{PUBLIC_BROKER_IDS.get(broker, broker)}")
        normalized_symbol = str(symbol or "").strip()
        if not normalized_symbol.isdigit() or not 5 <= len(normalized_symbol) <= 8:
            raise ValueError("invalid_stock_symbol")
        with self._lock:
            adapter = self._adapters.get(broker)
            if adapter is None:
                adapter = self.adapter_factory(broker, settings)
                if adapter is None:
                    raise RuntimeError(f"stock_adapter_unavailable:{PUBLIC_BROKER_IDS.get(broker, broker)}")
                self._adapters[broker] = adapter
        if hasattr(adapter, "connect") and not bool(getattr(adapter, "is_connected", False)):
            connected = adapter.connect()
            if connected is False:
                raise RuntimeError(f"stock_connection_failed:{PUBLIC_BROKER_IDS.get(broker, broker)}")
        getter = getattr(adapter, "get_daily_candles", None)
        if not callable(getter):
            raise RuntimeError(f"stock_candles_unsupported:{PUBLIC_BROKER_IDS.get(broker, broker)}")
        rows = getter(normalized_symbol, max(10, min(int(limit), 500))) or []
        if not rows:
            raise RuntimeError(f"stock_candles_unavailable:{PUBLIC_BROKER_IDS.get(broker, broker)}")
        return [dict(row) for row in rows if isinstance(row, dict)]

    def analyze_symbol(self, source: str, symbol: str) -> dict[str, Any]:
        """Run the same broker-backed ``StockAnalysisService`` used by the legacy UI.

        The Web shell must not replace the established stock analysis with a
        public quote-only approximation.  This remains a read-only operation:
        it creates no worker and submits no order.
        """
        broker = self._canonical(source)
        settings = self._settings_snapshot()
        enabled = {self._canonical(item) for item in settings.get("enabled_stock_brokers", [])}
        if broker not in enabled:
            raise RuntimeError(f"stock_source_not_enabled:{PUBLIC_BROKER_IDS.get(broker, broker)}")
        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol.isdigit() or not 5 <= len(normalized_symbol) <= 8:
            raise ValueError("invalid_stock_symbol")
        with self._lock:
            adapter = self._adapters.get(broker)
            if adapter is None:
                adapter = self.adapter_factory(broker, settings)
                if adapter is None:
                    raise RuntimeError(f"stock_adapter_unavailable:{PUBLIC_BROKER_IDS.get(broker, broker)}")
                self._adapters[broker] = adapter
        if hasattr(adapter, "connect") and not bool(getattr(adapter, "is_connected", False)):
            connected = adapter.connect()
            if connected is False:
                raise RuntimeError(f"stock_connection_failed:{PUBLIC_BROKER_IDS.get(broker, broker)}")
        service = self.service_factory(
            adapter,
            broker_name=PUBLIC_BROKER_IDS.get(broker, broker),
            recorder=self.recorder,
        )
        result = service.analyze_symbol(normalized_symbol)
        if not isinstance(result, dict) or result.get("status") != "ok":
            raise RuntimeError(f"stock_analysis_unavailable:{normalized_symbol}")
        return deepcopy(result)

    def symbol_suggestions(self, source: str, query: str = "", asset_mode: str = "all", limit: int = 8) -> list[dict[str, Any]]:
        """Return the legacy broker-backed stock/ETF autocomplete list.

        This mirrors ``dashboard_modern._build_stock_symbol_index`` without
        importing any widget.  It only reads broker symbol lists and never
        starts a worker or submits an order.
        """
        broker = self._canonical(source)
        settings = self._settings_snapshot()
        enabled = {self._canonical(item) for item in settings.get("enabled_stock_brokers", [])}
        if broker not in enabled:
            return []
        with self._lock:
            adapter = self._adapters.get(broker)
            if adapter is None:
                adapter = self.adapter_factory(broker, settings)
                if adapter is None:
                    return []
                self._adapters[broker] = adapter
        if hasattr(adapter, "connect") and not bool(getattr(adapter, "is_connected", False)):
            try:
                if adapter.connect() is False:
                    return []
            except Exception:
                return []

        mode = str(asset_mode or "all").strip().lower()
        if mode not in {"all", "stock", "etf"}:
            mode = "all"
        needle = str(query or "").strip().upper()
        maximum = max(1, min(int(limit or 8), 20))
        indexed: list[dict[str, Any]] = []
        seen: set[str] = set()
        for kind, is_etf_default, method_name, args in (
            ("stock", False, "get_stock_list", ("ALL",)),
            ("etf", True, "get_etf_list", ()),
        ):
            getter = getattr(adapter, method_name, None)
            if not callable(getter):
                continue
            try:
                raw_items = getter(*args) or []
            except Exception:
                raw_items = []
            for item in raw_items[:220]:
                if not isinstance(item, dict):
                    continue
                code = str(item.get("code") or item.get("symbol") or "").strip().upper()
                if not code or code in seen:
                    continue
                is_etf = bool(item.get("is_etf", is_etf_default))
                detector = getattr(adapter, "is_etf", None)
                if callable(detector):
                    try:
                        is_etf = bool(detector(code))
                    except Exception:
                        pass
                if mode != "all" and (mode == "etf") != is_etf:
                    continue
                name = str(item.get("name") or code).strip()
                indexed.append({
                    "code": code,
                    "name": name or code,
                    "is_etf": is_etf,
                    "broker": PUBLIC_BROKER_IDS.get(broker, broker),
                    "kind": kind,
                })
                seen.add(code)

        def rank(item: dict[str, Any]) -> tuple[int, str]:
            code = str(item["code"]).upper()
            name = str(item["name"]).upper()
            if not needle:
                return (4, code)
            if code.startswith(needle):
                return (0, code)
            if needle in code:
                return (1, code)
            if name.startswith(needle):
                return (2, code)
            if needle in name:
                return (3, code)
            return (99, code)

        return [deepcopy(item) for item in sorted(indexed, key=rank) if rank(item)[0] < 99][:maximum]

    def start(self, source: str) -> bool:
        broker = self._canonical(source)
        settings = self.settings_provider() or {}
        enabled = {self._canonical(item) for item in settings.get("enabled_stock_brokers", [])}
        if broker not in enabled:
            raise RuntimeError(f"stock_source_not_enabled:{broker}")
        with self._lock:
            current = self._threads.get(broker)
            if current is not None and current.is_alive():
                return True
            stop_event = threading.Event()
            self._events[broker] = stop_event
            thread = threading.Thread(
                target=self._worker,
                args=(broker, stop_event),
                daemon=True,
                name=f"noahai-stock-{broker}",
            )
            self._threads[broker] = thread
            thread.start()
        return True

    def request_stop(self, source: str, *, close_all: bool = False) -> None:
        broker = self._canonical(source)
        if close_all:
            raise RuntimeError("account_wide_close_blocked:position_ownership_required")
        with self._lock:
            event = self._events.get(broker)
            if event is not None:
                event.set()

    def wait_for_stops(self, sources: list[str], *, timeout: float = 12.0) -> dict[str, list[str]]:
        """Wait for signalled workers against one deadline and release adapters."""
        deadline = time.monotonic() + max(0.0, float(timeout or 0.0))
        stopped: list[str] = []
        alive: list[str] = []
        for public_source in list(dict.fromkeys(sources or [])):
            broker = self._canonical(public_source)
            with self._lock:
                thread = self._threads.get(broker)
            if thread is not None and thread is not threading.current_thread() and thread.is_alive():
                thread.join(timeout=max(0.0, deadline - time.monotonic()))
            if thread is not None and thread.is_alive():
                alive.append(PUBLIC_BROKER_IDS.get(broker, broker))
                continue
            with self._lock:
                adapter = self._adapters.get(broker)
            disconnect = getattr(adapter, "disconnect", None)
            if callable(disconnect):
                try:
                    disconnected = disconnect()
                    if disconnected is False:
                        alive.append(PUBLIC_BROKER_IDS.get(broker, broker))
                        continue
                except Exception as exc:
                    self.logger.warning("Stock adapter disconnect failed: %s: %s", broker, exc)
                    alive.append(PUBLIC_BROKER_IDS.get(broker, broker))
                    continue
            with self._lock:
                self._threads.pop(broker, None)
                self._events.pop(broker, None)
                self._adapters.pop(broker, None)
                self._services.pop(broker, None)
                self._universe_cache.pop(broker, None)
            stopped.append(PUBLIC_BROKER_IDS.get(broker, broker))
        return {"stopped": stopped, "alive": list(dict.fromkeys(alive))}

    def stop(self, source: str, *, close_all: bool = False, timeout: float = 5.0) -> bool:
        self.request_stop(source, close_all=close_all)
        return not self.wait_for_stops([source], timeout=timeout)["alive"]

    def stop_all(self, *, timeout: float = 12.0) -> dict[str, list[str]]:
        sources = self.lifecycle_sources()
        for source in sources:
            self.request_stop(source)
        return self.wait_for_stops(sources, timeout=timeout)

    def _public_adapter_sources(self) -> list[str]:
        with self._lock:
            return [PUBLIC_BROKER_IDS.get(source, source) for source in self._adapters]

    def _broker_config(self, settings: dict[str, Any], broker: str) -> dict[str, Any]:
        configs = settings.get("stock_broker_configs", {}) or {}
        for key in (broker, broker.lower(), "mirae_asset" if broker == "miraeAsset" else "", "kis" if broker == "koreaInvestment" else ""):
            if key and isinstance(configs.get(key), dict):
                return dict(configs[key])
        return {}

    def _live_permission(self, settings: dict[str, Any], broker: str, adapter: Any) -> tuple[bool, str]:
        cfg = self._broker_config(settings, broker)
        api_type = str(cfg.get("api_type") or getattr(adapter, "api_type", "") or "openapi").lower()
        api_version = str(cfg.get("api_version") or getattr(adapter, "api_version", "") or "").lower()
        ready, reason = None, ""
        readiness = getattr(adapter, "get_live_readiness", None)
        if callable(readiness):
            ready, reason = readiness()
        return ExchangeFactory.evaluate_stock_live_order_permission(
            broker=broker,
            api_type=api_type,
            api_version=api_version,
            global_live_flag=bool(settings.get("enable_stock_live_order", False)),
            broker_live_flag=bool(cfg.get("allow_live_order", False)),
            adapter_ready=ready,
            adapter_ready_reason=reason,
        )

    def _worker(self, broker: str, stop_event: threading.Event) -> None:
        from trading.runtime_observability import emit_runtime_status
        emit_runtime_status(self, broker, "starting", "증권 실행 워커 시작 · API 인증 후 종목 선정·분석 상태를 확인합니다.")
        while not stop_event.is_set():
            try:
                result, interval = self._run_once(broker)
                analysis_errors = [item for item in result.get("decisions", [])
                                   if item.get("reason") == "analysis_error"]
                with self._lock:
                    self._last_results[broker] = result
                    if analysis_errors:
                        self._errors[broker] = str(analysis_errors[0].get("analysis_error") or "analysis_error")
                    else:
                        self._errors.pop(broker, None)
                reason = str(result.get("reason") or result.get("blocked_reason") or "cycle_complete")
                if reason == "empty_stock_universe":
                    message = "분석 대기 · 분석 가능한 주식·ETF 후보가 없습니다. 종목 목록 연결 또는 설정의 관심종목을 확인하세요. 잔고 인증 성공과 종목 분석 가능 여부는 별개입니다."
                elif analysis_errors:
                    reason = "stock_analysis_incomplete"
                    message = f"증권 분석 일부 실패 · {len(analysis_errors)}개 종목의 조회/분석 오류로 신규 진입을 보류했습니다. 시세·종목 조회와 최초 오류를 확인하세요."
                else:
                    message = f"증권 분석 주기 완료 · {str(result.get('execution_mode', '')).upper()} · 후보 {result.get('candidate_count', 0)}개 · 주문 {result.get('executed_orders', result.get('orders_executed', 0))}건. 주문 0건은 진입 조건·장 운영시간·가드레일을 확인하세요."
                issues = result.get("universe_issues") or []
                if issues:
                    message += " 목록 조회 상태: " + "; ".join(issues)
                emit_runtime_status(self, broker, (reason, tuple(issues)), message, level="WARNING" if analysis_errors or reason == "empty_stock_universe" or issues else "INFO")
            except Exception as exc:
                error_text = str(exc)
                reconnect_latched = "kiwoom_manual_reconnect_required" in error_text
                interval = 300 if reconnect_latched else 60
                with self._lock:
                    previous_error = self._errors.get(broker, "")
                    self._errors[broker] = error_text
                self.logger.exception("Stock runtime cycle failed: %s", broker)
                if reconnect_latched:
                    emit_runtime_status(
                        self,
                        broker,
                        "kiwoom_manual_reconnect_required",
                        "키움 자동 재로그인 차단 · 세션 상태가 불확실합니다. 중복 로그인 알림을 확인하고 증권 거래 실행을 중지한 뒤 키움 연결을 정리하고 다시 시작하세요.",
                        level="ERROR",
                    )
                else:
                    emit_runtime_status(self, broker, f"error:{type(exc).__name__}", f"증권 실행 주기 오류({type(exc).__name__}) · 연결·종목 조회·로그 상세를 확인하세요. 60초 후 재확인합니다.", level="ERROR")
                # The first latched state is actionable; repeating the same
                # notification every five minutes only obscures the original
                # transport failure and encourages duplicate login attempts.
                if not reconnect_latched or previous_error != error_text:
                    from trading.notifications import publish_runtime_failure
                    publish_runtime_failure(broker, exc)
            stop_event.wait(max(5, interval))
        emit_runtime_status(self, broker, "stopped", "증권 실행 워커 중지 · 계좌 전체 주문·포지션을 임의 청산하지 않습니다.")

    def _run_once(self, broker: str) -> tuple[dict[str, Any], int]:
        settings = self._settings_snapshot()
        cfg = dict(settings.get("stock_auto_trading", {}) or {})
        interval = int(cfg.get("interval_sec", 60) or 60)
        adapter = self._adapters.get(broker)
        if adapter is None:
            adapter = self.adapter_factory(broker, settings)
            if adapter is None:
                raise RuntimeError(f"stock_adapter_unavailable:{broker}")
            self._adapters[broker] = adapter
        if hasattr(adapter, "connect") and not bool(getattr(adapter, "is_connected", False)):
            if adapter.connect() is False:
                reason = str(getattr(adapter, "last_error", "") or getattr(adapter, "_last_connect_failure_reason", "") or "connection_rejected")
                raise RuntimeError(f"stock_connection_failed:{broker}:{reason}")

        allow_live, blocked_reason = self._live_permission(settings, broker, adapter)
        execution_mode = resolve_stock_execution_mode(
            settings,
            allow_live_order=allow_live,
            adapter_api_type=str(getattr(adapter, "api_type", "") or ""),
        )
        asset_mode = str(settings.get("stock_asset_mode", "all") or "all").lower()
        configured = list(cfg.get("symbols", []) or []) + list(cfg.get("watchlist", []) or [])
        strategy_pool = list(self.strategy_pool_provider() or [])
        strategy_signature = tuple(
            sorted(
                str(item.get("strategy_version_id") or item.get("version_id") or item.get("strategy_id") or "")
                for item in strategy_pool
                if isinstance(item, dict)
            )
        )
        universe_signature = (
            asset_mode,
            tuple(str(symbol or "").strip().upper() for symbol in configured),
            strategy_signature,
        )
        universe_ttl = max(30, int(cfg.get("universe_cache_ttl_sec", 300) or 300))
        cached_universe = self._universe_cache.get(broker)
        if (
            cached_universe
            and cached_universe[1] == universe_signature
            and time.monotonic() - cached_universe[0] < universe_ttl
        ):
            symbols = list(cached_universe[2])
        else:
            symbols = select_stock_universe(
                adapter,
                configured_symbols=configured,
                asset_mode=asset_mode,
                limit=8,
                custom_strategy_pool=strategy_pool,
            )
            if symbols:
                self._universe_cache[broker] = (
                    time.monotonic(),
                    universe_signature,
                    list(symbols),
                )
        advanced = dict(settings.get("advanced_trading_layers", {}) or {})
        override = dict((advanced.get("exchange_overrides", {}) or {}).get(str(broker).lower(), {}) or {})
        policy = deep_merge_policy(cfg, deep_merge_policy(advanced, override))
        policy.pop("exchange_overrides", None)
        # 네 증권사가 코인 거래소와 같은 최종 투자금 계약을 사용한다.
        # 기존 설정은 fixed_notional이 기본이므로 업데이트만으로 주문액이
        # 조용히 커지지 않는다.
        policy["position_sizing_policy"] = dict(
            settings.get("position_sizing_policy", {}) or {}
        )
        policy["max_positions"] = int(settings.get("max_positions", 3) or 3)
        service = self._services.get(broker)
        if service is None or getattr(service, "adapter", adapter) is not adapter:
            service = self.service_factory(
                adapter,
                broker_name=broker,
                recorder=self.recorder,
                paper_settings=settings,
            )
            self._services[broker] = service
        service.parallel_paper_observer = self.parallel_paper_observer
        service.notification_settings = dict(settings.get("notification_integrations", {}) or {})
        service.paper_validation_strategy_pool = list(self.paper_strategy_pool_provider() or [])
        result = service.run_auto_trade_cycle(
            symbols=symbols,
            quantity=float(cfg.get("quantity", 1.0) or 1.0),
            order_type=str(cfg.get("order_type", "MARKET") or "MARKET"),
            buy_threshold=float(cfg.get("buy_threshold", 70.0) or 70.0),
            sell_threshold=float(cfg.get("sell_threshold", 30.0) or 30.0),
            asset_mode=asset_mode,
            max_orders=max(1, int(cfg.get("max_orders_per_cycle", 1) or 1)),
            allow_live_order=allow_live,
            guardrails=normalize_stock_order_guardrails(settings.get("stock_order_guardrails", {})),
            auto_risk_policy=policy,
            exit_policy=cfg,
            custom_strategy_pool=strategy_pool,
            execution_mode_override=execution_mode.value,
        )
        if execution_mode == ExecutionMode.LEARNING and blocked_reason:
            result = {**result, "live_blocked_reason": blocked_reason}
        if not symbols:
            result = {**result, "reason": "empty_stock_universe"}
        return {**result, "candidate_count": len(symbols), "universe_issues": list(getattr(adapter, "last_universe_issues", []) or [])}, interval
