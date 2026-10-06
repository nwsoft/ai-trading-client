from copy import deepcopy
import pytest
from trading.source_condition_compiler import ConditionCompiler
from trading.retrained_strategy_evaluation import run_retrained_evaluation


def candles(n=500):
    return [[i*300000,100,101,99,100,10,(i+1)*300000-1] for i in range(n)]


def rules():
    return {'decision_timeframe':'15m','executable_entry':{'expression':ConditionCompiler().compile('rsi < 50')},
            'risk_model':{'stop_loss_percent':1.},'numeric_state':None}


def test_fit_only_uses_past_and_does_not_pick_from_profitable_test_results():
    original=rules();before=deepcopy(original);calls=[]
    def runner(variant, rows, **kw):
        value=variant['executable_entry']['expression']['condition']['value']
        test=kw['entry_start_ms'] is not None
        calls.append({'value':value,'test':test,'end':rows[-1][6], 'timeframes':kw['timeframe_klines']})
        # Train prefers 55. Holdout reverses that ordering. A leaky fitter
        # would choose 45 based on test returns; this fitter must reject 55.
        pnl=(value-40) if not test else (60-value)
        return {'decisions':5,'net_pnl_percent':pnl,'max_drawdown_percent':1.}
    result=run_retrained_evaluation(original,candles(),timeframe_rows={'1h':candles(800)},
                runner=runner,cost_profile={'rates':{'buy_fee_rate':.001}})
    assert result['status']=='candidate_not_better_than_baseline'
    assert [f['chosen_value'] for f in result['folds']]==[55.,55.]
    assert result['replay_calls']==12 and original==before
    assert not result['auto_applied'] and not result['live_permission_granted']
    for fold in result['folds']:
        assert fold['training_end_ms'] < fold['test_start_ms']
    for call in calls:
        assert all(row[6]<=call['end'] for row in call['timeframes']['1h'])


def test_cost_stressed_or_small_samples_cannot_be_accepted():
    def runner(variant, rows, **kw):
        value=variant['executable_entry']['expression']['condition']['value']
        return {'decisions':5,'net_pnl_percent':value if kw['cost_profile']['rates']['fee']<.02 else -1.,'max_drawdown_percent':1.}
    result=run_retrained_evaluation(rules(),candles(),runner=runner,cost_profile={'rates':{'fee':.01}})
    assert result['status']=='candidate_not_better_than_baseline'
    assert all(f['cost_2x_test_net_percent']==-1. for f in result['folds'])


def test_actual_replay_runs_without_mutating_approved_rules():
    from trading.replay_costs import resolve_replay_costs
    data=[]
    for i in range(500):
        price=100+(i%20)-10
        data.append([i*900000,price,price+2,price-2,price,10,(i+1)*900000-1])
    original=rules();before=deepcopy(original)
    result=run_retrained_evaluation(original,data,cost_profile=resolve_replay_costs({},'binance','crypto','futures'))
    assert result['status'] in {'candidate_ready_for_paper_review','candidate_not_better_than_baseline','training_quality_or_sample_insufficient'}
    assert result['replay_calls']>=3
    assert original==before


@pytest.mark.parametrize('n', [0,100,399,3001])
def test_history_budget_is_explicit(n):
    assert run_retrained_evaluation(rules(),candles(n))['status']=='bounded_history_required'


def test_resource_budget_cannot_promote_partial_evaluation():
    result=run_retrained_evaluation(rules(),candles(),cost_profile={'rates':{'fee':0}},budget_seconds=0.)
    assert result['status']=='evaluation_resource_budget_exceeded'
    assert not result.get('proposal',{}).get('accepted_for_review')
