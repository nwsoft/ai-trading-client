# Zenodo Upload Runbook (Step-by-Step)

이 문서는 NoahAI 논문 패키지를 Zenodo에 업로드할 때 그대로 따라할 수 있도록 만든 실무 절차서다.

## 목적

- 업로드 전에 해야 할 준비를 완료한다.
- Zenodo 업로드 중 입력해야 할 값을 미리 확정한다.
- 업로드 후 DOI를 문서에 반영한다.

## 중요한 원칙

- Zenodo가 먼저다. (아카이브 + DOI)
- arXiv는 Zenodo DOI 발급 후 진행한다.
- 과학 내용은 같은 버전을 유지한다.

## A. 업로드 전 준비 (지금 바로 가능)

### A-1. 파일 준비

다음 파일이 준비되어 있어야 한다.

- NOAHAI_DAL_FINANCIAL_DECISION_PREPRINT_2026.md
- NOAHAI_DAL_FINANCIAL_DECISION_PREPRINT_2026_EN.md
- SUBMISSION_GUIDE.md
- ROADMAP.md
- ZENODO_METADATA_DRAFT.md
- ARXIV_SUBMISSION_CHECKLIST.md
- FINAL_PACKAGE_STATUS.md

### A-2. 메타데이터 값 확정

다음 값을 복사해 Zenodo 입력에 사용한다.

- Title: NoahAI-DAL: A Governable Financial Decision Architecture with XAI and Risk Governance
- Creator: JUNG HAESUNG
- Affiliation: Dream AI Lab, NoahAI Labs
- Version: v1.0
- Publication date: 2026-06-05
- Keywords:
  - financial decision AI
  - DAL
  - explainable AI
  - risk governance
  - decision logging
  - human-in-the-loop
- Description:
  - Preprint archive for the NoahAI-DAL manuscript package. Includes Korean and English companion versions, references, and supporting submission notes.
- License (권장): CC BY 4.0

### A-3. 상태표 확인

업로드 직전 체크:

- FINAL_PACKAGE_STATUS.md에서 Core Manuscript Lock 완료 여부 확인
- Zenodo metadata/version/bundle finalized 항목 확인

## B. Zenodo 업로드 절차 (클릭 순서)

### B-1. 새 레코드 생성

- Zenodo 로그인
- New upload 선택
- Upload type을 preprint 또는 publication 성격에 맞게 선택

### B-2. 파일 업로드

- A-1 목록 파일을 모두 업로드
- 파일명 오타 여부 확인
- 영문/한글 문서가 모두 들어갔는지 확인

### B-3. 메타데이터 입력

- Title 입력
- Creator 입력
- Affiliation 입력
- Description 입력
- Keywords 입력
- Version 입력
- Publication date 입력
- License 선택

### B-4. 최종 검토

- 제목, 저자, 버전, 날짜를 다시 확인
- Description 문구가 내부 메모처럼 보이지 않는지 확인
- 파일 누락 여부 재확인

### B-5. Publish

- Publish 실행
- 발급된 DOI 기록

## C. 업로드 직후 해야 할 일

### C-1. DOI 기록

발급 DOI를 다음 문서에 반영한다.

- FINAL_PACKAGE_STATUS.md
- SUBMISSION_GUIDE.md
- 필요 시 NOAHAI_DAL_FINANCIAL_DECISION_PREPRINT_2026_EN.md 메모 섹션

### C-2. 상태표 업데이트

FINAL_PACKAGE_STATUS.md에서 다음 항목을 체크한다.

- DOI issued
- DOI back-linked in docs

## D. 실패/수정 시 처리

- 메타데이터 오타 수정이 필요하면 Zenodo 편집 가능 범위에서 정정
- 과학 내용이 바뀌면 기존 레코드 덮어쓰기 대신 새 버전 발행
- 버전 변경 시 v1.1, v1.2처럼 명시

## E. arXiv로 넘어가는 조건

다음 조건이 모두 충족되면 arXiv를 진행한다.

- Zenodo DOI 발급 완료
- DOI가 문서에 반영 완료
- 영문 제출본 문구 최종 고정 완료
- arXiv 체크리스트 준비 완료

## 빠른 요약

- 업로드 전에 할 수 있는 준비: 거의 전부 가능
- 실제 업로드에서 필요한 작업: Zenodo 입력/게시와 DOI 확인
- 권장 순서: Zenodo 먼저, arXiv 나중
