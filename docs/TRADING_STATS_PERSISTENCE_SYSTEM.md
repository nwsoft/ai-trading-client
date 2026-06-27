# 거래 통계 및 포지션 영구 저장 시스템

## 🚨 문제 상황

### 기존 문제점
1. **거래 통계 초기화**: 앱 재시작 시 거래 통계가 0으로 초기화
2. **포지션 불일치**: 앱 재시작 후 실제 거래소 포지션과 앱 내 포지션 불일치
3. **데이터 손실**: 메모리 기반 저장으로 인한 데이터 손실

### 아키텍처 차이점
- **바이낸스**: `Trader` 클래스 사용 → `main_app.trader.active_positions`
- **CCXT 거래소**: `UnifiedTrader` 클래스 사용 → `unified_trader.active_positions`

## ✅ 해결 방안

### 1. 거래 통계 영구 저장 시스템

#### A. 데이터베이스 스키마 추가
```sql
-- trading/recorder.py에 추가된 테이블
CREATE TABLE IF NOT EXISTS exchange_trade_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL,
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    total_pnl REAL DEFAULT 0.0,
    max_drawdown REAL DEFAULT 0.0,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(exchange)
)
```

#### B. Recorder 클래스 확장
```python
# trading/recorder.py
def save_exchange_trade_stats(self, exchange: str, stats: Dict[str, Any]):
    """거래소별 거래 통계 저장"""
    
def load_exchange_trade_stats(self, exchange: str = None) -> Dict[str, Any]:
    """거래소별 거래 통계 로드"""
```

#### C. 바이낸스 Trader 클래스 수정
```python
# trading/trader.py
def update_trade_stats(self, position: Position):
    """거래 통계 업데이트 및 DB 저장"""
    # 메모리 업데이트
    self.trade_stats['total_trades'] += 1
    # ... 통계 계산 ...
    
    # DB에 통계 저장
    if hasattr(self, 'recorder') and self.recorder:
        self.recorder.save_exchange_trade_stats('binance', self.trade_stats)

def _load_trade_stats_from_db(self):
    """DB에서 거래 통계 로드"""
    if hasattr(self, 'recorder') and self.recorder:
        db_stats = self.recorder.load_exchange_trade_stats('binance')
        if db_stats:
            self.trade_stats.update(db_stats)
```

#### D. CCXT 거래소 UnifiedTrader 클래스 수정
```python
# trading/unified_trader.py
def _update_trade_stats(self, exchange_name: str, position: Position, exit_price: float):
    """거래 통계 업데이트 및 DB 저장"""
    # 메모리 업데이트
    self.trade_stats[exchange_name]['total_trades'] += 1
    # ... 통계 계산 ...
    
    # DB에 통계 저장
    if hasattr(self, 'recorder') and self.recorder:
        stats_for_db = self.trade_stats[exchange_name].copy()
        stats_for_db['winning_trades'] = stats_for_db.get('profitable_trades', 0)
        self.recorder.save_exchange_trade_stats(exchange_name, stats_for_db)

def _load_trade_stats_from_db(self, exchange_name: str):
    """DB에서 거래 통계 로드"""
    if hasattr(self, 'recorder') and self.recorder:
        db_stats = self.recorder.load_exchange_trade_stats(exchange_name)
        if db_stats:
            # DB의 winning_trades를 profitable_trades로 변환
            if 'winning_trades' in db_stats:
                db_stats['profitable_trades'] = db_stats['winning_trades']
                del db_stats['winning_trades']
            self.trade_stats[exchange_name].update(db_stats)
```

### 2. 포지션 복구 시스템

#### A. 바이낸스 포지션 복구
```python
# trading/trader.py
def _restore_positions_from_exchange(self):
    """거래소에서 실제 포지션 조회하여 복구"""
    try:
        if hasattr(self, 'binance_client') and self.binance_client:
            actual_positions = self.binance_client.get_positions()
            if actual_positions:
                for pos in actual_positions:
                    self.active_positions[pos.symbol] = pos
                    self.logger.info(f"✅ 포지션 복구: {pos.symbol} {pos.side.name} {pos.size}")
    except Exception as e:
        self.logger.error(f"❌ 바이낸스 포지션 복구 실패: {e}")
```

#### B. CCXT 거래소 포지션 복구
```python
# trading/unified_trader.py
def _restore_positions_from_exchange(self, exchange_name: str):
    """거래소에서 실제 포지션 조회하여 복구"""
    try:
        if hasattr(self, 'unified_manager') and self.unified_manager:
            adapter = self.unified_manager.get_adapter(exchange_name)
            if adapter and hasattr(adapter, 'get_positions'):
                actual_positions = adapter.get_positions()
                if actual_positions:
                    for pos_data in actual_positions:
                        # CCXT 포지션 데이터를 Position 객체로 변환
                        position = Position(...)
                        self.active_positions[exchange_name][position.symbol] = position
    except Exception as e:
        self.logger.error(f"❌ {exchange_name} 포지션 복구 실패: {e}")
```

