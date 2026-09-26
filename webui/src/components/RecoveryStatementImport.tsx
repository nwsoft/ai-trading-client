import { useEffect, useRef, useState } from 'react';
import type { GatewayClient } from '../api';

const fields: Record<string,string> = {
  entry_allocations:'원본 체결별 진입 주문·수량 배분 JSON(선택·추측 입력 금지)',
  ledger_allocations:'원본 체결별 관리 기록 ID·수량 JSON(같은 주문 공유 시·추측 입력 금지)',
  execution_id:'체결 번호',order_id:'주문 번호',symbol:'종목',side:'매수/매도',quantity:'체결 수량',
  price:'체결 가격',fee:'수수료(환급은 음수)',fee_currency:'수수료 통화',timestamp:'체결 시각',
  realized_pnl:'가격 실현손익(선택)',tax:'세금(증권 필수)',position_side:'포지션 방향 BOTH/LONG/SHORT(선택)',entry_order_id:'원본에 명시된 청산 대상 진입 주문 ID(선택·추측 입력 금지)',
};
const aliases:Record<string,string[]>={execution_id:['tradeid','execid','체결번호'],order_id:['orderid','주문번호'],
  symbol:['symbol','종목','종목코드'],side:['side','매수매도','매매구분'],quantity:['quantity','qty','체결수량'],
  price:['price','체결가격','체결단가'],fee:['fee','commission','수수료'],fee_currency:['feecurrency','수수료통화'],
  timestamp:['timestamp','datetime','체결시각','체결시간'],tax:['tax','세금','제세금'],position_side:['positionside']};
const key=(s:string)=>s.toLowerCase().replace(/[ _-]/g,'');

