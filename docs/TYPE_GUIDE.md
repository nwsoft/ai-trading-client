# 타입 안정성 가이드 (엄격 모드)

본 프로젝트는 CustomTkinter 기반 대시보드와 통합 트레이딩 코어를 대상으로 “엄격 타입 정리” 정책을 적용합니다. 목표는 정적 분석 경고를 최소화하고, 런타임 안정성을 높이는 것입니다.

- 생성이 보장되는 UI 구성요소는 Optional을 지양합니다.
  - 예: `tab_widget`, `start_stop_btn`, `analytics_summary_label`, 배지/라벨 등은 생성 함수에서 즉시 할당합니다.
- 생성 시점이 가변적인 컴포넌트는 Optional 유지 + 안전 가드로 접근합니다.
  - 예: 외부 위젯(학습/리포트/어시스턴트), 사용자 상태 매니저 등은 `hasattr(...) and obj`로 확인 후 사용.
- 코어 접근은 지역 변수로 안전 추출 후 사용합니다.
  - `ut = getattr(self, 'unified_trader', None)` → 이후 `if ut and hasattr(ut, '...'):` 패턴 사용.
  - 매니저도 동일: `mgr = getattr(self, 'unified_manager', None)`
- Dict 형태 기대값은 런타임 타입 보정 후 `.get()`/`.items()` 호출합니다.
  - 결과 타입이 불명확한 외부 유틸/CSV 요약 결과는 `isinstance(x, dict)`로 확인 후 접근.
- configure/메서드 호출 전 존재/메서드 체크
  - `if hasattr(label, 'configure'):`와 같은 방어적 접근을 유지합니다.

추가 권장
- 헬퍼 함수로 가드 반복 최소화: `_cfg(widget, **kw)`, `_has(o, name)` 등.
- 새 위젯/라벨 추가 시 생성 함수에서 반드시 `self.xxx =`로 보관하고, Optional을 피하세요.

---

변경 로그 요약 (2025-09-21)
- `ui/dashboard_modern.py`: 생성자 속성 초기화 확대, unified_trader/unified_manager 접근시 지역 변수 안전 추출, analytics 요약 타입 보정, 여러 Optional 호출부 가드 강화.
- 레거시 PyQt5 파일: ImportError 스텁 유지(사용 차단) – CustomTkinter-only 정책 고수.

## UI 위젯 라이프사이클 원칙 (대시보드)
- 탭뷰 참조는 항상 `self.tab_widget`에서 지역 변수로 캐스팅해 사용합니다.
  - 예: `tv = cast(CTkTabview, self.tab_widget)` 후 `tv.add/remove/tab(...)` 호출
  - 과거 `self.tabview` 별칭은 사용하지 않습니다.
- 블록체인 서비스 하위 탭은 업데이트 시 매번 초기화 후 재구성합니다.
  - 조건부로 건드리지 말고 “지우고 다시 만든다”를 기본 원칙으로 합니다.
- 리포트 탭은 `AIReportWidgetReal` 하나로 통일합니다.
  - `self.ai_report_widget`에 보관하고, `generate_report()`는 `auto_generate_reports()`로 위임합니다.
  - 과거 `report_display` 경로는 제거/미사용입니다.
- 체크박스/토글 접근은 존재/메서드 확인 후 안전 호출합니다.
  - `cb = getattr(self, 'show_signals_only', None)` → `if cb and hasattr(cb, 'get'):`
  - `deselect()` 호출 전 `hasattr(cb, 'deselect')` 확인
- 배지/라벨 텍스트·컬러는 기본값을 먼저 설정한 뒤 조건부 업데이트합니다.
  - 언바운드 변수 경고를 원천 차단하기 위해 “안전 기본값 → 조건 업데이트” 흐름을 지킵니다.

### 타입 힌트 실무 규칙
- 생성 보장 위젯은 Optional을 피하고, 조건부 외부 위젯만 Optional로 남깁니다.
- 외부 유틸/CSV 결과 등 동적 타입은 `isinstance(x, dict)` 등으로 확인 후 접근합니다.
- UI 메서드 호출 전 `hasattr(..., 'configure')` 등 메서드 존재를 확인합니다.

---

추가 변경 요약 (2025-09-21 오후)
- 탭 운영: `self.tab_widget` 단일 경로로 정리, 서비스 탭 결정적 재생성.
- 리포트: `AIReportWidgetReal`로 통합, `generate_report()` 위젯 위임.
- `refresh_balance_info` 호출 제거, `update_balance_display`로 표준화.

---

## 필수 패턴 모음 (회귀 방지)

1) Optional/속성 접근은 항상 지역 변수로 가드

```python
client = getattr(self, 'binance_client', None)
if not client:
  return
ws = getattr(client, 'websocket_manager', None)
if not ws:
  return
# 이후부터 ws 사용
depth = ws.get_latest_orderbook(symbol) if hasattr(ws, 'get_latest_orderbook') else None
```

2) selected_coins는 항상 dict 정규화 후 사용

```python
normalized: list[dict[str, object]] = []
for c in selected_coins:
  if isinstance(c, str):
    normalized.append({'symbol': c})
  elif isinstance(c, dict):
    normalized.append(c)
self.selected_coins = normalized

for coin in self.selected_coins:
  c = coin if isinstance(coin, dict) else {'symbol': str(coin)}
  symbol = str(c.get('symbol', 'N/A'))
  # 안전한 .get 사용 가능
```

3) coin_symbol은 try 블록 밖에서 안전 기본값으로 초기화

```python
for coin in self.selected_coins:
  coin_symbol = 'UNKNOWN'
  try:
    coin_symbol = coin['symbol'] if isinstance(coin, dict) and 'symbol' in coin else str(coin)
    # ...
  except Exception as e:
    self.logger.error(f"[{coin_symbol}] Processing error: {e}")
```

4) UI 텍스트/위젯 업데이트는 destroy 체크 후 수행

```python
def _widget_alive(w):
  try:
    return w and getattr(w, 'winfo_exists', lambda: 0)() == 1
  except Exception:
    return False

def _safe_text_set(text_widget, value: str):
  if _widget_alive(text_widget) and hasattr(text_widget, 'configure'):
    text_widget.configure(text=value)
```

5) 분석기/트레이더 같은 코어 객체 접근

```python
analyzer = getattr(self, 'analyzer', None)
if analyzer:
  result = analyzer.analyze_symbol(symbol)
else:
  self.logger.warning('Analyzer not available')
```

6) 메서드명 통일(WebSocket)
- 구독: `subscribe_symbol(symbol)`, `unsubscribe_symbol(symbol)`
- 조회: `get_latest_ticker(symbol)`, `get_latest_orderbook(symbol)`

7) 예외 로깅에서 안전 태그 사용

```python
safe_coin_symbol = None
try:
  # 처리
  safe_coin_symbol = symbol
except Exception as e:
  tag = safe_coin_symbol if safe_coin_symbol else 'UNKNOWN'
  self.logger.error(f'[{tag}] 오류: {e}')
```

8) Fallback 접근 전 None 가드

```python
client = getattr(self, 'binance_client', None)
binance_raw_client = getattr(client, 'client', None) if client else None
if not binance_raw_client:
  return None  # 안전 종료
```

위 규칙을 어기면 PR 리뷰에서 반려됩니다. PR 전 자기점검 체크리스트를 참고하세요.
