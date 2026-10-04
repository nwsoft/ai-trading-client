from copy import deepcopy
from types import SimpleNamespace
import json
import pytest
from web_platform.finance_decision import FAST_MODELS, decision_status, selected_settings, preview, decide, validate_decision
from web_platform.interactive_ai import InteractiveAIService
from trading.ai.provider_router import ProviderResponse

QUESTION='자동차로 출퇴근해요. 가입한 보험은 없어요.'
def valid():return {'goal':'driver','insurance_state':'none','goal_evidence':'자동차로 출퇴근','state_evidence':'가입한 보험은 없어요','needs_clarification':False}
def payload(provider='openai',model='gpt-6-luna'):
    return {'kind':'insurance','question':QUESTION,'selection':{'provider':provider,'model':model}}

def configured(p=None):
    selection=(p or payload())['selection']
    return {'ai_provider_profiles':{'finance_decision':deepcopy(selection)},
            'ai_credentials':{selection['provider']:{'api_key':'synthetic-local-key'}}}

def service(tmp_path,content=None):
    calls=[]
    def factory(settings,**kw):
        assert kw['workload']=='finance_decision'
        route=settings['ai_provider_profiles']['finance_decision']
        def chat(system,question,**options):
            calls.append({'system':system,'question':question,'options':options,'route':route})
            return ProviderResponse(provider=route['provider'],model=route['model'],content=deepcopy(content if content is not None else valid()),usage={'input_tokens':80,'output_tokens':40,'total_tokens':120},finish_reason='stop')
        return SimpleNamespace(spec=SimpleNamespace(provider=route['provider']),adapter=SimpleNamespace(model=route['model'],is_ready=lambda:True,chat_json=chat))
    return InteractiveAIService(data_dir=tmp_path,router_factory=factory),calls

@pytest.mark.parametrize('provider,model',FAST_MODELS.items())
def test_each_existing_provider_is_really_dispatched_as_json_with_budget_and_no_cache(tmp_path,provider,model):
    ai,calls=service(tmp_path);p=payload(provider,model)
    view=preview(ai,configured(p),p);assert not calls
    with pytest.raises(ValueError,match='consent|route_changed'):decide(ai,configured(p),p)
    p['consent']={'confirmed':True,'payload_hash':view['payload_hash']}
    result=decide(ai,configured(p),p)
    assert result['status']=='proposal' and result['applied'] is False and result['provider']==provider
    assert calls[0]['route']==p['selection'] and calls[0]['options']['timeout_seconds']==15
    assert calls[0]['options']['max_tokens']==400
    assert calls[0]['options'].get('reasoning_effort')==('none' if provider=='openai' else None)
    assert not ai.cache_path.exists() and QUESTION not in ai.usage_path.read_text()
    assert 'finance_decision' in ai.usage_path.read_text()

@pytest.mark.parametrize('change',[{'question':QUESTION+' 추가'}, {'kind':'loan'},{'selection':{'provider':'gemini','model':'gemini-3.5-flash-lite'}}])
def test_change_requires_new_preview(tmp_path,change):
    ai,calls=service(tmp_path);p=payload();v=preview(ai,configured(p),p);p['consent']={'confirmed':True,'payload_hash':v['payload_hash']};p.update(change)
    with pytest.raises(ValueError,match='consent|route_changed'):decide(ai,configured(p),p)
    assert not calls

@pytest.mark.parametrize('change',[{'goal':'approve_trade'},{'goal':[]},{'insurance_state':'approved'},{'needs_clarification':'false'},{'goal_evidence':'invented'},{'goal_evidence':''},{'state_evidence':''},{'confidence':.99},{'insurance_state':False}])
def test_invalid_output_falls_back_without_application(tmp_path,change):
    bad={**valid(),**change};ai,calls=service(tmp_path,bad);p=payload();v=preview(ai,configured(p),p);p['consent']={'confirmed':True,'payload_hash':v['payload_hash']}
    r=decide(ai,configured(p),p)
    assert r['status']=='local_fallback' and r['applied'] is False and len(calls)==1
    assert 'decision' not in r

@pytest.mark.parametrize('state',['none','existing'])
def test_savings_cannot_apply_insurance_state(state):
    with pytest.raises(ValueError):validate_decision({**valid(),'goal':'deposit','insurance_state':state},'savings',QUESTION)

def test_unknown_is_not_an_applicable_proposal(tmp_path):
    ai,calls=service(tmp_path,{**valid(),'goal':'unknown','goal_evidence':'','needs_clarification':True})
    p=payload();v=preview(ai,configured(p),p);p['consent']={'confirmed':True,'payload_hash':v['payload_hash']}
    assert decide(ai,configured(p),p)['status']=='needs_clarification'

@pytest.mark.parametrize('selection',[{'provider':'openrouter','model':'jev'},{'provider':'openai','model':'invented'},{'provider':'deepseek','model':'deepseek-chat'},{'provider':'openai','model':'gpt-4o-mini-transcribe'},{'provider':'openai','model':'gpt-6-luna','url':'https://invalid.test'}])
def test_unsupported_routes_never_construct_a_provider(selection):
    with pytest.raises(ValueError):selected_settings({},selection)