export function RecoveryStatementImport({client,source}:{client:GatewayClient;source:string}) {
  const [content,setContent]=useState(''); const [name,setName]=useState('');
  const [mapping,setMapping]=useState<Record<string,string>>({});
  const [encoding,setEncoding]=useState('utf-8-sig'); const [zone,setZone]=useState('UTC');
  const [delimiter,setDelimiter]=useState(','); const [complete,setComplete]=useState(false);
  const [own,setOwn]=useState(false); const [preview,setPreview]=useState<Record<string,any>|null>(null);
  const [contractSize,setContractSize]=useState('1');
  const [timeFormat,setTimeFormat]=useState('iso'); const [numberFormat,setNumberFormat]=useState('plain');
  const futures=['binance','okx','bybit','bitget'].includes(source);
  const [headers,setHeaders]=useState<string[]>([]); const [busy,setBusy]=useState(false);
  const [error,setError]=useState(''); const [stored,setStored]=useState(false);
  const revision=useRef(0);
  useEffect(()=>()=>{++revision.current;},[]);
  function invalidate() { ++revision.current; setPreview(null); setStored(false); setError(''); }
  function payload() { return {source,content_base64:content,mapping,encoding,timezone:zone,delimiter,complete_cycles:complete,linear_contract:true,contract_size:futures?contractSize:'1',time_format:timeFormat,number_format:numberFormat}; }
  async function choose(file?:File) {
    invalidate(); const current=revision.current; setContent(''); setHeaders([]); setMapping({}); setOwn(false); setComplete(false);
    if(!file) return;
    if(file.size>8*1024*1024) {setError('파일은 8 MiB 이하로 선택하세요.'); return;}
    setName(file.name); setBusy(true);
    try {
      const bytes=new Uint8Array(await file.arrayBuffer()); let binary='';
      for(let i=0;i<bytes.length;i+=8192) binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
      if(current===revision.current) setContent(btoa(binary));
    } catch {if(current===revision.current) setError('파일을 읽지 못했습니다.');}
    finally {if(current===revision.current) setBusy(false);}
  }
  async function inspect(headerOnly=false) {
    if(!client.recoveryStatement) return;
    const current=++revision.current; setBusy(true);setError('');setStored(false);setPreview(null);
    try {
      const result=await client.recoveryStatement({...payload(),action:'preview',mapping:headerOnly?{}:mapping});
      if(current!==revision.current) return;
      setHeaders(result.headers||[]);
      if(headerOnly) {
        const suggested:Record<string,string>={};
        for(const field of Object.keys(fields)) {
          const found=(result.headers||[]).filter((h:string)=>[key(field),...(aliases[field]||[])].includes(key(h)));
          if(found.length===1) suggested[field]=found[0];
        }
        setMapping(suggested);
      } else setPreview(result);
    } catch(e) {if(current===revision.current) setError(`파일 검증 실패: ${e instanceof Error?e.message:String(e)}. 인코딩·구분자·열 대응을 확인하세요.`);}
    finally {if(current===revision.current) setBusy(false);}
  }
  async function save() {
    if(!preview?.ready || !own || !client.recoveryStatement) return;
    const current=revision.current;setBusy(true);setError('');
    try {
      const result=await client.recoveryStatement({...payload(),action:'import',reviewed_digest:preview.digest,confirmed_own_account:own});
      if(current===revision.current) setStored(result.stored===true);
    } catch(e) {if(current===revision.current) setError(`저장 실패: ${e instanceof Error?e.message:String(e)}`);}
    finally {if(current===revision.current) setBusy(false);}
  }
  return <details className="recovery-statement-import">
    <summary>공식 체결 내역 파일 가져오기 · CSV/TSV</summary>
    <p>거래소·증권사에서 내려받은 본인 계좌의 내역을 선택하세요. 파일은 이 PC의 계정 DB에 보관되며 외부 AI로 전송하지 않습니다. 파일의 진위가 API로 인증됐다는 뜻은 아닙니다.</p>
    <p>8 MiB·20,000행 이하. Excel은 CSV로 저장하세요. 수량은 앱 원장과 같은 단위, 수수료는 비용 양수·환급 음수입니다. 날짜·숫자 형식을 직접 확인하세요. 손익은 거래 비용 차감 기준이며 펀딩·입출금은 포함하지 않습니다.</p>
    <fieldset disabled={busy}>
      <input aria-label="공식 체결 내역 CSV" type="file" accept=".csv,.tsv,.txt" onChange={e=>void choose(e.target.files?.[0])}/>
      <span>{name}</span>
      <label>인코딩 <select value={encoding} onChange={e=>{invalidate();setEncoding(e.target.value);}}><option value="utf-8-sig">UTF-8</option><option value="cp949">CP949(한글 Windows)</option></select></label>
      <label>구분자 <select value={delimiter} onChange={e=>{invalidate();setDelimiter(e.target.value);}}><option value=",">쉼표</option><option value={'\t'}>탭</option><option value=";">세미콜론</option></select></label>
      <label>시간대 없는 시각의 기준 <select value={zone} onChange={e=>{invalidate();setZone(e.target.value);}}><option value="UTC">UTC</option><option value="Asia/Seoul">한국 시간</option></select></label>
      <label>시각 형식 <select value={timeFormat} onChange={e=>{invalidate();setTimeFormat(e.target.value);}}><option value="iso">ISO 날짜·시각</option><option value="epoch_ms">Unix 밀리초</option><option value="epoch_seconds">Unix 초</option></select></label>
      <label>숫자 형식 <select value={numberFormat} onChange={e=>{invalidate();setNumberFormat(e.target.value);}}><option value="plain">1234.56 (구분자 없음)</option><option value="grouped">1,234.56 (쉼표 천 단위)</option></select></label>
      {futures && <label>선형 선물만 지원 · 수량 1단위의 기초자산 수량(contractSize)<input value={contractSize} onChange={e=>{invalidate();setContractSize(e.target.value);}}/><small>거래소 계약 명세를 확인하세요. 원장이 BTC 단위면 1, 계약 단위면 해당 계약 크기입니다. 역선물은 지원하지 않습니다.</small></label>}
      <button type="button" disabled={!content} onClick={()=>void inspect(true)}>파일 열 확인</button>
      {headers.length>0 && <div className="recovery-statement-fields">{Object.entries(fields).map(([field,label])=><label key={field}>{label}<select value={mapping[field]||''} onChange={e=>{
        invalidate();const next={...mapping};if(e.target.value)next[field]=e.target.value;else delete next[field];setMapping(next);
      }}><option value="">열 선택</option>{headers.map(h=><option key={h} value={h}>{h}</option>)}</select></label>)}</div>}
      <label><input type="checkbox" checked={complete} onChange={e=>{invalidate();setComplete(e.target.checked);}}/>포함한 종목·포지션 방향별로 보유 0에서 시작해 0으로 끝나는 전체 체결 구간입니다. 중간 체결·수동 거래를 빼지 않았고, 해당 구간에 자산 입출고·주식 분할 등 수량 변동이 없습니다.</label>
      <button type="button" disabled={!content||!headers.length} onClick={()=>void inspect()}>검증·미리보기</button>
      {preview && <div role="status">
        <p>유효 체결 {preview.valid_count}건 · 오류 {preview.error_count}건 · 누락 열 {(preview.missing_fields||[]).map((k:string)=>fields[k]||k).join(', ')||'없음'}</p>
        <p>잘못된 행이 하나라도 있으면 파일을 저장하지 않습니다. 날짜·숫자 형식 선택과 매수/매도 값(buy/sell 또는 매수/매도)을 확인하세요. 자동으로 제안한 열도 확인해야 합니다.</p>
        <pre style={{maxHeight:200,overflow:'auto',whiteSpace:'pre-wrap'}}>{JSON.stringify(preview.errors?.length?preview.errors:preview.sample,null,2)}</pre>
        <label><input type="checkbox" checked={own} onChange={e=>setOwn(e.target.checked)}/>현재 NoahAI 계정의 {source.toUpperCase()} LIVE 내역이며 열·시간대·수량 단위·비용 부호와 위 미리보기를 확인했습니다.</label>
        <button type="button" disabled={!preview.ready||!own||stored} onClick={()=>void save()}>검토한 파일을 복구 근거로 저장</button>
      </div>}
    </fieldset>
    {error && <p role="alert">{error}</p>}
    {stored && <p role="status">파일을 보존했습니다. 위의 「거래 기록 점검·복구 실행」을 눌러 원장과 대조하세요. 파일 저장만으로 손익을 확정하거나 거래를 시작하지 않았습니다.</p>}
  </details>;
}
