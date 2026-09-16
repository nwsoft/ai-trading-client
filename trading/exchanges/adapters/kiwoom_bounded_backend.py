"""Bound pykiwoom event waits on the OCX owner thread.

pykiwoom 0.1.6's synchronous helpers discard the TR submission return code
and wait indefinitely. Keep its parser, but correlate callbacks and bound the
wait inside the host, before the parent RPC deadline can destroy the session.
"""
from __future__ import annotations

import time

from .kiwoom_host_diagnostics import record_stage


class BoundedKiwoomMixin:
    def configure_deadlines(self, *, request_timeout=30, pump=None, clock=None):
        self._tr_timeout = min(10.0, max(1.0, float(request_timeout) / 3))
        self._event_pump = pump or self._pump_windows_events
        self._clock = clock or time.monotonic
        self._pending_tr = None
        self._tr_serial = 0
        self._next_tr_at = 0.0
        self._tr_retry_at = 0.0
        self._login_result = None
        self._rpc_deadline = None

    def set_rpc_deadline(self, seconds):
        self._rpc_deadline = None if seconds is None else self._clock() + max(0, seconds)

    def _check_rpc_budget(self):
        if self._rpc_deadline is not None and self._clock() >= self._rpc_deadline:
            raise TimeoutError("kiwoom_tr_rpc_budget_exhausted")

    @staticmethod
    def _pump_windows_events():
        import pythoncom
        from PyQt5.QtWidgets import QApplication
        pythoncom.PumpWaitingMessages()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        time.sleep(0.01)

    @staticmethod
    def _load_tr_schema(trcode):
        from pykiwoom import parser
        return parser.parse_dat(trcode, parser.read_enc(trcode))

    def OnEventConnect(self, err_code):
        self._login_result = int(err_code)
        self.connected = int(err_code) == 0
        super().OnEventConnect(err_code)

    def CommConnect(self, block=True):
        if self.GetConnectState() == 1:
            self.connected = True
            return 0
        self._login_result = None
        self.connected = False
        result = self.ocx.dynamicCall("CommConnect()")
        if result is not None and int(result) < 0:
            raise RuntimeError(f"kiwoom_login_rejected:{int(result)}")
        if not block:
            return result
        deadline = self._clock() + 90.0
        while self._login_result is None:
            if self._clock() >= deadline:
                raise TimeoutError("kiwoom_login_callback_timeout:90s")
            self._event_pump()
        if self._login_result != 0:
            raise RuntimeError(f"kiwoom_login_failed:{self._login_result}")
        return 0

    def OnReceiveTrData(self, screen, rqname, trcode, record, next, *extra):
        pending = getattr(self, "_pending_tr", None)
        if pending is None or (str(screen), str(rqname), str(trcode).lower()) != pending:
            # Late replies and order callbacks must not complete a later read.
            return
        record_stage("tr_callback", error_type=str(trcode).lower())
        try:
            super().OnReceiveTrData(screen, rqname, trcode, record, next)
            if not self.received:
                self._tr_error = "kiwoom_tr_parse_failed:" + str(trcode).lower()
        except Exception as exc:
            self._tr_error = f"kiwoom_tr_parse_failed:{trcode}:{type(exc).__name__}"
        finally:
            self._tr_done = True

    def block_request(self, trcode, **kwargs):
        self._check_rpc_budget()
        if self._pending_tr is not None:
            raise RuntimeError("kiwoom_tr_reentrant_request")
        if self._clock() < self._tr_retry_at:
            # Do not sleep through the outer RPC deadline during overload.
            raise RuntimeError("kiwoom_tr_cooldown:query_overload")
        trcode = str(trcode).lower()
        schema = self._load_tr_schema(trcode)
        output = kwargs.get("output")
        if not any(output in entry for entry in schema.get("output", [])):
            raise ValueError(f"kiwoom_tr_output_invalid:{trcode}")
        while self._clock() < self._next_tr_at:
            self._check_rpc_budget()
            self._event_pump()
        self._check_rpc_budget()
        self._tr_serial += 1
        rqname = f"noah{self._tr_serial}"
        screen = "0101"
        self.tr_items, self.tr_record = schema, output
        self.tr_data, self.received, self.tr_remained = None, False, False
        self._tr_error, self._tr_done = "", False
        for key, value in kwargs.items():
            if key not in {"output", "next"}:
                self.SetInputValue(key, value)
        self._pending_tr = (screen, rqname, trcode)
        record_stage("tr_submit", error_type=trcode)
        try:
            # Call the OCX directly: the upstream wrapper discards this result.
            result = self.ocx.dynamicCall(
                "CommRqData(QString, QString, int, QString)",
                rqname, trcode, int(kwargs.get("next", 0)), screen,
            )
            self._next_tr_at = self._clock() + 0.25
            if result is None or int(result) != 0:
                code = "missing" if result is None else str(int(result))
                record_stage("tr_rejected", error_type=f"{trcode}:{code}")
                if code == "-200":
                    self._tr_retry_at = self._clock() + 60.0
                raise RuntimeError(f"kiwoom_tr_request_rejected:{trcode}:{code}")
            deadline = self._clock() + self._tr_timeout
            while not self._tr_done:
                self._check_rpc_budget()
                if self._clock() >= deadline:
                    raise TimeoutError(f"kiwoom_tr_response_timeout:{trcode}")
                self._event_pump()
            if self._tr_error:
                raise RuntimeError(self._tr_error)
            record_stage("tr_complete", error_type=trcode)
            return self.tr_data
        except Exception as exc:
            record_stage("tr_failed", error_type=f"{trcode}:{type(exc).__name__}")
            raise
        finally:
            self._pending_tr = None


def create_bounded_backend(backend_type, *, request_timeout):
    class BoundedKiwoom(BoundedKiwoomMixin, backend_type):
        pass

    backend = BoundedKiwoom()
    backend.configure_deadlines(request_timeout=request_timeout)
    return backend
