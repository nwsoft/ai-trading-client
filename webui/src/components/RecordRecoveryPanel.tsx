import { useEffect, useRef, useState } from 'react';
import type { GatewayClient } from '../api';
import { localized } from '../i18n';
import { CRYPTO_SOURCES, STOCK_SOURCES } from '../venueSources';
import { accountConnectionView } from '../accountConnection';
import { RecoveryStatementImport } from './RecoveryStatementImport';

const labels: Record<string, [string, string]> = {
  open_position_history_unsupported: ['미청산 원장의 청산 근거 자동 수집 미지원', 'Missing close discovery not supported'],
  execution_time_outside_position: ['진입·체결 시각 대조 필요', 'Entry and execution time review required'],
  execution_order_ambiguous: ['동일 시각 여러 주문의 체결 순서 근거 필요', 'Execution ordering at identical timestamps is ambiguous'],
  entry_time_evidence_mismatch: ['원장과 내역의 진입 시각 불일치', 'Entry time differs from the local ledger'],
  entry_price_evidence_mismatch: ['원장과 내역의 진입 가격 불일치', 'Entry price differs from the local ledger'],
  exit_lot_allocation_required: ['여러 청산 가격의 진입별 배분 근거 필요', 'Evidence needed to allocate multiple exit prices to entries'],
  cycle_gross_reconciliation_required: ['전체 포지션 손익과 체결 가격 계산 불일치', 'Position PnL and fill-price calculation disagree'],
  execution_mode_evidence_missing: ['과거 기록의 LIVE/PAPER 근거 미기록 · 원본 실행 로그 확인 필요', 'Historical execution mode missing · original session evidence needed'],
  idle: ['점검 전', 'Not checked'], running: ['거래 기록 점검·복구 중', 'Checking trade records'],
  paused: ['조회량 제한 · 이어서 점검 가능', 'Request budget reached · continue available'],
  retry_wait: ['일시적 조회·정산 지연 · 자동 재시도 대기', 'Temporary query / settlement delay · automatic retry pending'],
  interrupted: ['이전 점검 중단 · 이어서 점검 가능', 'Interrupted · continue available'],
  failed: ['조회 실패 · 잠시 후 다시 시도', 'Check failed · retry shortly'],
  checked: ['대상 기록 점검 완료 · 운용 조건은 별도 확인', 'Records checked · trading conditions still apply'],
  needs_evidence: ['추가 근거 필요 · 미확정 기록 보존', 'More evidence needed · records preserved'],
  missing_exit_order_evidence: ['청산 주문과 NoahAI 거래의 연결 근거 없음', 'Missing exit-order ownership evidence'],
  provider_history_collecting: ['거래소 과거 주문·체결·손익 원장 수집 중', 'Collecting exchange order, fill and income history'],
  position_cycle_ambiguous: ['다른 진입·보유분과 섞여 전략별 귀속을 확정하지 못함', 'Other entries or holdings prevent unique strategy attribution'],
  position_cycle_incomplete: ['완전한 진입·청산 구간을 확인하지 못함', 'Complete entry-to-close cycle not established'],
  position_anchor_changed: ['조회 중 포지션이 변경됨 · 신규 진입 일시정지 후 다시 점검', 'Position changed during collection · pause new entries and retry'],
  position_anchor_unavailable: ['거래소 포지션 기준값 확인 필요', 'Exchange position anchor unavailable'],
  entry_order_not_in_history: ['조회한 원장에서 진입 주문을 찾지 못함', 'Entry order absent from downloaded history'],
  order_history_incomplete: ['체결 주문의 완료 상태·수량 확인 필요', 'Complete order status and quantity required'],
  history_identity_mismatch: ['기관 원장의 식별 정보가 서로 일치하지 않음', 'Provider history identities do not agree'],
  history_storage_limit: ['자동 조회 근거의 보존 용량 한도 도달 · 공식 내역 파일 가져오기를 이용하세요', 'History evidence storage limit reached; import an official statement'],
  income_reconciliation_required: ['체결 실현손익과 거래소 정산 내역 대조 필요', 'Fill realized PnL does not yet reconcile with income history'],
  execution_storage_incomplete: ['체결 원장 저장 검증 실패 · 재점검 필요', 'Execution storage verification failed · retry required'],
  history_retention_exceeded: ['API 과거 조회 보존기간 초과 · 공식 내역 필요', 'API retention exceeded · official statements required'],
  credential_scope_changed: ['점검 중 API 계정이 변경됨 · 다시 연결 후 점검', 'API account changed · reconnect and restart the check'],
  order_attribution_conflict: ['같은 체결의 다른 거래 귀속을 확인해야 함', 'A fill is already attributed to another trade'],
  entry_fee_evidence_missing: ['진입 수수료 근거 부족', 'Entry-fee evidence missing'],
  provider_connection_required: ['기관 API 연결 확인 필요', 'Check provider connection'],
  broker_historical_evidence_unsupported: ['증권사 과거 주문·비용 복구 연동 미지원', 'Broker historical order/cost recovery not supported'],
  provider_historical_evidence_unsupported: ['기관의 과거 체결 조회 경로 미지원', 'Historical execution query not supported'],
  exchange_fill_not_found: ['조회 범위에서 해당 주문 체결을 확인하지 못함', 'Order fills not found in the query window'],
  history_page_incomplete: ['조회 상한 도달 · 전체 체결 근거 필요', 'Query limit reached · complete fills required'],
  partial_or_quantity_mismatch: ['부분체결 또는 수량 불일치', 'Partial fill or quantity mismatch'],
  provider_pnl_or_cost_evidence_incomplete: ['기관 손익 또는 수수료 근거 부족', 'Provider PnL or cost evidence incomplete'],
  provider_realized_pnl_unavailable: ['기관 실현손익 근거 없음', 'Provider realized PnL unavailable'],
  fee_or_fill_data_incomplete: ['체결·수수료 값 누락 또는 유효하지 않음', 'Missing or invalid fill/fee data'],
  owned_protection_pending: ['보호 주문 체결 확인 대기', 'Protective-order evidence pending'],
  provider_query_failed: ['기관 조회 실패', 'Provider query failed'],
  contract_unit_verification_required: ['선물 계약 수량·단위의 대조 근거 필요', 'Futures contract-unit evidence required'],
  local_trade_data_invalid: ['로컬 거래 수량·진입가격 근거 확인 필요', 'Local trade quantity / entry-price evidence invalid'],
  record_identity_changed: ['점검 중 거래 식별 정보가 변경되어 복구하지 않음', 'Record identity changed during the check; not modified'],
  record_missing: ['점검 대상 기록이 없어 복구하지 않음', 'Target record no longer exists; not modified'],
  entry_order_allocation_required: ['여러 거래가 같은 진입 주문을 사용하여 비용 배분 근거 필요', 'Shared entry order requires proven cost allocation'],
  entry_fee_conversion_required: ['진입 수수료 통화 환산 근거 필요', 'Entry-fee currency conversion evidence required'],
  recovery_cooldown: ['직전 점검 후 30초가 지나면 다시 실행할 수 있습니다.', 'Wait 30 seconds after the last check before retrying.'],
  recovery_already_running: ['현재 계정에서 다른 점검이 진행 중입니다.', 'A check is already running for this account.'],
  recovery_engine_not_ready: ['대시보드의 실시간 새로고침으로 API 계좌 연결을 확인한 뒤 다시 점검하세요. LIVE 거래를 시작할 필요는 없습니다.', 'Refresh the account connection from the dashboard, then retry. You do not need to start LIVE trading.'],
  recovery_credential_required: ['설정 → 거래소 API에서 해당 기관 연결 정보를 확인하세요.', 'Check the venue credentials in Settings → Venue APIs.'],
  recovery_login_required: ['먼저 NoahAI에 로그인하세요.', 'Sign in to NoahAI first.'],
  recovery_ledger_unavailable: ['거래 기록 저장소 연결을 확인하지 못했습니다.', 'The trade ledger is unavailable.'],
  recovery_runtime_unavailable: ['이 실행 환경에서는 거래 기록 점검이 연결되지 않았습니다.', 'Trade record recovery is not connected in this runtime.'],
};
const label = (key: string) => labels[key] ? localized(...labels[key]) : key;

