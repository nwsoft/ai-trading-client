# NoahAI v3.9.1.40

Strategy Studio 가독성과 AlphaArena PAPER 안전성, 설정 연결 점검을 보강한 Windows 릴리스입니다. 공개 v3.9.1.39 자산은 변경하지 않고 v40 전용 자산을 제공합니다.

## 주요 변경 사항

- Strategy Studio의 코인 및 주식·ETF 설명 가독성, 입력 공간과 단계 이동 흐름을 개선했습니다.
- AlphaArena 실행 중 PAPER 설정이 바뀌어도 LIVE 주문 경로로 전환되지 않도록 차단했습니다.
- 설정 변경 시 실행을 정지하고 이전 요청 종료 전 중복 시작을 거부하며, 재시작 시 저장된 새 설정을 적용합니다.
- AlphaArena 전용 DeepSeek 키와 선택 엔진으로 실행 및 연결 점검 경로를 통일했습니다.
- AI 응답, 구조화 판단, PAPER 점검 결과와 실행 오류를 구분해 표시하고 존재하지 않는 가상 손익을 만들지 않습니다.
- 설정 화면의 실제 호출 점검, 모델 목록 분리와 자격정보·기관·알림 상태 변경 후 오래된 성공 표시 제거를 보강했습니다.

## Windows 배포 자산

- `NoahAI-3.9.1.40-Setup.exe`
- `NoahAI-3.9.1.40-Setup.exe.blockmap`
- `latest.yml` (updater `3.9.140`)
- 설치기에 포함된 x64 `NoahAIEngine.exe`와 x86 `NoahAIKiwoomHost.exe`

## 검증 범위

자동 회귀, Web production build, x64 엔진, 키움 x86 호스트, PE 아키텍처, IPC 시작·종료와 설치기·blockmap·manifest 해시는 빌드 과정에서 검증합니다. 공개 v3.9.1.39에서의 실제 업데이트, 키움·증권·거래소 계정 연결, AlphaArena 실제 AI 호출과 장시간 PAPER 운용은 별도 외부 검증 항목입니다.

AlphaArena는 Binance PAPER 판단·조건 점검 실험이며 실제 또는 가상 체결 수익을 보장하지 않습니다. LIVE 거래는 계정 권한과 위험 설정을 별도로 확인한 뒤 사용해야 합니다.
