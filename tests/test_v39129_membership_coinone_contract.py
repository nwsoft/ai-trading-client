from pathlib import Path
import pytest

from membership_policy import membership_position_cap, referral_allowed_exchanges
from trading.exchanges.adapters.coinone_spot_adapter import CoinoneSpotAdapter
from trading.exchanges.adapters.bithumb_spot_adapter import BithumbSpotAdapter
from trading.exchanges.adapters.upbit_spot_adapter import UpbitSpotAdapter
from trading.exchanges.venue_capabilities import public_venue_registry, venue_supports_execution
from trading.unified_trader import UnifiedTrader
from trading.unified_trading_manager import UnifiedTradingManager
from web_platform.runtime_bridge import HeadlessRuntimeBridge, _credential_status


ROOT = Path(__file__).resolve().parents[1]


def test_strategy_rights_and_account_capacity_are_separate():
    assert membership_position_cap("referral", strategy_validation=True) == 5
    assert membership_position_cap("pro_coin", strategy_validation=True) == 5
    assert membership_position_cap("premium", strategy_validation=True) == 5
    assert membership_position_cap("referral") == 3
    assert membership_position_cap("pro_coin") == 5
    assert membership_position_cap("premium") == 5
    assert membership_position_cap("pro_stock") == 0
    assert membership_position_cap("referral", {"max_managed_positions_per_venue": 99}) == 3
    assert membership_position_cap("pro_coin", {"max_managed_positions_per_venue": 2}) == 2


def test_domestic_free_scope_does_not_open_unverified_foreign_venues():
    assert referral_allowed_exchanges({}) == {"upbit", "bithumb", "coinone"}
    assert referral_allowed_exchanges({"allowed_exchanges": "tampered"}) == {
        "upbit", "bithumb", "coinone"
    }
    assert referral_allowed_exchanges({"allowed_exchanges": ["binance", "unknown"]}) == {
        "upbit", "bithumb", "coinone", "binance"
    }


def test_coinone_uses_common_paper_live_contract_but_requires_order_credentials():
    registry = {row["client_id"]: row for row in public_venue_registry()["venues"]}
    assert registry["coinone"]["paper_supported"] is True
    assert registry["coinone"]["live_supported"] is True
    assert venue_supports_execution("coinone", "paper") is True
    assert venue_supports_execution("coinone", "live") is True

    adapter = CoinoneSpotAdapter("", "", live_e2e_verified=False)
    result = adapter.place_order("ETH/KRW", "buy", 0.01)
    assert result["error_code"] == "credential_required"
    assert adapter.get_order_status("order-without-symbol") == {}
    assert "종목" in adapter.last_error


def test_user_surfaces_explain_capacity_and_coinone_boundary():
    settings = (ROOT / "web_platform/application_services.py").read_text(encoding="utf-8")
    manual = (ROOT / "ui/widgets/user_manual_widget.py").read_text(encoding="utf-8")
    changelog = (ROOT / "docs/CHANGELOG.md").read_text(encoding="utf-8")
    for source in (settings, manual, changelog):
        assert "무료" in source and "3개" in source
        assert "유료" in source and "5개" in source
        assert "Coinone" in source or "코인원" in source


def test_coinone_credentials_are_part_of_the_canonical_runtime_status():
    empty = _credential_status({})
    configured = _credential_status({
        "coinone_api_key": "read-trade-key",
        "coinone_secret_key": "secret",
        "coinone_live_e2e_verified": True,  # User input cannot approve provider E2E.
    })
    assert empty["coinone"] is False
    assert configured["coinone"] is True


def test_krw_spot_paper_start_does_not_require_private_credentials():
    class FakeApp:
        def __init__(self):
            self.started = []

        def start_source(self, source):
            self.started.append(source)
            return True

        def running_crypto_exchanges(self):
            return list(self.started)

    for venue in ("upbit", "bithumb", "coinone"):
        app = FakeApp()
        bridge = HeadlessRuntimeBridge(account="tester", factory=lambda _account, app=app: app)
        bridge._settings = lambda venue=venue: {
            "paper_trading": True,
            "enabled_exchanges": [venue],
            "trade_enabled_exchanges": [venue],
        }
        result = bridge.execute("trading.start", {"source": venue})
        assert result["command"] == "trading.start"
        assert result["running_sources"] == [venue]


