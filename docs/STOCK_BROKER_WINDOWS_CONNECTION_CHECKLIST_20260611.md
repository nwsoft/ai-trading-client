# 증권사 연결 점검 체크리스트 (Windows 사용자용)

기준 버전: v3.8.9.22
대상: Windows용 NoahAI Client 사용자 (키움증권, 신한증권, 미래에셋증권, 한국투자증권)

## 1. 먼저 결론

- 코인 거래소와 증권사는 연결 구조가 다릅니다.
- 코인은 API Key/Secret 중심이라 비교적 단순합니다.
- 증권사는 브로커별 인증 체계, OS 제약, 라이브러리 제약이 있어 실패 요인이 더 많습니다.

## 2. 공통 사전 점검

1. NoahAI 버전이 v3.8.9.22 이상인지 확인
2. 설정 저장 후 앱 재시작
3. settings 파일에서 값 반영 여부 확인
4. 방화벽/백신이 앱 네트워크 호출을 차단하지 않는지 확인

앱 내 확인 경로(사용자 기준):

1. 대시보드 → 설정(거래소 API)
2. `증권 연결 점검` 클릭
3. `지원요약 복사` 또는 `파일로 저장` 클릭
4. `3분 점검본 저장` 클릭
5. 필요 시 `연결 실패 5분 점검 가이드 열기` 클릭

권장 확인 파일:

- data/<사용자계정>/config/settings.json

## 3. 키움증권 점검

## 3.1 필수 조건

1. Windows 환경에서 실행 중인지 확인
2. 키움 OpenAPI+ 설치 완료
3. PyQt5, pykiwoom 설치 확인
4. Python 비트수와 OpenAPI 비트수 정합 확인

권장 조합:

- 키움 OpenAPI+ 실연결은 현재 앱 경로 기준으로 Windows 32bit Python 3.11.x 조합을 우선 권장

## 3.2 설정 권장값

1. API 연결 방식: openapi
2. API 버전: pykiwoom
3. 계정 ID, 비밀번호, 계좌번호 입력
4. 저장 후 앱 재시작

## 3.3 실패 시 즉시 분기

1. mock 모드로 전환 후 연결 테스트
2. mock 성공 + openapi 실패면 환경 제약(설치/비트/OCX) 이슈 가능성 높음
3. KOA Studio 단독 로그인 성공 여부 먼저 확인

## 3.4 ActiveX 실패가 로그에 찍히는 경우(확정 패턴)

아래 문구가 반복되면, 입력값 문제가 아니라 키움 런타임(OCX/COM) 초기화 실패입니다.

- `KHOpenAPI ActiveX 로딩 실패 또는 이벤트 바인딩 실패`
- `setControl=False, OnReceiveTrData=False`
- `최근 실패 사유: activex_control_probe_failed`

이 경우 사용자 실행 순서:

1. 키움 OpenAPI+를 관리자 권한으로 재설치
2. KOA Studio에서 단독 로그인 성공 확인
3. Python 비트수와 OpenAPI 비트수 정합 확인(로그의 `python_bits` 참고)
4. NoahAI 재실행 후 `증권 연결 점검` 재확인
5. 실패 지속 시 `지원요약` + `3분 점검본` + 실패 시각을 함께 전달

## 4. 미래에셋증권 점검

## 4.1 핵심 포인트

- 미래에셋은 REST/OpenAPI 설정 조합을 사용하며, app_key/app_secret 반영 여부가 중요합니다.

## 4.2 설정 권장값

1. API 연결 방식: openapi 또는 rest
2. API 버전: miraemts 또는 운영 정책상 허용 버전
3. 미래에셋 ID/비밀번호/계좌번호 입력
4. 저장 후 앱 재시작

## 5. 한국투자증권 점검

## 5.1 핵심 포인트

- 한국투자증권(KIS)은 REST API 기반이며 Windows/macOS 점검 경로를 사용합니다.
- app_key/app_secret 또는 대응 저장값 누락 시 토큰 발급이 실패합니다.

## 5.2 설정 권장값

1. API 연결 방식: rest
2. API 버전: kis
3. KIS 앱 키/시크릿 또는 대응 ID/비밀번호/계좌번호 입력
4. 저장 후 앱 재시작

## 4. 신한증권 점검

## 4.1 핵심 포인트

- 신한 어댑터는 토큰 발급에 app_key/app_secret을 사용합니다.
- v3.8.9.22에서 설정 저장 시 id/password를 app_key/app_secret에 동기화 저장하도록 보강했습니다.

## 4.2 설정 권장값

1. API 연결 방식: openapi 또는 rest
2. API 버전: solapi (또는 운영 정책상 허용 버전)
3. 신한 ID/비밀번호/계좌번호 입력
4. 저장 후 앱 재시작

## 4.3 저장값 실제 확인

settings.json에서 아래 값 확인:

1. stock_broker_configs.shinhan.api_type
2. stock_broker_configs.shinhan.api_version
3. stock_broker_configs.shinhan.app_key
4. stock_broker_configs.shinhan.app_secret

주의:

- app_key/app_secret이 비어 있으면 토큰 발급이 실패합니다.

## 6. 코인과 왜 다른가

1. 코인: API Key/Secret + 거래소 REST/WS 중심
2. 증권사: 브로커 전용 인증, 전용 SDK/런타임, 계정 정책, 주문 보호정책 동시 적용
3. 따라서 "설정만 맞으면 항상 즉시 연결"이 아니라, 브로커 환경 요건도 함께 만족해야 합니다.

## 7. 운영팀 표준 진단 순서

1. mock 연결 성공 여부 확인
2. 설정 저장값(settings.json) 확인
3. 브로커 전용 환경 요건 확인
4. 실연결 재시도
5. 실패 로그 수집 후 원인 분류

## 8. 성공 기준

- 연결 성공 로그 확인
- 계좌/잔고 조회 API 1회 이상 성공
- 주문은 실전 허용 플래그 OFF 상태에서 조회 경로부터 먼저 검증

## 9. 여전히 실패하면

아래 4개를 함께 수집해 이슈 등록:

1. 앱 버전
2. 사용 브로커, api_type, api_version
3. settings.json의 해당 브로커 항목(민감정보 마스킹)
4. 실패 시각 전후 로그 100줄

전달 템플릿(복붙용):

- 현상: 키움 OpenAPI ActiveX 로딩 실패 반복
- 실패 패턴: setControl=False / OnReceiveTrData=False / activex_control_probe_failed
- 확인 결과: mock은 가능, openapi 실패(해당 시)
- 첨부: support_report + 3min_checklist + 실패시각 전후 로그
