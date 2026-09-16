"""Bounded, TLS-verified KRX universe from the official KIS public master.

Layout: koreainvestment/open-trading-api/stocks_info/kis_{kospi,kosdaq}_code_mst.py.
Only ordinary stock group ST and ETF group EF are accepted, never ETN/funds.
The prior-day volume/reference price rank candidates, not execution prices.
No credentials, extracted files, account data or orders are involved.
"""
from __future__ import annotations

import io
import threading
import time
import zipfile
from copy import deepcopy

import requests

_CACHE = {}
_LOCK = threading.Lock()
_TTL = 6 * 3600

# Prefix fields through previous-day volume in the official fixed-width tail.
_SPECS = {
    "KOSPI": (227, [2, 1, 4, 4, 4] + [1] * 26 + [9, 5, 5, 1, 1, 1, 2, 1, 1, 1, 2, 2, 2, 3, 1, 3, 12], 31, 47, (34, 35, 36)),
    "KOSDAQ": (221, [2, 1, 4, 4, 4] + [1] * 21 + [9, 5, 5, 1, 1, 1, 2, 1, 1, 1, 2, 2, 2, 3, 1, 3, 12], 26, 42, (29, 30, 31)),
}


def parse_market_master(payload: bytes, market: str) -> list[dict]:
    tail_length, widths, price_index, volume_index, blocked_indices = _SPECS[market]
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        member = archive.getinfo(f"{market.lower()}_code.mst")
        if member.file_size > 10_000_000:
            raise ValueError("market_master_too_large")
        lines = archive.read(member).decode("cp949").splitlines()
    result = []
    for line in lines:
        if len(line) < 21 + tail_length:
            raise ValueError("market_master_layout_invalid")
        prefix, tail = line[:-tail_length], line[-tail_length:]
        code = prefix[:9].strip()
        fields, offset = [], 0
        for width in widths:
            fields.append(tail[offset:offset + width].strip())
            offset += width
        if fields[0] not in {"ST", "EF"} or len(code) != 6 or not code.isdigit():
            continue
        if any(fields[index] == "Y" for index in blocked_indices):
            continue
        price, volume = float(fields[price_index] or 0), int(fields[volume_index] or 0)
        result.append({
            "code": code, "symbol": code, "name": prefix[21:].strip(),
            "market": market, "is_etf": fields[0] == "EF", "status": "ok",
            "current_price": price, "volume": volume, "trade_value": price * volume,
            "source": "kis_public_master", "valuation_basis": "previous_day_reference",
        })
    if not result:
        raise ValueError("market_master_empty")
    return result


def market_master(market: str) -> list[dict]:
    market = str(market).upper()
    if market not in _SPECS:
        raise ValueError("unsupported_master_market")
    with _LOCK:
        cached = _CACHE.get(market)
        now = time.monotonic()
        if cached and now < cached[0]:
            if isinstance(cached[1], str):
                raise RuntimeError(cached[1])
            return deepcopy(cached[1])
        try:
            url = f"https://new.real.download.dws.co.kr/common/master/{market.lower()}_code.mst.zip"
            with requests.get(url, timeout=(5, 15), stream=True) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data) > 2_000_000:
                        raise ValueError("market_master_download_too_large")
            rows = parse_market_master(bytes(data), market)
            _CACHE[market] = (time.monotonic() + _TTL, rows)
            return deepcopy(rows)
        except Exception as exc:
            # Never cache credentials or a raw HTTP response/error in UI state.
            reason = f"{market} 종목 목록 수신 실패({type(exc).__name__}) · 공개 시세 서버 연결을 확인하세요"
            _CACHE[market] = (time.monotonic() + 60, reason)
            raise RuntimeError(reason) from exc
