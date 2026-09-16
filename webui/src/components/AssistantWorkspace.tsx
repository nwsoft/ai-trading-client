import { Fragment, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";

import type { GatewayClient } from "../api";
import type { ManualSection } from "../types";

type QuickQuestion = readonly [label: string, prompt: string];

const ASSISTANT_PROFILES: Record<string, { title: string; placeholder: string; questions: QuickQuestion[] }> = {
  settings: {
    title: "설정·연결 자주 묻는 질문",
    placeholder: "API 연결, 운용 모드, 회원 등급, 고급 안전 계층을 질문하세요…",
    questions: [
      ["거래소 API 연결", "거래소 API 발급, 최소 권한, IP 허용목록과 연결 점검 순서를 알려줘"],
      ["증권사 API 연결", "증권사 API 이용 신청, 모의/실전 구분과 연결 점검 순서를 알려줘"],
      ["AI 엔진 연결", "AI Provider 키와 모델을 비용·정밀도별로 선택하는 순서를 알려줘"],
      ["PAPER와 LIVE", "PAPER와 LIVE의 차이, 별도 확인 항목과 주문 가드레일을 알려줘"],
      ["회원 등급", "현재 회원 등급과 서버 정책에 따라 허용되는 연결 범위를 설명해줘"],
      ["고급 매매 계층", "고급 매매 계층의 safe 프리셋과 각 가드레일 목적을 알려줘"],
      ["투자금 계산", "현재 투자금 계산 방식과 성과회복 뒤 거래금액이 언제 어떻게 달라지는지 알려줘"],
    ],
  },
  blockchain: {
    title: "자주 하는 질문",
    placeholder: "AI에게 질문하거나 요청사항을 입력하세요…",
    questions: [
      ["High vol 설정", "high vol 차단이 지금 켜져 있는지와 설정 위치, 남아 있는 가드레일을 알려줘"],
      ["전략 스튜디오 사용법", "전략 스튜디오에서 외부 전략을 분석한 뒤 실제 적용하기까지 순서와 확인 항목을 알려줘"],
      ["전략 스튜디오 프로필", "전략 스튜디오 초보자·일반·고급·실험실 프로필과 현재 켜진 기능을 알려줘"],
      ["백테스트·PAPER", "전략 스튜디오 백테스트의 PnL·MDD와 PAPER 결과를 어떻게 구분해 봐야 하는지 알려줘"],
      ["다중 거래소 실행", "같은 BTC 신호가 여러 거래소에 오면 내 현재 설정에서 어떻게 실행되고 위험은 어떻게 합산되는지 알려줘"],
      ["일반·고급 종목선정", "전략 스튜디오 일반과 고급의 코인 선정 및 국면 기준 차이를 현재 설정 기준으로 알려줘"],
      ["게이트 원인 점검", "수익성 검증 차단 원인을 최근 로그와 설정 기준으로 요약해줘"],
      ["게이트 임시 OFF", "수익성 게이트 임시 OFF 절차와 적용 후 점검 항목을 알려줘"],
      ["게이트 기준 완화", "수익성 게이트 기준 완화안을 보수·중립·공격 3단계로 보여줘"],
      ["거래 부재 원인", "왜 거래가 발생하지 않고 있는지 최근 상태와 설정 기준으로 분석해줘"],
      ["수익률 개선", "현재 수익률을 개선할 방법을 제안해줘"],
      ["리스크 점검", "현재 리스크 상황과 위험 요소를 점검해줘"],
      ["전략 평가", "현재 거래 전략의 장단점을 평가해줘"],
      ["레버리지·투자금", "레버리지는 올랐는데 거래금액이 같은 이유와 현재 투자금 계산 방식을 알려줘"],
      ["안전 모드", "손실을 줄이기 위한 보수적 설정 순서와 영향을 알려줘"],
      ["시장 상황", "현재 암호화폐 시장 상황과 근거를 알려줘"],
      ["코인 분석", "현재 선택된 코인의 분석 결과와 근거를 보여줘"],
      ["거래 성과", "최근 거래 성과와 통계를 요약해줘"],
    ],
  },
  ai_custom: {
    title: "전략 스튜디오 도움말",
    placeholder: "현재 전략의 누락 조건, 수정 방법, 저장·검증 순서를 질문하세요…",
    questions: [
      ["현재 차단 항목", "전략 스튜디오 최종 재검증에서 차단된 항목을 쉬운 말과 수정 예시로 설명해줘"],
      ["Pine 수정 순서", "Pine Script에서 지원되지 않는 조건을 NoahAI 실행 규칙으로 명확히 적는 순서를 알려줘"],
      ["TP·SL 작성", "전략 원문에 손절·익절 단위와 값을 안전하게 작성하는 예시를 보여줘"],
      ["시장국면 작성", "상승·하락·횡보 국면과 LONG·SHORT 조건을 혼동하지 않게 작성하는 예시를 보여줘"],
      ["저장부터 PAPER", "분석이 끝난 전략을 저장·승인·자동검증·PAPER까지 진행하는 순서를 알려줘"],
      ["429·30회 한도", "상태 429와 심층분석 기본 30회 한도의 이유, 계속 사용할 수 있는 로컬 기능과 설정 위치를 알려줘"],
    ],
  },
  stock: {
    title: "주식/ETF 자주 묻는 질문",
    placeholder: "주식/ETF 관련 질문을 입력하세요…",
    questions: [
      ["증권 연결 점검", "현재 증권사 연결과 설정 상태를 점검하고 문제 가능성을 알려줘"],
      ["다중 증권사 실행", "같은 주식 신호가 여러 증권사에 오면 어떻게 실행되고 위험이 어떻게 합산되는지 알려줘"],
      ["전략 스튜디오 종목선정", "전략 스튜디오 일반과 고급에서 주식·ETF 후보를 어떻게 고르는지 알려줘"],
      ["전략 스튜디오 프로필", "전략 스튜디오 초보자·일반·고급·실험실 프로필과 현재 켜진 기능을 알려줘"],
      ["백테스트·PAPER", "백테스트의 PnL·MDD와 PAPER 결과를 어떻게 구분해 봐야 하는지 알려줘"],
      ["ETF vs 주식", "ETF와 개별 주식 접근의 차이와 선택 기준을 비교해줘"],
      ["섹터 리스크", "현재 시장에서 주의할 섹터 리스크를 정리해줘"],
      ["변동성 대응", "변동성이 큰 장에서 손실을 줄이는 대응을 알려줘"],
      ["포지션 점검", "현재 주식 포지션 운용이 공격적인지 보수적인지 평가해줘"],
      ["수익/손실 리뷰", "최근 주식 성과를 기준으로 개선 포인트를 알려줘"],
      ["매수 타이밍", "분할매수 관점의 진입 점검 기준을 설명해줘"],
      ["ETF 후보", "점검할 ETF 유형과 후보 선정 기준을 알려줘"],
      ["설정 권장", "현재 설정에서 주식/ETF 운용에 맞는 권장 설정을 알려줘"],
      ["투자금 계산", "현재 주식·ETF 투자금 계산 방식과 성과회복 뒤 금액 변화 기준을 알려줘"],
    ],
  },
  personal_finance: {
    title: "생활금융 AI 상담",
    placeholder: "대출·보험·적금·생활비 관련 질문을 입력하세요…",
    questions: [
      ["대출 비교", "현재 입력한 금액과 기간을 기준으로 대출 상품 비교 방법과 확인할 위험을 알려줘"],
      ["보험 점검", "현재 가입 보험의 보장 공백을 점검할 때 필요한 정보와 순서를 알려줘"],
      ["적금 추천", "목표 금액과 기간에 맞는 예금·적금 비교 기준을 알려줘"],
      ["현금흐름 분석", "저장된 수입·지출 패턴을 기준으로 개선할 항목을 설명해줘"],
      ["비상자금 점검", "현재 생활비를 기준으로 적정 비상자금과 준비 순서를 알려줘"],
      ["금융 목표 설정", "나이와 소득, 기간에 맞는 금융 목표 설정 방법을 안내해줘"],
      ["지출 절감", "저장된 지출 기록에서 절감 가능 항목을 찾는 방법을 알려줘"],
      ["신용 관리", "신용점수를 관리하는 방법과 피해야 할 행동을 알려줘"],
      ["금리 전망 대응", "금리 변화에 대응하는 저축·대출 점검 방법을 설명해줘"],
    ],
  },
  portfolio: {
    title: "자산 통합 AI 상담",
    placeholder: "통합 자산·배분·리스크 관련 질문을 입력하세요…",
    questions: [
      ["통합 자산 점검", "현재 연결된 자산을 통화별로 구분해 요약하고 데이터가 없는 기관도 알려줘"],
      ["자산 배분 진단", "현재 자산 배분의 집중도와 분산 위험을 근거와 함께 설명해줘"],
      ["리스크 브리핑", "현재 자산 구성에서 먼저 확인할 위험과 대응 순서를 알려줘"],
      ["성과·위험 분석", "종료 거래 표본을 기준으로 성과와 최대 손실 위험을 구분해 설명해줘"],
      ["리밸런싱 검토", "주문을 실행하지 말고 현재 자료로 검토할 리밸런싱 후보와 주의점을 알려줘"],
    ],
  },
  ai_analyst: {
    title: "AI 애널리스트 질문",
    placeholder: "시장 분석, 투자 아이디어, 종합 전략을 질문하세요…",
    questions: [
      ["시장 종합 진단", "현재 글로벌 시장 상황을 종합적으로 진단해줘"],
      ["투자 아이디어", "현 시점에서 주목할 투자 아이디어 3개와 위험을 제안해줘"],
      ["포트폴리오 최적화", "멀티에셋 관점에서 포트폴리오 최적화 방향을 알려줘"],
      ["리스크 분석", "현재 시장의 주요 리스크 요인을 분석해줘"],
      ["시나리오 점검", "상승·기준·하락 시나리오별 대응을 정리해줘"],
    ],
  },
};

const SETTINGS_SECTION_LABELS: Record<string, string> = {
  general: "일반",
  exchange_selection: "거래소·증권사 선택",
  exchange_api: "거래소·증권 API",
  ai_engine: "AI 엔진/API",
  notifications: "외부 알림",
  advanced: "고급 매매 계층",
  alpha: "AlphaArena",
  system: "AI 시스템 상태",
  update: "업데이트",
};

const INTRO_FLOW_STEPS = [
  ["판단", "시장·포지션·설정을 함께 읽습니다."],
  ["설명", "왜 HOLD/진입/차단인지 근거를 남깁니다."],
  ["기록", "결정과 실행 결과를 나중에 복기할 수 있게 저장합니다."],
  ["검증", "과거재생·PAPER·실계정 확인을 구분합니다."],
  ["환류", "성과와 오류를 다음 판단의 참고 자료로 돌립니다."],
] as const;

const INTRO_FIRST_STEPS = [
  ["1", "설정 확인", "PAPER/LIVE, 사용할 거래소·증권사, API 연결을 먼저 확인합니다."],
  ["2", "대시보드 관찰", "잔고·포지션·로그·가드레일이 정상적으로 보이는지 봅니다."],
  ["3", "PAPER 검증", "실주문 없이 가상 거래로 전략과 설정을 먼저 확인합니다."],
  ["4", "LIVE는 별도 승인", "실계정 주문은 사용자가 별도 권한과 범위를 켠 뒤에만 후보가 됩니다."],
] as const;

const INTRO_COMPARE_ROWS = [
  ["중심", "매수·매도 신호 또는 주문 편의", "판단·설명·기록·검증·실행 경계"],
  ["전략 확인", "백테스트 수치나 외부 설명에 의존하기 쉬움", "원문 보존, 구조화, 과거재생, PAPER 전진검증을 분리"],
  ["위험 통제", "사용자 설정과 주문 경로가 분리되는 경우가 많음", "가드레일, TP/SL, 수량 제한, 실행 권한을 같은 흐름에서 확인"],
  ["책임 경계", "앱과 거래소 역할이 화면에서 흐려지기 쉬움", "사용자·NoahAI·거래소/증권사의 역할을 분리 표시"],
] as const;

type ManualGuideDefinition = {
  kicker: string;
  title: string;
  description: string;
  visual: [[string, string], [string, string], [string, string]];
  highlights: Array<[string, string]>;
  flowTitle: string;
  flow: Array<[string, string]>;
  guideTitle: string;
  guide: Array<[string, string, string]>;
  notice: [string, string];
};

const MANUAL_GUIDES: Record<string, ManualGuideDefinition> = {
  live: {
    kicker: "실계좌를 켜기 전에",
    title: "PAPER 확인 뒤, LIVE 권한은 따로 여세요.",
    description: "API가 연결되었다는 사실만으로 실주문 준비가 끝난 것은 아닙니다. 기관 권한·주문 대상·손실 한도·가드레일을 순서대로 확인해야 합니다.",
    visual: [["LEARNING", "분석·기록"], ["PAPER", "가상 체결 검증"], ["LIVE", "별도 허용 기관만"]],
    highlights: [["가장 안전한 기본값", "처음에는 PAPER를 사용하고 포지션·손익·로그가 정상인지 확인합니다."], ["LIVE는 기관별", "사용자가 실제 주문 대상으로 켠 거래소·증권사만 LIVE 후보가 됩니다."], ["연결 오류 시 중단", "API 권한·허용 IP·계정 상태 오류가 있으면 LIVE를 시작하지 않습니다."]],
    flowTitle: "실거래 전 5단계 확인",
    flow: [["버전", "설정과 하단 표시가 현재 배포판인지 확인"], ["연결", "API 조회·잔고·계정 권한 확인"], ["PAPER", "가상 진입·청산·통계 확인"], ["가드레일", "손실 한도·포지션 수·TP/SL 확인"], ["LIVE", "허용 기관을 직접 선택하고 시작"]],
    guideTitle: "문제가 보일 때의 판단 기준",
    guide: [["1", "잔고만 보임", "조회 권한은 정상이어도 주문 권한이나 회원 정책이 막힐 수 있습니다."], ["2", "409·권한 차단", "계정 등급과 해당 기관 승인 상태를 확인하고 안내된 승인 경로를 이용합니다."], ["3", "체결 불일치", "앱 로그와 거래소·증권사 원장을 함께 대조하기 전 통계를 확정하지 않습니다."], ["4", "즉시 정지", "이상 주문·가드레일 누락·반복 오류가 보이면 기관별 정지 버튼을 사용합니다."]],
    notice: ["중요", "PAPER 성과는 거래소 확인 LIVE 체결이나 미래 수익 보장이 아닙니다. 실제 체결·잔고·정산의 1차 기록은 연결 기관에서 확인하세요."],
  },
  settings: {
    kicker: "처음 설정하는 분",
    title: "질문에 답하고, 저장하고, 연결을 확인하세요.",
    description: "빠른 시작은 새 운용 모드가 아니라 기존 설정을 안전한 초깃값으로 준비하는 안내입니다. 거래를 자동으로 시작하거나 LIVE로 바꾸지 않습니다.",
    visual: [["선택", "자산·기관"], ["저장", "변경값 확정"], ["점검", "연결·대시보드"]],
    highlights: [["빠른 시작", "코인 또는 주식·ETF와 처음 관찰할 기관 한 곳을 고릅니다."], ["저장 전 미적용", "선택한 값은 전체 설정 저장과 중요 설정 확인을 거쳐야 적용됩니다."], ["고급 설정 유지", "기존 상세 설정과 Strategy Studio Level 1~4는 그대로 남습니다."]],
    flowTitle: "처음 설정하는 순서",
    flow: [["일반", "PAPER/LIVE와 운용 기본값 확인"], ["기관 선택", "화면·분석·주문 대상 구분"], ["API", "키·권한·계정 정보 저장"], ["연결 점검", "조회 성공과 실제 선택 모델 확인"], ["대시보드", "기관별 시작 버튼으로 실행"]],
    guideTitle: "사용자가 직접 결정하는 항목",
    guide: [["1", "실주문 여부", "PAPER를 끄는 것과 실제 주문 기관을 허용하는 것은 별도입니다."], ["2", "손실 허용 범위", "거래당 위험·동시 포지션·일일 손실 한도를 확인합니다."], ["3", "AI 구성", "작업별 Provider와 모델, 호출 한도와 비용 기준을 선택합니다."], ["4", "저장 확인", "중요한 변경은 확인창의 범위를 읽고 직접 저장합니다."]],
    notice: ["안전 원칙", "빠른 시작과 설정 도우미는 API 키를 대신 만들거나 거래를 자동 시작하지 않습니다. 비밀키는 해당 기관에서 발급받아 사용자가 직접 관리합니다."],
  },
  intelligence: {
    kicker: "분석 화면 읽기",
    title: "숫자보다 출처·기준시각·가정을 먼저 보세요.",
    description: "금융 인텔리전스는 시장·뉴스·기업·전략·내 성과를 같은 화면에서 살펴보는 분석 도구입니다. 이 화면만으로 주문이 자동 실행되지는 않습니다.",
    visual: [["데이터", "시장·뉴스·재무"], ["분석", "비교·위험·시나리오"], ["판단 보조", "주문과 분리"]],
    highlights: [["코인과 주식", "자산군별 시장·섹터·종목 분석을 각각 제공합니다."], ["내 성과", "자산 통합에서 손익·비용·낙폭·편중을 함께 확인합니다."], ["임의 값 금지", "운영 데이터가 없으면 데이터 연결 필요 또는 준비 중으로 표시합니다."]],
    flowTitle: "가장 쉬운 분석 순서",
    flow: [["영역", "블록체인·주식·자산 통합 중 선택"], ["대상", "프리셋 또는 종목 직접 입력"], ["기준", "출처와 기준시각 확인"], ["해석", "수익·위험과 계산 가정 함께 읽기"], ["대조", "주문 전 로그·가드레일 별도 확인"]],
    guideTitle: "결과를 오해하지 않는 법",
    guide: [["1", "시세 기준", "지연 시세인지 실시간인지, 어느 시장의 값인지 먼저 봅니다."], ["2", "비교 단위", "KRW와 USDT, PAPER와 LIVE 결과를 임의로 합산하지 않습니다."], ["3", "빈 결과", "0으로 추정하지 않고 연결 필요·계산 전 상태로 이해합니다."], ["4", "주문 판단", "분석 한 화면만으로 주문하지 않고 계좌 상태와 위험 한도를 함께 확인합니다."]],
    notice: ["분석의 한계", "차트와 AI 설명은 판단 자료입니다. 데이터 지연·누락·시장 급변 가능성이 있으므로 실제 주문의 확정 근거로 단독 사용하지 마세요."],
  },
  runtime: {
    kicker: "NoahAI 작동 원리",
    title: "입력에서 판단, 실행, 기록, 환류까지 이어집니다.",
    description: "가격을 한 번 예측하고 끝나는 모델이 아니라 시장·계정·설정을 반복해서 읽고, 가드레일 안에서 판단과 실행 결과를 기록하는 운영 루프입니다.",
    visual: [["입력", "시세·계정·설정"], ["판단", "신호·가드레일"], ["기록", "체결·손익·복기"]],
    highlights: [["반복 갱신", "시장과 포지션 상태가 바뀌면 다음 주기에 다시 판단합니다."], ["가드레일 우선", "AI 의견보다 계좌 한도·주문 규칙·정지 조건이 먼저 적용됩니다."], ["기록과 환류", "결정과 결과를 남겨 이후 점검과 개선의 입력으로 사용합니다."]],
    flowTitle: "한 번의 판단 주기",
    flow: [["읽기", "시장·잔고·포지션 최신 상태"], ["분석", "국면·기술·비용·전략 조건"], ["통제", "가드레일과 기관 기능 검사"], ["실행", "허용된 모드와 기관에만 전달"], ["기록", "결과·오류·근거를 원장에 보존"]],
    guideTitle: "같아야 하는 것과 달라야 하는 것",
    guide: [["1", "공통 계약", "상태·근거·위험·원장 의미는 모든 거래소와 증권사에서 같습니다."], ["2", "기관별 변환", "수수료·최소주문·호가·현물/선물·세금은 기관 규칙에 맞게 계산합니다."], ["3", "외부 AI", "연결한 경우 일부 질문과 맥락이 선택 Provider로 전달될 수 있습니다."], ["4", "최종 원장", "체결·잔고·거절 사유는 거래소·증권사 기록과 대조합니다."]],
    notice: ["책임 경계", "NoahAI는 허용된 범위의 판단과 실행을 연결하는 소프트웨어입니다. 브로커나 운용사가 아니며, 실제 계정 통제와 최종 확인 책임은 사용자에게 있습니다."],
  },
  assets: {
    kicker: "자산별 시작 경로",
    title: "같은 원칙으로 운영하되, 상품 규칙은 섞지 않습니다.",
    description: "암호화폐·주식·ETF는 같은 판단·기록 골격을 사용하지만 현물/선물, 통화, 거래시간, 세금과 주문 규칙은 기관별로 분리됩니다.",
    visual: [["암호화폐", "현물·선물"], ["공통 판단", "국면·위험·기록"], ["주식·ETF", "증권사·장 운영"]],
    highlights: [["기관별 시작", "선택한 거래소·증권사를 각각 시작하고 상태를 확인합니다."], ["성과 분리", "거래소·증권사·통화·PAPER/LIVE 성과를 서로 섞지 않습니다."], ["다중 운용", "각각 실행·총위험 분할·우선순위 한 곳 정책을 설정에서 구분합니다."]],
    flowTitle: "공통 사용 순서",
    flow: [["API", "기관 자격정보와 권한 저장"], ["선택", "분석 대상과 주문 대상 구분"], ["PAPER", "상품별 가상 체결 확인"], ["통계", "기관·통화·기간 기준 확인"], ["LIVE", "지원 상태와 권한 통과 후 별도 허용"]],
    guideTitle: "자산군별 핵심 차이",
    guide: [["1", "해외 선물", "LONG/SHORT·레버리지·펀딩비·증거금 규칙을 적용합니다."], ["2", "국내 현물", "보유 수량 안의 매도만 가능하며 SHORT와 레버리지를 사용하지 않습니다."], ["3", "주식·ETF", "장 시간·휴장·호가 단위·수수료·세금·증권사 체결을 반영합니다."], ["4", "신규 기관", "시세·PAPER·주문·체결 대조 게이트를 통과한 기능만 준비 완료로 표시합니다."]],
    notice: ["확장 원칙", "새 거래소가 추가돼도 전략 카테고리를 고정 이름으로 늘리지 않습니다. 상품 유형·기능·기관 호환성과 기관별 검증 근거로 구분합니다."],
  },
  stocks: {
    kicker: "증권·주식·ETF",
    title: "증권사 연결과 실주문 준비는 별개의 단계입니다.",
    description: "계좌 조회가 성공해도 주문 권한·운영체제·장 시간·종목 유형·가드레일이 맞지 않으면 주문은 차단될 수 있습니다.",
    visual: [["증권사", "계정·API"], ["NoahAI", "분석·위험 통제"], ["시장", "장 시간·체결·세금"]],
    highlights: [["PAPER 우선", "주식·ETF도 실계정 주문 전 가상 체결과 통계를 먼저 확인합니다."], ["키움 환경", "OpenAPI+는 Windows COM/ActiveX와 지원 런타임 조건을 확인해야 합니다."], ["증권사별 근거", "연결·조회·주문·체결·정산 상태를 증권사별로 따로 봅니다."]],
    flowTitle: "증권 시작 체크",
    flow: [["신청", "증권사 OpenAPI와 계좌 권한 준비"], ["등록", "설정에 계정·키를 저장"], ["점검", "토큰·조회·계좌 상태 확인"], ["PAPER", "매수·부분매도·비용 원장 확인"], ["LIVE", "장 상태와 실주문 권한을 다시 확인"]],
    guideTitle: "자주 막히는 지점",
    guide: [["1", "키움 연결", "Windows와 OpenAPI+ 로그인, COM 호스트 상태를 확인합니다."], ["2", "REST 증권사", "토큰 제한·계좌 상품코드·모의/실계정 구분을 확인합니다."], ["3", "ETF", "주식과 같은 이름으로 보여도 ETF 여부와 주문 가능 종목을 따로 판별합니다."], ["4", "통계", "매수 로트·부분매도·수수료·세금이 확정된 기록만 손익으로 집계합니다."]],
    notice: ["지원 상태 표시", "구현됨은 모든 사용자 실계정 E2E 완료를 뜻하지 않습니다. 각 증권사의 현재 연결·PAPER·LIVE 배지와 오류 안내를 기준으로 판단하세요."],
  },
  assistant: {
    kicker: "AI에게 묻기",
    title: "현재 화면과 설정을 설명받는 보조 채널입니다.",
    description: "AI 어시스턴트는 상태 요약·오류 해석·설정 위치·전략 보완 안내를 돕습니다. 질문만으로 주문이나 중요 설정을 확정하지 않습니다.",
    visual: [["질문", "현재 화면·오류"], ["AI 설명", "맥락·근거·다음 단계"], ["사용자 확인", "설정·전략에 명시 적용"]],
    highlights: [["맥락 연결", "열어 둔 서비스와 설정 섹션을 구조화된 맥락으로 전달합니다."], ["답변과 적용 분리", "AI 답변은 제안이며 저장·승인·PAPER/LIVE는 별도 확인이 필요합니다."], ["비용과 한도", "Provider 오류와 로컬 일·월 호출 제한을 구분해 표시합니다."]],
    flowTitle: "효과적으로 질문하는 순서",
    flow: [["상태", "현재 모드·기관·전략 요약 요청"], ["원인", "로그 또는 오류 문구 해석 요청"], ["위치", "바꿀 설정의 탭과 영향 확인"], ["제안", "안전한 다음 단계와 예시 요청"], ["확인", "화면에서 직접 검토·저장"]],
    guideTitle: "답변을 신뢰하기 전 확인",
    guide: [["1", "빈 답변", "선택 모델 응답 실패·한도·Provider 오류를 상태 카드에서 확인합니다."], ["2", "429", "NoahAI 호출 한도인지 Provider의 속도·잔액 한도인지 구분합니다."], ["3", "전략 보완", "진입·청산·TP/SL을 AI가 임의 창작하지 않도록 원문과 보완 근거를 확인합니다."], ["4", "민감 정보", "API 키·계좌번호·비공개 전략 원문은 공개 데이터 공유 Project에 보내지 않습니다."]],
    notice: ["중요", "AI가 그럴듯하게 답해도 거래소 상태나 실제 체결을 직접 확인한 것은 아닐 수 있습니다. 답변의 기준시각·데이터 범위·선택 모델을 함께 확인하세요."],
  },
  custom: {
    kicker: "전략 스튜디오",
    title: "아이디어를 실행 가능한 규칙과 검증 이력으로 바꿉니다.",
    description: "대화·문서·Pine·TradingView 전략을 가져와 원문을 보존하고, 지원 가능한 규칙만 구조화한 뒤 승인·과거 시세 재생·PAPER를 거칩니다.",
    visual: [["원문", "대화·문서·Pine"], ["전략 버전", "규칙·위험·승인"], ["검증", "과거재생·PAPER·LIVE"]],
    highlights: [["5분 따라 만들기", "Level을 바꾸지 않고 예제를 통해 한 단계씩 전략 버전을 만듭니다."], ["사용자 승인", "저장만으로 실행되지 않으며 보완값·위험·규칙을 확인하고 승인해야 합니다."], ["버전별 이력", "각 버전의 파라미터·검증 시도·PAPER 거래를 분리해 보존합니다."]],
    flowTitle: "전략 생명주기",
    flow: [["가져오기", "아이디어·파일·Pine 원문 보존"], ["구조화", "진입·청산·위험·시장 조건 추출"], ["승인", "누락과 실제 실행 규칙 사용자 확인"], ["검증", "과거 시세 재생 후 PAPER 전진검증"], ["적용·공유", "가드레일 적용 후 패키지·허브 제출"]],
    guideTitle: "검증 단계의 의미",
    guide: [["1", "과거 시세 재생", "전략 시간봉과 비용을 반영한 사전 규칙 검사이며 PAPER를 대체하지 않습니다."], ["2", "PAPER", "같은 버전·시도 ID로 실시간 시장의 가상 거래 근거를 누적합니다."], ["3", "LIVE", "사용자 실계정과 기관별 체결 근거이며 별도 승인과 가드레일이 필요합니다."], ["4", "허브 E0", "권리 선언과 구조 확인 단계로, 제작자 자기입력 성과는 검증 점수로 쓰지 않습니다."]],
    notice: ["자동 보완 경계", "화면에서 사용자가 확정한 위험예산·시장국면은 보완 근거로 추가할 수 있지만, 진입·청산·방향·TP/SL을 AI가 임의로 만들어서는 안 됩니다."],
  },
  arena: {
    kicker: "숙련자용 실험 기능",
    title: "AlphaArena는 기본 자동매매와 분리된 고급 루프입니다.",
    description: "선택한 AI 엔진이 구조화된 매매 의도를 만들고 자체 가드레일을 거쳐 PAPER 결과를 기록하는 고급 실험 기능입니다. v3.9.1.37에서는 LIVE가 차단됩니다.",
    visual: [["시장 입력", "시세·지표"], ["선택 모델", "구조화 판단"], ["가드레일", "허용 주문만"]],
    highlights: [["기본 OFF", "설정에서 명시적으로 활성화해야 화면과 실행 루프가 나타납니다."], ["한 번에 한 엔진", "여러 모델 동시 경쟁이 아니라 선택 모델 하나로 같은 규칙을 평가합니다."], ["현재 PAPER 전용", "Windows·주문 소유권·복구 외부 검증 전에는 LIVE 시작을 실패 폐쇄합니다."]],
    flowTitle: "한 세션의 흐름",
    flow: [["틱", "설정 주기마다 시장 입력 구성"], ["모델", "설명과 구조화 매매 의도 생성"], ["파싱", "지원 형식과 값의 유효성 검사"], ["통제", "위험 캡·쿨다운·포지션 수 검사"], ["환류", "주문 결과를 다음 판단에 반영"]],
    guideTitle: "사용 전 필수 이해",
    guide: [["1", "비교 목적", "모델을 바꾸면 동일 조건에서 판단 차이를 관찰하는 실험에 가깝습니다."], ["2", "초기 자본", "프롬프트의 비교 기준이며 실제 거래소 잔고를 대체하지 않습니다."], ["3", "실패·스킵", "키·권한·거래소 장애·가드레일 차단은 정상적인 중단 사유일 수 있습니다."], ["4", "기본 모드", "일반 사용자는 기본 NoahAI와 PAPER에서 먼저 운영 흐름을 확인합니다."]],
    notice: ["고위험 기능", "AlphaArena를 켜도 가드레일을 제거하지 마세요. 선택 모델의 응답 품질은 실제 수익이나 주문 안정성을 보장하지 않습니다."],
  },
  updates: {
    kicker: "현재 설치와 변경사항",
    title: "최신 변경과 아직 남은 검증을 분리해서 보세요.",
    description: "업데이트 탭은 현재 설치 식별, 사용자 영향, 검증된 범위와 남은 배포 게이트를 확인하는 곳입니다. 사용법은 각 기능 탭에서 확인합니다.",
    visual: [["버전", "3.9.1.37"], ["변경", "키움 조회 대기·실패 상태 수정"], ["검증", "Windows 실계정 확인 별도"]],
    highlights: [["이번 후보", "같은 국면의 반복 알림, 자동 버전 확인 주기, Coinone 후보 수집과 증권 실행 로그를 보강했습니다."], ["유지한 안전장치", "점수 없는 후보 진입 차단·주문 권한·TP/SL·가드레일은 유지합니다. 후보 수집 복구는 수익이나 즉시 진입을 보장하지 않습니다."], ["배포 전 확인", "Windows 설치본의 주기 확인·업데이트 재시작·Coinone PAPER와 증권사 실계정 동작은 별도로 점검합니다."]],
    flowTitle: "업데이트를 확인하는 순서",
    flow: [["식별", "설정과 하단의 버전·패치 확인"], ["변경", "내 사용 흐름에 영향 주는 항목 확인"], ["보존", "설정·원장·전략 버전 유지 확인"], ["검증", "PAPER와 연결 상태 재확인"], ["배포", "설치·재시작 뒤 실제 화면 확인"]],
    guideTitle: "완료 표현을 읽는 기준",
    guide: [["1", "소스 완료", "코드와 자동 테스트가 통과한 상태입니다."], ["2", "빌드 완료", "배포 산출물이 만들어졌지만 실계정 검증과는 다릅니다."], ["3", "E2E 완료", "해당 OS·기관·계정에서 조회·주문·체결까지 확인한 상태입니다."], ["4", "운영 검증", "24~72시간 지속성과 실제 사용자 환경을 포함한 별도 근거입니다."]],
    notice: ["버전 주의", "버전 번호가 같아도 패치 식별이나 배포 산출물이 다를 수 있습니다. 실제 설치 화면과 릴리스 노트를 함께 확인하세요."],
  },
};

function ManualIntroContent({ content, query }: { content: string; query: string }) {
  return <article className="manual-intro-page">
    <section className="manual-intro-hero">
      <div>
        <span className="manual-kicker">처음 보는 분은 여기부터</span>
        <h3>{highlightedManualText("NoahAI는 자동매매 버튼이 아니라 금융 판단 흐름입니다.", query)}</h3>
        <p>{highlightedManualText("시장 데이터를 읽고, 이유를 설명하고, 기록과 검증을 남긴 뒤 사용자가 허용한 범위에서만 실행으로 이어집니다.", query)}</p>
      </div>
      <div className="manual-intro-visual" role="img" aria-label="사용자, NoahAI, 거래소와 증권사의 역할 관계">
        <div className="manual-visual-node user">사용자<br /><small>허용·확인</small></div>
        <div className="manual-visual-core">NoahAI<br /><small>판단·기록·가드레일</small></div>
        <div className="manual-visual-node venue">거래소·증권사<br /><small>체결·잔고</small></div>
      </div>
    </section>

    <section className="manual-intro-summary">
      <div><b>먼저 기억할 3가지</b><p>실계좌 체결·잔고의 1차 주체는 항상 연결한 기관입니다.</p></div>
      <div><b>PAPER 먼저</b><p>PAPER는 실주문 없이 설정과 전략을 확인하는 안전한 검증 단계입니다.</p></div>
      <div><b>LIVE는 별도</b><p>API 권한, 주문 대상, 가드레일, 사용자 확인이 모두 필요합니다.</p></div>
    </section>

    <section className="manual-book-section">
      <header><span>작동 흐름</span><h4>판단이 실행으로 이어지는 5단계</h4></header>
      <div className="manual-flow-strip">
        {INTRO_FLOW_STEPS.map(([title, body]) => <div key={title}><strong>{highlightedManualText(title, query)}</strong><p>{highlightedManualText(body, query)}</p></div>)}
      </div>
    </section>

    <section className="manual-book-section">
      <header><span>처음 사용</span><h4>가장 안전한 시작 순서</h4></header>
      <div className="manual-step-grid">
        {INTRO_FIRST_STEPS.map(([step, title, body]) => <div key={step}><b>{step}</b><strong>{highlightedManualText(title, query)}</strong><p>{highlightedManualText(body, query)}</p></div>)}
      </div>
    </section>

    <section className="manual-book-section">
      <header><span>비교</span><h4>일반 자동매매와 NoahAI의 차이</h4></header>
      <div className="manual-compare-table" role="table" aria-label="일반 자동매매와 NoahAI 비교">
        <div role="row"><b role="columnheader">구분</b><b role="columnheader">일반 자동매매</b><b role="columnheader">NoahAI</b></div>
        {INTRO_COMPARE_ROWS.map(([label, legacy, noah]) => <div role="row" key={label}><strong role="cell">{highlightedManualText(label, query)}</strong><span role="cell">{highlightedManualText(legacy, query)}</span><span role="cell">{highlightedManualText(noah, query)}</span></div>)}
      </div>
    </section>

    <section className="manual-book-section manual-responsibility-panel">
      <header><span>책임 경계</span><h4>누가 무엇을 확인하나요?</h4></header>
      <div>
        <p><b>사용자</b><span>API 키, 손실 허용 범위, PAPER/LIVE 전환, 실제 주문 허용 기관을 결정합니다.</span></p>
        <p><b>NoahAI</b><span>판단 보조, 설명, 로그, 전략 검증, 가드레일과 허용 범위의 실행 연계를 담당합니다.</span></p>
        <p><b>거래소·증권사</b><span>실제 체결, 정산, 잔고, 주문 거절 사유와 계정 정책의 1차 주체입니다.</span></p>
      </div>
    </section>

    <ManualDocumentContent sectionId="intro" content={content} query={query} />
  </article>;
}

function ManualGuideContent({ sectionId, content, query }: { sectionId: string; content: string; query: string }) {
  const guide = MANUAL_GUIDES[sectionId];
  if (!guide) return <pre className="manual-raw-content">{highlightedManualText(content, query)}</pre>;
  return <article className={`manual-guide-page manual-guide-${sectionId}`}>
    <section className="manual-guide-hero">
      <div>
        <span className="manual-kicker">{highlightedManualText(guide.kicker, query)}</span>
        <h3>{highlightedManualText(guide.title, query)}</h3>
        <p>{highlightedManualText(guide.description, query)}</p>
      </div>
      <div className="manual-guide-visual" role="img" aria-label={`${guide.title} 핵심 흐름`}>
        {guide.visual.map(([title, body], index) => <Fragment key={title}>
          <div className={`manual-guide-visual-node node-${index + 1}`}>
            <strong>{highlightedManualText(title, query)}</strong>
            <small>{highlightedManualText(body, query)}</small>
          </div>
          {index < guide.visual.length - 1 && <span aria-hidden="true">›</span>}
        </Fragment>)}
      </div>
    </section>

    <section className="manual-intro-summary">
      {guide.highlights.map(([title, body]) => <div key={title}><b>{highlightedManualText(title, query)}</b><p>{highlightedManualText(body, query)}</p></div>)}
    </section>

    <section className="manual-book-section">
      <header><span>한눈에 보는 흐름</span><h4>{highlightedManualText(guide.flowTitle, query)}</h4></header>
      <div className="manual-flow-strip">
        {guide.flow.map(([title, body]) => <div key={title}><strong>{highlightedManualText(title, query)}</strong><p>{highlightedManualText(body, query)}</p></div>)}
      </div>
    </section>

    <section className="manual-book-section">
      <header><span>실제 사용 안내</span><h4>{highlightedManualText(guide.guideTitle, query)}</h4></header>
      <div className="manual-step-grid">
        {guide.guide.map(([step, title, body]) => <div key={`${step}-${title}`}><b>{step}</b><strong>{highlightedManualText(title, query)}</strong><p>{highlightedManualText(body, query)}</p></div>)}
      </div>
    </section>

    <section className="manual-guide-notice">
      <strong>{highlightedManualText(guide.notice[0], query)}</strong>
      <p>{highlightedManualText(guide.notice[1], query)}</p>
    </section>

    <ManualDocumentContent sectionId={sectionId} content={content} query={query} />
  </article>;
}

export function AssistantWorkspace({ client, service, initialQuestion = "", settingsSection = "", onOpenSettings, onChartAnalysis, onReturn, returnLabel, onSendToStrategy }: { client: GatewayClient; service: string; initialQuestion?: string; settingsSection?: string; onOpenSettings?: () => void; onChartAnalysis?: () => void; onReturn?: () => void; returnLabel?: string; onSendToStrategy?: (answer: string) => void }) {
  const [question, setQuestion] = useState("");
  const [level, setLevel] = useState<"beginner" | "standard" | "advanced">(service === "ai_custom" ? "beginner" : "standard");
  const [mode, setMode] = useState<"guide" | "deep_analysis">("guide");
  const [dataScope, setDataScope] = useState<"private" | "public_general">("private");
  const [messages, setMessages] = useState<Array<{ role: "assistant" | "user"; text: string }>>([
    { role: "assistant", text: "안녕하세요. NoahAI 공식 AI 어시스턴트입니다." },
    { role: "assistant", text: "사용법·현재 상태·설정의 현재값·영향·위치를 설명합니다. 실제 변경과 저장은 설정 화면에서 직접 확인해 주세요." },
  ]);
  const [meta, setMeta] = useState<Record<string, any> | null>(null);
  const [status, setStatus] = useState<Record<string, any> | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [voice, setVoice] = useState({ enabled: false, auto_tts: false, lang: "ko-KR", rate: 180 });
  const [chartOpen, setChartOpen] = useState(false);
  const [chartFileName, setChartFileName] = useState("");
  const [chartImage, setChartImage] = useState("");
  const [chartResult, setChartResult] = useState<Record<string, any> | null>(null);
  const [chartMessage, setChartMessage] = useState("");
  const [chartBusy, setChartBusy] = useState(false);
  const recognitionRef = useRef<any>(null);
  async function submit(event: FormEvent) {
    event.preventDefault();
    const prompt = question.trim();
    if (prompt.length < 2) return;
    setBusy(true); setMessage(""); setMessages((items) => [...items, { role: "user", text: prompt }]);
    try {
      const recentMessages = dataScope === "public_general" ? [] : messages.slice(-12).map((item) => ({ role: item.role, content: item.text }));
      const result = await client.askAssistant(prompt, service, level, mode, recentMessages, settingsSection, dataScope);
      const answer = String(result.answer ?? "").trim() || "AI 응답이 비어 있어 답변을 표시하지 못했습니다. 일반 안내로 다시 시도하거나 AI Provider 연결 상태를 확인하세요.";
      setMessages((items) => [...items, { role: "assistant", text: answer }]);
      if (voice.enabled && voice.auto_tts && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(answer);
        utterance.lang = voice.lang;
        utterance.rate = Math.max(0.5, Math.min(2, Number(voice.rate || 180) / 180));
        window.speechSynthesis.speak(utterance);
      }
      setMeta(result); setStatus(result.budget ? { ...(status ?? {}), budget: result.budget } : status);
      setQuestion("");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "AI 가이드 요청에 실패했습니다.");
    } finally { setBusy(false); }
  }
  useEffect(() => {
    client.assistantStatus().then(setStatus).catch(() => undefined);
    client.settings().then((snapshot) => {
      const field = snapshot.fields.find((item) => item.path === "assistant_voice");
      const value = field?.value;
      if (value && typeof value === "object" && !Array.isArray(value) && !("configured" in value)) {
        const config = value as Record<string, unknown>;
        setVoice({ enabled: Boolean(config.enabled), auto_tts: Boolean(config.auto_tts), lang: String(config.lang || "ko-KR"), rate: Number(config.rate || 180) });
      }
    }).catch(() => undefined);
    return () => { recognitionRef.current?.abort?.(); window.speechSynthesis?.cancel(); };
  }, [client]);
  useEffect(() => { if (initialQuestion) setQuestion(initialQuestion); }, [initialQuestion]);
  useEffect(() => { if (service === "ai_custom") setLevel("beginner"); }, [service]);
  useEffect(() => { setDataScope("private"); }, [service, settingsSection]);
  const budget = status?.budget ?? {};
  const budgetExhausted = Number(budget.daily_used ?? 0) >= Number(budget.daily_limit ?? Number.POSITIVE_INFINITY)
    || Number(budget.monthly_used ?? 0) >= Number(budget.monthly_limit ?? Number.POSITIVE_INFINITY);
  const profile = ASSISTANT_PROFILES[service] ?? ASSISTANT_PROFILES.blockchain;
  const publicRoute = status?.data_routing ?? {};
  async function togglePublicGeneral(enabled: boolean) {
    if (!enabled) { setDataScope("private"); return; }
    let route = publicRoute;
    try {
      const latest = await client.assistantStatus();
      setStatus(latest);
      route = latest.data_routing ?? {};
    } catch {
      setMessage("공개 Project 준비 상태를 조회하지 못했습니다. 연결을 확인하고 다시 선택하세요.");
      return;
    }
    if (!route.public_general_effective) {
      setMessage(!route.public_general_enabled
        ? "공개 질문 경로가 OFF입니다. 설정 → AI 엔진/API에서 켠 뒤 저장하세요."
        : "공개 질문 설정은 ON이지만 별도 OpenAI Project 키가 저장되지 않았습니다. AI 엔진/API의 공개 질문용 키를 저장하세요. 기본 AI 키와는 별도입니다.");
      return;
    }
    if (!window.confirm("이 질문에는 비공개 전략·Pine·파일·차트·계좌·포지션·개인정보가 없습니까? 공개 질문 모드는 최근 대화와 앱 상태를 보내지 않고 질문 1건만 공유용 OpenAI Project로 전송합니다.")) return;
    setDataScope("public_general");
    setMessages([
      { role: "assistant", text: "공개 일반 질문 전용 대화입니다." },
      { role: "assistant", text: "최근 대화·계좌·설정·전략·파일 문맥은 전달하지 않습니다. 민감한 내용을 입력하지 마세요." },
    ]);
    setMessage("공개 일반 질문 경로를 선택했습니다. 일반 안내 또는 화면 상태 질문에는 사용하지 마세요.");
  }
  function toggleVoiceInput() {
    if (!voice.enabled) { setMessage("설정 → AI 엔진/API → 고급 설정에서 음성 도우미를 먼저 활성화하세요."); return; }
    const Recognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!Recognition) { setMessage("이 실행 환경은 음성 인식을 지원하지 않습니다. Chromium/Electron 마이크 권한을 확인하세요."); return; }
    if (listening) { recognitionRef.current?.stop?.(); return; }
    const recognition = new Recognition();
    recognition.lang = voice.lang;
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.onstart = () => { setListening(true); setMessage("듣는 중… 완료하면 자동으로 입력칸에 옮깁니다."); };
    recognition.onresult = (event: any) => {
      const transcript = Array.from(event.results as ArrayLike<any>).map((result: any) => result[0]?.transcript || "").join("").trim();
      if (transcript) setQuestion(transcript);
    };
    recognition.onerror = (event: any) => setMessage(`음성 입력 실패: ${String(event.error || "마이크 권한을 확인하세요.")}`);
    recognition.onend = () => { setListening(false); setMessage((current) => current === "듣는 중… 완료하면 자동으로 입력칸에 옮깁니다." ? "음성 입력을 질문 칸에 옮겼습니다. 확인 후 전송하세요." : current); };
    recognitionRef.current = recognition;
    recognition.start();
  }
  const chartService = (["blockchain", "stock", "portfolio", "ai_analyst"].includes(service)
    ? service
    : null) as "blockchain" | "stock" | "portfolio" | "ai_analyst" | null;
  function openChartAnalysis() {
    if (!chartService) { onChartAnalysis?.(); return; }
    setChartOpen(true); setChartMessage("");
  }
  function selectChartFile(file?: File) {
    setChartResult(null); setChartMessage("");
    if (!file) { setChartFileName(""); setChartImage(""); return; }
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      setChartMessage("PNG, JPG 또는 WEBP 차트 스크린샷만 선택할 수 있습니다."); return;
    }
    if (file.size > 8_000_000) { setChartMessage("이미지는 8MB 이하만 분석할 수 있습니다."); return; }
    const reader = new FileReader();
    reader.onload = () => { setChartFileName(file.name); setChartImage(String(reader.result || "")); };
    reader.onerror = () => setChartMessage("이미지 파일을 읽지 못했습니다.");
    reader.readAsDataURL(file);
  }
  async function runChartAnalysis() {
    if (!chartService || !chartImage || !chartFileName) return;
    setChartBusy(true); setChartMessage(""); setChartResult(null);
    try {
      setChartResult(await client.analyzeChart(chartFileName, chartImage, chartService));
    } catch (reason) {
      setChartMessage(reason instanceof Error ? reason.message : "차트 분석에 실패했습니다.");
    } finally { setChartBusy(false); }
  }
  const chartAnalysis = chartResult?.analysis ?? {};
  return <><section className="legacy-assistant-workspace">
    <div className="assistant-info-bar">
      {onReturn ? <button className="assistant-return-button" type="button" onClick={onReturn}>← {returnLabel || "이전 화면으로 돌아가기"}</button> : <span />}
      <div><button type="button" onClick={() => navigator.clipboard?.writeText(messages.map((item) => `${item.role === "user" ? "사용자" : "NoahAI"}: ${item.text}`).join("\n\n"))}>전체 복사</button><button type="button" onClick={() => { const blob = new Blob([messages.map((item) => `${item.role === "user" ? "사용자" : "NoahAI"}: ${item.text}`).join("\n\n")], { type: "text/plain;charset=utf-8" }); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = "NoahAI-어시스턴트.txt"; anchor.click(); URL.revokeObjectURL(url); }}>TXT 저장</button></div>
    </div>
    <div className="assistant-main-grid">
      <article className="legacy-chat-panel">
        {service === "settings" && settingsSection && <div className="assistant-settings-context" role="status"><strong>설정 문맥 고정</strong><span>{SETTINGS_SECTION_LABELS[settingsSection] ?? settingsSection} 탭의 저장 상태와 안전 계약만 기준으로 답합니다.</span></div>}
        <div className="legacy-chat-history">{messages.map((item, index) => <div className={`legacy-chat-message ${item.role}`} key={`${item.role}-${index}`}><b>{item.role === "user" ? "사용자" : "NoahAI"}</b><p>{item.text}</p>{item.role === "assistant" && index >= 2 && onSendToStrategy && <button className="assistant-send-to-strategy" type="button" onClick={() => onSendToStrategy(item.text)}>이 답변을 전략 스튜디오 검토 영역으로 보내기</button>}</div>)}{busy && <div className="legacy-chat-message assistant"><b>NoahAI</b><p>질문을 확인하고 있습니다…</p></div>}</div>
        {message && <div className="inline-notice error-text">{message}</div>}
        {meta?.provider_failed && <div className="analysis-meta"><b>외부 분석 미완료 · 로컬 안내</b><span>{meta.provider_called ? `${String(meta.provider).toUpperCase()} · ${String(meta.model)} 호출 시도` : "Provider 응답 확인 전"}{meta.provider_status_code ? ` · HTTP ${meta.provider_status_code}` : ""} · {String(meta.provider_error ?? "연결 상태 확인 필요")}</span></div>}
        {meta?.provider_called && !meta?.provider_failed && <div className="analysis-meta"><b>{String(meta.provider).toUpperCase()} · {String(meta.model)}</b><span>{meta.privacy_route === "openai_shared_public_general" ? "공개 일반 질문용 Project" : meta.privacy_route === "protected_default_fallback" ? "기본 보호 경로로 대체" : "기본 보호 경로"} · {meta.cache_hit ? "캐시 응답 · 추가 호출 없음" : `토큰 ${Number(meta.usage?.total_tokens ?? 0).toLocaleString()} · 예상 $${meta.estimated_cost_usd ?? "산정 불가"}`}</span></div>}
        <form className="legacy-chat-input" onSubmit={submit}><input maxLength={4000} placeholder={profile.placeholder} value={question} onChange={(event) => setQuestion(event.target.value)} /><button className="send" disabled={busy || question.trim().length < 2} type="submit">전송</button><button className={listening ? "active" : ""} type="button" onClick={toggleVoiceInput}>{listening ? "듣기 중지" : "음성입력"}</button><button type="button" onClick={onOpenSettings}>설정관리</button><button type="button" onClick={openChartAnalysis}>차트분석</button></form>
      </article>
      <aside className="legacy-quick-question-panel"><h3>{profile.title}</h3><div>{profile.questions.map(([label, prompt]) => <button key={label} type="button" onClick={() => setQuestion(prompt)}>{label}</button>)}</div><footer><div className="assistant-mode-controls"><label>설명 수준<select aria-label="설명 수준" value={level} onChange={(event) => setLevel(event.target.value as typeof level)}><option value="beginner">초보자 · 따라하기</option><option value="standard">일반 · 핵심 요약</option><option value="advanced">고급 · 계약/근거</option></select></label><button className={mode === "guide" ? "active" : ""} onClick={() => { setMode("guide"); setDataScope("private"); }} title="제품 설정과 사용법을 로컬 정본으로 설명하며 외부 AI 비용이 들지 않습니다." type="button">일반 안내</button><button className={mode === "deep_analysis" ? "active danger" : ""} onClick={() => setMode("deep_analysis")} title="심층분석 (외부 AI·비용) · 사용자가 명시적으로 요청한 질문 1건만 외부 AI Provider로 분석하며 토큰 비용이 발생할 수 있습니다." type="button">심층분석</button></div>{mode === "deep_analysis" && <label className="assistant-public-route"><input type="checkbox" checked={dataScope === "public_general"} onChange={(event) => togglePublicGeneral(event.target.checked)} /><span>공개 일반 질문용 Project 사용</span><small>{publicRoute.public_general_effective ? "질문 1건만 전송 · 최근 대화와 앱 상태 제외" : "설정에서 별도 OpenAI Project 키와 공개 경로를 먼저 준비하세요."}</small></label>}<span>{mode === "guide" ? "일반 안내" : "심층분석 외부 AI 사용량"}</span><b>{mode === "guide" ? "외부 호출 없음" : `오늘 ${budget.daily_used ?? 0}/${budget.daily_limit ?? "—"} · 이번 달 ${budget.monthly_used ?? 0}/${budget.monthly_limit ?? "—"}`}</b>{budgetExhausted && <div className="assistant-budget-warning"><strong>외부 AI 사용 한도 도달</strong><span>비용·반복 호출 보호용 사용자 설정입니다. 일반 안내와 로컬 전략 분석은 계속됩니다.</span><button type="button" onClick={onOpenSettings}>AI 비용 한도 확인</button></div>}<small>{dataScope === "public_general" ? "공개 질문 모드: 질문 문장 외의 문맥을 보내지 않습니다. 전략·계좌·개인정보를 입력하지 마세요." : "기본 보호 경로: 초보자·일반·고급은 실제 프롬프트와 캐시 문맥이 분리됩니다."} 거래 설정은 변경하지 않습니다.</small></footer></aside>
    </div>
  </section>{chartOpen && chartService && <div className="modal-backdrop chart-analysis-backdrop" role="dialog" aria-modal="true" aria-label="차트 스크린샷 분석기"><section className="chart-analysis-dialog">
    <header><div><small>AI 어시스턴트 보조 도구</small><h2>차트 스크린샷 분석기</h2><p>PNG·JPG·WEBP 이미지를 OCR과 설정된 비전 AI로 분석합니다. 분석은 주문을 실행하지 않습니다.</p></div><button type="button" disabled={chartBusy} onClick={() => setChartOpen(false)}>×</button></header>
    <div className="chart-analysis-body">
      <div className="chart-upload-panel">
        <label className="chart-file-picker">차트 이미지 선택<input type="file" accept="image/png,image/jpeg,image/webp" disabled={chartBusy} onChange={(event) => selectChartFile(event.target.files?.[0])} /></label>
        <small>최대 8MB · 심볼, 시간봉, 가격축과 지표 이름이 함께 보이도록 캡처하세요.</small>
        {chartImage ? <img src={chartImage} alt="분석할 차트 미리보기" /> : <div className="chart-empty-preview">선택한 차트 미리보기가 여기에 표시됩니다.</div>}
        <div className="chart-analysis-actions"><button className="primary-button" type="button" disabled={!chartImage || chartBusy} onClick={() => void runChartAnalysis()}>{chartBusy ? "분석 중…" : "외부 비전 AI로 분석"}</button><button type="button" disabled={chartBusy} onClick={() => { setChartFileName(""); setChartImage(""); setChartResult(null); setChartMessage(""); }}>초기화</button></div>
        <p className="chart-cost-note">이 버튼을 누를 때만 이미지가 설정된 Analyst Provider로 전송되며 1회 AI API 비용과 일·월 예산을 사용합니다.</p>
      </div>
      <div className="chart-result-panel">
        {chartMessage && <div className="inline-notice error-text">{chartMessage}</div>}
        {!chartResult && !chartMessage && <div className="honest-empty-state"><b>분석 결과 없음</b><span>이미지를 선택하고 분석을 실행하세요. 읽을 수 없는 값은 추정하지 않습니다.</span></div>}
        {chartResult && <><div className="chart-result-summary"><span className={`state-pill ${String(chartAnalysis.stance || "NEUTRAL").toLowerCase()}`}>{String(chartAnalysis.stance || "NEUTRAL")}</span><b>{String(chartAnalysis.summary || "분석 요약이 없습니다.")}</b><small>신뢰도 {Math.round(Number(chartAnalysis.confidence || 0) * 100)}% · {String(chartResult.provider).toUpperCase()} / {String(chartResult.model)}</small></div>
          <section><h3>화면에서 확인된 근거</h3>{(chartAnalysis.visible_evidence || []).map((item: unknown, index: number) => <p key={`e-${index}`}>• {String(item)}</p>)}</section>
          <section><h3>위험·불확실성</h3>{(chartAnalysis.risks || []).map((item: unknown, index: number) => <p key={`r-${index}`}>• {String(item)}</p>)}</section>
          <section><h3>참고 플랜</h3><pre>{JSON.stringify(chartAnalysis.plan || {}, null, 2)}</pre></section>
          {chartResult.ocr?.warning && <p className="chart-ocr-warning">OCR 안내: {String(chartResult.ocr.warning)} 비전 분석 결과와 구분해 확인하세요.</p>}
          <small>주문 실행: 없음 · 사용량 {Number(chartResult.usage?.total_tokens || 0).toLocaleString()} tokens · 예상 비용 {chartResult.estimated_cost_usd ?? "산정 불가"}</small></>}
      </div>
    </div>
  </section></div>}</>;
}


