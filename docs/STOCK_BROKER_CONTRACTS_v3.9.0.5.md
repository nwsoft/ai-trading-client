# NoahAI v3.9.0.5 증권사 API 계약·실행 권한 정본

작성일: 2026-08-01  
적용 범위: 키움증권, 신한증권, 미래에셋증권, 한국투자증권, 설정 UI, 자동매매, 사용자 문서

## 1. 지원 계약 정본

| 증권사 | 설정 `api_type` | 설정 `api_version` | 실제 계약/드라이버 | 실행 조건 |
|---|---|---|---|---|
| 키움증권 | `openapi_plus` | `pykiwoom` | 키움 OpenAPI+ OCX를 pykiwoom으로 호출 | Windows, OpenAPI+ 설치·사용등록, 로그인·계좌 연결 |
| 신한증권 | `partner_rest` | `shinhan_openapi_v2` | 신한 Open API v2 제휴 계약 프로필 | 제휴 client id/secret, 채널, 운영 URL, 엔드포인트 프로필 |
| 미래에셋증권 | `partner_rest` | `mirae_partner_profile` | 미래에셋증권 제휴 API 계약 프로필 | 제휴 API 키, 운영 URL, 인증·엔드포인트 프로필 |
| 한국투자증권 | `rest` | `kis_openapi_v1` | KIS Developers Open API REST | 앱키/앱시크릿, 8+2자리 계좌, 실전 또는 모의 서버 |
| 공통 테스트 | `mock` | `mock` | NoahAI 내부 모의 어댑터 | 외부 주문 없음 |

`pykiwoom`은 증권사 API 상품명이 아니라 키움 OpenAPI+ 호출 드라이버다. `XingAPI`는 LS증권 API이므로 신한 선택지로 취급하지 않는다. KIS Developers는 한국투자증권 계약이며 미래에셋 경로로 재사용하지 않는다.

## 2. v3.9.0.5 자동 설정 이전

앱 시작 시 레거시 `api_type/api_version`을 다음과 같이 이전한다. 인증값·계좌번호·자산유형은 보존한다.

| 과거 값 | 이전 값 | 추가 조치 |
|---|---|---|
| 키움 `openapi/pykiwoom`, `openapi/kiwoom_api` | `openapi_plus/pykiwoom` | 비공식 별도 선택지 제거 |
| 신한 `openapi/solapi`, `rest/solapi_rest` | `partner_rest/shinhan_openapi_v2` | 제휴 프로필 적용 필요 |
| 신한 `openapi/xingapi` | `partner_rest/shinhan_openapi_v2` | LS증권 오분류이므로 신한 enabled/LIVE만 OFF, 인증값은 보존 |
| 미래에셋 `openapi/miraemts`, `openapi/miraedaas`, `rest/kis` | `partner_rest/mirae_partner_profile` | 미래에셋 제휴 프로필 적용 필요 |
| 한국투자 `rest/kis`, `openapi/kis` | `rest/kis_openapi_v1` | KIS 공식 계약으로 통일 |

이전 원본 표기는 `_legacy_stock_api_migrations`에 민감정보 없이 남긴다.

## 3. PAPER / LEARNING / LIVE 결정 규칙

실행 모드는 아래 순서로 하나만 결정한다.

1. `paper_trading=true` 또는 어댑터가 `mock`이면 무조건 `PAPER`다.
2. PAPER가 아니고 LIVE 조건 중 하나라도 거짓이면 `LEARNING`이다. 분석·신호·주문계획은 만들지만 외부 주문을 전송하지 않는다.
3. 아래 조건이 모두 참일 때만 `LIVE`다.
   - 전역 `enable_stock_live_order=true`
   - 해당 증권사 `stock_broker_configs.<broker>.allow_live_order=true`
   - 해당 어댑터의 연결·계좌·계약 프로필 준비상태가 정상
   - 기존 주문 가드레일·장시간·위험한도 통과

즉 권한식은 다음과 같다.

`LIVE = NOT PAPER AND GLOBAL_LIVE AND BROKER_LIVE AND ADAPTER_READY AND GUARDRAILS_PASS`