export function RecordRecoveryPanel({ client, initialSource = 'binance', sources = [...CRYPTO_SOURCES, ...STOCK_SOURCES] }: {
  client: GatewayClient; initialSource?: string; sources?: string[];
}) {
  const [source, setSource] = useState(sources.includes(initialSource) ? initialSource : sources[0] || 'binance');
  const [status, setStatus] = useState<Record<string, any> | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [connectionMessage, setConnectionMessage] = useState('');
  const sequence = useRef(0);
  const autoContinue = useRef(false);
  const commandRevision = useRef(0);
  useEffect(() => {
    const id = ++sequence.current;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    setStatus(null); setError(''); setBusy(false); setConnectionMessage('');
    autoContinue.current = false;
    const poll = async () => {
      const revision = commandRevision.current;
      try {
        let next = await client.recordRecovery(source);
        if (alive && id === sequence.current && revision === commandRevision.current && autoContinue.current && next.state === 'paused' && !next.background_continuation) {
          next = await client.recordRecovery(source, true);
        }
        if (alive && id === sequence.current && revision === commandRevision.current) {
          if (['failed', 'needs_evidence', 'checked'].includes(next.state)) autoContinue.current = false;
          setStatus(next); setError('');
        }
      } catch { if (alive) setError(localized('점검 상태를 불러오지 못했습니다.', 'Could not load recovery status.')); }
      if (alive) timer = setTimeout(poll, 3000);
    };
    void poll();
    return () => { alive = false; autoContinue.current = false; ++sequence.current; clearTimeout(timer); };
  }, [client, source]);
  async function start() {
    const id = sequence.current;
    ++commandRevision.current;
    autoContinue.current = true;
    setBusy(true); setError('');
    try {
      const next = await client.recordRecovery(source, true);
      if (id === sequence.current) setStatus(next);
    } catch (e) { autoContinue.current = false; if (id === sequence.current) setError(label(e instanceof Error ? e.message : String(e))); }
    finally { if (id === sequence.current) setBusy(false); }
  }
  async function checkConnection() {
    const id = sequence.current;
    setBusy(true); setError(''); setConnectionMessage('');
    try {
      const result = await client.refreshAccounts([source], true);
      if (id !== sequence.current) return;
      const connection = accountConnectionView(result.sources?.[source] ?? result[source], source);
      setConnectionMessage(connection.connected
        ? localized('기관 연결을 확인했습니다. 아래 점검·복구를 실행하세요. 거래는 시작하지 않았습니다.', 'Connection checked. Run recovery below. Trading was not started.')
        : `${connection.reason} ${localized('거래는 시작하지 않았습니다.', 'Trading was not started.')}`);
    } catch (e) { if (id === sequence.current) setError(e instanceof Error ? e.message : String(e)); }
    finally { if (id === sequence.current) setBusy(false); }
  }
  return <section className="settings-parity-panel record-recovery" aria-label={localized('거래 기록 점검·복구', 'Trade record recovery')}>
    <h3>{localized('유지관리 · 거래 기록 점검·복구', 'Maintenance · Trade record recovery')}</h3>
    {client.recoveryStatement && <RecoveryStatementImport key={source} client={client} source={source}/>}
    <p>{localized('새 점검은 보관된 전체 기간의 LIVE 미확정 기록을 300건 제한 없이 확인합니다. 진행 중인 작업은 기존 범위에서 이어집니다. 거래소의 과거 조회 제한으로 근거를 확보하지 못한 기록은 미확정으로 보존합니다. PAPER 기록·손실 한도는 변경하지 않습니다.', 'A new check covers unresolved LIVE records across the entire stored history, beyond the 300-record policy sample. Existing jobs continue within their original range. Records outside exchange history availability remain unresolved. PAPER records and loss limits are unchanged.')}</p>
    <p>{localized('한 번 실행하면 앱이 켜져 있는 동안 이 화면을 닫아도 조회량을 조절하며 이어갑니다. 일시적 오류·정산 지연은 최대 2회 자동 재시도합니다. 앱 종료 시 진행을 보존하고 다음 실행에서 이어갈 수 있습니다.', 'Start once: while the app is open, recovery continues with bounded queries even if you close this panel. Temporary errors or settlement delays retry at most twice. App exit preserves progress for your next check.')}</p>
    {source === 'binance' && <p>{localized('청산 번호 누락·여러 주문으로 나눈 청산·기록 수량 불일치는 전체 체결 구간으로 재검증합니다. 진입 주문 소유권, 완전한 진입·청산 수량과 정산 근거가 확인될 때만 수정합니다.', 'Missing close IDs, multiple closing orders and quantity mismatches are checked against the full fill cycle. Repairs require proven entry ownership, complete entry/exit quantities and settlement evidence.')}</p>}
    <label>{localized('거래소·증권사', 'Exchange / broker')} <select value={source} disabled={busy || ['running','retry_wait'].includes(status?.state)} onChange={e => setSource(e.target.value)}>
      {sources.map(s => <option key={s} value={s}>{s.toUpperCase()}</option>)}
    </select></label>
    <button type="button" disabled={busy || ['running','retry_wait'].includes(status?.state)} onClick={() => void checkConnection()}>
      {localized('기관 연결 확인 · 거래 시작 안 함', 'Check connection · do not start trading')}
    </button>
    {connectionMessage && <p role="status">{connectionMessage}</p>}
    <button type="button" disabled={busy || ['running','retry_wait'].includes(status?.state)} onClick={() => void start()}>
      {localized('거래 기록 점검·복구 실행 / 이어서 실행', 'Check / continue trade record recovery')}
    </button>
    <div role="status" aria-live="polite">
      <strong>{label(status?.state || 'idle')}</strong>
      {Number(status?.retry_count) > 0 && <p>{localized('자동 재시도', 'Automatic retry')}: {status?.retry_count}/2</p>}
      {status?.state !== 'idle' && status && <p>{localized('처리', 'Processed')} {status.processed} / {status.total} · {localized('확인 완료', 'Verified')} {status.recovered} · {localized('미확정·대기', 'Unresolved / pending')} {status.remaining}</p>}
      {status?.backup_created && <small>{localized('최초 점검 전 DB 백업·작업별 변경 기록 보존', 'Initial database backup and per-run change evidence preserved')}</small>}
      {Number(status?.verified_open) > 0 && <p>{localized('실제 보유 확인 · 미청산 유지', 'Confirmed open · not closed')}: {status?.verified_open}</p>}
      {status?.history_pages && Object.keys(status.history_pages).length > 0 && <p>{localized('거래소 원장 조회 구간', 'Exchange history windows')}: {localized('완료', 'Complete')} {status.history_pages.complete || 0} · {localized('대기', 'Pending')} {status.history_pages.pending || 0}</p>}
    </div>
    {error && <p role="alert">{error}</p>}
    {Object.keys(status?.reasons || {}).length > 0 && <ul>{Object.entries(status?.reasons || {}).map(([reason, count]) => <li key={reason}>{label(reason)}: {String(count)}</li>)}</ul>}
    {status?.next_actions && <section aria-label={localized('미확정 사유별 필요한 자료와 다음 조치', 'Required evidence and next steps')}>
      {Object.entries(status.next_actions).map(([reason, value]) => { const action = value as any; return <div key={reason}>
        <strong>{label(reason)}</strong><p>{localized(action.action_ko, action.action_en)}</p>
        {action.retry_without_new_evidence === false && <small>{localized('새 근거 없이 반복 실행하지 마세요.', 'Do not repeat without new evidence.')}</small>}
      </div>; })}
    </section>}
    {status && status.unresolved_items?.length > 0 && <details open><summary>{localized('미확정 거래별 사유 · 최근 최대 100건', 'Unresolved records · latest 100')}</summary><ul>{status.unresolved_items.map((item: any) => <li key={item.trade_id}>#{item.trade_id} · {item.symbol} · {item.exit_time} · {label(item.reason || item.state)}</li>)}</ul></details>}
    <p>{localized('기관 API 조회 또는 검토해 가져온 파일을 사용하며 주문 제출·취소·청산·거래 시작은 하지 않습니다. 파일 출처와 API 출처는 구분해 보존합니다. 근거 없는 기록은 삭제하거나 수익으로 확정하지 않습니다. 점검 완료가 거래 재개 승인은 아닙니다.', 'Uses read-only provider queries or reviewed statement files; no orders, cancellations, position closing or trading start. File and API provenance remain distinct. Completing a check does not authorize trading.')}</p>
    <p>{localized('이미 실행 중인 엔진은 복구된 기록을 다음 판단에 사용하므로 기존 진입 보류가 해제될 수 있습니다. 결과를 확인하기 전 새 거래를 원하지 않으면 먼저 기존 새 거래 일시정지를 사용하세요.', 'An already-running engine uses repaired records in its next evaluation, so an existing entry block may clear. Pause new entries first if you want to review the result before further trading.')}</p>
    {status?.state === 'needs_evidence' && <p>{localized('추가 근거가 없으면 반복 실행해도 결과가 같을 수 있습니다. 정산 반영 후 재점검하거나 공식 체결 내역 CSV를 가져오세요. 파일도 완전한 진입·청산 구간과 주문·수량·비용을 확인해야 적용합니다. 혼합 보유·부족한 열은 미확정으로 보존하며 기록 초기화나 미확정 무시로 우회하지 않습니다.', 'Retry after settlement or import the official executions CSV. Files must prove complete entry/exit cycles, orders, quantities and costs. Mixed ownership and missing fields remain unresolved; resets and ignoring uncertainty are not recovery.')}</p>}
  </section>;
}
