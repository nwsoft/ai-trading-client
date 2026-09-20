// Isolated fixture: real Settings + maintenance components, simulated API only.
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { SettingsCenter } from '../src/components/SettingsCenter';
import { setLocale } from '../src/i18n';
import '../src/styles.css';

let result: Record<string, any> = {state:'idle',total:0,processed:0,recovered:0,remaining:0,reasons:{}};
let starts = 0;
const discovery = new URLSearchParams(location.search).has('discovery');
const client: any = {
  settings:async()=>({revision:'fixture',schema_version:'1',account_scope:'QA_ONLY',fields:[]}),
  settingsDiagnostics:async()=>({}),platform:async()=>({release_version:'3.9.1.43'}),assistantStatus:async()=>({}),
  recordRecovery:async(source: string, start: boolean)=>{
    if(start && discovery) {
      starts += 1;
      result = starts === 1
        ? {state:'paused',total:40,processed:0,recovered:0,remaining:40,reasons:{provider_history_collecting:1},history_pages:{complete:60,pending:4},backup_created:true}
        : {state:'checked',total:40,processed:40,recovered:40,remaining:0,reasons:{},history_pages:{complete:64,pending:0},backup_created:true,auto_started:false};
    } else if(start) result={state:'needs_evidence',total:40,processed:40,recovered:12,remaining:28,
      reasons:{missing_exit_order_evidence:28},backup_created:true,auto_started:false};
    return {...result,source};
  },
};
function QA() {
  const [open,setOpen]=useState(true),[lang,setLang]=useState('ko');
  return <><p>Offline QA · no account, API or order</p><button onClick={()=>{setLocale(lang==='ko'?'en':'ko');setLang(lang==='ko'?'en':'ko');}}>한국어 / English</button><button onClick={()=>setOpen(true)}>설정 열기</button><SettingsCenter client={client} open={open} onClose={()=>setOpen(false)} onAskAssistant={()=>{}} /></>;
}
createRoot(document.getElementById('root')!).render(<QA/>);
