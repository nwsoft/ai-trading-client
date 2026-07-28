# 배포 체크리스트 (2026-07-28 · v3.9.0.3 후보 기준)

운영 환경 배포 전/후 점검해야 할 항목을 정리했습니다. 이 문서는 `noahai_client/build_safe.py`의 현재 PyInstaller 스펙을 기준으로 작성되었습니다.

## 운영 정책 (2026-06-26 반영)

- SaaS 구축 완료 전까지 배포 지원 범위는 Windows 전용으로 고정한다.
- 개발 작업은 macOS/Linux에서도 가능하나, 최종 고객 배포 산출물은 Windows 빌드에서 생성한 `AITrading.exe`만 사용한다.
- GitHub Release 업로드 기준 산출물도 Windows 자산(`AITrading.exe`, `version.txt`, `release_notes.md`, `release-manifest.json`)으로 통일한다.

## 0) 패키징 스펙 요약(build_safe.py)
- **실제 배포 스펙**: `build_safe.py`가 런타임에 `aiautotrade_safe.spec`을 동적 생성하여 빌드. `aiautotrade.spec`은 참고용.
- UI 정책: CustomTkinter-only. Windows 빌드에서만 PyQt5 포함 허용(키움증권 OpenAPI+ 필수)
- datas 포함
  - config: `config/settings_template.json`, `config/token_template.json`, `config/theme_config.json`
  - 코드/리소스: `trading/`, `trading/ai/`, `trading/exchanges/`, `trading/exchange_manager.py`, `trading/api_signal_manager.py`, `api/`
  - 루트 파일: `strategy_customizer.py`, `ai_chat_strategy.py`, `web_deployment_analysis.py`, `user_status_manager.py`, `path_utils.py`, `README.md`, `requirements*.txt`, `icon.ico`, `icon.png`
  - 포함 안 함: data 폴더(런타임에 `path_utils`가 사용자 Documents 하위에 생성)
- hiddenimports(발췌)
  - GUI: `tkinter`, `tkinter.ttk`, `tkinter.messagebox`, `customtkinter`
  - 거래/네트워크: `websockets`, `websocket`, `websocket_client`, `binance`, `ccxt`, `ccxt.binance`, `ccxt.upbit`, `ccxt.bithumb`
  - 증권 어댑터(hidden import): `trading.exchanges.exchange_factory`, `trading.exchanges.adapters.kiwoom_stock_adapter`, `trading.exchanges.adapters.stock_mock_adapter`, `trading.exchanges.adapters.shinhan_stock_adapter`, `trading.exchanges.adapters.mirae_asset_stock_adapter`, `trading.exchanges.adapters.korea_investment_stock_adapter` (실브로커 4개 + mock 1개)
  - 키움 전용(Windows 빌드 시 자동 추가): `pykiwoom`, `pykiwoom.kiwoom`, `PyQt5`, `PyQt5.QtWidgets`, `PyQt5.QtCore`, `PyQt5.QtGui`, `PyQt5.QAxContainer`
  - 유틸: `openai`, `numpy`, `pandas`, `loguru`, `aiohttp`, `ujson`, `dateparser`, `colorama`, `dotenv`, `psutil` 등
  - 플랫폼 주의: `win32_setctime`는 Windows 전용. macOS/Linux 빌드 시 제거/무시 필요
- excludes
  - macOS/Linux: `PyQt5`, `PySide6`, `qt4`, `qt6`, `wx`, `gtk` 등
  - Windows: `PySide6`, `qt4`, `qt6`, `wx`, `gtk` (PyQt5는 키움 때문에 제외하지 않음)
  - 과학/노트북 대형 패키지: `matplotlib`, `scipy`, `scikit-learn`, `tensorflow`, `torch`, `jupyter`, `ipython`, `pytest`, `unittest` 등

권장 Python 버전: 3.11+ (개발/테스트는 3.11-3.13에서 확인)
키움 OpenAPI+ 실연동 권장: Windows Python 3.11.x 32bit (COM/ActiveX bitness 일치)

## 1) 필수 설정
- OpenAI API Key 설정 및 테스트
- 거래소 API Key/Secret(및 OKX Passphrase) 입력 및 연결 테스트
- enabled_exchanges/selected_exchange 확인
- default_margin_type (ISOLATED/CROSS) 설정 확인
- 증권사 설정 저장 검증
  - `stock_broker_configs.shinhan.app_key/app_secret` 값 반영 확인
  - `stock_broker_configs.miraeAsset.app_key/app_secret` 값 반영 확인