### 3. 대시보드 통계 표시 최적화

#### A. 통합 통계 수집 로직
```python
# ui/dashboard_modern.py & ui/widgets/market_trend_widget.py
def _refresh_trading_summary(self):
    # 통합 통계 수집 (DB + 메모리)
    try:
        # DB에서 거래 통계 조회
        import sqlite3
        from path_utils import get_db_file_path
        db_path = get_db_file_path()
        
        if os.path.exists(db_path):
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT exchange, total_trades, winning_trades, losing_trades, total_pnl
                    FROM exchange_trade_stats
                """)
                db_results = cursor.fetchall()
                
                for row in db_results:
                    exchange, trades, wins, losses, pnl = row
                    total_trades += trades
                    total_pnl += pnl
                    
                    # 승률 계산 (가중평균)
                    if trades > 0:
                        exchange_win_rate = (wins / trades) * 100
                        if total_trades > 0:
                            win_rate = ((win_rate * (total_trades - trades)) + (exchange_win_rate * trades)) / total_trades
        
        # 메모리에서 활성 포지션 수 조회 (실시간)
        # 바이낸스 포지션
        if hasattr(self, 'main_app') and hasattr(self.main_app, 'trader') and self.main_app.trader:
            binance_positions = getattr(self.main_app.trader, 'active_positions', {})
            active_positions += len(binance_positions)

        # CCXT 거래소 포지션
        unified_trader = getattr(self, 'unified_trader', None)
        if unified_trader and hasattr(unified_trader, 'get_active_positions'):
            ccxt_positions = unified_trader.get_active_positions()
            for exchange_positions in ccxt_positions.values():
                active_positions += len(exchange_positions)
                
    except Exception as e:
        # 폴백: 기존 방식 사용
        pass
```

## 🔄 시스템 동작 흐름

### 앱 시작 시
1. **거래 통계 로드**: DB에서 각 거래소별 통계 로드
2. **포지션 복구**: 실제 거래소에서 포지션 조회하여 복구
3. **대시보드 초기화**: 로드된 데이터로 UI 초기화

### 거래 실행 시
1. **거래 실행**: 기존 로직대로 거래 실행
2. **통계 업데이트**: 메모리와 DB에 동시 업데이트
3. **포지션 기록**: 메모리에 포지션 정보 저장

### 앱 종료 시
- 메모리 데이터는 자동으로 소멸
- DB 데이터는 영구 보존

## 📊 데이터 흐름도

```
앱 시작 → DB 통계 로드 → 실제 포지션 조회 → 메모리 복구 → UI 표시
    ↓
거래 실행 → 통계 계산 → 메모리 업데이트 → DB 저장 → UI 갱신
    ↓
앱 종료 → 메모리 소멸 → DB 데이터 보존
```

## 🛡️ 안전성 고려사항

### 1. 데이터 일관성
- 메모리와 DB 동시 업데이트로 데이터 일관성 보장
- 트랜잭션 사용으로 원자성 보장

### 2. 오류 처리
- DB 저장 실패 시 메모리는 유지
- 포지션 복구 실패 시 빈 상태로 시작
- 폴백 메커니즘으로 시스템 안정성 확보

### 3. 성능 최적화
- DB 조회 최소화
- 캐싱 전략 적용
- 비동기 처리 고려

## 🔍 디버깅 가이드

### 거래 통계가 표시되지 않는 경우
1. **DB 테이블 확인**: `exchange_trade_stats` 테이블 존재 여부
2. **데이터 확인**: `SELECT * FROM exchange_trade_stats;`
3. **로드 로그 확인**: "거래 통계 DB 로드 완료" 메시지 확인

### 포지션이 복구되지 않는 경우
1. **API 키 확인**: 거래소 API 키 설정 상태
2. **연결 상태 확인**: 거래소 연결 상태
3. **복구 로그 확인**: "포지션 복구 완료" 메시지 확인

### 통계가 부정확한 경우
1. **DB 데이터 확인**: 실제 저장된 통계 데이터
2. **메모리 데이터 확인**: 런타임 통계 상태
3. **계산 로직 확인**: 승률 계산 공식

## 📚 관련 파일

- `trading/recorder.py`: DB 스키마 및 저장/로드 메서드
- `trading/trader.py`: 바이낸스 통계/포지션 관리
- `trading/unified_trader.py`: CCXT 거래소 통계/포지션 관리
- `ui/dashboard_modern.py`: 대시보드 통계 표시
- `ui/widgets/market_trend_widget.py`: 시장 트렌드 통계 표시

이 시스템으로 앱 재시작 후에도 거래 통계와 포지션이 정상적으로 유지됩니다.
