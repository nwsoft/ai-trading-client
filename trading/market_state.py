#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
시장 전반 상태(레짐) 분석
"""

from typing import Dict, List
from dataclasses import dataclass
from datetime import datetime
import numpy as np


@dataclass
class MarketRegime:
    timestamp: datetime
    avg_volatility_24h: float
    adv_usdt_volume: float
    breadth_up_ratio: float
    avg_spread_bp: float
    liquidity_score: float
    regime: str  # LOW_VOL / NORMAL / HIGH_VOL


class MarketStateAnalyzer:
    def __init__(self, binance_client):
        self.binance_client = binance_client

    def analyze(self) -> MarketRegime:
        tickers = self.binance_client.get_all_24h_tickers() or []
        # 선물 심볼 중 USDT 페어만
        rows = [t for t in tickers if isinstance(t, dict) and str(t.get('symbol','')).endswith('USDT')]
        if not rows:
            return MarketRegime(datetime.now(), 0.0, 0.0, 0.5, 5.0, 0.5, 'NORMAL')

        try:
            changes = []
            usdt_volumes = []
            spreads_bp = []
            ups = 0
            for r in rows:
                try:
                    pchg = float(r.get('priceChangePercent', r.get('P', 0.0)))
                    last = float(r.get('lastPrice', r.get('c', 0.0)))
                    bid = float(r.get('bidPrice', r.get('b', last)))
                    ask = float(r.get('askPrice', r.get('a', last)))
                    vol = float(r.get('quoteVolume', 0.0))
                except Exception:
                    continue
                changes.append(abs(pchg))
                usdt_volumes.append(vol)
                if bid > 0:
                    spreads_bp.append((ask - bid) / bid * 10000)
                if pchg > 0:
                    ups += 1
            avg_vol = float(np.mean(changes)) if changes else 0.0
            adv = float(np.median(usdt_volumes)) if usdt_volumes else 0.0
            avg_spread = float(np.median(spreads_bp)) if spreads_bp else 5.0
            breadth = ups / max(1, len(rows))
            # 간단한 레짐 분류
            if avg_vol >= 10.0:
                regime = 'HIGH_VOL'
            elif avg_vol <= 2.0:
                regime = 'LOW_VOL'
            else:
                regime = 'NORMAL'
            # 유동성 점수(낮은 스프레드, 높은 거래대금)
            liq = max(0.0, min(1.0, (1/(1+avg_spread/5.0)) * 0.5 + (np.log10(adv+1)/8.0)))
            return MarketRegime(datetime.now(), avg_vol, adv, breadth, avg_spread, liq, regime)
        except Exception:
            return MarketRegime(datetime.now(), 0.0, 0.0, 0.5, 5.0, 0.5, 'NORMAL')


