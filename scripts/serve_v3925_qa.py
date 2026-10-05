"""Synthetic follow-up and ledger gateway. Temporary storage; no external services."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.serve_v3924_qa import app,services
import scripts.serve_v3923_qa as base
from trading.life_finance import LifeFinanceManager
from trading.finance_ledger import dispatch
from datetime import datetime,timezone,timedelta
manager=LifeFinanceManager(str(base.root/'ledger'))
services.life_ledger=lambda payload:dispatch(manager,payload)
services.add_life_transaction=lambda **kw:manager.add_transaction(__import__('datetime').date.fromisoformat(kw['transaction_date']),kw['amount'],__import__('trading.life_finance',fromlist=['TransactionType']).TransactionType(kw['transaction_type']),kw['description'],method=kw['method'],category=kw['category']).to_dict()
def transport(recipient,action,payload,key):
 base.calls[action]+=1
 return {'request_id':payload['request_id'],'status':'withdrawn' if action=='withdraw' else 'in_consultation','receipt_id':'synthetic-receipt','result':{'assigned_advisor':'합성 상담사','expected_reply_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'quotes':[{'id':'synthetic-q','provider':'합성 기관','name':'회신된 시험 견적','source_url':'https://example.org/q','valid_until':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat(),'terms':{'annual_rate':3,'fees':0}}]}}
base.handoff_transport=transport
if __name__=='__main__':
 import uvicorn
 uvicorn.run(app,host='127.0.0.1',port=3919,log_level='warning')
