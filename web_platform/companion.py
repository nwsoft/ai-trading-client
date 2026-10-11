"""Bounded local evidence and task proposals. No provider, order or persistence API."""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from trading.exchanges.venue_capabilities import CRYPTO_VENUE_ORDER, STOCK_VENUE_ORDER
import json
import hashlib
import math
import re
import sqlite3

VERSION = 'companion-1'
VENUES = {'binance', 'bybit', 'okx', 'bitget', 'upbit', 'bithumb', 'coinone', 'kis', 'kiwoom', 'mirae', 'shinhan'}
TARGETS = {
    'wealth': ('portfolio', 'portfolio.plan', '내 돈 계획 열기'),
    'trading': ('blockchain', 'blockchain.logs', '거래 현황·기관 운용 요약'),
    'stock': ('stock', 'stock.logs', '증권 거래 현황'),
    'portfolio': ('portfolio', 'portfolio.insights', '자산 통합'),
    'market': ('ai_analyst', 'ai_analyst.intelligence', '시장·뉴스·일정 근거'),
    'strategy': ('blockchain', 'blockchain.ai_custom', '전략 초안 검토'),
    'life': ('personal_finance', 'personal_finance.service', '생활금융'),
    'tax': ('personal_finance', 'personal_finance.tax', '절세 조건·세금 계산 확인'),
}


def finite(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError, OverflowError):
        return None


def instant(value):
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, timezone.utc)
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def evidence(source, observed_at=None, *, now=None, ttl=900, valid_until=None,
             data_class='stored_observation', assumptions=(), unknowns=()):
    now = now or datetime.now(timezone.utc)
    observed, expiry = instant(observed_at), instant(valid_until)
    status = ('unknown_time' if not observed else 'future_time' if (observed-now).total_seconds() > 60
              else 'expired' if expiry and expiry <= now
              else 'stale' if (now-observed).total_seconds() > ttl else 'recent')
    if valid_until and not expiry:
        status = 'unknown_expiry'
    return dict(source=str(source)[:160], observed_at=observed.isoformat() if observed else None,
                valid_until=expiry.isoformat() if expiry else None, freshness=status,
                data_class=data_class, calculation_version=VERSION,
                assumptions=list(assumptions), unknowns=list(unknowns))


def _json(path, default):
    if not path.exists():
        return deepcopy(default)
    if path.stat().st_size > 2_000_000:
        raise ValueError('local_record_limit')
    return json.loads(path.read_text(encoding='utf-8'))


def local_finance(directory, now):
    """Reuse the review calculator without constructing a manager or creating files."""
    from trading.personal_finance_review import build_finance_review
    tx = []
    goals = []
    for name in ('life_finance_transactions.json', 'life_finance_transfers.json'):
        rows = _json(directory/name, [])
        if not isinstance(rows, list) or len(rows) > 5000:
            raise ValueError('local_record_limit')
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('local_record_invalid')
            tx.append(SimpleNamespace(amount=row.get('amount'), type=SimpleNamespace(value=row.get('type')),
                      date=date.fromisoformat(str(row.get('date'))[:10]), category=row.get('category', '미분류')))
    rows = _json(directory/'life_finance_goals.json', [])
    if not isinstance(rows, list) or len(rows) > 1000:
        raise ValueError('local_record_limit')
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('local_record_invalid')
        target, current = finite(row.get('target_amount')), finite(row.get('current_amount'))
        goals.append(SimpleNamespace(is_completed=target is not None and current is not None and current >= target,
                     deadline=date.fromisoformat(str(row['deadline'])[:10]) if row.get('deadline') else None))
    return build_finance_review(tx, goals, today=now.date())


def read_catalog(directory, now):
    """Read existing rows with SQLite mode=ro; never refresh feeds or seed tables."""
    from trading.insurance_reference_directory import BUNDLED
    result = {'products': [], 'reference_products': deepcopy(BUNDLED), 'status': 'not_connected'}
    path = directory/'finance_product_catalog.sqlite3'
    if path.exists():
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=.2)) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table, key in (('products', 'products'), ('insurance_references', 'reference_products')):
                if table not in tables:
                    continue
                rows = db.execute(f'SELECT payload FROM {table} LIMIT 1001').fetchall()
                if len(rows) > 1000 or sum(len(r[0]) for r in rows) > 4_000_000:
                    raise ValueError('catalog_limit')
                result[key] = [json.loads(r[0]) for r in rows]
            result['status'] = 'stored_only'
    for key, deadline in (('products', 'valid_until'), ('reference_products', 'review_due')):
        for row in result[key]:
            expiry = instant(row.get(deadline))
            row['evidence_status'] = ('withdrawn' if row.get('status') == 'withdrawn' else
                                     'unknown' if not expiry else 'stale' if expiry <= now else
                                     'current' if key == 'products' else 'reference')
    return result


