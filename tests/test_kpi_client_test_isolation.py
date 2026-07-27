from api import kpi_client


def test_pytest_does_not_enqueue_or_send_production_kpi(monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_example.py::test_example (call)")
    monkeypatch.setattr(
        kpi_client,
        "_ensure_kpi_worker_started",
        lambda: (_ for _ in ()).throw(AssertionError("worker must not start")),
    )

    client = kpi_client.ServerKPIClient(async_mode=True)

    assert client.emit_event(
        event_type="trade_order_executed",
        category="trade",
        asset_class="stock",
        status="success",
        metadata={"execution_mode": "mock"},
    ) is True


def test_lifecycle_delivery_retries_server_error_and_confirms_success(monkeypatch):
    responses = iter((type("Response", (), {"status_code": 503})(), type("Response", (), {"status_code": 200})()))
    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return next(responses)

    monkeypatch.setattr(kpi_client.requests, "post", fake_post)
    monkeypatch.setattr(kpi_client.time, "sleep", lambda _seconds: None)

    delivered = kpi_client._deliver_kpi_item({
        "url": "https://daltrading.net/auth/kpi/event",
        "payload": {"event_type": "trade_position_closed"},
        "timeout": 1.5,
        "max_attempts": 3,
    })

    assert delivered is True
    assert len(calls) == 2


def test_lifecycle_delivery_does_not_retry_validation_error(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return type("Response", (), {"status_code": 400})()

    monkeypatch.setattr(kpi_client.requests, "post", fake_post)

    delivered = kpi_client._deliver_kpi_item({
        "url": "https://daltrading.net/auth/kpi/event",
        "payload": {"event_type": "trade_position_closed"},
        "timeout": 1.5,
        "max_attempts": 3,
    })

    assert delivered is False
    assert len(calls) == 1
