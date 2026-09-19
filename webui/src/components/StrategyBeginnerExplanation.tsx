import { t } from '../i18n';
import { STRATEGY_RULE_LABELS, strategyExplanation } from "../strategyExplanation";

export function StrategyBeginnerExplanation({ analysis, name, service }: {
  analysis: Record<string, any>; name: string; service: string;
}) {
  const explanation = strategyExplanation(analysis, name, service);
  return <section className="legacy-xai-card strategy-beginner-explanation" aria-label={t("이 전략 쉽게 이해하기")}>
    <h4>{t("이 전략 쉽게 이해하기")}</h4>
    <p>{t("분석 시점의 원문·사용자 확인 보완 규칙입니다. 아래에서 편집한 최종 적용값이나 이미 실행 중인 전략을 뜻하지 않습니다.")}</p>
    <dl>{STRATEGY_RULE_LABELS.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{explanation.rules[key]}</dd></div>)}</dl>
    <small>{t("줄임표(…)는 요약된 내용입니다. 자료 분석 범위와 상세 규칙을 함께 확인하세요. 조건이 보여도 실행 지원·승인·검증을 통과했다는 뜻은 아닙니다.")}</small>
    <details><summary>{t("영상·문서가 말하는 성과는 검증된 수익인가요?")}</summary>
      <p>{t("읽은 범위: ")}{explanation.coverage}</p>
      {explanation.source_excerpts.length ? <><p>{t("성과 관련 원문 발췌입니다. 저자의 주장·예시·질문 중 무엇인지 확인해야 합니다.")}</p><ul>{explanation.source_excerpts.map((text, i) => <li key={i}>{text}</li>)}</ul></>
        : <p>{t("전달된 발췌에서 성과를 확인하지 못했습니다. 영상·책 전체에 성과 설명이 없다는 의미는 아닙니다.")}</p>}
      <p>{t("출처의 승률·수익률은 NoahAI의 과거재생·PAPER·LIVE 성과나 여권 인증이 아닙니다. 기간·종목·비용·검증 조건이 없으면 성과는 미확인으로 봅니다.")}</p>
    </details>
    <p>{t("「이 결과 AI에게 묻기」로 현재 규칙·읽은 범위·일부 발췌를 가져갑니다. 일반 안내는 로컬 요약이며, AI와 이어서 대화하려면 기본 보호 경로의 「심층분석」을 선택하세요. 외부 AI에 질문과 전략 문맥이 전송되며 설정·비용 한도를 따릅니다.")}</p>
  </section>;
}

export function StrategyBeginnerHelp() {
  return <details className="legacy-xai-card strategy-beginner-help">
    <summary>{t("처음이라면 · AI와 함께 만들기 / 항목 뜻 / 차트 보는 순서")}</summary>
    <h4>{t("짧은 설명부터 대화로 완성하기")}</h4>
    <ol>
      <li>{t("「질문으로 함께 완성」을 선택하고 원하는 전략을 적거나 본인이 사용할 권리가 있는 자료를 넣습니다.")}</li>
      <li>{t("「분석하고 보완 질문 받기」 후 「이 전략 쉽게 이해하기」와 빠진 조건을 확인합니다. 원문 그대로 모드의 버튼은 「AI 분석 및 전략 초안 만들기」입니다. 읽지 못한 자료는 자막·텍스트·Pine 원문으로 보완합니다.")}</li>
      <li>{t("질문 카드에 자신의 답을 적습니다. 어려우면 「이 질문을 AI와 상의」 또는 「이 결과 AI에게 묻기」 → 「심층분석」에서 한 조건씩 대화합니다. 일반 안내는 로컬 사용법이며 자유로운 AI 대화가 아닙니다.")}</li>
      <li>{t("AI 답변을 전략 스튜디오 검토 영역으로 가져와 예시·추측을 지우고 필요한 조건만 남긴 뒤 「사용자 보완 근거로 확정·재분석」합니다. 원문 충돌이나 미지원 동작은 원본 수정이 필요합니다.")}</li>
      <li>{t("최종 재검증 후 버전 저장 → 사용자 승인 → 과거재생 또는 비대상 확인 → PAPER → 검증 후 최종 적용 순서입니다. 대화만으로 저장·승인·실거래가 실행되지는 않습니다.")}</li>
    </ol>
    <h4>{t("주요 항목은 무엇인가요?")}</h4>
    <dl>
      <div><dt>{t("판단 시간봉")}</dt><dd>{t("한 캔들의 길이입니다. 원문과 같은 시간을 선택합니다. 없는 증권 분봉을 일봉으로 바꾸지 않습니다.")}</dd></div>
      <div><dt>{t("전략 역할")}</dt><dd>{t("기본 AI 후보 확인은 NoahAI의 후보에 추가 조건을 거는 방식, 내 전략이 진입 신호 생성은 원문 조건으로 후보를 만드는 방식입니다.")}</dd></div>
      <div><dt>{t("시장상황·호환 범위")}</dt><dd>{t("언제, 어느 기관에서 후보가 될지 정합니다. 전체 선택도 모든 기관에서 실행 지원이 완료됐다는 뜻은 아닙니다.")}</dd></div>
      <div><dt>{t("청산 책임·TP/SL")}</dt><dd>{t("스마트 청산 상속과 원문의 고정 익절(TP)·손절(SL)을 구분합니다. 독립 전략은 명확한 자체 청산 조건이 필요합니다.")}</dd></div>
      <div><dt>{t("위험예산·비중·레버리지")}</dt><dd>{t("허용 손실, 사용 자금, 배율은 서로 다릅니다. 전략 요청값이 계좌 상한을 높이지 못하며 주식·ETF는 현물 1배입니다.")}</dd></div>
      <div><dt>{t("우선순위·국면 이탈")}</dt><dd>{t("복수 후보의 순서와 조건이 맞지 않을 때의 대응입니다. 우선순위가 높아도 진입조건·가드레일을 우회하지 않습니다.")}</dd></div>
    </dl>
    <h4>{t("차트는 어디서 보나요?")}</h4>
    <p>{t("저장 버전 → 「검증 근거 보기」 → 「과거재생 차트 · 타점·누적 수익률·거래 내역」을 펼칩니다. 자체 진입조건으로 과거 시세 재생을 실행한 결과에 표시됩니다. 기본 진입 보조처럼 과거재생 비대상인 전략에는 만들지 않습니다.")}</p>
    <p>{t("상단은 캔들·모의 타점, 하단은 청산 기준 누적 수익률입니다. 거래표의 「#번호 보기」로 해당 구간을 확대하고 「전체 구간」으로 돌아갑니다. 초록 BUY는 매수, 빨강 SELL은 매도이며 SHORT에서는 SELL 진입·BUY 청산입니다.")}</p>
    <p>{t("시각은 UTC, 비용은 설정 기반 추정치입니다. 실제 잔고·미실현손익·계좌 PnL과 다릅니다. 자세한 예제와 자료별 제한은 매뉴얼의 전략 스튜디오 안내에서 확인하세요.")}</p>
  </details>;
}
