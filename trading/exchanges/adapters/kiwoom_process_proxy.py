"""Process-isolated Kiwoom OpenAPI+ adapter for the Web gateway.

QAx/COM objects must be created and called on the same process main thread.
FastAPI handlers and stock workers are background threads, so the Web runtime
uses this narrow RPC proxy instead of constructing QAx in an AnyIO worker.
"""

from __future__ import annotations

import multiprocessing
import struct
import sys
import threading
from typing import Any, Dict, List, Optional

from ..interfaces.stock_exchange import StockExchange


def _kiwoom_process_main(connection: Any, config: dict[str, Any], ready_handshake: bool = False) -> None:
    from .kiwoom_host_diagnostics import record_stage
    adapter = None
    try:
        record_stage("adapter_import")
        from .kiwoom_stock_adapter import KiwoomStockAdapter
        adapter = KiwoomStockAdapter(**config)
        record_stage("adapter_ready")
        from config.app_version import RELEASE_VERSION
        record_stage("host_version", error_type=RELEASE_VERSION)
        if ready_handshake:
            connection.send((0, True, "kiwoom_host_ready_v1"))
        while True:
            # Keep QAx callbacks alive while no HTTP/RPC call is pending.
            app = getattr(adapter, "_qt_app", None)
            if app is None:
                try:
                    from PyQt5.QtWidgets import QApplication
                    app = QApplication.instance()
                except ImportError:
                    pass
            if app is not None:
                app.processEvents()
            if not connection.poll(0.02):
                continue
            request = connection.recv()
            if request is None:
                break
            request_id, method_name, args, kwargs = request
            record_stage("rpc_" + method_name)
            set_deadline = getattr(getattr(adapter, "kiwoom", None), "set_rpc_deadline", None)
            if callable(set_deadline):
                # Compound reads (e.g. stats) share one outer RPC budget.
                # Leave time to serialize a failure instead of killing login.
                set_deadline(max(1, adapter.request_timeout - 2))
            try:
                result = getattr(adapter, method_name)(*args, **kwargs)
                if method_name == "connect" and result is False:
                    reason = getattr(adapter, "_last_connect_failure_reason", "") or "connection_rejected"
                    connection.send((request_id, False, str(reason)))
                    continue
                connection.send((request_id, True, result))
                record_stage("rpc_complete_" + method_name)
            except BaseException as exc:
                record_stage("rpc_failed", error_type=type(exc).__name__)
                connection.send((request_id, False, f"{type(exc).__name__}: {exc}"))
            finally:
                if callable(set_deadline):
                    set_deadline(None)
    except BaseException as exc:
        record_stage("host_failed", error_type=type(exc).__name__)
        if adapter is None and ready_handshake:
            try:
                connection.send((0, False, "kiwoom_host_initialization_failed:" + type(exc).__name__))
            except (OSError, EOFError):
                pass
        raise
    finally:
        disconnect = getattr(adapter, "disconnect", None)
        if callable(disconnect):
            try:
                disconnect()
            except Exception:
                pass
        connection.close()


