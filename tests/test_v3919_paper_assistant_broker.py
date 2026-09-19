import json
from unittest.mock import patch

from strategy_customizer import StrategyCustomizer
from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.exchanges.adapters.kiwoom_process_proxy import KiwoomProcessProxy
from trading.exchanges.exchange_factory import ExchangeFactory
from ui.ai_custom_guidance import AI_CUSTOM_SAFE_STEPS


def _rules():
    return {
        "entry": "RSI < 30",
        "exit": "RSI > 55",
        "stop_loss": 1.0,
        "take_profit": 2.0,
        "position_size": 0.05,
        "market_conditions": ["trend", "range"],
    }


def test_user_safe_flow_places_paper_before_final_apply():
    paper_index = next(index for index, step in enumerate(AI_CUSTOM_SAFE_STEPS) if "PAPER 전진검증" in step)
    apply_index = next(index for index, step in enumerate(AI_CUSTOM_SAFE_STEPS) if "최종 적용" in step)
    assert paper_index < apply_index


def test_historical_validation_can_enter_paper_only_runtime_pool(tmp_path):
    storage = tmp_path / "custom_strategies" / "binance_private.json"
    pipeline = CustomStrategyPipeline(storage_path=str(storage), min_paper_trades=3)
    item = pipeline.submit(name="paper candidate", rules=_rules())
    key, version_id = item["strategy_key"], item["version_id"]
    pipeline.approve(key, version_id, approved_by="tester")
    pipeline.record_execution_validation(
        key, version_id, decisions=3, mode="historical_replay",
        metrics={"net_pnl": 1.2},
    )

    observing = pipeline.start_paper_observation(key, version_id)
    assert observing["status"] == "paper_observing"
    assert pipeline.paper_versions == {key: version_id}
    assert pipeline.active_versions == {}

    customizer = StrategyCustomizer(None, None, None, None, storage_path=str(storage))
    assert customizer.get_active_strategy_pool() == []
    paper_pool = customizer.get_paper_strategy_pool()
    assert len(paper_pool) == 1
    assert paper_pool[0]["strategy_key"] == key
    assert paper_pool[0]["version_id"] == version_id
    assert paper_pool[0]["operation_mode"] == "paper_validation"


def test_approved_strategy_without_historical_window_can_gather_paper_evidence(tmp_path):
    pipeline = CustomStrategyPipeline(storage_path=str(tmp_path / "strategy.json"), min_paper_trades=3)
    item = pipeline.submit(name="new forward only", rules=_rules())
    key, version_id = item["strategy_key"], item["version_id"]
    pipeline.approve(key, version_id, approved_by="tester")

    observing = pipeline.start_paper_observation(key, version_id)
    assert observing["status"] == "paper_observing"
    assert observing["paper_observation_previous_status"] == "approved"
    stopped = pipeline.stop_paper_observation(key, version_id)
    assert stopped["status"] == "paper_paused"


def test_forward_paper_progress_is_not_mislabeled_as_failure(tmp_path):
    pipeline = CustomStrategyPipeline(storage_path=str(tmp_path / "strategy.json"), min_paper_trades=3)
    item = pipeline.submit(name="forward", rules=_rules())
    key, version_id = item["strategy_key"], item["version_id"]
    pipeline.approve(key, version_id, approved_by="tester")
    pipeline.record_execution_validation(key, version_id, decisions=3, mode="historical_replay")
    pipeline.start_paper_observation(key, version_id)

    progress = pipeline.record_paper_validation(
        key, version_id, trades=1,
        metrics={"require_forward_days": True, "observation_days": 1.0},
    )
    assert progress["status"] == "paper_observing"
    assert progress["paper_validation"]["passed"] is False
    complete = pipeline.record_paper_validation(
        key, version_id, trades=3,
        metrics={"require_forward_days": True, "observation_days": 7.0},
    )
    assert complete["status"] == "paper_validated"
    assert key not in pipeline.paper_versions


def test_default_paper_close_is_visible_without_custom_strategy(tmp_path, monkeypatch):
    import trading.paper_strategy_ledger as ledger

    monkeypatch.setattr(ledger, "get_app_data_dir", lambda: str(tmp_path))
    row = ledger.record_paper_strategy_outcome(
        scope="binance", exchange="binance", symbol="BTCUSDT",
        strategy_key="", version_id="", opened_at="2026-08-24T00:00:00+00:00",
        closed_at="2026-08-24T01:00:00+00:00", net_pnl=1.25,
    )
    assert row["strategy_key"] == ""
    assert ledger.read_paper_strategy_outcomes()[0]["net_pnl"] == 1.25