- 저장 후 자동 1차 진단 옵션 확인
  - `ui_settings.auto_show_stock_broker_diagnosis_after_save` 기본값 `true`
  - 위험 경고 시 `연결 실패 5분 점검 가이드 열기`로 상세 체크리스트 실행

## 1-A) 사용자 동선/매뉴얼 동기화 (배포 게이트)
- 새 EXE를 캐시의 `AITrading.new.exe`가 아니라 정상 설치 경로에서 실행하고 자동 업데이트 진단의 설치 대상도 같은 정상 EXE인지 확인
- `release-manifest.json`의 EXE SHA-256이 실제 파일과 일치하고, Windows `Get-AuthenticodeSignature`가 `Valid`이며 서명자 인증서가 존재하지 않으면 업로드하지 않음
- 열린 포지션/주문/주문 제출 중 기본 연기, 유지 모드 TP·SL 전수 확인, 청산 모드 실제 0건 확인을 각각 검증
- 종료·DB/log flush 실패 시 적용 금지와 `auto_update_transaction.json`의 단계·이전/새 버전·SHA·대상/백업 경로 기록 확인
- 재시작 후 버전·DB quick_check·API 읽기·포지션 복구 health check, 실패 자동 복원, 성공 알림, 사용자 재개 전 주문 잠금 확인
- 24~72시간 실행에서 숨은 AI 학습 탭이 `initial_defer_until_visible`을 반복 기록하지 않고 `ui_perf_metrics.jsonl`이 20MB×3 회전을 넘지 않는지 확인
- 숨은 금융 인텔리전스 탭에서 작업 없는 50ms 큐 폴링이 없고, 탭 파괴 후 callback이 재등록되지 않는지 확인
- 숨은 거래소·증권사 상세 탭에서 잔고·포지션·통계 API 호출이 중지되고, 다시 열면 최신값을 즉시 조회하는지 확인
- 비정상 종료 시 `runtime_stability.jsonl`·`runtime_faulthandler.log`를 회수하고 정상 종료와 구분
- `trade_enabled_exchanges=[]` 저장 시 모든 실제 주문이 차단되고, 활성 거래소 일괄 선택 후 저장할 때만 선택 거래소 주문이 허용되는지 확인
- Binance/Bybit/OKX/Bitget/Upbit/Bithumb을 최소 위험으로 각각 주문 제출·체결·취소/청산 E2E 확인
- AI 커스텀 고급모드에서 EMA 17·63, 15분·1시간 조건과 미지원 기간 501 차단, 런타임 실제 계산값 메타데이터를 확인
- 대시보드 하단에 `v3.9.0.3 안정성·멀티 AI API·AI 커스텀 통합` 요약과 `업데이트·사용법` 버튼이 노출되는지 확인
- 1500×980과 배포 최소 지원 해상도에서 하단 3영역이 한 줄로 유지되고 거래소·분석 탭의 마지막 카드·버튼이 잘리지 않는지 확인
- macOS와 Windows에서 상단 서비스·매뉴얼·설정·종료 아이콘의 모양·크기·정렬이 동일한지 확인
- 현재 서비스의 고유 선택 색상·테두리와 비선택 탭의 배경 구분이 명확한지 확인
- `업데이트·사용법` 클릭 시 사용자 매뉴얼 `업데이트` 탭이 열리고, 여기서 `AI 커스텀`·`금융 인텔리전스` 상세 사용법으로 이동 가능한지 확인
- 사용자 매뉴얼 `업데이트` 최상단에 v3.9.0.3 변경·제한·배포 상태와 v3.9.0.2 이전 배포본 안내가 노출되는지 확인
- 대시보드 업데이트 카드에 `안정성·멀티 AI API·AI 커스텀 통합`이 표시되는지 확인
- 거래 통계 기존 4개 KPI 아래 실제 운용 한 줄에 USDT·KRW 체결금액과 평균 보유시간·유효 건수가 표시되는지 확인
- AI 자동 리포트 오늘·주간·월간·실시간에 같은 통화 분리·청산일·보유시간 기준이 표시되는지 확인
- AI 커스텀의 거래당 허용손실·최대 증거금·레버리지 상한·국면 이탈 선택과 `개선안 · …` 버튼을 확인
- AI 커스텀의 `처음 사용법 AI에게 묻기`, `이 결과 AI에게 묻기`, 명시 국면 추천·제외 근거를 확인
- EMA/SMA 20·50·200, ADX, ATR, MACD 세부값, 볼린저 폭, 거래량·시간 조건이 XAI와 자동검증에서 같은 의미로 표시되는지 확인
- 미지원 필드·연산자가 조용히 무시되지 않고 승인 전에 `unsupported_executable_conditions`로 차단되는지 확인
- 자동검증 결과에 비용 전/후 PnL, 진입·청산 양쪽 수수료, 슬리피지·스프레드, Profit Factor, 기대값, MDD, 거래목록·국면별 결과가 표시되는지 확인
- 코인 전략의 명시 청산 조건이 진입 당시 전략 버전과 함께 포지션에 보존되고 Binance/Unified 모니터에서 평가되는지 확인
- 주식/ETF는 현재 선언형 진입·신호 임계값까지만 공통 지원하며 명시 청산까지 지원한다고 오표시하지 않는지 확인
- AI 어시스턴트가 모호한 설정 요청을 재질문하고, 현재값·변경안·위험을 설명한 뒤 허용 설정만 확인형으로 저장하는지 확인
- 설정 저장 후 파일 재조회 값이 변경안과 일치하는지 확인하고, 불일치 시 원래 설정으로 자동 롤백되는지 확인
- 현재 로그인 사용자의 앱 데이터 `assistant/settings_change_history.json`에 비밀값 없이 감사 이력이 저장되고 앱 재시작 뒤에도 마지막 변경 되돌리기가 가능한지 확인
- 주문·거래 시작/정지·API 키 변경을 채팅이 직접 실행하지 않는지 확인
- 자동검증 미통과 안전 시험만 1배·최대 1%이며 일반 운용 레버리지는 위험모델에서 계산되는지 확인
- 선택 거래소만 실제 주문하고 다른 활성 거래소는 학습 전용으로 표시·동작하는지 확인
- 전략 차단 결과에 국면 판단 시각·신뢰도·현재/후보 국면이 남고, 오래된 입력과 한 번만 튄 일반 국면 전환이 즉시 주문 근거가 되지 않는지 확인
- 동일 시장상태 캐시, 시장 이벤트 재호출, 호출 한도 시 로컬 신호 지속 로그를 확인
- 신규 거래의 `trade_log`에 진입/청산 주문번호·모델·전략·실체결 수수료 출처가 저장되는지 확인
- 7일 챔피언/챌린저에 수수료 차감 순PnL·거래당 순기대값·모델/전략별 비교가 표시되는지 확인
- 설정 `거래소 API` 탭에 아래 2개가 노출되는지 확인
  - `연결 실패 5분 점검 가이드 열기` 버튼
  - `설정 저장 후 연결 위험이 보이면 자동으로 1차 진단 안내` 체크박스
