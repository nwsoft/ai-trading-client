"""trading/fraud_detection_service.py 단위 테스트."""

import pytest
from datetime import date
from trading.fraud_detection_service import (
    FraudAlert,
    TransactionRecord,
    analyze_voice_phishing,
    detect_abnormal_transactions,
    check_predatory_loan,
    compute_fraud_risk_summary,
)


# ─────────────────────────────────────────────────────────────
# 보이스피싱 탐지
# ─────────────────────────────────────────────────────────────

class TestAnalyzeVoicePhishing:
    def test_clean_text_low_risk(self):
        result = analyze_voice_phishing("안녕하세요, 오늘 날씨 좋네요.")
        assert result.risk_level == 'low'
        assert result.score == 0.0
        assert result.matched_patterns == []

    def test_government_impersonation(self):
        result = analyze_voice_phishing("검찰청입니다. 귀하의 계좌가 범죄에 연루되었습니다.")
        assert result.risk_level in ('high', 'critical')
        assert result.score >= 0.75
        assert len(result.matched_patterns) >= 1

    def test_safe_account_scam(self):
        result = analyze_voice_phishing("안전계좌로 이체해 주세요.")
        assert result.score >= 0.80
        assert result.risk_level in ('high', 'critical')

    def test_remote_control_app_critical(self):
        result = analyze_voice_phishing("원격제어 앱을 설치하고 접속해 주세요.")
        assert result.risk_level == 'critical'
        assert result.score >= 0.90

    def test_otp_steal_critical(self):
        result = analyze_voice_phishing("OTP 인증번호를 알려주세요.")
        assert result.risk_level == 'critical'

    def test_multiple_patterns_higher_score(self):
        single = analyze_voice_phishing("검찰청입니다.")
        multi = analyze_voice_phishing("검찰청입니다. 안전계좌로 이체하고 OTP를 알려주세요.")
        assert multi.score >= single.score

    def test_smishing_url_detected(self):
        result = analyze_voice_phishing("http://kb-bank.click/abc 클릭하세요.")
        assert result.score > 0
        assert len(result.matched_patterns) >= 1

    def test_guaranteed_return_fraud(self):
        result = analyze_voice_phishing("월 수익률 50% 보장 투자 상품입니다.")
        assert result.score >= 0.80

    def test_returns_fraud_alert_type(self):
        result = analyze_voice_phishing("검찰청입니다.")
        assert isinstance(result, FraudAlert)
        assert result.alert_type == 'voice_phishing'

    def test_actions_provided_for_high_risk(self):
        result = analyze_voice_phishing("검찰청입니다. 안전계좌로 이체하세요.")
        assert len(result.recommended_actions) > 0


# ─────────────────────────────────────────────────────────────
# 이상 거래 탐지
# ─────────────────────────────────────────────────────────────

def _make_history(amounts, category='소비'):
    return [
        TransactionRecord(amount=a, tx_date=date(2026, 1, i+1), category=category)
        for i, a in enumerate(amounts)
    ]


class TestDetectAbnormalTransactions:
    def test_normal_transaction_low_risk(self):
        history = _make_history([50000, 60000, 45000, 55000, 52000])
        new_tx = TransactionRecord(amount=53000, tx_date=date(2026, 1, 10))
        result = detect_abnormal_transactions(history, new_tx)
        assert result.risk_level == 'low'
        assert result.score < 0.4

    def test_large_amount_anomaly(self):
        history = _make_history([50000, 60000, 45000, 55000, 52000])
        # 평균 5.2만 대비 1000배
        new_tx = TransactionRecord(amount=50_000_000, tx_date=date(2026, 1, 10))
        result = detect_abnormal_transactions(history, new_tx)
        assert result.score >= 0.4
        assert len(result.matched_patterns) >= 1

    def test_repeated_transfer_to_same_account(self):
        history = [
            TransactionRecord(amount=990000, tx_date=date(2026, 1, i+1),
                              counterpart='악성계좌123', is_transfer=True)
            for i in range(5)
        ]
        new_tx = TransactionRecord(
            amount=990000, tx_date=date(2026, 1, 6),
            counterpart='악성계좌123', is_transfer=True
        )
        result = detect_abnormal_transactions(history, new_tx)
        assert result.score >= 0.60
        any_split = any('반복' in p for p in result.matched_patterns)
        assert any_split

    def test_new_counterpart_large_transfer(self):
        history = [
            TransactionRecord(amount=100000, tx_date=date(2026, 1, i+1),
                              counterpart='단골식당', is_transfer=True)
            for i in range(5)
        ]
        new_tx = TransactionRecord(
            amount=5_000_000, tx_date=date(2026, 1, 6),
            counterpart='처음거래계좌', is_transfer=True
        )
        result = detect_abnormal_transactions(history, new_tx)
        assert result.score > 0
        any_new = any('신규' in p for p in result.matched_patterns)
        assert any_new

    def test_short_history_no_crash(self):
        history = _make_history([100000, 200000])  # 2건 (임계값 미달)
        new_tx = TransactionRecord(amount=50_000_000, tx_date=date(2026, 1, 5))
        result = detect_abnormal_transactions(history, new_tx)
        assert isinstance(result, FraudAlert)
        assert result.alert_type == 'abnormal_tx'

    def test_empty_history_no_crash(self):
        result = detect_abnormal_transactions([], TransactionRecord(amount=1000000, tx_date=date(2026, 1, 1)))
        assert isinstance(result, FraudAlert)
        assert result.score == 0.0

    def test_rapid_cash_withdrawal(self):
        history = [
            TransactionRecord(amount=2_000_000, tx_date=date(2026, 1, i+1), category='현금인출')
            for i in range(3)
        ]
        new_tx = TransactionRecord(amount=2_000_000, tx_date=date(2026, 1, 4), category='현금인출')
        result = detect_abnormal_transactions(history, new_tx)
        assert result.score >= 0.4