def test_web_stock_controller_marker_forces_kiwoom_process_proxy_without_env(monkeypatch):
    monkeypatch.delenv("NOAHAI_ENABLE_WEB_RUNTIME", raising=False)
    settings = {
        "_noahai_web_runtime": True,
        "stock_broker_configs": {
            "kiwoom": {
                "api_type": "openapi_plus", "api_version": "pykiwoom",
                "id": "user", "password": "pw", "cert_password": "cert",
                "account_no": "12345678",
            }
        },
    }
    with patch("trading.exchanges.exchange_factory.platform.system", return_value="Windows"):
        adapter = ExchangeFactory.create_stock_exchange("kiwoom", settings)
    assert isinstance(adapter, KiwoomProcessProxy)


def test_general_assistant_answers_position_from_runtime_evidence(tmp_path, monkeypatch):
    import web_platform.application_services as module

    class Runtime:
        def snapshot(self):
            return {
                "selected_source": "binance", "selected_sources": {"blockchain": "binance"},
                "running_sources": ["binance"], "paper_trading": True,
            }

        def assistant_context_snapshot(self, **_kwargs):
            return {
                "source": "binance", "execution_mode": "PAPER", "running": True,
                "engine_attached": True,
                "managed_positions": [{
                    "symbol": "BTCUSDT", "side": "LONG", "entry_price": 100,
                    "current_price": 105, "tp_price": 110, "sl_price": 95,
                    "custom_strategy_name": "추세 전략", "custom_strategy_version_id": "v-test",
                }],
                "active_custom_strategies": [], "cycle_execution_metrics": [],
            }

    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(module, "load_settings", lambda **kwargs: {})
    services = module.ApplicationServices(account="tester", runtime_bridge=Runtime())
    monkeypatch.setattr(services.queries, "learning_snapshot", lambda **kwargs: {
        "status": "ok", "pagination": {"total_count": 1},
        "records": [{"symbol": "BTCUSDT", "signal": "HOLD", "trend": "LONG_TREND", "reason": "추세 유지"}],
    })

    result = services.ask_assistant(
        question="지금 포지션을 계속 들고 있는 이유?",
        service="blockchain", explanation_level="standard", mode="guide",
    )
    assert result["provider_called"] is False
    assert "BTCUSDT" in result["answer"]
    assert "TP 110" in result["answer"]
    assert "SL 95" in result["answer"]
    assert "LONG_TREND" in result["answer"]
    assert "현재가가 기록된 TP·SL 청산선에 아직 도달하지 않음" in result["answer"]
    assert "AI 커스텀 엔진 ON" not in result["answer"]


def test_deep_assistant_receives_authoritative_position_evidence(tmp_path, monkeypatch):
    import web_platform.application_services as module

    class Runtime:
        def snapshot(self):
            return {
                "selected_source": "binance", "selected_sources": {"blockchain": "binance"},
                "running_sources": ["binance"], "paper_trading": True,
            }

        def assistant_context_snapshot(self, **_kwargs):
            return {
                "source": "binance", "execution_mode": "PAPER", "running": True,
                "engine_attached": True,
                "managed_positions": [{"symbol": "ETHUSDT", "tp_price": 2200, "sl_price": 1800}],
                "active_custom_strategies": [{"strategy_key": "trend", "version_id": "v1"}],
                "cycle_execution_metrics": [],
            }

    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(module, "load_settings", lambda **kwargs: {})
    services = module.ApplicationServices(account="tester", runtime_bridge=Runtime())
    monkeypatch.setattr(services.queries, "learning_snapshot", lambda **kwargs: {
        "status": "ok", "records": [{"symbol": "ETHUSDT", "signal": "LONG", "reason": "EMA 정렬"}],
    })
    captured = {}
    services.interactive_ai.ask = lambda **kwargs: captured.update(kwargs) or {
        "answer": "근거 답변", "provider_called": True, "provider": "openai", "model": "test",
    }
    services.workspace_snapshot = lambda **kwargs: {"screen": "surface"}

    services.ask_assistant(
        question="ETH 포지션 유지 근거를 심층 분석해줘",
        service="blockchain", explanation_level="advanced", mode="deep_analysis",
    )
    context = json.loads(captured["context"])
    evidence = context["authoritative_operational_evidence"]
    assert evidence["execution"]["managed_positions"][0]["symbol"] == "ETHUSDT"
    assert evidence["latest_signals"][0]["reason"] == "EMA 정렬"
    assert "managed_positions" in captured["system_prompt"]


