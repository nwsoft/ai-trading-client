import { useEffect, useState } from 'react';
import type { GatewayClient } from '../api';
import { localized } from '../i18n';

const POLICY = 'product-observation-20261018';
const errorText: Record<string, string> = {
  delivery_pending: '연결 대기 중입니다. 저장된 활동은 연결되면 다시 전송합니다.',
  authentication_required: '다시 로그인하면 미전송 활동을 이어서 전송합니다.',
  collection_error: '활동을 저장하지 못했습니다. 저장 공간과 파일 권한을 확인하세요.',
  observation_rejected: '일부 활동을 서버가 거부했습니다. 통계 누락 가능성을 확인해야 합니다.',
  outbox_full: '미전송 보관 공간이 가득 찼습니다. 연결 상태를 확인하세요.'
};
export function ProductMetricsConsent({client}: {client: GatewayClient}) {
  const [state, setState] = useState<Record<string, any> | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    const load = () => client.productMetricsStatus?.().then(s => { if(active) setState(s); }).catch(() => {if(active) setError('통계 설정을 불러오지 못했습니다.');});
    void load(); const timer = setInterval(load, 10000);
    return () => {active=false; clearInterval(timer);};
  }, [client]);
  async function save(enabled: boolean) {
    if (!client.configureProductMetrics || (enabled && !agreed)) return;
    setBusy(true); setError('');
    try {setState(await client.configureProductMetrics(enabled, POLICY)); setAgreed(false); if(enabled) await client.observeProduct?.('app_open', crypto.randomUUID());}
    catch {setError('통계 설정을 저장하지 못했습니다. 다시 확인해 주세요.');}
    finally {setBusy(false);}
  }
  return <section className="product-metrics-consent" aria-label="제품 이용 통계 동의">
    <h3>{localized('제품 이용 통계 · 선택 동의', 'Product usage statistics · optional')}</h3>
    <p>{localized('앱·전략 화면 열기, 전략 저장·검증·승인·적용과 검증 근거 열기, PAPER 시작·일시정지, LIVE 시작의 종류와 시각을 제품 개선과 이용률 측정에 사용합니다. 이름·이메일·거래소 인증정보·잔고·주문 원문·전략 내용은 이 통계에 담지 않습니다.', 'Optional activity types (including opening validation explanations) and times help measure usage and improve the product. These statistics exclude names, email, exchange credentials, balances, order details and strategy contents.')}</p>
    <p>{localized('계정은 서버에서 가명 처리합니다. 서버의 원시 활동은 90일 기준으로 매일 정리합니다. 오프라인 활동은 이 PC에 보관해 재연결 시 전송하며, 동의를 철회하면 이 PC의 미전송 활동을 삭제합니다. 이미 수신된 통계의 삭제는 고객지원에 요청할 수 있습니다. 선택하지 않아도 제품을 사용할 수 있습니다.', 'Accounts are pseudonymized by the server. Server raw activity is cleaned daily under a 90-day retention policy. Offline events stay on this PC until delivery. Withdrawal clears unsent events; contact support about received data. Product access does not require consent.')}</p>
    <p>{localized('이 설정은 위 제품 이용 통계에 적용됩니다. 거래 기록과 계정 보안 기록은 별도로 유지됩니다.', 'This setting covers these product usage statistics. Trading and account security records are managed separately.')}</p>
    <p>{localized('동의·철회 시각, 동의 문서 버전, 클라이언트 버전과 무작위 설치 식별자를 함께 전송합니다. 상세 이력은 90일 정리 대상이며, 최신 동의 상태는 과거 요청의 재활성화를 막기 위해 유지합니다. 철회 즉시 이 PC의 수집을 끄며, 오프라인에서는 서버 철회가 전송 대기로 남습니다.', 'Consent and withdrawal times, policy version, client version and a random installation identifier are transmitted. Detailed history is retained for 90 days; the latest consent state remains to prevent stale requests from re-enabling collection. Withdrawal stops local collection immediately; offline server notification remains pending.')}</p>
    {state?.consent_reconfirmation_required && <p>{localized('이전 동의 이력은 서버에서 확인되지 않아 수집을 멈췄습니다. 다시 동의하거나 미전송 활동을 삭제할 수 있습니다.', 'Collection is paused because the previous consent has no server history. You can reconfirm or clear unsent activity.')}</p>}
    {state?.consent_reconfirmation_required && <button type="button" disabled={busy} onClick={()=>void save(false)}>{localized('철회 · 미전송 활동 삭제', 'Withdraw and clear pending activity')}</button>}
    {state?.enabled ? <button type="button" disabled={busy} onClick={()=>void save(false)}>{localized('통계 동의 철회 · 미전송 활동 삭제', 'Withdraw consent and clear unsent activity')}</button> : <>
      <label><input type="checkbox" checked={agreed} disabled={busy||!state} onChange={e=>setAgreed(e.target.checked)} />{localized(' 위 항목·목적·보관기간을 확인했고 선택 수집에 동의합니다.', ' I agree to this optional collection and retention.')}</label>
      <button type="button" disabled={busy||!agreed||!state} onClick={()=>void save(true)}>{localized('동의하고 통계 켜기', 'Agree and enable statistics')}</button>
    </>}
    <p role="status" aria-live="polite">{error || errorText[state?.error] || (state ? (state.enabled ? localized('동의됨', 'Enabled') : localized('수집 꺼짐', 'Disabled')) : localized('불러오는 중', 'Loading'))}
      {state && ` · ${localized('미전송', 'Pending')} ${state.pending} · ${localized('수신 거부', 'Rejected')} ${state.rejected}`}
      {state && ` · ${localized('동의·철회 전송 대기', 'Pending consent notifications')} ${state.consent_pending ?? 0} · ${localized('동의 알림 거부', 'Rejected consent notifications')} ${state.consent_rejected ?? 0}`}
      {state?.last_received && ` · ${localized('마지막 수신 확인', 'Last receipt')} ${new Date(state.last_received).toLocaleString()}`}
    </p>
  </section>;
}
