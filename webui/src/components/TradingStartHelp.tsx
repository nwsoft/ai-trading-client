import { useState } from 'react';
import type { GatewayClient } from '../api';
import { RecordRecoveryPanel } from './RecordRecoveryPanel';

/** Deliberately allowlisted diagnostics: no keys, account IDs, amounts or raw logs. */
export function TradingStartHelp({ client, source, mode, message, occurredAt, onAskAssistant }: {
  client: GatewayClient; source: string; mode: string; message: string; occurredAt: string;
  onAskAssistant?: (question: string) => void;
}) {
  const [report, setReport] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const managed = message.includes('managed_position_reconciliation_required');
  async function prepareReport() {
    setBusy(true); setNotice('');
    const safeSource = /^[a-z]{2,24}$/.test(source) ? source : 'unknown';
    const request = message.match(/요청 ID[:：]\s*([A-Za-z0-9_-]{16,80})/)?.[1] || '미기록';
    let version = '조회 실패 · 앱 제목의 버전을 함께 알려주세요';
    try {
      const platform = await client.platform();
      if (/^\d+(?:\.\d+){2,3}$/.test(platform.release_version)) version = platform.release_version;
    } catch { /* Reporting must work even during a partial gateway failure. */ }
    let recovery = '복구 상태 조회 실패 또는 아직 점검 전';
    try {
      const status = await client.recordRecovery(source);
      const safeState = /^[a-z_]{1,50}$/.test(String(status.state)) ? status.state : 'unknown';
      const reasons = Object.entries(status.reasons ?? {}).filter(([code, count]) => /^[a-z_]{1,80}$/.test(code) && Number.isSafeInteger(count) && Number(count) >= 0);
      recovery = `복구 상태: ${safeState}\n미확정 사유: ${JSON.stringify(Object.fromEntries(reasons))}`;
    } catch { /* A report must still be possible when the local journal fails. */ }
    setReport(`NoahAI 거래 시작 진단\n버전: ${version}\n기관: ${safeSource}\n모드: ${['live','paper','learning'].includes(mode) ? mode : 'unknown'}\n시각(UTC): ${occurredAt}\n동작: 거래 시작\n지원 코드: ${managed ? 'managed_position_reconciliation_required' : 'start_refused_check_displayed_reason'}\n요청 ID: ${request}\n${recovery}\n거래 시작은 보류됨. 복구 완료 후 시작 재평가 필요.\nAPI 키·계좌번호·잔고·주문 내역·원본 로그는 포함하지 않았습니다.`);
    setBusy(false);
  }
  return <section className="trading-start-help" aria-label="거래 시작 보류 해결 안내">
    <h3>거래 시작이 보류되었습니다</h3>
    <p>{managed ? '현재 포지션과 앱의 미청산 기록이 맞지 않습니다. 실제 청산 근거를 확인해 기록을 정리해야 합니다.' : '위에 표시된 원인을 먼저 확인하세요. API 권한·손실 한도·기록 불일치는 서로 다른 조치가 필요합니다.'}</p>
    <p>앱 전체가 잠긴 것은 아닙니다. 상태 조회·설정 확인·기록 점검은 이용할 수 있습니다. 오류를 무시하거나 기록을 삭제해 LIVE를 시작하지 마세요. 기존 포지션의 실제 보호 주문 상태는 별도로 확인하세요.</p>
    <details open={managed}><summary>이 화면에서 거래 기록 점검·복구</summary><RecordRecoveryPanel client={client} initialSource={source} /></details>
    <p>복구 후 직접 시작을 누르면 현재 위험 기준을 다시 확인합니다. 같은 사유가 남으면 아래 진단을 Q&amp;A 또는 관리자에게 전달하세요. AI는 설명을 도울 뿐 손익을 확정하거나 거래 제한을 해제하지 않습니다.</p>
    <button type="button" disabled={busy} onClick={() => void prepareReport()}>Q&amp;A·관리자용 진단 만들기</button>
    {report && <div><label>공유 전 진단 내용 확인<textarea readOnly rows={12} value={report} /></label>
      <button type="button" onClick={() => {
        if (!navigator.clipboard) { setNotice('위 내용을 선택해 복사하세요.'); return; }
        void navigator.clipboard.writeText(report).then(() => setNotice('복사했습니다. Q&A에 붙여 넣으세요.'), () => setNotice('자동 복사가 안 되면 위 내용을 선택해 복사하세요.'));
      }}>진단 복사</button>
      {onAskAssistant && <button type="button" onClick={() => onAskAssistant(`다음은 사용자가 공유하기로 확인한 거래 시작 진단입니다. 확인된 원인과 미확인 원인을 구분하고 앱에서 할 조치를 설명하세요. 손익 추정·보호 우회·자동 거래 시작을 권하지 마세요.\n${report}`)}>검토한 진단으로 AI에게 묻기</button>}
    </div>}
    {notice && <p role="status">{notice}</p>}
  </section>;
}
