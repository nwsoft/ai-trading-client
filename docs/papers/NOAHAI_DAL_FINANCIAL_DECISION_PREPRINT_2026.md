# NoahAI-DAL: A Governable Financial Decision Architecture with XAI and Risk Governance

Preprint draft v1.0 · 2026-06-05

- Document ID: NOAHAI-PAPER-2026-001
- Author: JUNG HAESUNG
- Affiliation: Dream AI Lab, NoahAI Labs
- Author contribution: Originated the DAL concept and led the NoahAI implementation
- Submission note: Use the contribution line only when the target venue permits author-role disclosure; otherwise move it to acknowledgments or an internal provenance appendix
- Submission sequence: Archive the manuscript on Zenodo first, then submit the cited preprint version to arXiv
- Correspondence: noahailabs.com
- Related docs:
  - docs/technical/NOAHAI_TECHNICAL_WHITEPAPER.md
  - docs/guides/AI_LEARNING_CASE_STUDY_PUBLIC_V1.md

---

## Abstract

본 논문은 AI Digital Care Log(DAL)의 핵심 원리인 Decision-Log-Review-Learning 폐루프를 재테크 의사결정 운영에 확장한 NoahAI 아키텍처를 제안한다. 기존 자동매매/재테크 AI는 예측 정확도 중심으로 설명되는 경우가 많아, 운영 통제 가능성, 설명 가능성(XAI), 리스크 거버넌스 설계가 상대적으로 약했다. NoahAI는 의사결정 엔진, 표준화 로그, 인간 검토, 학습 루프를 분리 계층으로 설계하고, 정책 기반 리스크 제한과 감사 가능한 실행 이력을 결합한다. 본 문서는 시스템 설계와 운영 원리를 중심으로 기술하며, 정량 성능 주장보다 재현 가능한 구조와 검증 프레임을 제시한다. 향후 연구에서는 롤링 코호트 성능, 손실 제한 효과, XAI 신뢰도 지표를 포함한 외부 검증을 수행한다.

Keywords: financial decision AI, DAL, explainable AI, risk governance, decision logging, human-in-the-loop

---

## 1. Introduction

재테크 영역의 AI는 높은 기대와 높은 리스크를 동시에 만든다. 일반 사용자는 "왜 이 판단이 나왔는지", "언제 중단해야 하는지", "잘못된 판단이 반복되는지"를 확인하기 어렵다. 따라서 핵심 문제는 신호 생성 그 자체가 아니라, AI 판단을 운영 가능한 프로세스로 전환하는 아키텍처다.

NoahAI는 DAL 원리(Decision-Log-Review-Learning)를 금융 의사결정에 맞게 확장하여 다음 질문에 답하도록 설계되었다.

- AI 판단은 어떤 경로로 실행되며 어디서 통제되는가?
- 판단 근거는 사람이 사후 검토 가능한 형태로 남는가?
- 리스크 제한은 모델 성능과 분리된 정책 계층으로 동작하는가?

본 논문의 목적은 수익률 홍보가 아니라, AI 재테크 시스템의 운영 신뢰성을 위한 설계 원칙을 제시하는 것이다.

---

## 2. Problem Statement

기존 재테크 AI 제품은 다음 한계를 반복한다.

- 블랙박스 판단: 신호 출력은 있으나 근거 구조가 불명확함
- 운영 취약성: 상태 오염, 동시성 충돌, 장시간 운용 불안정
- 통제 취약성: 손실 제한 규칙이 모델 출력에 종속됨
- 감사 불가성: 의사결정-실행-결과의 연결 이력이 부족함

이 한계는 모델 성능 개선만으로 해결되지 않는다. 운영 계층의 구조화가 필요하다.

---

## 3. Core Contribution

본 논문의 기여는 다음과 같다.

- DAL 원리의 금융 확장
  - Decision-Log-Review-Learning 루프를 재테크 운영에 맞게 계층화
