# 설치 및 설정 가이드 (CustomTkinter 전용)

## 📋 시스템 요구사항

### 운영체제
- **Windows**: Windows 10 이상
- **macOS**: macOS 10.14 이상
- **Linux**: Ubuntu 18.04 이상

### 하드웨어
- **RAM**: 최소 4GB (권장 8GB)
- **저장공간**: 최소 2GB 여유 공간
- **네트워크**: 안정적인 인터넷 연결

## 🚀 설치 방법

### 방법 1: 실행 파일 사용 (권장)

#### Windows
1. **AITrading.exe** 다운로드
2. 실행 파일을 원하는 위치에 저장
3. 더블클릭하여 실행
4. 첫 실행 시 필요한 라이브러리 자동 설치

#### macOS
1. **AITrading.app** 다운로드
2. Applications 폴더로 이동
3. 더블클릭하여 실행
4. 보안 설정에서 "열기" 허용

### 방법 2: 소스 코드에서 실행 (개발용)

#### 1. Python 설치
```bash
# Python 3.11 이상 권장 (macOS는 시스템 Tk 포함 빌드 사용 권장)
python --version
```

#### 2. 프로젝트 다운로드
```bash
git clone [repository-url]
cd noahai_client
```

#### 3. 의존성 설치
```bash
# Windows
pip install -r requirements_windows.txt

# Linux/macOS
pip install -r requirements.txt
```

#### 4. 실행
```bash
# macOS/Linux (권장)
python3 main.py

# Windows
python main.py
```

실행 팁 (macOS)
- 기본 쉘: zsh (터미널/VS Code에서 동일 버전 파이썬 사용 권장)
- 시스템 파이썬(Tk 포함) 사용을 권장합니다. Homebrew Python은 Tk가 없을 수 있습니다.
- 한글/유니코드 경로에서도 동작하도록 경로 처리를 보강했습니다.

실행 실패 시(Exit Code 1)
- 터미널에 “===== 진단 정보 =====”와 함께 CWD, Python 경로, 버전, Traceback이 출력됩니다.
- 해당 로그를 TROUBLESHOOTING.md 지침에 따라 확인하세요.

## ⚙️ 초기 설정

### 1. 첫 실행
1. **AITrading.exe** 실행
2. 로그인 화면에서 계정 정보 입력
3. 로그인 성공 시 대시보드 표시

### 2. 거래소 설정
1. **환경설정** 버튼 클릭
2. **거래소 선택** 탭에서 사용할 거래소 선택
3. **거래소 API** 탭에서 API 키 입력
4. **저장** 버튼 클릭

### 3. 연결 테스트
1. 대시보드에서 **"잔고 새로고침"** 버튼 클릭
2. 연결 성공 시 계정 정보 표시 확인

## 🔧 고급 설정

### 환경 변수 설정
```bash
# Windows
set BINANCE_API_KEY=your_api_key
set BINANCE_SECRET_KEY=your_secret_key

# Linux/macOS
export BINANCE_API_KEY=your_api_key
export BINANCE_SECRET_KEY=your_secret_key
```

### 설정 파일 위치
- **Windows**: `%USERPROFILE%\Documents\NoahAI\`
- **macOS**: `~/Documents/NoahAI/`
- **Linux**: `~/Documents/NoahAI/`

모든 런타임 데이터(data/logs/analytics)는 사용자 Documents 하위에 생성됩니다. 저장 위치는 `path_utils.py`가 관리합니다.

## 🛠️ 빌드 가이드 (요약)

### 개발자용 빌드

#### 1. PyInstaller 설치
```bash
pip install pyinstaller
```

#### 2. 빌드 실행
```bash
# Windows
python build_safe.py --platform windows --gate-profile release
```

`aiautotrade.spec`과 임시 `aiautotrade_safe.spec`은 모두 `build_safe.py`가 같은 정책으로 생성합니다. 직접 PyInstaller를 호출하지 마세요.

#### 3. 실행 파일 생성
- **Windows**: `dist/AITrading.exe`
- **macOS**: `dist/AITrading.app`
- **Linux**: `dist/AITrading`

### 빌드 옵션
```bash
# 디버그 모드
python build_safe.py --debug

# 릴리즈 모드
python build_safe.py --release
```

## 📁 파일 구조

### 설치 후 생성되는 폴더
```
Documents/NoahAI/
├── settings.json          # 설정 파일
├── token.json            # 인증 토큰
├── trading.db            # 거래 데이터베이스
└── logs/                 # 로그 파일
    ├── trading.log       # 거래 로그
    └── error.log         # 오류 로그
```

### 다중 계정 지원
```
Documents/
├── NoahAI/              # 첫 번째 계정
├── NoahAI2/             # 두 번째 계정
└── NoahAI3/             # 세 번째 계정
```

## 🔄 업데이트

### 자동 업데이트
- 앱 시작 시 자동으로 업데이트 확인
- 업데이트 가능 시 알림 표시
- 사용자 승인 후 자동 다운로드 및 설치

### 수동 업데이트
1. 최신 버전 다운로드
2. 기존 파일 덮어쓰기
3. 앱 재시작

## 🚨 문제 해결 (발췌)

### 일반적인 문제

#### 1. 실행 파일/소스가 실행되지 않음
**해결방법**:
- Windows Defender 예외 처리 / macOS 파일 및 폴더 접근 권한 허용
- 관리자 권한(최초 1회) 또는 사용자 권한으로 재실행
- VS Code/터미널에서 동일한 Python 인터프리터 사용 확인
- TROUBLESHOOTING.md “직접 실행 실패(Exit Code 1)” 섹션 확인

#### 2. Python 모듈 오류
**해결방법**:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### 3. 네트워크 연결 오류
**해결방법**:
- 방화벽 설정 확인
- 프록시 설정 확인
- VPN 연결 상태 확인

### 로그 파일 확인
- **위치**: `Documents/NoahAI/logs/`
- **파일**: `trading.log`, `error.log`
- **내용**: 오류 메시지 및 디버깅 정보

## 📞 지원

### 문제 신고
1. 로그 파일 수집
2. 오류 메시지 스크린샷
3. 시스템 정보 제공

### 문의사항
- **이메일**: support@noahai.com
- **GitHub**: [Issues 페이지]
- **커뮤니티**: [커뮤니티 링크]