def market_records(directory):
    path = directory/'financial_intelligence/web_ui.sqlite3'
    output = {'market': [], 'news': [], 'event': []}
    if not path.exists():
        return output
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=.2)) as db:
        for kind in output:
            rows = db.execute('SELECT payload_json, as_of, source FROM fi_records WHERE record_type=? ORDER BY as_of DESC LIMIT 50', (kind,)).fetchall()
            if sum(len(r[0]) for r in rows) > 2_000_000:
                raise ValueError('market_record_limit')
            for payload, as_of, source in rows:
                row = json.loads(payload)
                if not isinstance(row, dict):
                    raise ValueError('market_record_invalid')
                output[kind].append({**row, '_stored_as_of': as_of, '_stored_source': source})
    return output


def symbol_key(symbol):
    # Keep explicit pair/venue symbols; do not map BTC to an ETF or a stock name.
    return re.sub(r'[^A-Z0-9]', '', str(symbol).upper())


def account_context(snapshot, now):
    positions = []
    sources = []
    for source, row in (snapshot.get('sources') or {}).items():
        if source not in VENUES or not isinstance(row, dict):
            continue
        proof = evidence(source, row.get('captured_at'), now=now, data_class='live_account_cache',
                         unknowns=['캐시 조회 이후 체결·잔고 변화', 'ETF 구성종목·실제 주문 비용'])
        sources.append({'source': source, 'status': row.get('status', 'unknown'), 'evidence': proof})
        if row.get('status') != 'success':
            continue
        raw = row.get('positions') or []
        if isinstance(raw, dict):
            raw = [dict(value, symbol=key) for key, value in raw.items() if isinstance(value, dict)]
        for item in raw[:100] if isinstance(raw, list) else []:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get('symbol') or item.get('asset') or '')[:50]
            if symbol:
                positions.append({'symbol': symbol, 'source': source, 'evidence': proof})
    return {'positions': positions[:100], 'sources': sources}


