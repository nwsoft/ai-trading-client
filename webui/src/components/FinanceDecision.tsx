import {useEffect,useRef,useState} from 'react';
import type {GatewayClient} from '../api';

export function FinanceDecision({client,kind,question,contextKey,onApply,onOpenAISettings,settingsRevision=0}:{client:GatewayClient;kind:string;question:string;contextKey:string;onApply:(change:Record<string,string>)=>void;onOpenAISettings?:()=>void;settingsRevision?:number}) {
 const [status,setStatus]=useState<{selection:{provider:string;model:string}|null;can_request:boolean;notice:string}|null>(null);
 const expanded=useRef(false);
 const [preview,setPreview]=useState<any>(null),[result,setResult]=useState<any>(null),[accepted,setAccepted]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const generation=useRef(0),loaded=useRef(false);
 const signature=JSON.stringify({kind,question,contextKey,settingsRevision});
 useEffect(()=>{generation.current++;setPreview(null);setResult(null);setAccepted(false);setBusy(false);setError('');},[signature]);
 useEffect(()=>{const clear=()=>{generation.current++;setPreview(null);setResult(null);setAccepted(false);setBusy(false);};window.addEventListener('noah-finance-vault-locked',clear);return()=>{clear();window.removeEventListener('noah-finance-vault-locked',clear);};},[]);
 useEffect(()=>{loaded.current=false;setStatus(null);if(expanded.current)void load();},[client,settingsRevision]);
 async function load(){
  if(loaded.current)return;
  const revision=++generation.current;setBusy(true);
  try{const r=await client.productIntelligence!({action:'decision_status'});if(revision!==generation.current)return;setStatus({selection:r.selection??null,can_request:r.can_request===true,notice:String(r.notice||'')});loaded.current=true;}
  catch{if(revision===generation.current)setError('AI 설정 상태를 불러오지 못했습니다. 다시 펼치면 재시도합니다.');}
  finally{if(revision===generation.current)setBusy(false);}
 }
 async function run(action:'decision_preview'|'decision_run') {const revision=++generation.current;setBusy(true);setError('');try{
  const r=await client.productIntelligence!({action,kind,question,consent:action==='decision_run'?{confirmed:true,payload_hash:preview.payload_hash}:undefined});
  if(revision!==generation.current)return;if(action==='decision_preview'){setPreview(r);setResult(null);setAccepted(false);}else{setResult(r);setPreview(null);setAccepted(false);}
 }catch{if(revision===generation.current){setPreview(null);setAccepted(false);loaded.current=false;setError('설정이 바뀌었거나 AI 연결을 확인하지 못했습니다. AI 엔진/API 설정을 확인한 후 다시 시도하세요.');void load();}}finally{if(revision===generation.current)setBusy(false);}}
 return <details onToggle={e=>{if(e.target!==e.currentTarget)return;expanded.current=e.currentTarget.open;if(expanded.current)void load();}} className="finance-decision"><summary>내 말을 AI로 이해하기</summary>
 <p>어떤 상황 버튼을 골라야 할지 모를 때, 내 말을 읽고 안내받을 유형을 찾아주는 선택 기능입니다. 버튼으로 상황을 고를 수 있다면 모델을 설정하지 않아도 됩니다.</p>
 <p>예를 들어 “보험은 없고 차로 출퇴근해요”라고 적으면 ‘보험 없음 · 운전 관련 보장’을 제안합니다. 내가 확인하면 해당 유형의 설명과 비교 준비로 이어집니다.</p>
 <details className="finance-decision-help"><summary>언제 AI 도움을 쓰면 좋나요?</summary>
  <p>기본 안내가 내 표현을 이해하지 못할 때, 설정된 AI가 질문의 목적을 짧게 정리합니다. 결과를 확인하면 해당 유형의 안내로 이어집니다. 자세한 비교 이유는 ‘AI 설명 더 보기’에서 물어볼 수 있습니다.</p>
  <p>질문을 보내기 전 내용과 API 비용 가능성을 확인합니다. 해석이 틀리면 적용하지 않고 상황 버튼이나 질문을 수정하세요.</p>
 </details>
 {status&&<p>{status.selection?`설정된 AI: ${status.selection.provider} · ${status.selection.model}`:'AI 설정 확인 필요'}<br/>{status.notice}</p>}
 {onOpenAISettings?<button type="button" onClick={()=>{generation.current++;setPreview(null);setResult(null);setAccepted(false);setBusy(false);loaded.current=false;onOpenAISettings();}}>AI 엔진/API 설정 열기</button>:<p>모델·API 연결은 설정 → AI 엔진/API에서 관리합니다.</p>}
 <button disabled={busy||!status?.can_request||!question.trim()} onClick={()=>void run('decision_preview')}>질문 분류에 보낼 내용 확인</button>
 {!question.trim()&&<p>위 ‘내 상황이나 궁금한 점’에 질문을 먼저 적어 주세요.</p>}
 {preview&&<section><p>판단 AI: {preview.packet.selection.provider} · {preview.packet.selection.model}</p><p>{preview.notice}</p><blockquote>{preview.packet.question}</blockquote><p>분류 선택지: {Object.values(preview.packet.choices).join(' / ')}</p><label><input type="checkbox" checked={accepted} onChange={e=>setAccepted(e.target.checked)}/>질문·수신 모델·API 비용 가능성을 확인하고 분류 요청에 동의합니다</label><button disabled={busy||!accepted} onClick={()=>void run('decision_run')}>선택한 AI로 질문 분류</button></section>}
 {result&&<section aria-live="polite"><p>{result.notice}</p>{result.status==='local_fallback'?<p>{result.local.answer}</p>:<><p>판단한 목적: <strong>{result.goal_label}</strong></p><p>질문에서 찾은 근거: {result.decision.goal_evidence||'확인 필요'}</p>{kind==='insurance'&&<p>가입 상태: {({none:'보험 없음',existing:'가입 보험 있음',unknown:'확인 필요'} as Record<string,string>)[result.decision.insurance_state]} · 근거 {result.decision.state_evidence||'미확인'}</p>}<p>실제 응답 모델: {result.provider} · {result.model} · 처리 {result.elapsed_ms??'미확인'}ms · 추정 비용 {typeof result.estimated_cost_usd==='number'?`$${result.estimated_cost_usd}`:'미확인'}</p>{result.status==='proposal'?<button onClick={()=>onApply({discovery_goal:result.decision.goal,...(kind==='insurance'&&result.decision.insurance_state!=='unknown'?{insurance_state:result.decision.insurance_state}:{})})}>이 해석이 맞아요 · 상황 안내에 적용</button>:<p>목적을 하나로 정하지 않았습니다. 위 상황 버튼에서 고르거나 질문을 더 구체적으로 적어 주세요.</p>}</>}</section>}
 {busy&&<p role="status">처리 중입니다…</p>}{error&&<p role="alert">{error}</p>}
 </details>;
}