전역 또는 증권사별 토글 하나만 켜서는 LIVE가 되지 않는다.

## 4. 어댑터별 호출 계약

### 키움 OpenAPI+

- 연결: `CommConnect`, `GetConnectState`, `GetLoginInfo`
- 조회: 공식 TR 코드의 `block_request`
- 주문·취소: `SendOrder`
- 실행 직전: Windows/OCX/로그인/계좌/`SendOrder` 준비상태 확인

### 한국투자 KIS

- 토큰: `/oauth2/tokenP`
- 공통 헤더: `authorization`, `appkey`, `appsecret`, `tr_id`, `custtype=P`
- 현재가: `FHKST01010100`
- 잔고: 실전 `TTTC8434R`, 모의 `VTTC8434R`
- 현금주문: 실전 매수/매도 `TTTC0012U`/`TTTC0011U`, 모의 `VTTC0012U`/`VTTC0011U`
- 정정취소: 실전 `TTTC0013U`, 모의 `VTTC0013U`
- API 응답에 성공코드와 주문번호가 함께 없으면 성공으로 기록하지 않는다.

### 신한·미래에셋 제휴 API

운영 URL과 세부 거래 엔드포인트를 추정값으로 하드코딩하지 않는다. 증권사와 체결한 계약에서 받은 `partner_profile`을 사용한다.

- 신한: `dataHeader/dataBody`, `apikey`, HMAC-SHA256 `hsKey`, Bearer 토큰 지원
- 미래에셋: 계약별 base/sandbox URL, token path, 인증 헤더, endpoint map, success code 지원
- 필수 프로필이 빠지면 잘못된 외부 URL로 전송하지 않고 설정 미완료 사유를 표시한다.

설정 화면의 `제휴 계약 프로필 JSON`에는 증권사가 제공한 값만 입력한다. 아래는 필드 구조 예시이며 URL은 예시값을 운영에 사용하면 안 된다.

```json
{
  "base_url": "https://증권사가-발급한-운영호스트",
  "sandbox_url": "https://증권사가-발급한-테스트호스트",
  "token_path": "/계약서의-토큰-경로",
  "sub_channel": "신한에서-발급한-채널코드",
  "endpoints": {
    "balance": "/잔고조회",
    "positions": "/보유종목",
    "price": "/현재가",
    "buy": "/매수",
    "sell": "/매도",
    "order": "/주문",
    "cancel": "/취소",
    "open_orders": "/미체결",
    "trade_history": "/체결내역"
  },
  "success_codes": ["0", "00"]
}
```

신한은 `buy/sell`을 사용하고 미래에셋 계약이 단일 주문 엔드포인트를 제공하면 `order`를 사용한다. 실제 필드명과 필수 작업은 계약서/개발가이드에 맞춰야 하며 비밀키를 이 프로필 JSON에 중복 기입하지 않는다.

## 5. 배포·검증 경계

- macOS 소스 테스트는 Windows 키움 OCX, 실제 증권 계좌 주문, 배포 EXE를 증명하지 않는다.
- Windows 빌드는 Windows PC에서 수행한다.
- 배포 후 각 증권사 계정으로 연결·조회·소액 주문·주문조회·취소·체결내역 순서의 운영 검증을 수행한다.
- 운영 검증 전에도 구현 경로를 영구 차단하지는 않는다. 다만 계약 프로필이나 연결상태가 없는 경로를 LIVE로 오판하지 않는다.

## 6. 공식 참고

- 키움증권 OpenAPI+: https://www1.kiwoom.com/h/customer/download/VOpenApiInfoView?dummyVal=0
- 신한 Open API 이용 절차: https://openapi.shinhan.com/use-step-info
- 신한 Open API 개발 가이드: https://openapi.shinhan.com/dev-guide
- 한국투자증권 KIS Developers: https://apiportal.koreainvestment.com/docs
- 한국투자증권 공식 샘플: https://github.com/koreainvestment/open-trading-api
- LS Open API(XingAPI 소유 구분): https://openapi.ls-sec.co.kr/about-openapi