# ─────────────────────────────────────────────────────────────
# 약탈적 대출 경고
# ─────────────────────────────────────────────────────────────

class TestCheckPredatoryLoan:
    def test_normal_loan_low_risk(self):
        result = check_predatory_loan(annual_rate=4.5, requested_amount=100_000_000)
        assert result.risk_level == 'low'
        assert result.score == 0.0

    def test_over_legal_max_rate_critical(self):
        result = check_predatory_loan(annual_rate=25.0, requested_amount=5_000_000)
        assert result.risk_level in ('high', 'critical')
        assert result.score >= 0.70
        assert any('법정 최고금리' in p for p in result.matched_patterns)

    def test_upfront_fee_high_risk(self):
        result = check_predatory_loan(
            annual_rate=10.0, requested_amount=5_000_000,
            upfront_fee_required=True
        )
        assert result.score >= 0.80
        assert result.risk_level in ('high', 'critical')

    def test_no_credit_check_low_rate_critical(self):
        result = check_predatory_loan(
            annual_rate=3.0, requested_amount=50_000_000,
            no_credit_check=True
        )
        assert result.score >= 0.85
        assert result.risk_level == 'critical'

    def test_guaranteed_return_critical(self):
        result = check_predatory_loan(
            annual_rate=15.0, requested_amount=10_000_000,
            promises_guaranteed_return=True
        )
        assert result.score >= 0.85
        assert result.risk_level == 'critical'

    def test_illegal_usury(self):
        result = check_predatory_loan(annual_rate=120.0, requested_amount=500_000)
        assert result.score >= 0.90
        assert result.risk_level == 'critical'

    def test_actions_available_for_critical(self):
        result = check_predatory_loan(annual_rate=30.0, requested_amount=3_000_000)
        assert len(result.recommended_actions) > 0

    def test_high_rate_warning(self):
        result = check_predatory_loan(annual_rate=17.0, requested_amount=5_000_000)
        assert result.score >= 0.50


# ─────────────────────────────────────────────────────────────
# 종합 리스크 요약
# ─────────────────────────────────────────────────────────────

class TestFraudRiskSummary:
    def test_empty_alerts(self):
        result = compute_fraud_risk_summary([])
        assert result['overall_score'] == 0.0
        assert result['overall_risk_level'] == 'low'
        assert result['top_alert'] is None

    def test_single_high_alert(self):
        alert = analyze_voice_phishing("검찰청입니다. OTP를 알려주세요.")
        result = compute_fraud_risk_summary([alert])
        assert result['overall_score'] >= 0.70
        assert result['overall_risk_level'] in ('high', 'critical')

    def test_all_patterns_merged(self):
        alert1 = analyze_voice_phishing("안전계좌로 이체해 주세요.")
        alert2 = check_predatory_loan(30.0, 1_000_000)
        result = compute_fraud_risk_summary([alert1, alert2])
        assert len(result['all_patterns']) == len(alert1.matched_patterns) + len(alert2.matched_patterns)

    def test_actions_deduplicated(self):
        a1 = analyze_voice_phishing("검찰청입니다.")
        a2 = analyze_voice_phishing("안전계좌로 이체하세요.")
        result = compute_fraud_risk_summary([a1, a2])
        actions = result['all_actions']
        assert len(actions) == len(set(actions))

    def test_summary_contains_risk_level(self):
        alert = analyze_voice_phishing("검찰청입니다. 즉시 이체하세요.")
        result = compute_fraud_risk_summary([alert])
        assert 'HIGH' in result['summary'].upper() or 'CRITICAL' in result['summary'].upper()

    def test_disclaimer_present(self):
        result = compute_fraud_risk_summary([])
        assert '참고' in result['disclaimer']

    def test_multiple_medium_alerts_escalate(self):
        alert_low = check_predatory_loan(annual_rate=17.0, requested_amount=5_000_000)
        alert_med = check_predatory_loan(annual_rate=18.0, requested_amount=5_000_000)
        result = compute_fraud_risk_summary([alert_low, alert_med])
        # 두 개 합산 시 medium 이상
        assert result['overall_score'] > 0
