# NoahAI-DAL: A Governable Financial Decision Architecture with XAI and Risk Governance

Preprint draft v1.0 · 2026-06-05

- Submission build status: Zenodo-ready wording freeze (2026-06-06)

- Document ID: NOAHAI-PAPER-2026-001-EN
- Author: JUNG HAESUNG
- Affiliation: Dream AI Lab, NoahAI Labs
- Author contribution: Originated the DAL concept and led the NoahAI implementation
- Submission note: Use the contribution line only when the target venue permits author-role disclosure; otherwise move it to acknowledgments or an internal provenance appendix
- Submission sequence: Archive the manuscript on Zenodo first, then submit the cited preprint version to arXiv
- arXiv note: Keep the same scientific version; remove or move internal provenance wording only if required by public-facing policy
- Companion manuscript: Korean original version in docs/papers/NOAHAI_DAL_FINANCIAL_DECISION_PREPRINT_2026.md
- Correspondence: noahailabs.com
- Related docs:
  - docs/technical/NOAHAI_TECHNICAL_WHITEPAPER.md
  - docs/guides/AI_LEARNING_CASE_STUDY_PUBLIC_V1.md

---

## Abstract

This paper proposes the NoahAI architecture as an extension of the core Decision-Log-Review-Learning loop of AI Digital Care Log (DAL) into financial decision operations. Existing automated trading and wealthtech AI systems are often described primarily through prediction accuracy, while operational controllability, explainability (XAI), and risk governance are less systematically designed. NoahAI separates the decision engine, standardized logging, human review, and learning loop into distinct layers, and combines them with policy-based risk limits and auditable execution histories. This manuscript focuses on system design and operating principles rather than performance claims, and it presents a reproducible structure and validation framework. Future work will evaluate rolling cohort performance, loss-limitation effects, and XAI trust metrics through external validation.

Keywords: financial decision AI, DAL, explainable AI, risk governance, decision logging, human-in-the-loop

---

## 1. Introduction

AI in wealthtech creates both high expectations and high risk. Users often cannot determine why a decision was made, when a system should stop, or whether a faulty decision is repeating. The core challenge is therefore not signal generation alone, but the transformation of AI judgment into an operational process.

NoahAI extends the DAL principle of Decision-Log-Review-Learning to financial decision-making and is designed to answer the following questions.

- Through which path is an AI judgment executed, and where is it controlled?
- Is the reasoning trace preserved in a form that can be reviewed after the fact?
- Are risk limits enforced as a policy layer separate from model performance?

The goal of this paper is not return promotion, but the articulation of design principles for reliable AI wealthtech operations.

---

## 2. Problem Statement

Conventional wealthtech AI products repeatedly exhibit the following limitations.

- Black-box decisions: signals are produced without a clear reasoning structure
- Operational fragility: state contamination, concurrency conflicts, and instability during long-running operations
- Control fragility: loss-limitation rules become dependent on model output
- Poor auditability: the connection between decision, execution, and outcome is not preserved

These limitations cannot be solved by model improvement alone. They require structural design in the operational layer.

---

## 3. Core Contribution

The contributions of this paper are as follows.

- Financial extension of DAL
  - The Decision-Log-Review-Learning loop is layered for wealthtech operations
- Operationalization of XAI
  - Explanation is not limited to text generation; it is coupled to review and audit workflows
- Separation of the risk-governance layer
  - Entry, exit, stop, and limit policies are enforced independently of the model
- Operational reproducibility frame
  - A reproducible validation procedure is defined using version, configuration, and log artifacts

---

## 4. NoahAI-DAL Architecture

### 4.1 Layer Overview

NoahAI is composed of five layers.

- Ingestion Layer
  - Collects market data, exchange state, user settings, and policy parameters
- Decision Layer
  - Produces combined model-based and rule-based judgments
  - Generates candidate actions by considering market regime, asset class, and risk state