def test_selection_does_not_change_trading_or_persisted_settings():
    original={'ai_provider_profiles':{'analyst':{'provider':'deepseek','model':'deepseek-flash'}},'ai_model_roles':{'frequent_cheap':{'provider':'gemini','model':'gemini-3.5-flash-lite'}}}
    before=deepcopy(original);r=selected_settings(original,payload()['selection'])
    assert original==before and r['ai_model_roles']==before['ai_model_roles'] and r['ai_provider_profiles']['analyst']==before['ai_provider_profiles']['analyst']

def test_status_only_exposes_saved_route_and_key_presence_not_catalog_or_secrets():
    options=decision_status(configured())
    assert options['selection']==payload()['selection'] and options['can_request']
    assert not options['account_verified'] and not options['provider_called']
    assert 'models' not in options and 'synthetic-local-key' not in json.dumps(options)

@pytest.mark.parametrize('key',['','   ','********','<redacted>',None])
def test_missing_or_placeholder_key_blocks_before_preview_and_call(tmp_path,key):
    ai,calls=service(tmp_path);settings=configured();settings['ai_credentials']['openai']['api_key']=key
    assert not decision_status(settings)['can_request']
    with pytest.raises(ValueError,match='credential_missing'):preview(ai,settings,payload())
    assert not calls

def test_payload_cannot_override_saved_model_and_setting_change_invalidates_consent(tmp_path):
    ai,calls=service(tmp_path);settings=configured();p=payload()
    view=preview(ai,settings,p);p['consent']={'confirmed':True,'payload_hash':view['payload_hash']}
    with pytest.raises(ValueError,match='route_changed'):decide(ai,settings,{**p,'selection':payload('gemini','gemini-3.5-flash-lite')['selection']})
    p.pop('selection')
    changed=configured(payload('gemini','gemini-3.5-flash-lite'))
    with pytest.raises(ValueError,match='consent'):decide(ai,changed,p)
    assert not calls

def test_status_handles_legacy_key_owner_without_borrowing_other_provider_keys():
    settings={'ai_provider':'deepseek','openai_api_key':'synthetic-legacy-key'}
    assert not decision_status(settings)['can_request']
    settings['ai_provider_profiles']={'finance_decision':payload('deepseek','deepseek-flash')['selection']}
    assert decision_status(settings)['can_request']

def test_invalid_saved_route_is_not_silently_replaced():
    settings={'ai_provider_profiles':{'finance_decision':{'provider':'openai','model':'invented'}}}
    assert decision_status(settings)['state']=='configuration_required'
    assert decision_status(settings)['selection'] is None


def test_budget_error_never_calls_model_and_does_not_retry(tmp_path,monkeypatch):
    ai,calls=service(tmp_path)
    def blocked(*a,**k):raise ValueError('budget_exceeded')
    monkeypatch.setattr(ai,'reserve_operation',blocked)
    p=payload();v=preview(ai,configured(p),p);p['consent']={'confirmed':True,'payload_hash':v['payload_hash']}
    assert decide(ai,configured(p),p)['status']=='local_fallback' and not calls

def test_malformed_or_truncated_json_is_rejected_and_usage_recorded(tmp_path):
    ai,calls=service(tmp_path)
    factory=ai.router_factory
    def truncated(*a,**kw):
        router=factory(*a,**kw);router.adapter.chat_json=lambda *a,**k:ProviderResponse(provider='openai',model='gpt-6-luna',content=valid(),finish_reason='length',usage={'input_tokens':10,'output_tokens':400});return router
    ai.router_factory=truncated
    p=payload();v=preview(ai,configured(p),p);p['consent']={'confirmed':True,'payload_hash':v['payload_hash']}
    assert decide(ai,configured(p),p)['status']=='local_fallback'
    assert '400' in ai.usage_path.read_text()

def test_settings_schema_has_independent_profile():
    from web_platform.application_services import MODEL_SELECT_PROVIDER_PATHS,MODEL_SELECT_CAPABILITIES
    assert MODEL_SELECT_PROVIDER_PATHS['ai_provider_profiles.finance_decision.model']=='ai_provider_profiles.finance_decision.provider'
    assert MODEL_SELECT_CAPABILITIES['ai_provider_profiles.finance_decision.model']=='chat_json'

@pytest.mark.parametrize('provider,model',FAST_MODELS.items())
def test_real_router_honors_finance_selection_without_trading_or_public_route_override(tmp_path,provider,model):
    settings={'ai_provider_profiles':{'analyst':{'provider':'openai','model':'gpt-6-sol'}},
              'ai_data_routing':{'public_general_sharing_enabled':True,'public_openai_model':'gpt-6-sol'}}
    settings.update(configured(payload(provider,model)))
    ai=InteractiveAIService(data_dir=tmp_path)
    view=preview(ai,settings,payload(provider,model))
    assert view['packet']['selection']=={'provider':provider,'model':model}
    assert view['provider_called'] is False
    assert not ai.usage_path.exists()