- XAI 운영화
  - 설명 문구 생성에 그치지 않고 검토/감사 프로세스에 결합
- 리스크 거버넌스 계층 분리
  - 진입/청산/중단/한도 정책을 모델과 분리하여 강제
- 운영 재현성 프레임
  - 버전, 설정, 로그 단위를 기준으로 재현 가능한 검증 절차 제시

---

## 4. NoahAI-DAL Architecture

### 4.1 Layer Overview

NoahAI는 다음 5계층으로 구성된다.

- Ingestion Layer
  - 시장 데이터, 거래소 상태, 사용자 설정, 정책 파라미터 수집
- Decision Layer
  - 모델 기반/규칙 기반 결합 판단
  - 시장 국면, 자산군, 리스크 상태를 반영한 후보 액션 생성
- Governance Layer
  - 리스크 정책 검증(포지션 한도, 손실 제한, 실행 중단 조건)
  - 통과 액션만 실행 계층으로 전달
- Execution and Logging Layer
  - 거래/시뮬레이션 실행
  - 판단 근거, 파라미터, 결과, 예외를 구조화 로그로 기록
- Review and Learning Layer
  - 사람 검토(운영자/사용자) + 사후 분석
  - 정책/프롬프트/파라미터 업데이트 루프로 환류

### 4.2 Decision-Log-Review-Learning Loop

- Decision: 현재 상태를 입력으로 AI/규칙이 액션 후보를 생성
- Log: 후보 생성 근거와 실행 결과를 표준 스키마로 저장
- Review: XAI 근거 및 결과를 기준으로 사람/시스템이 검토
- Learning: 검토 결과를 규칙/정책/모델 업데이트에 반영

이 루프는 "한 번 맞추는 모델"이 아니라 "운영 중 학습하는 시스템"을 지향한다.

---

## 5. XAI Operational Design

NoahAI의 XAI는 설명 출력 기능이 아니라 운영 기능이다.

### 5.1 Explanation Unit

각 의사결정 단위는 최소한 다음을 포함한다.

- 판단 시각과 버전
- 입력 상태 요약(시장/포지션/리스크)
- 선택 액션 및 대안 액션
- 주요 판단 근거(규칙, 지표, 모델 신호)
- 신뢰도/경고 수준

### 5.2 Review Workflow

- 실행 전: 위험 경고 조건 충족 시 사용자 확인 또는 자동 보류
- 실행 중: 정책 위반 감지 시 즉시 중단 또는 축소
- 실행 후: 결과와 근거를 연결해 회고 가능

### 5.3 Audit Readiness

- 로그 누락/변조를 줄이기 위해 이벤트 흐름을 표준화
- 사후 분석 시 "무엇을 왜 실행했는지" 추적 가능해야 함

---

## 6. Risk Governance Model

NoahAI 리스크 거버넌스는 모델 외부 정책 계층으로 정의된다.

### 6.1 Policy Categories

- Entry Control
  - 신규 진입 허용 조건, 동시 포지션 제한, 자산군별 노출 제한
- Exit Control
  - 손절/익절/시간 기반 청산 규칙
- Exposure Control
  - 계정/자산/거래소 단위 익스포저 한도
- Circuit Breaker
  - 연속 손실, 비정상 변동, 인프라 장애 시 자동 중단

### 6.2 Separation Principle

모델이 높은 확신을 출력해도 정책 위반이면 실행하지 않는다. 이는 모델 성능과 운영 안전을 분리하는 핵심 원칙이다.

---

## 7. How AI Works in Practical WealthTech

사용자 관점에서 NoahAI의 동작은 다음 흐름으로 요약된다.

- 상태 인식
  - 시장/포지션/리스크/설정 상태 수집
- 판단 생성
  - AI가 다중 후보 액션을 생성하고 우선순위를 계산
- 정책 검증
  - 거버넌스 계층이 실행 가능 여부를 판정
- 실행 및 기록
  - 허용된 액션만 실행하고 결과를 표준 로그로 저장
