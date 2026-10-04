> 2026-10-04 버전 귀속 정정: 공개 v3.9.2.3 이후 소스 보완은 [v3.9.2.4 업데이트](V3924_FINANCE_DECISION_UPDATE_PLAN.md)에 포함합니다. 이 문서의 기존 파일명·검증 버전은 당시 기록으로 보존합니다.

# 2026-10-04 — Mac 로컬 실행·바탕화면 바로가기 복구

## 확인한 원인

사용자가 실행한 `env -u ELECTRON_RUN_AS_NODE npm --prefix webui run electron:dev`는 Python 엔진을 시작하기 전에 종료됐다. `webui/package.json`은 3.9.203 / 제품 3.9.2.3인데 `webui/dist/ui-build.json`은 3.9.2.2였다. 기존 실행기가 오래된 화면을 감지해 문구만 출력하고 종료하는 경로와 일치했다.

발견 당시 화면 hash는 `cdcde35a3b388b151c99025338fee53cc8b3a871f00636ab995b9b1903cc9008`, 현재 소스 hash는 `5ad959d36e36c9f1c8f49159bbd2bae288a65b74cc73a2ec590fca52faca159a`였다. 10월 3일 이전 Mac 화면 검증은 그 당시 증거이며 이후 변경된 3.9.2.3 소스의 로컬 실행 증거가 아니었다. 별도 Windows 배포 자산을 Mac 개발 폴더의 화면 빌드로 대신 사용할 수 없다.

추가로 기본 셸 Node는 20.20.0, 설치된 호환 버전은 22.23.1이었다. 기존 node_modules에는 Mac arm64 Rollup/esbuild 패키지가 없고 tsc 실행 비트도 없었다. 해당 의존성은 원본을 백업하고 **기존 package-lock.json 그대로** 임시 폴더에서 npm ci --include=optional로 설치한 다음 교체했다. 전역 Node 기본값·금융 설정·원장·배포 manifest는 변경하지 않았다.

## 수정

- 소스 실행기: 화면이 현재 상태이면 바로 실행. 오래됐거나 없으면 설치된 호환 Node로 TypeScript/Vite 빌드 → 지문·index/참조 자산 확인 → Electron 실행.
- npm의 셸 Node/동기화된 실행 권한에 의존하지 않고 컴파일러 JS 진입점을 선택 Node로 호출한다. 실행마다 npm 설치나 버전 변경을 수행하지 않는다.
- 동시에 여러 번 실행하면 같은 빌드를 기다린다. 실패·빌드 중 소스 변경이면 이전 화면을 새 화면처럼 실행하지 않는다. 빌드 중 소스가 변경되면 새 지문을 잘못 발급하지 않는다.
- 화면 메타데이터가 있어도 index.html/참조 자산이 빠진 경우 다시 빌드한다.
- 개발 실행의 화면 준비 이벤트에 제품 버전을 출력한다. 실제 packaged Windows 앱의 시작/업데이트 경로와 거래 권한은 바꾸지 않는다.
- 이 Mac 바탕화면에서 기존 NoahAI 바로가기를 찾지 못해 `~/Desktop/NoahAI.app`을 생성했다. 저장소의 NoahAI 아이콘을 사용하고 **현재 소스 실행기**를 호출한다. 별도 배포용 패키지로 가장하지 않는다. 실행 로그: `~/Library/Logs/NoahAI/local-launch.log`.

## 검증

- TypeScript/Vite production build 통과, renderer 버전 3.9.2.3 및 소스 지문 일치.
- 기존 사용자 명령 실행 → Electron `v3.9.2.3 화면 준비 완료` 이벤트 확인.
- 실제 로컬 Gateway `/api/v1/health`: HTTP 200 / release_version=3.9.2.3.
- 메타데이터를 백업 위치로 이동해 누락 상태를 의도적으로 재현한 후 **같은 명령**으로 Node 22 선택·자동 재빌드·종료 코드 0 확인. 이미 열린 앱의 단일 인스턴스를 사용하며 엔진을 중복 실행하지 않음.
- 생성된 바탕화면 앱의 CFBundleExecutable 직접 실행 exit=0. 소스 경로/Node 경로/아이콘/Info.plist 및 zsh 문법 확인.
- Node 전체 계약 시험 **73 passed / 0 failed**. 현재 빌드 무작업, 불일치 복구, 동시 실행, 실패 시 잠금 해제, 살아 있는 잠금 보존, 누락 자산, 빌드 중 변경 검사 포함.
- native UI 조회 도구가 `Sky Computer Use native pipe startup failed`로 실패하여 Finder 더블클릭·아이콘 모양의 시각 인수는 수행하지 못했다. 실행 파일/창 준비 이벤트/엔진 health와 시각 인수를 구분한다.

현재 열어 둔 앱에서 로그인이나 거래 시작을 수행하지 않았다. 기존 공개 자산/버전은 교체하지 않았다. 수정 파일과 백업 위치는 `reports/v3923-mac-launcher-fix-20261004.json`에 기록한다.

## 실행

바탕화면 NoahAI.app 또는 저장소 루트에서 다음 명령을 사용한다.

```bash
npm --prefix webui run electron:dev
```

소스 폴더/Node 설치 위치를 옮겼다면 바로가기를 재생성한다.

```bash
.venv/bin/python scripts/install_macos_source_launcher.py --node /absolute/path/to/compatible/node
```
