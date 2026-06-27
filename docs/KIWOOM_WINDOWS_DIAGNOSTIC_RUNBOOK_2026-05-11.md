# 키움 OpenAPI+ Windows 진단 런북 (2026-05-11)

## 목적
이 문서는 Windows PC에서 키움 OpenAPI+ 연결 실패 원인을 빠르게 분리하기 위한 실행 절차입니다.
진단 스크립트는 scripts/verify_stock_broker_connection.py 를 사용합니다.

## 사전 확인
- 프로젝트 폴더 예시: D:/Works/noahai_client
- 필수 파일 위치: scripts/verify_stock_broker_connection.py
- 실행 환경: Windows PowerShell

## 1) 프로젝트 폴더 이동
```powershell
cd D:\Works\noahai_client
```

## 2) 가상환경 활성화
```powershell
.\.venv\Scripts\Activate.ps1
```

실행 정책 에러가 나면 현재 세션에서만 1회 허용:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 3) 키움 실연결 진단 실행

### 방법 A: 명령행 인자 직접 입력
```powershell
python .\scripts\verify_stock_broker_connection.py --broker kiwoom --api_type openapi --api_version pykiwoom --id 사용자ID --password 비밀번호 --cert_password 인증서비밀번호 --account_no 계좌번호
```

### 방법 B: 환경변수 사용 (권장)
```powershell
$env:BROKER_USER_ID="사용자ID"
$env:BROKER_PASSWORD="비밀번호"
$env:BROKER_CERT_PASSWORD="인증서비밀번호"
$env:BROKER_ACCOUNT_NO="계좌번호"
python .\scripts\verify_stock_broker_connection.py --broker kiwoom --api_type openapi --api_version pykiwoom
```

## 4) 결과 파일 확인
- 저장 폴더: data/reports
- 파일명 예시: stock_broker_verify_kiwoom_YYYYMMDD_HHMMSS.json

PowerShell에서 최신 결과 1개 확인:
```powershell
Get-ChildItem .\data\reports\stock_broker_verify_kiwoom_*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1
```

## 5) 로그/리포트에서 반드시 확인할 항목
Step 이름: 키움 런타임 진단

Step data에서 아래 키를 확인:
- control_ok
- has_OnReceiveTrData
- python_bits
- os

## 6) 원인 판정 기준
1. control_ok = false
- KHOpenAPI ActiveX 로딩 실패
- 주요 원인: OCX 등록 문제 또는 32/64비트 불일치

2. control_ok = true, has_OnReceiveTrData = false
- ActiveX는 로딩되었지만 이벤트 바인딩 실패
- 주요 원인: 런타임/스레드/패키지 조합 문제

3. 키움 런타임 진단 = OK, 이후 API 연결 단계 = FAIL
- 주요 원인: 계정정보/인증서/계좌번호/로그인 세션 문제

## 7) 실행 후 전달할 자료 (필수 3개)
1. 콘솔 출력 전체
2. JSON의 Step 0(키움 런타임 진단) 블록
3. API 연결 단계 FAIL detail 문구

---

## 실행 결과 기록 템플릿 (Windows에서 채우기)

### A. 실행 시각 / 담당자
- 실행 시각:
- 실행 PC:
- Python 버전:
- 가상환경 경로:

### B. 콘솔 출력 붙여넣기
```text
(여기에 콘솔 출력 전체 붙여넣기)
```

### C. JSON Step 0 (키움 런타임 진단)
```json
{
  "step": "키움 런타임 진단",
  "status": "",
  "detail": "",
  "data": {
    "os": "",
    "python_bits": 0,
    "control_ok": false,
    "has_OnReceiveTrData": false
  }
}
```

### D. API 연결 단계 결과
- status:
- detail:

### E. 최종 판정
- 판정 코드:
- 1차 원인:
- 다음 조치:

---

## 참고: 현재 Mac 개발 환경 사전 검증 결과
이 결과는 스크립트 자체 회귀 확인용이며, 키움 실연결 성공을 의미하지 않습니다.

- 실행 명령:
```bash
source .venv/bin/activate && pytest -q tests/test_kiwoom_backend_adapter.py tests/test_stock_integration.py -k kiwoom
```
- 결과:
```text
13 passed, 4 skipped, 60 deselected
```
