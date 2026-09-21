// Isolated real-component QA. No exchange, account credentials or orders.
import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {RecordRecoveryPanel} from '../src/components/RecordRecoveryPanel';
import {ExecutionEvidenceNote, executionEvidenceCount} from '../src/components/ExecutionEvidenceNote';
import {setLocale, localized} from '../src/i18n';
import '../src/styles.css';
let started = 0;
let commands = 0;
const client: any = {recordRecovery: async (_source: string, start: boolean) => {
  if(start) {started=Date.now();commands++;}
  const done=started>0 && Date.now()-started>4000;
  return {state:!started?'idle':done?'checked':'running',total:10,processed:done?10:0,recovered:done?10:0,remaining:done?0:10,
    reasons:{},background_continuation:true,backup_created:!!started,history_pages:started?{complete:done?44:40,pending:done?0:4}:{}};
}};
function QA() {
  const [show,setShow]=useState(true),[locale,changeLocale]=useState('ko');
  return <main style={{maxWidth:900,margin:'auto',padding:16}}>
    <p>Offline QA · v44 · no API / orders · commands: {commands}</p>
    <button onClick={()=>{const next=locale==='ko'?'en':'ko';setLocale(next);changeLocale(next);}}>한국어 / English</button>
    <button onClick={()=>setShow(!show)}>{show?'점검 화면 닫기':'점검 화면 열기'}</button>
    {show && <RecordRecoveryPanel client={client}/>}
    <h3>{localized('NoahAI 완료 거래 3건','NoahAI completed trades: 3')}</h3>
    <p>{localized('거래소 체결 기록','Exchange fill records')}: {executionEvidenceCount(7,'stored_only')}</p>
    <ExecutionEvidenceNote status="stored_only" count={7} rows={Array.from({length:7},(_,i)=>({id:i,exchange:'binance',symbol:'TESTUSDT',side:i%2?'sell':'buy',quantity:1,order_id:`TEST-ORDER-${i}`,trade_id:`TEST-FILL-${i}`,executed_at:'2026-09-21 10:00:00'}))}/>
  </main>;
}
createRoot(document.getElementById('root')!).render(<QA/>);
