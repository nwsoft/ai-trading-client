const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
const ts=require(process.env.NOAHAI_QA_TYPESCRIPT||'../webui/node_modules/typescript');
const file=path.join(__dirname,'../webui/src/startDiagnostics.ts');
const m=new Module(file,module);m._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,file);
const {startDiagnostic,startGuidance,GatewayRequestError}=m.exports;
test('six venues retain request-correlated safe stage without exposing raw detail',()=>{
 for(const venue of ['okx','bybit','bitget','upbit','bithumb','coinone']){
  const d=startDiagnostic(`runtime_start_exception:${venue}:market_observation`,'4f9ff0b8fc574c5d8407b79834c86f06',409);
  assert.equal(d.code,'runtime_start_exception');assert.equal(d.stage,'market_observation');assert.equal(d.status,409);
  assert.ok(new GatewayRequestError('localized text',d) instanceof Error);
 }
 for(const input of ['SECRET raw error', {code:'SECRET',stage:'APIKEY',balance:500},null,{},true]){
  assert.deepEqual(startDiagnostic(input,'invalid key',200),{code:'start_reason_not_recorded',stage:'unknown',requestId:'미기록',status:null});
 }
});
test('PAPER failures never prescribe or read LIVE journal recovery',()=>{
 for(const code of ['exchange_initialization_failed','trading_candidates_unavailable','runtime_start_exception','risk_data_unavailable','managed_position_reconciliation_required', 'trading_candidate_catalogue_unavailable', 'trading_candidate_markets_unavailable', 'trading_candidate_tickers_unavailable', 'trading_candidate_filters_excluded']){
  assert.equal(startGuidance(code,'paper').recovery,false);
  assert.equal(startDiagnostic(code+':okx:candidate_selection').code,code);
 }
 assert.equal(startGuidance('managed_position_reconciliation_required','live').recovery,true);
 assert.equal(startGuidance('daily_loss_limit_exceeded','live').recovery,false);
 assert.equal(startDiagnostic('risk_data_unavailable:managed_position_reconciliation_required:recovery_unavailable').code,'managed_position_reconciliation_required');
 assert.match(startGuidance('runtime_request_timeout','paper').action,/미확정/);
 for(const code of ['runtime_source_stopping','runtime_start_cancelled']){
  assert.equal(startDiagnostic(code+':okx:worker_start').code,code);
  assert.equal(startGuidance(code,'paper').recovery,false);
 }
 assert.match(startGuidance('runtime_start_cancelled','paper').action,/자동 재시작하지 않습니다/);
});
test('report UI uses original evidence and only conditional recovery',()=>{
 const ui=fs.readFileSync(path.join(__dirname,'../webui/src/components/TradingStartHelp.tsx'),'utf8');
 assert.match(ui,/if \(guidance.recovery\) try/);assert.match(ui,/guidance.recovery &&/);
 assert.doesNotMatch(ui,/start_refused_check_displayed_reason/);
 assert.match(ui,/evidence.requestId/);assert.match(ui,/시작 응답과 별도 조회/);
});