def build_briefing(*, operations, account, finance, catalog, market, plans, now, failures=()):
    cards = []
    for source in (*CRYPTO_VENUE_ORDER, *STOCK_VENUE_ORDER):
        row = operations.get(source)
        if source not in VENUES or not isinstance(row, dict):
            continue
        health, activity = row.get('entry_health') or {}, row.get('entry_activity') or {}
        captured = health.get('observed_at') or activity.get('last_cycle_at')
        detail = health.get('label') or '진입 근거 미수신'
        if activity.get('attention'):
            detail += ' · '+str(activity.get('label') or '주기 확인 필요')
        pre = row.get('pre_entry') or {}
        measured, threshold = finite(pre.get('confidence')), finite(pre.get('required_confidence'))
        if measured is not None and threshold is not None:
            detail += f' · 신뢰도 {measured:g} / 필요 {threshold:g}'
        mode = str(row.get('mode') or '').lower()
        state = ('engine_inactive' if row.get('runtime_state') == 'engine_inactive' else
                 'unavailable' if row.get('status') == 'unavailable' else
                 'observed' if health.get('blocked') or activity.get('attention') else
                 'stopped' if activity.get('status') == 'stopped' else
                 'unobserved' if (not health.get('label') or health.get('code') == 'unavailable') and not captured else 'observed')
        if state == 'observed' and activity.get('status') == 'stopped':
            detail = '현재 정지 · 최근 확인: '+detail
        next_action = health.get('action') or activity.get('action') or '기관 운용 요약을 확인하세요.'
        if state == 'engine_inactive':
            detail, next_action = '이 실행에서 거래 엔진이 아직 준비되지 않았습니다.', '기관 화면에서 연결·거래 모드를 확인하세요. 이 창은 거래를 시작하지 않습니다.'
        elif state == 'stopped':
            detail, next_action = '현재 이 기관의 거래가 정지되어 있습니다.', '거래를 원하면 기관 화면에서 모드·설정을 검토한 뒤 직접 시작하세요.'
        elif state == 'unavailable':
            detail, next_action = '이 기관의 거래 상태를 읽지 못했습니다.', '기관 화면의 연결 상태와 최근 로그를 확인하세요.'
        elif state == 'unobserved':
            detail, next_action = '이 실행에서 아직 판단 기록을 받지 못했습니다.', '기관 화면에서 실행·연결 상태를 확인하세요. 기록이 없어 거래 보류 원인을 확정할 수 없습니다.'
        mode_label = {'paper': 'PAPER', 'live': 'LIVE', 'learning': '관찰 모드'}.get(mode, '거래 모드 미확인')
        cards.append({'id': 'entry:'+source, 'section': 'trading', 'source': source, 'mode': mode, 'state': state,
                      'title': source.upper()+' · '+mode_label,
                      'detail': detail, 'next': next_action,
                      'evidence': evidence(source, captured, now=now, data_class='runtime_session'),
                      'action': 'stock' if source in {'kis','kiwoom','mirae','shinhan'} else 'trading'})
    if finance:
        from trading.personal_finance_review import explain_finance_review
        cards.append({'id': 'finance', 'section': 'finance', 'title': '등록 기록으로 본 월간 돈 점검',
                      'detail': explain_finance_review(finance), 'next': '등록 기록·계획을 확인하세요.', 'action': 'life',
                      'evidence': evidence('local_life_finance_records', None, now=now, data_class='registered_records',
                          assumptions=['은행 잔액·PAPER 성과와 합산하지 않음'], unknowns=['실제 은행 잔액', '미등록 수입·지출'])})
    assets = account_context(account, now)
    symbols = {symbol_key(r['symbol']) for r in assets['positions']}
    matching = []
    for kind, rows in market.items():
        for index, row in enumerate(rows[:50]):
            provenance = row.get('provenance') or {}
            declared = row.get('symbols') or row.get('tickers') or ([row['symbol']] if row.get('symbol') else [])
            if not isinstance(declared, list):
                declared = []
            related = bool(symbols.intersection(symbol_key(s) for s in declared if isinstance(s,str)))
            holding_proofs = [r['evidence'] for r in assets['positions'] if symbol_key(r['symbol']) in
                              {symbol_key(s) for s in declared if isinstance(s,str)}]
            proof = evidence(row.get('_stored_source') or provenance.get('source') or 'unknown',
                             row.get('_stored_as_of') or provenance.get('as_of'), now=now,
                             ttl=86400 if kind != 'market' else 900, data_class='registered_market_data',
                             unknowns=['저장 이후 변경', '개인 투자 적합성'])
            card = {'id': kind+':'+str(index), 'section': kind, 'title': str(row.get('title') or row.get('symbol') or '저장 시장 자료')[:200],
                    'detail': ('LIVE 조회 캐시의 명시 종목과 연결된 자료 · 보유 여부는 캐시 기준' if related else '등록한 시장 자료') +
                              ((' · 일정 '+str(row['starts_at'])[:50]) if row.get('starts_at') else ''),
                    'next': '시장 화면에서 원문·입력·기준시각을 확인하세요.', 'evidence': proof,
                    'action': 'market', 'holding_related': related, 'holding_evidence': holding_proofs}
            cards.append(card)
            if related:
                matching.append(card)
    for item in plans.get('reviews', [])[:50]:
        if item.get('review_due'):
            cards.append({'id': 'plan:'+str(item.get('plan_id', '')), 'section': 'review', 'title': '저장 계획 재점검',
                          'detail': ' · '.join(str(v)[:200] for v in item.get('reasons', [])[:5]),
                          'next': '보관함에서 계획·자료를 다시 확인하세요.', 'action': 'life',
                          'evidence': evidence('encrypted_saved_plan', None, now=now, data_class='saved_plan',
                              unknowns=['실제 가입·납입·갱신 상태'])})
    return {'schema_version': VERSION, 'captured_at': now.isoformat(), 'read_only': True, 'provider_called': False,
            'orders_submitted': False, 'cards': cards[:200], 'assets': assets, 'holding_news': matching[:20],
            'catalog_coverage': {'reference_count': None if 'catalog' in failures else len(catalog.get('reference_products', [])),
                'providers': None if 'catalog' in failures else len({r.get('provider') for r in catalog.get('reference_products', [])}),
                'current_products': None if 'catalog' in failures else sum(r.get('evidence_status') == 'current' for r in catalog.get('products', [])),
                'basis': '저장 상품 자료·내장 편집 자료, 전체 시장·개인 견적이 아님'},
            'vault_state': plans.get('state', 'locked'), 'unavailable_sections': list(failures),
            'notice': '저장 근거를 연결한 브리핑입니다. 조회 시각과 원본 기준시각은 다릅니다. 앱을 열 때 또는 새로고침할 때 재점검하며 외부 알림·자동 주문은 없습니다.'}


