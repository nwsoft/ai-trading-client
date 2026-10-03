"""Retrieve reviewed product clauses as data, never as executable instructions."""
import re
from trading.finance_product_intelligence import public_url


def validate_chunks(chunks):
    if not isinstance(chunks, list) or len(chunks) > 50:
        raise ValueError('finance_evidence_limit')
    for row in chunks:
        if not isinstance(row, dict) or set(row) - {'id', 'text', 'page', 'clause', 'source_url'}:
            raise ValueError('finance_evidence_invalid')
        for key, limit in (('id',100), ('text',4000), ('clause',200)):
            if key in row and (not isinstance(row[key],str) or not 1 <= len(row[key]) <= limit):
                raise ValueError('finance_evidence_invalid')
        if not row.get('id') or not row.get('text'):
            raise ValueError('finance_evidence_invalid')
        if row.get('page') is not None and (type(row['page']) is not int or row['page'] < 1):
            raise ValueError('finance_evidence_invalid')
        if row.get('source_url'):
            public_url(row['source_url'])
    if len({row['id'] for row in chunks}) != len(chunks):
        raise ValueError('finance_evidence_duplicate')


def search_evidence(catalog, question, kind=None, limit=5):
    tokens = {w for w in re.findall(r'[가-힣A-Za-z0-9]{2,}', str(question)[:2000])}
    # Short domain terms also match Korean particles without claiming semantic entailment.
    for word in ('벌금','변호사','합의','면책','갱신','보장','상환','금리','수수료','해지','우대','납입','세금','한도'):
        if word in question:tokens.add(word)
    results=[]
    for product in (catalog or {}).get('products',[]):
        if product.get('evidence_status') != 'current' or (kind and product.get('kind') != kind):
            continue
        for chunk in product.get('evidence',[]):
            score=sum(token in chunk['text'] or token in product['name'] for token in tokens)
            if not score:continue
            results.append({'product':product['name'],'provider':product['provider'],'product_id':product['source_id']+':'+product['id'],
                            'version':product['version'],'chunk_id':chunk['id'],'text':chunk['text'],
                            'page':chunk.get('page'),'clause':chunk.get('clause'),'source_url':chunk.get('source_url') or product['source_url'],
                            'ai_processing_allowed':product.get('ai_processing_allowed') is True,'verified_at':product['verified_at'],'valid_until':product['valid_until'],'score':score})
    return sorted(results,key=lambda r:(-r['score'],r['product_id'],r['chunk_id']))[:max(1,min(10,limit))]
