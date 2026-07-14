import asyncio

from ai_chat_strategy import AITradingChatbot


class DummyTrader:
    def __init__(self):
        self.settings = {}
        self.available_balance = 280.0
        self.trade_history = [
            {"symbol": "BTCUSDT", "pnl": 120.0, "fees": 0.12, "timestamp": "2026-07-10T10:00:00"},
            {"symbol": "ETHUSDT", "pnl": -40.0, "fees": 0.08, "timestamp": "2026-07-10T11:00:00"},
            {"symbol": "SOLUSDT", "pnl": 60.0, "fees": 0.06, "timestamp": "2026-07-10T12:00:00"},
            {"symbol": "XRPUSDT", "pnl": -20.0, "fees": 0.04, "timestamp": "2026-07-10T13:00:00"},
        ]
        self.active_positions = {
            "BTCUSDT": {"quantity": 0.01, "entry_price": 60000.0},
            "ETHUSDT": {"quantity": 0.2, "entry_price": 3000.0},
        }

    def update_settings(self, new_settings):
        self.settings.update(new_settings)


class DummyAnalyzer:
    def set_user_signal_threshold(self, _threshold):
        return None


def test_performance_review_builds_health_report():
    bot = AITradingChatbot(analyzer=DummyAnalyzer(), trader=DummyTrader(), risk_manager=None)

    result = asyncio.run(bot._handle_performance_review_request())

    assert "계좌 건강도 + 거래 복기" in result["text"]
    assert "포트폴리오 진단" in result["text"]
    assert "현금 비율" in result["text"]
    assert "건강도 점수" in result["text"]
    assert "Sharpe" in result["text"]
    assert "MDD" in result["text"]
    assert result.get("action", {}).get("type") == "performance_review"
    assert "portfolio_diagnosis" in result.get("action", {})


def test_performance_review_without_trades_returns_guidance():
    trader = DummyTrader()
    trader.trade_history = []
    bot = AITradingChatbot(analyzer=DummyAnalyzer(), trader=trader, risk_manager=None)

    result = asyncio.run(bot._handle_performance_review_request())

    assert "최근 거래 데이터가 없어" in result["text"]
    assert "거래 이력 보기" in result["suggested_actions"]


def test_daily_report_contains_cost_and_portfolio_sections():
    bot = AITradingChatbot(analyzer=DummyAnalyzer(), trader=DummyTrader(), risk_manager=None)

    # 의도 분류 확인 (S-3)
    assert bot._analyze_intent("오늘 일일 리포트 보여줘") == bot._analyze_intent("일일 리포트")

    result = asyncio.run(bot._handle_daily_report_request())

    assert "AI 일일 리포트" in result["text"]
    assert "아침 브리프" in result["text"]
    assert "저녁 복기" in result["text"]
    assert "누적Fee" in result["text"]
    assert "Fee/PnL" in result["text"]
    assert result.get("action", {}).get("type") == "daily_report"
    assert "cost" in result.get("action", {})


def test_daily_report_without_trades_returns_data_missing_message():
    trader = DummyTrader()
    trader.trade_history = []
    bot = AITradingChatbot(analyzer=DummyAnalyzer(), trader=trader, risk_manager=None)

    result = asyncio.run(bot._handle_daily_report_request())

    assert "거래 데이터가 없어 일일 리포트를 생성" in result["text"]


def test_general_question_returns_investment_assistant_briefing():
    bot = AITradingChatbot(analyzer=DummyAnalyzer(), trader=DummyTrader(), risk_manager=None)

    result = asyncio.run(bot._handle_general_question("투자 비서로 지금 조언해줘"))

    assert "AI 투자비서 브리핑" in result["text"]
    assert "현재 포커스" in result["text"]
    assert result.get("action", {}).get("type") == "investment_assistant"
    assert "일일 리포트" in result["suggested_actions"]


def test_general_question_without_trades_returns_guidance():
    trader = DummyTrader()
    trader.trade_history = []
    bot = AITradingChatbot(analyzer=DummyAnalyzer(), trader=trader, risk_manager=None)

    result = asyncio.run(bot._handle_general_question("투자비서 도움"))

    assert "거래 데이터가 부족" in result["text"]
    assert result.get("action", {}).get("type") == "investment_assistant"