def test_krw_spot_public_selection_and_analysis_do_not_require_private_credentials():
    class Unified:
        @staticmethod
        def select_trading_coins_unified(source):
            return [{"symbol": "BTC/KRW", "selection_status": "scored", "exchange": source}]

    class Analyzer:
        @staticmethod
        def analyze_symbol(symbol, *, exchange_name):
            assert exchange_name in ('upbit', 'bithumb', 'coinone')
            return {"symbol": symbol, "signal": "HOLD"}

    class FakeApp:
        unified_trader = Unified()
        analyzer = Analyzer()

        @staticmethod
        def running_crypto_exchanges():
            return []

    for venue in ("upbit", "bithumb", "coinone"):
        bridge = HeadlessRuntimeBridge(account="tester", factory=lambda _account: FakeApp())
        bridge._settings = lambda venue=venue: {
            "paper_trading": True,
            "enabled_exchanges": [venue],
        }
        selected = bridge.execute("coins.select", {"source": venue})
        analyzed = bridge.execute("coins.analyze", {"source": venue, "symbol": "BTC"})
        assert selected["selected_symbols"] == ["BTC/KRW"]
        assert analyzed["symbol"] == "BTCKRW"
        assert analyzed["order_submitted"] is False


@pytest.mark.parametrize('venue',['upbit','bithumb','coinone'])
@pytest.mark.parametrize('old_flag',[False,True])
def test_domestic_live_start_uses_common_confirmation_and_credentials(venue,old_flag):
    class FakeApp:
        def __init__(self): self.started=[]
        def start_source(self,source): self.started.append(source);return True
        def running_crypto_exchanges(self): return self.started
    app=FakeApp()
    bridge = HeadlessRuntimeBridge(account="tester", factory=lambda _account: app)
    bridge._settings = lambda: {
        "paper_trading": False,
        "enabled_exchanges": [venue],
        "trade_enabled_exchanges": [venue],
        "_trade_scope_user_confirmed_v3905": True,
        f"{venue}_api_key": "key",
        f"{venue}_secret_key": "secret",
        "coinone_live_e2e_verified": old_flag,
    }
    with pytest.raises(RuntimeError,match='live_start_confirmation_required'):
        bridge.execute('trading.start',{'source':venue})
    assert app.started==[]
    assert bridge.execute('trading.start',{'source':venue,'live_confirmation':True})['running_sources']==[venue]
    settings=bridge._settings();settings[f'{venue}_api_key']=''
    bridge._settings=lambda:settings
    with pytest.raises(RuntimeError,match='credential_required'):
        bridge.execute('trading.start',{'source':venue,'live_confirmation':True})


def test_unified_manager_allows_public_clients_only_for_krw_spot_paper(monkeypatch):
    class PublicAdapter:
        def connect(self):
            return True

    created = []

    def create_spot(name, settings):
        created.append((name, bool(settings.get("paper_trading"))))
        return PublicAdapter()

    monkeypatch.setattr(
        "trading.unified_trading_manager.ExchangeFactory.create_spot_exchange",
        create_spot,
    )
    for venue in ("upbit", "bithumb", "coinone"):
        manager = UnifiedTradingManager({
            "paper_trading": True,
            "enabled_exchanges": [venue],
        })
        assert manager.get_exchange(venue, "spot") is not None

    live = UnifiedTradingManager({
        "paper_trading": False,
        "enabled_exchanges": ["coinone"],
        "trade_enabled_exchanges": ["coinone"],
        "_trade_scope_user_confirmed_v3905": True,
    })
    assert live.get_exchange("coinone", "spot") is None
    assert created == [("upbit", True), ("bithumb", True), ("coinone", True)]


def test_krw_spot_adapters_share_symbol_and_default_universe_contracts():
    adapters = (
        UpbitSpotAdapter("", ""),
        BithumbSpotAdapter("", ""),
        CoinoneSpotAdapter("", ""),
    )
    for adapter in adapters:
        for symbol in ("BTC/KRW", "KRW-BTC", "BTCKRW", "BTCUSDT"):
            assert adapter._normalize_symbol(symbol) == "BTC/KRW"

    trader = object.__new__(UnifiedTrader)
    for venue in ("upbit", "bithumb", "coinone"):
        assert [row["symbol"] for row in trader._get_default_coins(venue)] == [
            "BTC/KRW" if venue != "upbit" else "KRW-BTC",
            "ETH/KRW" if venue != "upbit" else "KRW-ETH",
            "ADA/KRW" if venue != "upbit" else "KRW-ADA",
        ]
