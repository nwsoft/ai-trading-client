# 계정 관리 및 보안 시스템

## 🔐 사용자 인증 시스템

### 📁 계정 정보 파일 구조

#### 토큰 파일 (`token.json`)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "timestamp": "2025-09-03 19:02:39.873798",
  "user_id": "nwsoft",
  "session_id": "796f457a-1563-453d-9b9f-8921e5cb285e",
  "email": "nwsoft@hotmail.com",
  "token_type": "bearer"
}
```

#### 자격 증명 파일 (`credentials.json`)
```json
{
  "username": "사용자명",
  "password": "암호화된_비밀번호",
  "remember": true
}
```

### 📂 파일 저장 위치

#### 개발 환경
- `noahai_client/data/token.json`
- `noahai_client/data/credentials.json`

#### 배포 환경 (PyInstaller)
- `~/Documents/NoahAI/token.json`
- `~/Documents/NoahAI/credentials.json`
- `~/Documents/NoahAI2/token.json` (다중 계정)
- `~/Documents/NoahAI3/token.json` (다중 계정)

## 🛡️ 중복 실행 방지 시스템

### 🔄 UserStatusManager 클래스

#### 주요 기능
- **중복 실행 감지**: 동일 계정으로 다중 로그인 차단
- **서버 상태 체크**: 10분마다 서버에서 사용자 상태 확인
- **자동 종료**: 중복 감지 시 관련 프로세스 정리 후 앱 종료

#### 상태 체크 프로세스
```python
def check_user_status(self) -> bool:
    # 1. 토큰 파일에서 사용자 정보 읽기
    with open(self.env_file, 'r', encoding='utf-8') as f:
        token_data = json.load(f)
    
    user_id = token_data.get('user_id')
    session_id = token_data.get('session_id')
    
    # 2. 서버에 상태 체크 요청
    response = requests.post(
        f"{self.server_url}/auth/check_status",
        json={"id": user_id, "session_id": session_id},
        timeout=10
    )
    
    # 3. 서버 응답 확인
    if not data.get("is_active", False) or data.get("force_quit", False):
        return False  # 앱 종료 필요
    
    return True  # 정상 상태
```

### ⚡ 자동 종료 프로세스

#### 1. 프로세스 정리 (`cleanup_processes()`)
```python
def cleanup_processes(self):
    # Noah AI Client 관련 프로세스 종료
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        if ('python' in proc.info['name'].lower() and 
            ('main.py' in process_path or 'aiautotrade' in process_path)):
            proc.kill()  # 관련 프로세스 종료
```

#### 2. 파일 정리 (`cleanup_files()`)
```python
def cleanup_files(self):
    # 임시 파일 및 로그 정리
    # 데이터베이스 백업
    # 설정 파일 보존
```

#### 3. 강제 종료 (`cleanup_and_exit()`)
```python
def cleanup_and_exit(self):
    self.is_running = False
    self.cleanup_processes()
    self.cleanup_files()
    app.quit()  # PyQt5 애플리케이션 종료
    os._exit(0)  # 강제 종료
```

## 🌐 백엔드 서버 통신

### 📡 서버 API 엔드포인트

#### 기본 서버 URL
- **프로덕션**: `https://daltrading.net`
- **개발**: `http://localhost:8000`

#### 주요 API
- **로그인**: `POST /auth/api_login`
- **상태 체크**: `POST /auth/check_status`
- **KPI 업로드**: `POST /auth/kpi/event`
- **KPI 기준 조회**: `GET /auth/kpi/catalog`
- **신호 수신**: `GET /api/signals`

### 📈 클라이언트 KPI 전송 범위

현재 클라이언트가 서버로 보내는 항목:

- 로그인 성공/실패 이벤트
- AI 리포트 생성 성공/실패 이벤트
- 거래 주문 성공/실패 이벤트 (crypto/stock/etf)
- 학습 데이터 기록 성공/실패 이벤트
- 리포트 파일 저장 성공/실패 이벤트

서버 기준(화이트리스트)으로 허용된 `event_type`만 수집되며,
카테고리/자산군/상태가 기준과 다르면 400 오류로 거절됩니다.

