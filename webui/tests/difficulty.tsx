// Isolated UI fixture. No account, engine, network or order API is connected.
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { SettingsCenter } from '../src/components/SettingsCenter';
import { StrategyStudio } from '../src/components/StrategyStudio';
import { setLocale } from '../src/i18n';
import '../src/styles.css';

let profile = 'standard';
const snapshot = () => ({revision:'fixture', save_receipt:{verified:true}, schema_version:'1', account_scope:'QA_ONLY', fields:[
  {path:'ai_custom_features.profile',label:'전략 스튜디오 사용 난이도',help:'화면 복잡도만 변경합니다. 변경 후 저장하세요.',section:'ai_engine',kind:'select',presentation:'primary',risk:'low',options:['beginner','standard','advanced','lab','research'],value:profile,default_value:'standard'},
]});
const client: any = {
  settings:async()=>snapshot(), settingsDiagnostics:async()=>({}), platform:async()=>({release_version:'3.9.1.43'}), assistantStatus:async()=>({}),
  strategies:async()=>({strategies:[],scopes:[]}),
  updateSettings:async(_revision: string,changes: Record<string,unknown>)=>{profile=String(changes['ai_custom_features.profile']??profile);return snapshot();},
};
function QA() {
  const [open,setOpen]=useState(false), [revision,setRevision]=useState(0), [service,setService]=useState<'blockchain'|'stock'>('blockchain');
  return <><p>QA fixture · no real account or trading</p><button onClick={()=>{setLocale('ko');setRevision(v=>v+1);}}>한국어</button><button onClick={()=>{setLocale('en');setRevision(v=>v+1);}}>English</button><button onClick={()=>setService(service==='stock'?'blockchain':'stock')}>코인/주식 전환</button><StrategyStudio client={client} service={service} settingsRevision={revision} onOpenDifficultySettings={()=>setOpen(true)} /><SettingsCenter client={client} open={open} initialField="ai_custom_features.profile" onClose={()=>setOpen(false)} onAskAssistant={()=>{}} onSettingsSaved={()=>setRevision(v=>v+1)} /></>;
}
createRoot(document.getElementById('root')!).render(<QA/>);
