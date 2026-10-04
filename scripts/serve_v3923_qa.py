import sys,tempfile,json
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trading.finance_product_intelligence import ProductCatalog,compare_scenario
from trading.insurance_workspace import InsuranceWorkspace
from trading.profitability_validation import ProfitabilityValidator
from web_platform.gateway import create_gateway_app
from trading.finance_handoff import FinanceHandoff
from web_platform.interactive_ai import InteractiveAIService
root=Path(tempfile.mkdtemp(prefix='v3923-synthetic-'))
calls={'ai':0,'submit':0,'status':0,'withdraw':0}
def handoff_transport(recipient,action,payload,key):
 calls[action]+=1
 return {'request_id':payload['request_id'],'status':'withdrawn' if action=='withdraw' else 'received','receipt_id':'synthetic-ui-receipt'}
class SyntheticVault(InsuranceWorkspace):
 def finance_handoff(self,operation='list',**kwargs):
  return FinanceHandoff(self,handoff_transport).dispatch(operation,**kwargs)
recipients=[]
for mode in ('manual','api'):
 recipients.append({'id':'synthetic-'+mode,'name':'시험 상담사 '+mode,'organization':'합성 시험','role':'UI 검증 전용',
  'kinds':['loan','insurance','savings'],'mode':mode,'enabled':True,'review_reference':'synthetic-only',
  'contract_version':'fixture-1','retention_days':30,'privacy_url':'https://example.org/privacy','contact_url':'https://example.org/contact',
  'endpoints':{k:'https://example.org/'+k for k in ('submit','status','withdraw')},'token_env':'NOAHAI_FINANCE_TEST_TOKEN'})
(root/'finance_recipients.json').write_text(json.dumps(recipients))
catalog=ProductCatalog(root/'finance_product_catalog.sqlite3');vault=SyntheticVault(root,'synthetic-ui')
def ai_chat(*args,**kwargs):
 calls['ai']+=1
 return SimpleNamespace(ok=True,content='입력한 비교 결과입니다. 추가 비용과 기관 조건을 확인하세요.',provider='synthetic',model='fixture',usage={})
router=SimpleNamespace(spec=SimpleNamespace(provider='synthetic'),adapter=SimpleNamespace(is_ready=lambda:True,model='fixture',chat_text=ai_chat))
ai=InteractiveAIService(data_dir=root,router_factory=lambda *a,**k:router)
def diagnose(source):
 report=ProfitabilityValidator().evaluate_strategy([{'return_fraction':-.001}]*20)
 report.update(status='evaluated',source=source,sample_days=45,sample_limit=300,policy_origins={'underperformance_mode':'validator_default'})
 return report
def product_intelligence(payload=None):
 if payload and payload.get('action')=='discover':
  from trading.finance_discovery import discover
  return discover(payload,catalog.snapshot())
 if payload and payload.get('action')=='refresh':return catalog.refresh_feeds(force=True)
 if payload and payload.get('action')=='dialogue':
  from trading.finance_product_dialogue import revise_scenario
  return revise_scenario(payload.get('scenario'),payload.get('question'),catalog.snapshot())
 if payload and payload.get('action') in {'ai_preview','ai_explain'}:
  from web_platform.finance_ai import preview,explain
  return preview(ai,{},payload['scenario'],payload['question'],catalog.snapshot(),payload['scopes'],payload.get('workload','assistant')) if payload['action']=='ai_preview' else explain(ai,{},payload,catalog.snapshot())
 return catalog.snapshot() if payload is None else compare_scenario(payload,catalog.snapshot())
services=SimpleNamespace(account='synthetic-ui',runtime_snapshot=lambda:{},insurance_workspace=lambda:vault,
 product_intelligence=product_intelligence,
 runtime_bridge=SimpleNamespace(profitability_diagnostic=diagnose))
import web_platform.gateway as gateway_module
gateway_module.ALLOWED_ORIGINS = (*gateway_module.ALLOWED_ORIGINS, 'http://127.0.0.1:4193')
app=create_gateway_app(token='synthetic-v3923-token-for-local-qa-only',application_services=services)
@app.get('/qa-counters')
def qa_counters():return calls
if __name__=='__main__':
 import uvicorn
 uvicorn.run(app,host='127.0.0.1',port=3919,log_level='warning')
