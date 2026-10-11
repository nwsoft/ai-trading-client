# 3.9.2.11 준비: 사이트 버전 정합성 인계

확인일: 2026-10-11. **현재 공개 클라이언트는 3.9.2.10, 다음 Windows 빌드 소스 후보는 3.9.2.11**이다. 이 작업은 사이트 패치를 준비·로컬 검증한 것이며 운영 웹사이트를 게시하지 않았다. Windows 설치기 배포와 웹사이트 배포는 별개다. 사이트 갱신 대기를 테스터 설치기 전달의 필수 조건으로 추가하지 않는다.

## 수정본과 기준

|대상|확인한 기준|준비한 수정본|
|---|---|---|
|회사 noahailabs.com|원격 main `552a2f2a07dcd9839722896b20872b6b8ed5946e`, 운영과 같은 .8 기준|[최신 운영 소스 기반 작업 폴더](../../Noahailabs/reports/v39211-public-alignment-20261011/operating-source/README.md): .10 기능·4언어 릴리스·상품 상태·다운로드·백서·llms·sitemap 정합|
|정보 info.noahai.net / IP ip.noahai.net|운영 서버의 대상 6개 파일 SHA-256이 로컬과 일치하는 것을 읽기 전용 확인|[정보 사이트 FAQ](../../infonoahai/noahai-info/src/app/faq/page.tsx), 공통 제품 범위·위키·llms·변경 URL 날짜: .10 공개/.11 후보, 국면 질문·무거래·배포 후 테스터 검증 안내|
|제품 noahai.net|운영 JSON은 공개 .8/준비 .9, 로컬 JSON은 준비 .5로 더 오래됨|[운영본 기준 검토 파일](../reports/v39211-tester-handoff-20261011/portal-reviewed/product-facts.json): 4언어 8개 항목·허브 제한을 보존하고 .10 공개/.11 후보를 정합. llms의 과거 보험 미출시 표기도 갱신|

회사 사이트의 기존 `Noahailabs/` 루트는 .3 기준에 사용자 변경이 있어 덮어쓰지 않았다. 배포 담당자는 위 최신 운영 소스 작업 폴더의 패치를 검토·병합해야 한다. 오래된 루트를 그대로 배포하면 이전 안내로 되돌아갈 수 있다. 제품 포털도 오래된 로컬 파일 전체를 운영본에 덮어쓰지 않고 검토 패치의 대상 항목만 적용한다.

패치·파일별 해시·검사 결과: [현재 검증 기록](../reports/v39211-tester-handoff-20261011/validation.json). 클라이언트 문서, 회사, 정보, 제품 포털의 패치를 따로 제공하며 사이트 패치를 Windows 클라이언트 저장소에 적용하지 않는다.

## .11 게시 후 전환

1. 사용자 Windows PC에서 새 빌드·기본 설치 확인 후 릴리즈하고 실제 .11 stable 태그·manifest·설치기·blockmap·latest.yml·원격 digest를 확인한다.
2. 회사 사이트의 검토된 릴리스 기능·4언어 설명·sourcePath를 .11로 갱신한 뒤 `npm run sync:release`, `npm run test:release-docs`, `npm run check:public-data`, `npm run build`를 실행한다. 현재 sync는 검토되지 않은 새 버전을 만나면 기존 검토 버전을 유지하므로 기능 목록 없이 번호만 자동 승격하지 않는다.
3. 정보/IP FAQ·공통 범위·위키·llms와 제품 포털의 publicVersion·다음 후보 상태를 같은 공개 근거로 갱신한다. .11을 공개판과 다음 후보에 동시에 남기지 않는다. 실제 수집·색인·AI 인용은 검색 서비스에서 별도로 확인한다.
4. 각 웹사이트를 별도 게시한 뒤 실제 URL의 본문·다운로드·canonical·llms·sitemap을 GET하여 확인한다. 로컬 빌드 통과를 운영 게시 완료로 기록하지 않는다.

## 테스터 운용

테스터는 설치본을 받은 뒤 PAPER 24시간, 필요 시 72시간을 검증한다. 운영자가 기관·모드·보류 수치·시각·장애/복구와 다음 조치를 취합한다. 외부 인수 대기는 manifest에 유지하며 그 자체로 stable 게시를 차단하지 않는다. [Windows 명령·담당·기록 양식](V39211_WINDOWS_TESTER_HANDOFF.md).
