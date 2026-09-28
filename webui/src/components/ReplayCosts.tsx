import {useEffect, useState} from 'react';
import type {GatewayClient} from '../api';

const labels: Record<string,string> = {buy_fee_rate:'매수 수수료',sell_fee_rate:'매도 수수료',buy_slippage_rate:'매수 슬리피지',sell_slippage_rate:'매도 슬리피지',spread_rate:'왕복 스프레드',sell_tax_rate:'매도 세금'};
const origins:Record<string,string>={reference_estimate:'기관 참조 가정',legacy_global_setting:'기존 공통 설정',venue_setting:'기관별 설정',venue_product_setting:'기관·상품별 설정',default_stock_paper_contract:'증권 시뮬레이션 기본 가정',user_run_override:'이번 검사 입력','settings.paper_costs':'기존 증권 비용 설정',normalized_paper_costs:'기존 증권 비용 설정',invalid_settings_fallback:'기존 증권 설정 오류의 기본 가정'};
export function ReplayCosts({client,source,assetClass,onChange}: {client:GatewayClient;source:string;assetClass:string;onChange:(value:Record<string,number>|null)=>void}) {
  const [profile,setProfile]=useState<Record<string,any>|null>(null);
  const [values,setValues]=useState<Record<string,string>>({});
  const [error,setError]=useState('');
  const [custom,setCustom]=useState(false);
  useEffect(()=>{
    let cancelled=false;
    setProfile(null);setValues({});setCustom(false);setError('');onChange(null);
    client.replayCosts(source,assetClass).then(p=>{
      if(cancelled)return;
      setProfile(p);setValues(Object.fromEntries(Object.entries(p.rates).map(([k,v])=>[k,String(Number((Number(v)*100).toFixed(6)))])));
    }).catch(e=>{if(!cancelled)setError(e instanceof Error?e.message:'비용 조회 실패');});
    return ()=>{cancelled=true;};
  },[client,source,assetClass]);
  function update(next:Record<string,string>,enabled:boolean){
    if(!enabled && profile)next=Object.fromEntries(Object.entries(profile.rates).map(([k,v])=>[k,String(Number((Number(v)*100).toFixed(6)))]));
    setValues(next);setCustom(enabled);
    onChange(enabled ? Object.fromEntries(Object.entries(next).map(([k,v])=>[k,v.trim()===''?NaN:Number(v)/100])) : null);
  }
  const total=Object.values(values).reduce((n,v)=>n+Number(v),0);
  return <fieldset className="replay-cost-panel" data-testid="replay-costs"><legend>검사 비용 · {source.toUpperCase()} · {profile?.product ?? assetClass}</legend>
    <p>계정 확정 요율이 아닌 추정값입니다. 주문별 실제 수수료는 등급·할인·메이커/테이커에 따라 다릅니다. 아래 입력은 이번 백테스트에만 적용되며 PAPER/LIVE 설정을 변경하지 않습니다.</p>
    {error ? <p role="alert">{error} · 비용을 확인하기 전에는 검사하지 마세요.</p> : !profile ? <p>비용 가정 조회 중</p> : <>
      <label className="replay-cost-toggle"><input type="checkbox" checked={custom} onChange={e=>update(values,e.target.checked)}/>이번 검사 비용 직접 입력</label>
      <div className="form-grid">{Object.entries(labels).map(([key,label])=><label key={key}>{label} (%)<input aria-label={`${label} (%)`} type="number" min="0" max="5" step="0.001" disabled={!custom} value={values[key]??''} onChange={e=>update({...values,[key]:e.target.value},true)}/><small>{custom?'사용자 검사값':origins[profile.field_sources[key]]||'추정 비용 가정'}</small></label>)}</div>
      <p>왕복 수수료 {Number((Number(values.buy_fee_rate)+Number(values.sell_fee_rate)).toFixed(6))}% · 비용 합계 {Number(total.toFixed(6))}% (진입·청산 금액이 같을 때). 결과에서는 실제 모의 진입·청산 금액으로 계산합니다. 펀딩비·시장충격은 별도 미모델링입니다.</p>
      {profile.warnings.map((warning:string)=><p key={warning}>{warning}</p>)}
      {String(profile.reference_url).startsWith('https://') && <a href={profile.reference_url} target="_blank" rel="noreferrer">요율 참고 출처 · 실제 계정 요율 확인 필요</a>}
    </>}
  </fieldset>;
}

export function ReplayCostEvidence({profile}: {profile:any}) {
  return !profile ? <p>구버전 비용 구성 미기록 · 현재 요율을 과거 결과에 소급하지 않습니다.</p> : <div data-testid="replay-cost-evidence"><strong>검사 당시 비용 가정 · {profile.venue} / {profile.product} · 추정값</strong><p>{Object.entries(labels).map(([key,label])=>`${label} ${Number((Number(profile.rates[key])*100).toFixed(6))}%`).join(' · ')}</p><p>기준 왕복 비용 {profile.round_trip_cost_percent}% · 펀딩비 미포함 · 계정 확정 요율 아님</p></div>;
}
