from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from trading.exchanges.adapters.kiwoom_bounded_backend import BoundedKiwoomMixin
from trading.exchanges.adapters.kiwoom_stock_adapter import KiwoomStockAdapter


class ParserBackend:
    def OnReceiveTrData(self, screen, rqname, trcode, record, next):
        self.tr_data = [{"현재가": "70000"}]
        self.received = True

    def OnEventConnect(self, code):
        pass


class Backend(BoundedKiwoomMixin, ParserBackend):
    pass


@pytest.fixture
def backend():
    client = Backend()
    ticks = [0.0]
    client.configure_deadlines(
        request_timeout=3, clock=lambda: ticks[0],
        pump=lambda: ticks.__setitem__(0, ticks[0] + 0.05),
    )
    client.ocx = SimpleNamespace(dynamicCall=Mock(return_value=0))
    client.SetInputValue = Mock()
    client.GetConnectState = Mock(return_value=0)
    client._load_tr_schema = lambda code: {"output": [{"price": ["현재가"]}]}
    return client


def request(client):
    return client.block_request("opt10001", 종목코드="005930", output="price", next=0)


def test_rejected_tr_returns_code_without_waiting(backend):
    backend.ocx.dynamicCall.return_value = -200
    backend._event_pump = Mock(side_effect=AssertionError("must not wait for rejected TR"))
    with pytest.raises(RuntimeError, match="request_rejected:opt10001:-200"):
        request(backend)
    assert backend._pending_tr is None
    assert backend.ocx.dynamicCall.call_count == 1
    with pytest.raises(RuntimeError, match="kiwoom_tr_cooldown"):
        request(backend)
    assert backend.ocx.dynamicCall.call_count == 1


def test_missing_reply_times_out_inside_host_and_next_request_can_succeed(backend):
    with pytest.raises(TimeoutError, match="kiwoom_tr_response_timeout:opt10001"):
        request(backend)
    assert backend._clock() < 2
    first_name = backend.ocx.dynamicCall.call_args.args[1]

    def pump():
        screen, name, code = backend._pending_tr
        backend.OnReceiveTrData(screen, first_name, code, "", "0")
        assert backend._tr_done is False
        backend.OnReceiveTrData(screen, name, code, "", "0")

    backend._event_pump = pump
    assert request(backend) == [{"현재가": "70000"}]
    assert backend._pending_tr is None


def test_parse_failure_is_not_an_infinite_wait(backend, monkeypatch):
    monkeypatch.setattr(ParserBackend, "OnReceiveTrData", lambda *args: None)
    backend._event_pump = lambda: backend.OnReceiveTrData(*backend._pending_tr, "", "0")
    with pytest.raises(RuntimeError, match="kiwoom_tr_parse_failed"):
        request(backend)


def test_invalid_output_fails_before_submission(backend):
    with pytest.raises(ValueError, match="kiwoom_tr_output_invalid"):
        backend.block_request("opw00018", output="wrong", next=0)
    backend.ocx.dynamicCall.assert_not_called()


def test_login_failure_callback_does_not_wait_for_success_forever(backend):
    backend._event_pump = lambda: backend.OnEventConnect(-100)
    with pytest.raises(RuntimeError, match="kiwoom_login_failed:-100"):
        backend.CommConnect()
    assert not backend.connected


def test_existing_session_does_not_open_another_login(backend):
    backend.GetConnectState.return_value = 1
    assert backend.CommConnect() == 0
    backend.ocx.dynamicCall.assert_not_called()


def test_actual_backend_list_account_contract_is_preserved():
    client = SimpleNamespace(
        CommConnect=lambda **kwargs: 0, GetConnectState=lambda: 1,
        GetLoginInfo=lambda key: ["1234567890", "2345678901"] if key == "ACCNO" else "user",
    )
    adapter = KiwoomStockAdapter("user", "login-secret", "", backend_client=client)
    assert adapter.connect()
    assert adapter.account_no == "1234567890"


def test_account_requests_use_distinct_outputs_and_never_login_password():
    client = SimpleNamespace(block_request=Mock(return_value=[]))
    adapter = KiwoomStockAdapter("user", "login-secret", "", "1234567890", backend_client=client)
    adapter.is_connected = True
    adapter.get_balance()
    adapter.get_positions()
    assert [c.kwargs["output"] for c in client.block_request.call_args_list] == [
        "계좌평가결과", "계좌평가잔고개별합산",
    ]
    assert all(c.kwargs["비밀번호"] == "" for c in client.block_request.call_args_list)


