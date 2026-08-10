from pathlib import Path

from trading.runtime_scope import requires_binance_runtime


def test_bitget_only_referral_profile_does_not_construct_binance_runtime():
    assert requires_binance_runtime(
        {
            "selected_exchange": "bitget",
            "enabled_exchanges": ["bitget"],
            "trade_enabled_exchanges": ["bitget"],
            "learning_enabled_exchanges": ["bitget"],
            "paper_trading": True,
        }
    ) is False


def test_binance_runtime_is_created_only_when_explicitly_in_scope():
    assert requires_binance_runtime(
        {"selected_exchange": "bitget", "enabled_exchanges": ["bitget", "binance"]}
    ) is True
    assert requires_binance_runtime({"selected_exchange": "binance"}) is True


def test_main_no_longer_requires_binance_components_for_dashboard():
    source = Path("main.py").read_text(encoding="utf-8")
    assert "if not all([self.analyzer, self.evaluator, self.recorder]):" in source
    assert "if not all([self.binance_client, self.analyzer" not in source
    assert "for exchange_name in list(self.settings.get('enabled_exchanges'" in source
