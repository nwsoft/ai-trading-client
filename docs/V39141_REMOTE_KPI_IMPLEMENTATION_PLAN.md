# v3.9.1.41 KPI·인증 및 원격 관리 실행 계획

공개판 3.9.1.40 / 후보 3.9.1.41 · updater 3.9.141. 2026-09-19 소스 구현·격리 시험 완료, 운영 이관·Windows 배포 대기. 기존 내부 patch 식별자 `Market Trend Visuals and Evidence-based XAI Patch`는 유지하되 같은 v41 후보 범위에 아래 기능을 추가합니다.

## 진행 현황

**9월 19일 DB 확인 후 배포 보류:** [PnL 차단·손실 알림 조사](V39141_PNL_GUARDRAIL_FEEDBACK.md). 청산 주문 ID 누락 원인 확인, 보호 주문 근거/재대조·가짜 평가손실 방지·일일 기준값 영속화와 관련 계산 경로를 보강했다. Client 2,741 passed. 아래 수치는 이전 단계 기록이며 검증 보고의 DB 수령 후 절을 따른다. 특정 사용자 DB 복구는 배포 필수 조건이 아니지만 기존 미대조 기록을 가진 사용자의 안전한 업데이트 처리와 Windows/실기관 게이트는 남는다.

- [x] 운영 읽기 진단 및 아키텍처 검토.
- [x] KPI DB 격리 설정·집계 저장·인증 경로 경량화 소스 및 격리 회귀. 실제 로그인 속도 개선은 운영 전후 측정 대기.
- [x] 성공 텔레메트리만 외부 아카이브·30일 보관·이관과 복원 도구. 해시/내용 검증 실패 시 원본 보존.
- [x] daltrading 모바일 내 PC 화면과 기기 토큰 해시·세션·소유권·CSRF 인증.
- [x] PC 연결 동의·60초 상태 전송·폐기/3분 오프라인·명령 120초 만료 처리.
- [x] 원격 신규 제출 일시정지의 7개 거래소·4개 증권사 공통 코드 경계 회귀. 보호·청산 유지, 중복 명령·PC 재개·재시작 검사. 실제 기관 주문 시험은 아님.
- [x] Client 2,665 passed / 8 skipped / 3 subtests, daltrading 113 passed / 3 subtests, Node 43 passed, 64 modules Web build.
- [x] 300계정 1,200요청 로컬 ASGI 시험(40 workers) 오류 0, PC·390px 모바일 fixture 및 오프라인 제어 차단.
- [x] 매뉴얼 11개 섹션 재생성·설정 AI 설명·릴리스·빌드·배포·테스트 문서 정합 PASS.

## 구현 범위와 근거

원격은 상태 공유 + PC에서 별도 허용한 기관의 신규 주문 제출 일시정지입니다. 시작·재개·전량 청산·API 키 변경·PnL/포지션 상세 공유는 제공하지 않습니다. 재개는 PC에서만 하며 이미 제출된 주문은 체결될 수 있습니다. AlphaArena 별도 PAPER 판단 실험 종료를 제어하는 기능은 아닙니다.

- Client: `api/telemetry_batch.py`, `api/kpi_client.py`, `web_platform/remote_monitor.py`, `trading/remote_entry_pause.py`, 설정 UI·gateway.
- daltrading: `utils/metrics_storage.py`, `kpi_migrate.py`, `routes/remote.py`, `utils/remote_store.py`, 별도 relay·maintenance unit.
- [사용법](REMOTE_MANAGEMENT_GUIDE_V39141.md) · [최종 검증/화면/명령](../reports/v39141-remote-kpi-verification.md).
- 서버 상세 실행 문서: sibling daltrading의 `docs/V39141_REMOTE_KPI_DEPLOYMENT.md`.

## 아직 완료하지 않은 운영 게이트

- [ ] 여유 공간 확보 → 운영 백업으로 DB 분리 리허설·내용/건수/복원 대조 → 점검창 최종 이관.
- [ ] S3 실제 업로드·다운로드 복원, 독립 relay·Nginx/Cloudflare private cache 경계, timer 배포.
- [ ] 로그인 POST p50/p95·DB busy·디스크/오류율 전후 비교 및 실제 EC2 300대 부하·재연결 집중.
- [ ] Windows v41 새 설치본·v40→v41 업데이트·실제 기기 등록/명령/만료/재연결·기관별 관리 경계.
- [ ] 개인정보·원격 권한/약관 확인 후 allowlist 20→100→300명과 24시간 피드백.

이번 작업은 운영 DB를 삭제/이관하거나 공개 설치기·manifest·stable/latest를 변경하지 않았습니다. 로컬 ASGI 시험은 실제 300PC의 24시간 운용 증거가 아닙니다. 기존 PnL 원본 대조 미완료 항목도 그대로 유지합니다.

## 원칙

전략 실행과 거래소 자격증명은 PC에 유지한다. 모바일 웹 세션과 PC 세션은 공존한다. 체결/손익 원본을 일반 KPI와 함께 정리하지 않는다. 기관별 검증되지 않은 명령을 실행 가능하다고 표시하지 않는다. 운영 데이터는 외부 보관/복원 확인과 이관 검증 전에 삭제하지 않는다.

구현·자동 시험·Windows 설치본·운영 이관·배포를 각각 증거에 따라 기록한다. 공개 자산은 소스 변경만으로 갱신하지 않는다. 최초 20→100→300명 기능 활성화를 목표로 한다.

[운영 진단](../reports/v39141-remote-kpi-review.md)
