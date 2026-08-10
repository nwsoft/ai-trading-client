"""거래소 계좌 패널의 명칭·데이터·오류 상태 정본.

CustomTkinter에 의존하지 않는 순수 정책만 둔다. 현물 보유자산을 선물 포지션과
같은 의미로 다루거나, 조회 실패를 정상 0건으로 바꾸는 일을 방지한다.
"""

from dataclasses import dataclass
from typing import Any, Dict


SPOT_EXCHANGES = frozenset({"upbit", "bithumb"})


@dataclass(frozen=True)
class AccountPanelContract:
    title: str
    loading_text: str
    empty_text: str
    quote_asset: str
    holding_mode: bool
    source: str


@dataclass(frozen=True)
class AccountPanelResult:
    state: str
    rows: Any
    message: str = ""
    error_code: str = ""
    execution_mode: str = ""

    @property
    def is_error(self) -> bool:
        return self.state in {"error", "unavailable"}


def get_exchange_account_contract(exchange: str) -> AccountPanelContract:
    exchange_key = str(exchange or "").strip().lower()
    if exchange_key in SPOT_EXCHANGES:
        return AccountPanelContract(
            title="보유자산",
            loading_text="보유자산 조회 중",
            empty_text="보유자산 없음",
            quote_asset="KRW",
            holding_mode=True,
            source="balance",
        )
    return AccountPanelContract(
        title="포지션",
        loading_text="포지션 조회 중",
        empty_text="활성 포지션 없음",
        quote_asset="USDT",
        holding_mode=False,
        source="positions",
    )


def _numeric_balance(value: Any) -> float:
    if isinstance(value, dict):
        value = value.get("total", value.get("balance", value.get("wallet_balance", 0)))
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def normalize_spot_holdings(balance: Any, quote_asset: str = "KRW") -> Dict[str, Dict[str, Any]]:
    """정규화된 잔고에서 기준통화·요약키를 제외한 실제 현물 보유량을 만든다."""
    if not isinstance(balance, dict):
        return {}

    excluded = {
        str(quote_asset or "KRW").upper(),
        "TOTAL",
        "TOTAL_BALANCE",
        "TOTAL_ASSETS",
        "AVAILABLE",
        "AVAILABLE_BALANCE",
        "FREE",
        "CASH",
        "EQUITY",
        "UNREALIZED_PNL",
        "UNREALIZEDPNL",
    }
    holdings: Dict[str, Dict[str, Any]] = {}
    for raw_asset, raw_value in balance.items():
        asset = str(raw_asset or "").strip().upper()
        quantity = _numeric_balance(raw_value)
        if not asset or asset in excluded or quantity <= 0:
            continue
        holdings[asset] = {
            "symbol": asset,
            "side": "HOLD",
            "quantity": quantity,
            "entry_price": 0.0,
            "unrealized_pnl": 0.0,
        }
    return holdings


def build_account_panel_result(
    rows: Any,
    *,
    empty_message: str,
    stale: bool = False,
    message: str = "",
    execution_mode: str = "",
) -> AccountPanelResult:
    has_rows = bool(rows) if isinstance(rows, (dict, list, tuple)) else False
    if stale:
        return AccountPanelResult(
            "stale",
            rows if has_rows else {},
            message or "로컬 캐시",
            execution_mode=execution_mode,
        )
    if has_rows:
        return AccountPanelResult("success", rows, execution_mode=execution_mode)
    return AccountPanelResult("empty", {}, empty_message, execution_mode=execution_mode)


def summarize_paper_positions(positions: Any) -> Dict[str, float]:
    """PAPER 전용 저장소를 가상 계좌 요약으로 만든다.

    가상 원금·가용 잔고 장부가 없는 상태에서 실잔고를 추정하지 않고,
    엔진이 관리하는 활성 건수와 미실현 PnL만 집계한다.
    """
    if isinstance(positions, dict):
        rows = list(positions.values())
    elif isinstance(positions, (list, tuple)):
        rows = list(positions)
    else:
        rows = []

    total_pnl = 0.0
    for position in rows:
        value = 0.0
        for key in ("unrealized_pnl", "unrealizedPnl", "pnl"):
            if hasattr(position, key):
                value = getattr(position, key)
                break
            if isinstance(position, dict) and position.get(key) is not None:
                value = position.get(key)
                break
        try:
            total_pnl += float(value or 0.0)
        except (TypeError, ValueError):
            continue
    return {"position_count": float(len(rows)), "unrealized_pnl": total_pnl}


def select_paper_position_store(
    *,
    execution_mode: str,
    exchange: str,
    binance_store: Any = None,
    unified_stores: Any = None,
) -> Any:
    """PAPER 저장소만 복사해 반환하고 LIVE/LEARNING은 `None`을 반환한다."""
    if str(execution_mode or "").strip().lower() != "paper":
        return None
    exchange_key = str(exchange or "").strip().lower()
    if exchange_key == "binance":
        return dict(binance_store or {}) if isinstance(binance_store, dict) else {}
    if not isinstance(unified_stores, dict):
        return {}
    exchange_store = unified_stores.get(exchange_key, {})
    return dict(exchange_store or {}) if isinstance(exchange_store, dict) else {}


def account_panel_error(message: str, error_code: str = "account_read_failed") -> AccountPanelResult:
    return AccountPanelResult("error", {}, str(message or "조회 오류"), error_code)


def account_panel_unavailable(message: str) -> AccountPanelResult:
    return AccountPanelResult("unavailable", {}, str(message or "연결 미준비"), "client_unavailable")
