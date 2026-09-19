from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

from web_platform.application_services import ApplicationServices, DetachedRuntimeBridge


class _VisionClient:
    def __init__(self):
        self.paths: list[str] = []

    def is_ready(self):
        return True

    def vision_json(self, system_prompt, user_prompt, image_paths, **kwargs):
        self.paths = list(image_paths)
        assert Path(self.paths[0]).exists()
        return {
            "summary": "보이는 범위에서는 중립입니다.",
            "stance": "NEUTRAL",
            "confidence": 0.55,
            "visible_evidence": ["BTCUSDT", "1H"],
            "risks": ["가격축 일부가 흐림"],
            "scenarios": [],
            "plan": {"entry_zone": [], "stop": None, "targets": [], "note": "재캡처 권장"},
        }

    def get_last_usage(self):
        return {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}


def test_web_chart_analysis_uses_explicit_budgeted_vision_and_deletes_temp_image(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    client = _VisionClient()
    adapter = SimpleNamespace(model="vision-test", is_ready=lambda: True)
    router = SimpleNamespace(
        spec=SimpleNamespace(provider="openai", capabilities=SimpleNamespace(vision=True)),
        adapter=adapter,
        client_facade=lambda: client,
    )

    class LocalAnalyzer:
        def __init__(self, **kwargs): pass
        def _extract_text(self, path): return "BTCUSDT 1H", {}
        def _parse_features(self, text): return {"symbol": "BTCUSDT", "timeframe": "1H"}

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: {"ai_cost_control": {"max_daily_interactive_calls": 5}})
    monkeypatch.setattr(service_module, "ChartScreenshotAnalyzer", LocalAnalyzer)
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())
    services.interactive_ai.router_factory = lambda settings, workload: router
    services._audit = lambda *args, **kwargs: None
    png = b"\x89PNG\r\n\x1a\n" + b"safe-test-image"
    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")

    result = services.analyze_chart_image(
        file_name="chart.png",
        image_data_url=data_url,
        service="blockchain",
    )

    assert result["analysis"]["stance"] == "NEUTRAL"
    assert result["features"] == {"symbol": "BTCUSDT", "timeframe": "1H"}
    assert result["order_submitted"] is False
    assert result["usage"]["total_tokens"] == 150
    assert result["budget"]["token_usage"]["openai"]["total_tokens"] == 150
    assert client.paths and not Path(client.paths[0]).exists()


def test_web_chart_analysis_ui_is_real_upload_flow_not_asset_info_redirect():
    root = Path(__file__).resolve().parents[1]
    assistant = (root / "webui" / "src" / "components" / "AssistantWorkspace.tsx").read_text(encoding="utf-8")
    app = (root / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")
    gateway = (root / "web_platform" / "gateway.py").read_text(encoding="utf-8")

    assert 'accept="image/png,image/jpeg,image/webp"' in assistant
    assert "client.analyzeChart(" in assistant
    assert "외부 비전 AI로 분석" in assistant
    assert '"/api/v1/assistant/chart-analysis"' in gateway
    assert "onClick={openChartAnalysis}" in assistant
    assert "onClick={onChartAnalysis}>차트분석" not in assistant
    assert "setActiveFeature" in app  # navigation remains for non-chart personal-finance fallback only


def test_chart_analysis_rejects_known_text_only_model_before_provider_call(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    client = _VisionClient()
    adapter = SimpleNamespace(model="deepseek-v4-flash", is_ready=lambda: True)
    router = SimpleNamespace(
        spec=SimpleNamespace(provider="deepseek", capabilities=SimpleNamespace(vision=True)),
        adapter=adapter,
        client_facade=lambda: client,
    )
    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: {})
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())
    services.interactive_ai.router_factory = lambda settings, workload: router
    png = b"\x89PNG\r\n\x1a\n" + b"safe-test-image"
    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")

    import pytest

    with pytest.raises(ValueError, match="chart_vision_model_not_supported:deepseek:deepseek-v4-flash"):
        services.analyze_chart_image(file_name="chart.png", image_data_url=data_url, service="blockchain")
    assert client.paths == []
