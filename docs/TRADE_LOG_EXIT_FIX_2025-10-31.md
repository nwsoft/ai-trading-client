# trade_log 청산 인식/저장 안정화 패치 - 2025-10-31

본 문서는 대시보드 통계가 0으로 표시되는 문제의 근본 원인(청산 정보 미저장/오저장)을 해결하기 위해 적용한 코드 변경 사항을 기록합니다. 변경 이유, 영향 범위, 롤백 방법, 검증 방법을 포함합니다.

## 요약

- 문제: 진입 로그는 저장되지만 청산 시점 데이터(exit_price, pnl, exit_time 등)가 저장되지 않거나 0으로 저장되어 대시보드 집계가 0으로 보임.
- 원인:
  - (1) 실제 체결 조회 시 “반대 방향” 체결만 걸러야 하는데 느슨한 필터로 인해 정확한 청산 평균가·수수료·수량 산출 실패 가능성.
  - (2) DB UPDATE가 `symbol + entry_time` 정확 일치 조건으로만 동작하여, 정밀도/타임존 차이 등으로 미스매치 시 통째로 실패.
- 조치:
  - 반대 방향 체결만 집계하도록 필터 강화
  - UPDATE 실패 시 동일 심볼(+가능하면 side) 기준 “가장 최근 미종료 1건” 폴백 업데이트 추가
  - 디버그 로그 보강(폴백 시도, 최근 3건 스냅샷, 성공/실패 로그)

## 변경 파일

- trading/recorder.py

## 상세 변경 내용

### 1) 실제 체결 조회 필터 강화

- 함수 시그니처 변경:
  - 이전: `get_actual_trade_info(symbol: str, entry_time: datetime)`
  - 변경: `get_actual_trade_info(symbol: str, entry_time: datetime, side: str)`
- 로직 변경:
  - 엔트리 시간 이후 체결 중 “반대 방향(side)” 체결만 누적
    - LONG → SELL 체결만, SHORT → BUY 체결만
  - 가중 평균 청산가, 총 수수료, 총 체결수량을 계산 후 반환
- 호출부(`log_trade_exit`)도 side를 전달하도록 수정

### 2) UPDATE 매칭 안정성 개선 (정확 매칭 실패 시 폴백)

- 함수 시그니처 변경:
  - 이전: `update_trade_on_exit(symbol, entry_time, *, exit_price, pnl, pnl_percent, fees, slippage, reason)`
  - 변경: `update_trade_on_exit(symbol, entry_time, *, exit_price, pnl, pnl_percent, fees, slippage, reason, side: Optional[str] = None)`
- 로직 변경:
  - 1차: `WHERE symbol=? AND entry_time=? AND exit_time IS NULL`로 정확 매칭 시도
  - 2차 폴백: rowcount=0이면 동일 심볼(+가능하면 side) 기준 “가장 최근 미종료 거래 1건”을 찾아 UPDATE
  - 디버깅 보강: 최근 거래 상위 3건(id, symbol, side, entry_time, exit_time) 스냅샷 로깅

### 3) log_trade_exit 연계 수정

- `get_actual_trade_info(..., side)`로 변경된 시그니처 반영
- `update_trade_on_exit(..., side=...)`로 폴백에 필요한 side 전달

## 기대 효과 (Before → After)

- Before:
  - 청산 로그 자체가 드물고, 저장되더라도 exit_price/pnl/exit_time이 0/None으로 남는 사례
  - 대시보드 통계(승률/손익)가 0 표시
- After:
  - 반대 방향 체결만 집계 → 평균 청산가/수수료/수량 계산 정확도 향상
  - UPDATE 폴백으로 entry_time 미스매치 시에도 저장 성공률 상승
  - 로그 상 “거래 청산 로그 업데이트 완료” 또는 “폴백 업데이트 성공” 확인 가능

## 위험도/영향 범위

- 함수 시그니처 변경은 내부 파일(trading/recorder.py) 내에서만 사용되며, 외부 공개 API 변경 없음
- DB 스키마 변경 없음(업데이트 로직만 변경)
- 실거래 환경에서 정상 동작하나, 폴백이 “가장 최근 미종료 1건”을 집는 특성상 동시 다중 포지션(같은 심볼 다중 엔트리) 케이스에서는 정확 매칭이 더 안전합니다(향후 개선안 참조)

## 롤백 방법

- 파일 되돌리기:
  - `trading/recorder.py`의 아래 변경을 되돌립니다.
    - `get_actual_trade_info` 시그니처/내부 반대 방향 필터 제거
    - `update_trade_on_exit`의 side 파라미터 및 폴백 로직 제거
    - `log_trade_exit`에서 side 인자 전달 제거
- Git 사용 시:

```powershell
# 마지막 커밋 전체 롤백 (commit hash 치환)
git revert <commit_sha>
# 또는 특정 파일만 되돌리기
git checkout <commit_sha> -- trading/recorder.py
```

## 검증 방법

- 실행 로그 확인
  - 청산 시점에 아래 로그가 보이는지 확인
    - “거래 청산 로그 업데이트 완료: {symbol} ...” 또는
    - “✅ 폴백 업데이트 성공: {symbol} (id=...)”
  - 실패 시 “업데이트할 거래를 찾을 수 없음 … (정확 매칭 실패, 폴백 시도)”와 함께 최근 3건 스냅샷 로그가 남습니다.

- DB 확인 (간단 점검)

```powershell
# 파워쉘에서 Python으로 최근 청산건 확인 (옵션)
python - << 'PY'
import sqlite3, json
conn = sqlite3.connect('data/nwsoft/test_user/trading_stats.db')
cur = conn.cursor()
cur.execute("SELECT symbol, entry_price, exit_price, pnl, pnl_percent, entry_time, exit_time FROM trade_log WHERE exit_time IS NOT NULL ORDER BY exit_time DESC LIMIT 5")
for r in cur.fetchall():
    print(r)
PY
```

- 대시보드 집계 확인
  - 대시보드에서 총 거래 수/승률/누적 손익이 0이 아닌 값으로 갱신되는지 확인

## 향후 권장 개선안

- 엔트리 삽입 시 반환된 trade_log.id를 포지션 컨텍스트에 저장하고, 청산 시 id 기준으로 직접 UPDATE
  - entry_time 정밀도/타임존 이슈를 원천 제거
- 수수료/슬리피지 실제값 추가 수집(현재 슬리피지는 추정치)
- 포지션 0 전환(완전 청산) 이벤트 워처 추가: TP/SL 자동청산 등도 `log_trade_exit()`가 반드시 호출되도록 보강

---
작성일: 2025-10-31
담당: Recorder/거래 로그 경로 안정화 패치
