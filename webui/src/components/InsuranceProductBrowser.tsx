import {useEffect,useState} from 'react';

export type InsuranceReference={id:string;name:string;provider:string;category:string;category_label:string;coverage:string;renewal:string;checks:string;source_url:string;observed_at:string;review_due:string;version:string;evidence_status:string};
const date=(s:string)=>s?.slice(0,10)||'미확인';
export function InsuranceProductBrowser({products,goalCategory,onPrepare,busy=false,selected,onSelectionChange}:{products:InsuranceReference[];selected:string[];onSelectionChange:(ids:string[])=>void;goalCategory?:string;onPrepare:(ids:string[],category:string)=>void;busy?:boolean}) {
 const [search,setSearch]=useState(''),[company,setCompany]=useState(''),[category,setCategory]=useState('');
 useEffect(()=>{setCategory(goalCategory||'');},[goalCategory]);
 useEffect(()=>{const valid=selected.filter(id=>products.some(p=>p.id===id&&p.evidence_status==='reference'));if(valid.length!==selected.length)onSelectionChange(valid);},[products,selected]);
 const companies=[...new Set(products.map(p=>p.provider))].sort((a,b)=>a.localeCompare(b,'ko'));
 const categories=[...new Map(products.map(p=>[p.category,p.category_label])).entries()];
 const visible=products.filter(p=>(!company||p.provider===company)&&(!category||p.category===category)&&`${p.name} ${p.provider} ${p.coverage}`.toLowerCase().includes(search.toLowerCase()));
 const chosen=selected.map(id=>products.find(p=>p.id===id)).filter((p):p is InsuranceReference=>!!p);
 const sameType=chosen.length>0&&chosen.every(p=>p.category===chosen[0].category);
 function toggle(id:string){onSelectionChange(selected.includes(id)?selected.filter(v=>v!==id):[...selected,id].slice(0,4));}
 return <section className="insurance-product-browser" aria-label="보험회사·상품 둘러보기">
  <h4>보험회사·상품 둘러보기</h4>
  <p>상품 이름을 몰라도 종류와 회사별로 살펴보세요. 관심 상품을 최대 4개 골라 이 화면에서 비교할 수 있습니다.</p>
  <p className="reference-notice">공식 안내를 바탕으로 정리한 {products.length}개 상품의 탐색 자료입니다. 전체 시장 목록이나 개인 견적이 아니며, 현재 판매·가입 가능 여부는 확인이 필요합니다. 표시 순서는 추천 순위가 아닙니다.</p>
  <div className="product-result-grid">
   <label>보험 종류<select aria-label="보험 종류" value={category} onChange={e=>setCategory(e.target.value)}><option value="">모든 종류</option>{categories.map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
   <label>보험회사<select aria-label="보험회사" value={company} onChange={e=>setCompany(e.target.value)}><option value="">모든 회사</option>{companies.map(c=><option key={c}>{c}</option>)}</select></label>
   <label>상품·보장 검색<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="예: 운전자, 갱신, 진단"/></label>
  </div>
  <p>{visible.length}개 표시 · 관심 상품 {chosen.length}/4개 <button onClick={()=>{setSearch('');setCompany('');setCategory('');}}>전체 상품 보기</button></p>
  <div className="product-result-grid">{visible.map(p=><article key={p.id}>
   <small>{p.provider} · {p.category_label}</small><h4>{p.name}</h4><p>{p.coverage}</p>
   <p>개인 보험료: 견적 확인 필요</p>
   {p.evidence_status!=='reference'&&<p role="status">자료 재확인 기한이 지났습니다. 현재 비교·상담 후보 선택은 보류합니다.</p>}
   <details><summary>{p.provider} 상품 상세·확인할 조건</summary><dl><dt>갱신·기간</dt><dd>{p.renewal}</dd><dt>확인할 조건</dt><dd>{p.checks}</dd><dt>확인일 / 재확인 기한</dt><dd>{date(p.observed_at)} / {date(p.review_due)}</dd></dl><details><summary>자료 출처</summary><p>버전 {p.version}</p>{/^https:\/\//i.test(p.source_url)&&<a href={p.source_url} target="_blank" rel="noreferrer">보험회사 공식 안내 원문 ↗</a>}<p>원문은 외부 창에서 열립니다. 내 조건은 전송하지 않습니다.</p></details></details>
   <label><input type="checkbox" checked={selected.includes(p.id)} disabled={busy||p.evidence_status!=='reference'||(!selected.includes(p.id)&&selected.length>=4)} onChange={()=>toggle(p.id)}/>관심 상품 선택 · {p.name}</label>
  </article>)}</div>
  {!visible.length&&<p>현재 조건으로 표시할 상품이 없습니다. 전체 상품 보기로 필터를 초기화할 수 있습니다.</p>}
  {chosen.length>0&&<section aria-label="관심 보험 상품 비교"><h4>관심 상품 나란히 비교</h4><p>확인되지 않은 금액은 0원으로 계산하지 않습니다. 같은 종류라도 특약과 가입 조건을 맞춰야 보험료 비교가 가능합니다.</p>
   <p className="reference-swipe-hint">비교표를 좌우로 넘겨 다른 상품의 조건을 확인하세요.</p><div className="reference-comparison" role="region" aria-label="관심 상품 비교표" tabIndex={0}><table><caption>공식 안내 특징 비교 · 개인 보험료와 가입 자격 미확인</caption><thead><tr><th scope="col">비교 항목</th>{chosen.map(p=><th key={p.id} scope="col">{p.provider}<br/>{p.name}<br/><button aria-label={`${p.name} 선택 해제`} onClick={()=>toggle(p.id)}>선택 해제</button></th>)}</tr></thead><tbody>
    {[['종류','category_label'],['보장 특징','coverage'],['갱신·기간','renewal'],['확인할 조건','checks']].map(([label,key])=><tr key={key}><th scope="row">{label}</th>{chosen.map(p=><td key={p.id}>{p[key as keyof InsuranceReference]}</td>)}</tr>)}
    <tr><th scope="row">개인 보험료·가입 가능 여부</th>{chosen.map(p=><td key={p.id}>개인 견적·심사 확인 필요</td>)}</tr><tr><th scope="row">자료 확인일</th>{chosen.map(p=><td key={p.id}>{date(p.observed_at)}</td>)}</tr>
   </tbody></table></div>
   {!sameType&&<p>서로 다른 보험 종류를 선택했습니다. 상담 준비로 이어가려면 먼저 같은 종류끼리 선택하세요.</p>}
   <button className="primary-button" disabled={busy||!sameType} onClick={()=>onPrepare(selected,chosen[0].category)}>선택 상품으로 비교·상담 준비</button>
  </section>}
 </section>;
}
