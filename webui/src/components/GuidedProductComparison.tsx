import {useState,type KeyboardEvent} from 'react';
import type {GatewayClient} from '../api';
import {FinanceDiscovery} from './FinanceDiscovery';
import {InsuranceWorkspace} from './InsuranceWorkspace';
import './GuidedProductComparison.css';

type Kind='loan'|'insurance'|'savings';
type Tab='overview'|Kind;
const tabs:Array<[Tab,string]>=[['overview','전체 안내'],['loan','대출 비교'],['insurance','보험 비교'],['savings','예금·적금 비교']];
const guides:Array<{kind:Kind;title:string;intro:string;action:string}>=[
 {kind:'loan',title:'빌릴 돈',intro:'생활자금·주거·대환 중 목적부터 정하고, 갚을 여력과 실제 금리·총비용을 함께 살펴봐요.',action:'내 대출 목적부터 알아보기'},
 {kind:'insurance',title:'지킬 보장',intro:'보험이 없거나 가입 여부를 몰라도 시작해요. 걱정되는 상황에 맞춰 보장 종류와 차이를 설명해요.',action:'내 보장부터 이해하기'},
 {kind:'savings',title:'모을 돈',intro:'지금 가진 목돈인지, 매달 모을 돈인지, 곧 써야 할 돈인지부터 함께 구분해요.',action:'내 저축 목적부터 알아보기'},
];
export function GuidedProductComparison({client,onOpenAISettings,settingsRevision=0}:{client:GatewayClient;onOpenAISettings?:()=>void;settingsRevision?:number}) {
 const [tab,setTab]=useState<Tab>('overview'),[visited,setVisited]=useState<Kind[]>([]),[documents,setDocuments]=useState(false);
 function navigate(next:Tab){setTab(next);if(next!=='overview')setVisited(old=>old.includes(next)?old:[...old,next]);}
 function keys(e:KeyboardEvent<HTMLButtonElement>,i:number){let target=i;if(e.key==='ArrowRight')target=(i+1)%tabs.length;else if(e.key==='ArrowLeft')target=(i+tabs.length-1)%tabs.length;else if(e.key==='Home')target=0;else if(e.key==='End')target=tabs.length-1;else return;e.preventDefault();navigate(tabs[target][0]);document.getElementById(`product-tab-${tabs[target][0]}`)?.focus();}
 return <section className="product-studio data-workspace">
  <header className="panel product-hero"><div><span className="eyebrow">FINANCE GUIDE · 상황부터 함께 찾기</span><h2>내게 필요한 금융, 한 단계씩</h2><p>상품 이름을 몰라도 시작하세요. 내 상황을 이해하고, 필요한 유형을 찾은 다음 같은 기준으로 비교합니다.</p></div><span className="product-local-badge">상황 안내는 내 PC에서</span></header>
  <nav className="product-tabs" role="tablist" aria-label="금융상품 비교 종류">{tabs.map(([key,title],i)=><button key={key} id={`product-tab-${key}`} role="tab" aria-selected={tab===key} aria-controls={`product-panel-${key}`} tabIndex={tab===key?0:-1} onKeyDown={e=>keys(e,i)} onClick={()=>navigate(key)}>{title}</button>)}</nav>
  <section hidden={tab!=='overview'} role="tabpanel" id="product-panel-overview" aria-labelledby="product-tab-overview" className="panel"><h3>무엇부터 알아보고 싶으세요?</h3><p>견적이나 증권을 준비하지 않아도 됩니다. 선택하거나 편하게 질문해 주세요.</p><div className="product-purpose-grid">{guides.map((g,i)=><article key={g.kind}><span className="product-number">0{i+1}</span><h3>{g.title}</h3><p>{g.intro}</p><button className="primary-button" onClick={()=>navigate(g.kind)}>{g.action}</button></article>)}</div><p>실제 회사·상품 후보는 출처와 유효 기한을 확인한 자료가 연결된 범위에서 보여드립니다. 개인 견적·가입 가능 여부는 기관 확인이 필요합니다.</p></section>
  {guides.map(g=><section key={g.kind} hidden={tab!==g.kind} role="tabpanel" id={`product-panel-${g.kind}`} aria-labelledby={`product-tab-${g.kind}`}>{visited.includes(g.kind)&&<FinanceDiscovery onOpenAISettings={onOpenAISettings} settingsRevision={settingsRevision} client={client} kind={g.kind}/>}</section>)}
  <section hidden={tab!=='insurance'}><details className="panel" onToggle={e=>{if(e.currentTarget.open)setDocuments(true);}}><summary>이미 가입한 보험의 증권·약관을 확인하고 싶어요</summary>{documents&&<InsuranceWorkspace client={client}/>}</details></section>
 </section>;
}
