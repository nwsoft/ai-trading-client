# 3.9.2.3 금융상품 공급·상담 연결 운영 계약

작성/검증 대상: 2026-10-03 로컬 소스. 실제 금융기관·상담사 등록, 외부 전송, 공개 배포는 실행하지 않았다. 아래 예시는 `example.org` 합성 주소이며 운영에 그대로 활성화하지 않는다.

## 상담사 또는 기관 API 등록

계정 데이터 디렉터리의 `finance_recipients.json`에 운영자가 검토한 수신처를 등록한다. 직접 상담사 방식은 `manual`, 서버 방식은 `api`다. 같은 요청을 두 방식으로 동시에 보내지 않는다. API 공급사별 원래 형식은 기관 측 어댑터에서 아래 정규화 계약으로 변환한다.

```json
[
  {
    "id": "reviewed-advisor",
    "name": "지정 상담 담당자",
    "organization": "검토한 수신 기관",
    "role": "보험 견적 상담",
    "kinds": ["insurance"],
    "mode": "manual",
    "enabled": false,
    "review_reference": "수신 권한·연락처·처리 목적 검토 기록",
    "contract_version": "review-1",
    "privacy_url": "https://example.org/privacy",
    "contact_url": "https://example.org/contact",
    "retention_days": 30,
    "commercial_notice": "제휴·수수료 관계에 대한 실제 안내"
  }
]
```

```bash
# 검증만 수행. 기본 동작은 파일 변경/네트워크 호출 없음.
python scripts/configure_finance_recipients.py --data-directory <account-data> --registry <reviewed.json>
# 검토한 설정을 백업·원자 교체하여 적용
python scripts/configure_finance_recipients.py --data-directory <account-data> --registry <reviewed.json> --apply
```

API 방식은 `endpoints: {submit,status,withdraw}`와 `token_env`를 추가한다. 세 주소는 동일한 HTTPS 호스트/443이어야 한다. 토큰은 JSON에 넣지 않고 `NOAHAI_FINANCE_...` 환경 변수 이름만 기록한다. DNS에서 사설/로컬 주소가 나오면 차단하며, 검증한 IP로 연결하면서 원래 호스트의 TLS 인증서를 확인한다. 리다이렉트는 따라가지 않는다. 응답 크기는 128 KiB, 연결/읽기 제한 시간은 10초다.

| 작업 | 정규화 API 계약 |
|---|---|
| 접수 | `POST submit`, JSON 상담 packet, `Idempotency-Key: request_id` |
| 결과 확인 | `GET status?request_id=...`, 같은 요청 ID |
| 철회 | `POST withdraw`, `{request_id,receipt_id}`, `Idempotency-Key: request_id:withdraw` |
| 응답 | `{request_id,status,receipt_id}`. 요청 ID 일치 필수. 성공 HTTP 200/201/202라도 확인 가능한 상태·접수번호가 없으면 접수 확정하지 않음 |
| 확인 상태 | `received`, `in_consultation`, `closed`, `withdrawn`, `deleted` |
| 전송 결과 불명 | 상태 조회에서 `not_found`가 확인된 경우에만 동일 idempotency key로 다시 제출 가능 |

기관은 idempotency key를 실제로 중복 방지하고, 상태 조회에 일관된 결과를 반환해야 한다. 이 계약은 로컬 시험용 전송기로 검증했으며 특정 기관의 실서비스 호환 인증은 아니다. 실제 사용 전 기관 샌드박스에서 지연 접수·응답 유실·중복·철회·삭제 의미를 검증한다. 기관별 원래 인증 방식/응답이 다르면 어댑터가 추가로 필요하다.

## 사용자 흐름과 정보 보호

