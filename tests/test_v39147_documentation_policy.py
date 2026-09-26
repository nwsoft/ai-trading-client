"""Guard the specific product-policy contradictions found during v47 review."""
import re
import pytest

from scripts.doc_consistency_check import TARGETS, check_strategy_policy_alignment, check_whitepaper_release_identity, read_text


def documents():
    return {key: read_text(TARGETS[key]) for key in (
        'strategy_master', 'strategy_plan', 'ai_custom_architecture', 'release_gate')}


def test_current_product_contracts_agree():
    assert check_strategy_policy_alignment(documents()) == []


@pytest.mark.parametrize('key,heading,contradiction', [
    ('strategy_master', '### Level 명칭', '다섯 번째 Level을 만들지 않는다'),
    ('strategy_plan', '### 3.3 백테스트의 제품 포지션', '다음 순서를 강제한다'),
    ('ai_custom_architecture', '## 실사용 제품 원칙', '과거재생 자동검증 → PAPER'),
])
def test_contradiction_fails_even_with_current_version_and_valid_markers(key,heading,contradiction):
    docs=documents()
    docs[key]=docs[key].replace(heading,heading+'\n'+contradiction,1)
    assert any('현행 계약 충돌' in error for error in check_strategy_policy_alignment(docs))


def test_missing_release_classification_is_not_passed():
    docs=documents()
    docs['release_gate']=docs['release_gate'].replace('사용자 정의·외부 근거 필요','',1)
    assert any('현행 계약 누락' in error for error in check_strategy_policy_alignment(docs))


def test_dated_history_does_not_override_current_contract():
    docs=documents()
    docs['strategy_plan']+='\n## 과거 정책 이력\n다음 순서를 강제한다\n'
    assert check_strategy_policy_alignment(docs) == []


def test_future_level_extension_is_explicit_not_a_permanent_five_level_cap():
    docs=documents()
    docs['strategy_master']=docs['strategy_master'].replace('향후 Level 6 이상도 추가할 수 있다','Level 5까지만 제공한다')
    assert any('현행 계약 누락' in error for error in check_strategy_policy_alignment(docs))


@pytest.mark.parametrize('obsolete',[False, True])
def test_whitepaper_current_identity_matches_code_and_public_manifest(obsolete):
    docs={key:read_text(TARGETS[key]) for key in ('technical_whitepaper','release_manifest')}
    if obsolete:
        docs['technical_whitepaper']=re.sub(r'현재 공개 기반: NoahAI Client v\d+\.\d+\.\d+\.\d+',
            '현재 공개 기반: NoahAI Client v0.0.0.0',docs['technical_whitepaper'],count=1)
    assert bool(check_whitepaper_release_identity(docs)) is obsolete
