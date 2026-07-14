# API 참조 문서 - v3.8.8.3

## 🌐 백엔드 서버 API

### 기본 정보
- **Base URL**: `https://daltrading.net`
- **인증**: JWT Bearer Token
- **Content-Type**: `application/json`

### 인증 API

#### 로그인
```http
POST /auth/api_login
Content-Type: application/json

{
  "username": "string",
  "password": "string"
}
```

**응답**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "string",
    "email": "string",
    "grade": "string",
    "session_id": "string"
  }
}
```

#### 상태 체크
```http
POST /auth/check_status
Authorization: Bearer {token}
Content-Type: application/json

{
  "id": "string",
  "session_id": "string"
}
```

**응답**:
```json
{
  "is_active": true,
  "force_quit": false,
  "message": "정상 상태"
}
```

#### KPI 이벤트 업로드
```http
POST /auth/kpi/event
Content-Type: application/json

{
    "event_type": "string",
    "category": "auth|report|...",
    "asset_class": "platform|crypto|stock|etf|life_finance|risk",
    "status": "success|failed",
    "user_id": "string|null",
    "session_id": "string|null",
    "source": "noahai_client_*",
    "metric_value": 0.0,
    "metadata": {}
}
```

**현재 클라이언트에서 서버로 전송되는 KPI 이벤트 예시**:
- `login_success_api`
- `login_failed`
- `ai_market_report_generated`
- `ai_market_report_failed`

참고:

- 실제 허용 이벤트는 서버 카탈로그/화이트리스트 기준으로 관리됩니다.
- 외부 공개 페이지에서 보는 KPI는 위 이벤트를 포함한 운영 집계 전체와 동일하지 않을 수 있습니다.
- 공개 KPI는 코호트 기반 정적 스냅샷이고, 관리자 KPI는 익명 이벤트 기반 최신 운영 집계입니다.
- `hold_seconds`, 응답시간, `ai_inference_completed` 계열 운영 KPI는 v3.8.9.28 이후부터 본격 누적되는 항목입니다.

### 거래 신호 API

#### 신호 수신
```http
GET /api/signals
Authorization: Bearer {token}
```

**응답**:
```json
{
  "signals": [
    {
      "id": "string",
      "symbol": "string",
      "action": "BUY|SELL|HOLD",
      "confidence": 0.85,
      "price": 50000.0,
      "quantity": 0.001,
      "tp_price": 51000.0,
      "sl_price": 49000.0,
      "reason": "string",
      "timestamp": "2025-01-01T00:00:00Z",
      "expires_at": "2025-01-01T01:00:00Z"
    }
  ]
}
```

## 💱 거래소 API

### 바이낸스 API

#### 기본 정보
- **Base URL**: `https://fapi.binance.com`
- **인증**: API Key + Secret Key
- **Rate Limit**: 1200 requests/minute

#### 계정 정보 조회
```python
def get_account_info(self) -> Dict[str, Any]:
    """계정 정보 조회"""
    try:
        balance = self.exchange.fetch_balance()
        return {
            'total_balance': balance.get('USDT', {}).get('total', 0),
            'available_balance': balance.get('USDT', {}).get('free', 0),
            'used_balance': balance.get('USDT', {}).get('used', 0),
            'positions': balance.get('info', {}).get('positions', [])
        }
    except Exception as e:
        self.logger.error(f"계정 정보 조회 실패: {e}")
        return {}
```

### WebSocket 표준 API (공통 명세) - 최적화됨 (2025-10-20)

다음 메서드 명은 거래소별 WebSocket 매니저에서 동일하게 제공합니다.

- `subscribe_symbol(symbol: str) -> bool`: 포지션 모니터링용 구독 시작
- `unsubscribe_symbol(symbol: str) -> bool`: 구독 해제
- `get_latest_ticker(symbol: str) -> Optional[Dict]`: 최신 티커 반환 `{ price, v(volume), P(%) , timestamp }`
- `get_latest_orderbook(symbol: str) -> Optional[Dict]`: 최신 오더북 요약

**⚠️ 중요 변경사항 (2025-10-20)**:
- **코인 분석**: WebSocket 구독 제거, REST API 기반 분석으로 변경
- **WebSocket 사용**: 실제 포지션 모니터링에만 사용
- **성능 향상**: 시작 시간 46초 → 즉시 시작

예시 (Binance) - 포지션 모니터링용
```python
from api.binance_client import BinanceWebSocketManager

ws = BinanceWebSocketManager(api_key="...", secret_key="...")
# 거래 성공 시에만 구독 (포지션 모니터링용)
ok = ws.subscribe_symbol("BTCUSDT")
if ok:
    data = ws.get_latest_ticker("BTCUSDT")
    if data and (time.time() - data.get('timestamp', 0) < 30):
        print("last price:", data['price'])
    ob = ws.get_latest_orderbook("BTCUSDT")
    if ob:
        print("best bid/ask:", ob.get('bid'), ob.get('ask'))
ws.unsubscribe_symbol("BTCUSDT")
```


