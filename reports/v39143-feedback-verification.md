# 2026-09-20 피드백 검증 기록

## Client 소스 후보 3.9.1.43

- 제품 3.9.1.43, updater 3.9.143. 공개42는 보존. 설치기 생성·릴리스 미수행.
- 원본 고객 DB read-only 감사: 300/40, 청산 주문 ID 없는 LIVE 40건, 원본 해시 불변. 과거40 복구 미완료.
- PnL/주문 근거/안전차단 + 영어/난이도 회귀 121 passed.
- TypeScript/Vite build 통과, 기존 대형 번들 경고는 남음.
- `webui/tests/difficulty.html`은 외부 API·계좌·주문 없는 격리 fixture. 실제 SettingsCenter/StrategyStudio를 렌더링해 버튼→AI 엔진/API→난이도 선택기 스크롤·포커스 확인.
- Level 1~4 한국어 표기, verified save 후 Level 1 즉시 반영, 코인→주식 전환 후 유지, 영어 Beginner 표기 확인.
- 처음 fixture의 저장 receipt가 없어 기존 저장 검증이 거부하는 것도 확인했다. 실제 계약의 verified receipt를 모사한 뒤 정상 저장 확인. 안전 검증을 제거하지 않았다.
- 한국어 매뉴얼 11개 section 재생성, 영어 매뉴얼과 변경/빌드 가이드 갱신.
- Windows 설치본, 실계좌 체결 대조, 미대조 과거40 복구, 장시간 재발 없음은 확인하지 않았다.

## 웹사이트 (설치기와 별도)

- daltrading 홈 영어 전체 본문을 서버 렌더링. 한국어 홈 유지. 130 tests + 3 subtests 통과.
- 운영 홈 1200px 및390px 실제 브라우저 확인: 긴 설명 영어, 로그인/가입 뒤 언어 선택, 본문 한글 잔여 없음, 수평 overflow 없음.
- 운영 로그인/가입390px 확인. 가입·거래 등 외부 쓰기는 수행하지 않았다.
- 전략 허브390px 검사에서 헤더 브랜드가 좁게 압축되는 추가 문제를 발견하여 허브·가이드·제출·라이선스 공통 반응형 헤더 보강.
- 전략 원문·제작자 설명은 번역하지 않는다. 동적 근거 일부와 레거시 가이드/법률 전문은 아직 한국어가 남아 있다. 사이트 전체 완역으로 보고하지 않는다.
- Labs 회사 설명4언어, hero 표현, 한국어 body/제목 keep-all. 운영390px의 제보된 제목과 360/768/1440px overflow 검사. 태블릿 Footer 브랜드 영역 추가 개선.
- Labs build/public-data 검사 통과, lint 오류0/기존 경고19. 공개manifest42 동기화.

## 운영 배포 식별

- daltrading: `94988b1` (홈 본문/헤더 `1b53353` 포함). EC2 `/home/ubuntu/daltrading` fast-forward 반영, daltrading/remote service active 확인. 기존 venue registry 로컬 변경과 서버 backups는 건드리지 않았다.
- NoahAI Labs: `41fe9bd` (`7f1670f` 포함). Cloudflare Pages `https://21deb978.noahailabs-website.pages.dev`, 운영 `/ko` 새 hero/회사 설명 반영 확인.

사용자 안내와 PnL 미완료 경계: [V39143_FEEDBACK_REVIEW.md](../docs/V39143_FEEDBACK_REVIEW.md).
