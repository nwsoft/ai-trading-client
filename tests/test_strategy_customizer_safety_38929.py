import os
import stat

from strategy_customizer import StrategyCustomizer


class _Trader:
    def __init__(self):
        self.calls = []

    def update_settings(self, settings):
        self.calls.append(dict(settings))


def _rules():
    return {
        "entry": {"condition": "RSI below 30"},
        "exit": {"condition": "RSI above 60"},
        "stop_loss": 1.0,
        "take_profit": 2.0,
        "position_size": 0.05,
        "market_conditions": ["sideways"],
    }


def test_user_strategy_cannot_bypass_approval_and_paper_validation(tmp_path):
    trader = _Trader()
    customizer = StrategyCustomizer(
        None,
        trader,
        None,
        None,
        storage_path=str(tmp_path / "private.json"),
        min_paper_trades=2,
    )
    strategy_id = customizer.create_custom_strategy({
        "name": "safe custom",
        "rules": _rules(),
        "base_params": {"leverage": 1, "tp_percent": 2.0, "sl_percent": 1.0},
    })
    strategy = customizer.user_strategies[strategy_id]

    assert customizer.apply_strategy(strategy_id) is False
    assert trader.calls == []

    key = strategy["pipeline_strategy_key"]
    version_id = strategy["pipeline_version_id"]
    customizer.approve_custom_strategy(key, version_id, approved_by="user")
    customizer.record_paper_validation(key, version_id, trades=2)
    customizer.activate_custom_strategy(key, version_id, live_confirmation=True)

    # 사용자 전략은 후보별 설정으로만 전달하며 글로벌 기본값을 바꾸지 않는다.
    assert trader.calls == []
    pool = customizer.get_active_strategy_pool()
    assert len(pool) == 1
    assert pool[0]["engine_settings"]["leverage"] == 1
    assert pool[0]["engine_settings"]["tp_percent"] == 0.02
    assert pool[0]["engine_settings"]["sl_percent"] == 0.01


def test_trusted_runtime_preset_remains_available_without_user_pipeline(tmp_path):
    trader = _Trader()
    customizer = StrategyCustomizer(None, trader, None, None, storage_path=str(tmp_path / "private.json"))
    strategy_id = customizer.create_custom_strategy({
        "name": "balanced preset",
        "trusted_system": True,
        "source_kind": "system_preset",
        "base_params": {"leverage": 1},
    })

    assert customizer.apply_strategy(strategy_id) is True
    assert trader.calls[-1] == {"default_leverage": 1}


def test_user_strategy_adaptive_adjustment_never_mutates_global_trader(tmp_path):
    trader = _Trader()
    customizer = StrategyCustomizer(
        None,
        trader,
        None,
        None,
        storage_path=str(tmp_path / "private.json"),
        min_paper_trades=1,
    )
    strategy_id = customizer.create_custom_strategy(
        {
            "name": "candidate-local",
            "rules": {
                **_rules(),
                "regime_parameters": {
                    "bull": {"leverage": 2, "tp_percent": 3.0}
                },
            },
            "base_params": {
                "leverage": 1,
                "tp_percent": 2.0,
                "sl_percent": 1.0,
            },
        }
    )
    strategy = customizer.user_strategies[strategy_id]
    key = strategy["pipeline_strategy_key"]
    version_id = strategy["pipeline_version_id"]
    customizer.approve_custom_strategy(key, version_id, approved_by="user")
    customizer.record_paper_validation(key, version_id, trades=1)
    customizer.activate_custom_strategy(key, version_id, live_confirmation=True)

    assert customizer.apply_dynamic_adjustment(
        "market_condition",
        {"market_condition": "BULL"},
    ) is False
    assert trader.calls == []


def test_private_versions_are_restored_after_restart(tmp_path):
    storage = tmp_path / "private.json"
    first = StrategyCustomizer(None, _Trader(), None, None, storage_path=str(storage))
    first.create_custom_strategy({"name": "persist me", "rules": _rules(), "base_params": {"leverage": 1}})

    restored = StrategyCustomizer(None, _Trader(), None, None, storage_path=str(storage))
    rows = restored.list_strategies()

    assert len(rows) == 1
    assert rows[0]["name"] == "persist me"
    assert rows[0]["status"] == "analyzed"
    if os.name != "nt":
        assert stat.S_IMODE(storage.stat().st_mode) == 0o600


def test_natural_language_rules_without_engine_settings_cannot_activate(tmp_path):
    customizer = StrategyCustomizer(
        None,
        _Trader(),
        None,
        None,
        storage_path=str(tmp_path / "private.json"),
        min_paper_trades=1,
    )
    strategy_id = customizer.create_custom_strategy({"name": "not compiled", "rules": _rules()})
    strategy = customizer.user_strategies[strategy_id]
    key = strategy["pipeline_strategy_key"]
    version_id = strategy["pipeline_version_id"]
    customizer.approve_custom_strategy(key, version_id, approved_by="user")
    customizer.record_paper_validation(key, version_id, trades=1)

    try:
        customizer.activate_custom_strategy(key, version_id, live_confirmation=True)
    except ValueError as exc:
        assert "실행 엔진 설정" in str(exc)
    else:
        raise AssertionError("uncompiled strategy must not activate")