- 자동 동기화 게이트 통과 확인
  - `python3 scripts/user_visible_sync_guard.py --strict`
  - 사용자 노출 코드 변경 시 문서/인앱 4종(`CHANGELOG`, `USER_GUIDE`, `USER_GUIDE_AI_EXECUTION`, `user_manual_widget`) 누락이 없어야 함
- `.git`이 없는 복사본에서는 변경 파일 목록을 직접 전달해야 함
  - PowerShell: `$env:SYNC_GUARD_CHANGED_FILES='ui/dashboard_modern.py,ui/widgets/custom_strategy_widget.py,docs/CHANGELOG.md,docs/USER_GUIDE.md,RELEASE_NOTES.md,USER_GUIDE_AI_EXECUTION.md,ui/widgets/user_manual_widget.py'`
  - 이후 `python build_safe.py --platform windows` 실행
- 문서 진입점 확인
  - `RELEASE_NOTES.md`
  - `docs/CHANGELOG.md`
  - `docs/USER_GUIDE.md`
  - `USER_GUIDE_AI_EXECUTION.md`
  - `docs/STOCK_BROKER_WINDOWS_CONNECTION_CHECKLIST_20260611.md`

## 2) 경로/권한
- 저장 경로 확인: `docs/STORAGE_PATHS.md`
- 사용자 Documents/NoahAI* 하위 디렉토리 생성 권한 확인
- logs/analytics 디렉토리 쓰기 권한 확인

