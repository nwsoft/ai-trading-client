"""90 distinct single turns / 30 multi-turn reference cases; no live data/provider."""
import json
from pathlib import Path
import pytest
from trading.finance_profile_parser import interpret
DATA=json.loads((Path(__file__).parent/'fixtures/v3923_finance_dialogue_eval.json').read_text())

@pytest.mark.parametrize('case',DATA['single'],ids=lambda c:c['id'])
def test_single_reference(case):
    if case['error']:
        with pytest.raises(ValueError):interpret(case['initial'],case['question'],case['kind'])
        return
    result,_,unresolved=interpret(case['initial'],case['question'],case['kind'])
    assert bool(unresolved)==case['unresolved']
    for key,value in case['expected'].items():assert result[key]==value
    if not case['expected'] and not case['unresolved']:assert result==case['initial']

@pytest.mark.parametrize('case',DATA['multi'],ids=lambda c:c['id'])
def test_multiple_reference(case):
    result=case['initial']
    for question in case['turns']:result,_,_=interpret(result,question,case['kind'])
    for key,value in case['expected'].items():assert result[key]==value
