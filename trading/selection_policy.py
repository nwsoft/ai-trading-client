#!/usr/bin/env python3
"""자산·거래대상 선정과 AI 커스텀 적용 전 경계를 정의한다.

SelectionPolicy는 주문 전략을 평가하지 않는다. 사용자가 고정한 종목과
시장·유동성 기반 자동 후보를 합쳐, 각 거래소/증권사에서 분석할 유니버스만
결정한다. AI 커스텀은 이 결과의 각 종목을 이후 단계에서 정확히 한 번 평가한다.

v3.9.0.4 계약:
- 일반/confirm 경로는 NoahAI 자동 후보를 사용한다.
- 고급/independent 경로는 전략에 저장된 StrategyUniversePolicy로 로컬 필터한다.
- 사용자 고정 종목은 "항상 평가" 대상이지 강제 주문 대상이 아니다.
- 유니버스 사전 필터는 LLM을 호출하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Sequence


def _symbol(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("symbol") or value.get("code")
    return str(value or "").strip().upper()


@dataclass(frozen=True)
class SelectionPolicy:
    """수동 고정 종목 우선 + 자동 후보 보충이라는 공통 선정 계약."""

    target: str
    asset_class: str
    limit: int = 20

    def resolve(
        self,
        *,
        automatic_candidates: Sequence[Any] | None,
        pinned_symbols: Sequence[Any] | None = None,
        supported_symbols: Iterable[Any] | None = None,
    ) -> List[Dict[str, Any]]:
        normalized_limit = max(1, int(self.limit or 1))
        supported = {
            _symbol(item) for item in (supported_symbols or []) if _symbol(item)
        }
        validate_support = supported_symbols is not None
        result: List[Dict[str, Any]] = []
        seen = set()

        def append(value: Any, source: str) -> None:
            symbol = _symbol(value)
            if not symbol or symbol in seen:
                return
            if validate_support and symbol not in supported:
                return
            item = dict(value) if isinstance(value, Mapping) else {"symbol": symbol}
            item["symbol"] = symbol
            item["_selection_source"] = source
            item["_selection_target"] = str(self.target or "").strip().lower()
            item["_selection_asset_class"] = str(self.asset_class or "").strip().lower()
            result.append(item)
            seen.add(symbol)

        # 사용자가 명시적으로 고정한 대상은 자동 재선정으로 사라지지 않는다.
        for value in pinned_symbols or []:
            append(value, "user_pinned")

        # 고정 종목이 한도를 넘으면 사용자의 명시적 선택을 조용히 삭제하지 않는다.
        effective_limit = max(normalized_limit, len(result))
        for value in automatic_candidates or []:
            if len(result) >= effective_limit:
                break
            append(value, "auto_market")

        return result


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _candidate_value(item: Mapping[str, Any], *keys: str) -> float:
    for key in keys:
        if key not in item:
            continue
        value = _float(item.get(key), 0.0)
        if value:
            return value
    return 0.0


def _scope_matches(scope: Any, *, asset_class: str, target: str) -> bool:
    normalized = str(scope or "asset:crypto").strip().lower()
    asset = str(asset_class or "").strip().lower()
    current = str(target or "").strip().lower()
    if normalized == "asset:all":
        return True
    if normalized == f"asset:{asset}":
        return True
    if normalized.startswith("exchange:"):
        return asset == "crypto" and normalized.split(":", 1)[1] == current
    if normalized.startswith("broker:"):
        return asset == "stock" and normalized.split(":", 1)[1] == current
    return False


@dataclass(frozen=True)
class StrategyUniversePolicy:
    """고급 독립 전략이 소유하는 저비용 종목 유니버스 정책.

    값의 단위:
    - min_quote_volume: 거래소/증권사가 제공하는 quote 거래대금 원단위
    - max_spread_bps: basis point
    - min/max_volatility_percent: percent point (예: 1.5 == 1.5%)
    """

    include_symbols: tuple[str, ...] = ()
    exclude_symbols: tuple[str, ...] = ()
    asset_types: tuple[str, ...] = ()
    min_quote_volume: float = 0.0
    max_spread_bps: float = 0.0
    min_volatility_percent: float = 0.0
    max_volatility_percent: float = 0.0
    min_history_points: int = 0
    max_candidates: int = 20
    ranking: str = "liquidity"

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None) -> "StrategyUniversePolicy":
        raw = dict(values or {})

        def symbols(key: str) -> tuple[str, ...]:
            value = raw.get(key, [])
            if isinstance(value, str):
                value = value.replace(";", ",").split(",")
            return tuple(dict.fromkeys(_symbol(item) for item in (value or []) if _symbol(item)))

        raw_types = raw.get("asset_types", [])
        if isinstance(raw_types, str):
            raw_types = raw_types.replace(";", ",").split(",")
        asset_types = tuple(
            dict.fromkeys(
                str(value or "").strip().lower()
                for value in (raw_types or [])
                if str(value or "").strip()
            )
        )
        return cls(
            include_symbols=symbols("include_symbols"),
            exclude_symbols=symbols("exclude_symbols"),
            asset_types=asset_types,
            min_quote_volume=max(0.0, _float(raw.get("min_quote_volume"), 0.0)),
            max_spread_bps=max(0.0, _float(raw.get("max_spread_bps"), 0.0)),
            min_volatility_percent=max(
                0.0, _float(raw.get("min_volatility_percent"), 0.0)
            ),
            max_volatility_percent=max(
                0.0, _float(raw.get("max_volatility_percent"), 0.0)
            ),
            min_history_points=max(0, int(_float(raw.get("min_history_points"), 0))),
            max_candidates=max(1, min(200, int(_float(raw.get("max_candidates"), 20)))),
            ranking=str(raw.get("ranking") or "liquidity").strip().lower(),
        )

    def _matches(self, item: Mapping[str, Any]) -> bool:
        symbol = _symbol(item)
        if not symbol or symbol in self.exclude_symbols:
            return False
        if self.include_symbols and symbol not in self.include_symbols:
            return False

        asset_type = str(
            item.get("asset_type")
            or ("etf" if bool(item.get("is_etf", False)) else "")
        ).strip().lower()
        if self.asset_types and asset_type and asset_type not in self.asset_types:
            return False

        quote_volume = _candidate_value(
            item,
            "quoteVolume",
            "quote_volume",
            "trade_value",
            "trading_value",
            "turnover",
            "acc_trade_value",
        )
        if self.min_quote_volume > 0 and quote_volume < self.min_quote_volume:
            return False

        spread_bps = _candidate_value(item, "spread_bps", "bid_ask_spread_bps")
        if self.max_spread_bps > 0 and (
            spread_bps <= 0 or spread_bps > self.max_spread_bps
        ):
            return False

        volatility = abs(
            _candidate_value(
                item,
                "volatility_percent",
                "market_volatility",
                "volatility",
                "change_1h",
            )
        )
        # 0~1 fraction으로 들어온 값은 percent point로 맞춘다.
        if 0 < volatility <= 1 and bool(item.get("_volatility_is_fraction", False)):
            volatility *= 100.0
        if self.min_volatility_percent > 0 and volatility < self.min_volatility_percent:
            return False
        if self.max_volatility_percent > 0 and (
            volatility <= 0 or volatility > self.max_volatility_percent
        ):
            return False

        history_points = int(
            _candidate_value(item, "history_points", "candle_count", "count")
        )
        if self.min_history_points > 0 and history_points < self.min_history_points:
            return False
        return True

    def resolve(
        self,
        *,
        market_candidates: Sequence[Any] | None,
        pinned_symbols: Sequence[Any] | None = None,
        strategy_id: str = "",
    ) -> List[Dict[str, Any]]:
        source_by_symbol: Dict[str, Dict[str, Any]] = {}
        for item in market_candidates or []:
            symbol = _symbol(item)
            if symbol and symbol not in source_by_symbol:
                source_by_symbol[symbol] = (
                    dict(item) if isinstance(item, Mapping) else {"symbol": symbol}
                )

        ordered: List[Dict[str, Any]] = []
        seen: set[str] = set()

        def append(value: Any, source: str, *, force_evaluate: bool = False) -> None:
            symbol = _symbol(value)
            if not symbol or symbol in seen or symbol in self.exclude_symbols:
                return
            base = source_by_symbol.get(symbol)
            item = dict(base or (value if isinstance(value, Mapping) else {"symbol": symbol}))
            item["symbol"] = symbol
            if not force_evaluate and not self._matches(item):
                return
            item["_selection_source"] = source
            item["_selection_pipeline"] = "advanced"
            item["_strategy_universe_id"] = str(strategy_id or "")
            item["_force_evaluate"] = bool(force_evaluate)
            ordered.append(item)
            seen.add(symbol)

        # 고정 종목은 유니버스 수치 필터로 조용히 제거하지 않는다. 실제 진입은
        # 데이터 품질·전략 진입조건·공통 안전 경계에서 별도로 판단한다.
        for value in pinned_symbols or []:
            append(value, "user_pinned", force_evaluate=True)
        for symbol in self.include_symbols:
            append(symbol, "strategy_include", force_evaluate=True)

        eligible = [
            dict(item) if isinstance(item, Mapping) else {"symbol": _symbol(item)}
            for item in (market_candidates or [])
            if isinstance(item, Mapping) and self._matches(item)
        ]

        def rank(item: Mapping[str, Any]) -> tuple[float, float, str]:
            liquidity = _candidate_value(
                item,
                "quoteVolume",
                "quote_volume",
                "trade_value",
                "trading_value",
                "turnover",
                "acc_trade_value",
            )
            volatility = abs(
                _candidate_value(item, "volatility_percent", "market_volatility", "volatility")
            )
            if self.ranking == "volatility":
                return volatility, liquidity, _symbol(item)
            return liquidity, volatility, _symbol(item)

        for item in sorted(eligible, key=rank, reverse=True):
            if len(ordered) >= max(self.max_candidates, len(seen)):
                break
            append(item, "strategy_universe")
        return ordered


def select_advanced_strategy_universe(
    *,
    strategy_pool: Sequence[Mapping[str, Any]] | None,
    market_candidates: Sequence[Any] | None,
    pinned_symbols: Sequence[Any] | None,
    asset_class: str,
    target: str,
    default_limit: int = 20,
) -> List[Dict[str, Any]]:
    """대상에 맞는 independent 전략들의 유니버스를 우선순위순 합친다."""

    independent = []
    for strategy in strategy_pool or []:
        if not isinstance(strategy, Mapping):
            continue
        rules = dict(strategy.get("rules") or {})
        mode = str(
            strategy.get("signal_mode") or rules.get("signal_mode") or "confirm"
        ).strip().lower()
        if mode != "independent":
            continue
        scope = strategy.get("target_scope") or rules.get("target_scope")
        if not _scope_matches(scope, asset_class=asset_class, target=target):
            continue
        independent.append(dict(strategy))

    independent.sort(
        key=lambda item: int(item.get("priority", 5) or 5),
        reverse=True,
    )
    combined: List[Dict[str, Any]] = []
    index: Dict[str, Dict[str, Any]] = {}
    for strategy in independent[:10]:
        rules = dict(strategy.get("rules") or {})
        policy_values = dict(
            strategy.get("universe_policy")
            or rules.get("universe_policy")
            or {"max_candidates": default_limit}
        )
        policy_values.setdefault("max_candidates", default_limit)
        selected = StrategyUniversePolicy.from_mapping(policy_values).resolve(
            market_candidates=market_candidates,
            pinned_symbols=pinned_symbols,
            strategy_id=str(
                strategy.get("version_id")
                or strategy.get("id")
                or strategy.get("strategy_key")
                or ""
            ),
        )
        for item in selected:
            symbol = _symbol(item)
            if not symbol:
                continue
            if symbol not in index:
                index[symbol] = dict(item)
                index[symbol]["_eligible_strategy_modes"] = ["independent"]
                index[symbol]["_eligible_strategy_ids"] = []
                combined.append(index[symbol])
            strategy_id = str(item.get("_strategy_universe_id") or "")
            if strategy_id and strategy_id not in index[symbol]["_eligible_strategy_ids"]:
                index[symbol]["_eligible_strategy_ids"].append(strategy_id)
    return combined


def combine_selection_paths(
    general_candidates: Sequence[Any] | None,
    advanced_candidates: Sequence[Any] | None,
) -> List[Dict[str, Any]]:
    """일반/고급 유니버스를 합치되 후보 출처와 평가 가능한 역할을 보존한다."""

    result: List[Dict[str, Any]] = []
    index: Dict[str, Dict[str, Any]] = {}

    def append(value: Any, pipeline: str) -> None:
        symbol = _symbol(value)
        if not symbol:
            return
        item = dict(value) if isinstance(value, Mapping) else {"symbol": symbol}
        item["symbol"] = symbol
        if symbol not in index:
            index[symbol] = item
            index[symbol]["_selection_pipeline"] = pipeline
            index[symbol]["_eligible_strategy_modes"] = (
                ["confirm", "independent"] if pipeline == "general" else ["independent"]
            )
            result.append(index[symbol])
            return
        current = index[symbol]
        if pipeline not in str(current.get("_selection_pipeline") or ""):
            current["_selection_pipeline"] = "general+advanced"
        current["_eligible_strategy_modes"] = ["confirm", "independent"]
        for strategy_id in item.get("_eligible_strategy_ids", []) or []:
            ids = current.setdefault("_eligible_strategy_ids", [])
            if strategy_id not in ids:
                ids.append(strategy_id)

    for candidate in general_candidates or []:
        append(candidate, "general")
    for candidate in advanced_candidates or []:
        append(candidate, "advanced")
    return result


def normalize_market_regime(value: Any, default: str = "range") -> str:
    normalized = str(value or "").strip().upper().split(".")[-1]
    aliases = {
        "BULL": "bull",
        "BULLISH": "bull",
        "UPTREND": "bull",
        "BEAR": "bear",
        "BEARISH": "bear",
        "DOWNTREND": "bear",
        "SIDEWAYS": "range",
        "RANGE": "range",
        "NORMAL": "range",
        "TREND": "trend",
        "TRENDING": "trend",
        "VOLATILE": "volatile",
        "HIGH_VOLATILITY": "volatile",
        "CALM": "calm",
        "LOW_VOLATILITY": "calm",
    }
    return aliases.get(normalized, str(value or default).strip().lower() or default)


REGIME_SCOPES = {"market", "symbol", "both", "none"}


def normalize_regime_scope(value: Any, default: str = "market") -> str:
    normalized = str(value or default).strip().lower()
    return normalized if normalized in REGIME_SCOPES else default


def resolve_market_regimes(
    context: Mapping[str, Any] | None,
    market_fallback: Any = "range",
) -> Dict[str, str]:
    """전체 시장국면과 종목 국면을 서로 다른 값으로 추출한다."""

    values = dict(context or {})
    market_value = market_fallback
    market_source = "target_fallback"
    for key in (
        "_market_regime",
        "overall_market_regime",
        "venue_market_regime",
        "exchange_market_regime",
    ):
        if values.get(key) not in (None, ""):
            market_value = values.get(key)
            market_source = f"context:{key}"
            break

    symbol_value: Any = ""
    symbol_source = "symbol_unavailable"
    for key in ("symbol_market_regime", "_symbol_market_regime"):
        if values.get(key) not in (None, ""):
            symbol_value = values.get(key)
            symbol_source = f"context:{key}"
            break
    if not symbol_value:
        for key in ("trend_direction", "market_trend", "trend"):
            if values.get(key) in (None, ""):
                continue
            normalized = normalize_market_regime(values.get(key), "")
            if normalized in {"bull", "bear", "range", "trend", "volatile", "calm"}:
                symbol_value = normalized
                symbol_source = f"context:{key}"
                break

    market = normalize_market_regime(market_value)
    symbol = normalize_market_regime(symbol_value, "") if symbol_value else ""
    return {
        "market": market,
        "market_source": market_source,
        "symbol": symbol,
        "symbol_source": symbol_source,
    }


def resolve_effective_market_regime(
    context: Mapping[str, Any] | None,
    fallback: Any = "range",
    regime_scope: Any = "market",
) -> tuple[str, str]:
    """명시적 regime_scope에 따라 표시·기본 평가 국면을 반환한다."""

    regimes = resolve_market_regimes(context, fallback)
    scope = normalize_regime_scope(regime_scope)
    if scope == "none":
        return "unrestricted", "scope:none"
    if scope == "symbol":
        if regimes["symbol"]:
            return regimes["symbol"], regimes["symbol_source"]
        return regimes["market"], f"{regimes['market_source']}:symbol_fallback"
    if scope == "both":
        symbol = regimes["symbol"] or regimes["market"]
        if symbol == regimes["market"]:
            return regimes["market"], "scope:both_same"
        return f"{regimes['market']}+{symbol}", "scope:both"
    return regimes["market"], regimes["market_source"]
