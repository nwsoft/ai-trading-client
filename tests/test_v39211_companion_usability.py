from datetime import datetime, timezone
import pytest
from web_platform.companion import build_briefing
from web_platform.runtime_bridge import HeadlessRuntimeBridge

def card(row):
    return build_briefing(operations={'okx':row}, account={}, finance=None, catalog={}, market={}, plans={}, now=datetime(2026,10,11,tzinfo=timezone.utc))['cards'][0]

def test_uninitialized_bridge_reports_state_without_starting_engine():
    def forbidden(_):
        raise AssertionError('read must not construct engine')
    bridge=HeadlessRuntimeBridge(account='fixture',factory=forbidden)
    row=bridge.operation_summary_snapshot(source='okx',include_paper_pool=False)
    assert bridge._app is None and row['runtime_state']=='engine_inactive'
    result=card(row)
    assert result['state']=='engine_inactive' and 'UNKNOWN' not in result['title']
    assert result['source']=='okx' and result['evidence']['observed_at'] is None

@pytest.mark.parametrize('row,state,text',[
    ({'mode':'paper','entry_activity':{'status':'stopped'}},'stopped','정지'),
    ({'mode':'unknown'},'unobserved','판단 기록'),
    ({'status':'unavailable'},'unavailable','읽지 못했습니다'),
    ({'entry_activity':{'status':'unobserved','attention':True,'label':'실행 근거 미수신'}},'observed','실행 근거 미수신'),
])
def test_distinguishes_stopped_unknown_read_failure_and_running_without_evidence(row,state,text):
    result=card(row)
    assert result['state']==state and text in result['detail']
    assert 'UNKNOWN' not in result['title']

def test_stopped_does_not_hide_known_funding_blocker_or_confidence():
    result=card({'mode':'paper','entry_activity':{'status':'stopped'},'entry_health':{'blocked':True,'code':'paper_funds_reconciliation_required','label':'가상 자금 대조 필요','action':'원장 확인','observed_at':1791676800},'pre_entry':{'confidence':.65,'required_confidence':.7}})
    assert result['state']=='observed'
    assert '현재 정지' in result['detail'] and '가상 자금 대조 필요' in result['detail']
    assert '0.65 / 필요 0.7' in result['detail'] and result['next']=='원장 확인'
