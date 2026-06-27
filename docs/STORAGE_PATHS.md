# 저장 경로 가이드 (v3.7.6)

본 문서는 개발/배포 환경에서 NoahAI가 사용하는 주요 저장 경로를 정리합니다. 모든 경로 처리는 `noahai_client/path_utils.py`를 통해 일관되게 관리됩니다.

## 개요
- 개발 환경: 프로젝트 내부 `data/` 폴더를 사용합니다.
- 배포 환경(PyInstaller): 사용자 `Documents/NoahAI*` 폴더를 사용합니다.
- 사용자 로그인 후에는 계정별 하위 폴더를 자동으로 만듭니다.

예시 경로(운영체제별)
- Windows: `C:\\Users\\<USER>\\Documents\\NoahAI\\<username>`
- macOS: `~/Documents/NoahAI/<username>`
- Linux: `~/Documents/NoahAI/<username>` (배포 정책에 따라 XDG 문서 경로 상이 가능)

## 핵심 경로
- 앱 데이터 디렉토리: `get_app_data_dir()`
  - 개발: `<repo>/noahai_client/data[/<username>]`
  - 배포: `~/Documents/NoahAI*[/<username>]`
- 설정 디렉토리: `get_config_dir()`
  - 개발: `data[/<username>]/config` (로그인 전에는 `data` 그대로 사용)
  - 배포: `Documents/NoahAI*[/<username>]/config`
- 로그 디렉토리/파일: `get_log_dir()`, `get_log_file_path()`
  - 경로: `…/logs/`, 파일명: `trading.log`
- 데이터베이스: `get_db_file_path()`
  - 경로: `…/trading.db`
- AI 학습 데이터: `get_ai_learning_data_path()`
  - 경로: `…/ai_learning_data.json`
- 테마 설정 파일: `get_theme_config_path()`
  - 경로: `…/config/theme_config.json` (로그인 전: 임시 경로)
- 인증/토큰 파일: `get_credentials_file_path()`, `get_token_file_path()`
  - 경로: `…/credentials.json`, `…/token.json`

## 계정별 폴더
- 로그인 성공 시 `set_current_user_account(<username>)`를 통해 계정명이 설정됩니다.
- 이후 생성되는 파일/폴더는 계정별 하위 폴더에 배치됩니다.

## 팁
- 배포 환경에서 실제 사용 경로는 `find_noahai_dir()`가 `~/Documents` 내 `NoahAI*` 폴더를 탐색/생성하여 결정합니다.
- 로그/애널리틱스 보존을 위해 `Documents/NoahAI*/logs`와 `Documents/NoahAI*/analytics`를 백업 대상으로 포함하세요.

## 관련 코드
- 파일: `noahai_client/path_utils.py`
- 주요 함수: `get_app_data_dir`, `get_config_dir`, `get_log_dir`, `get_db_file_path`, `get_ai_learning_data_path`, `get_theme_config_path`, `get_token_file_path`, `get_credentials_file_path`, `find_noahai_dir`, `set_current_user_account`
