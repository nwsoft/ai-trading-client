"""Validated ledger edits, paged search, and preview-bound duplicate-safe import."""
from datetime import date
from copy import deepcopy
from trading.finance_connections import digest
from trading.finance_product_intelligence import number
from trading.life_finance import TransactionType, ExpenseClassifier


def clean(row):
    if not isinstance(row,dict) or set(row)-{'date','amount','type','description','method','category'}:raise ValueError('ledger_row_invalid')
    day=date.fromisoformat(row['date']);kind=TransactionType(row['type'])
    for key,limit in (('description',500),('method',100),('category',100)):
        if row.get(key) is not None and (not isinstance(row[key],str) or len(row[key])>limit or '\x00' in row[key]):raise ValueError('ledger_text_invalid')
    if not row.get('description','').strip():raise ValueError('ledger_description_required')
    category=row.get('category') or (ExpenseClassifier.classify(row['description'])[0].value if kind==TransactionType.EXPENSE else '기타')
    return {'date':day.isoformat(),'amount':number(row['amount'],minimum=.01),'type':kind.value,'description':row['description'].strip(),'method':row.get('method') or '기타','category':category}


def fingerprint(row):return digest({k:row.get(k) for k in ('date','amount','type','description','method','category')})


def dispatch(manager,payload):
    if not isinstance(payload,dict) or set(payload)-{'operation','query','start','end','offset','rows','preview_hash','confirmed','id','row','expected_revision'}:raise ValueError('ledger_request_invalid')
    operation=payload.get('operation','list');existing=[r.to_dict() for r in manager.get_transactions()]
    if operation=='list':
        query=payload.get('query','');start=payload.get('start');end=payload.get('end');offset=payload.get('offset',0)
        if not isinstance(query,str) or len(query)>200 or type(offset) is not int or offset<0:raise ValueError('ledger_filter_invalid')
        if start:date.fromisoformat(start)
        if end:date.fromisoformat(end)
        if start and end and start>end:raise ValueError('ledger_date_order')
        matched=[r for r in existing if (not start or r['date']>=start) and (not end or r['date']<=end) and query.casefold() in (' '.join(str(r[k]) for k in ('description','method','category','type'))).casefold()]
        return {'rows':[dict(r,revision=digest(r)) for r in matched[offset:offset+50]],'total':len(matched),'offset':offset,'record_balance_is_account_balance':False}
    if operation=='update':
        old=next((r for r in existing if r['id']==payload.get('id')),None)
        if not old or payload.get('expected_revision')!=digest(old):raise ValueError('ledger_revision_changed')
        row=clean(payload.get('row'))
        item=manager.update_transaction(old['id'],date=row['date'],type=TransactionType(row['type']),amount=row['amount'],description=row['description'],method=row['method'],category=row['category'])
        return {'row':item.to_dict()}
    if operation not in {'preview_import','import'}:raise ValueError('ledger_operation_invalid')
    rows=payload.get('rows')
    if not isinstance(rows,list) or not 1<=len(rows)<=300:raise ValueError('ledger_import_limit')
    normalized=[clean(r) for r in rows];seen={fingerprint(r) for r in existing};accepted=[];duplicates=[]
    for i,row in enumerate(normalized):
        key=fingerprint(row)
        if key in seen:duplicates.append(i+1)
        else:accepted.append(row);seen.add(key)
    preview_hash=digest({'rows':normalized,'ledger':existing})
    if operation=='preview_import':return {'rows':accepted,'duplicate_rows':duplicates,'preview_hash':preview_hash,'imported':False}
    if payload.get('confirmed') is not True or payload.get('preview_hash')!=preview_hash:raise ValueError('ledger_preview_changed')
    # Each accepted row is persisted by the existing manager. A retry must preview
    # again; previously written rows are detected even if a later write failed.
    for r in accepted:manager.add_transaction(date.fromisoformat(r['date']),r['amount'],TransactionType(r['type']),r['description'],method=r['method'],category=r['category'])
    return {'imported':len(accepted),'duplicate_rows':duplicates}
