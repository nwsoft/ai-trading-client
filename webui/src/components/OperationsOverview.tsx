import type {ReactNode} from 'react';
import type {RuntimeSnapshot,WorkspaceSnapshot} from '../types';
import {evidenceOld,evidenceTime,regimeText} from './OperationVisuals';
import {sourcesForService} from '../venueSources';
import {localized as L} from '../i18n';
import {VisualTradingOverview} from './VisualTradingOverview';

export function dashboardTime(value:unknown) {
  if (!value) return L('미수신','Not received');
  const date=new Date(String(value));
  if(!Number.isFinite(date.getTime())) return L('시각 미확인','Time unknown');
  return date.toDateString()===new Date().toDateString()
    ? date.toLocaleTimeString(undefined,{hour12:false}) : date.toLocaleString();
}
export const executionLabel=(mode:string)=>({live:L('실거래','Live'),paper:L('가상 거래','Paper'),learning:L('관찰','Observe')}[mode]||L('모드 미확인','Unknown mode'));

export function OperationsOverview({runtime,workspace,service,failed,onSource,onFeature,onSettings,onAssets,onAsk,summary,controls}: {
  runtime:RuntimeSnapshot|null; workspace:WorkspaceSnapshot|null;service:string;failed:boolean;
  onSource:(source:string)=>void;onFeature:(suffix:string)=>void;onSettings:()=>void;onAssets:()=>void;onAsk:(question:string)=>void;
  summary:ReactNode; controls:ReactNode;
}) {
  const sources=sourcesForService(service).filter(s=>runtime?.enabled_sources?.includes(s)||runtime?.running_sources?.includes(s));
  const running=sources.filter(s=>runtime?.running_sources?.includes(s));
  const runtimeUncertain=!runtime||['error','stale','detached'].includes(runtime.status);
  const rows=sources.map(source=>{
    const mode=runtime?.execution_modes?.[source]||'unknown';
    const raw=workspace?.operation_overview?.[source];
    const evidence=raw?.source===source&&raw.mode===mode?raw:undefined;
    const blocked=evidence?.risk?.blocked===true;
    const old=evidence?.risk?evidenceOld(evidence.risk.observed_at):false;
    return {source,mode,evidence,blocked,old,running:running.includes(source)};
  });
  const blocked=rows.filter(r=>r.blocked);
  return <div className="operations-overview dashboard-overview">
    <header className="dashboard-heading">
      <div><h2>{service==='stock'?L('주식·증권','Stocks'):L('블록체인','Crypto')} {L('거래 현황','trading overview')}</h2>
        <span className="dashboard-runtime-count">{L('실행','Running')} <b>{runtimeUncertain?'—':running.length}</b> · {L('정지','Stopped')} {runtimeUncertain?'—':sources.length-running.length} / {L('대상','Configured')} {sources.length}</span>
      </div><div className="dashboard-control-slot">{controls}</div>
    </header>
    {(failed||runtimeUncertain)&&<div className="operations-attention dashboard-alert" role="status">{L('갱신 확인 필요 · 마지막 수신 자료가 남아 있을 수 있습니다.','Refresh needs checking. Data may be from a previous update.')} <button onClick={onSettings}>{L('연결 설정','Connection settings')}</button></div>}
    {blocked.length>0&&<div className="operations-attention dashboard-alert" role="status"><strong>{L('신규 진입 보류','Entry on hold')} {blocked.length}</strong>{blocked.map(r=><button key={r.source} onClick={()=>onSource(r.source)}>{r.source.toUpperCase()} · {r.old?L('이전 위험 평가','Earlier risk check'):L('위험 평가 확인','Review risk check')} →</button>)}</div>}
    <VisualTradingOverview runtime={runtime} workspace={workspace} sources={sources} failed={failed||runtimeUncertain} onSource={onSource} onFeature={onFeature}/>
    {summary}
    {!sources.length?<section className="dashboard-empty"><h3>{L('아직 선택한 기관이 없습니다.','No venues selected yet.')}</h3><p>{L('사용할 거래소·증권사를 설정하세요. 화면을 여는 것만으로 거래가 시작되지는 않습니다.','Choose venues in settings. Opening this screen does not start trading.')}</p><button onClick={onSettings}>{L('연결 설정 열기','Open connection settings')}</button></section>:
    <section className="dashboard-venues">
      <div className="dashboard-section-heading"><h3>{L('기관별 실행 상태','Venue execution status')}</h3><span title={runtime?.captured_at}>{L('갱신','Updated')} {dashboardTime(runtime?.captured_at)}</span><button onClick={()=>onFeature('trends')}>{L('시장 트렌드','Market trends')}</button></div>
      <table className="dashboard-venue-table"><thead><tr><th>{L('기관','Venue')}</th><th>{L('실행 설정','Execution mode')}</th><th>{L('상태','State')}</th><th>{L('시장 국면 · 관찰 / 확정','Regime · observed / confirmed')}</th><th>{L('최근 판단 / 연결 안내','Latest decision / setup')}</th><th><span className="dashboard-sr-only">{L('상세','Details')}</span></th></tr></thead>
      <tbody>{rows.map(r=>{
        const regime=r.evidence?.regime,candidate=r.evidence?.candidate;
        const decision=candidate?.allowed===true?L('후보 통과','Candidate passed'):candidate?.allowed===false?L('후보 보류','Candidate held'):L('판단 미확인','Decision unknown');
        return <tr key={r.source} className={`operations-venue ${r.blocked?'needs-attention':''}`}>
          <th scope="row">{r.source.toUpperCase()}</th>
          <td><span className={`dashboard-mode mode-${r.mode}`}>{executionLabel(r.mode)}</span></td>
          <td><span className={`dashboard-state ${!runtimeUncertain&&r.running?'is-running':''}`}>{runtimeUncertain?L('확인 필요','Check state'):r.running?L('실행 중','Running'):L('정지','Stopped')}</span></td>
          <td title={regime?`${evidenceTime(regime.observed_at)} · ${r.running?'최근 관찰':'정지 전 기록'}`:undefined}>{regime?<><span>{regimeText(regime.observed)} / {regimeText(regime.confirmed)}</span>{(evidenceOld(regime.observed_at)||!r.running)&&<small>{L('이전 기록','Earlier record')}</small>}</>:<span className="dashboard-muted">{L('분석 기록 없음','No analysis yet')}</span>}</td>
          <td className="dashboard-decision">{r.blocked?<span className="warning">{r.old?L('이전 평가 · 보류','Earlier hold'):L('신규 진입 보류','Entry held')}</span>:candidate?<span title={`${candidate.strategy_name||'기본 NoahAI'} · ${candidate.symbol||''} · ${evidenceTime(candidate.observed_at)}`}>{candidate.symbol||candidate.strategy_name||'NoahAI'} · {decision}{evidenceOld(candidate.observed_at)?L(' · 이전 기록',' · old'):''}</span>:<span className="dashboard-muted">{runtime?.credential_status?.[r.source]?L('키 저장됨 · 연결은 별도 확인','Keys saved · verify connection'):L('API 연결 설정 필요','API setup needed')}</span>}</td>
          <td><button aria-label={`${r.source.toUpperCase()} ${L('상세 보기','details')}`} onClick={()=>onSource(r.source)}>{L('상세','Details')} →</button></td>
        </tr>;
      })}</tbody></table>
      <details className="dashboard-explanation"><summary>{L('표시 기준과 연결 상태 안내','About these states')}</summary><p>{L('위쪽 실거래·가상 거래 선택은 오늘 통계만 바꿉니다. 이 목록은 각 기관의 실제 실행 설정입니다. 키 저장이나 실행 중 표시가 시세·계좌·보호주문 정상 여부를 보증하지 않습니다. 국면은 해당 기관 엔진의 관찰/확정 상태이며 상승 확률이 아닙니다. 후보 통과는 주문·체결 확인과 다릅니다.','The statistics filter does not change execution modes. Saved keys and running workers do not verify quotes, accounts or protective orders. Regimes are not probabilities. Passing a candidate check is not order or fill confirmation.')}</p></details>
    </section>}
    <nav className="operations-destinations dashboard-destinations" aria-label={L('빠른 실행','Quick actions')}>
      <strong>{L('빠른 실행','Quick actions')}</strong><button onClick={()=>onFeature('statistics')}>{L('거래 통계 · 대조','Statistics · reconciliation')}</button><button onClick={()=>onFeature('ai_custom')}>{L('전략 스튜디오','Strategy Studio')}</button>
      <button onClick={onAssets}>{L('자산 통합','Portfolio')}</button><button onClick={()=>onAsk(`현재 ${service==='stock'?'주식·증권':'블록체인'} 거래 현황을 설명해줘. 기관별 모드: ${rows.map(r=>`${r.source} ${r.mode} ${r.running?'실행':'정지'}`).join(', ')}. 미수신 자료는 추정하지 말고 확인할 메뉴와 다음 조치를 알려줘. 설정 저장과 거래 실행은 하지 마.`)}>{L('이 현황 AI에게 묻기','Ask AI about this view')}</button>
    </nav>
  </div>;
}
