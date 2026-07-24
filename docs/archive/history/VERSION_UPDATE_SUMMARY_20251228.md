# 📋 버전 3.8.9.9 업데이트 요약 (이력 보관)

## 📅 업데이트 날짜: 2025-12-28

## 🔧 주요 변경사항

### 1. TP/SL 가격 계산 오류 수정 (-4006 오류)

**문제:**
- RSRUSDT, RVNUSDT 등 저가 코인에서 "Stop price less than zero" 오류 발생
- TP/SL 가격 계산 시 스냅 로직에서 음수 또는 0으로 반올림되는 문제

**해결:**
- TP/SL 가격 계산 후 스냅 로직 이전에 유효성 검증 추가
- SHORT/LONG 포지션별로 올바른 TP/SL 관계 검증
- 0 이하 값 방지 및 기본값 적용

**수정 파일:**
- `trading/trader.py` (2561-2587줄)

### 2. 포지션 개수 제한 불일치 수정

**문제:**
- 설정 파일(max_positions: 3)과 코드(하드코딩된 5) 불일치
- 프로그램 재시작 후 포지션 복구 시 4-5개 포지션이 생성됨

**해결:**
- `trader.py`의 `max_positions` 하드코딩값(5)을 설정값(3)으로 변경
- `unified_trader.py`의 하드코딩된 5 값도 설정값 사용으로 변경

**수정 파일:**
- `trading/trader.py` (168줄)
- `trading/unified_trader.py` (3602줄)

### 3. AI 어시스턴트 거래소 연결 상태 확인 개선

**문제:**
- 거래소가 연결되었음에도 "거래소 연결 불가" 같은 잘못된 답변
- `validate_exchange_connection()`에서 BinanceClient의 `is_connected` 속성 확인 부족

**해결:**
- `ExchangeManager.validate_exchange_connection()`에서 BinanceClient의 `is_connected` 속성 확인
- `is_connected=True`이면 연결 상태로 간주

**수정 파일:**
- `trading/exchange_manager.py` (655-696줄)

### 4. AI 프롬프트 개선

**문제:**
- AI 프롬프트에 "거래소 연결 상태와 무관하게 설정 변경 가능"이라고 명시
- 하지만 컨텍스트에 "거래소 연결 상태: 연결 안됨"이 포함되면 AI가 혼란하여 잘못 답변

**해결:**
- 설정 변경과 거래소 연결의 관계를 명확히 설명
- 컨텍스트에 "설정 변경은 거래소 연결 상태와 무관하게 가능" 명시적 안내 추가
- "거래소 연결이 필요합니다"라는 잘못된 답변을 방지하는 규칙 추가

**수정 파일:**
- `ui/widgets/ai_assistant_widget.py` (567-602줄, 970-974줄)

## 📝 관련 문서

- **버그 수정 보고서**: `docs/BUG_FIX_REPORT_20251228.md`
- **AI 어시스턴트 문제 분석**: `docs/AI_ASSISTANT_ISSUES_20251228.md`

## ✅ 업데이트 완료 파일

1. ✅ `ui/dashboard_modern.py` - 버전 3.8.9.9로 업데이트
2. ✅ `ui/widgets/user_manual_widget.py` - 버전 3.8.9.9로 업데이트 및 업데이트 탭 내용 추가
3. ✅ `docs/USER_GUIDE.md` - 버전 3.8.9.9로 업데이트 및 주요 변경사항 추가
4. ✅ `docs/CHANGELOG.md` - v3.8.9.9 업데이트 내용 추가