def action(key, *, question='', profile=None, kind=None):
    if key == 'finance':
        return {'id': key, 'label': '조건 확인 후 비교·저장 이어가기', 'kind': kind, 'profile': profile or {}, 'question': question}
    service, feature, label = TARGETS[key]
    return {'id': key, 'label': label, 'service': service, 'feature': feature, 'question': question}


def query(question, briefing, catalog, *, service='blockchain'):
    compact = re.sub(r'\s+', '', question).lower()
    matches = [kind for kind, words in {'insurance': ('보험',), 'loan': ('대출','상환','대환'),
               'savings': ('예금','적금','저축','비상금')}.items() if any(w in compact for w in words)]
    output = {'schema_version': VERSION, 'read_only': True, 'provider_called': False, 'saved': False,
              'orders_submitted': False, 'question': question, 'cards': [], 'actions': []}
    from config.assistant_support_knowledge import support_topic, build_support_answer, GUIDE_REVISION
    topic = support_topic(question)
    if (topic and topic.key == 'market_regime_comparison'
        and not any(w in compact for w in ('거래가없','거래안','거래가안','무거래','진입보류','왜거래','거래현황','진단'))):
        return {**output, 'status':'guide', 'answer':build_support_answer(question),
                'guide_revision':GUIDE_REVISION, 'guide_topic':topic.key, 'guide_source':topic.source,
                'evidence':evidence('국면 판단 기준 안내', None, data_class='product_guide',
                    assumptions=['현재 소스 기본값에 대한 안내', '안내 기준 '+GUIDE_REVISION],
                    unknowns=['사용자 당시 실제 지표·설정·실행 상태']),
                'actions':[action('trading'), action('stock')]}
    if any(w in compact for w in ('재확인','재점검','갱신알림','만기알림','갱신일정','만기일정')) or ('갱신' in compact and '알려' in compact):
        cards = [r for r in briefing['cards'] if r['section']=='review']
        return {**output, 'status':'observed' if cards else 'insufficient_data', 'cards':cards,
                'answer':'열린 보관함의 저장 계획에서 예약일·자료 만료·버전 변경을 점검합니다. 현재 확인할 항목이 없거나 잠겨 있으면 실제 만기·갱신 상태를 단정하지 않습니다. 보관함을 열고 저장 계획을 확인하세요. 앱 밖 자동 알림은 제공하지 않습니다.',
                'actions':[action('life')]}
    tax_question = any(w in compact for w in ('절세','비과세','세금','isa','irp','연금저축','연말정산','종합과세'))
    expense_question = any(w in compact for w in ('구독','고정지출','매달나가','월지출','생활비','지출줄','절약'))
    if tax_question and expense_question:
        return {**output, 'status': 'clarification', 'answer': '지출 절약과 절세를 함께 검토할 질문입니다. 먼저 월 수입·필수/선택 지출·부채 상환·비상금·돈을 쓸 시점과 기존 절세 계좌를 확인하세요. 생활금융의 등록 기록과 세금 계산을 각각 확인할 수 있습니다. 자산 통합의 내 돈 계획에서 현재 예산·비상금·부채·반복 지출·목표별 배분을 함께 계산하고 암호화 저장한 뒤 월 실제 기록과 비교할 수 있습니다. 예상 절약액은 현재 배분 재원에 넣지 않습니다.',
                'actions': [action('wealth', question=question), action('life', question=question), action('tax', question=question), action('portfolio', question=question)]}
    if any(w in compact for w in ('내돈계획','자산관리계획','비상금','목돈모','돈을모','저축계획')) and not tax_question:
        return {**output, 'status':'clarification', 'answer':'내 돈 계획에서 현재 월 예산과 직접 확인한 자산·부채를 입력하세요. 비상금과 변경 비용을 먼저 남기고 목표에 돈을 나누며, 미확인 세후 수익은 확정하지 않습니다. 검토 후 암호화 저장하고 월 실제 기록으로 재점검할 수 있습니다.', 'actions':[action('wealth', question=question)]}
    if tax_question:
        return {**output, 'status': 'clarification', 'answer': '오래 예탁한다는 이유만으로 일반 예금이 비과세가 되지는 않습니다. ISA의 비과세·분리과세와 연금저축·IRP의 납입 세액공제·수령 시 과세를 구분해야 합니다. 귀속연도·소득과 가입 자격·기존 납입액·실제 공제 가능한 세액·돈을 쓸 시점·중도인출 조건을 확인한 뒤 생활금융의 세금 계산에서 가정을 비교하세요. 현재 자료만으로 가장 유리한 계좌나 환급액을 확정하지 않습니다.',
                'actions': [action('tax', question=question), action('life', question=question)]}
    if expense_question:
        return {**output, 'status': 'clarification', 'answer': '생활금융에서 등록한 지출과 월간 계획을 먼저 확인하세요. 구독·보험료·통신비 등 반복 결제의 실제 금액과 해지 비용·보장 손실을 확인한 뒤 줄일 항목을 정해야 합니다. 기록만으로 해지나 절약액을 확정하지 않으며, 모든 은행·카드 결제가 자동 수집되는 것은 아닙니다.',
                'cards': [r for r in briefing['cards'] if r['section'] == 'finance'],
                'actions': [action('wealth', question=question), action('life', question=question)] + [action('finance', question=question, kind=k) for k in matches]}
    if len(matches) > 1:
        return {**output, 'status': 'clarification', 'answer': '여러 금융 목적이 있습니다. 먼저 비교할 분야를 선택하고 각 분야의 금액·기간·우선순위를 확인하세요.',
                'actions': [action('finance', question=question, kind=k) for k in matches]}
    if matches:
        from trading.finance_discovery import discover
        result = discover({'kind': matches[0], 'question': question}, catalog)
        return {**output, 'status': 'review', 'answer': result['answer'],
                'actions': [action('finance', question=question, kind=matches[0], profile=result['profile'])],
                'evidence': evidence('local_finance_discovery', None, data_class='user_question',
                    assumptions=['질문에서 명시한 조건의 검토 초안', '계산·저장은 기존 비교 화면에서 확인'],
                    unknowns=['개인 확정 견적·가입 가능 여부'])}
    if any(w in compact for w in ('거래가없','거래안','거래가안','무거래','진입보류','왜거래','거래현황','진단')):
        named = [v for v in VENUES if v in compact]
        cards = [r for r in briefing['cards'] if r['section'] == 'trading' and (not named or r['id'] in ['entry:'+v for v in named])]
        return {**output, 'status': 'observed' if cards else 'insufficient_data', 'cards': cards,
                'answer': '\n'.join(r['title']+': '+r['detail']+'\n'+r['next'] for r in cards) or '현재 기관의 실행 근거가 없습니다. 거래 현황·운용 요약에서 연결과 모드를 확인하세요.',
                'actions': [action('stock' if service == 'stock' else 'trading')]}
    if any(w in compact for w in ('전략','손절','익절','백테스트','실험')):
        prompt = '[NOAH_STRATEGY_CONSULTATION] '+question+'\n원본·승인을 바꾸지 않고 별도 검토 초안을 만들어 주세요. 비교할 원본/후보, 같은 기간·시간봉·비용·자금 가정을 확인하고 저장·재생·PAPER는 각각 직접 검토합니다.'
        target = action('strategy', question=question)
        if service == 'stock':
            target.update(service='stock', feature='stock.ai_custom')
        consultation = {**target, 'id':'strategy_consultation', 'label':'선택적 AI 전략 상담', 'question':prompt}
        return {**output, 'status': 'review', 'answer': '스튜디오에서 별도 후보 초안을 검토합니다. 원본/후보를 동일 기간·시간봉·비용·자금으로 재생한 뒤 전략 실험 비교에서 저장 결과를 대조하세요. 질문만으로 원본 변경·전략 실행을 하지 않습니다. 선택적 AI 상담은 기존 Provider 설정·동의·예산을 사용합니다.', 'actions': [target, consultation]}
    if any(w in compact for w in ('배분','리밸런싱','조정안')):
        return {**output, 'status': 'preview_required', 'answer': '통화와 현재/목표 비중을 확인한 뒤 배분 미리보기에서 집중도·이동 금액·입력 비용을 비교하세요. 파생 노출·다른 통화·계좌 잔액을 임의로 합산하지 않습니다.',
                'actions': [{'id':'allocation','label':'배분 가정 미리보기'},action('portfolio')]}
    if any(w in compact for w in ('내종목','보유','뉴스','etf','겹치')):
        return {**output, 'status': 'observed' if briefing['holding_news'] else 'insufficient_data',
                'answer': '조회 캐시의 명시 종목과 연결된 저장 뉴스·일정만 표시합니다. 통화·모드를 구분하고 캐시 기준시각을 확인하세요. ETF 구성종목 자료가 없으면 중복 비중을 계산하지 않습니다.',
                'cards': briefing['holding_news'], 'actions': [action('portfolio'), action('market')]}
    if any(w in compact for w in ('부담','줄여','유리','최적')):
        return {**output, 'status': 'clarification', 'answer': '어떤 부담을 줄일까요? 대출의 월 상환액, 보험료, 저축액 중 대상을 정하고 현재 금액·기간과 유지할 조건을 확인해야 변경 전후를 비교할 수 있습니다.',
                'actions': [action('finance', kind=k, question=question) for k in ('loan','insurance','savings')]}
    return {**output, 'status': 'briefing', 'answer': '저장된 근거로 오늘 확인할 항목을 모았습니다. 거래 진단·보유 종목·생활금융·전략 질문으로 범위를 좁히거나 아래 검토 화면으로 이어가세요.',
            'cards': briefing['cards'], 'actions': [action(k) for k in ('trading','portfolio','life','market')]}


