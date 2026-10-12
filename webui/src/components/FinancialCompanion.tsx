import {paperRecoveryGuide} from '../paperRecoveryGuide';
import {useEffect, useRef, useState, type FormEvent} from 'react';
import type {GatewayClient} from '../api';
import {ProductIntelligenceWorkspace} from './ProductIntelligenceWorkspace';
import {UserTime} from './UserTime';
import {CRYPTO_SOURCES, STOCK_SOURCES} from '../venueSources';
import './FinancialCompanion.css';

const destinations: Record<string, [string, string]> = {
  trading:['blockchain','blockchain.logs'], stock:['stock','stock.logs'],
  wealth:['portfolio','portfolio.plan'], portfolio:['portfolio','portfolio.insights'], market:['ai_analyst','ai_analyst.intelligence'],
  strategy:['blockchain','blockchain.ai_custom'], strategy_consultation:['blockchain','blockchain.ai_custom'], life:['personal_finance','personal_finance.service'], tax:['personal_finance','personal_finance.tax'],
};
const fresh: Record<string,string> = {recent:'최근 기록',stale:'이전 기록',expired:'기한 만료',unknown_time:'기준시각 미기록',future_time:'시각 확인 필요',unknown_expiry:'기한 미확인'};
const sections: Record<string,string> = {catalog:'상품 자료',finance:'생활금융 기록',market:'시장 자료',plans:'저장 계획',trading:'거래 진단','trading:blockchain':'코인 거래 진단','trading:stock':'증권 거래 진단'};
const actionLabels: Record<string,string> = {trading:'코인 거래 현황 열기',stock:'증권 거래 현황 열기',life:'생활금융에서 확인',market:'시장 자료 확인',portfolio:'통합 자산 확인'};
const quietStates = new Set(['engine_inactive','stopped','unobserved']);
function Evidence({value}:{value?:Record<string,any>}) {
  if(!value)return <p className="companion-evidence">근거 미수신</p>;
  return <details className="companion-evidence"><summary>{fresh[value.freshness]||'최신성 미확인'} · {({local_life_finance_records:'등록 생활금융 기록',saved_historical_replay:'저장 전략 재생',local_finance_discovery:'질문에서 확인한 조건',explicit_user_assumptions:'직접 입력한 가정',encrypted_saved_plan:'암호화 저장 계획'} as Record<string,string>)[value.source]||String(value.source||'출처 미기록')}</summary>
    <p>자료 종류: {({runtime_session:'현재 실행 세션',registered_records:'등록 생활금융 기록',registered_market_data:'저장 시장 자료',saved_plan:'저장 계획',live_account_cache:'LIVE 계좌 조회 캐시',user_question:'사용자 질문',scenario:'입력 가정',historical_replay:'과거 재생'} as Record<string,string>)[value.data_class]||'저장 관측'}</p>
    <p>자료 기준시각: <UserTime value={value.observed_at}/> · 유효기한: <UserTime value={value.valid_until}/></p>
    <p>계산 기준: {value.calculation_version||'미기록'}</p>
    <p>가정: {(value.assumptions||[]).join(' · ')||'추가 가정 미기록'}</p><p>미확인: {(value.unknowns||[]).join(' · ')||'전체 정확도·기관 실행은 별도 확인'}</p>
  </details>;
}

