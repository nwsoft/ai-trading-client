"""Loopback-only isolated gateway for manual inspection of the real Electron app.
No credentials, accounts, markets, providers, LIVE orders or customer data.
"""
import sys,json,tempfile,socket,datetime
from pathlib import Path
from types import SimpleNamespace
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
import uvicorn
from fastapi.responses import JSONResponse
from trading.insurance_workspace import InsuranceWorkspace
from trading.opportunity_coordinator import OpportunityCoordinator
from trading.paper_capital import paper_available_funds,remember_capital
from web_platform.runtime_bridge import HeadlessRuntimeBridge
from web_platform.application_services import ApplicationServices
from web_platform.gateway import create_gateway_app
from web_platform import companion
from config.app_version import RELEASE_VERSION,RELEASE_BUILD_LABEL
TOKEN='native-fixture-noahai-token-20261012'
with tempfile.TemporaryDirectory(prefix='noah-native-inspection-') as directory:
    data=Path(directory);running={'binance'};account='qa-native'
    owner=SimpleNamespace(settings={'paper_trading':True},recorder=SimpleNamespace(db_path=str(data/'trading.db')),_opportunity_account=account,
        paper_active_positions={},paper_positions={},_opportunity_coordinator=OpportunityCoordinator(data/'runtime.db'))
    ledger=data/'strategy_paper_outcomes.jsonl';ledger.write_text(json.dumps({'event_id':'synthetic-legacy','exchange':'binance','execution_mode':'paper','net_pnl':5})+'\n')
    remember_capital(owner,venue='binance',mode='paper',funds=paper_available_funds(1000,{},venue='binance',quote='USDT',ledger_file=ledger))
    bridge=HeadlessRuntimeBridge(account=account);bridge._app=SimpleNamespace(trader=owner,unified_trader=owner,settings=owner.settings,running_crypto_exchanges=lambda:list(running))
    vault=InsuranceWorkspace(data,account);vault.unlock('synthetic-native-vault-password')
    services=ApplicationServices.__new__(ApplicationServices);services.account=account;services.runtime_bridge=bridge
    services.insurance_workspace=lambda:vault
    def runtime():return {'enabled_sources':['binance'],'running_sources':list(running),'selected_sources':{'blockchain':'binance','stock':'kis'},'credential_status':{},'paper_trading':True,'mode':'manual'}
    services.runtime_snapshot=runtime
    def briefing():return companion.build_briefing(operations=bridge.operation_overview_snapshot(service='blockchain'),account={},finance=None,catalog={},market={},plans={},now=datetime.datetime.now(datetime.timezone.utc))
    services.companion_briefing=briefing
    services.companion_query=lambda question,service='blockchain':companion.query(question,briefing(),{},service=service)
    app=create_gateway_app(token=TOKEN,application_services=services)
    @app.middleware('http')
    async def fixture_only(request,call_next):
        ep=request.url.path
        if request.method=='OPTIONS':return await call_next(request)
        if ep.startswith('/api/') and ep!='/api/v1/health' and request.headers.get('authorization')!='Bearer '+TOKEN:return JSONResponse({'detail':'unauthorized'},401)
        payload=None
        if request.method=='GET':
            if ep.endswith('/platform'):payload={'release_version':RELEASE_VERSION,'release_label':RELEASE_BUILD_LABEL+' · 격리 검증'}
            elif ep.endswith('/session'):payload={'authenticated':True,'account':account,'user':{'id':account,'user_grade':'premium','nickname':'검증 전용'}}
            elif ep.endswith('/features'):payload=json.loads((root/'config/web_ui_feature_inventory.json').read_text())
            elif ep.endswith('/display-preferences'):payload={'saved':False,'locale':'ko'}
            elif ep.endswith('/runtime/snapshot'):payload=runtime()
            elif ep.endswith('/settings'):payload={'fields':[],'revision':'synthetic-only'}
            elif ep.endswith('/assistant/status'):payload={'budget':{'daily_used':0,'daily_limit':30,'monthly_used':0,'monthly_limit':500}}
            elif ep.endswith('/audit/export'):payload={'records':[]}
            elif ep.endswith('/product-intelligence'):payload={'products':[],'reference_products':[],'plans':[],'reviews':[],'state':'locked'}
            elif ep.endswith('/portfolio/analysis'):payload={'allocation_by_currency':{},'performance_by_currency':{},'positions':[],'account_status':{}}
            elif ep.startswith('/api/v1/workspaces/'):
                source=request.query_params.get('source','binance');payload={'source':source,'trading':{'execution_mode':'paper'},'logs':[],'statistics':[],'paper_positions':[],
                    'ai_decisions':[],'ai_analysis':[],'risk':[],'operation_summary':bridge.operation_summary_snapshot(source=source),
                    'scenario':{'available_currencies':[],'policy':{},'scopes':{'all':{'sample_count':0,'scenarios':[]}}}}
            elif ep.endswith('/strategies'):payload={'strategies':[],'min_paper_trades':3,'hub_available':False}
            elif ep.endswith('/logs'):payload={'lines':[],'entries':[],'sources':[],'categories':[],'levels':[]}
            elif ep.startswith('/api/v1/life-finance') and not ep.endswith('/insurance'):payload={'summary':{},'transactions':[],'goals':[],'alerts':[],'rows':[],'analysis':{},'cash_flow':{},'monthly':[]}
        if payload is not None:
            return JSONResponse(payload,headers={'Cache-Control':'no-store','Access-Control-Allow-Origin':'noahai://app'})
        if request.method=='POST' and ep=='/api/v1/runtime/commands':
            body=await request.json()
            if body.get('action')=='trading.stop' or body.get('command')=='trading.stop':running.discard(body.get('source','binance'));return JSONResponse({'accepted':True},headers={'Access-Control-Allow-Origin':'noahai://app'})
            return JSONResponse({'detail':'qa_trading_disabled'},409,headers={'Access-Control-Allow-Origin':'noahai://app'})
        if request.method!='GET' and ep not in {'/api/v1/life-finance/insurance','/api/v1/assistant/ask','/api/v1/companion/query','/api/v1/maintenance/paper-session'}:
            return JSONResponse({'detail':'qa_external_mutation_disabled'},409,headers={'Access-Control-Allow-Origin':'noahai://app'})
        return await call_next(request)
    sock=socket.socket();sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);sock.bind(('127.0.0.1',int(sys.argv[1]) if len(sys.argv)>1 else 0));sock.listen(128)
    print(sock.getsockname()[1],flush=True)
    try:uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False)).run(sockets=[sock])
    finally:vault.lock();sock.close()