def allocation_preview(payload):
    """User-assumption arithmetic, never executable orders or expected returns."""
    rows = payload.get('rows')
    currency = payload.get('currency')
    if currency not in {'KRW','USD','USDT','EUR','JPY'} or not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        raise ValueError('allocation_inputs_invalid')
    values = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'symbol','before','after'}:
            raise ValueError('allocation_inputs_invalid')
        symbol = row['symbol']
        before, after = finite(row['before']), finite(row['after'])
        if not isinstance(symbol, str) or not re.fullmatch(r'[A-Za-z0-9._:/-]{1,40}', symbol) or before is None or after is None or not 0 <= before <= 100 or not 0 <= after <= 100:
            raise ValueError('allocation_inputs_invalid')
        values.append((symbol.upper(), before, after))
    if len({r[0] for r in values}) != len(values) or any(abs(sum(r[i] for r in values)-100) > .000001 for i in (1,2)):
        raise ValueError('allocation_weights_must_sum_100')
    total, fee = finite(payload.get('total_value')), finite(payload.get('fee_bps'))
    if (payload.get('total_value') is not None and (total is None or not 0 < total <= 1e15)) or (payload.get('fee_bps') is not None and (fee is None or not 0 <= fee <= 10000)):
        raise ValueError('allocation_cost_assumption_invalid')
    turnover = sum(abs(r[2]-r[1]) for r in values)/100
    return {'schema_version': VERSION, 'currency': currency, 'rows': [{'symbol':s, 'before':b, 'after':a,
        'delta_percent':a-b, 'delta_value':(a-b)*total/100 if total is not None else None} for s,b,a in values],
        'before_hhi':sum((r[1]/100)**2 for r in values), 'after_hhi':sum((r[2]/100)**2 for r in values),
        'turnover_percent':turnover*100, 'estimated_cost':total*turnover*fee/10000 if total is not None and fee is not None else None,
        'fee_bps':fee, 'total_value':total, 'orders_submitted':False, 'saved':False,
        'evidence':evidence('explicit_user_assumptions', datetime.now(timezone.utc).isoformat(), data_class='scenario',
            assumptions=['같은 통화의 현물 가치 가정', '매수+매도 합산 회전율에 입력 수수료 적용', '집중도 HHI는 손실 위험 예측이 아님'],
            unknowns=['실제 체결 가격·슬리피지·세금', '수수료' if fee is None else '실제 기관 수수료와 입력값 차이'])}


