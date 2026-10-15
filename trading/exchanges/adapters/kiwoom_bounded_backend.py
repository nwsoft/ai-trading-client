"""Bound pykiwoom event waits on the OCX owner thread.

pykiwoom 0.1.6's synchronous helpers discard the TR submission return code
and wait indefinitely. Keep its parser, but correlate callbacks and bound the
wait inside the host, before the parent RPC deadline can destroy the session.
"""
from __future__ import annotations

import time
import re

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
        self._tr_timeouts = {}
        self._consecutive_read_timeouts = 0
        self._read_retry_at = 0.0

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

    def OnReceiveMsg(self, screen, rqname, trcode, msg):
        pending = getattr(self, '_pending_tr', None)
        if pending != (str(screen), str(rqname), str(trcode).lower()):
            return
        # Messages can contain account details. Record only a bounded provider
        # code, never text; known negative TR errors terminate this read early.
        match = re.search(r'\[(-?[A-Za-z0-9]{1,16})\]', str(msg))
        candidate = match.group(1) if match else ''
        known = {'-200','-201','-202','-100','-101','-102','-106','-301','-302'}
        # Unknown bracketed values may be account numbers, not provider codes.
        code = candidate if candidate in known else 'unclassified'
        record_stage('tr_server_message', error_type=f'{trcode}:{code}')
        if code in known:
            self._tr_error = f'kiwoom_tr_server_rejected:{trcode}:{code}'
            self._tr_done = True
            if code == '-200':
                self._tr_retry_at = self._clock() + 60

    def OnReceiveTrData(self, screen, rqname, trcode, record, next, *extra):
        pending = getattr(self, "_pending_tr", None)
        if pending is None or (str(screen), str(rqname), str(trcode).lower()) != pending:
            # Late replies and order callbacks must not complete a later read.
            # No rqname/screen/record or payload is written to diagnostics.
            if str(trcode).lower().startswith(('opt', 'opw')):
                record_stage('tr_callback_ignored', error_type=str(trcode).lower()[:16])
            return
        record_stage("tr_callback", error_type=str(trcode).lower())
        try:
            # OCX signature after prev_next: data_length, error_code, message,
            # supplementary_message. Do not discard explicit server rejection.
            code = str(extra[1]).strip() if len(extra) >= 2 else ''
            if code and code != '0':
                self._tr_error = 'kiwoom_tr_callback_rejected:' + str(trcode).lower()
                return
            super().OnReceiveTrData(screen, rqname, trcode, record, next)
            if not self.received:
                self._tr_error = "kiwoom_tr_parse_failed:" + str(trcode).lower()
        except Exception as exc:
            self._tr_error = f"kiwoom_tr_parse_failed:{trcode}:{type(exc).__name__}"
        finally:
            self._tr_done = True

    def block_request(self, trcode, **kwargs):
        self._check_rpc_budget()
        if int(self.GetConnectState()) != 1:
            self.connected = False
            record_stage('tr_connection_lost')
            raise RuntimeError('kiwoom_tr_not_connected')
        if self._clock() < self._read_retry_at:
            raise RuntimeError('kiwoom_tr_cooldown:session_read_stalled')
        if self._pending_tr is not None:
            raise RuntimeError("kiwoom_tr_reentrant_request")
        if self._clock() < self._tr_retry_at:
            # Do not sleep through the outer RPC deadline during overload.
            raise RuntimeError("kiwoom_tr_cooldown:query_overload")
        trcode = str(trcode).lower()
        failures, retry_at = self._tr_timeouts.get(trcode, (0, 0.0))
        if self._clock() < retry_at:
            raise RuntimeError(f"kiwoom_tr_cooldown:response_timeout:{trcode}")
        schema = self._load_tr_schema(trcode)
        output = kwargs.get("output")
        if not any(output in entry for entry in schema.get("output", [])):
            raise ValueError(f"kiwoom_tr_output_invalid:{trcode}")
        while self._clock() < self._next_tr_at:
            self._check_rpc_budget()
            self._event_pump()
        self._check_rpc_budget()
        if self._rpc_deadline is not None and self._rpc_deadline-self._clock() < self._tr_timeout:
            # Do not submit a read that cannot finish within its allocated wait.
            raise TimeoutError('kiwoom_tr_rpc_budget_insufficient')
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
        submitted_at = self._clock()
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
                if int(self.GetConnectState()) != 1:
                    self.connected = False
                    raise RuntimeError('kiwoom_tr_connection_lost')
            if self._tr_error:
                raise RuntimeError(self._tr_error)
            record_stage("tr_complete", error_type=trcode)
            self._tr_timeouts.pop(trcode, None)
            self._consecutive_read_timeouts = 0
            return self.tr_data
        except Exception as exc:
            if isinstance(exc, TimeoutError):
                # A missing callback is not a reason to repeat the same TR for
                # every candidate. Three consecutive read timeouts pause reads
                # for 30s; SendOrder is not retried, login is not destroyed.
                self._consecutive_read_timeouts += 1
                if self._consecutive_read_timeouts >= 3:
                    self._read_retry_at = self._clock() + 30
                failures += 1
                self._tr_timeouts[trcode] = (
                    failures, self._clock() + 30.0 if failures >= 3 else 0.0,
                )
            record_stage("tr_failed", error_type=f"{trcode}:{type(exc).__name__}")
            try:
                state = int(self.GetConnectState())
            except Exception:
                state = -1
            elapsed_ms = max(0, int((self._clock()-submitted_at)*1000))
            record_stage('tr_failure_context', error_type=f'{trcode}:connected={state}:elapsed_ms={elapsed_ms}')
            raise
        finally:
            self._pending_tr = None


def create_bounded_backend(backend_type, *, request_timeout):
    class BoundedKiwoom(BoundedKiwoomMixin, backend_type):
        pass

    backend = BoundedKiwoom()
    backend.configure_deadlines(request_timeout=request_timeout)
    return backend
