import {useEffect,useRef,useState} from 'react';
import type {GatewayClient} from '../api';
import {ProductIntelligenceWorkspace} from './ProductIntelligenceWorkspace';
import {FinanceAIExplanation} from './FinanceAIExplanation';
import {FinanceDecision} from './FinanceDecision';
import {InsuranceProductBrowser,type InsuranceReference} from './InsuranceProductBrowser';
import './ProductIntelligenceWorkspace.css';
import './FinanceDiscovery.css';

type Kind='loan'|'insurance'|'savings';
type Discovery={reference_products?:InsuranceReference[];reference_answer?:string;profile:Record<string,any>;answer:string;cards:Array<{id:string;title:string;reason:string;explanation:string;checks:string}>;goal_options:Array<{id:string;label:string}>;questions:string[];products:Array<Record<string,string>>;catalog_notice:string;can_compare:boolean;unresolved:string[]};
const starting=(kind:Kind)=>({discovery_goal:'unknown',...(kind==='insurance'?{insurance_state:'unknown'}:{})});
export function FinanceDiscovery({client,kind,onOpenAISettings,settingsRevision=0}:{client:GatewayClient;kind:Kind;onOpenAISettings?:()=>void;settingsRevision?:number}) {
 const [data,setData]=useState<Discovery|null>(null),[profile,setProfile]=useState<Record<string,any>>(starting(kind));
 const [question,setQuestion]=useState(''),[lastQuestion,setLastQuestion]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [selected,setSelected]=useState<string[]>([]),[references,setReferences]=useState<string[]>([]),[filter,setFilter]=useState('');
 const [comparison,setComparison]=useState<{profile:Record<string,any>;revision:number;mode:'prepare'|'quotes'|'saved'|'existing'}|null>(null),[advanced,setAdvanced]=useState(false),[step,setStep]=useState<'situation'|'products'>('situation');
 const generation=useRef(0),container=useRef<HTMLDivElement>(null);
 const context={...profile,reference_product_ids:references,...(selected.length?{discovery_product_ids:selected}:{})};
 async function explore(next:Record<string,any>,text='') {
  const revision=++generation.current;setBusy(true);setError('');
  try {if(!client.productIntelligence)throw Error('unavailable');const r=await client.productIntelligence({action:'discover',kind,profile:next,question:text}) as unknown as Discovery;
   if(revision!==generation.current)return;setData(r);setProfile(r.profile);setLastQuestion(text);setSelected(old=>old.filter(id=>r.products.some(p=>`${p.source_id}:${p.id}`===id)));
  }catch{if(revision===generation.current)setError('안내를 불러오지 못했습니다. 다시 시도해 주세요. 입력한 질문은 유지됩니다.');}
  finally{if(revision===generation.current)setBusy(false);}
 }
 useEffect(()=>{let active=true;void explore(starting(kind));const initialRevision=generation.current;void client.productIntelligence?.().then(()=>{if(active&&generation.current===initialRevision)void explore(starting(kind));}).catch(()=>{});const clear=()=>{generation.current++;setData(null);setProfile(starting(kind));setQuestion('');setLastQuestion('');setSelected([]);setReferences([]);setFilter('');setComparison(null);setAdvanced(false);setStep('situation');void explore(starting(kind));};window.addEventListener('noah-finance-vault-locked',clear);return()=>{active=false;generation.current++;window.removeEventListener('noah-finance-vault-locked',clear);};},[client,kind]);
 function pick(next:Record<string,any>){setQuestion('');setLastQuestion('');setReferences([]);void explore({...next,reference_product_ids:[]});}
 function focus(){requestAnimationFrame(()=>{container.current?.scrollIntoView({block:'start'});container.current?.focus({preventScroll:true});});}
 function proceed(mode:'prepare'|'quotes'|'saved'|'existing'='prepare',refs?:{ids:string[];category:string}) {
  if(comparison&&!window.confirm('새로 선택한 상황으로 비교를 시작하면 저장하지 않은 비교 입력이 바뀝니다. 계속할까요?'))return;
  const next={...context,...(kind==='insurance'&&!profile.insurance_kind?{insurance_kind:'unknown'}:{}),...(refs?{reference_product_ids:refs.ids,insurance_kind:refs.category,discovery_product_ids:[]}:{}),...(mode==='existing'?{insurance_state:'existing'}:{})};
  setComparison({profile:next,revision:Date.now(),mode});setAdvanced(true);focus();
 }
 async function refreshProducts(){setBusy(true);setError('');try{await client.productIntelligence?.({action:'refresh'});await explore(context);}catch{setError('상품 자료를 갱신하지 못했습니다. 입력은 유지됩니다. 잠시 후 다시 확인하세요.');}finally{setBusy(false);}}
 const products=data?.products.filter(r=>`${r.provider} ${r.name}`.toLowerCase().includes(filter.toLowerCase()))||[];
 return <div className="finance-discovery" ref={container} tabIndex={-1}>
 <section className="panel product-intelligence" hidden={advanced} aria-label="상황부터 상품 찾기">
  <nav className="discovery-choices" aria-label="금융상품 시작 방법"><button aria-pressed={step==='situation'} onClick={()=>setStep('situation')}>처음 알아보기</button><button onClick={()=>proceed('quotes')}>받은 견적 직접 비교하기</button>{kind==='insurance'&&<button onClick={()=>proceed('existing')}>기존 보험 점검</button>}<button onClick={()=>proceed('saved')}>저장한 계획 이어하기</button></nav>
  <p className="eyebrow">{step==='situation'?'1. 내 상황':'2. 상품 후보'} → 비교·상담 준비</p>
  <div hidden={step!=='situation'}><h3>상품을 몰라도 괜찮아요. 내 상황부터 알려주세요</h3><p>모르는 항목은 건너뛰어도 됩니다. 알려주신 내용으로 필요한 질문과 후보를 정리합니다.</p>
  {kind==='insurance'&&<fieldset><legend>현재 보험이 있나요?</legend><div className="command-row">{[['unknown','잘 모르겠어요'],['none','보험이 없어요'],['existing','가입한 보험이 있어요']].map(([id,label])=><button key={id} aria-pressed={profile.insurance_state===id} disabled={busy} onClick={()=>pick({...profile,insurance_state:id})}>{label}</button>)}</div></fieldset>}
  <h4>어떤 상황에 가까우세요?</h4><div className="discovery-choices">{data?.goal_options.map(o=><button key={o.id} aria-pressed={profile.discovery_goal===o.id} disabled={busy} onClick={()=>pick({...profile,discovery_goal:o.id,loan_purpose:''})}>{o.label}</button>)}<button disabled={busy} onClick={()=>pick({...profile,discovery_goal:'unknown',loan_purpose:''})}>아직 잘 모르겠어요</button></div>
  {kind==='loan'&&profile.discovery_goal==='housing'&&<label>주거 자금 용도<select aria-label="주거 자금 용도" value={profile.loan_purpose||'housing'} onChange={e=>pick({...profile,loan_purpose:e.target.value})}><option value="housing">아직 정하지 않음</option><option value="mortgage">집 구입</option><option value="jeonse">전세·임차</option></select></label>}
  <details><summary>금액·기간도 알고 있다면 · 선택 입력</summary>{(kind==='insurance'?[['insurance_budget','유지 가능한 월 보험료 예산(원)']]:[['amount',profile.method==='installment'?'매달 모을 금액(원)':'필요하거나 맡길 금액(원)'],[profile.method==='liquid'?'liquid_days':'months',profile.method==='liquid'?'보관할 기간(일)':'예상 기간(개월)']]).map(([key,label])=><label key={key}>{label}<input disabled={busy} inputMode="numeric" value={profile[key]||''} onChange={e=>setProfile(old=>({...old,[key]:e.target.value}))} placeholder="모르면 비워 두세요"/></label>)}</details>
  </div>
  <form onSubmit={e=>{e.preventDefault();void explore(context,question);}}><label>내 상황이나 궁금한 점<textarea maxLength={2000} value={question} onChange={e=>setQuestion(e.target.value)} placeholder={step==='products'?'예: 선택한 두 상품은 어떤 차이가 있나요?':kind==='insurance'?'예: 보험이 없고 운전을 해요. 예산은 아직 모르겠어요.':kind==='loan'?'예: 전세 자금이 필요한데 금리와 한도를 모르겠어요.':'예: 비상금 100만원을 한 달 정도 보관하고 싶어요.'}/></label><button type="submit" disabled={busy||!question.trim()}>내 상황으로 안내받기</button></form>
  <details><summary>AI 도움 받기 · 선택</summary><FinanceDecision onOpenAISettings={onOpenAISettings} settingsRevision={settingsRevision} client={client} kind={kind} question={question} contextKey={JSON.stringify(context)} onApply={change=>pick({...profile,...change})}/><FinanceAIExplanation client={client} scenario={{kind,mode:'discovery',profile:context}} question={question.trim()||lastQuestion||'선택한 상품과 상황에서 확인할 차이를 설명해 주세요'}/></details>
  {busy&&<p role="status">내용을 확인하고 있어요…</p>}{error&&<p role="alert">{error}<button onClick={()=>void explore(context,question)}>다시 시도</button></p>}
  {data&&<><p className="discovery-answer" aria-live="polite">{data.answer}</p>{data.reference_answer&&<p className="reference-answer" style={{whiteSpace:'pre-wrap'}}>{data.reference_answer}</p>}{data.unresolved.length>0&&<p>추가 확인: {data.unresolved.join(', ')}</p>}
   <details><summary>유형 차이와 다음 확인 질문</summary><div className="product-result-grid">{data.cards.map(c=><article key={c.id}><h4>{c.title}</h4><p>{c.explanation}</p><p>비교할 것: {c.checks}</p><button disabled={busy} onClick={()=>pick({...profile,discovery_goal:c.id})}>{c.title} 알아보기</button></article>)}</div><ul>{data.questions.map(q=><li key={q}>{q}</li>)}</ul></details>
   {step==='situation'?<button className="primary-button" disabled={busy} onClick={()=>{setStep('products');focus();}}>다음 · 상품 후보 살펴보기</button>:<>
    <button onClick={()=>{setStep('situation');focus();}}>← 내 상황 수정</button>
    {kind==='insurance'&&<InsuranceProductBrowser products={data.reference_products||[]} selected={references} onSelectionChange={setReferences} goalCategory={profile.discovery_goal==='unknown'?undefined:profile.insurance_kind} busy={busy} onPrepare={(ids,category)=>proceed('prepare',{ids,category})}/>}
    <details><summary>비교용 상품 자료 {data.products.length}건 · 출처·갱신 확인</summary><p>{data.catalog_notice}</p><p>자료 연결이 없는 경우에도 관심 계획과 상담 질문을 저장할 수 있습니다. 새로 확인은 연결된 공급 자료를 읽으며 개인 보험료·금리 조회를 실행하지 않습니다.</p><button disabled={busy} onClick={()=>void refreshProducts()}>상품 자료 새로 확인</button></details>
    {data.products.length>0&&<><label>회사·상품 이름으로 좁히기<input value={filter} onChange={e=>setFilter(e.target.value)}/></label><div className="product-result-grid">{products.map(p=>{const id=`${p.source_id}:${p.id}`;return <article key={id}><label><input type="checkbox" checked={selected.includes(id)} disabled={!selected.includes(id)&&selected.length>=20} onChange={e=>setSelected(old=>e.target.checked?[...old,id]:old.filter(v=>v!==id))}/>{p.provider} · {p.name}</label><p>표시 이유: 선택한 목적·방식의 자료입니다. 개인 자격은 확인이 필요합니다.</p><details><summary>출처·자료 기한</summary><p>확인 {p.verified_at} / 기한 {p.valid_until}</p>{/^https:\/\//i.test(p.source_url)&&<a href={p.source_url} target="_blank" rel="noreferrer">공식 자료 확인</a>}</details></article>;})}</div>{!products.length&&<p>검색 결과가 없습니다. 검색어를 지우거나 내 상황을 수정하세요.</p>}</>}
    {profile.discovery_goal==='liquid'&&<p>비상금은 인출 가능 여부를 먼저 확인합니다. 비교 화면에서 보관할 일수와 확인한 잔액 구간 금리를 입력할 수 있습니다.</p>}
    <button className="primary-button" disabled={busy} onClick={()=>proceed()}>이 상황으로 비교·상담 준비하기</button>
   </>}
  </>}
  {comparison&&<button onClick={()=>{setAdvanced(true);focus();}}>작성 중인 비교로 돌아가기</button>}
 </section>
 {comparison&&<div hidden={!advanced}><button onClick={()=>{setAdvanced(false);focus();}}>← 상황 안내로 돌아가기 · 비교 입력 유지</button><ProductIntelligenceWorkspace key={comparison.revision} client={client} kind={kind} initialProfile={comparison.profile} initialMode={comparison.mode}/></div>}
 </div>;
}