def replay_comparison_basis(rows, timeframe_rows, *, source, symbol, interval, horizon, entry_start_ms, costs):
    """Stamp the actual replay inputs, excluding variant rules. No invented legacy hash."""
    packet = {'rows':rows, 'timeframe_rows':timeframe_rows, 'source':source, 'symbol':symbol,
              'interval':interval, 'horizon':horizon, 'entry_start_ms':entry_start_ms, 'costs':costs}
    digest = hashlib.sha256(json.dumps(packet, sort_keys=True, allow_nan=False, separators=(',',':')).encode()).hexdigest()
    return {'schema':VERSION, 'input_sha256':digest, 'source':source, 'symbol':symbol,
            'interval':interval, 'horizon':horizon, 'costs':deepcopy(costs), 'equity_basis':'normalized_1.0'}


def experiment_versions(directory):
    versions = []
    for scope in ('binance','unified'):
        data = _json(directory/'custom_strategies'/f'{scope}_private.json', {})
        for key, items in (data.get('strategies') or {}).items():
            if not isinstance(items,list):
                raise ValueError('strategy_record_invalid')
            for version in items:
                validation = version.get('execution_validation') or {}
                if not version.get('version_id'):
                    continue
                versions.append({'scope':scope, 'strategy_key':str(key), 'version_id':version['version_id'],
                    'name':str(version.get('name') or version.get('strategy_name') or key)[:160],
                    'recorded_at':validation.get('recorded_at'), 'mode':validation.get('mode'),
                    'metrics':validation.get('metrics') or {}})
                if len(versions)>200:
                    raise ValueError('strategy_record_limit')
    return versions


