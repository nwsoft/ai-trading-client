/** Shareable start diagnostics contain only protocol enums, never raw errors. */
export type StartDiagnostic = { code: string; requestId: string; stage: string; status: number | null };
const codes = new Set([
  'runtime_source_not_enabled', 'stock_source_not_enabled', 'exchange_initialization_failed',
  'runtime_source_stopping', 'runtime_start_cancelled',
  'trading_candidates_unavailable', 'runtime_start_exception', 'runtime_command_rejected',
  'trading_candidate_catalogue_unavailable', 'trading_candidate_markets_unavailable',
  'trading_candidate_tickers_unavailable', 'trading_candidate_filters_excluded',
  'credential_required', 'risk_data_unavailable', 'daily_loss_limit_exceeded',
  'managed_position_reconciliation_required', 'live_start_confirmation_required',
  'binance_runtime_not_ready', 'binance_worker_shutdown_timeout', 'runtime_shutdown_in_progress',
  'runtime_shutdown_incomplete', 'runtime_account_change_requires_restart',
  'stock_runtime_controller_not_attached', 'headless_runtime_start_unavailable',
  'stock_adapter_unavailable', 'stock_connection_failed', 'venue_live_onboarding_required',
  'venue_paper_onboarding_required', 'membership_exchange_approval_required',
  'membership_exchange_not_approved', 'membership_exchange_approval_pending',
  'membership_exchange_approval_rejected', 'membership_exchange_approval_expired',
  'membership_exchange_activation_pending', 'membership_crypto_plan_required',
  'membership_stock_plan_required', 'membership_session_inactive', 'membership_source_unsupported',
  'gateway_authentication_required', 'runtime_request_timeout', 'runtime_transport_unavailable',
]);
const stages = new Set(['scope', 'initialization', 'market_observation', 'candidate_selection', 'worker_start']);
export const startStageLabel = (stage: string) => ({scope:'실행 대상 확인',initialization:'기관 연결 초기화',market_observation:'시장 시세·국면 관찰',candidate_selection:'거래 후보 선정',worker_start:'거래 워커 시작',unknown:'단계 미기록'}[stage] || '단계 미기록');
export function startDiagnostic(detail: unknown, requestId?: unknown, status?: number): StartDiagnostic {
  const item = detail && typeof detail === 'object' ? detail as Record<string, unknown> : null;
  const parts = typeof detail === 'string' ? detail.split(':') : [];
  let code = item?.code ?? parts[0];
  if (code === 'risk_data_unavailable' && parts[1] === 'managed_position_reconciliation_required') code = parts[1];
  const stage = item?.stage ?? parts[2];
  return { code: typeof code === 'string' && codes.has(code) ? code : 'start_reason_not_recorded',
    requestId: typeof requestId === 'string' && /^[A-Za-z0-9_-]{16,80}$/.test(requestId) ? requestId : '미기록',
    stage: typeof stage === 'string' && stages.has(stage) ? stage : 'unknown',
    status: Number.isInteger(status) && Number(status) >= 400 && Number(status) <= 599 ? Number(status) : null };
}
export class GatewayRequestError extends Error {
  constructor(message: string, public diagnostic: StartDiagnostic) { super(message); this.name = 'GatewayRequestError'; }
}
export function startGuidance(code: string, mode: string) {
  const recovery = mode === 'live' && ['managed_position_reconciliation_required', 'risk_data_unavailable'].includes(code);
  const action = recovery ? '거래 기록 점검·복구에서 미확정 사유와 필요한 체결 근거를 확인하세요. 복구 결과를 확인한 뒤 시작을 다시 평가하세요.'
    : code === 'runtime_source_stopping' ? '이전 거래 워커가 아직 종료 중입니다. 종료 상태를 확인한 뒤 다시 시작하세요. 강제 종료하거나 시작을 반복하지 마세요.'
    : code === 'runtime_start_cancelled' ? '시작 준비 중 정지 요청이 들어와 시작을 취소했습니다. 자동 재시작하지 않습니다. 현재 상태를 확인한 뒤 필요할 때 직접 시작하세요.'
    : code === 'trading_candidate_catalogue_unavailable' ? '현재 종목 목록을 조회하지 못했습니다. 해당 기관의 연결·공개 시세 접근과 초기화 로그를 확인하세요. 과거 목록으로 거래를 시작하지 않습니다.'
    : code === 'trading_candidate_markets_unavailable' ? '현재 목록에서 거래 가능한 지원 상품이 확인되지 않았습니다. 종목 상태·상품 종류·결제통화와 제외 설정을 확인하세요. 상장 상태 검사를 우회하지 마세요.'
    : code === 'trading_candidate_tickers_unavailable' ? '지원 상품은 있지만 유효한 현재 시세를 받지 못했습니다. 해당 기관의 시세 수신과 조회 오류를 확인한 뒤 다시 시작하세요. 가격을 0으로 간주하지 않습니다.'
    : code === 'trading_candidate_filters_excluded' ? '받은 시세가 거래대금·변동성 필터를 통과하지 못했습니다. 코인 정보와 거래소별 선정 설정, 로그의 유효 시세·필터 통과 수를 확인하세요. 기준을 자동 완화하지 않습니다.'
    : code === 'trading_candidates_unavailable' ? '해당 기관의 코인·종목 정보에서 선정 결과와 시세 수신 상태를 확인하세요. 후보가 확보된 뒤 다시 시작하세요.'
    : code === 'exchange_initialization_failed' ? '설정에서 해당 기관의 연결을 점검하고 같은 시각의 초기화 로그를 확인하세요. API 키 오류로 단정할 수 없습니다.'
    : code === 'credential_required' ? '설정에서 해당 기관의 필수 인증 정보를 저장하고 연결을 확인하세요.'
    : code.startsWith('membership_') ? '회원·기관 이용 권한을 확인하세요. 승인 또는 활성화가 필요하면 관리자에게 이 진단을 전달하세요.'
    : ['runtime_source_not_enabled', 'stock_source_not_enabled'].includes(code) ? '설정 → 거래소 선택에서 분석·학습 대상과 실제 주문 대상을 구분해 확인하세요.'
    : code === 'daily_loss_limit_exceeded' ? '당일 손익과 설정된 손실 한도를 확인하세요. 손익 초기화로 한도를 우회하지 마세요.'
    : ['runtime_request_timeout', 'runtime_transport_unavailable'].includes(code) ? '응답을 받지 못해 시작 여부가 미확정입니다. 기관 실행 상태를 새로 확인한 뒤 조치하세요. 중복 시작하지 마세요.'
    : '기관 실행 상태와 발생 시각의 최초 오류를 확인하세요. 이 진단의 요청 ID를 Q&A·관리자에게 전달해 원인을 확인하세요. 반복 시작이나 기록 초기화는 해결책이 아닙니다.';
  return { recovery, action };
}
