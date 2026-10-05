"""Editorial product discovery, isolated from licensed feeds and personal quotes.

Only short, authored factual summaries are bundled. No scraped tables, prices,
eligibility decisions or claims of redistribution/API rights are included.
"""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from trading.finance_product_intelligence import instant, public_url

VERSION = 'insurance-reference-20261004-1'
CATEGORIES = {'driver':'운전자','medical':'실손·의료비','cancer':'암·건강','income':'가족·소득','accident':'상해','auto':'자동차','term':'정기','whole_life':'종신','travel':'여행','home':'주택','pension':'연금','saving':'저축성'}


def _row(id, provider, name, category, url, coverage, renewal, checks):
    return dict(id=id, provider=provider, name=name, category=category, source_url=url,
                coverage=coverage, renewal=renewal, checks=checks, version=VERSION,
                observed_at='2026-10-04T00:00:00+00:00', review_due='2026-11-03T00:00:00+00:00', status='listed')


BUNDLED = [
    _row('samsung-driver', '삼성화재', '무배당 삼성화재 다이렉트 운전자보험', 'driver',
         'https://direct.samsungfire.com/mall/PP030301_001.html?ver=59',
         '운전 사고의 합의·벌금·변호사 비용을 특약으로 구성합니다.',
         '1·3·5·10·20년 만기 선택, 자동갱신 없음으로 안내',
         '비례보상, 음주·무면허 등 제외 사유와 특약별 자기부담을 확인하세요.'),
    _row('hyundai-driver', '현대해상', '현대해상 다이렉트 운전자보험', 'driver',
         'https://direct.hi.co.kr/service.do?m=c91a5781ba',
         '운전자 법률비용과 사고 부상 관련 보장을 특약으로 구성합니다.',
         '가입 설계별 납입·보장 기간 확인 필요',
         '운전 용도, 경찰조사 보장 요건과 특약별 지급 한도를 확인하세요.'),
    _row('db-driver', 'DB손해보험', 'DB손해보험 다이렉트 운전자보험', 'driver',
         'https://www.directidb.co.kr/',
         '운전 사고 비용과 상해 보장을 살펴볼 수 있는 운전자 상품입니다.',
         '가입 설계별 납입·보장 기간 확인 필요',
         '정식 계약 상품명·개정 차수와 선택 특약, 사고별 지급 조건을 확인하세요.'),
    _row('hyundai-medical', '현대해상', '현대해상 다이렉트 실손의료비보장보험', 'medical',
         'https://direct.hi.co.kr/service.do?m=ddd18946bf',
         '질병·상해의 급여와 비급여 의료비를 구분하여 살펴보는 상품입니다.',
         '갱신 보험료와 재가입 조건 확인 필요',
         '자기부담·비급여 특약과 기존 실손 계약의 중복 여부를 확인하세요.'),
    _row('samsung-health-renewable', '삼성화재', '무배당 삼성화재 다이렉트 건강보험(자동갱신형)', 'cancer',
         'https://direct.samsungfire.com/mall/PP030401_001.html?ver=40',
         '암·뇌·심장 질환의 진단·수술 등 선택 특약을 구성합니다.',
         '자동갱신형, 갱신 시 보험료 변경 가능',
         '각 진단의 정의, 면책·감액 기간과 장기 보험료 부담을 확인하세요.'),
    _row('samsung-health-fixed', '삼성화재', '무배당 삼성화재 다이렉트 비갱신 건강보험(해약환급금 미지급형Ⅱ)', 'cancer',
         'https://direct.samsungfire.com/mall/PP030401_001.html?ver=40',
         '암·뇌·심장 질환의 진단·수술 등 선택 특약을 구성합니다.',
         '비갱신형, 가입 시 보험료 고정으로 안내',
         '면책·감액 기간, 납입 기간과 해약환급금 미지급 조건을 확인하세요.'),
    _row('lifeplanet-term', '교보라이프플래닛', '(무)라이프플래닛 e정기보험Ⅱ', 'income',
         'https://www.lifeplanet.co.kr/products/dth/HPPC61S0N.dev',
         '가족 부양에 필요한 기간을 정해 사망 보장을 검토하는 정기보험입니다.',
         '보장 종료와 납입 기간을 따로 확인',
         '부양 기간, 사망 지급 제외 사유와 순수보장·환급형 차이를 확인하세요.'),
]


def validate(rows):
    if not isinstance(rows, list) or len(rows) > 2000:
        raise ValueError('insurance_reference_limit')
    result=[]; seen=set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(BUNDLED[0]):
            raise ValueError('insurance_reference_schema')
        if any(not isinstance(v,str) or not v.strip() or len(v)>600 for v in row.values()):
            raise ValueError('insurance_reference_text')
        if row['id'] in seen or len(row['id'])>100 or row['category'] not in CATEGORIES or row['status'] not in {'listed','withdrawn'}:
            raise ValueError('insurance_reference_identity')
        observed, due = instant(row['observed_at']), instant(row['review_due'])
        if observed > datetime.now(timezone.utc) or not 0 < (due-observed).total_seconds() <= 90*86400:
            raise ValueError('insurance_reference_review_window')
        public_url(row['source_url']); seen.add(row['id']); result.append(dict(row))
    return result


def snapshot(path, *, now=None):
    now=now or datetime.now(timezone.utc)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS insurance_references (id TEXT PRIMARY KEY, origin TEXT NOT NULL, payload TEXT NOT NULL)')
        for row in BUNDLED:
            db.execute("INSERT INTO insurance_references VALUES (?, 'bundled', ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload WHERE insurance_references.origin='bundled' AND insurance_references.payload!=excluded.payload",
                       (row['id'],json.dumps(row,ensure_ascii=False)))
        rows=[dict(json.loads(r[1]),_editorial_owned=r[0]=='bundled' or r[0].startswith('owned-feed:')) for r in db.execute('SELECT origin,payload FROM insurance_references ORDER BY id')]
    for row in rows:
        row.update(data_class='public_reference', quote_available=False, ai_processing_allowed=row.pop('_editorial_owned',False),
                   category_label=CATEGORIES[row['category']],
                   evidence_status='withdrawn' if row['status']=='withdrawn' else 'review_due' if instant(row['review_due'])<=now else 'reference')
    return rows


def import_rows(path, rows):
    """Atomic reviewed editorial upsert; withdrawn records remain tombstones.

    Does not grant provider feed rights or refresh an observation automatically.
    """
    rows=validate(rows)
    snapshot(path)
    with closing(sqlite3.connect(path)) as db, db:
        for row in rows:
            db.execute("INSERT INTO insurance_references VALUES (?, 'operator', ?) ON CONFLICT(id) DO UPDATE SET origin='operator',payload=excluded.payload",
                       (row['id'],json.dumps(row,ensure_ascii=False)))
    return {'updated':len(rows),'quote_available':False}


def selected_references(profile, catalog):
    ids=profile.get('reference_product_ids',[])
    if not isinstance(ids,list) or len(ids)>20 or len(set(str(v) for v in ids))!=len(ids) or not all(isinstance(v,str) and len(v)<=100 for v in ids):
        raise ValueError('finance_invalid_reference_selection')
    rows={row['id']:row for row in (catalog or {}).get('reference_products',[])}
    return [dict(rows[id]) if id in rows else {'id':id,'name':'이전에 선택한 상품', 'evidence_status':'unavailable'} for id in ids]
