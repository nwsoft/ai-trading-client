#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import logging

class AIAutoOptimizer:
    """
    시간/거래/성과 기반 자동 모니터링 및 파라미터 조정
    """
    def __init__(self, ai_manager, recorder, settings, logger=None):
        self.ai_manager = ai_manager
        self.recorder = recorder
        self.settings = settings
        self.logger = logger or logging.getLogger(__name__)
        self.is_running = False
        self.monitoring_intervals = {
            'hourly': 3600,   # 1시간
            'daily': 86400,
            'weekly': 604800
        }
        self.trade_based_triggers = {
            'min_trades_for_analysis': 10,
            'consecutive_losses_threshold': 3,
            'performance_check_interval': 5
        }
        self.performance_thresholds = {
            'win_rate_min': 0.40,
            'avg_profit_min': -0.001,
            'max_loss_threshold': -0.005,
            'drawdown_limit': -0.02
        }

    def start(self):
        if self.is_running: 
            return
        self.is_running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()
        self._thread = t
        self.logger.info("AIAutoOptimizer monitoring started")

    def stop(self):
        self.is_running = False
        try:
            self._thread.join(timeout=2.0)
        except Exception:
            pass
        self.logger.info("AIAutoOptimizer monitoring stopped")

    # --- internal ---

    def _loop(self):
        last_hourly = time.time()
        while self.is_running:
            try:
                now = time.time()

                # 1) 시간 기반: 1시간마다 성과 분석
                if now - last_hourly >= self.monitoring_intervals['hourly']:
                    self._hourly_performance_analysis()
                    last_hourly = now

                # 2) 거래 기반 트리거 검사(연속 손절, 누적 거래 수 등)
                self._check_trade_based_triggers()

                time.sleep(60)  # 1분 주기
            except Exception as e:
                self.logger.error(f"AutoOptimizer loop error: {e}")
                time.sleep(60)

    def _hourly_performance_analysis(self):
        try:
            # 최근 1시간 데이터만 분석 (정확한 시간창 사용)
            since = datetime.now(timezone.utc) - timedelta(hours=1)
            trades: List[Dict] = self.recorder.get_trade_history(since_ts=since.timestamp())
            if len(trades) < 5:
                return
            stats = self._analyze_performance(trades)
            self._maybe_adjust_parameters(stats)
        except Exception as e:
            self.logger.error(f"Hourly performance analysis error: {e}")

    def _check_trade_based_triggers(self):
        try:
            # 최근 1일 거래 데이터 조회 (정확한 시간창 사용)
            since = datetime.now(timezone.utc) - timedelta(days=1)
            trades: List[Dict] = self.recorder.get_trade_history(since_ts=since.timestamp())

            # 연속 손절 개수 계산
            consec_losses = self._count_consecutive_losses(trades)
            if consec_losses >= self.trade_based_triggers['consecutive_losses_threshold']:
                self._emergency_optimization(consec_losses)

            # 거래 10회 이상 / N회마다 점검
            if len(trades) >= self.trade_based_triggers['min_trades_for_analysis']:
                if len(trades) % self.trade_based_triggers['performance_check_interval'] == 0:
                    stats = self._analyze_performance(trades)
                    self._maybe_adjust_parameters(stats)
        except Exception as e:
            self.logger.error(f"Trade-based trigger error: {e}")

    # --- helpers ---

    def _analyze_performance(self, trades: List[Dict]) -> Dict:
        # 간단한 성과 집계(실 시스템의 recorder 통계로 대체 가능)
        total = len(trades)
        wins = sum(1 for t in trades if t.get('result') == 'WIN')
        losses = sum(1 for t in trades if t.get('result') == 'LOSS')
        win_rate = (wins / total) if total else 0.0
        avg_profit = sum(float(t.get('pnl_pct', 0.0)) for t in trades) / total if total else 0.0
        max_dd = min(0.0, min(float(t.get('equity_dd', 0.0)) for t in trades) if trades else 0.0)

        return {
            'total': total,
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate,
            'avg_profit_percent': avg_profit,
            'max_drawdown': max_dd
        }

    def _maybe_adjust_parameters(self, stats: Dict):
        # 임계 기준 비교 후 설정 조정안 제안(여기서는 로그/리턴으로 남김)
        issues = []
        if stats['win_rate'] < self.performance_thresholds['win_rate_min']:
            issues.append('LOW_WINRATE')
        if stats['avg_profit_percent'] < self.performance_thresholds['avg_profit_min']:
            issues.append('NEGATIVE_AVG_PROFIT')
        if stats['max_drawdown'] < self.performance_thresholds['drawdown_limit']:
            issues.append('DEEP_DRAWDOWN')

        if not issues:
            self.logger.info("AutoOptimizer: performance OK")
            return

        # 간단한 조정 휴리스틱 (tp↑, sl↓, 레버리지↓)
        new_tp = float(self.settings.get('default_tp', 0.0025)) * (1.10 if 'LOW_WINRATE' in issues else 1.0)
        new_sl = float(self.settings.get('default_sl', 0.0018)) * (0.90 if 'NEGATIVE_AVG_PROFIT' in issues else 1.0)
        new_lev = int(self.settings.get('default_leverage', 10))
        if 'DEEP_DRAWDOWN' in issues:
            new_lev = max(1, int(new_lev * 0.8))

        self.logger.warning(f"AutoOptimizer proposes: tp={new_tp:.6f}, sl={new_sl:.6f}, lev={new_lev}")
        try:
            # 실제 반영은 사용자 승인/세이프티 매니저와 연동하도록 훅만 남김
            self.settings['default_tp'] = new_tp
            self.settings['default_sl'] = new_sl
            self.settings['default_leverage'] = new_lev
        except Exception as e:
            self.logger.error(f"Apply adjustments failed: {e}")

    def _count_consecutive_losses(self, trades: List[Dict]) -> int:
        cnt = 0
        for t in trades[::-1]:
            if t.get('result') == 'LOSS':
                cnt += 1
            else:
                break
        return cnt

    def _emergency_optimization(self, consec_losses: int):
        self.logger.error(f"Emergency optimization: consecutive losses={consec_losses}")
        # 필요 시 ai_manager/analyzer 호출하여 즉시 조정안을 재평가/반영
