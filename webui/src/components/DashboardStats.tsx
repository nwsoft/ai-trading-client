import type {ReactNode} from 'react';
import {localized as L} from '../i18n';
import {dashboardTime} from './OperationsOverview';

export function DashboardStats({mode,onMode,positions,positionLabel,closed,pnl,winRate,pnlTone,capturedAt,failed,details,onAccounts,accountBusy,canReadAccounts,onStatistics}: {
  mode:'live'|'paper'; onMode:(mode:'live'|'paper')=>void;
  positions:ReactNode;positionLabel:string;closed:ReactNode;pnl:string;winRate:string;pnlTone:string;
  capturedAt?:string;failed:boolean;details:ReactNode;onAccounts:()=>void;accountBusy:boolean;canReadAccounts:boolean;onStatistics:()=>void;
}) {
  return <section className="dashboard-statistics" aria-label={L('오늘 거래 요약','Today’s trading summary')}>
    <header><h3>{L('오늘 거래 요약','Today’s trading summary')}</h3>
      <div className="dashboard-mode-switch" role="group" aria-label={L('통계 조회 대상','Statistics view')}>
        <button className="mode-live" aria-pressed={mode==='live'} onClick={()=>onMode('live')}>{mode==='live'?'✓ ':''}{L('실거래 내역','Live records')} <span>LIVE</span></button>
        <button className="mode-paper" aria-pressed={mode==='paper'} onClick={()=>onMode('paper')}>{mode==='paper'?'✓ ':''}{L('가상 거래 내역','Paper records')} <span>PAPER</span></button>
      </div>
      <small className="dashboard-stat-scope">{L('조회만 변경 · 주문 모드 유지','View only · execution unchanged')}</small>
    </header>
    <div className="legacy-kpi-grid dashboard-kpis">
      {[{label:positionLabel,value:positions},{label:mode==='paper'?L('오늘 가상 청산','Paper closes today'):L('오늘 청산','Closes today'),value:closed},
        {label:mode==='paper'?L('오늘 가상 순손익','Paper net P&L today'):L('대조 완료 순손익','Reconciled net P&L'),value:pnl,tone:pnlTone},
        {label:mode==='paper'?L('가상 승률','Paper win rate'):L('대조 완료 승률','Reconciled win rate'),value:winRate}].map(item=><div className="legacy-kpi-card" key={item.label}><span>{item.label}</span><b className={`${item.tone||''} ${typeof item.value==='string'&&/[가-힣]/.test(item.value)?'is-text':''}`}>{item.value}</b></div>)}
    </div>
    <footer><span className={failed?'warning':''}>{failed?L('갱신 실패 · 이전 자료','Update failed · previous data'):L('최근 수신','Received')} {dashboardTime(capturedAt)} · {L('서비스 전체 · 오늘','Whole service · today')}</span>
      <button onClick={onStatistics}>{L('거래 통계 상세','Detailed statistics')} →</button>
    </footer>
    <details className="dashboard-explanation"><summary>{L('집계·계좌 확인 / AI 진단','Scope, account check and AI guidance')}</summary>
      {details}
      {mode==='live'&&<div className="dashboard-account-check"><button onClick={onAccounts} disabled={accountBusy||!canReadAccounts}>{accountBusy?L('계좌 확인 중…','Checking accounts…'):L('현재 계좌 확인','Check current accounts')}</button><span>{L('원장과 실제 계좌는 다를 수 있습니다. 버튼을 누를 때만 계좌를 조회합니다.','Ledger and account may differ. Accounts are fetched only when requested.')}</span></div>}
    </details>
  </section>;
}
