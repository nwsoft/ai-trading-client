# 📊 맥 환경 실행 오류 분석 - 2025-12-28

## 📋 목적

맥 환경에서 프로그램 실행 시 발생한 에러의 원인을 분석하고 해결 방법을 제시합니다.

---

## 🔍 에러 분석

### 에러 1: `ModuleNotFoundError: No module named 'customtkinter'`

**발생 위치**: `ui/login_modern.py` 8줄

**원인**:
- 맥 환경에서 Python 패키지가 설치되지 않음
- `requirements.txt`에 명시된 패키지들이 설치되지 않은 상태

**해결 방법**:
```bash
pip install -r requirements.txt
```

### 에러 2: `No module named 'requests'`

**발생 위치**: `utils/time_sync.py` 58줄

**원인**:
- `requests` 패키지가 설치되지 않음
- 시간 동기화 확인 시 바이낸스 서버 시간을 조회하기 위해 `requests` 모듈 사용

**해결 방법**:
```bash
pip install requests
# 또는
pip install -r requirements.txt
```

### 경고: 시간 동기화 관련

**발생 위치**: `utils/time_sync.py` 19-21줄

**원인**:
- 맥 환경에서는 Windows 시간 동기화 기능을 지원하지 않음
- `sync_windows_time()` 함수가 Windows 전용으로 설계됨

**현재 동작**:
- 맥에서는 "Windows가 아닌 환경에서는 시간 동기화를 지원하지 않습니다" 경고만 출력
- 프로그램은 계속 진행됨 (치명적 에러 아님)

---

## 🔬 왜 지금까지 나오지 않았는가?

### 1. 윈도우 환경에서는 문제 없음

**이유**:
- 윈도우 클라이언트에서는 `requirements.txt`가 이미 설치되어 있음
- PyInstaller로 빌드된 실행 파일에는 모든 의존성이 포함됨
- 가상환경이 설정되어 있거나 시스템 Python에 패키지가 설치됨

### 2. 맥 환경에서 처음 실행

**이유**:
- 맥 환경에서 처음 실행하거나
- 가상환경이 활성화되지 않았거나
- `requirements.txt`가 설치되지 않은 상태

### 3. 코드 수정과 무관

**이유**:
- 이 에러는 코드 수정과 무관함
- 환경 설정 문제임
- `time_sync.py`는 기존부터 존재했지만, 맥에서 처음 실행하면서 발견됨

---

## ✅ 해결 방법

### 방법 1: requirements.txt 설치 (권장)

```bash
# 프로젝트 루트 디렉토리에서
pip install -r requirements.txt
```

**설치되는 주요 패키지**:
- `customtkinter>=5.2.0` (UI 라이브러리)
- `requests==2.31.0` (HTTP 요청)
- `python-binance==1.0.19` (바이낸스 API)
- 기타 의존성들

### 방법 2: 가상환경 사용 (권장)

```bash
# 가상환경 생성
python3 -m venv venv

# 가상환경 활성화 (맥)
source venv/bin/activate

# 패키지 설치
pip install -r requirements.txt

# 프로그램 실행
python main.py
```

### 방법 3: 개별 패키지 설치

```bash
pip install customtkinter requests
```

---

## 🔧 개선 제안

### 1. 맥 환경에서 시간 동기화 처리 개선

**현재 문제**:
- 맥에서는 Windows 시간 동기화를 지원하지 않음
- `requests` 모듈이 없으면 시간 동기화 확인이 실패함

**개선 방안**:
- 맥 환경에서는 시간 동기화 확인을 건너뛰거나
- `requests` 모듈이 없을 때 graceful하게 처리

### 2. 의존성 체크 추가

**개선 방안**:
- 프로그램 시작 시 필수 패키지 체크
- 누락된 패키지가 있으면 명확한 안내 메시지 출력

---

## 📋 결론

### 문제의 원인

1. **환경 설정 문제**: 맥 환경에서 Python 패키지가 설치되지 않음
2. **플랫폼 차이**: Windows 전용 기능(시간 동기화)이 맥에서 실행됨
3. **의존성 누락**: `requirements.txt`가 설치되지 않음

### 해결 방법

1. **즉시 해결**: `pip install -r requirements.txt` 실행
2. **장기적 해결**: 가상환경 사용 및 의존성 관리

### 코드 수정 필요성

- **없음**: 이 문제는 코드 수정과 무관한 환경 설정 문제
- **개선 가능**: 맥 환경에서 시간 동기화 처리 개선 (선택사항)

---

**작성일**: 2025-12-28  
**상태**: 분석 완료, 해결 방법 제시