OS별 권한/경로 팁
- Windows
  - 경로: `C:\Users\<USER>\Documents\NoahAI\<username>`
  - Windows Defender의 Controlled Folder Access가 쓰기를 차단할 수 있음 → 예외 추가 또는 기능 비활성화 필요
  - 바이러스 백신/EDR의 랜섬웨어 보호 정책에 의해 `Documents` 쓰기 제한 여부 확인
- macOS
  - 경로: `~/Documents/NoahAI/<username>`
  - 처음 접근 시 “Documents” 접근 권한을 요청할 수 있음 → 시스템 설정 > 개인정보 보호 및 보안 > 파일 및 폴더에서 허용
  - iCloud Drive가 “데스크탑 및 문서” 동기화 중일 때 동기화 지연/충돌 가능성 확인
- Linux
  - 경로: `~/Documents/NoahAI/<username>` (배포 정책에 따라 XDG 문서 경로 상이 가능)
  - 디렉토리 소유권/퍼미션 확인(`chown -R <user>:<group> ~/Documents/NoahAI`)
  - SELinux/AppArmor 정책으로 쓰기 제한 시 예외 정책 추가 필요

## 3) 로그/모니터링
- trading.log 생성/회전 확인
- position_sizing_debug 필요 시 true로 활성화(문서화된 키워드 확인)
- position_sizing_persist 필요 시 true로 CSV 생성 확인

## 4) 의존성/환경
- Python 3.11+ 확인
- requirements 설치 (플랫폼별 파일 구분)
  - 개발/macOS: `pip install -r requirements.txt`
  - Windows 배포: `pip install -r requirements_windows.txt`
- **키움증권 사용 시 Windows 빌드 PC 1회 필수**: `pip install pykiwoom PyQt5`
  - pykiwoom은 PyQt5.QAxWidget 기반으로 PyQt5 없이는 import 불가
  - pyaudio 설치 실패 시: `pip install pipwin && pipwin install pyaudio`
- 음성 사용 시 STT 의존성 설치 확인
  - `SpeechRecognition>=3.10.0`
  - `pyaudio>=0.2.14`
  - macOS: PortAudio 선설치 필요 가능 (`brew install portaudio` 후 `pip install pyaudio` 권장)
- 네트워크 접근 가능(거래소/백엔드/OpenAI)
- 방화벽/프록시: HTTPS(443) 허용, 기업망 프록시 설정 확인
- OS 권한: 사용자 Documents/NoahAI* 폴더 쓰기 권한 확인(Windows/macOS/Linux)
 - 시간 동기화: NTP 동기화 또는 OS 시간 정확도 보장(서명/만료/서버 검증 이슈 예방)

## 5) 기능 확인
- 설정 저장 → 런타임 재초기화 동작 확인(대시보드 즉시 반영)
- Analyzer가 거래소별 데이터(CCXT OHLCV) 수신하는지 로그 확인
- UnifiedTrader 선물 주문 시 레버리지/마진 타입 자동 설정 로그 확인
- 대시보드 애널리틱스 요약 표시/자동 새로고침 동작 확인
- 네 서비스의 금융 인텔리전스 화면과 기본 버튼 확인
  - 블록체인·주식/증권 `금융 인텔리전스`
  - 자산 통합 `성과·위험 분석`
  - AI애널리스트 `금융 인텔리전스 허브`
- 결과의 출처·기준시각·오류·가정 표시와 분석/주문 분리 문구 확인

## 6) 백업/복구
- Documents/NoahAI*/logs, analytics, config, trading.db 주기적 백업
- 장애 발생 시 로그/CSV 기반 원인 분석 절차

## 7) 문서 링크
- 아키텍처: ARCHITECTURE.md
- 업데이트 계획: UPDATE_PLAN.md
- 저장 경로: STORAGE_PATHS.md
- 사용자 가이드: USER_GUIDE.md
- 마스터 문서: MASTER_DOCUMENTATION.md

