"""Shipped support instructions; no account, provider or runtime access."""
TRIGGERS=('paper_ledger_currency_unverified','paper_ledger_pnl_unverified','과거paper결제통화','과거paper손익','새paper평가','새페이퍼평가','과거기록을보존','paper전략들삭제','paper다off','paperfunds')
ANSWER_KO='''이 안내는 전략이 망가졌다는 뜻이 아니라, 예전 가상 거래 기록에 결제통화(USDT/KRW)나 손익·비용 근거가 없어 현재 사용할 가상자금을 확인할 수 없다는 뜻입니다. 확인되지 않은 손익을 0으로 만들거나 원장을 삭제하지 않습니다.

전략을 삭제하지 마세요. 전략 스튜디오의 PAPER 검증 OFF, 거래소의 PAPER 자동매매 정지, 실제 LIVE 전환은 서로 다릅니다. 검증을 모두 끄거나 새 검증 1개를 만들어도 같은 거래소의 가상자금 문제는 남습니다. PAPER 모드를 LIVE로 바꿔 해결하지 마세요.

1. 해당 거래소 탭 → 왼쪽 거래소 제어에서 ‘거래 정지’를 누릅니다. 전략 검증 OFF만으로는 거래소가 정지하지 않습니다.
2. ‘운용 요약’ → ‘가상자금 복구 안내’에서 보유 가상 포지션과 주문 예약을 확인합니다. 남아 있거나 미확정이면 먼저 해당 거래소의 포지션·주문 상태를 대조하세요. 보유 자료를 삭제해 비우지 마세요.
3. 기관이 PAPER 모드이고 정지·포지션 없음·예약 없음이 확인되면, 과거 기록 보존 안내에 동의하고 ‘과거 기록 보존하고 새 PAPER 평가 준비’를 누릅니다. 이전 거래 원장은 보존하고 새 가상자금 평가 구간만 만듭니다. 손실을 지우는 반복 초기화가 아닙니다.
4. 준비 완료 후 같은 거래소의 ‘거래 시작’을 누릅니다. 이때 현재 종목·시세·전략·위험 조건을 다시 검사합니다. 전략 검증은 필요에 따라 다시 켭니다.

새 평가 준비는 전략 삭제·실계좌 입출금·자동 주문·과거 손익 복구가 아닙니다. 거래나 수익을 보장하지 않으며, 준비가 거절되면 화면의 사유를 먼저 확인하세요. 이 답변은 사용법 안내이며 현재 계정의 정지·잔액·복구 완료를 확인했다는 뜻은 아닙니다.'''
ANSWER_EN='''Legacy PAPER records are missing settlement currency or PnL/cost evidence, so available simulated funds cannot be verified. Do not delete strategies or the ledger, convert unknown PnL to zero, or switch to LIVE to bypass this guard.
Strategy PAPER validation OFF is different from stopping venue PAPER trading. A new validation still shares the venue wallet.
Open the venue tab, stop its trading, then open Operation summary → Simulated funds recovery guide. Reconcile open simulated positions and pending/reserved orders. Once PAPER mode, stopped execution, no positions and no reservations are verified, acknowledge preservation of history and explicitly prepare a new PAPER evaluation. Then start venue trading to recheck current markets, strategy and risk conditions. Re-enable strategy validation if desired.
The old ledger is preserved. This is a separate evaluation boundary, not recovered historical PnL, a repeatable loss reset, an executed order or a guarantee of trading/profit. This guide does not certify the current account state.'''

def matches(question):
    import re
    text=str(question or '')
    if 'NOAH_STRATEGY_EXPLANATION_V1\n' in text or '[MARKET_TREND_SNAPSHOT]' in text:return False
    compact=re.sub(r'\s+','',text.casefold())
    return any(token.casefold() in compact for token in TRIGGERS)
