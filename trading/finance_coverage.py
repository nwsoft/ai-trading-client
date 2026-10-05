"""Structured, explicit coverage facts; no semantic equivalence inferred."""
from trading.finance_product_intelligence import number

TEXT={'name','conditions','exclusions','waiting','reduction','deductible'}
KEYS=TEXT|{'amount','benefit_kind','renewal','evidence'}

def normalize(rows):
    if not isinstance(rows,list) or len(rows)>60:raise ValueError('finance_coverage_details_invalid')
    output=[];names=set()
    for raw in rows:
        if not isinstance(raw,dict) or set(raw)-KEYS:raise ValueError('finance_coverage_details_invalid')
        if any(not isinstance(raw.get(k,''),str) or len(raw.get(k,''))>2000 for k in TEXT):raise ValueError('finance_coverage_details_invalid')
        if not raw.get('name') or raw['name'] in names:raise ValueError('finance_coverage_duplicate')
        if raw.get('benefit_kind','unknown') not in {'fixed','indemnity','unknown'} or raw.get('renewal','unknown') not in {'yes','no','unknown'}:raise ValueError('finance_coverage_details_invalid')
        amount=number(raw.get('amount'),optional=True)
        # Document evidence is retained in the encrypted policy, not silently copied
        # into public/AI contexts. Comparison uses only the user's confirmed fields.
        row={k:raw.get(k,'') for k in TEXT};row.update(amount=amount,benefit_kind=raw.get('benefit_kind','unknown'),renewal=raw.get('renewal','unknown'))
        output.append(row);names.add(row['name'])
    return output