1. 암호화 보관함을 열고 수신처를 선택한다. 수신처 미지정은 준비 저장만 가능하다.
2. 요약/비교/선택 프로필/연락처를 선택한다. 기본은 요약만. 건강정보·보험 원문·계좌 전체 자료를 자동 첨부하지 않는다. 자유 입력 메모·보장 설명에 본인이 넣은 개인정보는 전체 내용 미리보기에서 확인한다.
3. 서버가 다시 계산한 실제 공유 packet을 표시한다. 수신처·계약 버전·내용 hash에 묶인 별도 동의를 기록한다. 동의는 7일 후 만료하며 수신처 변경 시 새 준비가 필요하다.
4. `manual`: 파일 받기 → 지정 상담사 안내 → 직접 전달 → 상담사가 준 접수번호를 직접 기록. 파일 저장/링크 열기는 접수가 아니다. 직접 기록한 번호/종료·철회는 `user_reported`이며 기관 API 검증과 구분한다.
5. `api`: 전송 버튼 → 전송 중 체크포인트 저장 → 응답 ID/접수번호 확인. 응답 유실은 `delivery_unknown`. 앱 종료 후에도 전송 중 상태를 보존하고 맹목적으로 재전송하지 않는다.
6. 철회 시 로컬 동의를 즉시 없앤다. 기관 요청 제한 시간·대기·설정 해제 중에도 `withdrawal_requested`를 보존한다. 기관 삭제 완료는 별도의 `deleted` 응답이 있어야 한다. 이전 수신처 안내는 암호화된 준비 스냅샷에 남는다.
7. 사용자는 로컬 준비/종료/철회 기록을 삭제할 수 있다. 로컬 삭제가 기관 자료 삭제를 뜻하지 않는다.

상담 기록은 기존 계정별 암호화 vault에 저장하며 최대 100건, 이벤트는 건별 최근 50개다. 전송 실패 재시도는 지수 간격/최대 1시간, 확인 후 최소 5초다. 백그라운드로 무한 발송하지 않는다. 목록은 잠금·계정 변경 때 지우고 기존 보관함 자동 잠금을 따른다. `retention_days`는 **수신처 보관 안내**이며 이 PC 기록을 자동 삭제하는 타이머가 아니다. 로컬 보관은 사용자 삭제/기존 암호화 백업 정책을 따른다.

## 상품 공급 API

`finance_product_sources.json`의 정규화 스냅샷 API는 실제 공급권을 확인한 후 등록한다. API 권한·약관 재배포권·AI 처리권은 서로 구분한다.

```json
[
  {
    "id": "reviewed-source",
    "url": "https://example.org/disclosure",
    "rights_verified": true,
    "rights_reference": "별도 보관한 실제 이용 계약 검토 참조",
    "ai_processing_allowed": false,
    "api_url": "https://example.org/noah-normalized-products",
    "token_env": "NOAHAI_FINANCE_SOURCE_TOKEN",
    "enabled": false,
    "interval_seconds": 86400
  }
]
```

응답은 `{source_id,products:[...]}`의 **완전 스냅샷**이다. 다중 페이지 API는 어댑터에서 전체 페이지 검증 후 이 형식으로 전달한다. 기관 원래 API URL만 넣으면 임의 형식을 자동 이해하는 기능이 아니다. 각 상품의 필수 필드는 `id,name,provider,kind,version,source_url,verified_at,valid_until,status,terms`. 시각은 시간대 있는 ISO, 상태는 active/withdrawn, kind는 loan/insurance/savings다. optional `evidence`는 `id,text,page,clause,source_url`을 가진 근거 문단 최대 50개다.

- HTTPS 인증과 검토 설정을 신뢰 경계로 사용한다. 중앙 배포 서명/공용 DB 운영을 구현했다고 주장하지 않는다.
- 원자적 공급원 교체, 중복 ID/기한/수치 검증, 마지막 정상본 보존, 제한 재시도, 갱신·복원의 공유 잠금이 적용된다. 원시 오류·토큰·파일 경로는 사용자 응답에서 숨긴다.
- 한 요청에서 최대 3개 공급원을 갱신한다. 최초/예정 갱신은 화면 접근 또는 CLI 실행 시 동작한다. 상시 스케줄은 운영자가 별도로 설정해야 한다.
- 깨진 설정 때문에 수동 견적 비교까지 막지 않는다. 화면에 공급 설정 점검 상태와 이전 유효 자료를 남긴다.
- 복원 후 자동 갱신 중지. 재개는 검토자가 명시한다. 복원해도 과거 상품의 만료시각을 최신 시각으로 고치지 않는다.

```bash
python scripts/refresh_finance_sources.py --data-directory <account-data> --validate-only
python scripts/refresh_finance_sources.py --data-directory <account-data>
python scripts/refresh_finance_sources.py --data-directory <account-data> --resume-source <reviewed-source>
python scripts/import_finance_product_catalog.py --database <account-data>/finance_product_catalog.sqlite3 --rollback-revision <reviewed-revision>
```

## 수치·규칙·약관 근거

