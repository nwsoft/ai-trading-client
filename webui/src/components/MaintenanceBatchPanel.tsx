import {useEffect,useState} from 'react';
import type {GatewayClient} from '../api';
import {CRYPTO_SOURCES,STOCK_SOURCES} from '../venueSources';

const labels:Record<string,string>={idle:'점검 전',queued:'대기',running:'백그라운드 점검 중',checked:'대조 완료',paused:'일시정지 · 이어서 실행 가능',interrupted:'중단됨 · 이어서 실행 가능',needs_evidence:'대조 근거 확인 필요',status_unavailable:'이전 진행 정보 확인 필요'};
export function MaintenanceBatchPanel({client}:{client:GatewayClient}){
 const [mode,setMode]=useState<'paper'|'live'>('paper'),[selected,setSelected]=useState<string[]>([]),[status,setStatus]=useState<Record<string,any>|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{let alive=true;let timer:ReturnType<typeof setTimeout>;const poll=async()=>{try{const next=await client.reconciliation?.();if(alive&&next)setStatus(next);}catch{if(alive)setError('대조 진행 상태를 불러오지 못했습니다. 다시 확인하세요.');}if(alive)timer=setTimeout(poll,2000);};void poll();return()=>{alive=false;clearTimeout(timer);};},[client]);
 if(!client.reconciliation)return null;
 const sources=mode==='paper'?CRYPTO_SOURCES:[...CRYPTO_SOURCES,...STOCK_SOURCES];
 const running=status?.state==='running';
 async function run(action:'start'|'resume'|'cancel'){
  if(action==='start'&&!selected.length)return;
  const effectiveMode=action==='resume'?status?.mode:mode;
  if(effectiveMode==='live'&&action!=='cancel'&&!window.confirm('선택 기관의 LIVE 미확정 거래를 공식 내역과 대조합니다. 이미 운용 중인 엔진은 복구된 기록으로 다음 판단을 할 수 있습니다. 새 거래를 원하지 않으면 먼저 신규 진입을 일시정지하세요. 주문 제출·취소는 하지 않습니다.'))return;
  setBusy(true);setError('');try{const next=await client.reconciliation?.(action==='cancel'?{action}:{action,mode:action==='resume'?status?.mode:mode,sources:action==='resume'?(status?.items??[]).map((r:any)=>r.source):selected});if(next)setStatus(next);}catch(e){setError(e instanceof Error?e.message:'대조 요청에 실패했습니다.');}finally{setBusy(false);}
 }
 return <section className="settings-parity-panel" aria-label="PAPER 자금 대조와 기관 일괄 점검"><h3>PAPER 자금 대조 · 기관 일괄 점검</h3>
 <p>PAPER는 로컬 가상 원장·청산·보유량을 대조합니다. 기록이 많아도 나눠 처리하며 원본·과거 손익·전략을 초기화하지 않습니다. 실행 후 화면을 닫아도 앱이 켜져 있으면 계속합니다.</p>
 <p>LIVE는 실제 체결 근거가 부족한 거래를 기관 내역과 비교하는 별도 작업입니다. 모든 기관은 순서대로 처리하고 각 결과를 표시합니다. 완료가 거래 시작이나 수익 보장을 뜻하지 않습니다.</p>
 <label>점검 대상 <select aria-label="대조 모드" value={mode} disabled={busy||running} onChange={e=>{setMode(e.target.value as 'paper'|'live');setSelected([]);}}><option value="paper">PAPER 가상 자금·보유량</option><option value="live">LIVE 거래기록 복구</option></select></label>
 <button type="button" disabled={busy||running} onClick={()=>setSelected([...sources])}>현재 모드 전체 기관 선택</button><button type="button" disabled={busy||running} onClick={()=>setSelected([])}>선택 해제</button>
 <fieldset disabled={busy||running}><legend>점검할 기관 선택</legend>{sources.map(s=><label key={s}><input type="checkbox" checked={selected.includes(s)} onChange={e=>setSelected(e.target.checked?[...selected,s]:selected.filter(v=>v!==s))}/>{s.toUpperCase()}</label>)}</fieldset>
 <button type="button" disabled={busy||running||!selected.length} onClick={()=>void run('start')}>선택 {selected.length}개 백그라운드 점검</button>
 {running&&<button type="button" disabled={busy} onClick={()=>void run('cancel')}>남은 작업 일시정지</button>}
 {['paused','interrupted','needs_evidence'].includes(status?.state)&&<button type="button" disabled={busy} onClick={()=>void run('resume')}>이전 선택 이어서 점검</button>}
 <p role="status">{labels[status?.state]??'점검 전'}{status?.mode?` · ${String(status.mode).toUpperCase()}`:''}</p>
 {status?.updated_at&&<p>마지막 점검 기록: {new Date(Number(status.updated_at)*1000).toLocaleString()} · 이후 기록은 다음 점검에서 확인합니다.</p>}
 {error&&<p role="alert">{error}</p>}
 {(status?.items??[]).map((row:any)=><p key={row.source}><strong>{String(row.source).toUpperCase()}</strong> · {labels[row.state]??row.state}{row.total_bytes!=null?` · ${(Number(row.processed_bytes??0)/1048576).toFixed(1)} / ${(Number(row.total_bytes)/1048576).toFixed(1)} MiB`:''}{row.reason?` · ${client.reconciliationReason?.(row.reason)??row.reason}`:''}</p>)}
 <p>원장이 손상되었거나 근거가 부족하면 해당 기관을 보류합니다. 파일 삭제·전략 재등록으로 우회하지 마세요. 기존 운용은 대조 후 다음 주기에 재평가할 수 있으며, 결과 검토 전 새 진입을 원하지 않으면 신규 진입을 일시정지하세요.</p></section>;
}
