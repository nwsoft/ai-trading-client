// Development-only browser fixture. No gateway, credentials or real orders.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { StrategyStudio } from '../src/components/StrategyStudio';
import { StorageMaintenancePanel } from '../src/components/StorageMaintenancePanel';
import { RecordRecoveryPanel } from '../src/components/RecordRecoveryPanel';
import { SourceWorkspace } from '../src/components/LegacyFeatureWorkspaces';
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
let validationCalls = 0;
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
  workspace: async () => ({ paper_positions_status:paperState, paper_positions:paperState==='success' ? [{symbol:'PAPER-FIXTURE',quantity:1,entry_price:10}] : [], membership_access: membershipDenied ? {exchange:stock?'kis':'bybit',status:stock?'stock_plan_required':'pending',label:stock?'현재 회원등급은 주식·ETF 거래를 지원하지 않음':'UID 귀속 확인 대기',allowed:false}:undefined, paper_statistics:{closed_count:2,win_rate:50,pnl_by_currency:{[stock?'KRW':'USDT']:1}},paper_trades:[],statistics:[],active_custom_strategies:[] }),
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
  submitStrategy: async (payload: any) => { (window as any).__qaSubmitted = payload; const v=version('new','analyzed');versions.push(v);return v;},
  strategyAction: async (p: any) => { (window as any).__qaStrategyActions = [...((window as any).__qaStrategyActions ?? []),p]; const v=versions.find(v=>v.version_id===p.version_id); if(p.action==='approve')v.status='approved';if(p.action==='start_paper'){v.status='paper_observing';v.paper_observing=true;}return {...v}; },
  runHistoricalValidation: async (p: any) => { (window as any).__qaReplayRequests = [...((window as any).__qaReplayRequests ?? []),p]; const v=versions.find(v=>v.version_id===p.version_id);v.status='execution_validated';v.execution_validation={mode:'historical_replay',passed:true,metrics:{validation_interval:rules.decision_timeframe,candle_count:200}};return {...v}; },
};
document.body.style.overflow='auto';
document.body.style.height='auto';
const sourceView = new URLSearchParams(location.search).get('view') === 'source';
const storageView = new URLSearchParams(location.search).get('view') === 'storage';
const recoveryView = new URLSearchParams(location.search).get('view') === 'recovery';
const connected = new URLSearchParams(location.search).get('connected') !== '0';
const runtime: any = {running_sources:[],enabled_sources:[venue],credential_status:{[venue]:connected},execution_modes:{[venue]:mode},paper_trading:mode==='paper'};
createRoot(document.getElementById('root')!).render(<main style={{height:'100vh',overflow:'auto',padding:12}}>{membershipDenied && <output data-testid="membership-error-copy">{userFacingGatewayError(`membership_exchange_approval_pending:${venue}`, 409)}</output>}{recoveryView ? <RecordRecoveryPanel client={client} initialSource={venue} /> : storageView ? <StorageMaintenancePanel client={client} /> : sourceView ? <SourceWorkspace client={client} runtime={runtime} service={stock?'stock':'blockchain'} source={venue} onOpenManual={()=>{}} onOpenSettings={()=>{}} onRuntimeChanged={()=>{}} onAskAssistant={question=>{(window as any).__qaAssistantQuestion=question;}} /> : <StrategyStudio client={client} service={stock ? 'stock' : 'blockchain'} source={venue} />}</main>);
