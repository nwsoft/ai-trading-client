"""Synthetic v3924 decisions on the existing authenticated QA gateway."""
import sys,json
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.serve_v3923_qa import app,ai,calls,services
from trading.ai.provider_router import ProviderResponse
from web_platform.finance_decision import decision_status,preview,decide
settings={'ai_provider_profiles':{'finance_decision':{'provider':'openai','model':'gpt-6-luna'}},'ai_credentials':{}};revision=0;calls['decision']=0
old_factory=ai.router_factory
old_product=services.product_intelligence

def factory(config,**kwargs):
 if kwargs.get('workload')!='finance_decision':return old_factory(config,**kwargs)
 route=config['ai_provider_profiles']['finance_decision']
 def chat(system,user,**options):
  calls['decision']+=1
  question=json.loads(user)['question']
  value={'goal':'driver','insurance_state':'none','goal_evidence':'차를 몰고','state_evidence':'보험은 없어요','needs_clarification':False}
  if '불확실' in question:value={'goal':'unknown','insurance_state':'unknown','goal_evidence':'','state_evidence':'','needs_clarification':True}
  if '형식오류' in question:value={'goal':'trade_approved','confidence':.99}
  return ProviderResponse(provider=route['provider'],model=route['model'],content=value,usage={'input_tokens':60,'output_tokens':35},finish_reason='stop')
 return SimpleNamespace(spec=SimpleNamespace(provider=route['provider']),adapter=SimpleNamespace(model=route['model'],is_ready=lambda:True,chat_json=chat))
ai.router_factory=factory

def product(payload=None):
 if payload and payload.get('action') in {'decision_status','decision_options'}:return decision_status(settings)
 if payload and payload.get('action')=='decision_preview':return preview(ai,settings,payload)
 if payload and payload.get('action')=='decision_run':return decide(ai,settings,payload)
 return old_product(payload)
services.product_intelligence=product

def snapshot():
 from trading.ai.model_registry import selectable_models
 from web_platform.application_services import EDITABLE_SETTINGS
 fields=[]
 for field in EDITABLE_SETTINGS:
  if not field.path.startswith('ai_provider_profiles.finance_decision.'):continue
  value=settings['ai_provider_profiles']['finance_decision'][field.path.rsplit('.',1)[1]]
  fields.append({'path':field.path,'label':field.label,'help':field.help,'section':'ai_engine','group':'AI 엔진','presentation':'primary','kind':field.kind,'value':value,'default':value,'options':list(field.options),'risk':'normal'})
 return {'schema_version':'qa','revision':f'{revision:064x}','account_scope':'synthetic-ui','fields':fields,
         'save_receipt':{'verified':True},
         'credential_status':{f'ai:{p}':bool(settings['ai_credentials'].get(p,{}).get('api_key')) for p in ['openai','gemini','deepseek','anthropic','kimi']},
         'model_catalogs':{p:{'chat_json':list(selectable_models(p,capability='chat_json'))} for p in ['openai','gemini','deepseek','anthropic','kimi']}}
def update(*,expected_revision,changes):
 global revision
 assert expected_revision==f'{revision:064x}'
 for key,value in changes.items():
  assert key.startswith('ai_provider_profiles.finance_decision.')
  settings.setdefault('ai_provider_profiles',{}).setdefault('finance_decision',{})[key.rsplit('.',1)[1]]=value
 revision+=1
 return snapshot()
def update_credentials(*,expected_revision,provider,values):
 global revision
 assert expected_revision==f'{revision:064x}' and provider in {'openai','gemini','deepseek','anthropic','kimi'}
 # QA-only dummy values stay in memory; never read/write user configuration.
 assert all(not v or v.startswith('synthetic-') for v in values.values())
 settings['ai_credentials'][provider]=dict(values);revision+=1
 return snapshot()
services.update_credentials=update_credentials
services.settings_snapshot=snapshot
services.update_settings=update
if __name__=='__main__':
 import uvicorn
 uvicorn.run(app,host='127.0.0.1',port=3919,log_level='warning')