def test_general_assistant_quick_topics_do_not_collapse_to_one_status_answer(tmp_path, monkeypatch):
    import web_platform.application_services as module

    class Runtime:
        def snapshot(self):
            return {
                "selected_source": "binance", "selected_sources": {"blockchain": "binance"},
                "running_sources": ["binance"], "paper_trading": True,
            }

        def assistant_context_snapshot(self, **_kwargs):
            return {
                "source": "binance", "execution_mode": "PAPER", "running": True,
                "engine_attached": True, "managed_positions": [],
                "active_custom_strategies": [{"strategy_key": "trend", "version_id": "v1"}],
                "cycle_execution_metrics": [{
                    "source": "binance", "candidate_count": 8, "signal_count": 2,
                    "order_count": 1, "blocked_count": 5,
                }],
            }

    settings = {
        "paper_trading": True,
        "position_mode": "multi",
        "max_positions": 3,
        "selected_exchange": "binance",
        "enabled_exchanges": ["binance", "bybit"],
        "trade_enabled_exchanges": ["binance"],
        "advanced_trading_layers": {
            "strategy_engine": {"enabled": True, "high_vol_action": "block"},
        },
    }
    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(module, "load_settings", lambda **kwargs: settings)
    services = module.ApplicationServices(account="tester", runtime_bridge=Runtime())
    monkeypatch.setattr(services.queries, "learning_snapshot", lambda **kwargs: {
        "status": "ok", "pagination": {"total_count": 1},
        "records": [{
            "symbol": "BTCUSDT", "signal": "HOLD", "trend": "RANGE",
            "reason": "합의 점수 미달",
        }],
    })

    high_vol = services.ask_assistant(
        question="high vol 차단이 지금 켜져 있는지와 설정 위치를 알려줘",
        service="blockchain", explanation_level="standard", mode="guide",
    )
    custom = services.ask_assistant(
        question="AI 커스텀 전략을 실제 적용하기까지 순서를 알려줘",
        service="blockchain", explanation_level="standard", mode="guide",
    )
    market = services.ask_assistant(
        question="현재 암호화폐 시장 상황과 근거를 알려줘",
        service="blockchain", explanation_level="standard", mode="guide",
    )
    performance = services.ask_assistant(
        question="최근 거래 성과와 통계를 요약해줘",
        service="blockchain", explanation_level="standard", mode="guide",
    )

    assert all(result["provider_called"] is False for result in (high_vol, custom, market, performance))
    assert "항상 차단(block)" in high_vol["answer"]
    assert "AI 커스텀" in custom["answer"]
    assert "BTCUSDT" in market["answer"] and "합의 점수 미달" in market["answer"]
    assert "후보 8" in performance["answer"] and "차단 5" in performance["answer"]
    assert len({result["answer"] for result in (high_vol, custom, market, performance)}) == 4


def test_general_assistant_trend_question_uses_signal_and_named_source(tmp_path, monkeypatch):
    import web_platform.application_services as module

    captured = {}

    class Runtime:
        def snapshot(self):
            return {
                "selected_source": "binance",
                "selected_sources": {"blockchain": "binance"},
                "running_sources": ["bybit"],
                "paper_trading": True,
            }

        def assistant_context_snapshot(self, **kwargs):
            captured.update(kwargs)
            return {
                "source": kwargs["source"], "execution_mode": "PAPER", "running": True,
                "engine_attached": True, "managed_positions": [],
                "active_custom_strategies": [], "cycle_execution_metrics": [],
            }

    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(module, "load_settings", lambda **kwargs: {})
    services = module.ApplicationServices(account="tester", runtime_bridge=Runtime())
    monkeypatch.setattr(services.queries, "learning_snapshot", lambda **kwargs: {
        "status": "ok",
        "records": [{"symbol": "ETHUSDT", "signal": "LONG", "trend": "LONG_TREND", "reason": "EMA 정렬"}],
    })

    result = services.ask_assistant(
        question="바이비트 지금 추세가 뭐야?",
        service="blockchain", explanation_level="standard", mode="guide",
    )

    assert captured["source"] == "bybit"
    assert "BYBIT" in result["answer"]
    assert "LONG_TREND" in result["answer"]
    assert "관리 포지션은 실행 메모리에서 확인되지 않습니다" not in result["answer"]
