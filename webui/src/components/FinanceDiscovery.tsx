import {useEffect,useRef,useState} from 'react';
import type {GatewayClient} from '../api';
import {ProductIntelligenceWorkspace} from './ProductIntelligenceWorkspace';
import {FinanceAIExplanation} from './FinanceAIExplanation';
import {FinanceDecision} from './FinanceDecision';
import './ProductIntelligenceWorkspace.css';
import './FinanceDiscovery.css';
import {InsuranceProductBrowser,type InsuranceReference} from './InsuranceProductBrowser';

type Kind='loan'|'insurance'|'savings';
type Discovery={reference_products?:InsuranceReference[];profile:Record<string,any>;answer:string;cards:Array<{id:string;title:string;reason:string;explanation:string;checks:string}>;goal_options:Array<{id:string;label:string}>;questions:string[];products:Array<Record<string,string>>;catalog_notice:string;can_compare:boolean;unresolved:string[]};
const starting=(kind:Kind)=>({discovery_goal:'unknown',...(kind==='insurance'?{insurance_state:'unknown'}:{})});
export function FinanceDiscovery({client,kind,onOpenAISettings,settingsRevision=0}:{client:GatewayClient;kind:Kind;onOpenAISettings?:()=>void;settingsRevision?:number}) {
 const [data,setData]=useState<Discovery|null>(null),[profile,setProfile]=useState<Record<string,any>>(starting(kind));
 const [question,setQuestion]=useState(''),[lastQuestion,setLastQuestion]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [selected,setSelected]=useState<string[]>([]),[filter,setFilter]=useState('');
 const [comparison,setComparison]=useState<{profile:Record<string,any>;revision:number}|null>(null),[advanced,setAdvanced]=useState(false);
 const generation=useRef(0);
 async function explore(next:Record<string,any>,text='') {
  const revision=++generation.current;setBusy(true);setError('');
  try {if(!client.productIntelligence)throw Error('unavailable');const r=await client.productIntelligence({action:'discover',kind,profile:next,question:text}) as unknown as Discovery;
   if(revision!==generation.current)return;setData(r);setProfile(r.profile);setLastQuestion(text);setSelected([]);setFilter('');
  }catch{if(revision===generation.current)setError('안내를 불러오지 못했습니다. 다시 시도해 주세요. 입력한 질문은 유지됩니다.');}
  finally{if(revision===generation.current)setBusy(false);}
 }
 useEffect(()=>{void explore(starting(kind));const clear=()=>{generation.current++;setData(null);setProfile(starting(kind));setQuestion('');setLastQuestion('');setSelected([]);setFilter('');setComparison(null);setAdvanced(false);void explore(starting(kind));};window.addEventListener('noah-finance-vault-locked',clear);return()=>{generation.current++;window.removeEventListener('noah-finance-vault-locked',clear);};},[client,kind]);
 function pick(next:Record<string,any>){setQuestion('');setLastQuestion('');void explore(next);}
 function proceed(manual=false,references?:{ids:string[];category:string}) {
  if(comparison&&!window.confirm('새로 선택한 상황으로 비교를 시작하면 이 종류의 기존 비교 입력이 바뀝니다. 계속할까요?'))return;
  setComparison({profile:manual?{}:{...profile,...(selected.length?{discovery_product_ids:selected}:{}),...(references?{reference_product_ids:references.ids,insurance_kind:references.category,discovery_product_ids:[]}:{} )},revision:Date.now()});setAdvanced(true);
 }
 async function refreshProducts(){const revision=++generation.current;setBusy(true);setError('');try{await client.productIntelligence?.({action:'refresh'});if(revision===generation.current)await explore(profile);}catch{if(revision===generation.current)setError('상품 자료를 갱신하지 못했습니다. 기존 안내는 유지합니다.');}finally{if(revision===generation.current)setBusy(false);}}
 const products=data?.products.filter(r=>`${r.provider} ${r.name}`.toLowerCase().includes(filter.toLowerCase()))||[];
 return <div className="finance-discovery">
 <section className="panel product-intelligence" hidden={advanced} aria-label="상황부터 상품 찾기">
  <span className="eyebrow">1. 내 상황 → 2. 필요한 유형 → 3. 상품·견적 비교</span>
  <h3>상품을 몰라도 괜찮아요. 내 상황부터 알려주세요</h3>
  <p>회사명·상품명·견적 없이 시작할 수 있습니다. 먼저 알아볼 유형과 이유를 함께 정리해요.</p>
  {kind==='insurance'&&<fieldset><legend>현재 보험이 있나요?</legend><div className="command-row">{[['unknown','잘 모르겠어요'],['none','보험이 없어요'],['existing','가입한 보험이 있어요']].map(([id,label])=><button key={id} type="button" aria-pressed={profile.insurance_state===id} disabled={busy} onClick={()=>pick({...profile,insurance_state:id})}>{label}</button>)}</div></fieldset>}
  <h4>어떤 상황에 가까우세요?</h4><div className="discovery-choices">{data?.goal_options.map(o=><button key={o.id} aria-pressed={profile.discovery_goal===o.id} disabled={busy} onClick={()=>pick({...profile,discovery_goal:o.id})}>{o.label}</button>)}<button disabled={busy} onClick={()=>pick({...profile,discovery_goal:'unknown'})}>아직 잘 모르겠어요</button></div>
  <form onSubmit={e=>{e.preventDefault();void explore(profile,question);}}><label>내 상황이나 궁금한 점<textarea maxLength={2000} value={question} onChange={e=>setQuestion(e.target.value)} placeholder={kind==='insurance'?'예: 보험이 없고 운전을 해요. 예산은 아직 모르겠어요.':kind==='loan'?'예: 기존 대출 부담을 줄이고 싶어요.':'예: 매달 30만원씩 모으고 싶어요. 기간은 1년이에요.'}/></label><button type="submit" disabled={busy||!question.trim()}>내 상황으로 안내받기</button></form>
  <small>빠른 기본 안내는 내 PC에서 처리합니다. 이름·연락처·건강정보를 적을 필요가 없습니다.</small>
  <FinanceDecision onOpenAISettings={onOpenAISettings} settingsRevision={settingsRevision} client={client} kind={kind} question={question} contextKey={JSON.stringify(profile)} onApply={change=>pick({...profile,...change})}/>
  {busy&&<p role="status">상황을 정리하고 있어요…</p>}{error&&<p role="alert">{error} <button onClick={()=>void explore(profile,question)}>다시 시도</button></p>}
  {data&&<div aria-live="polite"><p className="discovery-answer">{data.answer}</p>{data.unresolved.length>0&&<p>추가 확인: {data.unresolved.join(', ')}. 모호한 내용은 자동 확정하지 않습니다.</p>}
   <h4>{profile.discovery_goal==='unknown'?'목적별로 이런 차이가 있어요':'이 상황에서 먼저 알아볼 유형'}</h4>
   <div className="product-result-grid">{data.cards.map(card=><article key={card.id}><h4>{card.title}</h4><p>{card.reason}</p><p>{card.explanation}</p><p><strong>비교할 것</strong> · {card.checks}</p>{profile.discovery_goal==='unknown'&&<button disabled={busy} onClick={()=>pick({...profile,discovery_goal:card.id})}>{card.title} 알아보기</button>}</article>)}</div>
   <h4>다음에는 이것만 확인해요</h4><ul>{data.questions.map(q=><li key={q}>{q}</li>)}</ul>
   <details><summary>금액·기간도 알고 있다면 · 선택 입력</summary>{(kind==='insurance'?[['insurance_budget','유지 가능한 월 보험료 예산(원)']]:[['amount',profile.method==='installment'?'매달 모을 금액(원)':'필요하거나 맡길 금액(원)'],['months','예상 기간(개월)']]).map(([key,label])=><label key={key}>{label}<input disabled={busy} inputMode="numeric" value={profile[key]||''} onChange={e=>{generation.current++;setBusy(false);setProfile(old=>({...old,[key]:e.target.value}));}} placeholder="모르면 비워 두세요"/></label>)}</details>
   <h4>연결된 비교 자료</h4><p>{data.catalog_notice}</p><button disabled={busy} onClick={()=>void refreshProducts()}>상품 자료 새로 확인</button>
   {kind==='insurance'&&<InsuranceProductBrowser products={data.reference_products||[]} goalCategory={profile.discovery_goal==='unknown'?undefined:profile.insurance_kind} busy={busy} onPrepare={(ids,category)=>proceed(false,{ids,category})}/>}
   {data.products.length>0&&<><label>회사·상품 이름으로 좁히기<input value={filter} onChange={e=>setFilter(e.target.value)} placeholder="전체 후보를 먼저 둘러봐도 됩니다"/></label><p>선택 {selected.length}개 · 선택하지 않으면 이 유형의 유효 후보 전체를 비교합니다.</p><div className="product-result-grid">{products.map(p=>{const id=`${p.source_id}:${p.id}`;return <article key={id}><label><input type="checkbox" checked={selected.includes(id)} disabled={!selected.includes(id)&&selected.length>=20} onChange={e=>setSelected(old=>e.target.checked?[...old,id]:old.filter(v=>v!==id))}/>{p.provider} · {p.name}</label><p>버전 {p.version} · 확인 {p.verified_at} · 유효 기한 {p.valid_until}</p>{/^https?:\/\//i.test(p.source_url)&&<a href={p.source_url} target="_blank" rel="noreferrer">상품 원문 확인</a>}</article>;})}</div>{!products.length&&<p>검색어에 맞는 후보가 없습니다. 검색어를 지우면 전체 후보가 보입니다.</p>}</>}
   <p>유형 안내는 가입 추천·개인 심사 결과가 아닙니다. 보장·금리·비용을 확인한 뒤 실제 조건을 비교합니다.</p>
   <button className="primary-button" disabled={busy||!data.can_compare} onClick={()=>proceed()}>이 상황으로 비교·상담 준비하기</button>
   {profile.discovery_goal==='liquid'&&<p>수시 입출금 상품의 금리 구간 계산은 아직 지원하지 않습니다. 사용 시점과 인출 조건을 확인한 뒤 기관에 문의하세요.</p>}
   <FinanceAIExplanation client={client} scenario={{kind,mode:'discovery',profile}} question={question.trim()||lastQuestion||'선택한 상황에서 어떤 유형을 먼저 알아보고 무엇을 확인하면 좋을까요?'}/>
  </div>}
  <details><summary>이미 견적이 있거나 비교 입력을 직접 하고 싶어요</summary><button onClick={()=>proceed(true)}>받은 견적 직접 비교하기</button></details>
  {comparison&&<button onClick={()=>setAdvanced(true)}>작성 중인 비교로 돌아가기</button>}
 </section>
 {comparison&&<div hidden={!advanced}><button className="secondary-button" onClick={()=>setAdvanced(false)}>← 상황 안내로 돌아가기 · 비교 입력 유지</button><ProductIntelligenceWorkspace key={comparison.revision} client={client} kind={kind} initialProfile={comparison.profile}/></div>}
 </div>;
}
