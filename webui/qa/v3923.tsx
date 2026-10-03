import {createRoot} from 'react-dom/client';
import {GuidedProductComparison} from '../src/components/GuidedProductComparison';
import {ProductIntelligenceWorkspace} from '../src/components/ProductIntelligenceWorkspace';
import {ProfitabilityDiagnostic} from '../src/components/ProfitabilityDiagnostic';
import '../src/styles.css';
async function call(path:string,body?:unknown){const r=await fetch(path,{method:body?'POST':'GET',headers:{Authorization:'Bearer synthetic-v3923-token-for-local-qa-only','Content-Type':'application/json','X-NoahAI-Intent':'confirmed'},body:body?JSON.stringify(body):undefined});if(!r.ok)throw Error('request failed');return r.json();}
const client:any={productIntelligence:(payload?:any)=>call('/api/v1/life-finance/product-intelligence',payload),insuranceWorkspace:(action:string,payload:any)=>call('/api/v1/life-finance/insurance',{action,payload}),profitabilityDiagnostic:(source:string)=>call('/api/v1/maintenance/profitability?source='+source)};
const kind:any=new URLSearchParams(location.search).get('kind')||'loan';document.body.style.minWidth='0';createRoot(document.getElementById('root')!).render(<main style={{padding:16,height:'100vh',overflow:'auto'}}><p>합성 QA · 외부 거래/상품 연동 없음</p>{new URLSearchParams(location.search).has('guided')?<GuidedProductComparison client={client}/>:<ProductIntelligenceWorkspace client={client} kind={kind}/>}<ProfitabilityDiagnostic client={client} source="binance"/></main>);
