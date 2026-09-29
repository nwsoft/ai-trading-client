import {useState} from 'react';
import type {RuntimeSnapshot,WorkspaceSnapshot} from '../types';
import {localized as L} from '../i18n';
import {RegimeHistory,evidenceOld,evidenceTime,regimeText} from './OperationVisuals';

// Display-only projection: no client, polling, account requests or strategy writes.
export function VisualTradingOverview({runtime,workspace,service,sources,failed,onSource,onFeature,onSettings}: {
  runtime:RuntimeSnapshot|null;workspace:WorkspaceSnapshot|null;service:string;sources:string[];failed:boolean;
  onSource:(source:string)=>void;onFeature:(feature:string)=>void;onSettings:()=>void;
}) {
  const [choice,setChoice]=useState('');
  const preferred=runtime?.selected_sources?.[service];
  const source=sources.includes(choice)?choice:sources.includes(preferred||'')?preferred!:sources.find(s=>runtime?.running_sources?.includes(s))||sources[0]||'';
  const mode=runtime?.execution_modes?.[source]||'unknown';
  const raw=workspace?.operation_overview?.[source];
  const data=raw?.source===source&&raw.mode===mode?raw:undefined;
  const regime=data?.regime,candidate=data?.candidate;
  const running=runtime?.running_sources?.includes(source)===true;
  const uncertain=failed||!runtime||['error','stale','detached'].includes(runtime.status);
  const old=!running||uncertain||!!regime&&evidenceOld(regime.observed_at);
  const checks:Array<{passed?:boolean;reason?:unknown}>=Array.isArray(candidate?.checks)?candidate.checks.filter((c:unknown)=>c&&typeof c==='object').slice(0,20):[];
  const counts=[checks.filter(c=>c.passed===true).length,checks.filter(c=>c.passed===false).length,checks.filter(c=>typeof c.passed!=='boolean').length];
  const labels=[L('충족','Passed'),L('미충족','Not met'),L('미확인','Unknown')];
  const state=String(regime?.confirmed||'unknown');
  const known=['bull','bear','range','volatile','normal'].includes(state);
  const history=(Array.isArray(data?.regime_history)?data.regime_history:[]).slice(-24);
  return <section className="visual-overview" aria-label={L('시장·판단·전략 한눈에','Market, evidence and strategy')}>
    <header className="visual-scope"><h3>{L('시장·판단·전략 한눈에','Market, evidence and strategy')}</h3>
      <div className="visual-source-buttons" role="group" aria-label={L('분석 기관 선택','Analysis venue')}>
        {sources.map(s=><button key={s} aria-pressed={s===source} onClick={()=>setChoice(s)}>{s.toUpperCase()}</button>)}
        {!sources.length&&<button onClick={onSettings}>{L('기관 설정하기','Choose venues')}</button>}
      </div><small>{source?`${source.toUpperCase()} · ${mode.toUpperCase()}`:L('기관 미선택','No venue selected')} · {L('실행 설정 기준 근거 · 위쪽 통계 조회와 별개','Evidence uses execution mode, separate from statistics')}</small>
    </header>
    <div className="visual-insight-grid">
      <article className="visual-market visual-insight-card"><header><h4>{L('시장 국면','Market regime')}</h4><span className="visual-record-tag">{!regime?L('기록 대기','Awaiting evidence'):old?L('이전 기록','Earlier record'):L('최근 관찰','Latest observation')}</span></header>
        <div className="visual-market-main"><div className={`regime-state-orbit state-${known?state:'unknown'}`} role="img" aria-label={`${L('확정 국면','Confirmed regime')}: ${regimeText(regime?.confirmed)} · ${L('확률 아님','Not a probability')}`}>
          <span>{L('확정 국면','Confirmed regime')}</span><strong>{regimeText(regime?.confirmed)}</strong><small>{L('상태 표시 · 확률 아님','State, not probability')}</small>
        </div><div className="visual-regime-context"><span>{L('관찰','Observed')} <b>{regimeText(regime?.observed)}</b></span><span>{L('실행 상태','Worker')} <b>{uncertain?L('확인 필요','Unknown'):running?L('실행 중','Running'):L('정지','Stopped')}</b></span><small>{evidenceTime(regime?.observed_at)}</small></div></div>
        {history.length?<RegimeHistory rows={history}/>:<div className="visual-chart-empty"><span aria-hidden="true">— · — · —</span><p>{L('국면 변화 기록이 아직 없습니다.','No regime transitions recorded yet.')}</p><small>{L('관찰이 쌓이면 이곳에 변화 흐름을 표시합니다.','Recorded transitions will appear here.')}</small></div>}
        {regime&&<small className="visual-basis">{String(regime.basis||L('엔진 국면 판정','Engine regime classification'))}</small>}
        <button className="visual-detail" onClick={()=>onFeature('trends')}>{L('시장 분석 상세','Market analysis')} →</button>
      </article>
      <article className="visual-evidence visual-insight-card"><header><h4>{L('엔진 판단 근거','Engine decision evidence')}</h4><span className="visual-record-tag">{candidate?`${String(candidate.symbol||'')} · ${String(candidate.timeframe||'봉 미기록')}`:L('근거 대기','Awaiting evidence')}</span></header>
        {checks.length?<><div className="visual-check-chart" role="img" aria-label={counts.map((n,i)=>`${labels[i]} ${n}`).join(', ')}>{counts.map((n,i)=>n>0&&<span key={i} className={`check-state-${i}`} style={{flex:n}}>{n}</span>)}</div><div className="visual-check-legend">{counts.map((n,i)=><span key={i} className={`check-state-${i}`}>{labels[i]} {n}</span>)}</div><ul className="visual-check-list">{checks.slice(0,3).map((c,i)=><li key={i}><span className={`check-state-${c.passed===true?0:c.passed===false?1:2}`}>{c.passed===true?'✓':c.passed===false?'−':'?'}</span><span>{String(c.reason||L('사유 미기록','Reason not recorded'))}</span></li>)}</ul>{checks.length>3&&<details><summary>{L('나머지 검사 보기','More checks')} ({checks.length-3})</summary><ul className="visual-check-list">{checks.slice(3).map((c,i)=><li key={i}>{c.passed===true?'✓':c.passed===false?'−':'?'} {String(c.reason||'사유 미기록')}</li>)}</ul></details>}<small>{L('표시된 검사 최대 20개 · 중첩 검사 포함 · 승률/통과 확률 아님','Up to 20 checks, possibly nested; not a win rate or probability')}</small></>:<div className="visual-chart-empty"><div className="visual-empty-checks" aria-hidden="true"><i/><i/><i/></div><p>{L('최근 판단의 검사 기록이 없습니다.','No checks recorded for the latest decision.')}</p><small>{L('추세·거래량·시장 심리를 임의로 채우지 않습니다.','Trend, volume and sentiment are not inferred here.')}</small></div>}
        {candidate&&<small className="visual-evidence-time">{evidenceTime(candidate.observed_at)}{!running||uncertain||evidenceOld(candidate.observed_at)?L(' · 이전/확인 필요',' · earlier / check freshness'):''}</small>}
        <button className="visual-detail" disabled={!source} onClick={()=>onSource(source)}>{L('판단·로그 상세','Decision and log details')} →</button>
      </article>
      <article className="visual-strategy visual-insight-card"><header><h4>{L('최근 검토 전략','Recently evaluated strategy')}</h4><span className="visual-record-tag">{L('자동 추천 순위 아님','Not a recommendation ranking')}</span></header>
        <div className={`visual-decision-badge ${candidate?.allowed===true?'passed':candidate?.allowed===false?'held':'unknown'}`}>{candidate?.allowed===true?L('후보 통과','Candidate passed'):candidate?.allowed===false?L('후보 보류','Candidate held'):L('판단 기록 없음','No decision recorded')}</div>
        <h5>{candidate?String(candidate.strategy_name||L('기본 NoahAI','Default NoahAI')):L('전략 판단을 기다리고 있습니다','Awaiting a strategy decision')}</h5>
        {candidate?<><p className="visual-strategy-meta">{L('버전','Version')} {String(candidate.version_id||L('미기록','not recorded'))} · {String(candidate.signal||L('방향 미기록','direction unknown'))}</p><p className="visual-strategy-reason">{String(candidate.reason||L('판단 사유 미기록','Reason not recorded'))}</p><small>{L('봉 시각','Bar time')} {evidenceTime(candidate.bar_timestamp)}</small></>:<p className="visual-strategy-reason">{L('기존 전략의 적용·PAPER 검증 상태는 전략 스튜디오에서 확인할 수 있습니다.','Review applied strategies and PAPER validation in Strategy Studio.')}</p>}
        <div className="visual-safety-note">{data?.risk?.blocked===true?L('마지막 위험 평가: 신규 진입 보류','Latest risk check: entry held'):L('후보 판단 ≠ 주문·체결·보호 확인','Candidate decision ≠ order, fill or protection confirmation')}</div>
        <button className="visual-detail" onClick={()=>onFeature('ai_custom')}>{L('전략 적용·검증 상세','Strategy application and validation')} →</button>
      </article>
    </div>
  </section>;
}
