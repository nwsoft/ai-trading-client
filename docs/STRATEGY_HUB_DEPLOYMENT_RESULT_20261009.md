# 전략 허브 배포 결과와 v3.9.2.9 Windows 준비

2026-10-09 KST 검증. **noahai.net 전략 허브 배포 완료**, 최종 운영 커밋 **`a42cdc490c48af922603b9530a06473829e52023`**. GitHub 최신 정식 클라이언트는 **v3.9.2.8**, 공개 태그 **`9714cc565a013f0fc1fb8931235809c132f66bc1`**다. **v3.9.2.9는 도움말·버전·문서 수정의 Windows 빌드 준비판**이며 설치기·태그·공개 릴리스는 만들지 않았다.

## 배포한 변경

1. 다중 거래소·증권사 쉼표 범위의 모든 기관을 검사한다. 별칭·중복과 혼합 상품을 처리하고 미지원 기관·빈 토큰·잘못된 기관군을 거절한다. `volatile` 국면을 `high_volatility`로 보존한다.
2. 조건 그래프와 LONG/SHORT 진입 구조를 허브에서 분석한다. 패키지·IR 해시·민감정보 차단·비활성 가져오기 계약을 유지한다. 원본 파일의 범위를 임의로 줄이는 해결책을 사용하지 않는다.
3. 제작자 집계의 누락·비정상 손익·비용·표본을 `null/미기록`으로 표시하고 실제 기록 0과 구분한다. 빈 검증 메타데이터만 있으면 E0로 유지한다. 기존 DB 집계의 과거 0을 임의 복원하지 않았다.
4. 운영자 근거 등록을 자동 서명 검증·기관 체결 대조 완료처럼 설명하지 않는다. API는 `evidence_verification_method=administrator_attestation/unverified`, `automated_evidence_verification=false`를 제공한다. E0/E1은 순위에서 제외한다.
5. 허브·가이드·제출·여권·관리자·제품 상태·검색 설명·llms와 공개/투자자료 정본을 교정했다. 입증되지 않은 세계 최초 표현을 제거하고 무료 범위, 공개 .8, 준비 .9, 미구현 결제·정산을 분리했다. 배포 사이트는 **noahai.net**이며 noahailabs.com/info.noahai.net의 별도 저장소나 이름이 지정되지 않은 기존 투자 슬라이드를 게시한 결과는 아니다.

## 검증 연결

| 증거 | 결과 |
|---|---|
| 코드·커밋·실제 서버 파일 | 최종 운영 HEAD=GitHub main=검증 작업트리. 변경 파일 19개 SHA-256 일치. [최종 서버 신원](../reports/strategy-hub-deploy-20261009/production-final.json), [비교 영수증](../reports/strategy-hub-deploy-20261009/production-final-comparison.json) |
| 실제 배포 코드의 순수 함수 실행 | 다중 거래소·증권사 수용, 미지원 기관 거절, volatile 유지, 누락값 null·실제 0 구분, 빈 메타데이터 E0. 애플리케이션 import/DB 쓰기 없이 운영 파일 AST에서 확인 |
| 서비스 | daltrading/remote active. 최종 web PID 1746652, 시작 2026-10-09 05:06:03 KST. [배포 로그](../reports/strategy-hub-deploy-20261009/deployment-final.txt) |
| 허브 전체 Python 회귀 | **192 passed + 하위 사례 17 passed**, 운영 핵심 의존성 버전과 같은 격리 환경. [전체 결과](../reports/strategy-hub-deploy-20261009/tests-all.txt) |
| 실제 전략 파일 호환성 | 원본 3개 모두 분석 200·공개 201·다운로드 200. 원본 SHA와 받은 바이트 일치, 격리 DB만 사용. [원본 파일 회귀](../reports/strategy-hub-deploy-20261009/actual-packages.json) |
| 공개·취득·철회 | 임시 DB에서 분석→공개→무료 취득→재다운로드→중지 요청/확정→신규 취득 404→기존 라이선스 동일 파일 200. 운영 전략을 새로 게시/취득하지 않음 |
| 실제 HTTP | 공개 API 200, 비로그인 라이선스/계정 요약 401. 공개 여권 E0 2개, 신규 영역 2개, 검증 카테고리 10개 모두 0. [HTTP](../reports/strategy-hub-deploy-20261009/http-readonly.json) |
| 실제 운영 화면 | 한/영 허브·가이드·제품 상태 ×390/1440px =12개, 200·가로 넘침 없음·브라우저 예외 없음. [화면 결과](../reports/strategy-hub-deploy-20261009/production-final-browser/browser.json). 격리 E1 미기록 여권 등 14개도 별도 확인 |
| 기존 업무 기록 | 공개 전략/제출 각 2, FREE 취득/활성 라이선스/다운로드 감사 각 6, validation/E1/중지/신고 0으로 전후 동일. 인증·전략 핵심 6개 테이블 읽기 전용 integrity_check=ok. DB 전체 바이트 동일성·모든 KPI 행 무변경을 주장하지 않음 |
| 기존 작업 보존 | original daltrading HEAD 819e14f와 기존 60개 파일 해시 유지. 별도 작업트리에서 관련 파일만 commit/push. [보존 결과](../reports/strategy-hub-deploy-20261009/original-preservation.json) |