- 설명 및 피드백
  - 실행 이유와 리스크를 사용자에게 설명하고 후속 조정 반영

이 구조는 "자동매매"보다 넓은 개념인 "AI 의사결정 운영"을 목표로 한다.

---

## 8. Related Work and Positioning

NoahAI는 설명가능한 머신러닝, 인간 검토 기반 의사결정 지원, 그리고 감사 가능한 시스템 설계의 교차점에 있다.

- 설명가능한 AI: Doshi-Velez and Kim(2017), Rudin(2019), Ribeiro et al.(2016) 계열의 연구는 고위험 의사결정에서 블랙박스보다 투명한 모델 또는 충실한 설명 구조가 필요함을 강조한다.
- 인간-중심 의사결정 지원: 금융 및 운영 자동화에서 최종 판단을 완전 자동화하기보다, 사람이 검토 가능한 추적성과 단계적 승인을 두는 방식이 더 안전하다.
- 시스템 신뢰성: 단일 모델 정확도보다 버전 관리, 로그, 정책 상태, 재현 가능성이 함께 묶일 때 운영 신뢰성이 높아진다.

NoahAI의 포지션은 다음과 같다.

- NoahAI는 순수 예측 모델이 아니다.
- NoahAI는 실행 브로커나 자동 주문 주체가 아니다.
- NoahAI는 판단, 설명, 기록, 검증, 환류를 묶는 의사결정 인프라다.

### Selected References for Expansion

- Doshi-Velez, F. and Kim, B. (2017). Towards A Rigorous Science of Interpretable Machine Learning.
- Ribeiro, M. T., Singh, S., and Guestrin, C. (2016). "Why Should I Trust You?": Explaining the Predictions of Any Classifier.
- Rudin, C. (2019). Stop Explaining Black Box Machine Learning Models for High Stakes Decisions and Use Interpretable Models Instead.
- Sculley, D. et al. (2015). Hidden Technical Debt in Machine Learning Systems.

---

## 9. Comparative Baseline: Model-Centric vs NoahAI-DAL

본 절은 NoahAI-DAL이 기존 모델 중심 자동화 접근과 어디서 구조적으로 다른지를 명확히 하기 위한 비교 기준이다.

- 의사결정 단위
  - 모델 중심: 예측 점수 또는 신호 출력이 중심
  - NoahAI-DAL: Decision-Log-Review-Learning 단위가 중심
- 운영 통제
  - 모델 중심: 모델 신뢰도에 통제가 종속되기 쉬움
  - NoahAI-DAL: 정책 계층이 모델 외부에서 실행 허용 여부를 강제
- 설명 가능성
  - 모델 중심: 사후 설명이 부가 기능으로 붙는 경우가 많음
  - NoahAI-DAL: 설명 필드와 검토 절차가 실행 루프에 내장됨
- 감사 가능성
  - 모델 중심: 의사결정-실행-결과 연결 이력이 분절될 수 있음
  - NoahAI-DAL: 동일 이벤트 체인에서 추적 가능한 로그를 표준화
- 실패 대응
  - 모델 중심: 성능 저하 시 원인 구분이 어려움
  - NoahAI-DAL: 정책 위반, 데이터 결함, 인프라 결함을 운영 이벤트로 분리 진단

이 비교는 향후 정량 실험에서 ablation 또는 시스템 비교 실험 설계를 위한 기준선으로 사용된다.

---

## 10. Evaluation Framework for Next Study

본 문서는 아키텍처 중심 프리프린트이며, 후속 정량 연구를 위해 다음 지표를 제안한다.

- Reliability Metrics
  - 장시간 운용 안정성(메모리/스레드/복구율)
  - 상태 오염 재발률
  - 실행 실패 대비 자동 복구율
- Governance Metrics
  - 정책 위반 차단율
  - 손실 제한 규칙 준수율
  - 중단 조건 발동 정확도
- XAI Metrics
  - 설명 완결성(근거 필드 충족률)
  - 사후 검토 재현성(동일 입력 시 동일 설명 경향)
  - 사용자 이해도/수용도