## 8) FAQ (요약)
- CSV(analytics) 미생성: settings의 `position_sizing_persist: true` 확인, Documents/NoahAI*/analytics 쓰기 권한 확인
- 로그 미생성: Documents/NoahAI*/logs 권한/경로 확인, settings의 log_level 확인
- OpenAI 오류: API Key/네트워크/프록시 확인, 일시적 429/5xx 시 재시도
- 거래소 API 오류: 키/권한/네트워크/시간 동기화 확인, CCXT 버전 호환성 점검
- 프록시/방화벽: HTTPS 443 허용, 기업망 프록시 설정 반영
 - Windows 권한 문제: Controlled Folder Access 예외 추가, 관리자 권한으로 1회 실행 후 사용자 권한으로 재시도
 - macOS 권한 문제: “파일 및 폴더” 접근 권한 허용 후 앱 재실행

---

## 9) 빌드 절차(요약)

사전 준비
- 가상환경 구성 및 의존성 설치(프로젝트 루트에서 실행)

빌드 실행(Windows EXE 기준)
1) 안전 스펙 생성 및 빌드
   - `noahai_client/build_safe.py`를 실행하면 임시 스펙(`aiautotrade_safe.spec`) 생성 후 PyInstaller 빌드 수행
2) 산출물 확인
   - dist/AITrading.exe 생성 확인 → deploy/AITrading.exe로 자동 복사됨
3) 무결성 체크
   - dist/deploy 폴더 내에 PyQt5/PySide/Qt 관련 파일이 없는지 확인(아래 사후 점검 참고)

플랫폼별 빌드 (build_safe.py --platform)
- 운영 배포 기준(고정): Windows `python build_safe.py --platform windows` → dist/AITrading.exe → deploy/AITrading.exe 자동 복사
- macOS/Linux 빌드는 개발/내부 검증 용도로만 사용하고 고객 배포 자산으로 사용하지 않는다.

## 9-B) GitHub 자동 릴리즈 운영 (중요)

기준 저장소
- 자동업데이트 조회/릴리즈 업로드 기준 저장소는 `nwsoft/ai-trading-client` 단일 저장소로 운영한다.
- 웹사이트 저장소(`nwsoft/noahailabs-website`)는 공지/문서 반영 용도로만 사용한다.

자동 릴리즈가 동작하는 조건
- 클라이언트 코드가 Git 저장소 루트(`.git` 존재)여야 한다.
- 태그 `v*`를 push하면 GitHub Actions가 Windows 빌드 + Release 업로드를 수행한다.
- 워크플로 파일: `.github/workflows/windows-release.yml`

`.git`이 없는 복사본에서 해야 할 일
1) Git 저장소 상태 확인
  - `git rev-parse --is-inside-work-tree`
2) `fatal: not a git repository`가 나오면 아래 중 하나 선택
  - A안(권장): 실제 클라이언트 Git 작업본(원격 연결된 폴더)에서 빌드/태그/푸시 진행
  - B안: 현재 폴더를 Git 저장소로 초기화 후 원격 연결
    - `git init`
    - `git remote add origin https://github.com/nwsoft/ai-trading-client.git`
    - 기본 브랜치 맞춤(`main` 또는 기존 운영 브랜치)

사용자가 GitHub에서 해야 할 작업
1) 저장소 존재 확인: `nwsoft/ai-trading-client`
2) Actions 권한 확인
  - Repository Settings > Actions > Workflow permissions: `Read and write permissions`
3) 릴리즈 권한 확인
  - 워크플로의 `permissions: contents: write`가 유지되어야 릴리즈 업로드 가능
4) 태그 기반 배포 실행
  - 버전 업데이트 커밋 후 `git tag v3.9.0.3` / `git push origin v3.9.0.3`
  - 이후 버전도 동일 패턴
  - Windows 자동화 스크립트 사용 가능: `powershell -ExecutionPolicy Bypass -File scripts/release_tag_push.ps1 -Version 3.9.0.3 -Branch main -PushBranch`

전환 운영 기준(질문 반영)
- `v3.9.0.3`:
  - 클라이언트 저장소 릴리즈 업로드(필수)
  - 웹사이트 저장소 공지/다운로드 안내 반영(권장)
- `v3.9.0.1`부터:
  - 자동업데이트 기준은 클라이언트 저장소 하나만 사용
  - 웹사이트는 문서/공지만 반영

