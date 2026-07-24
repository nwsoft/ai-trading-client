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