소스는 `strategy_market.py:derive_strategy_submission_contract/_row_to_strategy`, `strategy_package_store.py:verify_noahstrategy_bytes/_publisher_evidence_summary`, `routes/strategies.py`, `tests/test_strategy_market.py`로 연결한다. 원본 저장소의 미커밋 소스는 보존되어 있으므로 배포 소스 리뷰는 `/private/tmp/noah-hub-deploy-20261009` 또는 위 운영 커밋을 사용한다.

## 기능 상태

| 기능 | 상태 | 제한 |
|---|---|---|
| 다중 기관 파서·조건 그래프·누락값 표시 | 현재 운영 확인 | 실제 서버 코드·한/영 응답과 격리 원본 파일 회귀. 운영 신규 제출 인수는 별도 |
| 권리 자기선언·E0 공개·무료 취득·계정별 라이선스 | 현재 운영 확인 | 기존 운영 기록 확인. 법적 권리 인증·유료 매출 아님 |
| E1 표시·버전 갱신·재다운로드·공개 중지·기존 라이선스 보존 | 구현·자동 테스트 완료, 운영 인수 필요 | 운영 E1/중지 기록 없음. 회원 쓰기 흐름은 격리 DB만 시험 |
| E0/E1 랭킹 제외 | 현재 운영 확인 | 검증 랭킹 0개. 자기신고 승률·수익률을 순위로 표시하지 않음 |
| E2~E5 분류·점수·운영자 승격 | 부분 구현 | 관리자 입력·표본/기관 규칙과 분류 기능. 실제 근거 서비스 완료가 아님 |
| 자동 서명 검증·실행 원장 귀속·기관 체결 대조 | 미구현·향후 계획 | 출처 enum/확인값을 자동 검증 결과로 사용하지 않음 |
| 전략 구독·유료 판매·포인트·환불·제작자 정산 | 미구현·향후 계획 | 무료 베타. PG/원장/지급 실행기를 제공하는 상태가 아님 |
| Windows 설치기·실계정·장시간 운용·운영 회원 화면 인수 | 접근/근거 부족으로 확인 불가 | Windows 빌드/릴리스는 사용자 수행, 실제 로그인 계정 인수 별도 |

## 백업 중 발생한 오류와 복구

