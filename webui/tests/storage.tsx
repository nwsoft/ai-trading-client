// Real component and styles; all responses are simulated, no account or orders.
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { StorageMaintenancePanel } from '../src/components/StorageMaintenancePanel';
import { setLocale } from '../src/i18n';
import '../src/styles.css';
let status: any={state:'idle',log_bytes:530*1048576,log_budget_bytes:512*1048576,learning_bytes:156*1048576,db_bytes:2600*1048576,
  last_compression:null,debug_expires_at:0,log_budget_exceeded:true,decision_rows_checked:0,archived_rows:0,
  log_archive_bytes:32*1048576,contract_rejected_records:2,log_archive_error:'OSError'};
const client:any={storageMaintenance:async(action?:string,hours?:number)=>{
  if(action==='debug')status={...status,debug_expires_at:hours?Date.now()/1000+hours*3600:0};
  if(action==='optimize')status={...status,state:'complete',decision_rows_checked:2500000,archived_rows:63000,last_compression:new Date().toISOString(),
    log_bytes:200*1048576,log_archive_bytes:55*1048576,log_budget_exceeded:false,log_archive_error:null,last_log_compression:Date.now()/1000};
  return {...status};
}};
function QA(){const [lang,change]=useState('ko');return <main style={{maxWidth:800,margin:'0 auto',padding:16}}>
  <p>Offline UI QA · simulated data · no trading</p>
  <button onClick={()=>{const next=lang==='ko'?'en':'ko';setLocale(next);change(next);}}>한국어 / English</button>
  <StorageMaintenancePanel key={lang} client={client}/>
</main>}
createRoot(document.getElementById('root')!).render(<QA/>);