export function FinancialCompanion({client, service, onClose, onNavigate, onAsk, onStrategyDraft, onSettings}:{client:GatewayClient;service:string;onClose:()=>void;onNavigate:(service:string,feature:string,source?:string,question?:string)=>boolean|void;onAsk:(question:string,service:string)=>void;onStrategyDraft:(text:string,service:string)=>void;onSettings:()=>void}) {
  const [brief,setBrief]=useState<Record<string,any>|null>(null),[result,setResult]=useState<Record<string,any>|null>(null);
  const [question,setQuestion]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [view,setView]=useState<'brief'|'finance'|'allocation'|'experiment'>('brief');
  const [versions,setVersions]=useState<Record<string,any>[]>([]),[selected,setSelected]=useState({baseline:'',candidate:''}),[experiment,setExperiment]=useState<Record<string,any>|null>(null);
  const [finance,setFinance]=useState<{id:number;kind:'loan'|'savings'|'insurance';profile:Record<string,any>;question:string}|null>(null);
  const [voice,setVoice]=useState({enabled:false,auto_tts:false,lang:'ko-KR',rate:180}),[listening,setListening]=useState(false);
  const [voiceNotice,setVoiceNotice]=useState('');
  const [pendingVoice,setPendingVoice]=useState<{text:string;action:string;label:string}|null>(null);
  const [voiceRequest,setVoiceRequest]=useState<{id:number;action:'compare'|'revise'|'save';text:string}|null>(null);
  const voiceSequence=useRef(0),currentView=useRef(view);currentView.current=view;
  useEffect(()=>{setPendingVoice(null);recognition.current?.abort?.();setListening(false);},[view]);
  const [allocation,setAllocation]=useState({currency:'KRW',rows:[{symbol:'',before:'',after:''},{symbol:'',before:'',after:''}],total:'',fee:''});
  const [preview,setPreview]=useState<Record<string,any>|null>(null);
  const epoch=useRef(0),recognition=useRef<any>(null),dialogRef=useRef<HTMLElement>(null);
  useEffect(()=>{
    const trigger=document.activeElement instanceof HTMLElement?document.activeElement:null;
    dialogRef.current?.querySelector<HTMLElement>('#companion-title')?.focus();
    return()=>{if(trigger?.isConnected)trigger.focus();};
  },[]);
  async function refresh(){
    const token=++epoch.current;setBusy(true);setError('');
    try{
      if(!client.companionBriefing)throw new Error('이 실행 엔진에 금융비서 조회 기능이 없습니다. 앱 버전을 확인하세요.');
      const next=await client.companionBriefing();if(token===epoch.current){setBrief(next);setResult(null);}
    }catch(e){if(token===epoch.current)setError(e instanceof Error?e.message:'브리핑을 읽지 못했습니다.');}
    finally{if(token===epoch.current)setBusy(false);}
  }
  useEffect(()=>{
    void refresh();let alive=true;
    client.settings().then(snapshot=>{
      if(!alive)return;const field=snapshot.fields.find(f=>f.path==='assistant_voice');
      if(field?.value&&typeof field.value==='object'&&!Array.isArray(field.value)){
        const v=field.value as Record<string,any>;setVoice({enabled:v.enabled===true,auto_tts:v.auto_tts===true,lang:String(v.lang||'ko-KR'),rate:Number(v.rate)||180});
      }
    }).catch(()=>undefined);
    const locked=()=>{epoch.current++;setResult(null);setBrief(null);setPreview(null);setExperiment(null);setPendingVoice(null);setVoiceRequest(null);void refresh();};
    window.addEventListener('noah-finance-vault-locked',locked);
    return()=>{alive=false;epoch.current++;recognition.current?.abort?.();window.speechSynthesis?.cancel();window.removeEventListener('noah-finance-vault-locked',locked);};
  },[client]);
  function close(){
    if(finance&&!window.confirm('비교 화면에서 저장하지 않은 입력은 닫으면 사라집니다. 닫을까요?'))return;
    onClose();
  }
  useEffect(()=>{
    const key=(e:KeyboardEvent)=>{
      if(e.isComposing)return;
      if(e.key==='Escape'){e.preventDefault();close();return;}
      if(e.key!=='Tab')return;
      const dialog=dialogRef.current;if(!dialog)return;
      const controls=Array.from(dialog.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),a[href],summary,[tabindex="0"]')).filter(el=>el.getClientRects().length>0);
      const first=controls[0],last=controls.at(-1);if(!first||!last)return;
      if(!dialog.contains(document.activeElement)||document.activeElement===dialog.querySelector('#companion-title')){e.preventDefault();(e.shiftKey?last:first).focus();}
      else if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
      else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
    };
    window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);
  },[finance]);
  useEffect(()=>{if(result)dialogRef.current?.querySelector('.companion-answer')?.scrollIntoView({block:'nearest'});},[result]);
  async function ask(event:FormEvent){
    event.preventDefault();const prompt=question.trim();if(prompt.length<2||prompt.length>2000)return;
    const token=++epoch.current;setBusy(true);setError('');setResult(null);
    const shippedGuide=paperRecoveryGuide(prompt);if(shippedGuide){setResult({answer:'내장 사용법 안내 · 현재 계정 상태는 연결 후 확인\n\n'+shippedGuide,actions:[{id:'trading',label:'거래소 화면에서 확인'}]});setView('brief');setBusy(false);return;}
    try{
      if(!client.companionQuery)throw new Error('금융비서 질문 기능이 없습니다. 앱 버전을 확인하세요.');
      const next=await client.companionQuery(prompt,['blockchain','stock','portfolio','personal_finance','ai_analyst'].includes(service)?service:'blockchain');
      if(token!==epoch.current)return;setResult(next);setView('brief');
      if(voice.enabled&&voice.auto_tts&&'speechSynthesis' in window){
        window.speechSynthesis.cancel();const speech=new SpeechSynthesisUtterance(String(next.answer||''));speech.lang=voice.lang;speech.rate=Math.max(.5,Math.min(2,voice.rate/180));window.speechSynthesis.speak(speech);
      }
    }catch(e){if(token===epoch.current){const guide=paperRecoveryGuide(prompt);if(guide){setResult({answer:'앱 내부 연결 실패 · 내장 사용법 안내\n\n'+guide,actions:[{id:'trading',label:'거래소 화면에서 확인'}]});setView('brief');}setError((e instanceof Error?e.message:'질문을 확인하지 못했습니다.')+(guide?' 현재 실행 상태는 확인하지 못했습니다.':''));}}
    finally{if(token===epoch.current)setBusy(false);}
  }
  function follow(action:Record<string,any>){
    if(action.id==='allocation'){setView('allocation');setError('');return;}
    if(action.id==='finance'&&['loan','savings','insurance'].includes(action.kind)){
      if(finance&&!window.confirm('다른 비교를 열면 저장하지 않은 이전 비교 입력은 사라집니다. 계속할까요?'))return;
      setVoiceRequest(null);setPendingVoice(null);setFinance({id:++voiceSequence.current,kind:action.kind,profile:action.profile||{},question:action.question||question});setView('finance');return;
    }
    const target=destinations[action.id];if(!target)return;
    if(finance&&!window.confirm('다른 화면으로 이동하면 저장하지 않은 비교 입력은 사라집니다. 이동할까요?'))return;
    if(action.id==='strategy')onStrategyDraft(String(action.question||question),action.service==='stock'?'stock':'blockchain');
    else if(action.id==='strategy_consultation')onAsk(String(action.question||question),action.service==='stock'?'stock':'blockchain');
    else {
      const source=String(action.source||'').toLowerCase();
      const allowed=target[0]==='stock'?STOCK_SOURCES:target[0]==='blockchain'?CRYPTO_SOURCES:[];
      const opened=onNavigate(target[0],allowed.includes(source)?`${target[0]}.source_workspaces`:target[1],allowed.includes(source)?source:undefined,String(action.question||question));
      if(opened===false){setError(`${source.toUpperCase()}가 사용 기관으로 선택되지 않았습니다. 설정 열기에서 사용 기관을 확인하세요.`);return;}
    }
    onClose();
  }
  function voiceInput(){
    if(listening){recognition.current?.stop?.();return;}
    if(!voice.enabled){setVoiceNotice('설정 → AI 엔진/API에서 음성 도우미를 활성화하세요.');return;}
    const Recognition=(window as any).SpeechRecognition||(window as any).webkitSpeechRecognition;
    if(!Recognition){setVoiceNotice('현재 실행 환경은 음성 인식을 지원하지 않습니다. 질문을 직접 입력하세요.');return;}
    const current=new Recognition();recognition.current=current;current.lang=voice.lang;current.continuous=false;current.interimResults=false;
    current.onstart=()=>{setListening(true);setVoiceNotice('말씀하신 내용을 입력한 뒤 확인합니다.');};
    const startedView=view;
    current.onresult=(e:any)=>{
      if(recognition.current!==current||currentView.current!==startedView)return;
      const text=String(e.results?.[0]?.[0]?.transcript||'').slice(0,2000),compact=text.replace(/\s+/g,'');
      if(/취소|하지마|하지말|말아|안할|안해|않/.test(compact)){setPendingVoice(null);setVoiceNotice('음성 명령을 취소했습니다. 저장·계산·이동을 실행하지 않았습니다.');return;}
      if(/배분미리보기.*(열|이동)/.test(compact))setPendingVoice({text,action:'allocation',label:'배분 미리보기 열기'});
      else if(/전략실험비교.*(열|이동)/.test(compact))setPendingVoice({text,action:'experiment',label:'저장 전략 실험 비교 열기'});
      else if(/자산화면.*(열|이동)/.test(compact))setPendingVoice({text,action:'portfolio',label:'자산 화면으로 이동'});
      else if(/비교화면.*(열|이동)/.test(compact)&&result?.actions?.some((a:Record<string,any>)=>a.id==='finance'))setPendingVoice({text,action:'finance',label:'질문 조건으로 비교 화면 열기'});
      else if(startedView==='finance'&&finance){
        const save=/계획.*저장/.test(compact),compare=/^(현재)?조건(을)?비교/.test(compact);
        setPendingVoice({text,action:save?'save':compare?'compare':'revise',label:save?'현재 계획 암호화 저장':compare?'현재 조건 비교':'조건 수정·재계산'});
      }else{setPendingVoice(null);setQuestion(text);}
      setVoiceNotice('인식한 금액·기간을 확인하고 질문 확인 또는 명령 확인을 누르세요.');
    };
    current.onerror=(e:any)=>setVoiceNotice(`마이크 권한·음성 연결을 확인하세요: ${String(e.error||'인식 실패')}`);
    current.onend=()=>setListening(false);
    try{current.start();}catch{setListening(false);setVoiceNotice('음성 인식을 시작하지 못했습니다. 권한과 실행 환경을 확인하세요.');}
  }
  function confirmVoice(){
    const pending=pendingVoice;if(!pending)return;setPendingVoice(null);
    if(['compare','revise','save'].includes(pending.action)){
      if(view!=='finance'||!finance){setError('먼저 비교 화면을 열어 조건을 확인하세요.');return;}
      setVoiceRequest({id:++voiceSequence.current,action:pending.action as 'compare'|'revise'|'save',text:pending.text});
    }else if(pending.action==='experiment')void loadExperiments();
    else if(pending.action==='finance'){
      const targets=(result?.actions||[]).filter((a:Record<string,any>)=>a.id==='finance');
      if(targets.length!==1){setError('여러 비교 목적 중 하나를 먼저 선택하세요.');return;}follow(targets[0]);
    }else follow({id:pending.action});
  }
  async function simulate(event:FormEvent){
    event.preventDefault();setError('');setPreview(null);const token=++epoch.current;
    const rows=allocation.rows.map(row=>{if(!row.symbol.trim()||!row.before.trim()||!row.after.trim())throw new Error('각 종목의 이름·현재 비중·바꿀 비중을 입력하세요.');return {symbol:row.symbol.trim(),before:Number(row.before),after:Number(row.after)};});
    setBusy(true);
    try{
      if(!client.companionAllocation)throw new Error('배분 미리보기 기능이 없습니다.');
      const next=await client.companionAllocation({currency:allocation.currency,rows,total_value:allocation.total.trim()?Number(allocation.total):null,fee_bps:allocation.fee.trim()?Number(allocation.fee):null});
      if(token===epoch.current)setPreview(next);
    }catch(e){if(token===epoch.current)setError(e instanceof Error?e.message:'비중·통화·입력값을 확인하세요.');}
    finally{if(token===epoch.current)setBusy(false);}
  }
  async function loadExperiments(){
    setView('experiment');const token=++epoch.current;setBusy(true);setError('');setExperiment(null);setSelected({baseline:'',candidate:''});setVersions([]);
    try{if(!client.companionExperiments)throw new Error('전략 실험 기능이 없습니다.');const next=await client.companionExperiments();if(token===epoch.current)setVersions(next.versions||[]);}
    catch(e){if(token===epoch.current)setError(e instanceof Error?e.message:'저장 검증을 읽지 못했습니다.');}finally{if(token===epoch.current)setBusy(false);}
  }
  async function compareExperiments(event:FormEvent){
    event.preventDefault();const token=++epoch.current;setBusy(true);setError('');setExperiment(null);
    const ref=(id:string)=>{const v=versions[Number(id)];return {scope:v.scope,strategy_key:v.strategy_key,version_id:v.version_id};};
    try{if(!client.companionExperimentCompare)throw new Error('전략 실험 비교 기능이 없습니다.');const next=await client.companionExperimentCompare(ref(selected.baseline),ref(selected.candidate));if(token===epoch.current)setExperiment(next);}
    catch(e){if(token===epoch.current)setError(e instanceof Error?e.message:'검증 결과를 비교하지 못했습니다.');}finally{if(token===epoch.current)setBusy(false);}
  }
  const cards=Array.isArray(result?.cards)?result.cards:Array.isArray(brief?.cards)?brief.cards:[];
  const quietCards=result?[]:cards.filter(card=>card.section==='trading'&&quietStates.has(card.state));
  const visibleCards=cards.filter(card=>!quietCards.includes(card));
  const selectPrompt=(prompt:string)=>{setQuestion(prompt);dialogRef.current?.querySelector<HTMLTextAreaElement>('#companion-question')?.focus();};
  const updateAllocationRow=(index:number,key:'symbol'|'before'|'after',value:string)=>{
    setPreview(null);setAllocation(current=>({...current,rows:current.rows.map((row,i)=>i===index?{...row,[key]:value}:row)}));
  };
  const renderCard=(card:Record<string,any>)=><article key={card.id}>
    <h4>{String(card.title||'확인할 항목').replace(/\bUNKNOWN\b/gi,'거래 모드 미확인')}</h4>
    <p>{String(card.detail||'').length>350?String(card.detail).split('\n').slice(0,2).join('\n'):card.detail}</p>
    {String(card.detail||'').length>350&&<details className="companion-evidence"><summary>기록별 상세 보기</summary><p>{card.detail}</p></details>}
    <p className="companion-next"><b>다음 확인</b> {card.next}</p>
    <Evidence value={card.evidence}/>{(card.holding_evidence||[]).map((proof:Record<string,any>,i:number)=><Evidence key={i} value={proof}/>)}
    {card.action&&<button type="button" onClick={()=>follow({id:card.action,source:card.source})}>{card.source?`${String(card.source).toUpperCase()} 상세 확인`:actionLabels[card.action]||'확인 화면 열기'}</button>}
  </article>;
  return <div className="modal-backdrop" role="presentation"><section ref={dialogRef} id="financial-companion-dialog" role="dialog" aria-modal="true" aria-labelledby="companion-title" aria-describedby="companion-description" className="companion-modal">
    <header><div><h2 id="companion-title" tabIndex={-1}>내 금융비서</h2><p id="companion-description">거래가 없는 이유를 확인하고, 금융 조건을 비교하고, 자산·전략을 점검하세요.</p></div><button type="button" onClick={close} aria-label="금융비서 닫기">× 닫기</button></header>
    <nav aria-label="금융비서 업무">
      <button type="button" className={view==='brief'?'active':''} aria-pressed={view==='brief'} onClick={()=>setView('brief')}>질문·내 상태</button>
      <button type="button" className={view==='allocation'?'active':''} aria-pressed={view==='allocation'} onClick={()=>{setView('allocation');setError('');}}>자산 비중 바꿔보기</button>
      <button type="button" className={view==='experiment'?'active':''} aria-pressed={view==='experiment'} disabled={busy} onClick={()=>void loadExperiments()}>저장된 전략 비교</button>
      {finance&&<button type="button" className={view==='finance'?'active':''} aria-pressed={view==='finance'} onClick={()=>setView('finance')}>진행 중인 비교</button>}
      <button type="button" className="companion-refresh" disabled={busy} onClick={()=>void refresh()}>내 상태 새로고침</button>
    </nav>
    <div className="companion-body"><div className="companion-voice-task">{view!=='brief'&&<button type="button" onClick={voiceInput}>{listening?'듣기 중지':'음성으로 업무 이어가기'}</button>}{voiceNotice&&<p role="status">{voiceNotice}</p>}{pendingVoice&&<aside><p>인식한 명령: {pendingVoice.text}</p><p>다음 행동: {pendingVoice.label}. 현재 금액·기간·보장 조건을 확인하세요.</p><button type="button" disabled={busy} onClick={confirmVoice}>명령 확인 · {pendingVoice.label}</button><button type="button" onClick={()=>setPendingVoice(null)}>명령 취소</button></aside>}</div>
      {error&&<p role="alert" className="error-text">{error} 마지막 근거가 남아 있으면 현재 상태로 확정하지 마세요.</p>}
      <div hidden={view!=='brief'}>
        <section className="companion-start" aria-labelledby="companion-start-title"><h3 id="companion-start-title">처음이라면, 궁금한 것 하나부터 물어보세요</h3><ol className="companion-steps"><li><b>1. 질문하기</b><span>예시를 고르거나 직접 입력</span></li><li><b>2. 이유 확인</b><span>답변과 사용한 자료 확인</span></li><li><b>3. 다음 화면으로</b><span>안내된 화면에서 검토·진행</span></li></ol>
        <div className="companion-prompts" aria-label="질문 예시">{['왜 거래가 없지?','보험이 없는데 무엇부터 볼까?','월 부담을 줄여줘','내 종목 관련 뉴스만 보여줘','손절 조건을 바꿔 비교하고 싶어','만기·갱신·재확인 항목 알려줘','내 돈 계획을 세우고 싶어'].map(prompt=><button key={prompt} type="button" onClick={()=>selectPrompt(prompt)}>{prompt}</button>)}</div>
        <form onSubmit={ask} className="companion-question"><label htmlFor="companion-question">무엇을 확인할까요?</label><textarea id="companion-question" aria-describedby="companion-question-help" maxLength={2000} value={question} onChange={e=>setQuestion(e.target.value)} placeholder="예: OKX에서 왜 거래가 안 되는지 알려줘" /><p id="companion-question-help">예시를 선택하면 질문이 입력됩니다. 내용을 확인한 뒤 ‘질문 확인’을 누르세요.</p><div><button className="companion-primary" disabled={busy||question.trim().length<2} type="submit">{busy?'확인 중…':'질문 확인'}</button><button type="button" onClick={voiceInput}>{listening?'듣기 중지':'음성으로 질문'}</button><button type="button" onClick={()=>{if(!finance||window.confirm("설정으로 이동하면 저장하지 않은 비교 입력은 사라집니다. 이동할까요?"))onSettings();}}>설정 열기</button></div></form></section>
        {result&&<article className="companion-answer" aria-label="질문 답변"><h3>질문에 대한 답변</h3><p>{result.answer}</p>{result.evidence?<Evidence value={result.evidence}/>:result.cards?.length>0?<p className="companion-evidence">아래 항목별 출처·기준시각을 확인하세요.</p>:null}<div>{(result.actions||[]).map((a:Record<string,any>,i:number)=><button type="button" key={`${a.id}-${i}`} onClick={()=>follow(a)}>{a.kind?`${{loan:'대출',insurance:'보험',savings:'예적금'}[a.kind as 'loan'|'insurance'|'savings']} · `:''}{a.label}</button>)}</div></article>}
        {!brief&&!busy&&!error&&<p>저장 근거가 없습니다. 연결·기록을 먼저 확인하세요.</p>}
        {busy&&<p role="status">저장된 근거를 확인하고 있습니다.</p>}
        {brief&&<section aria-labelledby="companion-status-title"><div className="companion-status-heading"><h3 id="companion-status-title">{result?'답변에 사용한 항목':'앱 기록으로 확인한 내 상태'}</h3><span className="companion-boundary">마지막 확인 <UserTime value={brief.captured_at}/></span></div>
          {brief.unavailable_sections?.length>0&&<p role="status" className="companion-unavailable">확인하지 못한 영역: {brief.unavailable_sections.map((name:string)=>sections[name]||'조회 영역').join(' · ')}. 자료를 읽지 못해 현재 상태를 판단할 수 없습니다.</p>}
          {!cards.length&&<p className="companion-empty">아직 표시할 기록이 없습니다. 위에서 질문하거나 생활금융에 기록을 등록하면 관련 내용을 확인할 수 있습니다.</p>}
          <div className="companion-cards">{visibleCards.map(renderCard)}</div>
          {quietCards.length>0&&<details className="companion-quiet"><summary>거래 기록이 없거나 정지된 기관 {quietCards.length}곳 · 펼쳐서 확인</summary><p>아직 판단 기록을 받지 못했거나 거래가 정지된 기관입니다. ‘정상’이나 ‘거래 오류’로 단정하지 않습니다. 기관별 상태와 다음 확인 방법을 아래에서 확인하세요.</p><div className="companion-cards">{quietCards.map(renderCard)}</div></details>}
          <details className="companion-data-guide"><summary>어떤 자료를 사용하나요? · 보관함 {brief.vault_state==='unlocked'?'열림':brief.vault_state==='unavailable'?'조회 불가':'잠김'}</summary><p>{brief.notice}</p><p>잠긴 보관함의 보험·계획 내용은 읽지 않습니다. 생활금융에서 보관함을 열고 이 창을 새로고침하세요.</p><p>{brief.catalog_coverage?.basis} · 탐색 자료 {brief.catalog_coverage?.reference_count??'미확인'}개 / 기관 {brief.catalog_coverage?.providers??'미확인'}개</p><p>마지막 확인은 이 화면을 조회한 시각입니다. 개별 자료의 기준시각은 각 항목을 펼쳐 확인하세요. 시각에 마우스를 올리면 원본 UTC를 볼 수 있습니다.</p></details>
        </section>}
      </div>
      {finance&&<div hidden={view!=='finance'}><p>질문에서 가져온 조건의 검토 초안입니다. 금액·기간·목적을 확인하고 비교·저장·상담을 각각 진행하세요.</p><ProductIntelligenceWorkspace key={finance.id} client={client} kind={finance.kind} initialProfile={finance.profile} initialQuestion={finance.question} voiceRequest={voiceRequest}/></div>}
      <div hidden={view!=='allocation'}><h3>자산 비중을 바꾸면 어떻게 달라질까요?</h3><p>같은 통화의 종목과 비중을 입력하면 변경 전후를 비교합니다. 예를 들어 BTC 80%·ETH 20%를 50%·50%로 바꿀 때의 집중도와 입력 비용을 확인할 수 있습니다. 실제 잔액을 가져오거나 주문하지 않습니다.</p><form onSubmit={event=>{void simulate(event).catch(e=>setError(e instanceof Error?e.message:'입력을 확인하세요.'));}} className="companion-allocation">
        <label>통화<select aria-label="통화" value={allocation.currency} onChange={e=>{setPreview(null);setAllocation({...allocation,currency:e.target.value});}}>{['KRW','USD','USDT','EUR','JPY'].map(c=><option key={c}>{c}</option>)}</select></label>
        <div className="companion-weight-rows"><div className="companion-weight-heading"><span>종목</span><span>현재 비중 (%)</span><span>바꿀 비중 (%)</span><span/></div>{allocation.rows.map((row,index)=><div className="companion-weight-row" key={index}><input aria-label={`종목 ${index+1}`} placeholder={index===0?'예: BTC':'예: ETH'} required maxLength={40} value={row.symbol} onChange={e=>updateAllocationRow(index,'symbol',e.target.value)}/><input aria-label={`현재 비중 ${index+1}`} type="number" min="0" max="100" step="any" required value={row.before} onChange={e=>updateAllocationRow(index,'before',e.target.value)}/><input aria-label={`바꿀 비중 ${index+1}`} type="number" min="0" max="100" step="any" required value={row.after} onChange={e=>updateAllocationRow(index,'after',e.target.value)}/><button type="button" aria-label={`종목 ${index+1} 삭제`} disabled={allocation.rows.length<=1} onClick={()=>{setPreview(null);setAllocation({...allocation,rows:allocation.rows.filter((_,i)=>i!==index)});}}>삭제</button></div>)}<button type="button" disabled={allocation.rows.length>=20} onClick={()=>{setPreview(null);setAllocation({...allocation,rows:[...allocation.rows,{symbol:'',before:'',after:''}]});}}>종목 추가</button><p>현재 비중과 바꿀 비중의 합계가 각각 100%여야 합니다. 통화가 다른 자산은 나누어 비교하세요.</p></div>
        <label>총 가치 (선택)<input type="number" min="0" value={allocation.total} onChange={e=>{setPreview(null);setAllocation({...allocation,total:e.target.value});}}/></label><label>매수·매도 각각 수수료 bps (선택 · 1bps=0.01%)<input type="number" step="any" min="0" value={allocation.fee} onChange={e=>{setPreview(null);setAllocation({...allocation,fee:e.target.value});}}/></label><button className="companion-primary" disabled={busy} type="submit">가정 비교</button>
      </form>{preview&&<article className="companion-preview"><h3>입력한 비중의 비교 결과</h3><p>집중도 HHI: {Number(preview.before_hhi).toFixed(3)} → {Number(preview.after_hhi).toFixed(3)} · 매수+매도 회전율: {Number(preview.turnover_percent).toLocaleString(undefined,{maximumFractionDigits:2})}%</p><p>집중도는 1에 가까울수록 일부 종목에 비중이 몰렸다는 뜻입니다. 수익·손실을 예측하는 점수는 아닙니다.</p><p>입력 가정 비용: {preview.estimated_cost===null?'계산 전 · 총 가치/비용 근거 미입력':`${preview.estimated_cost} ${preview.currency}`}</p><table><thead><tr><th>종목</th><th>현재 %</th><th>목표 %</th><th>차이 %p</th><th>금액 ({preview.currency})</th></tr></thead><tbody>{preview.rows.map((r:Record<string,any>)=><tr key={r.symbol}><th>{r.symbol}</th><td>{r.before}</td><td>{r.after}</td><td>{r.delta_percent}</td><td>{r.delta_value===null?'계산 전':r.delta_value}</td></tr>)}</tbody></table><Evidence value={preview.evidence}/><button type="button" onClick={()=>follow({id:'portfolio'})}>자산 화면에서 현재 자료 확인</button></article>}</div>
      <div hidden={view!=='experiment'}><h3>전략을 바꾸기 전에 저장 결과부터 비교하세요</h3><p>원본은 현재 비교 기준인 전략, 후보는 조건을 바꾼 별도 전략입니다. 전략 스튜디오에서 두 전략을 같은 시세·기간·시간봉·비용으로 검증한 뒤 아래에서 선택하세요. 여기서는 저장 결과만 비교하며 새 검증이나 전략 적용을 실행하지 않습니다.</p>{!busy&&versions.length===0&&<aside className="companion-empty"><p>아직 비교할 저장 검증이 없습니다.</p><p>전략 스튜디오에서 원본과 별도 후보를 검토하고 같은 조건으로 검증·저장한 뒤 돌아오세요.</p><button type="button" onClick={()=>follow({id:'strategy',service:service==='stock'?'stock':'blockchain',question:'원본과 별도 후보의 검증 조건을 확인하고 싶습니다.'})}>전략 스튜디오에서 준비하기</button></aside>}<form className="companion-experiment" onSubmit={compareExperiments}>{(['baseline','candidate'] as const).map(key=><label key={key}>{key==='baseline'?'원본':'후보'}<select aria-label={key==='baseline'?'원본':'후보'} value={selected[key]} onChange={e=>{setExperiment(null);setSelected({...selected,[key]:e.target.value});}}><option value="">버전 선택</option>{versions.map((v,i)=><option key={`${v.scope}:${v.strategy_key}:${v.version_id}`} value={i}>{v.name} · {v.version_id} · {v.mode==='historical_replay'?'과거 재생':v.mode==='paper'?'PAPER':'미검증'}</option>)}</select></label>)}<button disabled={busy||!selected.baseline||!selected.candidate||selected.baseline===selected.candidate} type="submit">저장 결과 대조</button></form>{experiment&&<article className="companion-preview"><p role="status">{experiment.reason}</p>{experiment.comparable&&<table><thead><tr><th>항목</th><th>원본</th><th>후보</th><th>차이</th></tr></thead><tbody>{experiment.metrics.map((r:Record<string,any>)=><tr key={r.key}><th>{r.label}</th><td>{r.before??'미기록'}</td><td>{r.after??'미기록'}</td><td>{r.delta??'계산 전'}</td></tr>)}</tbody></table>}<Evidence value={experiment.evidence}/></article>}</div>
    </div>
  </section></div>;
}
