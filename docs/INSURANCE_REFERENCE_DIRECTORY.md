# 보험 내부 탐색 자료 운영 — 3.9.2.4

## 자료 계약과 초기 범위

공식 안내의 상품명과 짧게 직접 작성한 특징 설명을 제공한다. 보험다모아 표·사진·보험료를 복제하거나 제휴/재배포 권리를 확보했다고 표시하지 않는다. 초기 4개 회사·7개 상품은 2026-10-04 확인, 2026-11-03 재확인 기한이다. 실시간 판매 여부와 개인별 가입 가능 여부는 미확인이다. 목록 순서는 추천 순위가 아니다.

| 회사 | 상품 | 근거 |
|---|---|---|
| 삼성화재 | 무배당 삼성화재 다이렉트 운전자보험 | [공식 안내](https://direct.samsungfire.com/mall/PP030301_001.html?ver=59) |
| 현대해상 | 다이렉트 운전자보험 | [공식 안내](https://direct.hi.co.kr/service.do?m=c91a5781ba) |
| DB손해보험 | 다이렉트 운전자보험 (안내 표시명) | [공식 안내](https://www.directidb.co.kr/) |
| 현대해상 | 다이렉트 실손의료비보장보험 | [공식 안내](https://direct.hi.co.kr/service.do?m=ddd18946bf) |
| 삼성화재 | 무배당 삼성화재 다이렉트 건강보험(자동갱신형) | [공식 안내](https://direct.samsungfire.com/mall/PP030401_001.html?ver=40) |
| 삼성화재 | 무배당 삼성화재 다이렉트 비갱신 건강보험(해약환급금 미지급형Ⅱ) | 위 공식 안내의 별도 상품 |
| 교보라이프플래닛 | (무)라이프플래닛 e정기보험Ⅱ | [공식 안내](https://www.lifeplanet.co.kr/products/dth/HPPC61S0N.dev) |

안내 페이지에서 확인한 정보이며 상품 안내 표시명이 정식 계약명과 다를 수 있다. 해당 항목은 세부 확인 질문에 기록한다. 보험료 예시·광고 할인율·최대 보장액을 개인 조건으로 옮기지 않는다. 보험다모아 직접 접근은 403이어서 전체 최신 목록 수집 근거로 사용하지 않았다.

## 저장과 갱신

기존 계정별 `finance_product_catalog.sqlite3`의 `insurance_references` 테이블에 저장한다. `products` 및 rights_verified 기반 공급사 피드와 별도다. `snapshot.reference_products`로만 반환하고 `current_count`/실제 비교 후보/최적 후보에는 넣지 않는다. 외부 AI에 요약 본문을 자동 첨부하지 않는다.

필드: id, provider, name, category(driver/medical/cancer/income), source_url(HTTPS), coverage, renewal, checks, version, observed_at, review_due, status(listed/withdrawn). 보험료 필드는 허용하지 않는다. 확인일부터 재확인 기한까지 최대 90일, 미래 확인일 거절. `listed`는 안내 목록 상태이며 판매 확인 의미가 아니다.

검토한 변경 자료를 JSON 배열로 작성한 뒤 다음 명령으로 반영한다. 원본 예시는 `trading/insurance_reference_directory.py`의 BUNDLED이며 실제 내용과 확인일을 검토 후 바꾼다.

```sh
.venv/bin/python scripts/import_insurance_references.py \
  --database /절대경로/계정/finance_product_catalog.sqlite3 \
  --snapshot /절대경로/검토한-상품-안내.json
```

일괄 검증 후 원자적으로 upsert한다. 파일에 없는 상품은 삭제하지 않는다. 판매 종료/목록 철회는 동일 ID에 status=withdrawn으로 명시한다. 운영자가 수정·철회한 레코드는 기본 내장 자료로 되돌아가지 않는다. 앱의 상품 자료 새로 확인 또는 화면 재진입으로 DB 변경을 읽는다. 버튼만으로 보험회사 사이트를 재수집하거나 확인일을 연장하지 않는다.

재확인 기한이 지난 자료는 `review_due`로 표시하고 신규 관심 선택을 막는다. withdrawn은 탐색에서 숨긴다. 이전 상담 준비의 관심 상품은 재조회 시 stale/withdrawn/unavailable 상태를 보존하며 유효 견적으로 간주하지 않는다. 보관함 저장·전송에는 기존 암호화/미리보기/동의 경계를 적용한다.

## 확장 경계

실제 상품 조건 피드는 기존 권리 검토 API 커넥터/카탈로그 수집기를 사용한다. 초기 탐색 자료 등록은 그 권리 검토를 대신하지 않는다. 전체 시장 자동 갱신, 개인별 보험료·심사·가입 API는 아직 연결하지 않았다. 공개 사이트의 화면을 임베드하여 내부 처리라고 표시하지 않는다. 현재 모든 탐색·필터·비교표는 앱 내부에서 수행한다.
