import {useEffect,useRef,useState} from 'react';
import type {GatewayClient} from '../api';

export function FinanceAIExplanation({client,scenario,question}:{client:GatewayClient;scenario:Record<string,any>;question:string}){
 const [scopes,setScopes]=useState(['numeric_results']),[preview,setPreview]=useState<any>(null),[accepted,setAccepted]=useState(false),[answer,setAnswer]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const generation=useRef(0),signature=JSON.stringify({scenario,question,scopes});
 useEffect(()=>{generation.current++;setPreview(null);setAccepted(false);setAnswer('');setBusy(false);},[signature]);
 useEffect(()=>()=>{generation.current++;},[]);
 async function run(action:string){const revision=++generation.current;setBusy(true);setError('');try{const result=await client.productIntelligence!({action,scenario,question,scopes,consent:action==='ai_explain'?{confirmed:true,payload_hash:preview.payload_hash}:undefined});if(revision!==generation.current)return;if(action==='ai_preview'){setPreview(result);setAccepted(false);}else setAnswer((result.status==='local_fallback'?result.reason+'\n':'AI 설명 초안 · 계산값·상품 가입 가능성을 확정하지 않습니다.\n')+result.answer);}catch{if(revision===generation.current)setError('AI 설정·질문·선택 내용을 확인하세요. 자료나 모델이 변경되면 전송 내용을 다시 확인해야 합니다. 위 로컬 비교·질문 기능은 계속 사용할 수 있습니다.');}finally{if(revision===generation.current)setBusy(false);}}
 return <details><summary>선택한 내용으로 AI 설명 더 보기</summary><p>위 질문과 선택한 정보가 설정된 AI로 전달될 수 있고 사용 비용이 발생할 수 있습니다. 원문·건강정보·연락처는 자동 첨부하지 않습니다. 자료 속 설명은 가입·승인 결과가 아닙니다.</p>
 <label><input type="checkbox" checked={scopes.includes('numeric_results')} onChange={e=>setScopes(old=>e.target.checked?[...old,'numeric_results']:old.filter(v=>v!=='numeric_results'))}/>비교 이름·계산 수치·미확인 조건</label>
 <label><input type="checkbox" checked={scopes.includes('public_evidence')} onChange={e=>setScopes(old=>e.target.checked?[...old,'public_evidence']:old.filter(v=>v!=='public_evidence'))}/>AI 처리 권한을 확인한 공개 상품 근거</label>
 <button disabled={busy||!question.trim()||!scopes.length} onClick={()=>void run('ai_preview')}>AI에 보낼 내용 먼저 확인</button>
 {preview&&<><p>수신 AI: {preview.packet.provider} · {preview.packet.model}</p><p>{preview.notice}</p><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(preview.packet.facts,null,2)}</pre><label><input type="checkbox" checked={accepted} onChange={e=>setAccepted(e.target.checked)}/>위 수신 AI·전송 내용·비용 가능성을 확인하고 동의합니다</label><button disabled={busy||!accepted} onClick={()=>void run('ai_explain')}>선택한 내용 전송·AI 설명 요청</button></>}
 {answer&&<p style={{whiteSpace:'pre-wrap'}} aria-live="polite">{answer}</p>}{error&&<p role="alert">{error}</p>}
 </details>;
}
