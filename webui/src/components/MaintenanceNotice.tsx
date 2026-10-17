import {useEffect, useState} from 'react';
import type {GatewayClient} from '../api';

/** Read-only observer. Opening this notice never starts an engine or a job. */
export function MaintenanceNotice({client,onOpen}:{client:GatewayClient;onOpen:()=>void}) {
 const [status,setStatus]=useState<Record<string,any>|null>(null);
 const [unavailable,setUnavailable]=useState(false);
 useEffect(()=>{
  let alive=true;let timer:ReturnType<typeof setTimeout>;
  if(!client.reconciliation)return;
  const poll=async()=>{
   let delay=2000;
   try {const next=await client.reconciliation!();if(alive){setStatus(next);setUnavailable(false);}}
   catch {delay=5000;if(alive)setUnavailable(true);}
   if(alive)timer=setTimeout(poll,delay);
  };
  void poll();return()=>{alive=false;clearTimeout(timer);};
 },[client]);
 if(!client.reconciliation||(!unavailable&&(!status||status.state==='idle')))return null;
 const items=Array.isArray(status?.items)?status.items:[];
 const done=items.filter((row:any)=>row.state==='checked').length;
 const attention=items.filter((row:any)=>row.state==='needs_evidence').length;
 const labels:Record<string,string>={running:'백그라운드 대조 중',checked:'대조 완료',needs_evidence:'대조 후 확인 필요',paused:'대조 일시정지',interrupted:'앱 종료로 대조 중단 · 이어서 점검 필요',status_unavailable:'이전 대조 기록 확인 필요'};
 const label=unavailable?'대조 상태를 확인하지 못했습니다 · 연결 복구 후 다시 확인합니다':labels[String(status?.state)]??'대조 상태 확인 필요';
 const epoch=Number(status?.updated_at);
 const time=Number.isFinite(epoch)&&epoch>0?new Date(epoch*1000).toLocaleString():'';
 return <aside className="maintenance-notice" aria-label="백그라운드 대조 상태">
  <p role="status"><strong>{label}</strong>{!unavailable&&<> · {String(status?.mode??'').toUpperCase()} · 완료 {done}/{items.length}{attention>0?` · 확인 필요 ${attention}개`:''}</>}{time&&<> · 마지막 기록 {time}</>}</p>
  <button type="button" onClick={onOpen}>진행·결과 보기</button>
  {!unavailable&&status?.state==='checked'&&<small>표시 시점의 대조 결과입니다. 이후 거래는 다시 확인하며 거래를 새로 시작하지 않습니다. 이미 실행 중인 엔진은 다음 주기에 정상 조건을 재평가합니다.</small>}
  {!unavailable&&status?.state==='needs_evidence'&&<small>미해결 기관은 근거 확인이 필요합니다. 결과에서 기관별 사유를 확인하세요.</small>}
 </aside>;
}
