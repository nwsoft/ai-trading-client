from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from trading.insurance_workspace import InsuranceWorkspace
from web_platform.gateway import create_gateway_app

TOKEN = "synthetic-gateway-token-insurance-3922"
HEADERS = {"Authorization": "Bearer " + TOKEN, "X-NoahAI-Intent": "confirmed"}


@pytest.fixture
def gateway(tmp_path):
    store = InsuranceWorkspace(tmp_path, "synthetic-gateway-user")
    services = SimpleNamespace(insurance_workspace=lambda: store, runtime_snapshot=lambda: {})
    with TestClient(create_gateway_app(token=TOKEN, application_services=services)) as client:
        yield client, store
    store.lock()


def test_auth_intent_origin_no_private_validation_echo(gateway):
    client, _ = gateway
    route = "/api/v1/life-finance/insurance"
    assert client.get(route).status_code == 401
    assert client.post(route, headers={"Authorization": "Bearer " + TOKEN}, json={}).status_code == 428
    assert client.get(route, headers={**HEADERS, "Origin": "https://external.invalid"}).status_code == 403
    r = client.post(route, headers=HEADERS, json={"action": "unlock", "payload": {"password": "SENSITIVE"}})
    assert r.status_code == 400
    assert "SENSITIVE" not in r.text
    assert "insurance_password_length" in r.text
    r = client.post(route, headers=HEADERS, content='{"action": "unlock", "password": "PRIVATE"')
    assert r.status_code == 400 and "PRIVATE" not in r.text


def test_gateway_lifecycle_no_cache_and_backup(gateway):
    client, store = gateway
    route = "/api/v1/life-finance/insurance"
    r = client.post(route, headers=HEADERS, json={"action": "unlock", "payload": {"password": "synthetic-password-only"}})
    assert r.status_code == 200 and r.json()["state"] == "unlocked"
    assert r.headers["cache-control"] == "no-store"
    assert client.get(route, headers=HEADERS).headers["cache-control"] == "no-store"
    r = client.post(route, headers=HEADERS, json={"action": "backup", "payload": {}})
    assert r.json()["encrypted"] is True
    client.post(route, headers=HEADERS, json={"action": "lock", "payload": {}})
    assert store.snapshot()["state"] == "locked"


def test_insurance_guide_never_calls_external_even_in_deep_mode(tmp_path, monkeypatch):
    import web_platform.application_services as module
    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(module, "load_settings", lambda **kw: deepcopy({"paper_trading": True}))
    services = module.ApplicationServices(account="qa-insurance")
    monkeypatch.setattr(services.interactive_ai, "ask", lambda **kw: pytest.fail("external call"))
    for scope in ("private", "public_general"):
        for locale in ("ko", "en"):
            result = services.ask_assistant(question="보험 문서 비교 방법?", service="personal_finance", explanation_level="advanced", mode="deep_analysis", data_scope=scope, output_locale=locale)
            assert result["provider_called"] is False
            assert result["guide_topic"] == "insurance_workspace"
            for question in ("금융상품 비교가 어려워요", "원리금균등이 뭐야?", "예금과 적금은 왜 다른가요?", "중도상환 비용을 알려줘"):
                result = services.ask_assistant(question=question, service="personal_finance", explanation_level="beginner", mode="deep_analysis", data_scope=scope, output_locale=locale)
                assert result["provider_called"] is False
                assert result["guide_topic"] == "finance_products"
                assert result["source"] == "versioned_local_product_knowledge"
    assert not (tmp_path / "insurance_private").exists()


def test_authentication_switch_locks_and_discards_old_vault(tmp_path, monkeypatch):
    import web_platform.application_services as module
    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(module, "load_settings", lambda **kw: {})
    services = module.ApplicationServices(account="old-user")
    old = services.insurance_workspace()
    old.unlock("synthetic-password-only")
    # Stop after the account transition to avoid touching live auth/runtime.
    monkeypatch.setattr(module.requests, "post", lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: {"access_token": "synthetic", "id": "new-user"}))
    monkeypatch.setattr(module, "AccountQueryService", lambda: (_ for _ in ()).throw(RuntimeError("qa-stop-after-switch")))
    with pytest.raises(RuntimeError, match="qa-stop-after-switch"):
        services.authenticate(username="new-user", password="not-real")
    assert old.snapshot()["state"] == "locked"
    new = services.insurance_workspace()
    assert new is not old and new.snapshot()["state"] == "locked"
    assert new.owner != old.owner