def test_etf_catalog_accepts_backend_list_without_per_symbol_tr():
    client = SimpleNamespace(
        GetCodeListByMarket=lambda market: ["069500", "122630"] if market == "8" else [],
        GetMasterCodeName=lambda code: code,
        block_request=Mock(side_effect=AssertionError("catalog must not query each ETF")),
    )
    adapter = KiwoomStockAdapter("user", "pw", "", backend_client=client)
    adapter.is_connected = True
    assert [row["code"] for row in adapter.get_etf_list()] == ["069500", "122630"]
    client.block_request.assert_not_called()


def test_read_timeout_response_does_not_destroy_host_or_relogin():
    from trading.exchanges.adapters.kiwoom_process_proxy import KiwoomProcessProxy
    proxy = KiwoomProcessProxy("user", "pw", "")
    proxy._ensure_process = Mock()
    proxy._connection = Mock()
    proxy._connection.poll.return_value = True
    proxy._connection.recv.side_effect = [
        (1, False, "TimeoutError: kiwoom_tr_response_timeout:opt10081"),
        (2, True, [{"date": "20260916", "close": 70000}]),
    ]
    proxy._shutdown_process = Mock()
    with pytest.raises(RuntimeError, match="kiwoom_tr_response_timeout"):
        proxy.get_daily_candles("005930")
    assert proxy.get_daily_candles("005930")[0]["close"] == 70000
    proxy._shutdown_process.assert_not_called()
    assert proxy._restart_blocked_reason == ""
    assert [call.args[0][1] for call in proxy._connection.send.call_args_list] == [
        "get_daily_candles", "get_daily_candles",
    ]


def test_bounded_login_timeout_still_blocks_automatic_relogin():
    from trading.exchanges.adapters.kiwoom_process_proxy import KiwoomProcessProxy
    proxy = KiwoomProcessProxy("user", "pw", "")
    proxy._ensure_process = Mock()
    proxy._connection = Mock()
    proxy._connection.poll.return_value = True
    proxy._connection.recv.return_value = (1, False, "TimeoutError: kiwoom_login_callback_timeout:90s")
    proxy._shutdown_process = Mock()
    with pytest.raises(RuntimeError, match="kiwoom_login_callback_timeout"):
        proxy.connect()
    assert proxy.connect() is False
    assert "최초 오류:" in proxy.last_error
    assert "kiwoom_login_callback_timeout" in proxy.last_error
    proxy._ensure_process.assert_called_once()


def test_read_requests_are_paced_on_same_event_thread(backend):
    submitted = []
    def submit(*args):
        submitted.append(backend._clock())
        backend.OnReceiveTrData(*backend._pending_tr, "", "0")
        return 0
    backend.ocx.dynamicCall.side_effect = submit
    for _ in range(8):
        request(backend)
    assert all(b - a >= 0.25 for a, b in zip(submitted, submitted[1:]))


def test_compound_reads_share_rpc_budget_without_waiting_for_parent_timeout(backend):
    backend.set_rpc_deadline(1.5)
    with pytest.raises(TimeoutError, match='kiwoom_tr_response_timeout'):
        request(backend)
    with pytest.raises(TimeoutError, match='kiwoom_tr_rpc_budget_exhausted'):
        request(backend)
    assert backend._clock() < 1.6
    with pytest.raises(TimeoutError, match='kiwoom_tr_rpc_budget_exhausted'):
        request(backend)
    assert backend.ocx.dynamicCall.call_count == 2
    backend.set_rpc_deadline(None)
    with pytest.raises(TimeoutError, match='kiwoom_tr_response_timeout'):
        request(backend)


def test_metadata_failure_is_not_reported_as_success_with_only_a_name():
    client = SimpleNamespace(
        GetMasterCodeName=lambda code: "example",
        block_request=Mock(side_effect=TimeoutError("kiwoom_tr_response_timeout:opt10001")),
    )
    adapter = KiwoomStockAdapter("user", "pw", "", backend_client=client)
    adapter.is_connected = True
    result = adapter.get_stock_info("005930")
    assert result['status'] == 'error'
    assert 'kiwoom_tr_response_timeout' in result['error']
    assert adapter.is_connected  # a read timeout is not a new login request