- Governance Layer
  - Validates risk policies such as position limits, loss limits, and stop conditions
  - Passes only approved actions to the execution layer
- Execution and Logging Layer
  - Executes trading or simulation actions
  - Records reasoning, parameters, outcomes, and exceptions in structured logs
- Review and Learning Layer
  - Supports human review by operators or users and post-hoc analysis
  - Feeds policy, prompt, and parameter updates back into the loop

### 4.2 Decision-Log-Review-Learning Loop

- Decision: the current state is used by AI or rules to generate candidate actions
- Log: candidate reasoning and execution results are stored in a standard schema
- Review: XAI evidence and outcomes are reviewed by humans or systems
- Learning: review results are reflected in rule, policy, and model updates

This loop aims not at a single correct prediction, but at a system that improves during operation.

---

## 5. XAI Operational Design

In NoahAI, XAI is an operational function rather than a mere explanation output.

### 5.1 Explanation Unit

Each decision unit includes at minimum the following fields.

- Decision time and version
- Input state summary (market, position, risk)
- Selected action and alternative actions
- Main reasoning signals (rules, indicators, model outputs)
- Confidence and warning level

### 5.2 Review Workflow

- Before execution: the system requests confirmation or auto-holds when risk warnings are triggered
- During execution: the system stops or scales down when policy violations are detected
- After execution: the result can be reviewed together with its reasoning trace

### 5.3 Audit Readiness

- Event flow is standardized to reduce missing or tampered logs
- Post-hoc analysis should be able to trace what was executed and why

---

## 6. Risk Governance Model

NoahAI risk governance is defined as a policy layer external to the model.

### 6.1 Policy Categories

- Entry Control
  - New-entry conditions, concurrent-position limits, and asset-class exposure limits
- Exit Control
  - Stop-loss, take-profit, and time-based exit rules
- Exposure Control
  - Exposure limits at the account, asset, and exchange levels
- Circuit Breaker
  - Automatic stop on consecutive losses, abnormal volatility, or infrastructure failure

### 6.2 Separation Principle

Even if the model outputs high confidence, execution is blocked when policy conditions are violated. This is the core principle that separates model performance from operational safety.

---

## 7. How AI Works in Practical WealthTech

From the user perspective, NoahAI operates as follows.

- State awareness
  - The system collects market, position, risk, and configuration state
- Decision generation
  - AI generates multiple candidate actions and ranks them
- Policy validation
  - The governance layer determines whether execution is allowed
- Execution and recording
  - Only approved actions are executed and logged in a standard format
- Explanation and feedback
  - The system explains the decision and risk, then reflects follow-up adjustments

This structure aims at AI decision operations rather than narrow automated trading.

---

## 8. Related Work and Positioning

NoahAI sits at the intersection of interpretable machine learning, human-in-the-loop decision support, and auditable system design.

- Explainable AI: Work by Doshi-Velez and Kim (2017), Rudin (2019), and Ribeiro et al. (2016) argues that high-stakes decisions require transparent models or faithful explanations rather than opaque black boxes.
- Human-centered decision support: In financial and operational automation, it is often safer to preserve reviewable traces and staged approval rather than fully automate the final decision.
- System reliability: Operational trust improves when versioned artifacts, logs, policy states, and reproducibility are tied to each action rather than relying on model accuracy alone.

NoahAI is positioned as follows.

- NoahAI is not a pure prediction model.
- NoahAI is not an execution broker or auto-trader.
- NoahAI is a decision infrastructure that combines judgment, explanation, logging, verification, and feedback.

### Selected References for Expansion

- Doshi-Velez, F. and Kim, B. (2017). Towards A Rigorous Science of Interpretable Machine Learning.
- Ribeiro, M. T., Singh, S., and Guestrin, C. (2016). "Why Should I Trust You?": Explaining the Predictions of Any Classifier.
- Rudin, C. (2019). Stop Explaining Black Box Machine Learning Models for High Stakes Decisions and Use Interpretable Models Instead.
- Sculley, D. et al. (2015). Hidden Technical Debt in Machine Learning Systems.

