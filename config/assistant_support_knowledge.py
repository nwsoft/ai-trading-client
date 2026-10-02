"""Versioned, read-only support facts. No network, settings writes or trading actions.

Specific diagnostic codes precede broad product terms. A guide explains a code;
it never certifies an individual incident as fixed or a command as executed.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

GUIDE_REVISION = "3.9.2.2-support.20261002.2"


@dataclass(frozen=True)
class SupportTopic:
    key: str
    triggers: tuple[str, ...]
    source: str
    ko: str
    en: str


TOPICS = (
    SupportTopic("finance_products", ("금융상품비교", "대출비교", "원리금균등", "원금균등", "중도상환", "우대조건", "우대금리", "최저광고금리", "예금", "적금", "loan comparison", "savings comparison"),
        "docs/LIFE_FINANCE_GUIDE.md",
        "생활금융 → 금융상품의 전체 안내 / 대출 비교 / 보험 비교 / 예금·적금 비교 탭을 이용하세요. 처음에는 가상 예시로 연습하고, 내 조건은 비우고 직접 입력합니다. "
        "화면의 두 조건은 금융사 실시간 견적이나 전체 상품 순위가 아닙니다. 계산 입력은 PC 화면 메모리에만 두며 계좌/가계부에 저장하거나 신청하지 않습니다.\n"
        "대출: 원리금균등은 원금+이자를 합한 월 상환액을 일정하게, 원금균등은 매달 같은 원금을 갚아 월 이자가 감소하게 계산합니다. 만기일시는 기간 중 이자, 마지막에 원금을 갚습니다. "
        "가상으로 120만 원을 무이자로 12개월 균등 상환하면 월 10만 원이지만, 만기일시는 마지막에 원금 120만 원이 필요합니다. "
        "광고 최저 금리와 실제 적용 금리는 다를 수 있습니다. 변동 주기·우대 요건·인지세/보증료 등 비용·중도상환 수수료를 금융사에 확인하세요. 비용 미입력은 0원이 아닙니다.\n"
        "예금은 목돈 한 번, 적금은 매달 새 돈을 넣으므로 같은 연 금리라도 이자가 다릅니다. 가상으로 120만 원 예금과 월 10만 원 적금을 12개월, 단리 연 3%로 비교하면 세전 이자는 각각 36,000원과 19,500원입니다(적금 매월 초 납입 가정). "
        "세율은 자격·상품을 확인해 입력하며 미입력 시 세전 이자까지만 표시합니다. 우대 조건·적용 한도·예금보호 여부·중도해지 금리를 확인하세요.\n"
        "실제 일수·복리·금리 변경·연체·중도해지는 계산 범위 밖입니다. 금리만으로 가입·대환·해지를 권하지 않습니다. AI 도움은 질문 초안을 연 뒤 직접 전송하며 보험 원문이나 비교 입력을 자동 첨부하지 않습니다.",
        "Use Everyday Finance → Financial Products: Overview, Loans, Insurance, Deposits and Savings. Examples are fictional; clear them before entering actual terms. Loan calculations support annuity, equal principal and bullet repayment, with constant rates and monthly periods. Unknown fees are not zero. Deposits pay interest on an initial lump sum; installment savings use equal beginning-of-month deposits and simple interest. Enter the applicable tax rate yourself; otherwise only pre-tax interest is shown. Check eligibility, preferential-rate requirements, fees, deposit protection and early termination with the provider. These are local scenarios, not live quotes or recommendations. AI help prepares a draft only and does not automatically attach private documents or inputs."),
    SupportTopic("insurance_workspace", ("보험", "insurance", "insurance_vault", "insurance_quote_not_found"),
        "docs/LIFE_FINANCE_GUIDE.md",
        "생활금융 → 금융상품 → 보험 비교 → 내 보험 이해·비교에서 보험 자료 전용 비밀번호(12자 이상)로 계정별 암호화 저장소를 엽니다. "
        "앱 로그인 비밀번호와 별개이고 분실하면 복구할 수 없습니다. 암호화 백업과 비밀번호를 별도로 보관하세요.\n"
        "제공 권한이 있는 PDF·PNG·JPEG를 등록한 뒤 원문과 직접 입력한 보험료·납입 주기·보장·제외 조건을 대조하고 확인 저장하세요. "
        "스캔·이미지는 자동 OCR/보험 해석을 하지 않으며 수동 대조가 필요합니다. 파일당 20MB·PDF 100쪽, 저장 원본 합계 20MB·5개, 한 번에 1개입니다. "
        "암호 문서는 여기서 해제하지 않습니다. 잘못된 페이지·인용문은 원문에서 다시 확인하세요.\n"
        "확인한 계약 1개를 점검하거나 2개를 사실 비교합니다. 미확인 금액은 0원이 아니며 월 환산 차이는 절감액이나 같은 보장을 뜻하지 않습니다. "
        "실손/정액, 면책·감액·갱신·해약환급 손실·신규 인수 여부는 보험사에 확인하세요. 유지도 선택지입니다. "
        "자료 수정·삭제 후에는 다시 확인하고 비교하세요. 상담 질문지는 내용을 검토한 뒤 로컬 TXT로 저장하며 자동 가림은 완전하지 않습니다. "
        "보험금액을 자산에 더하거나 가계부에 자동 기록하지 않습니다. 전 보험사 추천·상담원 자동 접수는 지원하지 않습니다. "
        "보험 전용 외부 전송 동의 경로가 없으므로 이 질문은 심층분석을 선택해도 로컬 안내로 답하며 보험 원문을 외부 AI로 보내지 않습니다.",
        "Open Everyday Finance → Financial products → My insurance, using a separate vault password (12+ characters). "
        "The account-scoped vault is encrypted; a lost password cannot be recovered. Keep an encrypted backup and the password separately. "
        "Register authorized PDF/PNG/JPEG files, inspect the source and enter premiums, payment cycles, coverage and exclusions yourself. "
        "Scans/images require manual review, not automatic OCR or policy interpretation. Limits: 20 MB per file, 100 PDF pages, 5 documents/20 MB originals total, one job at a time. "
        "Confirm before reviewing one contract or comparing two. Unknown is not zero; a monthly premium difference is not a saving or equivalent coverage. "
        "Verify indemnity/fixed benefits, waiting/reduction/renewal terms, surrender losses and new underwriting with the insurer. Retaining a policy is a valid option. "
        "Changes invalidate comparisons. Preview and redact consultation questions before local unencrypted TXT export. No ledger writes, asset additions, universal recommendations or adviser submissions occur. "
        "Insurance-specific external-sharing consent is not available: even deep-analysis insurance questions receive this local guide without sending documents to an external AI."),
    SupportTopic("candidate_selection", ("trading_candidates_unavailable", "candidate_selection", "후보가없", "후보선정실패", "okx시작", "okx거래시작"),
        "docs/V3920_CUSTOMER_FEEDBACK_REVIEW.md",
        "후보 선정 단계의 시작 보류입니다. 거래 원장 복구 오류나 API 키 오류라고 단정할 수 없습니다. "
        "3.9.2.0에서는 OKX 개별 ticker 대체 조회 시 거래대금 근거 보존과 후보 제외 진단을 보강했습니다. 모든 사용자의 장애 해소를 뜻하지 않습니다.\n"
        "해당 기관의 코인·종목 정보에서 선정 결과, 제외 사유, 상품·거래 상태, 시세 수신 시각을 확인하세요. "
        "후보 0개가 필터 결과인지 조회 실패인지 구분해야 합니다. 다른 기관이 정상이어도 기관별 시세·상품 형식·응답 실패가 달라 같은 결과를 보장하지 않습니다. "
        "확인 불가 종목을 강제로 허용하거나 필터를 모두 끄지 마세요. 후보 확보 후 사용자가 다시 시작하고 실제 실행 상태를 확인하세요.",
        "Start was withheld during candidate selection. This alone does not establish a ledger or API-key fault. In 3.9.2.0, OKX fallback ticker turnover evidence and exclusion diagnostics were improved; that is not proof that your incident is resolved. Check the venue's instrument list, exclusion reasons, product status and quote timestamp. Distinguish zero eligible candidates from a failed query. Do not bypass eligibility filters. Retry after candidates are available and verify actual runtime state."),
    SupportTopic("shutdown", ("worker_shutdown_timeout", "runtime_still_alive", "woker", "안전종료실패", "키움종료", "shutdown timeout"),
        "docs/V3920_CUSTOMER_FEEDBACK_REVIEW.md",
        "거래 워커가 제한 시간 안에 종료되지 않았거나 실행 핸들이 아직 살아 있다는 뜻입니다. 종료 실패를 주문 청산 완료로 해석하면 안 됩니다. "
        "3.9.2.0은 키움 읽기 취소·워커 종료·연결 정리와 연속 조회 시간초과의 재시도 간격을 보강했습니다. Windows COM 실제 종료 확인은 별도입니다.\n"
        "현재 실행 상태·미체결·보호주문은 앱과 증권사에서 확인하세요. 강제 종료나 반복 시작을 첫 조치로 권하지 않습니다. "
        "멈춘 기관, 종료 요청 시각, worker_shutdown_timeout/runtime_still_alive 코드와 직전 읽기 요청 종류를 비식별 진단으로 전달하세요. "
        "이 안내만으로 워커 종료나 계좌 안전을 확인한 것은 아닙니다.",
        "The worker did not stop within its timeout, or its runtime handle is still alive. This is not confirmation that positions were closed. 3.9.2.0 improved Kiwoom read cancellation, shutdown ordering and read retry cooldowns; Windows COM verification remains separate. Check runtime state and open/protective orders in the app and broker. Do not repeatedly start or force-kill as a default remedy. Provide redacted codes, venue, time and preceding read-request type."),
    SupportTopic("reconciliation", ("pnl_reconciliation_required", "과거관리원장", "미청산기록", "미확정손익", "pnl초기화", "거래기록복구"),
        "docs/USER_GUIDE.md",
        "과거 관리 원장과 실제 체결의 대조가 필요할 수 있습니다. 설정 → 업데이트 → 유지관리 → 거래 기록 점검·복구에서 기관과 조회 진행·미확정 사유를 확인하세요. "
        "최근 구간의 해소와 전체 과거 복구 완료는 다릅니다. 수동 거래·부분청산·여러 진입의 귀속이나 비용 근거가 부족하면 미확정으로 남습니다. "
        "PnL 표시 기준 초기화는 누락 체결 복구가 아니며, 거래 차단 우회를 위해 원장 삭제·손익 0 처리·위험 제한 해제를 하지 마세요. "
        "복구 완료 뒤에도 시작 재평가와 실행 상태 확인이 필요합니다.",
        "Reconciliation needs actual fill and ownership evidence. Use Settings → Updates → Maintenance → Trade record recovery and inspect venue, paging progress and unresolved reasons. A cleared recent window is not full-history recovery. Mixed/manual/partial trades or missing costs may remain unresolved. Resetting the display baseline does not repair fills; never delete the ledger or set unknown PnL to zero to bypass a guard. Verify start reevaluation after recovery."),
    SupportTopic("start_diagnostic", ("start_refused_check_displayed_reason", "409", "거래시작오류", "거래시작실패", "시작진단"),
        "web_platform/runtime_bridge.py",
        "409는 요청과 현재 실행 조건이 충돌했다는 응답이며 원인 코드가 아닙니다. start_refused_check_displayed_reason도 포괄 안내이므로 이 코드만으로 복구 실패 원인을 확정할 수 없습니다. "
        "거래 시작 진단의 지원 코드·실패 단계·원래 사유를 먼저 확인하세요. candidate_selection은 후보·시세, 원장 대조 코드는 거래 기록, 권한 코드는 회원·거래 권한을 각각 확인해야 합니다. "
        "사유가 비어 있으면 근거 부족입니다. 모든 409에 거래 기록 복구나 API 키 재발급을 권하지 않습니다. "
        "거부를 무시하고 시작하지 말고 원인에 맞는 조치 후 재평가하세요. 요청 접수와 시작 완료는 다릅니다.",
        "HTTP 409 reports a state conflict, not its root cause. start_refused_check_displayed_reason is also generic. Inspect the support code, failed stage and original reason. Candidate failures, reconciliation and membership permissions require different remedies. Empty reasons mean insufficient evidence. Do not bypass the refusal or prescribe ledger recovery/API-key replacement for every 409. Request acceptance is not start completion."),
    SupportTopic("rate_limit", ("429", "interactive_ai_budget_exceeded", "심층분석한도", "30회제한"),
        "web_platform/interactive_ai.py",
        "429만으로는 원인을 확정하지 않습니다. interactive_ai_budget_exceeded는 Provider 호출 전 NoahAI의 대화형 비용 한도이고, Provider가 반환한 429는 요청 속도·동시 요청·쿼터·결제 등 별도 문제입니다. "
        "설정 → AI 엔진/API → AI 비용 관리에서 저장 한도와 사용량을 확인하세요. 외부 제공사 429라면 제공사의 상태·Usage·응답 재시도 시각을 확인하세요. "
        "일반 안내는 외부 AI 호출 없이 계속됩니다. 한도를 올려도 모델 권한 오류는 해결되지 않으며 비용이 증가할 수 있습니다. "
        "호출 거부 건수만으로 거래 엔진이 멈췄다거나 AI가 특정 비율만 작동했다고 계산할 수 없습니다.",
        "429 alone is ambiguous. interactive_ai_budget_exceeded is NoahAI's pre-call interactive budget guard; a provider 429 may be rate, concurrency, quota or billing related. Check saved limits/usage in AI Engine/API and the provider response/status as applicable. Local guides remain available. Raising a budget does not fix model permissions. Denial counts do not measure trading-engine downtime."),
    SupportTopic("paper_capacity", ("평가한도", "평가용량", "후보10", "10개제한", "30개", "40개전략", "paper capacity"),
        "docs/UPDATE_PLAN.md",
        "같은 PAPER 실행 풀의 동시 전략 평가 한도는 일반 최대 10개, 프리미엄 최대 30개이며 사용자 설정으로 더 낮출 수 있습니다. "
        "저장 전략 수·범위 적합·평가 대상·대기·조건 통과·가상 포지션 수는 서로 다릅니다. 적용 전략도 슬롯을 사용합니다. "
        "대기는 검증 실행 중이 아니며 자동 공정 순환이나 전략별 독립 계좌를 제공한다는 뜻이 아닙니다. "
        "LIVE 병행 독립 PAPER의 별도 용량과 실제/가상 포지션 한도는 이 10/30 정책으로 늘어나지 않습니다.",
        "The shared PAPER evaluation pool supports up to 10 strategies for standard membership and 30 for premium; user settings may lower this. Saved, eligible, evaluated, waiting, passing and positioned counts differ. Applied strategies consume slots. Waiting is not active validation or automatic fair rotation. LIVE-concurrent independent PAPER and position limits remain separate."),
    SupportTopic("bulk_strategy", ("일괄", "다중선택", "선택된전략", "선택삭제", "선택하기"),
        "docs/V3920_CUSTOMER_FEEDBACK_REVIEW.md",
        "전략 스튜디오 → 내 프라이빗 전략 버전에서 선택 후 삭제·일시중지·전략 내보내기·패키지 내보내기·PAPER 시작을 요청할 수 있습니다. "
        "현재 검색 결과만 전체 선택하며 필터·범위 변경 시 선택이 풀립니다. 최대 100개를 순차 처리하고 개별 성공·보류·실패를 확인합니다. "
        "활성/검증 중 버전은 바로 삭제하지 못하며 일시중지는 적용 해제 또는 PAPER 중지이지 강제청산이 아닙니다. "
        "PAPER 시작은 기존 승인·실행식·기관 범위·한도를 그대로 검사합니다. 자동 승인·검증 초기화·LIVE 전환은 하지 않습니다. "
        "정의와 근거 포함 패키지는 다르며 ZIP을 풀어 기존 가져오기로 확인합니다.",
        "In My private strategy versions, select versions for deletion, pause, definition/package export or PAPER start. Select-all covers current search results; changing scope/filters clears selection. Up to 100 are processed sequentially with per-item outcomes. Active/validating versions cannot simply be deleted. Pause is not liquidation. Approval, executable rules, scope and capacity checks still apply. There is no automatic approval, evidence reset or LIVE switch."),
    SupportTopic("strategy_flow", ("백테스트없이", "백테스트필수", "백테스트통과", "level", "레벨", "기존전략복구", "빈실행식", "실행식누락", "전략스튜디오사용법"),
        "ui/ai_custom_guidance.py",
        "전략 스튜디오는 Level 1~5를 지원합니다. 단계는 제작·표시 복잡도이며 수익 등급이나 안전 검사 면제권이 아닙니다. "
        "과거 시세 재생은 선택적 역사 시뮬레이션입니다. 유효한 실행식과 사용자 승인 등 PAPER 자격을 충족하면 백테스트 합격 없이 PAPER를 시작할 수 있습니다. "
        "PAPER 시작 자격, 검증 결과, 최종 적용, LIVE 권한은 별도입니다. PAPER 성과가 과거재생과 같아야 한다는 뜻도 아니고 수익 보장도 아닙니다. "
        "기존 원문·성과를 보존하고 보완 질문 → 재분석 → 새 버전 저장 → 사용자 승인으로 수정하세요. "
        "미지원·모호한 조건을 삭제하거나 임의 숫자로 채워 정상 실행식으로 만들지 않습니다. 0건은 실패 확정이 아니라 조건·기간·실행 상태를 확인할 근거입니다.",
        "Strategy Studio supports Levels 1–5 for authoring/display complexity, not return grades or guard exemptions. Historical replay is optional. An executable, user-approved version may start PAPER without passing a backtest, subject to PAPER eligibility. PAPER start, validation outcome, final application and LIVE authorization are separate. Preserve legacy sources/results and clarify, reanalyse, save a new version and approve it; do not invent missing rules. Zero trades is not proof of failure."),
    SupportTopic("indicator_contract", ("support_level", "resistance_level", "historical_volatility", "di_plus", "di_minus", "became_true"),
        "trading/strategy_source_ingestor.py",
        "지원 지표도 정의·시간봉·충분한 과거 봉이 일치해야 합니다. support_level/resistance_level은 현재 봉을 제외한 직전 완료 종가 20개의 최소/최대이며 임의 피벗이나 호가벽이 아닙니다. "
        "volatility/historical_volatility는 20개 로그수익률의 모집단 표준편차(%)로 연환산값이 아닙니다. di_plus/di_minus는 14기간 TR/DM 합 기준이며 Wilder RMA와 다릅니다. "
        "필드 간 비교와 지원되는 became_true 조건은 이전/현재 완료 봉의 같은 정의를 사용합니다. 첫 표본·누락값을 거짓/0으로 채우지 말고 보완하세요. "
        "원문 지표 정의가 다르면 이름만 맞춰 변환하지 않습니다.",
        "Indicator definitions and completed-bar timeframes must match. Support/resistance are min/max of the previous 20 completed closes, excluding the current bar, not pivots or order-book walls. Volatility/historical_volatility are population deviation of 20 log returns in percent, not annualized. DI uses 14-period rolling TR/DM sums, not Wilder RMA. Field comparisons and supported became_true conditions need compatible prior/current evidence; do not invent missing values."),
    SupportTopic("source_upload", ("업로드", "파일선택", "drive", "드라이브", "폴더자료"),
        "trading/strategy_source_ingestor.py",
        "자료 선택과 분석 완료는 다릅니다. 전략 스튜디오에서 선택 파일 목록·포함/누락/중복·추출 상태를 먼저 확인하고 원문 분석을 실행하세요. "
        "빈 파일·미지원 형식·용량 제한·추출 실패·AI 전사 한도는 서로 다른 원인입니다. 파일 이름만으로 내용을 읽었다고 판단하지 않습니다. "
        "Drive 공유 주소도 권한·공개 범위·다운로드 제한에 따라 달라지며 주소만으로 모든 폴더 내용의 수집을 보장하지 않습니다. 앱 회원 로그인과 Google 자료 접근 권한은 별개입니다. "
        "원문에 없는 조건은 보완 질문으로 확인하고 재분석합니다. 계속 실패하면 파일 형식·크기·실패 단계와 비민감 재현용 파일을 전달하세요.",
        "Selecting a file is not completed analysis. Check included/missing/duplicate files and extraction status, then analyse. Empty files, unsupported formats, size limits, extraction failure and transcription budgets differ. A Drive URL does not guarantee access or complete folder ingestion; sharing permissions and download restrictions still apply. App login and Google resource authorization are separate. Send format, size, failed stage and a non-sensitive reproduction sample."),
    SupportTopic("replay_cost", ("수수료", "과거재생차트", "재생차트", "슬리피지"),
        "docs/USER_GUIDE.md",
        "과거재생 비용은 기관·현물/선물·매수/매도·계정 등급·maker/taker와 세금 등 조건에 따라 달라집니다. 하나의 0.25%를 모든 기관에 적용하거나 최신 실계정 요율로 단정하면 안 됩니다. "
        "재생 설정과 결과의 수수료·슬리피지·비용 출처 및 미포함 항목을 확인하세요. 할인·펀딩·실제 시장 충격까지 완전 재현한 실현손익이 아닙니다. "
        "과거재생 차트는 확보된 과거 봉과 모의 진입·청산 근거를 표시하며 실체결 차트가 아닙니다. BUY/SELL은 주문 방향이므로 숏 진입 SELL을 청산으로 오해하지 마세요. "
        "요약만 있는 구기록에 차트 근거가 없으면 재생 자료를 새로 확보해야 하며 그래프를 만들어 채우지 않습니다.",
        "Replay costs vary by venue, spot/futures, side, account tier, maker/taker and taxes. Do not treat a universal 0.25% as an actual current account rate. Inspect modeled fees/slippage, source and exclusions. Replay is not fully realized PnL including funding/market impact. Its charts show historical candles and simulated entries/exits, not exchange fills. BUY/SELL denotes order side; a SELL can open a short. Summary-only legacy records cannot supply missing chart evidence."),
    SupportTopic("dashboard", ("운용요약", "거래대시보드", "거래현황", "시장국면확률", "그래프없", "미평가", "대조전"),
        "docs/V39150_VISUAL_OVERVIEW_PLAN.md",
        "거래 현황은 실제 엔진의 시장 관찰·판단·전략·거래 근거를 요약하고 기관 상세·로그로 연결합니다. "
        "실거래 내역/LIVE와 가상 거래 내역/PAPER 버튼은 조회 범위이며 주문 모드 전환이 아닙니다. "
        "기관·모드·전략 버전·관찰 시각이 다른 근거를 합쳐 확률이나 성과를 만들지 않습니다. "
        "그래프 근거가 없으면 데이터 없음·확인 필요를 표시하며, 미평가·대조 전을 0원 또는 정상으로 바꾸지 않습니다. "
        "신호·요청 접수·체결·보호주문 확인은 각각 별개입니다. 요약 화면만으로 계좌 안전이나 원인 해소를 보장하지 않습니다.",
        "The overview displays actual engine observations, decisions, strategies and recorded results, with links to venue details/logs. LIVE/PAPER history buttons change the view, not order mode. Do not combine different venues, modes, versions or observation times into probabilities or returns. Missing graph evidence is unknown, not zero or healthy. Signals, command acceptance, fills and protective-order confirmation are distinct."),
    SupportTopic("remote_portal", ("noahai.net", "daltrading", "원격관리", "모바일원격", "pc상태공유"),
        "docs/UPDATE_PLAN.md",
        "사용자 포털·로그인·원격 관리는 noahai.net, 개발사 공식 사이트는 noahailabs.com, 판매 안내는 info.noahai.net, 기업 제휴는 ip.noahai.net입니다. "
        "새 도메인에서는 재로그인이 필요할 수 있습니다. 구주소 API 호환 유지와 브라우저 주소 변경 안내는 별도이며 모든 구주소 요청을 강제 이동하지 않습니다.\n"
        "PC 설정 → 알림·리포트 → 원격 관리에서 상태 공유와 허용할 명령을 직접 확인·저장하세요. "
        "모바일 요청 접수는 PC 실행 완료가 아닙니다. 최종 수신 시각과 PC 응답을 확인하세요. 꺼짐·절전·오프라인 PC는 실행하지 못합니다. "
        "신규 진입 일시정지와 기존 포지션 청산은 다릅니다. 이 대화는 원격 명령·주문·설정을 실행하지 않습니다.",
        "Use noahai.net for the user portal/login/remote management, noahailabs.com for the company, info.noahai.net for sales information and ip.noahai.net for partnerships. A new domain may require login. Configure status sharing and permitted commands on the PC under Alerts/Reports → Remote management. Web acceptance is not PC execution: check freshness and acknowledgement. Offline/sleeping PCs cannot execute. Entry pause is not liquidation. This guide performs no commands."),
    SupportTopic("jev", ("jev", "제브", "typesafe"),
        "docs/V3921_JEV_EVALUATION.md",
        "JEV는 텍스트 상태에 대해 미리 정의한 선택·점수·예/아니오 확률을 반환하는 의사결정 모델입니다. 자유로운 설명을 생성하는 어시스턴트 대체 모델이 아닙니다. "
        "현재 NoahAI 실행 Provider로 통합되지 않았으며 검토 문서와 오프라인 자료 대조 단계입니다. "
        "형식이 제한돼도 의미 판단·수익 예측의 오류가 없어지는 것은 아닙니다. confidence, 선택 확률, 별도 noul 응답을 혼동하지 않습니다. "
        "첨부 10건만으로 실거래 성과·긴급 청산·100% 정확도를 입증할 수 없습니다. 연구한다면 기본 OFF·동의 후 비식별 입력·판단 기록만 하는 shadow 평가부터 진행합니다. "
        "손절·보호주문·승인·실행식·비용 한도는 JEV가 대체하거나 해제하지 않습니다.",
        "JEV returns typed choices, scores and yes/no probabilities from text; it is not a free-text assistant replacement. NoahAI has not integrated it as an execution provider. Current work is evidence review and offline audit. Structured output does not eliminate semantic errors or establish trading returns. Confidence, option probability and a separate noul answer differ. Ten supplied records cannot prove accuracy, live returns or emergency execution. A future opt-in shadow evaluation must not control orders or bypass protections/budgets."),
    SupportTopic("release", ("업데이트내용", "업데이트된", "새기능", "최신기능", "이번버전", "버전변경", "3.9.2.1"),
        "docs/UPDATE_PLAN.md",
        "최근 변경 안내: 48은 업로드·비용/종목 자격 점검, 49는 전략 평가 용량·지표·운용 근거, 50은 시각 요약·시작 진단, "
        "3.9.2.0은 포털 주소 통합·OKX 후보 진단·키움 종료·전략 다중 선택·모델 목록 보강입니다. "
        "3.9.2.1의 범위는 어시스턴트 안내 정합성과 JEV 근거 검토입니다. JEV 거래 엔진 도입 완료가 아닙니다. "
        "설정 → 업데이트에서 설치 버전을, 화면 하단에서 UI 빌드를 확인하세요. 소스 구현·로컬 시험·Windows 설치·공개 배포·고객 장애 재시험은 별개입니다. "
        "설치본 확인 없이 모든 피드백이 해결됐다고 안내하지 않습니다.",
        "Recent changes cover upload/cost/instrument checks (48), strategy capacity/fields/evidence (49), visual summaries/start diagnostics (50), and portal migration, OKX/Kiwoom fixes, bulk strategy actions and model catalogs (3.9.2.0). 3.9.2.1 covers support-guide consistency and JEV evidence review, not JEV trading integration. Check the installed version and UI build. Source changes, local tests, Windows installation, publication and customer retests are separate evidence."),
)


def support_topic(question: str) -> SupportTopic | None:
    # Embedded strategy/market snapshots must follow their evidence explanation
    # route, not match a field name or an error number inside untrusted data.
    if "NOAH_STRATEGY_EXPLANATION_V1\n" in str(question) or "[MARKET_TREND_SNAPSHOT]" in str(question):
        return None
    normalized = re.sub(r"\s+", "", str(question or "").casefold())
    def matches(token: str) -> bool:
        if token == "level":
            return bool(re.search(r"(?<![a-z_])level(?:[1-5]|[^a-z_]|$)", normalized))
        if token in {"409", "429"}:
            return bool(re.search(r"(?<![a-z0-9])" + token + r"(?![a-z0-9])", normalized))
        return re.sub(r"\s+", "", token.casefold()) in normalized
    return next((topic for topic in TOPICS if any(
        matches(token) for token in topic.triggers
    )), None)


def build_support_answer(question: str, *, locale: str = "ko") -> str | None:
    topic = support_topic(question)
    if topic is None:
        return None
    from config.app_version import RELEASE_VERSION
    if locale == "en":
        return (f"NoahAI support · source v{RELEASE_VERSION} · guide {GUIDE_REVISION}\n\n{topic.en}\n\n"
                "If unresolved, send the installed version/UI build, venue, PAPER/LIVE mode, UTC time, support code, failed stage, request ID and redacted reproduction steps to Q&A/admin. Never send API keys, account numbers or unredacted logs. This is a guide, not a live diagnosis or an executed fix.")
    return (f"NoahAI 안내 · 소스 v{RELEASE_VERSION} · 안내 기준 {GUIDE_REVISION}\n\n{topic.ko}\n\n"
            "해결되지 않으면 Q&A/관리자에게 설치 버전·UI 빌드, 기관, PAPER/LIVE 모드, UTC 시각, 지원 코드, 실패 단계, 요청 ID, 비식별 재현 순서를 전달하세요. "
            "API 키·계좌번호·원본 로그 전체를 보내지 마세요. 이 답변은 사용법 안내이며 실제 상태 진단이나 복구 실행 완료가 아닙니다.")