def compare_experiments(versions, baseline, candidate):
    def resolve(ref):
        match = [v for v in versions if all(v.get(k)==ref.get(k) for k in ('scope','strategy_key','version_id'))]
        if len(match)!=1:
            raise ValueError('strategy_experiment_not_found')
        return match[0]
    original, variant = resolve(baseline), resolve(candidate)
    if original is variant:
        raise ValueError('strategy_experiment_distinct_versions_required')
    first, second = original['metrics'], variant['metrics']
    a, b = first.get('comparison_basis') or {}, second.get('comparison_basis') or {}
    comparable = (original['mode']==variant['mode']=='historical_replay' and
                  a.get('schema')==b.get('schema')==VERSION and
                  isinstance(a.get('input_sha256'),str) and re.fullmatch(r'[a-f0-9]{64}',a['input_sha256']) and a==b)
    metrics = []
    if comparable:
        for key, label in (('net_pnl_percent','재생 순손익 %'),('max_drawdown_percent','최대 낙폭 %'),('decisions','재생 판단 수')):
            before, after = finite(first.get(key)), finite(second.get(key))
            metrics.append({'key':key, 'label':label, 'before':before, 'after':after,
                            'delta':after-before if before is not None and after is not None else None})
    return {'schema_version':VERSION, 'comparable':bool(comparable), 'metrics':metrics,
            'status':'comparable' if comparable else 'same_inputs_not_verified',
            'reason':'같은 원본 시세·기간·시간봉·보유 봉·비용 가정의 저장 재생 결과입니다.' if comparable else
                     '같은 입력 근거를 확인하지 못했습니다. 원본/후보를 같은 조건으로 새로 재생하세요. 과거 결과의 누락 해시를 만들어 넣지 않습니다.',
            'baseline':{k:original.get(k) for k in ('scope','strategy_key','version_id','recorded_at')},
            'candidate':{k:variant.get(k) for k in ('scope','strategy_key','version_id','recorded_at')},
            'orders_submitted':False, 'saved':False, 'auto_approved':False,
            'evidence':evidence('saved_historical_replay', variant.get('recorded_at'), data_class='historical_replay',
               assumptions=['정규화 초기 가치 1.0', '같은 입력 지문일 때만 수치 비교'], unknowns=['미래 수익·실제 체결', 'PAPER/LIVE 전진검증'])}
