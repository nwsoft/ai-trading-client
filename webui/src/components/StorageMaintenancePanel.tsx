import { useEffect, useRef, useState } from 'react';
import type { GatewayClient } from '../api';
import { localized } from '../i18n';

export function StorageMaintenancePanel({ client }: { client: GatewayClient }) {
  const [state, setState] = useState<Record<string, any> | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const request = useRef(0);
  useEffect(() => {
    let alive = true; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      const id = ++request.current;
      try { const result = await client.storageMaintenance(); if (alive && id === request.current) { setState(result); setError(''); } }
      catch { if (alive && id === request.current) setError(localized('저장소 상태 조회 실패', 'Storage status unavailable')); }
      if (alive) timer = setTimeout(poll, 5000);
    };
    void poll(); return () => { alive = false; clearTimeout(timer); };
  }, [client]);
  const act = async (action: 'optimize' | 'debug', hours?: number) => {
    const id = ++request.current;
    setBusy(true); setError('');
    try { const result = await client.storageMaintenance(action, hours); if (id === request.current) setState(result); }
    catch { setError(localized('작업을 시작하지 못했습니다. 다시 확인하세요.', 'Could not start. Please retry.')); }
    finally { setBusy(false); }
  };
  const mb = (value: number) => `${((value || 0) / 1048576).toFixed(1)} MiB`;
  const date = (value: string | number) => new Date(value).toLocaleString(localized('ko-KR', 'en-US'));
  const running = busy || state?.state === 'running';
  const labels: Record<string,string> = {
    idle: localized('점검 전','Not checked'), running: localized('최적화 중','Optimizing'),
    paused: localized('다음 구간 이어서 실행 가능','Ready to continue'),
    complete: localized('최적화 완료','Optimization complete'), failed: localized('최적화 실패 · 원본 보존','Failed · original records retained'),
  };
  return <section className="settings-parity-panel record-recovery" aria-label={localized('저장소 유지관리','Storage maintenance')}>
    <h3>{localized('유지관리 · 저장소','Maintenance · Storage')}</h3>
    <p>{localized('오래 사용해도 기록 조회가 느려지지 않도록 저장 방식을 정리합니다. 평소에는 누를 필요가 없습니다. 아래에 미완료·용량 경고가 있을 때 최적화를 실행하세요.',
      'Keep record lookups efficient over time. No routine action is needed. Optimize when an incomplete-work or storage warning appears below.')}</p>
    <p>{localized('닫힌 로그는 검증된 압축 파일로 옮기고 학습 근거는 중복 저장을 줄입니다. 거래·PAPER 원장과 기존 학습 원본은 보존하며, 매매 판단이나 학습 규칙은 바꾸지 않습니다.',
      'Closed logs move to verified archives and repeated learning evidence is stored once. Trade/PAPER ledgers and legacy learning originals are preserved. Trading and learning rules do not change.')}</p>
    <p>{localized('최초 이관에는 여유 공간이 필요합니다. 이전 JSON 아카이브는 그대로 보존하며, 이 작업은 손익 복구나 거래 시작이 아닙니다.',
      'Initial migration needs free disk space. Older JSON archives remain unchanged. This does not repair PnL or start trading.')}</p>
    {state && <div role="status">
      <span>{localized('로그 용량','Logs')}: {mb(state.log_bytes)} / {mb(state.log_budget_bytes)}</span>
      <span>{localized('보관 로그 · 별도 용량','Archived logs · separate storage')}: {mb(state.log_archive_bytes)} · {localized('마지막 로그 압축','Last log compression')}: {state.last_log_compression ? date(state.last_log_compression * 1000) : '—'}</span>
      <span>{localized('학습 저장소','Learning storage')}: {mb(state.learning_bytes)} · DB: {mb(state.db_bytes)}</span>
      <span>{localized('마지막 압축','Last compression')}: {state.last_compression ? date(state.last_compression) : '—'}</span>
      <span>{localized('상세 로그 만료','Detailed logging expires')}: {state.debug_expires_at * 1000 > Date.now() ? date(state.debug_expires_at * 1000) : localized('꺼짐','Off')}</span>
      <span>{labels[state.state] || state.state} · {localized('판단 점검','Decisions checked')}: {state.decision_rows_checked} · {localized('압축 기록','Archived records')}: {state.archived_rows}</span>
      {state.log_budget_exceeded && <p>{localized('진단 로그 예산 초과: 닫힌 로그를 자동 압축하며 공간 확보 후 기록을 재개합니다. 계속 표시되면 최적화를 실행하고 디스크 여유 공간을 확인하세요. 중요 이벤트는 별도 원장에 보존합니다.', 'Diagnostic budget exceeded: closed logs are compressed automatically; writing resumes after space is recovered. If this persists, optimize and check free disk space. Important events are retained separately.')}</p>}
      {state.log_archive_error && <p role="alert">{localized('로그 압축 미완료: 원본은 보존됩니다. 디스크 여유 공간·파일 잠금을 확인한 뒤 최적화를 다시 실행하세요.', 'Log compression incomplete: originals are retained. Check free disk space and file locks, then retry optimization.')}</p>}
      {state.contract_rejected_records > 0 && <p role="alert">{localized('기록 근거 충돌', 'Conflicting record evidence')}: {state.contract_rejected_records} · {localized('원본 별도 보존·학습 제외. 최적화로 기관이나 모드를 추측하여 고치지 않습니다. 반복 발생하면 지원팀에 이 상태와 로그를 전달하세요.', 'Originals retained separately and excluded from learning. Optimization does not guess venue or mode. If repeated, share this status and logs with support.')}</p>}
      {state.audit_error && <p role="alert">{localized('중요 이벤트 저장 오류: 디스크 여유 공간을 확인하세요.','Important event storage failed. Check free disk space.')}</p>}
      {(state.learning_archive_error || Object.keys(state.learning_migration_errors || {}).length > 0) && <p role="alert">{localized('학습 기록 이관·압축 일부 미완료입니다. 원본은 보존되어 있습니다. 저장소 최적화로 다시 점검하세요.', 'Some learning migration or compression is incomplete. Originals are retained. Retry storage optimization.')}</p>}
      {state.error && <p role="alert">{localized('저장소 처리 오류','Storage processing error')}: {state.error}</p>}
    </div>}
    {error && <p role="alert">{error}</p>}
    <button disabled={running} onClick={() => void act('optimize')}>{localized('저장소 최적화 · 이어서 실행','Optimize storage · continue')}</button>
    <button disabled={busy} onClick={() => void act('debug',24)}>{localized('상세 로그 24시간 켜기','Enable detailed logs for 24 hours')}</button>
    <button disabled={busy} onClick={() => void act('debug',0)}>{localized('상세 로그 끄기','Disable detailed logs')}</button>
  </section>;
}