---

## 9. Comparative Baseline: Model-Centric vs NoahAI-DAL

This section clarifies how NoahAI-DAL differs structurally from conventional model-centric automation.

- Decision unit
  - Model-centric: prediction score or signal output is the primary unit
  - NoahAI-DAL: Decision-Log-Review-Learning is the primary unit
- Operational control
  - Model-centric: control often follows model confidence
  - NoahAI-DAL: an external policy layer enforces execution eligibility
- Explainability
  - Model-centric: explanation is often a post-hoc add-on
  - NoahAI-DAL: explanation fields and review steps are embedded in the execution loop
- Auditability
  - Model-centric: links among decision, execution, and outcome can be fragmented
  - NoahAI-DAL: traceable logs are standardized within a single event chain
- Failure handling
  - Model-centric: failure diagnosis can be ambiguous under performance drop
  - NoahAI-DAL: policy violations, data defects, and infrastructure defects are separated as operational events

This baseline is intended for future ablation and system-comparison studies.

---

## 10. Evaluation Framework for Next Study

This manuscript is architecture-oriented. For future quantitative research, the following metrics are proposed.

- Reliability Metrics
  - Long-run stability (memory, threads, recovery rate)
  - Recurrence rate of state contamination
  - Automatic recovery rate after execution failures
- Governance Metrics
  - Policy violation blocking rate
  - Compliance rate with loss-limitation rules
  - Accuracy of stop-condition activation
- XAI Metrics
  - Explanation completeness (reasoning-field coverage)
  - Review reproducibility (similar explanation under the same input)
  - User comprehension and acceptance
- Business Metrics
  - Reduced downtime
  - Reduced manual intervention time
  - User trust retention

---

## 11. Business Impact Hypothesis

This architecture has the following business value.

- Trust as an asset
  - Competitive advantage comes from controllable AI operations rather than black-box return claims
- B2B scalability
  - The architecture supports auditable integration with brokerages, advisory firms, and platforms
- Product-line expansion
  - The system can evolve from a consumer app into an institutional governance dashboard
- Formalization of founder and original-author contribution
  - The origin of DAL and the implementation contribution of NoahAI are preserved in a scholarly form

---

## 12. Limitations

- This manuscript is architecture-oriented and does not include large-scale external empirical results
- Generalization across market regimes requires follow-up research
- Regulatory and jurisdiction-specific compliance requirements must be reviewed separately
- Financial decision support does not imply investment advice or guaranteed returns

---

## 13. Conclusion

NoahAI-DAL redefines wealthtech AI from a prediction engine into an operational decision system. Its core is the Decision-Log-Review-Learning loop, XAI operationalization, and separation of the risk-governance layer. This preprint demonstrates structural validity, while the next stage is generalization through quantitative validation and external review.

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
@misc{jung2026noahai_dal_en,
  author       = {Jung, Haesung},
  title        = {NoahAI-DAL: A Governable Financial Decision Architecture with XAI and Risk Governance},
  year         = {2026},
  howpublished = {Preprint},
  note         = {Document ID NOAHAI-PAPER-2026-001-EN. Originator of DAL and CTO/Co-founder of Dream AI Lab and NoahAI Labs.},
  url          = {https://noahailabs.com}
}
```

---

## Provenance Statement

AI Digital Care Log (DAL) was originated and designed by JUNG HAESUNG. NoahAI is a financial decision AI implementation that extends DAL principles into practical wealthtech operations.

---

## Submission Target Note

This draft is currently written as a preprint and internal manuscript. It is not yet formatted for a specific venue such as arXiv, a journal, or a conference template. The final version should be adjusted after the target venue is decided, especially for author metadata, length, citation style, and contribution disclosure rules.