- Business Metrics
  - 운영 중단 시간 감소
  - 수동 개입 시간 감소
  - 사용자 신뢰 유지율

---

## 11. Business Impact Hypothesis

본 아키텍처는 다음 사업 가치를 가진다.

- 신뢰 자산화
  - 블랙박스 수익률 경쟁이 아닌 통제 가능한 AI 운영 경쟁력 확보
- B2B 확장성
  - 증권사/자문사/플랫폼 연동 시 감사 가능 구조 제공
- 제품 라인업 확장
  - 개인형 앱에서 기관형 거버넌스 대시보드로 확장 가능
- 창업자/원작자 기여 명문화
  - DAL 기원과 NoahAI 구현 기여를 학술 문서로 고정

---

## 12. Limitations

- 본 문서는 아키텍처 중심 프리프린트이며 대규모 외부 실증 결과를 포함하지 않음
- 시장 환경별 일반화 성능은 후속 연구가 필요
- 규제/관할별 컴플라이언스 요구사항은 별도 검토 필요
- 금융 의사결정 지원은 투자 자문이나 확정 수익 보장을 의미하지 않음

---

## 13. Conclusion

NoahAI-DAL은 재테크 AI를 "예측 엔진"이 아니라 "운영 가능한 의사결정 시스템"으로 재정의한다. 핵심은 Decision-Log-Review-Learning 폐루프, XAI 운영화, 리스크 거버넌스 계층 분리다. 본 프리프린트는 구조적 타당성을 제시하며, 다음 단계는 정량 실증과 외부 검증을 통한 일반화다.

---

## 14. Reference List (Expanded)

- Doshi-Velez, F., and Kim, B. (2017). Towards A Rigorous Science of Interpretable Machine Learning. arXiv preprint arXiv:1702.08608.
- Ribeiro, M. T., Singh, S., and Guestrin, C. (2016). "Why Should I Trust You?": Explaining the Predictions of Any Classifier. Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining.
- Rudin, C. (2019). Stop Explaining Black Box Machine Learning Models for High Stakes Decisions and Use Interpretable Models Instead. Nature Machine Intelligence, 1, 206-215.
- Sculley, D., Holt, G., Golovin, D., Davydov, E., Phillips, T., Ebner, D., et al. (2015). Hidden Technical Debt in Machine Learning Systems. Advances in Neural Information Processing Systems (NeurIPS).
- Amershi, S., Weld, D., Vorvoreanu, M., Fourney, A., Nushi, B., Collisson, P., et al. (2019). Guidelines for Human-AI Interaction. Proceedings of the 2019 CHI Conference on Human Factors in Computing Systems.
- Mitchell, M., Wu, S., Zaldivar, A., Barnes, P., Vasserman, L., Hutchinson, B., et al. (2019). Model Cards for Model Reporting. Proceedings of the Conference on Fairness, Accountability, and Transparency (FAccT).

---

## Citation (Preprint)

```bibtex
@misc{jung2026noahai_dal,
  author       = {Jung, Haesung},
  title        = {NoahAI-DAL: A Governable Financial Decision Architecture with XAI and Risk Governance},
  year         = {2026},
  howpublished = {Preprint},
  note         = {Document ID NOAHAI-PAPER-2026-001. Originator of DAL and CTO/Co-founder of Dream AI Lab and NoahAI Labs.},
  url          = {https://noahailabs.com}
}
```

---

## Provenance Statement

AI Digital Care Log (DAL) was originated and designed by JUNG HAESUNG. NoahAI is a financial decision AI implementation that extends DAL principles into practical wealthtech operations.

## Submission Target Note

This draft is currently written as a preprint and internal manuscript. It is not yet formatted for a specific venue such as IEEE, ACM, arXiv, journal submission, or a conference template. The final version should be adjusted after the target venue is decided, especially for author metadata, length, citation style, and contribution disclosure rules.