class KiwoomProcessProxy(StockExchange):
    """Expose the stock-adapter contract while QAx lives in a child process."""

    def __init__(self, user_id: str, password: str, cert_password: str, account_no: str = "", **kwargs: Any):
        super().__init__("kiwoom")
        self.user_id = user_id
        self.password = password
        self.cert_password = cert_password
        self.account_no = account_no
        self.api_type = str(kwargs.get("api_type") or "openapi_plus")
        self.api_version = str(kwargs.get("api_version") or "pykiwoom")
        self.request_timeout = max(10, int(kwargs.get("request_timeout", 30) or 30))
        self._config = {
            "user_id": user_id, "password": password, "cert_password": cert_password,
            "account_no": account_no, "api_type": self.api_type, "api_version": self.api_version,
            "request_timeout": self.request_timeout,
            "account_password": str(kwargs.get("account_password") or ""),
        }
        self._context = multiprocessing.get_context("spawn")
        self._connection: Any = None
        self._process: Any = None
        self._request_id = 0
        self._rpc_lock = threading.RLock()
        self.last_error = ""
        self._order_outcome_unknown = False
        # A timed-out COM/RPC call leaves the Kiwoom login/session state
        # ambiguous.  Never let the 60-second stock worker turn that condition
        # into an automatic host/login loop.  A user stop/disconnect clears the
        # latch; the next explicit start may then create one fresh host.
        self._restart_blocked_reason = ""

    def _ensure_process(self) -> None:
        if self._restart_blocked_reason:
            raise RuntimeError(self._manual_reconnect_error())
        if self._process is not None and self._process.is_alive():
            return
        if sys.platform == "win32" and struct.calcsize("P") == 8:
            from .kiwoom_host_launcher import start_32bit_host
            self._process, self._connection = start_32bit_host(dict(self._config))
            return
        parent, child = self._context.Pipe()
        self._process = self._context.Process(
            target=_kiwoom_process_main,
            args=(child, dict(self._config)),
            name="noahai-kiwoom-openapi",
            daemon=True,
        )
        self._process.start()
        child.close()
        self._connection = parent

    def _call(self, method_name: str, *args: Any, timeout: Optional[int] = None, **kwargs: Any) -> Any:
        with self._rpc_lock:
            self._ensure_process()
            self._request_id += 1
            request_id = self._request_id
            wait_seconds = int(timeout or self.request_timeout)
            try:
                self._connection.send((request_id, method_name, args, kwargs))
                if not self._connection.poll(wait_seconds):
                    raise TimeoutError(f"kiwoom_rpc_timeout:{method_name}:{wait_seconds}s")
                response_id, ok, payload = self._connection.recv()
                if response_id != request_id:
                    raise OSError("kiwoom_rpc_response_mismatch")
            except (TimeoutError, EOFError, OSError) as exc:
                # Unknown outcomes are never retried. Dispose of the channel,
                # including late/mismatched replies and crashed COM workers.
                process = self._process
                exitcode = getattr(process, "exitcode", None)
                self.last_error = (
                    f"kiwoom_rpc_transport_error:{method_name}:exit={exitcode}:"
                    f"{type(exc).__name__}: 키움 전용 호스트 응답이 끊겼습니다. "
                    "키움 서버/인터넷 장애로 단정하지 않습니다. logs/kiwoom_host_events.jsonl을 확인하세요."
                )
                if method_name in {"place_order", "cancel_order"}:
                    self._order_outcome_unknown = True
                self._restart_blocked_reason = self.last_error
                try:
                    from .kiwoom_host_diagnostics import record_stage
                    from pathlib import Path
                    from path_utils import get_log_dir
                    record_stage(
                        "proxy_rpc_transport_fault",
                        error_type=f"{method_name}:{type(exc).__name__}",
                        log_path=str(Path(get_log_dir()) / "kiwoom_host_events.jsonl"),
                    )
                except Exception:
                    pass
                self._shutdown_process(clear_restart_block=False)
                if isinstance(exc, TimeoutError):
                    raise TimeoutError(self.last_error) from exc
                raise OSError(self.last_error) from exc
            if not ok:
                self.last_error = str(payload)
                if "kiwoom_login_callback_timeout" in self.last_error:
                    # A bounded login wait still has an unknown session outcome.
                    # Keep the same explicit-reconnect rule as transport faults.
                    self._restart_blocked_reason = self.last_error
                    self._shutdown_process(clear_restart_block=False)
                raise RuntimeError(f"kiwoom_rpc_failed:{method_name}:{payload}")
            self.last_error = ""
            return payload

    def connect(self) -> bool:
        if self._restart_blocked_reason:
            self.is_connected = False
            self.last_error = self._manual_reconnect_error()
            return False
        self.is_connected = bool(self._call("connect", timeout=max(120, self.request_timeout)))
        return self.is_connected

    def disconnect(self) -> bool:
        return self._shutdown_process(clear_restart_block=True)

    def _manual_reconnect_error(self) -> str:
        return (
            "kiwoom_manual_reconnect_required: 키움 세션 상태가 불확실하여 자동 재로그인을 "
            "차단했습니다. 중복 로그인 알림을 확인하고 NoahAI의 증권 거래 실행을 중지한 뒤 "
            "키움 연결 상태를 정리하고 다시 시작하세요. "
            f"최초 오류: {self._restart_blocked_reason}"
        )

    def _shutdown_process(self, *, clear_restart_block: bool) -> bool:
        # A balance/symbol request can still be waiting inside COM for up to
        # 120 seconds.  Safe shutdown must not wait behind that RPC lock and
        # then report runtime_still_alive.  Try graceful RPC shutdown briefly;
        # if the lock is busy, terminate only this proxy-owned child process.
        acquired = self._rpc_lock.acquire(timeout=1.0)
        try:
            process = self._process
            connection = self._connection
            try:
                if acquired and connection is not None:
                    connection.send(None)
            except (BrokenPipeError, EOFError, OSError):
                pass
            if process is not None:
                if acquired:
                    process.join(timeout=3)
                if process.is_alive():
                    # This is the proxy-owned COM child only.  Termination is
                    # the final fallback after graceful RPC shutdown timed out.
                    process.terminate()
                    process.join(timeout=3)
            alive = bool(process is not None and process.is_alive())
            if connection is not None:
                try:
                    connection.close()
                except (OSError, ValueError):
                    pass
            if not alive:
                self._connection = None
                self._process = None
            self.is_connected = False
            if clear_restart_block:
                self._restart_blocked_reason = ""
            return not alive
        finally:
            if acquired:
                self._rpc_lock.release()

    def get_live_readiness(self) -> tuple[bool, str]:
        if self._order_outcome_unknown:
            return False, "kiwoom_order_outcome_unknown: 주문내역과 포지션 대조가 필요합니다."
        if self._restart_blocked_reason:
            return False, self._manual_reconnect_error()
        return tuple(self._call("get_live_readiness"))  # type: ignore[return-value]

    def get_balance(self) -> Dict[str, Any]: return self._call("get_balance")
    def get_positions(self) -> List[Dict[str, Any]]: return self._call("get_positions")
    def get_stock_list(self, market: str = "ALL") -> List[Dict[str, Any]]: return self._call("get_stock_list", market)
    def get_etf_list(self) -> List[Dict[str, Any]]: return self._call("get_etf_list")
    def is_etf(self, symbol: str) -> bool: return bool(self._call("is_etf", symbol))
    def get_stock_info(self, symbol: str) -> Dict[str, Any]: return self._call("get_stock_info", symbol)
    def get_realtime_price(self, symbol: str) -> Dict[str, Any]: return self._call("get_realtime_price", symbol)
    def get_etf_realtime_metrics(self, symbol: str) -> Dict[str, Any]: return self._call("get_etf_realtime_metrics", symbol)
    def get_daily_candles(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]: return self._call("get_daily_candles", symbol, limit)
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]: return self._call("get_open_orders", symbol)
    def get_trade_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]: return self._call("get_trade_history", symbol, limit)
    def get_today_trades(self) -> List[Dict[str, Any]]: return self._call("get_today_trades")
    def get_trading_stats(self) -> Dict[str, Any]: return self._call("get_trading_stats")
    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool: return bool(self._call("cancel_order", order_id, symbol))

    def place_order(self, symbol: str, side: str, quantity: float,
                    price: Optional[float] = None, order_type: str = "MARKET") -> Dict[str, Any]:
        if self._order_outcome_unknown:
            raise RuntimeError("kiwoom_order_outcome_unknown: 이전 주문 결과를 대조하기 전 새 주문을 제출할 수 없습니다.")
        return self._call("place_order", symbol, side, quantity, price, order_type)
