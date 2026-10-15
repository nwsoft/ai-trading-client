// Development-only browser fixture. No gateway, credentials or real orders.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { StrategyStudio } from '../src/components/StrategyStudio';
import { StorageMaintenancePanel } from '../src/components/StorageMaintenancePanel';
import { RecordRecoveryPanel } from '../src/components/RecordRecoveryPanel';
import { StrategyBatchImport } from '../src/components/StrategyBatchImport';
import { TradingStatisticsWorkspace } from '../src/components/TradingStatisticsWorkspace';
import { OperationSummary } from '../src/components/OperationSummary';
import { AssetInfoWorkspace, LegacyAILearningWorkspace, SourceWorkspace } from '../src/components/LegacyFeatureWorkspaces';
import { userFacingGatewayError, createGatewayClient } from '../src/api';
import '../src/styles.css';

(window as any).__qaGatewayError = userFacingGatewayError;
(window as any).__qaCreateGateway = createGatewayClient;

const stock = new URLSearchParams(location.search).get('service') === 'stock';
const membershipDenied = new URLSearchParams(location.search).get('denied') === '1';
const venue = new URLSearchParams(location.search).get('venue') || (stock ? 'kis' : 'binance');
const mode = new URLSearchParams(location.search).get('mode') || 'paper';
const paperState = new URLSearchParams(location.search).get('paper_state') || 'pending';
const rules = { entry: 'RSI 30 이하 LONG', exit: 'RSI 55 이상 청산', stop_loss: '1%', take_profit: '2%', position_size: '5%', market_conditions: ['range'], market_regimes: ['range'], signal_mode: 'independent', entry_signal: 'LONG', decision_timeframe: stock ? '1d' : '15m', engine_settings: { _unit: 'percent_points', tp_percent: 2, sl_percent: 1 }, executable_entry: { all: [{ field: 'rsi', operator: 'lte', value: 30 }] }, executable_exit: { all: [{ field: 'rsi', operator: 'gte', value: 55 }] } };
const readiness = { ready: true, historical_validation_applicable: true, validation_subject: 'custom_entry_logic', reasons: [] };
Object.assign(rules, {target_scope:stock ? 'asset:stock' : 'exchange:binance'});
const version = (id: string, status: string) => ({ version: 1, version_id: id, strategy_key: id, name: 'QA 추세 따라가기', status, active: false, paper_observing: false, missing_conditions: [], rules, created_at: '2026-09-13T08:39:25Z', xai: { summary: '구조화 완료 · 승인 후 검증합니다.' }, execution_readiness: readiness, paper_execution_readiness: readiness, version_diff: { changes: Array.from({length:76}, (_, i) => ({field:String(i)})) } });
const versions: any[] = [version('paused', 'paper_paused')];
const controlState = new URLSearchParams(location.search).get('control_state');
if (controlState) {
  versions[0].status=controlState;
  versions[0].active=controlState==='active';
  versions[0].paper_observing=controlState==='paper_observing';
  if(['active','paper_validated'].includes(controlState)) versions[0].paper_validation={passed:true,trades:3,metrics:{observation_days:7}};
}
const trialState = new URLSearchParams(location.search).get('trial');
if (trialState) {
  const v=versions[0]; const ready=trialState==='ready';
  Object.assign(v,{status:'paper_observing',paper_observing:true,
    paper_observation_started_at:'2026-10-10T00:00:00Z',paper_trial:{schema_version:2,target_days:3,auto_stop:false},
    paper_validation:{passed:ready,trades:ready?3:2},
    paper_progress:{trades:ready?3:2,required_trades:3,required_days:0,target_days:3,period_is_gate:false,
      target_reached:true,permission_elapsed_seconds:259210,
      runtime:trialState==='missing'?{status:'not_recorded',seconds:null}:{status:'observed',seconds:1.25,evaluations:4,last_evaluated_at:'2026-10-14T01:02:03Z'},
      promotion:{ready,sample_passed:ready,risk_passed:ready,guardrail_violations:0,unknown_risk_records:ready?0:1,unverified_trades:0}}});
}
const replayState = new URLSearchParams(location.search).get('replay_state');
if (replayState) {
  versions[0].status = replayState;
  if (replayState !== 'approved') versions[0].execution_validation = {
    mode:'historical_replay',passed:false,guardrail_violations:0,
    metrics:{assessment_status:'no_trades',quality_passed:false,decisions:0,net_pnl_percent:0,
      assumptions:{entry_price:'signal_bar_close',maximum_holding_bars:12}}
  };
}
if (new URLSearchParams(location.search).get('repair') === '1') {
  versions[0].rules = {...rules, signal_mode:'confirm', executable_entry:{all:[],any:[]},
    source_evidence:{kind:'text',text:'기존 문서의 유동성 반전 진입'}, source_grounding:{status:'compiler_authoritative'}};
  versions[0].execution_readiness = versions[0].paper_execution_readiness = {ready:false,reasons:['confirm_executable_entry_missing']};
}
if (new URLSearchParams(location.search).get('named_repair') === '1') {
  versions[0].rules = {...versions[0].rules, source_evidence:{kind:'text',text:'ENTRY:\nconfirmed_setup\nEXIT:\nrsi >= 65\nRISK:\n15분봉, 손절 1%, 익절 2%, 자산 5%, 횡보장.'}};
}
(window as any).__qaOriginalVersions = JSON.stringify(versions);
if(new URLSearchParams(location.search).get('catalog')==='1'){
  versions.splice(0,versions.length,...['Charlie','Alpha','Beta'].map((name,i)=>({...version(`key-${i}`,'analyzed'),name,created_at:`2026-09-${21+i}T00:00:00Z`,active:i===0,paper_observing:i===1,paper_validation:i===2?{passed:true,trades:10}:undefined})));
}
if(new URLSearchParams(location.search).get('runtime_unsupported')==='1')versions[0].runtime_support={status:'stock_timeframe_unsupported',timeframe:'5m',affected_brokers:['mirae','shinhan'],supported_brokers:['kiwoom','kis'],message:'증권 5m 분봉: 키움·한국투자에서 완료봉을 조회해 평가합니다. 한국투자 모의 서버는 당일 자료만 제공합니다. 자료 수집 중/부족은 진입 근거 미확보로 표시하며 일봉으로 대체하지 않습니다. 미지원 기관: mirae, shinhan.',grants_execution:false};
let validationCalls = 0;
const view=new URLSearchParams(location.search).get('view');
const stats={execution_mode:'paper',closed_count:2,win_rate:50,groups:[{source:venue,settlement_currency:'USDT',closed_count:2,reconciled_closed_count:2,win_rate:50,net_pnl:1,fees:0.2,rows:[]}],range:{},pnl_by_currency:{USDT:1},fees_by_currency:{USDT:.2}};
const qaExtra={stock_candidates:new URLSearchParams(location.search).get('empty')==='1'?[]:[{source:venue,symbol:'005930',score:63,signal:'HOLD',reason:'synthetic risk hold',observed_at:1792022400}],selected_coins:[{symbol:'BTCUSDT',technical_score:null,overall_score:75,volume_score:90,trend_score:60}],learning:{source:'synthetic isolated',records:Array.from({length:120},(_,i)=>({id:i,symbol:'005930',signal:'HOLD',confidence:.7,rsi:43,macd:.1,trend:'range',reason:'synthetic evidence',timestamp:'2026-10-15T01:02:03Z'}))},trading_statistics:stats};
if(new URLSearchParams(location.search).get('live_evidence')==='1')versions[0].live_performance={status:'observed',groups:[{exchange:venue,settlement_currency:'USDT',recorded_closes:3,confirmed_closes:2,win_rate:50,net_pnl:1,recorded_costs:.2,cost_records:2}]};
const client: any = {
  replayCosts: async (source:string,asset:string)=>({venue:source,product:asset==='crypto'?'futures':asset,rates:{buy_fee_rate:.0005,sell_fee_rate:.0005,buy_slippage_rate:.0002,sell_slippage_rate:.0002,spread_rate:.0001,sell_tax_rate:0},field_sources:{},warnings:['QA estimate'],reference_url:''}),
  recoveryStatement: async (payload:any) => {
    (window as any).__qaStatementRequests=[...((window as any).__qaStatementRequests||[]),payload];
    const response=await fetch('/qa-statement',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    return response.json();
  },
  runtimeCommand: async (...args: any[]) => { (window as any).__qaRuntimeCommands = [...((window as any).__qaRuntimeCommands ?? []), args];
    if (new URLSearchParams(location.search).get('start_error') === '1') throw new Error(userFacingGatewayError('risk_data_unavailable:managed_position_reconciliation_required',409)+' 요청 ID: qa-start-123456789');
    return {}; },
  platform: async () => ({release_version:'3.9.1.47'}),
  storageMaintenance: async () => ({state:'paused', error:'writer_busy_continue_later', log_bytes:1024, log_budget_bytes:536870912,
    learning_bytes:2048, db_bytes:2878898176, record_writes:{pending:1,needs_review:0},
    writer_activity:{max_hold_ms:37.61,max_wait_ms:66.94,waiting_writers:2}, decision_rows_checked:9100, archived_rows:0}),
  workspace: async () => ({ ...qaExtra, paper_positions_status:paperState, paper_positions:paperState==='success' ? [{symbol:'PAPER-FIXTURE',quantity:1,entry_price:10}] : [], membership_access: membershipDenied ? {exchange:stock?'kis':'bybit',status:stock?'stock_plan_required':'pending',label:stock?'현재 회원등급은 주식·ETF 거래를 지원하지 않음':'UID 귀속 확인 대기',allowed:false}:undefined, paper_statistics:{closed_count:2,win_rate:50,pnl_by_currency:{[stock?'KRW':'USDT']:1}},paper_trades:[],statistics:[],active_custom_strategies:[] }),
  stockSearchProfile:async()=>({}), stockSuggestions:async()=>({suggestions:[]}),
  logs: async () => ({lines:[{source:stock?'kis':'binance',message:'QA PAPER · 합성 연결 로그'}]}),
  refreshAccounts: async (sources: string[]) => { (window as any).__qaAccountQueries = sources; return {sources:{[venue]:{status:new URLSearchParams(location.search).get('account_status') || 'success',balance:{},positions:[]}}}; },
  recordRecovery: async (source: string, start = false) => {
    if (start) (window as any).__qaRecoveryStart = source;
    const complete = Boolean((window as any).__qaRecoveryStart);
    return {source,state:complete?'checked':'needs_evidence',total:1,processed:1,recovered:complete?1:0,remaining:complete?0:1,auto_started:false,resume_authorized:false,
      reasons:complete?{}:{provider_connection_required:1},next_actions:complete?{}:{provider_connection_required:{action_ko:'기관 연결을 확인한 뒤 점검하세요.',action_en:'Check the connection then run recovery.',retry_without_new_evidence:true}}};
  },
  strategies: async () => ({ strategies: versions.map(v => ({scope: stock ? 'unified' : 'binance', strategy_key: v.strategy_key, versions:[v]})) }),
  settings: async () => ({ fields: [{path:'ai_custom_features.profile',value:new URLSearchParams(location.search).get('profile') || 'advanced'},{path:'paper_trading',value:true}] }),
  strategyMentor: async () => ({ candidates: [{ name: 'QA 예제', preset_key:'trend', source_text:'RSI 30 이하 LONG, 손절 1%, 익절 2%, 15분봉', draft_rules: rules, draft_analysis:{ rules, ready_for_execution:true, missing_conditions:[], source:{kind:'text'} } }] }),
  analyzeStrategySource: async (payload: any) => {
    (window as any).__qaSourcePayload = payload;
    if((window as any).__qaFailOnce){(window as any).__qaFailOnce=false;throw new Error('QA 자료 분석 일시 실패');}
    if ((window as any).__qaAnalyze) return (window as any).__qaAnalyze(payload);
    return { rules, ready_for_execution:true, missing_conditions:[], source:{kind:payload.files?.length?'bundle':'text'}, summary:'QA 원문 구조화 완료',
      source_manifest: (payload.files ?? []).map((f: any,i: number)=>({id:`S${i+1}`,name:f.name,included_characters:50,extracted_characters:50,warnings:[]})) };
  },
  driveAuthorization: async (action?:string) => {
    (window as any).__qaDriveAction=action || 'status';
    if (action==='connect') return {pending:true,authorization_ready:true};
    return {connected:action!=='disconnect',authorization_ready:true};
  },
  validateStrategyDraft: async (payload: any) => (window as any).__qaValidate ? (window as any).__qaValidate(payload) : ++validationCalls === 1 ? ({ ready:false, blocking_details:[{code:'qa_missing',title:'거래 위험예산을 확인하세요',action:'원문 또는 보완 답변에 자신의 위험예산을 적고 다시 분석하세요.',example:'거래당 손실 0.5%'}] }) : ({ready:true,rules:payload.rules}),
  submitStrategy: async (payload: any) => { (window as any).__qaSubmitted = payload; const id=(window as any).__qaSubmits?.length ? `new-${(window as any).__qaSubmits.length+1}`:'new';(window as any).__qaSubmits=[...((window as any).__qaSubmits||[]),payload];if((window as any).__qaSubmitLost)throw new Error('synthetic response lost');const v={...version(id,'analyzed'),name:payload.name,rules:payload.rules};versions.push(v);return v;},
  strategyAction: async (p: any) => { (window as any).__qaStrategyActions = [...((window as any).__qaStrategyActions ?? []),p]; const v=versions.find(v=>v.version_id===p.version_id); if(p.action==='deactivate'){v.status='paper_validated';v.active=false;v.deactivated={at:new Date().toISOString()};}if(p.action==='activate'){v.status='active';v.active=true;v.paper_observing=false;}if(p.action==='stop_paper'){v.status='paper_paused';v.paper_observing=false;}if(p.action==='approve')v.status='approved';if(['start_paper','restart_paper'].includes(p.action)){v.status='paper_observing';v.paper_observing=true;v.paper_trial={schema_version:2,target_days:p.trial_days||7,auto_stop:false};if(v.paper_progress){v.paper_progress.target_days=p.trial_days||7;v.paper_progress.target_reached=v.paper_progress.permission_elapsed_seconds>=(p.trial_days||7)*86400;}}return {...v}; },
  runHistoricalValidation: async (p: any) => { (window as any).__qaReplayRequests = [...((window as any).__qaReplayRequests ?? []),p]; const v=versions.find(v=>v.version_id===p.version_id);v.status='execution_validated';v.execution_validation={mode:'historical_replay',passed:true,metrics:{validation_interval:rules.decision_timeframe,candle_count:200}};return {...v}; },
};
document.body.style.overflow='auto';
document.body.style.height='auto';
const sourceView = new URLSearchParams(location.search).get('view') === 'source';
const storageView = new URLSearchParams(location.search).get('view') === 'storage';
const recoveryView = new URLSearchParams(location.search).get('view') === 'recovery';
const connected = new URLSearchParams(location.search).get('connected') !== '0';
const runtime: any = {running_sources:[],enabled_sources:[venue],credential_status:{[venue]:connected},execution_modes:{[venue]:mode},paper_trading:mode==='paper'};
function BatchFixture(){const [files,setFiles]=React.useState<File[]>([]);return <><input type="file" multiple onChange={e=>setFiles(Array.from(e.target.files||[]))}/><StrategyBatchImport client={client} files={files} scope="binance" defaultTarget="exchange:binance" disabled={false} onComplete={(id,count)=>{(window as any).__qaBatchComplete={id,count};}}/></>;}
createRoot(document.getElementById('root')!).render(<main style={{height:'100vh',overflow:'auto',padding:12}}>{membershipDenied && <output data-testid="membership-error-copy">{userFacingGatewayError(`membership_exchange_approval_pending:${venue}`, 409)}</output>}{view==='batch'?<BatchFixture/>:view==='info'?<AssetInfoWorkspace client={client} service={stock?'stock':'blockchain'} source={venue} enabledSources={[venue]}/>:view==='learning'?<LegacyAILearningWorkspace client={client} service={stock?'stock':'blockchain'} source={venue} sources={[venue]}/>:view==='statistics'?<TradingStatisticsWorkspace client={client} runtime={runtime} service={stock?'stock':'blockchain'} sources={[venue]} defaultSource={venue}/>:view==='regime'?<OperationSummary source={venue} mode="paper" running={true} failed={false} data={{source:venue,mode:'paper',regime:{observed:'normal',confirmed:'normal',observed_at:1792022400,trend_threshold_percent:3,trend_change_percent:-1,rsi:40,rsi_bull_threshold:65,rsi_bear_threshold:35,volume_ratio:.8,volume_required:1.2,lookback_bars:10,symbol_basis:'representative',calculation_at:1792022400}}}/>:recoveryView ? <RecordRecoveryPanel client={client} initialSource={venue} /> : storageView ? <StorageMaintenancePanel client={client} /> : sourceView ? <SourceWorkspace client={client} runtime={runtime} service={stock?'stock':'blockchain'} source={venue} onOpenManual={()=>{}} onOpenSettings={()=>{}} onRuntimeChanged={()=>{}} onAskAssistant={question=>{(window as any).__qaAssistantQuestion=question;}} /> : <StrategyStudio client={client} service={stock ? 'stock' : 'blockchain'} source={venue} />}</main>);
