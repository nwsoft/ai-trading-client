"""Audit exclusions from the actual pytest report; never enable LIVE tests."""
from __future__ import annotations
import json,sys
from pathlib import Path
import xml.etree.ElementTree as ET
WINDOWS_PE='tests.test_branding.test_real_non_noahai_executable_is_rejected'
ALLOWED={WINDOWS_PE:'windows_pe',
 'tests.test_tp_sl_validation.test_tp_sl_order_creation':'live_order_opt_in',
 'tests.test_tp_sl_validation.test_place_futures_order_directly':'live_order_opt_in',
 'tests.test_v39146_customer_write_recovery.test_customer_active_versions_and_missing_spot_holdings_readonly':'missing_historical_private_fixture',
 'tests.test_v39147_customer_boundaries.test_customer_cached_cycle_proof_without_api_or_original_writes':'missing_historical_private_fixture'}
for name in ('kiwoom_connect','kiwoom_get_balance','kiwoom_get_positions','kiwoom_get_stock_list','mirae_asset_connect','shinhan_connect'):
 ALLOWED['tests.test_stock_integration.TestLiveAPIIntegration.test_live_'+name]='live_broker_opt_in'

def audit(path,platform=None):
 platform=platform or sys.platform;path=Path(path)
 if path.stat().st_size>20*1024*1024:raise ValueError('test_report_limit')
 raw=path.read_text(encoding='utf-8')
 if '<!DOCTYPE' in raw or '<!ENTITY' in raw:raise ValueError('test_report_invalid')
 cases=list(ET.fromstring(raw).iter('testcase'));skipped=[];errors=[];pe=[]
 for row in cases:
  node=row.get('classname','')+'.'+row.get('name','');skip=row.find('skipped')
  if node==WINDOWS_PE:pe.append(row)
  if row.find('failure') is not None or row.find('error') is not None:errors.append('test_failed:'+node)
  if skip is not None:
   category=ALLOWED.get(node)
   if not category:errors.append('unexpected_skip:'+node)
   skipped.append({'test':node,'category':category or 'unexpected','reason':skip.get('message','')[:180]})
 if platform=='win32' and (len(pe)!=1 or pe[0].find('skipped') is not None):errors.append('windows_pe_must_run')
 return {'status':'PASS' if not errors else 'FAIL','platform':platform,'case_count':len(cases),'skipped_count':len(skipped),
         'skipped':skipped,'errors':errors,'live_tests_enabled_by_auditor':False,
         'scope':'Exclusion audit only; does not certify LIVE accounts, Windows installation or missing private fixtures'}
if __name__=='__main__':
 report=audit(sys.argv[1]);output=json.dumps(report,ensure_ascii=False,indent=2)
 if len(sys.argv)>2:Path(sys.argv[2]).write_text(output+'\n',encoding='utf-8')
 print(output);sys.exit(0 if report['status']=='PASS' else 1)