전체 운영 DB 백업을 시도하며 서버 여유 공간을 먼저 충분히 확인하지 않은 것은 이번 작업의 오류다. 원본 DB는 약 6.6GB, 최초 여유 약 5GB여서 불완전 백업이 디스크를 채웠다. 해당 **이번 작업의 불완전 백업만 삭제**하고 여유 약 5GB를 복구했다. 기존 DB·기존 backups·기존 소스는 삭제하지 않았다. 이 구간 KPI 수집 경로에서 `database or disk is full` 1건과 `disk I/O error` 17건, 총 18건이 기록됐다. 해당 요청의 원장 반영·재전송/누락 여부는 **대조 전**이다. 클라이언트 코드는 일반 KPI가 항상 영속 재전송되는 계약이 아니므로 자동 복구를 보장하지 않는다.

복구 후 인증·전략 업무 테이블을 읽기 트랜잭션으로 제한 백업했다. 서버 경로 `backups/strategy-hub-20261009-business/`는 KPI 이력을 제외한 업무 테이블 백업이며 전체 DB 복원본이 아니다. 의존성 재설치·명시적 DB 마이그레이션·운영 게시/취득/결제는 하지 않았다. 서비스 재시작 이후 SQLite disk-full/I/O/Traceback 0건 관측과 주요 DB 검사 통과를 확인했다. [오류 분류](../reports/strategy-hub-deploy-20261009/sqlite-error-summary.json), [복구 후 관측](../reports/strategy-hub-deploy-20261009/service-after-recovery.json). 이 결과를 KPI 영향 없음으로 표현하지 않는다.

## 클라이언트 3.9.2.9 준비

준비 브랜치 `release/v3.9.2.9-strategy-hub-20261009`, 커밋 **`c12321054a22c862c365ff3aa9b491d5bcbeb9be`**. 제품/엔진/PE 3.9.2.9, updater 3.9.209, renderer 3.9.2.9-ui.20261009.1. `.8` 공개 매니페스트 원본 SHA를 고정하고 Git 줄바꿈 변환으로 바뀌지 않도록 보호했다. 실제 매매 엔진·PAPER 계산/복구 변경은 없다.

관련 Python **162 passed**, Node **46 passed**, TypeScript 두 구성·Vite 빌드·문서 정합성·11탭 매뉴얼 추출 통과. 커밋 기준 소스 지문과 깨끗한 Git 작업트리 지문은 모두 `ab0cad4f5eb9d2f4906414d6719032cd1414f11b3fa20425d183703277039318`다. 실제 `noahai_client/` 29개 대상 파일과 웹 renderer를 반영하고 이전 바이트를 `reports/v3929-build-preparation-20261009/source-backup`, 이전 renderer를 `renderer-backup`에 보존했다.

동기화 폴더에는 Git이 없고 기존 `.github/workflows/windows-release.yml` 차이를 보존해 전체 지문은 다르다. 따라서 Windows에서는 동기화 폴더를 빌드 정본으로 우회 사용하지 않고 아래 깨끗한 준비 브랜치를 사용한다. Git bundle도 제공했으며 기본 .8 태그 커밋을 prerequisite로 요구한다. 기존 Windows 작업은 덮어쓰지 않는다.

```powershell
git fetch origin
git worktree add --detach ..\noahai_client_3929_build origin/release/v3.9.2.9-strategy-hub-20261009
Set-Location ..\noahai_client_3929_build
git rev-parse HEAD
# c12321054a22c862c365ff3aa9b491d5bcbeb9be와 대조
# Node >=22.12, x64 Python, 별도 x86 Kiwoom 환경 준비
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

검사 생략 옵션은 사용하지 않는다. 빌드 후 .8→.9 설치/업데이트·롤백·OCX·격리 허브 제출/가져오기를 사용자 Windows PC에서 인수한 뒤 기존 릴리스 게이트로 게시한다. 이번 세션은 준비 브랜치 push만 수행했고 Windows workflow 실행·설치기 생성·태그·GitHub 릴리스·latest.yml 교체는 하지 않았다. 마지막 GitHub 조회에서도 공개판은 v3.9.2.8, 새 준비 브랜치 workflow 실행 목록은 비어 있다.