## 9-A) macOS 서명 및 노타라이즈 절차 (선택·권장)

사전 준비
- Apple Developer 계정(Developer ID Application 인증서 보유)
- Xcode 및 Command Line Tools 설치
- notarytool 자격 증명 저장(1회):
  - xcrun notarytool store-credentials "noahai-notary" --apple-id <APPLE_ID> --team-id <TEAM_ID> --password <APP_SPECIFIC_PASSWORD>

1) 앱 번들 확인
- build_safe.py --platform macos 실행 후 dist/AITrading.app 생성 확인
- 필요 시 격리 속성 제거: xattr -dr com.apple.quarantine dist/AITrading.app

2) 엔타이틀먼트 파일(선택)
- CustomTkinter 기반 앱은 별도 entitlements 없이도 동작 가능
- 필요한 경우 최소 예시(entitlements.plist):
  - com.apple.security.files.user-selected.read-write (선택)
  - com.apple.security.cs.allow-unsigned-executable-memory (특수 케이스)
  - 샌드박스는 일반적으로 사용하지 않음

3) 코드서명(하든드 런타임 포함)
- codesign --force --deep --options runtime \
  --sign "Developer ID Application: YOUR NAME (TEAMID)" \
  --entitlements entitlements.plist \
  dist/AITrading.app
- entitlements가 불필요하면 --entitlements 옵션 생략 가능

4) 노타라이즈 제출 및 대기
- xcrun notarytool submit dist/AITrading.app --keychain-profile "noahai-notary" --wait
- 성공 시 id/status 출력

5) 스테이플(티켓 부착)
- xcrun stapler staple dist/AITrading.app

6) 검증
- spctl --assess --type execute -v dist/AITrading.app
- codesign -dv --verbose=4 dist/AITrading.app

문제 해결
- OSStatus -67062: 인증서/팀 ID/애플 ID 매칭, 신뢰 설정 확인
- Notarization Rejected: notarytool 로그로 거절 사유 확인 → entitlements/서명 옵션 보정 후 재시도

## 10) 사후 점검(필수)

패키징 구성 점검
- dist/ 또는 deploy/ 산출물 내에서 다음 확인
  - 포함: config 템플릿 3종, icon.ico/png, 코드 모듈(trading, api 등)
  - 포함 제외: data 폴더 전부(런타임 생성)
  - 배제: PyQt5/PySide6/Qt 관련 DLL/so, Jupyter/과학 패키지 바이너리

런타임 경로/권한 점검
- 빌드 산출물 실행 → 최초 실행 시 다음 확인
  - `~/Documents/NoahAI*` 폴더 자동 생성
  - 하위 `logs/` 내 `trading.log` 생성 및 로그 기록
  - `analytics/` 폴더(옵션)와 설정 템플릿 복사 위치 정상
  - 오류 시 `noahai_client/path_utils.py`의 경로 해석 로직 및 OS 권한 확인

기능 스모크 테스트(페이퍼 모드)
- 기본 설정으로 대시보드 실행 → 차트/요약/AI 탭 로딩 확인
- Analyzer에서 CCXT OHLCV 수신 로그 확인
- 모의 포지션 진입/청산 시도 → 레버리지/마진 타입 설정 로그 및 PnL 계산 정상 확인

## 11) 트러블슈팅

실행 중 "Module not found" 오류
- hiddenimports에 누락된 모듈 추가 후 재빌드(예: 특정 거래소 어댑터)
- macOS에서 `win32_setctime` 관련 오류 시 hiddenimports에서 제거

UI 초기화 오류/Qt 로딩 시도
- dist/deploy 내에 `PyQt5`, `PySide*`, `Qt*` 파일이 포함되었는지 확인 → 스펙 excludes 재점검
- 레거시 PyQt 파일은 ImportError 스텁으로 유지되어야 함

문서/권한 관련 오류
- macOS: 시스템 설정 > 개인정보 보호 및 보안 > 파일 및 폴더에서 앱 접근 허용 후 재실행
- Windows: Defender Controlled Folder Access 예외 추가 또는 임시 비활성화 후 재시도

네트워크/프록시
- 기업망 프록시 설정 반영 필요. HTTPS 443 오픈 여부 확인
- OpenAI/거래소 API 429/5xx는 지수 백오프 재시도 후 로그 확인
