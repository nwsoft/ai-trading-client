"""AI 리포트의 UI 비의존 텍스트 포맷 함수."""

from __future__ import annotations

from typing import Any, Dict


def format_champion_challenger_section(data: Dict[str, Any]) -> str:
    """챔피언-챌린저 결과를 결제통화 경계를 보존해 표시한다."""
    comp = data.get("comparison", {}) if isinstance(data, dict) else {}
    champion = data.get("champion", {}) if isinstance(data, dict) else {}
    challenger = data.get("challenger", {}) if isinstance(data, dict) else {}

    verdict = str(comp.get("verdict", "unknown"))
    summary = str(comp.get("summary", "요약 없음"))
    win_delta = float(comp.get("win_rate_delta", 0.0) or 0.0)
    pnl_delta = float(comp.get("total_pnl_delta", 0.0) or 0.0)
    trade_delta = int(comp.get("trades_delta", 0) or 0)
    champion_wr = float(champion.get("win_rate", 0.0) or 0.0)
    challenger_wr = float(challenger.get("win_rate", 0.0) or 0.0)
    champion_by_currency = champion.get("pnl_by_currency", {}) or {}
    challenger_by_currency = challenger.get("pnl_by_currency", {}) or {}

    currency_lines = []
    for currency in sorted(set(champion_by_currency) | set(challenger_by_currency)):
        currency_lines.append(
            f"- {currency}: 챔피언 {float(champion_by_currency.get(currency, 0.0)):+.4f} "
            f"→ 챌린저 {float(challenger_by_currency.get(currency, 0.0)):+.4f}"
        )
    currency_block = "\n".join(currency_lines)
    if currency_block:
        currency_block += "\n"

    monetary_line = (
        f"- 동일통화 총손익 변화: {pnl_delta:+.4f}\n"
        if comp.get("total_pnl_delta") is not None
        else "- 금액 우열: 결제통화 경계로 비교 보류\n"
    )
    return (
        "7일 챔피언-챌린저\n\n"
        f"- 판정: {verdict}\n"
        f"- 요약: {summary}\n"
        f"- 승률 변화: {win_delta:+.2f}%p "
        f"(챔피언 {champion_wr:.2f}% → 챌린저 {challenger_wr:.2f}%)\n"
        f"{monetary_line}"
        f"{currency_block}"
        f"- 거래 수 변화: {trade_delta:+d}건\n"
    )
