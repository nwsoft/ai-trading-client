import {useEffect, useRef, useState} from 'react';
import type {GatewayClient} from '../api';

type Item = {name:string; analysis?:Record<string,any>; state:string; message:string; saved?:boolean};
export function StrategyBatchImport({client,files,scope,defaultTarget,disabled,onComplete}:{
  client:GatewayClient;files:File[];scope:string;defaultTarget:string;disabled:boolean;onComplete:(id:string,count:number)=>void;
}) {
  const [items,setItems]=useState<Item[]>([]),[running,setRunning]=useState(false);
  const stop=useRef(false),lock=useRef(false),generation=useRef(0),mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;stop.current=true;generation.current++;};},[]);
  useEffect(()=>{stop.current=true;generation.current++;setItems([]);},[files,scope,defaultTarget]);
  const publish=(next:Item[],g:number)=>{if(mounted.current&&g===generation.current)setItems([...next]);};
  async function analyze() {
    if(lock.current||disabled||!files.length||files.length>10)return;
    lock.current=true;stop.current=false;setRunning(true);const g=generation.current;
    const next:Item[]=files.map(file=>({name:file.name,state:'대기',message:'미분석'}));publish(next,g);
    try {for(const [index,file] of files.entries()){
      if(stop.current||g!==generation.current)break;
      try {
        if(!/\.(txt|pine)$/i.test(file.name)||file.size>1024*1024)throw new Error('파일별 등록은 1MB 이하 TXT/Pine에 대응합니다.');
        next[index]={...next[index],state:'분석 중',message:'파일마다 독립적으로 분석합니다.'};publish(next,g);
        const text=await file.text();
        const analysis=await client.analyzeStrategySource({kind:'text',value:text,file_name:file.name,encoding:'text',authoring_mode:'source_faithful'});
        next[index]={name:file.name,analysis,state:analysis.ready_for_execution?'검토 준비 완료':'보완 필요',message:analysis.ready_for_execution?'저장 전 이름·범위·규칙을 확인하세요.':String(analysis.missing_conditions?.join(' · ')||'실행 조건 보완이 필요합니다.')};
      }catch(e){next[index]={name:file.name,state:'분석 실패',message:e instanceof Error?e.message:'자료를 읽지 못했습니다.'};}
      publish(next,g);
    }}finally{lock.current=false;if(mounted.current)setRunning(false);}
  }
  async function save() {
    if(lock.current||disabled||!items.some(row=>row.analysis?.ready_for_execution&&!row.saved))return;
    const targets=items.filter(row=>row.analysis?.ready_for_execution&&!row.saved&&row.state!=='저장 확인 필요');
    if(!window.confirm(`${targets.length}개 파일의 이름·거래소 범위·규칙을 검토했나요? 미승인 초안만 저장하며 PAPER 시작·실제 적용은 별도입니다.`))return;
    lock.current=true;stop.current=false;setRunning(true);const g=generation.current,next=[...items];let count=0,last='';
    try{for(const [index,item] of next.entries()){
      if(stop.current||g!==generation.current)break;
      if(!item.analysis?.ready_for_execution||item.saved||item.state==='저장 확인 필요')continue;
      try{
        const rules={...item.analysis.rules,target_scope:item.analysis.rules?.target_scope||defaultTarget};
        const validation=await client.validateStrategyDraft({rules,compiler_issues:rules.compiler_issues||[]});
        if(!validation.ready)throw new Error('최종 규칙 검사에서 보완이 필요합니다. 개별 파일을 확인하세요.');
        // A lost submit response is never automatically retried; inspect the catalog first.
        next[index]={...item,state:'저장 중',message:'응답이 유실되면 목록에서 저장 여부를 먼저 확인하세요.'};publish(next,g);
        try{
          const created=await client.submitStrategy({scope,name:String(rules.strategy_name||item.analysis.name||item.name.replace(/\.[^.]+$/,'')),rules:validation.rules||rules,source_kind:'text',source_reference:item.name});
          last=String(created.version_id);count++;next[index]={...item,saved:true,state:'저장 완료',message:'미승인 초안 저장 · 별도 승인·PAPER 검증 필요'};
        }catch(e){next[index]={...item,state:'저장 확인 필요',message:'자동 재전송하지 않습니다. 전략 목록에서 저장 여부를 확인하세요. '+(e instanceof Error?e.message:'응답 미확인')};}
      }catch(e){next[index]={...item,state:'저장 보류',message:e instanceof Error?e.message:'최종 검사 미통과'};}
      publish(next,g);
    }}finally{lock.current=false;if(mounted.current)setRunning(false);if(count&&mounted.current&&g===generation.current)onComplete(last,count);}
  }
  return <section className="strategy-batch-import"><h3>여러 파일을 각각 독립 전략으로 만들기</h3><p>TXT/Pine 최대 10개, 파일당 1MB. 파일별로 분석하고 내용을 검토한 뒤 미승인 초안을 저장합니다. 한 전략의 여러 참고자료는 기존 묶음 분석을 사용하세요. 설정된 외부 AI를 사용하면 파일별 비용이 발생할 수 있습니다.</p>
    <button className="secondary-button" type="button" disabled={disabled||running||files.length>10||items.some(item=>item.saved||item.state==='저장 확인 필요')} onClick={()=>void analyze()}>파일별 독립 분석</button>
    <button className="secondary-button" type="button" disabled={disabled||running||!items.some(row=>row.analysis?.ready_for_execution&&!row.saved&&row.state!=='저장 확인 필요')} onClick={()=>void save()}>검토한 준비 완료 초안 저장</button>
    {running&&<button className="secondary-button" type="button" onClick={()=>{stop.current=true;}}>현재 요청 후 중단</button>}
    <p role="status">분석·저장 결과 {items.length}개 · 저장 완료 {items.filter(item=>item.saved).length}개. 저장 후에도 내용 승인과 모의 운용은 각각 확인하세요.</p><ul>{items.map((item,index)=><li key={index}><b>{item.name}</b> · {item.state} · {item.message}{item.analysis&&<><dl><div><dt>전략 이름</dt><dd>{item.analysis.rules?.strategy_name||item.analysis.name||item.name}</dd></div><div><dt>기관 범위</dt><dd>{item.analysis.rules?.target_scope||`${defaultTarget} · 파일에 명시되지 않아 현재 선택 사용`}</dd></div><div><dt>국면 기준 · 우선순위</dt><dd>{({symbol:'종목별',market:'시장',both:'시장과 종목',none:'국면 무관'} as Record<string,string>)[String(item.analysis.rules?.regime_scope)]||'파일에 미명시'} · {item.analysis.rules?.priority??'파일에 미명시'}</dd></div></dl><details><summary>파일별 이름·기관·국면·우선순위·규칙 검토</summary><pre>{JSON.stringify({name:item.analysis.rules?.strategy_name||item.analysis.name||item.name,target_scope:item.analysis.rules?.target_scope||defaultTarget,regime_scope:item.analysis.rules?.regime_scope,priority:item.analysis.rules?.priority,rules:item.analysis.rules},null,2)}</pre></details></>}</li>)}</ul>
  </section>;
}