학습 KPI 기준(`learning_data_recorded`):
- `category=learning`, `asset_class=crypto`, `status in {success, failed}`
- `status=success`일 때 `metric_value` 필수 (신뢰도, 0.0~1.0)
- `metadata.exchange` 필수

현재 로컬에만 저장되는 항목:

- 상세 로그 본문
- AI 학습 데이터 파일
- 일/주/월 리포트 파일

즉, 운영 서버에는 원문 데이터가 아니라 집계 가능한 KPI 이벤트만 전송됩니다.

### 🔄 상태 체크 응답

#### 정상 상태
```json
{
  "is_active": true,
  "force_quit": false,
  "message": "정상 상태"
}
```

#### 중복 로그인 감지
```json
{
  "is_active": false,
  "force_quit": true,
  "message": "다른 곳에서 로그인되었습니다. 프로그램을 종료합니다."
}
```

#### 계정 비활성화
```json
{
  "is_active": false,
  "force_quit": true,
  "message": "계정이 비활성화되었습니다."
}
```

## 🔧 대시보드 통합

### 📊 상태 관리자 초기화
```python
# dashboard.py에서 초기화
if UserStatusManager and get_status_manager:
    self.status_manager = get_status_manager(self.backend_api, self.settings)
    
    # 5초 지연 후 상태 체크 시작
    self.status_init_timer = QTimer()
    self.status_init_timer.singleShot(5000, self.start_user_status_monitoring)
```

### ⏰ 상태 모니터링 시작
```python
def start_user_status_monitoring(self):
    if self.status_manager:
        self.status_manager.start_status_checker()
        print("✅ 사용자 상태 모니터링 시작")
```

## 🚨 보안 고려사항

### 🔐 API 키 보안
- **암호화 저장**: API 키는 암호화되어 저장
- **메모리 보호**: 사용 후 메모리에서 즉시 제거
- **접근 제한**: 필요한 모듈에서만 접근 가능

### 🛡️ 토큰 관리
- **자동 갱신**: 토큰 만료 시 자동 갱신
- **세션 관리**: 세션 ID 기반 상태 추적
- **로그아웃**: 앱 종료 시 서버에 로그아웃 알림

### 🔒 네트워크 보안
- **HTTPS 통신**: 모든 서버 통신은 HTTPS 사용
- **타임아웃 설정**: 네트워크 타임아웃으로 무한 대기 방지
- **재시도 로직**: 네트워크 오류 시 자동 재시도

## 📋 문제 해결

### ❌ 일반적인 문제

#### 1. 토큰 파일을 찾을 수 없음
```
❌ 토큰 파일을 찾을 수 없습니다: ~/Documents/NoahAI/token.json
```
**해결방법**: 로그인을 다시 시도하여 토큰 파일 재생성

#### 2. 서버 연결 실패
```
❌ 서버 응답 오류: 500
```
**해결방법**: 네트워크 연결 확인 및 서버 상태 점검

#### 3. 중복 실행 감지
```
⚠️ 사용자 계정이 비활성화되었거나 다른 곳에서 로그인되었습니다.
```
**해결방법**: 다른 곳에서 실행 중인 앱 종료 후 재시작

### 🔧 디버깅 정보

#### 로그 파일 위치
- `data/logs/trading.log`: 거래 관련 로그
- `data/logs/status.log`: 상태 관리 로그

#### 상태 확인 명령어
```python
# 토큰 파일 확인
import json
with open('data/token.json', 'r') as f:
    token_data = json.load(f)
    print(f"User ID: {token_data.get('user_id')}")
    print(f"Session ID: {token_data.get('session_id')}")
```

## 📈 모니터링 및 알림

### 📊 상태 모니터링
- **실시간 상태**: 대시보드에서 연결 상태 표시
- **로그 추적**: 모든 상태 변경 사항 로그 기록
- **알림 시스템**: 중요한 상태 변경 시 사용자 알림

### 🔔 알림 유형
- **연결 성공**: 서버 연결 및 인증 성공
- **연결 실패**: 네트워크 오류 또는 인증 실패
- **중복 감지**: 다른 곳에서 로그인 감지
- **계정 비활성화**: 서버에서 계정 비활성화