def test_metadata_and_quote_share_only_fresh_success(monkeypatch):
    import trading.exchanges.adapters.kiwoom_stock_adapter as module
    ticks = [1.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: ticks[0])
    client = SimpleNamespace(block_request=Mock(return_value=[{'현재가': '70000'}]))
    adapter = KiwoomStockAdapter("user", "pw", "", backend_client=client)
    adapter.is_connected = True
    assert adapter.get_stock_info("005930")['status'] == 'ok'
    assert adapter.get_realtime_price("005930")['current_price'] == 70000
    assert client.block_request.call_count == 1
    ticks[0] += 1.1
    client.block_request.side_effect = TimeoutError('read failed')
    assert adapter.get_realtime_price("005930")['status'] == 'error'
    assert adapter.get_stock_info("005930")['status'] == 'error'
    assert client.block_request.call_count == 3  # neither stale quote nor error cached


@pytest.mark.parametrize('method', ['get_stock_info', 'get_realtime_price'])
def test_empty_price_is_not_success(method):
    client = SimpleNamespace(block_request=Mock(return_value=[{'현재가': ''}]))
    adapter = KiwoomStockAdapter('user', 'pw', '', backend_client=client)
    adapter.is_connected = True
    assert getattr(adapter, method)('005930')['status'] == 'error'


@pytest.mark.parametrize('broker', ['kiwoom', 'kis', 'shinhan', 'mirae'])
def test_broker_read_failure_is_not_scored_as_normal_analysis(broker):
    from trading.stock_analysis_service import StockAnalysisService
    adapter = Mock()
    adapter.get_stock_info.return_value = {'status': 'error', 'error': 'kiwoom_tr_response_timeout:opt10001'}
    service = StockAnalysisService(adapter=adapter, broker_name=broker)
    result = service.analyze_symbol('005930')
    assert result['status'] == 'error'
    adapter.get_realtime_price.assert_not_called()


def test_inquiry_tr_contracts_match_output_records_not_request_names():
    calls = []
    def query(code, **kwargs):
        calls.append((code, kwargs))
        return [{'현재가': '70000', 'NAV': '69900'}]
    client = SimpleNamespace(block_request=query)
    adapter = KiwoomStockAdapter('user', 'login-secret', '', '1234567890', backend_client=client)
    adapter.is_connected = True
    adapter.get_open_orders()
    adapter.get_trade_history()
    adapter.get_etf_realtime_metrics('069500')
    by_code = dict(calls)
    assert by_code['opt10075']['output'] == '미체결'
    history = by_code['opw00007']
    assert history['비밀번호'] == ''
    assert history['비밀번호입력매체구분'] == '00'
    assert '주문일자' in history and '시작주문번호' in history
    assert not {'시작일', '종료일'} & history.keys()
    assert 'opt10079' not in by_code
    assert by_code['opt40006']['output'] == 'ETF시간대별추이'


def test_worker_preserves_analysis_failure_instead_of_normal_cycle_message(monkeypatch):
    from trading.stock_runtime_controller import StockRuntimeController
    controller = StockRuntimeController(settings_provider=lambda: {})
    controller._run_once = Mock(return_value=({'decisions': [
        {'reason': 'analysis_error', 'analysis_error': 'kiwoom_tr_response_timeout:opt10001'}
    ]}, 60))
    event = Mock()
    event.is_set.side_effect = [False, True]
    emit = Mock()
    monkeypatch.setattr('trading.runtime_observability.emit_runtime_status', emit)
    controller._worker('kiwoom', event)
    assert controller._errors['kiwoom'] == 'kiwoom_tr_response_timeout:opt10001'
    messages = [call.args[3] for call in emit.call_args_list]
    assert any('증권 분석 일부 실패' in message for message in messages)
    assert not any('증권 분석 주기 완료' in message for message in messages)


def test_manual_boundary_uses_release_source_not_mutable_manifest():
    from scripts.export_legacy_manual_sections import RELEASE_VERSION, _render_release_boundary
    text = _render_release_boundary('custom', 'guide')
    assert f'v{RELEASE_VERSION} Windows stable/latest 공개 제품' in text


def test_parent_fault_diagnostics_do_not_require_child_environment(tmp_path, monkeypatch):
    import json
    from trading.exchanges.adapters.kiwoom_host_diagnostics import record_stage
    monkeypatch.delenv('NOAHAI_KIWOOM_DIAGNOSTIC_LOG', raising=False)
    path = tmp_path / 'kiwoom_host_events.jsonl'
    record_stage('proxy_rpc_transport_fault', error_type='get_stock_info:TimeoutError', log_path=str(path))
    record = json.loads(path.read_text())
    assert record['stage'] == 'proxy_rpc_transport_fault'
    assert record['error_type'] == 'get_stock_info:TimeoutError'
