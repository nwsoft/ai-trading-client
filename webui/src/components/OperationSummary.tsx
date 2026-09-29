import type { WorkspaceSnapshot } from '../types';
import {RegimeHistory,regimeText,evidenceOld} from './OperationVisuals';

function timeLabel(value: unknown) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? new Date(n < 1e11 ? n * 1000 : n).toLocaleString() : '기록 없음';
}

export function OperationSummary({ data, source, mode, running, failed, onOpenFeature, onAskAssistant }: {
  data: WorkspaceSnapshot['operation_summary']; source: string; mode: string; running: boolean; failed: boolean;
  onOpenFeature?:(suffix:string)=>void; onAskAssistant?:(question:string)=>void;
}) {
  const scoped = data?.source === source && data?.mode === mode ? data : undefined;
  const regime = scoped?.regime, candidate = scoped?.candidate;
  const old = (row?: Record<string, any>) => row && evidenceOld(row.observed_at);
  const pool = scoped?.paper_pool;
  const checks=Array.isArray(candidate?.checks)?candidate.checks.slice(0,20):[];
  const passed=checks.filter(c=>c.passed===true).length;
  const reasonLabel = (value: unknown) => ({custom_entry_passed:'등록한 진입 조건 충족',custom_entry_not_met:'등록한 진입 조건 미충족',no_active_custom_strategy:'사용자 전략 없이 기본 NoahAI 후보 평가',paper_validation_not_matched_delegate_to_noah:'PAPER 전략 조건 미충족 · 기본 NoahAI로 판단'}[String(value)] || String(value || '사유 미기록'));
  return <section className="operation-summary" aria-label="운용 요약">
    <h3>{source.toUpperCase()} · {mode.toUpperCase()} 운용 요약</h3>
    <p role="status">{!running ? '현재 정지 · 아래는 마지막 관찰 기록입니다.' : failed ? '화면 갱신 실패 · 아래 기록은 최신 상태를 보장하지 않습니다.' : '실행 엔진이 기록한 최근 근거입니다. 새 AI 분석을 실행하지 않습니다.'}</p>
    <div className="operation-evidence-grid"><article><h4>시장국면 관찰</h4>
      <div className="operations-regime-pair"><span>관찰 <b>{regimeText(regime?.observed)}</b></span><span>확정 <b>{regimeText(regime?.confirmed)}</b></span></div>
      {regime ? <><small>{timeLabel(regime.observed_at)}{old(regime) ? ' · 오래된/불확실 근거 — 현재 국면으로 단정하지 마세요.' : ''}</small><p>{String(regime.basis ?? '엔진 국면 판정')} · 후보 판단과 관찰 시각이 다를 수 있습니다.</p></> : <p>해당 기관·모드의 국면 관찰 근거가 아직 없습니다.</p>}
    </article>
    <article><h4>종합 판단 근거 · 실제 검사</h4>
      {checks.length?<><div className="evidence-check-meter" role="img" aria-label={`표시된 검사 ${checks.length}개 중 충족 ${passed}개`}><span style={{width:`${passed/checks.length*100}%`}}/></div><p>표시된 검사 {checks.length}개 중 충족 {passed}개</p><small>중첩된 검사 일부(최대 20개)이며 점수·승률·독립 조건 충족률이 아닙니다. 상세 근거는 아래에서 확인하세요.</small></>:<p>실제 검사 근거 미수신 · 추세·거래량·시장 심리를 임의로 판정하지 않습니다.</p>}
    </article><article><h4>최근 검토 전략 · 자동 추천 아님</h4><p>{candidate?String(candidate.strategy_name||'기본 NoahAI'):'전략 판단 근거 없음'}</p>{candidate&&<p>버전 {String(candidate.version_id||'전략 버전 미지정')}</p>}{onOpenFeature&&<button onClick={()=>onOpenFeature('ai_custom')}>전략 스튜디오 · 적용/검증 확인</button>}<small>최근 후보에 사용된 전략이며 전체 적용 목록이나 최적 전략 순위가 아닙니다.</small></article></div>
    <RegimeHistory rows={scoped?.regime_history}/>
    {pool&&pool.scope_eligible>0&&<figure><figcaption>PAPER 평가 대상과 대기 · 학습 진행률 아님</figcaption><div className="paper-capacity-chart" role="img" aria-label={`평가 대상 ${pool.selected}개, 대기 ${pool.waiting}개`}><span style={{flex:Math.max(0,pool.selected)}}>평가 {pool.selected}</span>{pool.waiting>0&&<span className="waiting" style={{flex:pool.waiting}}>대기 {pool.waiting}</span>}</div></figure>}
    <article><h4>최근 후보 판단 — 주문 결과 아님</h4>
      {candidate ? <><p>{String(candidate.symbol)} · {String(candidate.signal)} · {candidate.allowed ? '후보 단계 통과' : '후보 단계 보류'}</p><p>{reasonLabel(candidate.reason)}</p><p>{String(candidate.strategy_name || '기본 NoahAI')} · 버전 {String(candidate.version_id || '전략 버전 미지정')}</p><small>판단 {timeLabel(candidate.observed_at)} · 봉 {timeLabel(candidate.bar_timestamp)} · {String(candidate.timeframe || '시간봉 미기록')}{old(candidate) ? ' · 오래된 근거' : ''}</small></> : <p>아직 평가된 후보가 없습니다. 상세 로그에서 실행·시세 상태를 확인하세요.</p>}
      <p>후보 통과 후에도 위험·포지션·주문 검사가 필요합니다. 이 화면은 보호주문 정상 여부를 보증하지 않습니다.</p>
      {Array.isArray(candidate?.checks) && candidate.checks.length > 0 && <details><summary>실제 평가 근거 (최대 20개)</summary><ul>{candidate.checks.map((item: {passed: boolean; reason: string}, i: number) => <li key={i}>{item.passed ? '충족' : '미충족/확인 불가'} · {item.reason}</li>)}</ul></details>}
    </article>
    {pool && <article><h4>PAPER 평가 용량</h4><p>범위 적합 {pool.scope_eligible}개 · 평가 대상 {pool.selected}개 · 대기 {pool.waiting}개</p><p>전체 슬롯 {pool.limit}개 중 적용 전략 {pool.applied_slots}개 사용. 우선순위·등록 순으로 선택하며 자동 순환하지 않습니다. 여러 전략이 같은 PAPER 실행 계좌를 공유하고, 포지션 수는 별도 한도를 따릅니다.</p>{pool.waiting > 0 && <p>전략 스튜디오에서 검증을 중지하거나 우선순위를 조정하면 대상을 변경할 수 있습니다.</p>}</article>}
    <article><h4>최근 위험 평가 — 보호주문 확인과 별개</h4>{scoped?.risk ? <><p>{scoped.risk.blocked ? '신규 진입 보류' : scoped.risk.status === 'not_applicable' ? '이 모드에서 LIVE 손실 평가 미적용' : scoped.risk.status === 'ok' ? '당시 손실 가드레일 보류 없음' : '평가 상태 확인 필요'}</p><p>{String(scoped.risk.reason_code || scoped.risk.reason || scoped.risk.status)}</p><small>{timeLabel(scoped.risk.observed_at)}{old(scoped.risk) ? ' · 오래된 근거' : ''}</small></> : <p>해당 모드의 위험 평가 근거 미수신. 정상 또는 손실 0으로 해석하지 않습니다.</p>}</article>
    <p>마지막 실행 상태: {String(scoped?.runtime?.code || '미기록')} · {timeLabel(scoped?.runtime?.observed_at)}</p>
    <nav className="operations-destinations" aria-label="기관 요약 상세 기능">{onOpenFeature&&<><button onClick={()=>onOpenFeature('trends')}>시장 트렌드</button><button onClick={()=>onOpenFeature('statistics')}>거래 통계 · 성과</button></>}{onAskAssistant&&<button onClick={()=>onAskAssistant(`${source.toUpperCase()} ${mode.toUpperCase()} 운용 근거를 설명해줘. 관찰 ${regimeText(regime?.observed)}, 확정 ${regimeText(regime?.confirmed)}, 관찰 시각 ${timeLabel(regime?.observed_at)}. 최근 후보 ${candidate?.symbol||'미수신'}, ${reasonLabel(candidate?.reason)}. 과거 기록·미수신은 현재 상태로 추정하지 말고 다음 확인 경로를 알려줘. 거래나 설정을 변경하지 마.`)}>이 근거 AI에게 묻기</button>}</nav>
  </section>;
}
