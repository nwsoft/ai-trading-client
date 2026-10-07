import type { WorkspaceSnapshot } from '../types';
import {useState, useEffect, useRef} from 'react';
import {RegimeHistory,regimeText,evidenceOld} from './OperationVisuals';

function timeLabel(value: unknown) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? new Date(n < 1e11 ? n * 1000 : n).toLocaleString() : '기록 없음';
}

export function OperationSummary({ data, source, mode, running, failed, onOpenFeature, onAskAssistant, onCancelRecovery, onNewPaperSession }: {
  data: WorkspaceSnapshot['operation_summary']; source: string; mode: string; running: boolean; failed: boolean;
  onOpenFeature?:(suffix:string)=>void; onAskAssistant?:(question:string)=>void;
  onCancelRecovery?:()=>Promise<void>;
  onNewPaperSession?:()=>Promise<Record<string,any>>;
}) {
  const [sessionAcknowledged,setSessionAcknowledged]=useState(false), [sessionBusy,setSessionBusy]=useState(false), [sessionMessage,setSessionMessage]=useState('');
  const [recoveryBusy,setRecoveryBusy]=useState(false), [recoveryError,setRecoveryError]=useState('');
  const recoveryGeneration=useRef(0);
  useEffect(()=>{recoveryGeneration.current++;setRecoveryError('');setRecoveryBusy(false);setSessionAcknowledged(false);setSessionBusy(false);setSessionMessage('');return()=>{recoveryGeneration.current++;};},[source,mode]);
  async function newPaperSession(){if(!sessionAcknowledged||!onNewPaperSession)return;const token=recoveryGeneration.current;setSessionBusy(true);setSessionMessage('');try{const result=await onNewPaperSession();if(token===recoveryGeneration.current){setSessionAcknowledged(false);setSessionMessage(result.created?'새 PAPER 평가 기준을 저장했습니다. 과거 손익은 복구되지 않았으며 거래는 시작하지 않았습니다. 시작 버튼으로 다시 검증하세요.':'이미 새 PAPER 평가 기준이 있습니다. 다시 초기화하지 않았습니다.');}}catch(error){if(token===recoveryGeneration.current)setSessionMessage(error instanceof Error?error.message:'새 PAPER 평가를 준비하지 못했습니다.');}finally{if(token===recoveryGeneration.current)setSessionBusy(false);}}
  async function cancelRecovery(){const token=recoveryGeneration.current;setRecoveryBusy(true);setRecoveryError('');try{await onCancelRecovery?.();if(token===recoveryGeneration.current)setRecoveryError('복원을 취소했습니다. 사용자 저장 정책은 유지되며 주문·거래 재개를 실행하지 않았습니다.');}catch{if(token===recoveryGeneration.current)setRecoveryError('복원 취소에 실패했습니다. 실행 상태를 다시 확인하세요.');}finally{if(token===recoveryGeneration.current)setRecoveryBusy(false);}}
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
    {scoped?.capital && <article role="status"><h4>자금 배분 근거</h4>
      <p>{({paper_reconciled_funds:'가상 초기자금 + 기록된 청산 순손익 − 보유 증거금·비용 여유',paper_virtual_equity:'LEARNING 가상 기준자금 · 주문 없음',paper_funds_unverified:'가상 자금 대조 필요 · 신규 진입 보류',available_balance_unverified:'기관 주문 가능금액 확인 필요 · 신규 진입 보류',orderable_cash:'기관 응답의 주문 가능현금',available_cash:'기관 응답의 가용현금',available_balance:'기관 응답의 가용잔고',availableBalance:'기관 응답의 가용잔고',currency_free_balance:'해당 통화의 사용 가능잔고'} as Record<string,string>)[String(scoped.capital.capital_basis)] ?? '자금 확인 근거 검토 필요'}</p>
      <p>예약 전 가용액 {['paper_reconciled_funds','paper_virtual_equity','orderable_cash','available_cash','available_balance','availableBalance','currency_free_balance'].includes(String(scoped.capital.capital_basis)) && scoped.capital.available_capital != null && Number.isFinite(Number(scoped.capital.available_capital)) ? Number(scoped.capital.available_capital).toLocaleString() : '미확인'} {String(scoped.capital.quote_currency || '')}</p>
      {scoped.capital.reason && <p>{({paper_ledger_currency_unverified:'과거 PAPER 청산 기록의 결제 통화가 누락되어 자금을 대조할 수 없습니다.',paper_ledger_pnl_unverified:'과거 PAPER 청산 기록의 손익·비용 근거가 부족하여 자금을 대조할 수 없습니다.',paper_ledger_reconciliation_budget:'PAPER 기록이 자동 대조 범위를 넘었습니다. 거래 기록 점검에서 원장을 확인하세요.',paper_position_mode_unverified:'보유 포지션의 PAPER 모드를 확인할 수 없습니다.',paper_position_notional_unverified:'보유 포지션의 수량·진입가를 확인할 수 없습니다.',paper_position_margin_unverified:'보유 포지션의 증거금 계산 근거를 확인할 수 없습니다.',paper_ledger_event_conflict:'같은 PAPER 청산 기록에 서로 다른 손익이 있어 대조가 필요합니다.'} as Record<string,string>)[String(scoped.capital.reason)] ?? 'PAPER 청산 원장·보유 포지션 대조가 필요합니다.'}</p>}
      <small>{timeLabel(scoped.capital.observed_at)}{old(scoped.capital) ? ' · 오래된 자금 관찰' : ''}</small>
      <p>미체결 주문 예약은 추가로 차감하며, 통화·기관 간 자금을 합치거나 미실현 이익을 지출 가능한 자금으로 계산하지 않습니다.</p>
      {scoped.capital.paper_session_id && <p>새 PAPER 평가 시작: {String(scoped.capital.paper_session_started_at)}. 이 가용액은 새 평가 구간의 기준자금·청산·보유만 반영합니다. 과거 기록과 전체 기간 통계는 보존되며 과거 손익 복구 완료를 뜻하지 않습니다.</p>}
      {mode==='paper' && !scoped.capital.paper_session_id && ['paper_ledger_currency_unverified','paper_ledger_pnl_unverified'].includes(String(scoped.capital.reason)) && onNewPaperSession && <div>
        <p>과거 기록의 필수 값이 없어 기존 가상 자금을 복원할 수 없는 경우, 과거 기록을 보존하고 설정의 PAPER 기준자금으로 새 평가를 시작할 수 있습니다. 해당 기관을 정지하고 보유 PAPER 포지션 청산과 주문 예약 해소를 먼저 확인하세요. 이 작업은 한 번만 가능하며 손실 후 반복 초기화는 지원하지 않습니다.</p>
        <label><input type="checkbox" checked={sessionAcknowledged} disabled={sessionBusy} onChange={event=>setSessionAcknowledged(event.target.checked)}/>과거 손익 복구가 아니라 별도의 새 PAPER 평가라는 점을 확인했습니다.</label>
        <button disabled={!sessionAcknowledged||sessionBusy||running} onClick={()=>void newPaperSession()}>{sessionBusy?'기준 저장 중…':'과거 기록 보존하고 새 PAPER 평가 준비'}</button>
      </div>}
      {sessionMessage&&<p role="status">{sessionMessage}</p>}
      {scoped.capital.capital_basis==='available_balance_unverified' && <p>LIVE는 거래 기록 점검과 기관 연결·주문 가능금액 응답을 확인하세요. PAPER 새 평가로 실거래 기록이나 위험 한도를 해제하지 않습니다.</p>}
      {scoped.capital.capital_basis==='paper_funds_unverified' && !['paper_ledger_currency_unverified','paper_ledger_pnl_unverified'].includes(String(scoped.capital.reason)) && <p>PAPER 원장·보유 자료의 오류를 먼저 확인해야 합니다. 기록 삭제나 기준자금 변경으로 해제하지 않습니다.</p>}
    </article>}
    {scoped?.orders?.portfolio_exposure && <article role="status"><h4>기관 통합 보유 노출</h4>
      <p>{scoped.orders.portfolio_exposure.status === 'allowed' ? '당시 통합 노출 한도 이내 · 주문 승인과 별개' : '통합 노출 확인 필요 · 신규 진입 보류'}</p>
      <p>{({portfolio_exposure_unverified:'지정 기관의 완전한 보유 자료 필요',portfolio_exposure_policy_incomplete:'대상 기관과 하나 이상의 노출 상한을 설정하세요',portfolio_current_venue_not_covered:'현재 기관을 통합 노출 대상에 포함하세요',portfolio_fx_unverified:'지정 현물 기관의 USDT/KRW 환산 시세 필요',portfolio_fx_stale:'환산 시세가 오래되었습니다',portfolio_reference_cap_exceeded:'환산한 통합 노출 상한 초과',portfolio_exposure_within_limits:'보유 노출과 신규 주문 예약을 함께 검사했습니다'} as Record<string,string>)[String(scoped.orders.portfolio_exposure.reason)] ?? (String(scoped.orders.portfolio_exposure.reason).startsWith('portfolio_gross_cap_exceeded:') ? '해당 통화의 총 보유 노출 상한 초과' : '기관 자료와 노출 설정 확인 필요')}</p>
      {scoped.orders.portfolio_exposure.gross_by_currency && <p>{Object.entries(scoped.orders.portfolio_exposure.gross_by_currency).map(([quote,value])=>`${quote} ${Number(value).toLocaleString()}`).join(' · ')}</p>}
      {scoped.orders.portfolio_exposure.reference_gross != null && <p>환산 노출 {Number(scoped.orders.portfolio_exposure.reference_gross).toLocaleString()} {String(scoped.orders.portfolio_exposure.reference_currency)}</p>}
      {scoped.orders.portfolio_exposure.fx && <p>환산 근거 {String(scoped.orders.portfolio_exposure.fx.source)} · {String(scoped.orders.portfolio_exposure.fx.rate)} · {timeLabel(scoped.orders.portfolio_exposure.fx.observed_at)}</p>}
      {scoped.orders.portfolio_exposure.missing_venues?.length>0 && <p>확인할 기관: {scoped.orders.portfolio_exposure.missing_venues.join(', ')}. 각 기관의 연결·운용을 확인하세요. 자료를 0으로 초기화하지 않습니다.</p>}
      <small>{timeLabel(scoped.orders.portfolio_exposure.observed_at)}</small><p>보유·예약과 이번 진입 검토액을 포함한 총 계약 노출이며 가용자금이 아닙니다. LONG/SHORT를 상쇄하지 않습니다. PAPER는 진입 금액 기준입니다. 설정에서 지정한 기관만 포함하며 보호·청산 주문은 계속 검사합니다.</p>
    </article>}
    {scoped?.correlation && <article><h4>관측 상관관계와 배분</h4><p>같은 통화의 기관·자산별 완료 일봉 수익률을 두 관측 날짜로 맞췄습니다. 과거 상관은 수익 예측이 아닙니다. 부족 자료는 무상관으로 처리하지 않습니다.</p><small>{timeLabel(scoped.correlation.observed_at)}</small>
      <details><summary>종목별 계산 근거</summary><ul>{(scoped.correlation.candidates ?? []).slice(0,30).map((row:Record<string,any>)=><li key={String(row.symbol)}>{String(row.symbol)} · {row.correlation_basis==='observed_aligned_daily_returns' ? `배분에 반영한 양의 상관 ${Number(row.avg_correlation).toFixed(3)}` : '상관 자료 부족 · 보수적인 배분'}<ul>{(row.correlation_pairs??[]).map((pair:Record<string,any>)=><li key={String(pair.symbol)}>{String(pair.symbol)} · {pair.value == null ? '미확인' : Number(pair.value).toFixed(3)} · 표본 {String(pair.samples)} · {pair.start && pair.end ? `${pair.start}~${pair.end}` : '기간 미확인'}</li>)}</ul></li>)}</ul></details>
    </article>}
    {scoped?.recovery && <article><h4>실행 정책 회복</h4><p>{({restored:'정상 정책으로 제한 복원 · 다음 주기에 재검증',stable_snapshot_recorded:'정상 실행 정책 저장',stable_sample_accumulating:'정상 실행 표본 축적 중',no_execution_sample:'주문 시도 표본 없음',compatible_stable_snapshot_required:'같은 버전의 정상 정책 근거 필요',no_safe_policy_change_available:'안전하게 복원할 설정 차이 없음',already_restored_recheck_required:'이미 복원됨 · 실행 상태 재확인 필요',cancelled_by_user:'사용자 취소',not_requested:'자동 복원 미사용',snapshot_integrity_failed:'정책 근거 무결성 확인 실패',recovery_storage_or_validation_failed:'정책 저장·검증 실패'} as Record<string,string>)[String(scoped.recovery.status)] ?? '회복 상태 확인 필요'}</p><small>{timeLabel(scoped.recovery.observed_at)}</small><p>사용자 저장 설정·위험 한도·LIVE 권한을 변경하지 않습니다. 복원은 거래 재개나 수익 회복을 보장하지 않습니다.</p>{scoped.recovery.status==='restored' && onCancelRecovery && <button disabled={recoveryBusy} onClick={()=>void cancelRecovery()}>{recoveryBusy?'취소 중…':'이번 실행 정책 복원 취소'}</button>}{recoveryError&&<p role="status">{recoveryError}</p>}</article>}
    {scoped?.orders?.requires_reconciliation && <article role="status"><h4>주문 접수·체결 대조 필요</h4><p>미확정 주문 {scoped.orders.pending_orders ?? '확인 중'}건. 이전 주문의 접수·체결 여부가 확인되기 전에는 같은 기관·종목의 추가 진입을 보류합니다.</p><p>거래 기록 점검·복구와 기관 주문 내역을 대조하세요. 앱 재시작이나 거래 기록 삭제로 해제하지 않습니다.</p>{onOpenFeature && <button onClick={()=>onOpenFeature('maintenance')}>유지관리 · 거래 기록 점검</button>}</article>}
    <article><h4>자동 종목 선정 근거</h4>{scoped?.selection ? <>
      <p>분석 후보 {scoped.selection.selected?.length ?? 0}개 · 선정 당시 자격 통과 {scoped.selection.eligible_count ?? 0}개</p>
      <small>{timeLabel(scoped.selection.observed_at)}{old(scoped.selection) ? ' · 오래된 선정 기록' : ''}</small>
      <p>후보 선정은 수익 추천이나 주문 승인이 아닙니다. 현재 시세·위험·주문 검사를 다시 통과해야 합니다. 고정 종목도 같은 검사를 받습니다.</p>
      {Array.isArray(scoped.selection.issues) && scoped.selection.issues.length > 0 && <p role="status">자료 확인 필요: {scoped.selection.issues.join(' · ')}</p>}
      <details><summary>후보·선정 이유·제외 목록</summary><ul>{(scoped.selection.selected ?? []).map((row:Record<string,any>) => <li key={String(row.symbol)}>{String(row.symbol)} · {row.score == null ? '점수 미산출' : `선정 점수 ${row.score}`} · {String(row.reason)} · {row.execution_eligible ? '선정 자격 통과' : '실행 보류'}</li>)}</ul><p>제외: {(scoped.selection.excluded ?? []).join(', ') || '제외 근거 미기록'}</p></details>
    </> : <p>선정 기록이 아직 없습니다. 기관 연결·종목 선택을 확인하고 다시 선정하세요. 빈 후보를 정상 운용으로 해석하지 않습니다.</p>}</article>
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
