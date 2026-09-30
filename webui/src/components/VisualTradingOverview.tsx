import {useState} from 'react';
import type {RuntimeSnapshot,WorkspaceSnapshot} from '../types';
import {RegimeHistory,REGIME_LABELS,regimeText,evidenceOld,evidenceTime} from './OperationVisuals';

/** Pure rendering of the existing, scoped engine snapshot. No API/AI calls. */
export function VisualTradingOverview({runtime,workspace,sources,failed,onSource,onFeature}: {
  runtime:RuntimeSnapshot|null;workspace:WorkspaceSnapshot|null;sources:string[];failed:boolean;
  onSource:(source:string)=>void;onFeature:(suffix:string)=>void;
}) {
  const [choice,setChoice]=useState('');
  const source=sources.includes(choice)?choice:sources.find(s=>runtime?.running_sources?.includes(s))||sources[0]||'';
  const mode=runtime?.execution_modes?.[source]||'unknown';
  const raw=workspace?.operation_overview?.[source];
  const data=raw?.source===source&&raw.mode===mode?raw:undefined;
  const regime=data?.regime,candidate=data?.candidate;
  const running=runtime?.running_sources?.includes(source);
  const checks:Array<{passed?:boolean;reason?:string}>=Array.isArray(candidate?.checks)?candidate.checks.filter(c=>c&&typeof c==='object').slice(0,20):[];
  const passed=checks.filter(c=>c.passed===true).length,held=checks.filter(c=>c.passed===false).length,unknown=checks.length-passed-held;
  const state=REGIME_LABELS[String(regime?.confirmed)]?String(regime?.confirmed):'unknown';
  const status=(row?:Record<string,any>)=>`${evidenceTime(row?.observed_at)}${row&&(failed||!running||evidenceOld(row.observed_at))?' · 이전 기록 / 최신 확인 필요':''}`;
  const reason=({custom_entry_passed:'등록한 진입 조건 충족',custom_entry_not_met:'등록한 진입 조건 미충족',no_active_custom_strategy:'기본 NoahAI 후보 평가',paper_validation_not_matched_delegate_to_noah:'PAPER 조건 미충족 · 기본 NoahAI 판단'} as Record<string,string>)[String(candidate?.reason)]||String(candidate?.reason||'사유 미기록');
  return <section className="visual-overview" aria-label="시장·판단·전략 한눈에">
    <header className="visual-heading"><div><h3>시장·판단·전략 한눈에</h3><small>선택 기관의 실제 실행 근거 · 통계 조회 모드와 별개</small></div>
      <div role="group" aria-label="분석 기관 선택">{sources.map(s=><button key={s} aria-pressed={source===s} onClick={()=>setChoice(s)}>{s.toUpperCase()}</button>)}</div>
    </header>
    <div className="visual-context">{source.toUpperCase()||'기관 미선택'} · {mode.toUpperCase()} · {running?'실행 중':'정지'}{failed?' · 갱신 실패':''} <span>새 AI 판단이나 주문을 실행하지 않습니다.</span></div>
    <div className="visual-insight-grid">
      <article><h4>시장 국면</h4>
        <div className={`regime-state-orbit regime-${state}`} role="img" aria-label={`확정 국면 ${regimeText(regime?.confirmed)} · 확률 아님`}><span>확정 국면</span><strong>{regimeText(regime?.confirmed)}</strong></div>
        <p>최근 관찰 <b>{regimeText(regime?.observed)}</b> <span>→</span> 확정 <b>{regimeText(regime?.confirmed)}</b></p>
        <small>{status(regime)}</small>
        <RegimeHistory rows={data?.regime_history}/>
        {!regime&&<p className="visual-empty">엔진의 국면 관찰 기록이 아직 없습니다. 시세 수신·실행 상태를 기관 상세에서 확인하세요.</p>}
      </article>
      <article><h4>AI·전략 판단 근거</h4><p>최근 후보의 실제 검사 결과</p>
        {checks.length?<><div className="visual-check-chart" role="img" aria-label={`검사 ${checks.length}개: 충족 ${passed}, 미충족 ${held}, 미확인 ${unknown}`}>
          {passed>0&&<span className="check-pass" style={{flex:passed}}/>}{held>0&&<span className="check-hold" style={{flex:held}}/>}{unknown>0&&<span className="check-unknown" style={{flex:unknown}}/>}
        </div><p className="visual-legend">충족 {passed} · 미충족 {held} · 미확인 {unknown}</p><ul className="visual-checks">{checks.slice(0,3).map((c,i)=><li key={i}><span>{c.passed===true?'✓':c.passed===false?'–':'?'}</span>{String(c.reason||'검사 사유 미기록')}</li>)}</ul>
        {checks.length>3&&<details><summary>나머지 검사 {checks.length-3}개</summary><ul>{checks.slice(3).map((c,i)=><li key={i}>{c.passed===true?'충족':c.passed===false?'미충족':'미확인'} · {String(c.reason||'사유 미기록')}</li>)}</ul></details>}</>:<div className="visual-empty-chart"><span>판단 근거 대기</span><p>조건별 검사 기록을 수신하면 여기에 표시합니다. 빈값은 통과가 아닙니다.</p></div>}
        <small>{status(candidate)}</small>
      </article>
      <article><h4>최근 검토 전략</h4><div className="visual-strategy"><span className="visual-decision">{candidate?.allowed===true?'후보 통과':candidate?.allowed===false?'후보 대기':'판단 기록 없음'}</span>
        <strong>{String(candidate?.strategy_name|| (candidate?'기본 NoahAI':'전략 근거 대기'))}</strong>
        {candidate&&<><p>{String(candidate.symbol||'종목 미기록')} · {String(candidate.timeframe||'시간봉 미기록')}</p><small>버전 {String(candidate.version_id||'미기록')}</small><p>{reason}</p><small>평가 {status(candidate)}<br/>기준 봉 {evidenceTime(candidate.bar_timestamp)}</small></>}
        {!candidate&&<p>실제 평가된 전략·종목·진입 또는 대기 이유를 보여줍니다. 적용 전략 전체나 추천 순위와는 다릅니다.</p>}
        {data?.risk?.blocked===true&&<p className="warning">신규 진입 보류 평가 · {status(data.risk)}</p>}
      </div>
        <nav><button onClick={()=>onFeature('ai_custom')}>전략 스튜디오</button>{source&&<button onClick={()=>onSource(source)}>근거·조치 상세 →</button>}</nav>
      </article>
    </div>
    <details className="visual-explanation"><summary>그래프·판단 표시 기준</summary><p>국면 원형은 상태이며 확률이 아닙니다. 변화 이력은 시간 간격이 아닌 상태 전환 순서입니다. 검사 막대는 개수 구성이며 성공 확률·추천 점수나 모든 전략의 평가 결과가 아닙니다. 후보 통과는 주문·체결 완료가 아니며 위험·포지션·주문 검사가 별도로 필요합니다.</p></details>
  </section>;
}
