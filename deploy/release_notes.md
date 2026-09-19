# NoahAI v3.9.1.41

시장 트렌드·근거형 XAI, KPI 경량화와 동의형 내 PC 원격 관리 베타를 포함한 Windows 릴리스입니다. 공개 v3.9.1.40 자산은 변경하지 않고 v41 전용 자산을 제공합니다.

9월 19일 DB 확인을 반영해 보호 주문 근거/청산 재대조, 과거 미청산의 가짜 평가손실 방지, 동일 API 연결의 일일 기준값 영속화, 순손익 통계/성과 튜닝과 누락/환급 처리를 보강했습니다. 특정 사용자 원장 복구 완료와 배포 검증은 구분합니다. 기존 미대조 기록의 안전한 업데이트 처리·실기관·일별 계좌 대조 등 `docs/V39141_PNL_GUARDRAIL_FEEDBACK.md`의 남은 항목은 외부 검증 pending으로 유지합니다.

## 주요 변경 사항

- 시장 트렌드 오늘·7일·30일 그래프와 코인/주식 데이터 경계, 화면 근거를 이용한 AI 브리핑·관찰 후보 XAI.
- 성공 학습·추론 KPI의 지원 서버 협상형 집계 전송. 서버 인증/KPI DB 격리, 30일 외부 보관·복원 검증 도구와 장기 가중 요약.
- 설정 → 알림·리포트의 동의형 내 PC 상태 공유. 모바일 daltrading 로그인 후 기관별 실행·PAPER/LIVE·수신 시각 확인.
- PC에서 별도 허용한 기관의 신규 주문 제출 일시정지. 이미 제출한 주문은 체결될 수 있고 보호·청산은 유지. 재개는 PC에서만 가능.
- 원격 시작·전량 청산·키 변경·손익 상세 공유는 제공하지 않음. API 키·전략 원문·거래 실행은 PC에 유지.

## Windows 배포 자산

- `NoahAI-3.9.1.41-Setup.exe`
- `NoahAI-3.9.1.41-Setup.exe.blockmap`
- `latest.yml` (updater `3.9.141`) 및 같은 버전 `release-manifest.json`
- 설치기에 포함된 x64 `NoahAIEngine.exe`와 x86 `NoahAIKiwoomHost.exe`

## 검증 범위

소스 자동 회귀·격리 브라우저 결과는 `reports/v39141-remote-kpi-verification.md`를 따릅니다. 새 Windows 설치본·v40→v41 업데이트·PE/SHA·키움 OCX·실기관·장시간 운용과 서버 DB 이관/S3 복원/relay/캐시/300명 확대는 별도 미완료 게이트입니다. 베타 대상 활성화 전 개인정보·권한 범위를 확인합니다.

이전 PnL 원본 대조 미완료 사항은 이 기능으로 해결되지 않습니다. 원격 화면은 마지막 수신 상태이며 거래소 원본 계좌 수치가 아닙니다. 상세 계획: `docs/V39141_REMOTE_KPI_IMPLEMENTATION_PLAN.md`, Windows 빌드: `docs/BUILD_GUIDE.md`.
