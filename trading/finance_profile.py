"""Explicit, account-encrypted reusable assumptions, never inferred balances."""
from copy import deepcopy
from trading.finance_product_intelligence import number
FIELDS={'monthly_income','monthly_expenses','other_repayments','insurance_budget','monthly_saving','target_amount'}


def dispatch(vault,operation='get',profile=None,confirmed=False):
    with vault._mutex:
        vault._require()
        data=deepcopy(vault._data)
        if operation=='save':
            if confirmed is not True or not isinstance(profile,dict) or set(profile)-FIELDS:raise ValueError('finance_profile_confirmation_required')
            clean={k:str(number(v,optional=True)) for k,v in profile.items() if v not in ('',None)}
            from datetime import datetime,timezone
            data['finance_profile']={'values':clean,'confirmed_at':datetime.now(timezone.utc).isoformat(),'basis':'user_confirmed_assumptions'}
            vault._persist(data)
        elif operation=='reset':
            if confirmed is not True:raise ValueError('finance_profile_confirmation_required')
            data.pop('finance_profile',None);vault._persist(data)
        elif operation!='get':raise ValueError('finance_profile_operation')
        return {'profile':deepcopy(data.get('finance_profile')),'state':'unlocked','ledger_applied':False}