#### 현재 가격 조회
```python
def get_current_price(self, symbol: str) -> float:
    """현재 가격 조회"""
    try:
        ticker = self.exchange.fetch_ticker(symbol)
        return ticker['last']
    except Exception as e:
        self.logger.error(f"가격 조회 실패 {symbol}: {e}")
        return 0.0
```

#### 주문 실행
```python
def place_order(self, symbol: str, side: str, quantity: float, 
               price: Optional[float] = None, order_type: str = "MARKET") -> Dict[str, Any]:
    """주문 실행"""
    try:
        order = self.exchange.create_order(
            symbol=symbol,
            type=order_type,
            side=side,
            amount=quantity,
            price=price
        )
        return order
    except Exception as e:
        self.logger.error(f"주문 실행 실패: {e}")
        return {}
```

### 업비트 API

#### 기본 정보
- **Base URL**: `https://api.upbit.com`
- **인증**: API Key + Secret Key
- **Rate Limit**: 600 requests/minute

#### 계정 정보 조회
```python
def get_account_info(self) -> Dict[str, Any]:
    """계정 정보 조회"""
    try:
        balance = self.exchange.fetch_balance()
        return {
            'total_balance': balance.get('KRW', {}).get('total', 0),
            'available_balance': balance.get('KRW', {}).get('free', 0),
            'used_balance': balance.get('KRW', {}).get('used', 0),
            'positions': []
        }
    except Exception as e:
        self.logger.error(f"계정 정보 조회 실패: {e}")
        return {}
```

#### 현재 가격 조회
```python
def get_current_price(self, symbol: str) -> float:
    """현재 가격 조회"""
    try:
        # 업비트는 KRW-XXX 형식 사용
        if not symbol.startswith('KRW-'):
            symbol = f'KRW-{symbol}'
            
        ticker = self.exchange.fetch_ticker(symbol)
        return ticker['last']
    except Exception as e:
        self.logger.error(f"가격 조회 실패 {symbol}: {e}")
        return 0.0
```

### 빗썸 API

#### 기본 정보
- **Base URL**: `https://api.bithumb.com`
- **인증**: API Key + Secret Key
- **Rate Limit**: 300 requests/minute

#### 계정 정보 조회
```python
def get_account_info(self) -> Dict[str, Any]:
    """계정 정보 조회"""
    try:
        balance = self.exchange.fetch_balance()
        return {
            'total_balance': balance.get('KRW', {}).get('total', 0),
            'available_balance': balance.get('KRW', {}).get('free', 0),
            'used_balance': balance.get('KRW', {}).get('used', 0),
            'positions': []
        }
    except Exception as e:
        self.logger.error(f"계정 정보 조회 실패: {e}")
        return {}
```

#### 현재 가격 조회
```python
def get_current_price(self, symbol: str) -> float:
    """현재 가격 조회"""
    try:
        # 빗썸은 KRW/XXX 형식 사용
        if '/' not in symbol:
            symbol = f'KRW/{symbol}'
            
        ticker = self.exchange.fetch_ticker(symbol)
        return ticker['last']
    except Exception as e:
        self.logger.error(f"가격 조회 실패 {symbol}: {e}")
        return 0.0
```

## 🤖 AI API

### OpenAI API

#### 기본 정보
- **Base URL**: `https://api.openai.com/v1`
- **인증**: API Key
- **Rate Limit**: 사용자별 제한

#### 채팅 완성
```python
def chat_completion(self, messages: List[Dict], model: str = "gpt-4") -> str:
    """채팅 완성"""
    try:
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        self.logger.error(f"OpenAI API 호출 실패: {e}")
        return ""
```

#### 거래 신호 생성
```python
def generate_trading_signal(self, market_data: Dict) -> Dict:
    """거래 신호 생성"""
    try:
        prompt = f"""
        시장 데이터를 분석하여 거래 신호를 생성해주세요.
        
        시장 데이터:
        {json.dumps(market_data, indent=2)}
        
        응답 형식:
        {{
            "action": "BUY|SELL|HOLD",
            "confidence": 0.0-1.0,
            "reason": "분석 근거",
            "tp_price": 가격,
            "sl_price": 가격
        }}
        """
        
        response = self.chat_completion([
            {"role": "system", "content": "당신은 전문 트레이더입니다."},
            {"role": "user", "content": prompt}
        ])
        
        return json.loads(response)
    except Exception as e:
        self.logger.error(f"거래 신호 생성 실패: {e}")
        return {"action": "HOLD", "confidence": 0.0, "reason": "분석 실패"}
```

## 📊 데이터베이스 API

### SQLite 데이터베이스

