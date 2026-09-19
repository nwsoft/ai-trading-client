import { useEffect, useRef, useState } from 'react';
import type { GatewayClient } from '../api';

export function RemoteMonitorSettings({client}: {client: GatewayClient}) {
  const [state,setState]=useState<Record<string,any>|null>(null);
  const [name,setName]=useState('내 NoahAI PC');
  const [allowPause,setAllowPause]=useState(false);
  const initialized=useRef(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  useEffect(()=>{let active=true;const refresh=()=>client.remoteStatus().then(s=>{if(active){setState(s);if(!initialized.current){setName(s.name);setAllowPause(s.allow_pause===true);initialized.current=true}}}).catch(()=>{if(active)setError('연결 설정을 불러오지 못했습니다.')});void refresh();const timer=setInterval(refresh,15000);return()=>{active=false;clearInterval(timer)}},[client]);
  async function save(enabled:boolean){setBusy(true);setError('');try{setState(await client.configureRemote(enabled,name,allowPause))}catch{setError('저장하지 못했습니다. 로그인 상태와 PC 이름을 확인하세요.')}finally{setBusy(false)}}
  return <article className="remote-monitor-settings"><h3>원격 관리 · 내 PC 상태 공유</h3><p>daltrading에 로그인하면 모바일에서 기관별 실행 상태와 PAPER/LIVE 모드를 확인할 수 있습니다. API 키·전략 원문·손익 상세는 전송하지 않습니다.</p><label>PC 이름 <input maxLength={60} value={name} onChange={e=>setName(e.target.value)} /></label><label><input type="checkbox" checked={allowPause} onChange={e=>setAllowPause(e.target.checked)} /> 모바일에서 신규 주문 제출 일시정지 허용</label><p>설정 변경 후 아래 저장 버튼을 누르세요. 이미 제출된 주문은 체결될 수 있으며 기존 포지션의 보호·청산 처리는 유지됩니다. 재개는 PC에서만 가능합니다.</p><div className="notification-actions"><button type="button" disabled={busy||!state} onClick={()=>void save(!state?.enabled)}>{state?.enabled?'상태 공유 끄기':'상태 공유에 동의하고 연결'}</button>{state?.enabled && <button type="button" disabled={busy} onClick={()=>void save(true)}>원격 권한 저장</button>}<a href="https://daltrading.net/remote" target="_blank" rel="noopener noreferrer">모바일 대시보드 열기</a></div><p role="status">{error||state?.error||(state?.enabled?'상태 공유 켜짐':'상태 공유 꺼짐')}{state?.last_sent?` · 마지막 전송 ${new Date(state.last_sent*1000).toLocaleString()}`:''}</p><div>{Object.keys(state?.entry_pauses||{}).map(source=><p key={source}>{source.toUpperCase()} 신규 진입 {state?.entry_pauses[source]?.status==='draining'?'정지 요청 · 처리 중 주문 확인 중':'일시정지'} <button type="button" disabled={busy} onClick={async()=>{if(!window.confirm(`${source.toUpperCase()} 신규 진입을 다시 허용할까요? 현재 PC의 전략·모드·한도로 동작합니다.`))return;setBusy(true);try{await client.resumeEntries(source);setState(await client.remoteStatus())}catch{setError('재개하지 못했습니다.')}finally{setBusy(false)}}}>PC에서 신규 진입 재개</button></p>)}</div><small>원격 거래 시작·전량 청산은 제공하지 않습니다. PC가 꺼지거나 절전 상태면 마지막 확인 정보만 표시됩니다. 공유를 끄면 전송이 중단되며 웹의 마지막 상태는 최대 3분 뒤 오프라인으로 바뀝니다. 웹에서 ‘연결 해제’하면 저장된 상태도 제거됩니다.</small></article>
}
