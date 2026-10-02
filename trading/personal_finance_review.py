"""Read-only, local financial context. No account valuation or AI calls."""
from datetime import date
from decimal import Decimal, InvalidOperation


def explain_finance_review(review):
    """Readable local answer; never turn missing evidence into zero."""
    def money(value):
        return "기록 없음" if value is None else f"{value:,.0f}원"
    lines = ["등록한 생활금융 기록 기준으로 설명합니다. 외부 AI 호출이나 거래 실행은 없습니다.",
             f"기간: {review.get('period_start', '미확인')} ~ {review.get('period_end', '미확인')} · KRW",
             f"등록 수입 {money(review.get('income'))} / 등록 지출 {money(review.get('expense'))}",
             f"기록상 수입−지출: {money(review.get('recorded_difference'))}",
             f"내 계좌 이체 {review.get('transfer_count', 0)}건은 수입·소비에서 제외했습니다.",
             f"진행 목표 {review.get('active_goal_count', 0)}개. 목표 적립은 계좌 잔액에 더하지 않습니다."]
    lines.extend(f"• {action}" for action in review.get("actions", []))
    lines.append(review.get("boundary", "기록을 다시 확인하세요."))
    lines.append("월간 계획 비교는 생활금융 → 대시보드에서 직접 가정을 입력해 확인할 수 있습니다.")
    return "\n".join(lines)


def build_finance_review(transactions, goals, *, today=None):
    today = today or date.today()
    start = today.replace(day=1)
    totals = {"수입": Decimal(0), "지출": Decimal(0), "내 계좌 이체": Decimal(0)}
    counts = dict.fromkeys(totals, 0)
    invalid = future = 0
    latest = None
    categories = {}
    for tx in transactions:
        try:
            amount = Decimal(str(tx.amount))
            kind = tx.type.value
            if not amount.is_finite() or amount <= 0 or kind not in totals:
                raise ValueError("invalid_transaction")
            if tx.date > today:
                future += 1
                continue
            latest = max(latest, tx.date) if latest else tx.date
            if tx.date < start:
                continue
            totals[kind] += amount
            counts[kind] += 1
            if kind == "지출":
                categories[tx.category] = categories.get(tx.category, Decimal(0)) + amount
        except (ValueError, TypeError, AttributeError, InvalidOperation):
            invalid += 1
    recorded = counts["수입"] + counts["지출"]
    actions = []
    if not recorded:
        actions.append("이번 달 수입·지출 기록을 입력하세요. 기록 없음은 실제 수입·지출 0원이 아닙니다.")
    elif not counts["수입"]:
        actions.append("수입 기록이 없습니다. 적자 여부를 판단하기 전에 누락된 수입을 확인하세요.")
    elif totals["지출"] > totals["수입"]:
        actions.append("등록한 이번 달 지출이 수입을 초과합니다. 누락 기록과 예정 지출을 먼저 확인하세요.")
    else:
        actions.append("기록상 차액은 계좌 잔액이나 투자 가능액이 아닙니다. 예정 결제·생활비를 별도로 확인하세요.")
    if future:
        actions.append(f"미래 날짜 기록 {future}건은 이번 점검에서 제외했습니다. 확정된 거래와 예정 지출을 구분하세요.")
    if invalid:
        actions.append(f"금액·유형을 확인할 수 없는 기록 {invalid}건은 합산하지 않았습니다.")
    active = [g for g in goals if not g.is_completed]
    overdue = sum(1 for g in active if g.deadline and g.deadline < today)
    if overdue:
        actions.append(f"기한이 지난 미완료 목표 {overdue}개가 있습니다. 목표 금액·기한을 재검토하세요.")
    top = sorted(categories.items(), key=lambda row: row[1], reverse=True)[:5]
    return {
        "schema_version": "1.0.0", "status": "recorded_only" if recorded else "no_records",
        "period_start": start.isoformat(), "period_end": today.isoformat(), "currency": "KRW",
        "source": "local_life_finance_records", "latest_record_date": latest.isoformat() if latest else None,
        "income": float(totals["수입"]) if recorded else None,
        "expense": float(totals["지출"]) if recorded else None,
        "recorded_difference": float(totals["수입"] - totals["지출"]) if recorded else None,
        "income_count": counts["수입"], "expense_count": counts["지출"],
        "transfer_count": counts["내 계좌 이체"], "transfer_amount": float(totals["내 계좌 이체"]),
        "future_count": future, "invalid_count": invalid, "active_goal_count": len(active),
        "overdue_goal_count": overdue,
        "top_expenses": [{"category": key, "amount": float(value)} for key, value in top],
        "actions": actions,
        "boundary": "등록된 원화 가계부만 점검합니다. 은행 자동 수집·가족 전체 자산·월말 예측·투자 가능액이 아닙니다. 내부 이체와 목표 적립은 수입·지출에 더하지 않습니다.",
    }
