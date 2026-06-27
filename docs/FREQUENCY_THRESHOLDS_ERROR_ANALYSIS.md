# frequency_thresholds 오류 분석 및 해결 (2026-01-13)

## 문제 요약

로그에서 `frequency_thresholds 잘못된 값 감지: [0.005, 0.01, 0.02, 0.05]` 오류가 반복적으로 발생하고 있습니다.

## 원인 분석

### 1. 잘못된 설정 형식

**현재 설정 파일의 잘못된 형식**:
```json
"frequency_thresholds": [0.005, 0.01, 0.02, 0.05]
```

**올바른 형식**:
```json
"frequency_thresholds": {
  "major": [5000, 20000, 50000, 200000, 500000],
  "altcoin": [1000, 5000, 10000, 50000, 100000]
}
```

### 2. 문제점

1. **형식 오류**: 리스트가 아닌 딕셔너리 형식이어야 함
2. **값 오류**: 소수점 값이 아닌 정수 값이어야 함 (거래 빈도 카운트)
3. **길이 오류**: 4개가 아닌 5개의 값이 필요함
4. **의미 오류**: `frequency_thresholds`는 거래 빈도(횟수)를 나타내는 정수 값이어야 하는데, 소수점 값이 설정됨

### 3. 코드 동작

- `trading/evaluator.py` 1217줄에서 잘못된 형식을 감지
- 기본값으로 자동 교체하여 시스템은 정상 작동
- 하지만 **ERROR 레벨 로그가 각 코인마다 반복 출력**되어 로그가 지저분해짐

## 해결 방법

### 1. 로그 레벨 변경 및 캐싱 (완료)

- ERROR → WARNING으로 변경
- 한 번만 출력하도록 캐싱 추가 (`_warning_cache` 사용)
- 올바른 형식 안내 메시지 추가

### 2. 설정 파일 수정 (권장)

사용자의 `settings.json` 파일에서 `frequency_thresholds` 값을 올바른 형식으로 수정해야 합니다:

```json
"frequency_thresholds": {
  "major": [5000, 20000, 50000, 200000, 500000],
  "altcoin": [1000, 5000, 10000, 50000, 100000]
}
```

## 영향도

- ✅ **기능적 영향 없음**: 코드가 자동으로 기본값으로 교체하여 정상 작동
- ⚠️ **로그 품질 저하**: ERROR 로그가 반복 출력되어 실제 오류를 찾기 어려움
- ⚠️ **성능 영향 미미**: 로그 출력 오버헤드만 있음

## 수정 내용

### `trading/evaluator.py` (1217-1226줄)

**변경 전**:
```python
self.logger.error(f"[{symbol}] ❌ frequency_thresholds 잘못된 값 감지: {raw_freq_config}")
self.logger.error(f"[{symbol}] ❌ criteria 전체 내용: {criteria}")
self.logger.error(f"[{symbol}] ❌ strategy_config 전체 내용: {strategy_config}")
```

**변경 후**:
```python
warning_key = "frequency_thresholds_invalid_format"
if warning_key not in self._warning_cache:
    self.logger.warning(f"⚠️ frequency_thresholds 잘못된 형식 감지: {raw_freq_config} (딕셔너리 형식 필요, 기본값으로 교체)")
    self.logger.warning(f"⚠️ criteria 전체 내용: {criteria}")
    self.logger.warning(f"⚠️ 올바른 형식: {{'major': [5000, 20000, 50000, 200000, 500000], 'altcoin': [1000, 5000, 10000, 50000, 100000]}}")
    self._warning_cache.add(warning_key)
```

## 결론

- ✅ **해결 완료**: 로그가 한 번만 출력되도록 수정
- 📝 **추가 작업 필요**: 사용자의 `settings.json` 파일에서 `frequency_thresholds` 값을 올바른 형식으로 수정 권장

## 참고

- `frequency_thresholds`는 거래 빈도(횟수)를 나타내는 정수 값입니다
- 메이저 코인과 알트코인에 대해 각각 다른 임계값을 설정할 수 있습니다
- 5개의 값은 낮은 빈도부터 높은 빈도까지의 구간을 나타냅니다
