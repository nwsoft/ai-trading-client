from __future__ import annotations

from typing import Dict, Iterable, List


DEFAULT_CRYPTO_SECTORS: Dict[str, List[str]] = {
    "L1": ["BTC", "ETH", "SOL", "ADA", "AVAX", "SUI"],
    "L2": ["ARB", "OP", "MATIC", "STRK"],
    "DeFi": ["AAVE", "UNI", "MKR", "CRV", "COMP"],
    "AI": ["FET", "RENDER", "TAO", "WLD"],
    "RWA": ["ONDO", "LINK", "MKR"],
    "Meme": ["DOGE", "SHIB", "PEPE", "BONK"],
}


class AssetTaxonomy:
    def __init__(
        self,
        stock_sectors: Dict[str, str] | None = None,
        crypto_sectors: Dict[str, Iterable[str]] | None = None,
    ):
        self.stock_sectors = {str(k).upper(): str(v) for k, v in (stock_sectors or {}).items()}
        self.crypto_sectors = {
            str(sector): {str(symbol).upper() for symbol in symbols}
            for sector, symbols in (crypto_sectors or DEFAULT_CRYPTO_SECTORS).items()
        }

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        value = str(symbol or "").strip().upper()
        for suffix in ("USDT", "USD", "KRW"):
            if value.endswith(suffix) and len(value) > len(suffix):
                return value[: -len(suffix)]
        return value

    def sector_for(self, symbol: str, asset_type: str) -> str:
        normalized = self.normalize_symbol(symbol)
        if str(asset_type).lower() in {"crypto", "coin", "blockchain"}:
            for sector, symbols in self.crypto_sectors.items():
                if normalized in symbols:
                    return sector
            return "기타"
        return self.stock_sectors.get(normalized, "미분류")

    def group(self, rows: Iterable[Dict]) -> Dict[str, List[Dict]]:
        result: Dict[str, List[Dict]] = {}
        for row in rows:
            sector = self.sector_for(str(row.get("symbol", "")), str(row.get("asset_type", "")))
            result.setdefault(sector, []).append(dict(row))
        return result