`terms`는 기존 직접 확인 금리/비용/세율 외에 다음을 받는다.

| 필드 | 의미 |
|---|---|
| `base_rate`, `max_rate`, `rate_bonuses` | 기본금리 + `condition,percentage_points`별 확인한 우대, 전체 금리 상한. 확인하지 않은 우대는 얻은 금리로 계산하지 않음 |
| `eligibility` | age/annual_income/credit_score/housing_count의 min/max. 누락은 조건부, 불충족은 제외, 확인해도 승인 확정 아님 |
| `documents`, `channels`, `application_url` | 해당 기관 자료의 서류·채널·공식 상세 링크. 링크 열기는 가입 접수 아님 |
| `tax_rule` | id/version/scope/source_url/effective_from/valid_until/reviewed/tax_rate/required_confirmations. 적용일·자격이 없으면 세후 계산 보류 |
| `lending_rules` | 같은 규칙 메타데이터 + metric(dsr/ltv), cap_percent, context. context는 borrower_type/region/loan_purpose/institution_sector/rate_type 중 명시한 정확한 값. 지역·차주·일자 불일치 시 규정 비율 보류 |
| 예금보호 | institution_id/protection_scheme=`kr_general_deposit`/protection_confirmed/eligible_protection_interest. 사용자도 동일 회사 기존 보호상품 합산액과 확인 여부를 제공해야 계산 |

규정 DSR은 단순 월 상환액×12를 임의로 사용하지 않는다. 기관이 확인한 규정상 **전체 연간 원리금 산정액**과 연 소득을 별도로 입력해야 한다. LTV도 신규 포함 규정상 담보부채 합계와 담보가치가 필요하다. 각 규칙의 모든 법정 예외를 자동 수집·해석하는 엔진이 아니며, 현재 실제 기관 규칙 묶음은 미등록이다.

일반 예금보호 참조는 [금융위원회 공식 안내](https://www.fsc.go.kr/no040101?cnId=2869)의 2025-09-01 시행 내용을 근거로 한다. 코드 확인일은 2026-10-03, 재검토 기한 2026-11-02이며 후자는 법의 만료일이 아닌 내부 자료 점검일이다. 대상 상품/기관/소정 이자가 불명확하면 한도 계산을 보류한다. 특별 보호·비보호·모든 기관 예외까지 일반 규칙으로 확정하지 않는다.

변동금리/부분인출은 사용자가 확인한 값으로 계산한 **가정**이다. 부분인출은 월말·선납입 원금 우선, 인출분 확인 금리 단리, 잔액은 선택 이자방식 유지, 건별 확인 비용이다. 중간 수령 포함 총액과 만기 잔액을 구분하고, 전체 해지/만기 분산과 동시에 혼합하지 않는다. 기관별 실제 일수·우대 상실·복잡한 해지 산식은 기관 약관 대조가 필요하다.

## AI와 후속 점검

로컬 후속 질문은 여러 금액/기간을 항목명으로 구분해 수정하고 계산한다. 애매한 변경·음수는 임의 해석하지 않는다. 문단 검색은 현재 유효한 자료만 검색하며 버전·쪽수·출처를 반환한다. 원문 문단은 모델 명령이 아니다.

`ai_preview`는 **모델 호출 없이** provider/model/실제 전송 내용/hash를 보여준다. `ai_explain`은 같은 내용·모델에 대한 명시 동의가 있어야 호출한다. 수치/공개 근거를 따로 선택하며 `ai_processing_allowed=true` 출처만 외부 근거 문맥에 포함한다. 보험 원문·건강정보·연락처를 자동 읽지 않는다. 질문에 직접 입력한 개인정보는 전송 미리보기에서 사용자가 제거할 수 있다. 외부 AI 설명은 계산값을 덮어쓰거나 일반 캐시에 저장하지 않으며 기존 사용량/예산 한도를 적용한다. 새 수치·보장/승인 확정 표현을 발견하거나 연결 실패하면 로컬 설명을 반환한다. 이 제한 검사는 모든 환각을 검증하는 전문 심사 장치가 아니다.

암호화 저장 비교에는 재점검일, 견적 기한 만료, 상품 버전 변경·판매 종료 검토 사유를 표시한다. 앱 안에서 보관함을 열었을 때 확인하는 방식이며 외부 문자/메일/상담사 자동 통지는 없다.
