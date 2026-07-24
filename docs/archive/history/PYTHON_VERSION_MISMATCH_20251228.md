# 📊 Python 버전 불일치 문제 해결 - 2025-12-28 (이력 보관)

## 🔍 문제 원인

맥 환경에서 여러 Python 버전이 설치되어 있고, 패키지가 설치된 Python과 실행하는 Python이 다릅니다.

### 현재 상황

1. **`python` 명령어**: Python 3.12.1 (`/opt/local/bin/python`)
2. **`python3` 명령어**: Python 3.11.12 (`/opt/homebrew/bin/python3.11`)
3. **패키지 설치 위치**: Python 3.11에 설치됨 (`python3 -m pip`로 설치)
4. **실행 시 사용**: Python 3.12로 실행 (`python main.py`)

**결과**: Python 3.12에는 패키지가 없어서 `ModuleNotFoundError` 발생

---

## ✅ 해결 방법

### 방법 1: python3로 실행 (가장 간단)

```bash
python3 main.py
```

**이유**: 패키지가 Python 3.11에 설치되어 있으므로, 같은 버전으로 실행

### 방법 2: Python 3.12에도 패키지 설치

```bash
python -m pip install -r requirements.txt
```

**이유**: 실행하는 Python 버전(3.12)에도 패키지 설치

### 방법 3: 가상환경 사용 (권장)

```bash
# 가상환경 생성 (Python 3.11 사용)
python3 -m venv venv

# 가상환경 활성화
source venv/bin/activate

# 패키지 설치
pip install -r requirements.txt

# 실행
python main.py  # 가상환경 내에서는 python이 3.11을 가리킴
```

---

## 🔧 확인 방법

### 현재 Python 버전 확인

```bash
python --version   # 실행 시 사용되는 버전
python3 --version # python3 명령어 버전
```

### 패키지 설치 위치 확인

```bash
python -m pip list | grep customtkinter   # Python 3.12에 설치 여부
python3 -m pip list | grep customtkinter  # Python 3.11에 설치 여부
```

### Python 경로 확인

```bash
python -c "import sys; print(sys.executable)"
python3 -c "import sys; print(sys.executable)"
```

---

## 💡 권장 사항

### 1. 가상환경 사용 (가장 안전)

- 프로젝트별로 독립적인 Python 환경 유지
- 버전 충돌 방지
- 배포 시 일관성 보장

### 2. python3 명령어 사용

- 맥에서는 `python3`가 명시적으로 Python 3를 가리킴
- `python`은 시스템에 따라 다를 수 있음

### 3. shebang 확인

- 스크립트 파일의 첫 줄에 `#!/usr/bin/env python3` 사용
- 명시적으로 Python 3 사용 보장

---

## 📋 결론

**문제**: Python 버전 불일치로 인한 모듈 찾기 실패  
**원인**: 패키지는 Python 3.11에, 실행은 Python 3.12로  
**해결**: `python3 main.py`로 실행하거나, Python 3.12에도 패키지 설치

---

**작성일**: 2025-12-28  
**상태**: 문제 원인 파악, 해결 방법 제시