#### 거래 로그 테이블
```sql
CREATE TABLE trade_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    quantity REAL NOT NULL,
    leverage INTEGER DEFAULT 1,
    entry_time DATETIME NOT NULL,
    exit_time DATETIME,
    pnl REAL,
    fees REAL,
    status TEXT DEFAULT 'OPEN',
    ai_confidence REAL,
    ai_reason TEXT
);
```

#### 분석 로그 테이블
```sql
CREATE TABLE analysis_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    market_condition TEXT,
    technical_indicators TEXT,
    ai_analysis TEXT,
    confidence REAL,
    recommendation TEXT
);
```

#### AI 최적화 테이블
```sql
CREATE TABLE ai_optimization (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    optimization_type TEXT NOT NULL,
    old_value REAL,
    new_value REAL,
    performance_metric REAL,
    reason TEXT
);
```

## 🔧 내부 API

### 설정 관리 API

#### 설정 로드
```python
def load_settings(self) -> Dict[str, Any]:
    """설정 로드"""
    try:
        with open(self.settings_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        self.logger.error(f"설정 로드 실패: {e}")
        return {}
```

#### 설정 저장
```python
def save_settings(self, settings: Dict[str, Any]) -> bool:
    """설정 저장"""
    try:
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        self.logger.error(f"설정 저장 실패: {e}")
        return False
```

### 로그 관리 API

#### 로그 기록
```python
def log_trade_entry(self, trade_data: Dict) -> bool:
    """거래 진입 로그"""
    try:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO trade_log 
            (symbol, side, entry_price, quantity, leverage, entry_time, ai_confidence, ai_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_data['symbol'],
            trade_data['side'],
            trade_data['entry_price'],
            trade_data['quantity'],
            trade_data.get('leverage', 1),
            trade_data['entry_time'],
            trade_data.get('ai_confidence', 0.0),
            trade_data.get('ai_reason', '')
        ))
        self.conn.commit()
        return True
    except Exception as e:
        self.logger.error(f"거래 진입 로그 실패: {e}")
        return False
```

#### 로그 조회
```python
def get_trade_history(self, symbol: str = None, days: int = 30, since_ts: float = None) -> List[Dict]:
    """거래 히스토리 조회"""
    try:
        cursor = self.conn.cursor()
        
        if since_ts:
            since_datetime = datetime.fromtimestamp(since_ts).strftime('%Y-%m-%d %H:%M:%S')
            query = "SELECT * FROM trade_log WHERE entry_time > ?"
            params = (since_datetime,)
        else:
            query = "SELECT * FROM trade_log WHERE entry_time > datetime('now', '-{} days')".format(days)
            params = ()
        
        if symbol:
            query += " AND symbol = ?"
            params = params + (symbol,)
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        self.logger.error(f"거래 히스토리 조회 실패: {e}")
        return []
```

## 🚨 오류 처리

### 일반적인 오류 코드

#### HTTP 상태 코드
- **200**: 성공
- **400**: 잘못된 요청
- **401**: 인증 실패
- **403**: 권한 없음
- **404**: 리소스 없음
- **500**: 서버 오류

#### 거래소 API 오류
- **-1001**: 알 수 없는 오류
- **-1002**: 잘못된 요청
- **-1003**: 요청 제한 초과
- **-1004**: 서버 오류
- **-1005**: 권한 없음

### 오류 처리 예시
```python
def handle_api_error(self, error: Exception) -> Dict[str, Any]:
    """API 오류 처리"""
    if isinstance(error, requests.exceptions.Timeout):
        return {"error": "timeout", "message": "요청 시간 초과"}
    elif isinstance(error, requests.exceptions.ConnectionError):
        return {"error": "connection", "message": "연결 오류"}
    elif isinstance(error, requests.exceptions.HTTPError):
        return {"error": "http", "message": f"HTTP 오류: {error.response.status_code}"}
    else:
        return {"error": "unknown", "message": str(error)}
```

## 📋 API 사용 예시

### 완전한 거래 플로우
```python
# 1. 로그인
login_response = requests.post("https://daltrading.net/auth/api_login", json={
    "username": "user",
    "password": "pass"
})
token = login_response.json()["access_token"]

# 2. 거래 신호 수신
signals_response = requests.get("https://daltrading.net/api/signals", 
    headers={"Authorization": f"Bearer {token}"})
signals = signals_response.json()["signals"]

# 3. 거래 실행
for signal in signals:
    if signal["action"] == "BUY":
        order = exchange_client.place_order(
            symbol=signal["symbol"],
            side="buy",
            quantity=signal["quantity"],
            price=signal["price"]
        )
        
        # 4. 결과 기록
        recorder.log_trade_entry({
            "symbol": signal["symbol"],
            "side": "buy",
            "entry_price": signal["price"],
            "quantity": signal["quantity"],
            "entry_time": datetime.now(),
            "ai_confidence": signal["confidence"],
            "ai_reason": signal["reason"]
        })
```
