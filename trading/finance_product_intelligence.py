"""Versioned product evidence and explainable, local scenario comparison.

Catalog holds public product facts only. Personal plans belong in the encrypted
workspace. Import requires an operator-reviewed source; no bundled samples are
promoted to current offers and no network, application or lead submission occurs.
"""
from __future__ import annotations
import hashlib
import json
import math
import time
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

RULE_VERSION = 'finance-products-3923-1'
KINDS = {'loan', 'insurance', 'savings'}


def number(value, *, minimum=0, maximum=1e12, optional=False):
    if optional and value in (None, ''):
        return None
    try:
        if isinstance(value, bool):
            raise ValueError()
        result = float(value)
        if not math.isfinite(result) or not minimum <= result <= maximum:
            raise ValueError()
        return result
    except (ValueError, TypeError, OverflowError):
        raise ValueError('finance_invalid_number') from None


def instant(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise ValueError('finance_invalid_timestamp') from None


def public_url(value):
    parsed = urlparse(str(value))
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('finance_source_url_required')
    return str(value)


def loan_cashflow(amount, months, rate, method='annuity', fees=None):
    amount = number(amount, minimum=1)
    months_value = number(months, minimum=1, maximum=600)
    if months_value != int(months_value):
        raise ValueError('finance_invalid_term')
    months = int(months_value)
    rate = number(rate, maximum=100)
    fees = number(fees, optional=True)
    if method not in {'annuity', 'principal', 'bullet'}:
        raise ValueError('finance_invalid_method')
    monthly = rate / 1200
    payment = amount/months if monthly == 0 else amount*monthly/-math.expm1(-months*math.log1p(monthly))
    balance, interest, schedule = amount, 0, []
    for month in range(1, months+1):
        cost = balance * monthly
        principal = balance if month == months else 0 if method == 'bullet' else amount/months if method == 'principal' else payment-cost
        balance = max(0, balance-principal)
        schedule.append({'month': month, 'payment': round(principal+cost, 2), 'interest': round(cost, 2), 'balance': round(balance, 2)})
        interest += cost
    return {'principal': amount, 'interest': round(interest, 2), 'fees': fees,
            'total_cost': None if fees is None else round(interest+fees, 2),
            'first_payment': schedule[0]['payment'], 'last_payment': schedule[-1]['payment'],
            'max_payment': max(row['payment'] for row in schedule), 'schedule': schedule}


def saving_cashflow(amount, months, rate, method='deposit', tax_rate=None):
    amount = number(amount, minimum=1)
    term = number(months, minimum=1, maximum=600)
    if term != int(term):
        raise ValueError('finance_invalid_term')
    months = int(term)
    rate = number(rate, maximum=100)
    tax_rate = number(tax_rate, maximum=100, optional=True)
    if method not in {'deposit', 'installment'}:
        raise ValueError('finance_invalid_method')
    principal = number(amount if method == 'deposit' else amount*months)
    interest = amount*rate/1200*(months if method == 'deposit' else months*(months+1)/2)
    net = None if tax_rate is None else interest*(1-tax_rate/100)
    return {'principal': principal, 'interest': round(interest, 2), 'tax_rate': tax_rate,
            'net_interest': None if net is None else round(net, 2), 'maturity': None if net is None else round(principal+net, 2),
            'assumptions': '단리·월초 정시 납입·고정 금리. 실제 일수·복리·중도해지 조건은 별도 확인.'}


class ProductCatalog:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript('''CREATE TABLE IF NOT EXISTS products (
              product_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, version TEXT NOT NULL,
              kind TEXT NOT NULL, payload TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS imports (
              revision TEXT PRIMARY KEY, source_id TEXT, imported_at TEXT, count INTEGER);
              CREATE TABLE IF NOT EXISTS source_snapshots (
              revision TEXT PRIMARY KEY, source_id TEXT, imported_at TEXT, source_json TEXT, records_json TEXT);
              CREATE TABLE IF NOT EXISTS source_feeds (
              source_id TEXT PRIMARY KEY, path TEXT, last_attempt REAL DEFAULT 0, next_attempt REAL DEFAULT 0,
              failures INTEGER DEFAULT 0, status TEXT DEFAULT 'registered', revision TEXT, error_code TEXT);''')

    def ingest(self, source, records, *, now=None):
        now = now or datetime.now(timezone.utc)
        if not isinstance(source, dict) or source.get('rights_verified') is not True or not source.get('rights_reference'):
            raise ValueError('finance_source_rights_required')
        source_id = str(source.get('id', '')).strip()
        if not source_id or len(source_id) > 100 or not isinstance(records, list) or len(records)>10000:
            raise ValueError('finance_invalid_import')
        public_url(source.get('url'))
        prepared = []
        for raw in records:
            if not isinstance(raw, dict) or raw.get('kind') not in KINDS:
                raise ValueError('finance_invalid_product')
            row = dict(raw)
            for key in ('id', 'name', 'provider', 'version'):
                if not isinstance(row.get(key), str) or not 1 <= len(row[key]) <= 200:
                    raise ValueError('finance_missing_product_field')
            public_url(row.get('source_url'))
            verified, expires = instant(row.get('verified_at')), instant(row.get('valid_until'))
            if verified > now or expires <= verified:
                raise ValueError('finance_invalid_validity')
            if row.get('status') not in {'active', 'withdrawn'}:
                raise ValueError('finance_invalid_product_status')
            if not isinstance(row.get('terms'), dict):
                raise ValueError('finance_terms_required')
            from trading.finance_evidence import validate_chunks
            validate_chunks(row.get('evidence',[]))
            terms=row['terms']
            from trading.finance_rule_evidence import eligibility_check
            eligibility_check({},terms)
            from trading.finance_terms import validate_terms
            validate_terms(terms)
            for key in ('annual_rate','tax_rate'):
                if terms.get(key) is not None: number(terms[key],maximum=100)
            for key in ('fees','min_amount','max_amount','monthly_premium'):
                if terms.get(key) is not None: number(terms[key])
            if 'months' in terms and (not isinstance(terms['months'],list) or any(number(m,minimum=1,maximum=600)!=int(float(m)) for m in terms['months'])):
                raise ValueError('finance_invalid_term')
            if 'conditions' in terms and (not isinstance(terms['conditions'],list) or not all(isinstance(c,str) and len(c)<=200 for c in terms['conditions'])):
                raise ValueError('finance_invalid_conditions')
            row['source_id'] = source_id
            row['source_kind'] = 'operator_verified'
            row['rights_reference'] = str(source['rights_reference'])[:1000]
            row['ai_processing_allowed'] = source.get('ai_processing_allowed') is True
            # Provider facts are data, never instructions to the assistant.
            encoded = json.dumps(row, ensure_ascii=False, allow_nan=False, sort_keys=True)
            if len(encoded)>30000:
                raise ValueError('finance_product_limit')
            prepared.append((source_id+':'+row['id'], source_id, row['version'], row['kind'], encoded))
        if len({r[0] for r in prepared})!=len(prepared):
            raise ValueError('finance_duplicate_product')
        revision=hashlib.sha256(json.dumps({'source':source_id,'records':prepared}, ensure_ascii=False).encode()).hexdigest()
        with closing(sqlite3.connect(self.path)) as db, db:
            # Atomic complete source snapshot: withdrawn/missing records cannot linger.
            db.execute('DELETE FROM products WHERE source_id=?', (source_id,))
            db.executemany('INSERT INTO products VALUES (?,?,?,?,?)', prepared)
            db.execute('INSERT OR REPLACE INTO imports VALUES (?,?,?,?)', (revision,source_id,now.isoformat(),len(prepared)))
            db.execute('INSERT OR IGNORE INTO source_snapshots VALUES (?,?,?,?,?)',
                       (revision,source_id,now.isoformat(),json.dumps(source,ensure_ascii=False),json.dumps(records,ensure_ascii=False,allow_nan=False)))
        return {'revision':revision,'count':len(prepared),'source_id':source_id}

    def register_feed(self, source_id, path):
        path=Path(path).expanduser().resolve()
        with path.open('rb') as stream:raw=stream.read(30*1024*1024+1)
        if len(raw)>30*1024*1024:raise ValueError('finance_feed_limit')
        payload=json.loads(raw)
        if payload.get('source',{}).get('id')!=source_id:raise ValueError('finance_feed_source_mismatch')
        result=self.ingest(payload['source'],payload['products'])
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('INSERT OR REPLACE INTO source_feeds VALUES (?,?,?,?,?,?,?,?)',
                       (source_id,str(path),time.time(),time.time()+900,0,'current',result['revision'],None))
        return result

    def refresh_feeds(self, *, force=False, now_epoch=None):
        from filelock import FileLock, Timeout
        try:
            with FileLock(str(self.path)+'.remote-refresh.lock',timeout=0):
                return self._refresh_feeds(force=force,now_epoch=now_epoch)
        except Timeout:
            return self.snapshot()

    def _refresh_feeds(self, *, force=False, now_epoch=None):
        now_epoch=time.time() if now_epoch is None else now_epoch
        with closing(sqlite3.connect(self.path)) as db:
            feeds=list(db.execute("SELECT source_id,path,next_attempt,failures,last_attempt FROM source_feeds WHERE status!='paused_after_rollback'"))
        for source_id,path,due,failures,last_attempt in feeds:
            # Manual clicks are also bounded; repeated clicking cannot hammer storage.
            if now_epoch-last_attempt<5 or (not force and now_epoch<due):continue
            try:
                with Path(path).open('rb') as stream:raw=stream.read(30*1024*1024+1)
                if len(raw)>30*1024*1024:raise ValueError('finance_feed_limit')
                payload=json.loads(raw)
                if payload.get('source',{}).get('id')!=source_id:raise ValueError('finance_feed_source_mismatch')
                result=self.ingest(payload['source'],payload['products'])
                status,code,failures,revision='current',None,0,result['revision']
            except (OSError,ValueError,TypeError,KeyError,AttributeError):
                status,code,failures,revision='refresh_failed','source_unavailable_or_invalid',failures+1,None
            delay=900 if not failures else min(3600,60*2**min(failures,6))
            with closing(sqlite3.connect(self.path)) as db,db:
                db.execute('UPDATE source_feeds SET last_attempt=?,next_attempt=?,failures=?,status=?,error_code=?,revision=COALESCE(?,revision) WHERE source_id=?',
                           (now_epoch,now_epoch+delay,failures,status,code,revision,source_id))
        return self.snapshot()

    def rollback(self, revision):
        from filelock import FileLock
        with FileLock(str(self.path)+'.remote-refresh.lock',timeout=2):
            return self._rollback(revision)

    def _rollback(self, revision):
        with closing(sqlite3.connect(self.path)) as db,db:
            row=db.execute('SELECT source_id,source_json,records_json FROM source_snapshots WHERE revision=?',(str(revision),)).fetchone()
            if not row:raise ValueError('finance_revision_not_found')
            source_id,source_raw,records_raw=row;source=json.loads(source_raw);records=json.loads(records_raw)
            prepared=[]
            for raw in records:
                record={**raw,'source_id':source_id,'source_kind':'operator_verified','rights_reference':str(source['rights_reference'])[:1000],'ai_processing_allowed':source.get('ai_processing_allowed') is True}
                prepared.append((source_id+':'+record['id'],source_id,record['version'],record['kind'],json.dumps(record,ensure_ascii=False,allow_nan=False,sort_keys=True)))
            db.execute('DELETE FROM products WHERE source_id=?',(source_id,))
            db.executemany('INSERT INTO products VALUES (?,?,?,?,?)',prepared)
            db.execute("UPDATE source_feeds SET status='paused_after_rollback',revision=?,error_code=NULL WHERE source_id=?",(revision,source_id))
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='remote_sources'").fetchone():
                db.execute("UPDATE remote_sources SET status='paused_after_rollback',revision=? WHERE source_id=?",(revision,source_id))
        # The imported timestamps/expiry are retained. Re-registering the feed
        # after operator review is required before automatic refresh resumes.
        return {'revision':revision,'source_id':source_id,'count':len(records),'feed_paused':True}

    def snapshot(self, *, now=None):
        now = now or datetime.now(timezone.utc)
        with closing(sqlite3.connect(self.path)) as db:
            rows = [json.loads(row[0]) for row in db.execute('SELECT payload FROM products ORDER BY product_id')]
            feeds=[{'source_id':r[0],'last_attempt':r[1],'next_attempt':r[2],'failures':r[3],'status':r[4],'error_code':r[5]} for r in db.execute('SELECT source_id,last_attempt,next_attempt,failures,status,error_code FROM source_feeds')]
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='remote_sources'").fetchone():
                feeds += [{'source_id':r[0],'last_attempt':r[1],'next_attempt':r[2],'failures':r[3],'status':r[4],'transport':'api'} for r in db.execute('SELECT source_id,last_attempt,next_attempt,failures,status FROM remote_sources')]
            imports = [{'revision':r[0],'source_id':r[1],'imported_at':r[2],'count':r[3]} for r in db.execute('SELECT * FROM imports ORDER BY imported_at DESC LIMIT 20')]
        for row in rows:
            row['evidence_status'] = 'withdrawn' if row['status']=='withdrawn' else 'stale' if instant(row['valid_until'])<=now else 'current'
        from trading.insurance_reference_directory import snapshot as reference_snapshot
        return {'reference_products':reference_snapshot(self.path, now=now), 'products':rows,'imports':imports,'feeds':feeds,'status':'available' if rows else 'source_not_connected',
                'current_count':sum(r['evidence_status']=='current' for r in rows),'rule_version':RULE_VERSION}


def compare_scenario(payload, catalog=None):
    if not isinstance(payload,dict) or payload.get('kind') not in KINDS:
        raise ValueError('finance_invalid_scenario')
    kind=payload['kind']; profile=payload.get('profile') or {}; offers=payload.get('offers') or []
    if not isinstance(profile,dict) or not isinstance(offers,list) or len(offers)>20:
        raise ValueError('finance_invalid_scenario')
    profile=dict(profile)
    selected=profile.get('discovery_product_ids')
    if selected is not None:
        if not isinstance(selected,list) or len(selected)>20 or not all(isinstance(v,str) and len(v)<=250 for v in selected):
            raise ValueError('finance_invalid_product_selection')
        catalog={**(catalog or {}),'products':[r for r in (catalog or {}).get('products',[]) if f"{r.get('source_id')}:{r.get('id')}" in selected]}
    for field in ('confirmed_conditions','declined_conditions'):
        values=profile.get(field) or []
        if isinstance(values,str):values=[v.strip() for v in values.split(',') if v.strip()]
        if not isinstance(values,list) or len(values)>50 or not all(isinstance(v,str) and 0<len(v)<=200 for v in values):raise ValueError('finance_invalid_conditions')
        profile[field]=values
    result={'kind':kind,'rule_version':RULE_VERSION,'status':'needs_input','candidates':[], 'excluded':[],
            'questions':[], 'best':None,'application_submitted':False,'external_delivery':False}
    if kind=='insurance':
        state=profile.get('insurance_state','unknown')
        if state not in {'none','existing','unknown'}:
            raise ValueError('finance_invalid_insurance_state')
        driver=profile.get('insurance_kind')=='driver'
        result.update({'status':'needs_assessment','insurance_state':state,
                       'priorities':['일상생활에서 큰 지출이 생길 위험', '이미 가입한 보장과 공적 보장 확인', '지속 가능한 월 보험료와 제외 조건'],
                       'questions':(['자가용·업무용 운전 중 어느 쪽인가요?', '자동차보험의 법률비용 특약이나 기존 운전자 보장이 있나요?', '벌금·변호사 선임비용·교통사고처리지원금의 지급 조건과 제외 사유를 확인했나요?'] if driver else ['현재 보험이 없나요, 가입 여부를 모르나요?', '가족 부양·소득 중단·의료비 중 먼저 대비하려는 위험은 무엇인가요?', '매달 유지할 수 있는 보험료는 얼마인가요?']),
                       'explanation':('보험이 없다면 증권 업로드 없이 필요한 보장부터 정리할 수 있습니다.' if state=='none' else '가입 여부를 모르면 보험이 없는 것으로 판단하지 않습니다.' if state=='unknown' else '기존 증권의 보장·면책·갱신 조건을 새 견적과 같은 항목으로 비교하세요.')})
        from trading.insurance_reference_directory import selected_references
        result['reference_products']=selected_references(profile,catalog)
        result['questions'] += [f"관심 상품 {r['name']}: 현재 판매 여부와 같은 보장 기준의 개인 견적을 확인하세요." for r in result['reference_products']]
        result['questions'].append('상담에서 같은 보장·가입 조건의 개인별 견적과 약관 원문을 요청하세요.')
        from trading.insurance_design import enrich_insurance
        return enrich_insurance(result, profile, offers, catalog)
    amount=number(profile.get('amount'), minimum=1, optional=True)
    months=number(profile.get('months'), minimum=1, maximum=600, optional=True)
    if amount is None or months is None:
        result['questions']=['비교할 금액과 기간을 알려주세요. 예금은 목돈, 적금은 매월 납입액입니다.']
        return result
    if months != int(months): raise ValueError('finance_invalid_term')
    method=profile.get('method', 'annuity' if kind=='loan' else 'deposit')
    if any(not isinstance(r,dict) or not isinstance(r.get('terms',{}),dict) for r in offers):
        raise ValueError('finance_invalid_offer')
    rows=[dict(r,source_kind='user_quote') for r in offers]
    rows += [dict(r) for r in (catalog or {}).get('products',[]) if r['kind']==kind]
    for index,row in enumerate(rows):
        terms=row.get('terms') or {}; name=str(row.get('name','받은 조건'))[:200]
        from trading.finance_rule_evidence import eligibility_check
        eligibility=eligibility_check(profile,terms)
        reason='명시된 가입 자격 불충족: '+', '.join(eligibility['failed']) if eligibility['failed'] else None
        if row.get('source_kind')!='user_quote' and row.get('evidence_status')!='current': reason='자료 만료·판매 종료'
        if row.get('source_kind')=='user_quote' and row.get('valid_until') and instant(row['valid_until'])<=datetime.now(timezone.utc): reason='견적 유효기간 만료'
        if terms.get('method') and terms['method']!=method: reason='상환·납입 방식 불일치'
        if number(terms.get('min_amount',0))>amount or number(terms.get('max_amount',1e12))<amount: reason='금액 조건 불일치'
        if terms.get('months') and months not in terms['months']: reason='가입 기간 불일치'
        if profile.get('category') and terms.get('category')!=profile['category']: reason='상품 종류 불일치'
        from trading.finance_terms import rate_terms, tax_terms, lending_rules
        rate_detail=rate_terms(terms,profile)
        rate=number(rate_detail['annual_rate'],maximum=100,optional=True)
        tax_detail=tax_terms(terms,profile) if kind=='savings' else None
        if rate is None: reason='적용 금리 미확인'
        if reason:
            result['excluded'].append({'name':name,'reason':reason});continue
        conditions=terms.get('conditions') or []
        if not isinstance(conditions,list): raise ValueError('finance_invalid_conditions')
        unmet=[str(c)[:200] for c in conditions if c not in (profile.get('confirmed_conditions') or [])]
        declined=profile.get('declined_conditions') or []
        if any(str(tag) in str(condition) for tag in declined for condition in conditions):
            result['excluded'].append({'name':name,'reason':'원하지 않는 우대 조건 포함'});continue
        from trading.finance_scenarios import loan_projection, saving_projection, affordability
        loan_advanced=any(profile.get(k) not in (None,'') for k in ('grace_months','day_count','rounding','early_month','early_amount','early_fee','start_date','rate_steps'))
        estimate=(loan_projection(amount,months,rate,method,terms.get('fees'),profile) if loan_advanced else loan_cashflow(amount,months,rate,method,terms.get('fees'))) if kind=='loan' else saving_projection(amount,months,rate,method,tax_detail['rate'],profile)
        entry={'id':f'quote-{index}' if row.get('source_kind')=='user_quote' else f"{row.get('source_id')}:{row.get('id')}",'name':name,'provider':str(row.get('provider',''))[:200], 'annual_rate':rate, 'source_kind':row.get('source_kind'),
               'source_url':row.get('source_url'),'verified_at':row.get('verified_at'),'valid_until':row.get('valid_until'),
               'version':row.get('version'),'estimate':estimate,'unconfirmed_conditions':unmet,'rate_detail':rate_detail,'tax_detail':tax_detail,
               'documents':terms.get('documents',[]),'channels':terms.get('channels',[]),'application_url':terms.get('application_url'),
               'eligibility':eligibility['status'],'eligibility_detail':eligibility,'terms_to_check':['중도해지·상환 비용','실제 적용 금리','가입 한도·자격','우대 조건 유효기간']}
        if kind=='loan':
            from trading.finance_scenarios import parse_month_values
            stress_profile=dict(profile)
            if profile.get('rate_steps'):
                stress_profile['rate_steps']=[{'month':r['month'],'annual_rate':min(100,r['annual_rate']+2)} for r in parse_month_values(profile['rate_steps'],int(months),'annual_rate',100)]
            stress=loan_projection(amount,months,min(100,rate+2),method,terms.get('fees'),stress_profile) if loan_advanced else loan_cashflow(amount,months,min(100,rate+2),method,terms.get('fees'))
            entry['affordability']=affordability(profile,estimate)
            entry['lending_rules']=lending_rules(terms,profile,estimate)
            entry['rate_plus_2pp_max_payment']=stress['max_payment']
            old_rate=number(profile.get('existing_rate'),maximum=100,optional=True)
            exit_fee=number(profile.get('existing_exit_fee'),optional=True)
            if old_rate is not None:
                old=loan_cashflow(amount,months,old_rate,method,0)
                net_saving=None if exit_fee is None or estimate['total_cost'] is None else old['interest']-estimate['total_cost']-exit_fee
                if loan_advanced: net_saving=None
                detailed_old=profile.get('existing_terms_confirmed') in (True,'true')
                if detailed_old:
                    old_method=profile.get('existing_method')
                    old_fees=number(profile.get('existing_remaining_fees'),optional=True)
                    if old_method not in {'annuity','principal','bullet'}:raise ValueError('finance_existing_method_required')
                    old_profile={key[len('existing_'):]:value for key,value in profile.items() if key.startswith('existing_')}
                    old=loan_projection(amount,months,old_rate,old_method,old_fees,old_profile)
                    net_saving=None if exit_fee is None or estimate['total_cost'] is None or old['total_cost'] is None else old['total_cost']-estimate['total_cost']-exit_fee
                entry['refinance']={'same_remaining_principal':amount,'same_remaining_months':months,
                    'old_remaining_interest':old['interest'],'exit_fee':exit_fee,'estimated_saving':net_saving,
                    'assumptions':('기존·신규의 각각 확인한 계산 조건을 동일 남은 원금·기간에 적용한 가정. 미래 변동금리와 조기상환은 예상이며 확정 절감액이 아닙니다.' if detailed_old else '거치·일수 계산·조기상환 조건을 변경했습니다. 기존 대출의 동일 조건을 확인하기 전 대환 절감액은 미확정입니다.' if loan_advanced else '기존·신규 대출의 같은 잔여 원금·기간·상환 방식·고정 금리 가정. 이미 낸 이자는 절감액에 포함하지 않음.')}
        if kind=='savings':
            from trading.finance_rule_evidence import protection_check
            entry['deposit_protection']=protection_check(profile,terms,estimate['principal'])
        result['candidates'].append(entry)
    key='total_cost' if kind=='loan' else 'net_interest'
    rankable=[r for r in result['candidates'] if r['estimate'][key] is not None and not r['unconfirmed_conditions'] and r['eligibility']!='needs_confirmation']
    rankable.sort(key=lambda r:r['estimate'][key],reverse=kind=='savings')
    result['status']='compared' if result['candidates'] else 'no_matching_candidates'
    result['best']=rankable[0]['name'] if rankable else None
    result['ranking_basis']='입력·확인된 조건의 총비용 오름차순' if kind=='loan' else '입력·확인된 조건의 세후 이자 내림차순'
    result['questions']=['개인 적용 금리·가입 자격은 기관 확인이 필요합니다. 미확인 비용·세율·우대 조건이 있으면 순위에서 제외합니다.']
    if not result['candidates']: result['questions'].append('유효한 자료가 없거나 조건에 맞지 않습니다. 필터를 풀지 않고 받은 견적을 직접 비교할 수 있습니다.')
    # Budget decisions retain unknown values; not a DSR or approval determination.
    income=number(profile.get('monthly_income'),optional=True);expenses=number(profile.get('monthly_expenses'),optional=True)
    debt=number(profile.get('other_repayments'),optional=True);premium=number(profile.get('insurance_budget'),optional=True);saving=number(profile.get('monthly_saving'),optional=True)
    result['monthly_remaining']=None if any(v is None for v in (income,expenses,debt,premium,saving)) else income-expenses-debt-premium-saving
    for row in result['candidates']:
        row['remaining_after_new_payment']=None if kind!='loan' or result['monthly_remaining'] is None else result['monthly_remaining']-row['estimate']['max_payment']
    result['budget_note']='생활비·기존 상환·보험·저축을 뺀 금액. 새 대출 상환은 후보별로 추가 차감하세요. 대출 한도 심사 결과가 아닙니다.'
    result['handoff']={'state':'draft_only','questions':['본인 적용 견적을 발급할 수 있나요?','미확인 비용·세금·자격·우대 조건을 확인해 주세요.','원문과 실제 적용 조건의 유효기간은 언제까지인가요?'],
                       'recipient':None,'consent':False,'sent':False}
    return result


def product_question_answer(question, recent_messages=None, *, catalog=None):
    """Local grounded follow-up; no implicit private-document/provider access."""
    current=str(question)
    prior=' '.join(str(r.get('content',''))[:2000] for r in (recent_messages or [])[-4:] if isinstance(r,dict) and r.get('role')=='user')
    text=current+' '+prior
    if any(w in current for w in ('대출','상환','금리 인상','갈아타')):
        kind='loan'
    elif any(w in current for w in ('예금','적금','저축','만기')):
        kind='savings'
    elif any(w in text for w in ('보험','보장','운전자')):
        kind='insurance'
    elif any(w in text for w in ('대출','상환')):
        kind='loan'
    elif any(w in text for w in ('예금','적금','저축')):
        kind='savings'
    else:
        return None
    if kind=='insurance':
        none=any(w in text for w in ('보험 없어','보험이 없어','보험 없음','미가입'))
        plan=compare_scenario({'kind':kind,'profile':{'insurance_state':'none' if none else 'unknown','insurance_kind':'driver' if '운전자' in text else 'medical'}})
        answer=plan['explanation']+'\n'+'\n'.join('- '+q for q in plan['questions'])
        if '운전자' in text:
            answer+='\n운전자보험은 자동차보험의 보장·특약과 먼저 대조해야 합니다. 벌금·형사합의 관련 비용·변호사 비용은 담보별 지급 조건이 다릅니다. 담보 이름만으로 지급이나 중복 보상을 확정하지 않습니다.\n참고: 보험연구원 운전자보험 소비자 유의사항 https://www.kiri.or.kr/report/downloadFile.do?docId=6005 (일반 설명 자료, 현재 상품 약관은 별도 확인).'
    elif kind=='loan':
        answer='대출은 실제 적용 금리뿐 아니라 월 상환 흐름과 전체 이자·추가 비용으로 비교합니다. 원리금균등은 월 부담이 대체로 일정하고, 원금균등은 초기에 부담이 크며, 만기일시는 만기에 원금이 집중됩니다.\n- 필요한 금액·기간과 받은 금리, 상환 방식을 알려주세요.\n- 변동금리 여부·부대비용·중도상환 비용이 확인됐나요?\n- 월 소득에서 생활비·기존 상환·보험료·저축을 뺀 뒤 새 상환액을 감당할 수 있나요?'
        if any(w in text for w in ('갈아타','대환','중도상환')):
            answer+='\n대환은 기존 대출의 남은 이자와 새 대출의 이자·기존 중도상환수수료·신규 비용을 같은 남은 기간으로 비교해야 합니다. 단순 금리 차이는 확정 절감액이 아닙니다.'
    else:
        answer='예금은 지금 가진 목돈, 적금은 매달 납입할 돈을 기준으로 비교합니다. 같은 연 금리라도 적금의 각 납입금이 맡겨지는 기간은 다릅니다.\n- 목돈을 맡기나요, 매달 모으나요? 금액과 사용할 예정 시점을 알려주세요.\n- 기본금리와 최고금리의 우대 조건 중 실제 충족하는 것은 무엇인가요?\n- 세율·중도해지 금리·납입 한도·보호 대상 여부를 원문에서 확인했나요?\n비교 참고: 저축은행중앙회 https://www.fsb.or.kr/ratuserguide_0100.act'
    from trading.finance_profile_parser import interpret
    from trading.finance_evidence import search_evidence
    session_kind=None; session_profile={}
    messages=[str(r.get('content','')) for r in (recent_messages or [])[-12:] if isinstance(r,dict) and r.get('role')=='user']+[current]
    for message in messages:
        next_kind='insurance' if any(w in message for w in ('보험','보장','운전자')) else 'savings' if any(w in message for w in ('예금','적금','저축')) else 'loan' if any(w in message for w in ('대출','상환','갈아타')) else session_kind
        if next_kind and next_kind!=session_kind:session_profile={};session_kind=next_kind
        if not session_kind:continue
        try:session_profile,_,_=interpret(session_profile,message,session_kind)
        except ValueError:continue
    if session_kind:
        kind=session_kind
        plan=compare_scenario({'kind':kind,'profile':session_profile},catalog)
        if kind=='insurance':
            answer=plan['explanation']+'\n'+'\n'.join('- '+q for q in plan['questions'])
        elif plan['status']!='needs_input':
            answer='확인한 대화 조건: '+str(session_profile.get('amount'))+'원 · '+str(session_profile.get('months'))+'개월.\n'
            for row in plan['candidates'][:5]:
                estimate=row['estimate'];key='total_cost' if kind=='loan' else 'maturity'
                answer+=row['name']+': '+('총비용 ' if kind=='loan' else '만기 수령 ')+(f"{estimate[key]:,.2f}원" if estimate.get(key) is not None else '미확인')+' · '+str(row.get('source_url') or '확인 경로 미입력')+'\n'
            answer+='\n'.join(plan['questions'])
            if not plan['candidates']:answer+='\n입력 조건에 맞는 유효 자료가 없습니다. 금융상품 화면에서 받은 개인 견적을 입력해 비교할 수 있습니다.'
    clauses=search_evidence(catalog,current,kind)
    if any(word in current for word in ('모르','몰라','추천','처음','없어','어떤','걱정','운전')):
        from trading.finance_discovery import discover
        discovery_profile={}
        try:
            for message in messages:
                # Keep only messages concerning the current kind or a short follow-up.
                if any(w in message for w in ('대출','예금','적금','보험')) and not any(w in message for w in ({'loan':('대출','상환'),'savings':('예금','적금','저축'),'insurance':('보험','보장','운전')}[kind])):
                    discovery_profile={};continue
                discovery=discover({'kind':kind,'profile':discovery_profile,'question':message},catalog)
                discovery_profile=discovery['profile']
            guide=discovery['answer']+'\n'+'\n'.join(c['title']+': '+c['explanation']+' 확인할 것: '+c['checks'] for c in discovery['cards'])
            answer=guide+'\n금융상품 화면에서 상황을 선택하면 같은 조건으로 비교·상담 준비를 이어갈 수 있습니다.\n\n'+answer
        except (ValueError,UnboundLocalError):
            pass
    for clause in clauses[:3]:
        answer+='\n[상품 근거 · '+clause['product']+' · 버전 '+clause['version']+'] '+clause['text'][:600]+'\n'+str(clause.get('page') or '쪽수 미기재')+'쪽 · '+str(clause.get('clause') or '조항 미기재')+' · '+clause['source_url']
    count=sum(r.get('kind')==kind and r.get('evidence_status')=='current' for r in (catalog or {}).get('products',[]))
    answer+=f'\n현재 연결된 이 종류의 유효 상품 자료는 {count}건입니다. '+('금융상품의 맞춤 비교에서 출처와 조건을 확인하세요.' if count else '현재 실상품 순위를 제시할 근거가 없습니다. 받은 조건을 입력하면 비용·만기금액·보장 차이를 비교할 수 있습니다.')
    from trading.finance_explanations import explain_terms
    direct=explain_terms(current)
    return ('\n'.join(direct)+'\n\n' if direct else '')+answer
