#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
자동 튜닝/권장치 산출 매니저
 - DB의 trade_log 기반으로 최근 성과/슬리피지 요약 → futures_selection 권장치 생성
 - operation_mode가 'auto'면 자동 적용, 'guided'면 권장만 반환, 'pro'는 미사용
"""

import os
import sqlite3
from typing import Dict, Any, Tuple


class TuningManager:
    def __init__(self, settings: Dict[str, Any]):
        self.settings = settings

    def _load_db_rows(self, db_path: str, days: int = 30):
        if not os.path.exists(db_path):
            return []
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT exchange, symbol, pnl_percent, slippage
                FROM trade_log
                WHERE date(entry_time) >= date('now', ?)
                """,
                (f"-{int(days)} days",)
            )
            return cur.fetchall()
        except Exception:
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _get_tuning_cfg(self) -> Dict[str, Any]:
        return (self.settings or {}).get('tuning', {}) if isinstance(self.settings, dict) else {}

    def _get_fs_cfg(self, ex: str) -> Dict[str, Any]:
        try:
            return ((self.settings or {}).get('futures_selection', {}) or {}).get(ex, {})
        except Exception:
            return {}

    def _clip(self, v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    def recommend_for_exchange(self, db_path: str, exchange: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """(권장치, 근거) 반환. 권장치는 futures_selection.{exchange}의 일부 키를 포함.
        단순한 규칙 기반:
          - 평균 절대 슬리피지가 높으면 min_quote_volume 상향, volatility_max 하향
          - 승률 낮으면 변동성 상한을 소폭 하향
          - 승률 높고 슬리피지 낮으면 min_quote_volume 완화
        """
        rows = self._load_db_rows(db_path, days=30)
        if not rows:
            return {}, {"reason": "no_data"}

        # 집계
        import math
        total = 0
        win = 0
        abs_slips = []
        for ex, sym, pnl_pct, slip in rows:
            if str(ex or '').lower() != str(exchange or '').lower():
                continue
            try:
                total += 1
                if (pnl_pct or 0) > 0:
                    win += 1
                abs_slips.append(abs(float(slip or 0.0)))
            except Exception:
                continue
        if total == 0:
            return {}, {"reason": "no_exchange_data"}
        win_rate = (win / total) * 100.0
        avg_abs_slip = sum(abs_slips) / len(abs_slips) if abs_slips else 0.0

        # 현재/튜닝 파라미터
        fs = self._get_fs_cfg(exchange)
        cur_min_qv = float(fs.get('min_quote_volume', 0.0) or 0.0)
        cur_vol_max = float(fs.get('volatility_max', 25.0) or 25.0)

        tcfg = self._get_tuning_cfg()
        abs_warn = float(tcfg.get('slippage_abs_warn', 0.001))
        abs_high = float(tcfg.get('slippage_abs_high', 0.002))
        step_vol = float(tcfg.get('adjust_step_volume', 0.15))  # 15%
        step_vlt = float(tcfg.get('adjust_step_volatility', 5.0))  # 5pt
        min_min_qv = float(tcfg.get('min_min_quote_volume', 5_000_000))
        max_min_qv = float(tcfg.get('max_min_quote_volume', 50_000_000))
        min_vmax = float(tcfg.get('min_volatility_max', 10.0))
        max_vmax = float(tcfg.get('max_volatility_max', 40.0))

        rec_min_qv = cur_min_qv if cur_min_qv > 0 else min_min_qv
        rec_vmax = cur_vol_max

        # 규칙 적용
        if avg_abs_slip >= abs_high:
            rec_min_qv = self._clip(rec_min_qv * (1.0 + step_vol), min_min_qv, max_min_qv)
            rec_vmax = self._clip(rec_vmax - step_vlt, min_vmax, max_vmax)
            reason = f"high_slippage({avg_abs_slip:.5f})"
        elif avg_abs_slip >= abs_warn:
            rec_min_qv = self._clip(rec_min_qv * (1.0 + step_vol * 0.5), min_min_qv, max_min_qv)
            rec_vmax = self._clip(rec_vmax - step_vlt * 0.5, min_vmax, max_vmax)
            reason = f"warn_slippage({avg_abs_slip:.5f})"
        else:
            # 슬리피지 양호, 승률 높으면 완화
            if win_rate >= 55.0:
                rec_min_qv = self._clip(rec_min_qv * (1.0 - step_vol * 0.3), min_min_qv, max_min_qv)
                rec_vmax = self._clip(rec_vmax + step_vlt * 0.3, min_vmax, max_vmax)
                reason = f"good_perf(win{win_rate:.1f}%)"
            else:
                reason = f"stable(win{win_rate:.1f}%)"

        rec = {
            "min_quote_volume": float(rec_min_qv),
            "volatility_max": float(rec_vmax)
        }
        return rec, {"reason": reason, "win_rate": win_rate, "avg_abs_slippage": avg_abs_slip}

    def apply_recommendations(self, db_path: str, enabled_exchanges: list) -> Dict[str, Any]:
        """설정에 권장치를 적용해 반환(딕셔너리 참조 기반 업데이트)."""
        if not isinstance(self.settings, dict):
            return self.settings
        fs_all = self.settings.setdefault('futures_selection', {})
        for ex in enabled_exchanges or []:
            if ex not in ('bybit', 'okx', 'bitget'):
                continue
            fs = fs_all.setdefault(ex, {})
            rec, meta = self.recommend_for_exchange(db_path, ex)
            if rec:
                fs.update(rec)
        return self.settings