function highlightedManualText(content: string, query: string): ReactNode {
  const target = query.trim();
  if (!target) return content;
  const escaped = target.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const parts = content.split(new RegExp(`(${escaped})`, "gi"));
  return parts.map((part, index) => part.toLocaleLowerCase("ko-KR") === target.toLocaleLowerCase("ko-KR")
    ? <mark key={`${part}-${index}`}>{part}</mark>
    : <Fragment key={`${part}-${index}`}>{part}</Fragment>);
}

type ManualDocumentBlock =
  | { kind: "heading"; level: 2 | 3 | 4; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "checklist"; items: string[] }
  | { kind: "note"; items: string[] }
  | { kind: "table"; rows: string[][] };

const MANUAL_SEPARATOR = /^[━─═—=\-\s]{8,}$/;
const MANUAL_BULLET = /^(?:•|[-*])\s+(.+)$/;
const MANUAL_ORDERED = /^\d+[.)]\s+(.+)$/;
const MANUAL_CHECK = /^(?:□|☐|\[\s?\])\s*(.+)$/;

function manualHeadingAt(lines: string[], index: number): { level: 2 | 3 | 4; text: string } | null {
  const text = lines[index].trim();
  if (!text || MANUAL_SEPARATOR.test(text) || text.includes("|")) return null;
  if (MANUAL_BULLET.test(text) || MANUAL_ORDERED.test(text) || MANUAL_CHECK.test(text) || text.startsWith("※")) return null;
  const markdown = text.match(/^(#{1,4})\s+(.+)$/);
  if (markdown) return { level: markdown[1].length <= 2 ? 2 : markdown[1].length === 3 ? 3 : 4, text: markdown[2] };
  const firstTextIndex = lines.findIndex((line) => Boolean(line.trim()));
  if (index === firstTextIndex) return { level: 2, text };
  const previous = lines[index - 1]?.trim() ?? "";
  const next = lines[index + 1]?.trim() ?? "";
  if (MANUAL_SEPARATOR.test(previous) || MANUAL_SEPARATOR.test(next)) return { level: 3, text };
  const bracketed = text.match(/^\[([^\]]+)\]$/);
  if (bracketed) return { level: 4, text: bracketed[1] };
  if (/^v?\d+\.\d+(?:\.\d+){0,2}(?:\s|$)/i.test(text)) return { level: 3, text };
  return null;
}

function manualLineStartsBlock(lines: string[], index: number): boolean {
  const text = lines[index]?.trim() ?? "";
  return !text || MANUAL_SEPARATOR.test(text) || Boolean(manualHeadingAt(lines, index)) || MANUAL_BULLET.test(text)
    || MANUAL_ORDERED.test(text) || MANUAL_CHECK.test(text) || text.startsWith("※") || text.includes("|");
}

function parseManualDocument(content: string): ManualDocumentBlock[] {
  const lines = content.replace(/\r\n?/g, "\n").split("\n");
  const blocks: ManualDocumentBlock[] = [];
  let index = 0;
  while (index < lines.length) {
    const text = lines[index].trim();
    if (!text || MANUAL_SEPARATOR.test(text)) { index += 1; continue; }

    const heading = manualHeadingAt(lines, index);
    if (heading) { blocks.push({ kind: "heading", ...heading }); index += 1; continue; }

    if (text.includes("|")) {
      const rows: string[][] = [];
      while (index < lines.length && lines[index].trim().includes("|")) {
        const cells = lines[index].trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
        if (!cells.every((cell) => /^:?-{3,}:?$/.test(cell))) rows.push(cells);
        index += 1;
      }
      if (rows.length >= 2) blocks.push({ kind: "table", rows });
      else if (rows.length) blocks.push({ kind: "paragraph", text: rows[0].join(" · ") });
      continue;
    }

    if (text.startsWith("※")) {
      const items: string[] = [];
      while (index < lines.length) {
        const note = lines[index].trim();
        if (!note) break;
        if (note.startsWith("※")) items.push(note.replace(/^※\s*/, ""));
        else if (/^\s+/.test(lines[index]) && items.length && !manualLineStartsBlock(lines, index)) items[items.length - 1] += ` ${note}`;
        else break;
        index += 1;
      }
      blocks.push({ kind: "note", items });
      continue;
    }

    const checklist = MANUAL_CHECK.exec(text);
    if (checklist) {
      const items: string[] = [];
      while (index < lines.length) {
        const match = MANUAL_CHECK.exec(lines[index].trim());
        if (!match) break;
        items.push(match[1]); index += 1;
      }
      blocks.push({ kind: "checklist", items });
      continue;
    }

    const bullet = MANUAL_BULLET.exec(text);
    const ordered = MANUAL_ORDERED.exec(text);
    if (bullet || ordered) {
      const isOrdered = Boolean(ordered);
      const matcher = isOrdered ? MANUAL_ORDERED : MANUAL_BULLET;
      const items: string[] = [];
      while (index < lines.length) {
        const match = matcher.exec(lines[index].trim());
        if (match) { items.push(match[1]); index += 1; continue; }
        const continuation = lines[index].trim();
        if (continuation && /^\s+/.test(lines[index]) && items.length && !manualLineStartsBlock(lines, index)) {
          items[items.length - 1] += ` ${continuation}`; index += 1; continue;
        }
        break;
      }
      blocks.push({ kind: "list", ordered: isOrdered, items });
      continue;
    }

    const paragraph: string[] = [text];
    index += 1;
    while (index < lines.length && !manualLineStartsBlock(lines, index)) {
      paragraph.push(lines[index].trim()); index += 1;
    }
    blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
  }
  return blocks;
}

function ManualDocumentContent({ sectionId, content, query }: { sectionId: string; content: string; query: string }) {
  const blocks = useMemo(() => parseManualDocument(content), [content]);
  const chapterLinks = blocks.map((block, index) => ({ block, index }))
    .filter(({ block }) => block.kind === "heading" && block.level <= 3)
    .slice(1, sectionId === "updates" ? 20 : 16) as Array<{ block: Extract<ManualDocumentBlock, { kind: "heading" }>; index: number }>;
  const jumpTo = (index: number) => document.getElementById(`manual-${sectionId}-block-${index}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  return <section className="manual-document" aria-label="전체 사용자 설명">
    <header className="manual-document-header">
      <div><span>전체 사용 설명</span><h4>접힌 원문 없이, 모든 내용을 읽기 쉽게 정리했습니다.</h4></div>
      <p>제목·목록·체크리스트·표를 구분했습니다. 상단 검색은 이 본문 전체에서 실제 일치 항목을 한 건씩 찾습니다.</p>
    </header>
    {chapterLinks.length > 1 && <nav className="manual-document-index" aria-label="이 탭의 목차">
      {chapterLinks.map(({ block, index }) => <button key={`${block.text}-${index}`} type="button" onClick={() => jumpTo(index)}>{highlightedManualText(block.text, query)}</button>)}
    </nav>}
    <div className="manual-document-body">
      {blocks.map((block, index) => {
        const key = `${block.kind}-${index}`;
        if (block.kind === "heading") {
          const Heading = block.level === 2 ? "h2" : block.level === 3 ? "h3" : "h4";
          return <Heading id={`manual-${sectionId}-block-${index}`} className={`manual-doc-heading level-${block.level}`} key={key}>{highlightedManualText(block.text, query)}</Heading>;
        }
        if (block.kind === "paragraph") return <p className="manual-doc-paragraph" key={key}>{highlightedManualText(block.text, query)}</p>;
        if (block.kind === "note") return <aside className="manual-doc-note" key={key}>{block.items.map((item, itemIndex) => <p key={itemIndex}>{highlightedManualText(item, query)}</p>)}</aside>;
        if (block.kind === "checklist") return <ul className="manual-doc-checklist" key={key}>{block.items.map((item, itemIndex) => <li key={itemIndex}><span aria-hidden="true">✓</span>{highlightedManualText(item, query)}</li>)}</ul>;
        if (block.kind === "list") {
          const List = block.ordered ? "ol" : "ul";
          return <List className={`manual-doc-list ${block.ordered ? "ordered" : "bulleted"}`} key={key}>{block.items.map((item, itemIndex) => <li key={itemIndex}>{highlightedManualText(item, query)}</li>)}</List>;
        }
        return <div className="manual-document-table-wrap" key={key}><table className="manual-document-table"><thead><tr>{block.rows[0].map((cell, cellIndex) => <th key={cellIndex}>{highlightedManualText(cell, query)}</th>)}</tr></thead><tbody>{block.rows.slice(1).map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{highlightedManualText(cell, query)}</td>)}</tr>)}</tbody></table></div>;
      })}
    </div>
  </section>;
}

export function ManualCenter({ client, onClose, onAskAssistant, onOpenSettings, onNavigate, initialTab = "intro" }: { client: GatewayClient; onClose: () => void; onAskAssistant: (question: string) => void; onOpenSettings?: () => void; onNavigate?: (service: string, feature: string) => void; initialTab?: string }) {
  const [activeTab, setActiveTab] = useState(initialTab);
  const [manualSections, setManualSections] = useState<ManualSection[]>([]);
  const [query, setQuery] = useState("");
  const [searchStatus, setSearchStatus] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [searchCursor, setSearchCursor] = useState(-1);
  const [searchOccurrence, setSearchOccurrence] = useState(0);
  const [guideError, setGuideError] = useState("");
  const manualContentRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    client.manual()
      .then((snapshot) => {
        setManualSections(snapshot.sections);
        setActiveTab(snapshot.sections.some((item) => item.id === initialTab) ? initialTab : "intro");
        setGuideError("");
      })
      .catch((reason) => setGuideError(reason instanceof Error ? reason.message : "사용자 메뉴얼 정본을 불러오지 못했습니다."));
  }, [client, initialTab]);
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);
  const active = manualSections.find((item) => item.id === activeTab) ?? manualSections[0];
  const highlightedContent = useMemo(() => highlightedManualText(active?.content ?? "사용자 메뉴얼 정본을 불러오는 중입니다…", query), [active?.content, query]);
  useEffect(() => {
    if (!searchTerm || searchCursor < 0) return;
    let innerFrame = 0;
    const frame = window.requestAnimationFrame(() => {
      innerFrame = window.requestAnimationFrame(() => {
        const marks = manualContentRef.current?.querySelectorAll(".manual-document-body mark") ?? [];
        marks[Math.min(searchOccurrence, Math.max(0, marks.length - 1))]?.scrollIntoView({ block: "center" });
      });
    });
    return () => { window.cancelAnimationFrame(frame); window.cancelAnimationFrame(innerFrame); };
  }, [activeTab, searchCursor, searchOccurrence, searchTerm]);
  function searchManual() {
    const target = query.trim().toLocaleLowerCase("ko-KR");
    if (!target) { setSearchStatus("검색어 입력"); return; }
    const hits = manualSections.flatMap((item) => {
      const source = item.content.toLocaleLowerCase("ko-KR");
      const sectionHits: Array<{ sectionId: string; occurrence: number; label: string }> = [];
      let offset = 0;
      let occurrence = 0;
      while (offset <= source.length) {
        const found = source.indexOf(target, offset);
        if (found < 0) break;
        sectionHits.push({ sectionId: item.id, occurrence, label: item.label });
        occurrence += 1;
        offset = found + Math.max(1, target.length);
      }
      return sectionHits;
    });
    if (!hits.length) { setSearchTerm(target); setSearchCursor(-1); setSearchStatus("검색 결과 없음"); return; }
    const nextIndex = searchTerm === target ? (searchCursor + 1) % hits.length : 0;
    const next = hits[nextIndex];
    setSearchTerm(target);
    setSearchCursor(nextIndex);
    setSearchOccurrence(next.occurrence);
    setActiveTab(next.sectionId);
    setSearchStatus(`${nextIndex + 1}/${hits.length} · ${next.label}`);
  }
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section aria-modal="true" aria-labelledby="manual-center-title" className="manual-modal" role="dialog">
      <header className="manual-header"><h2 id="manual-center-title">▥ NoahAI - AI 금융 의사결정 인프라</h2><p>현재 버전 기준 기능 안내 · 실제 화면 순서 · 운영 경계</p></header>
      <div className="manual-toolbar">
        <div className="manual-quick-links">{[["실거래 준비", "live"], ["설정 가이드", "settings"], ["전략 스튜디오", "custom"], ["거래소·증권", "assets"], ["업데이트", "updates"]].map(([label, id]) => <button key={id} type="button" onClick={() => setActiveTab(id)}>{label}</button>)}</div>
        <div className="manual-search"><input placeholder="전체 메뉴얼에서 기능·설정·오류 검색" value={query} onChange={(event) => { setQuery(event.target.value); setSearchTerm(""); setSearchCursor(-1); setSearchStatus(""); }} onKeyDown={(event) => event.key === "Enter" && searchManual()} /><button type="button" onClick={searchManual}>검색 결과 다음</button>{query && <button type="button" onClick={() => { setQuery(""); setSearchTerm(""); setSearchCursor(-1); setSearchStatus(""); }}>지우기</button>}<button className="primary-button" type="button" onClick={() => onAskAssistant(query.trim() ? `사용자 매뉴얼에서 '${query.trim()}'을 찾고 있었습니다. 현재 설정과 실제 작동 기준으로 초보자도 이해하게 설명해줘.` : "현재 버전에서 실행 모드, 거래소 선택, 전략 스튜디오 사용 난이도, 고급 매매 계층과 AlphaArena를 초보자도 이해하게 설명해줘.")}>AI에게 묻기</button><span role="status">{searchStatus}</span></div>
      </div>
      <nav className="manual-tabs">{manualSections.map((item) => <button className={item.id === activeTab ? "active" : ""} key={item.id} onClick={() => setActiveTab(item.id)} type="button">{item.label}</button>)}</nav>
      {guideError && <div className="inline-notice error-text">{guideError}</div>}
      <div className={`manual-content ${active && (active.id === "intro" || MANUAL_GUIDES[active.id]) ? "manual-rich-content" : ""}`} ref={manualContentRef}>
        {active?.id === "intro"
          ? <ManualIntroContent content={active?.content ?? ""} query={query} />
          : active && MANUAL_GUIDES[active.id]
            ? <ManualGuideContent sectionId={active.id} content={active.content} query={query} />
            : <pre className="manual-raw-content">{highlightedContent}</pre>}
      </div>
      <footer><div className="manual-deep-links">
        <button className="manual-action-button" type="button" onClick={onOpenSettings}>설정 화면 열기</button>
        {activeTab === "custom" && <button type="button" onClick={() => onNavigate?.("blockchain", "blockchain.ai_custom")}>전략 스튜디오 화면 열기</button>}
        {activeTab === "assets" && <><button type="button" onClick={() => onNavigate?.("blockchain", "blockchain.source_workspaces")}>거래소 화면 열기</button><button type="button" onClick={() => onNavigate?.("stock", "stock.source_workspaces")}>증권사 화면 열기</button></>}
      </div><button className="manual-close-button" onClick={onClose} type="button">× 닫기</button></footer>
    </section>
  </div>;
}
