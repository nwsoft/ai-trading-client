"""Bounded, explicit numeric state on completed bars; no eval or order APIs.

All assignments read the previous state and commit together. Runtime storage
is account-scoped, version/mode isolated and idempotent by candle timestamp.
"""
import ast
import hashlib
import json
import math
import re
import sqlite3
import threading
from functools import lru_cache
from contextlib import closing

NAME=re.compile(r'[a-z][a-z0-9_]{0,31}\Z')
FIELDS={'open','high','low','close','volume','rsi','macd','macd_signal','macd_histogram',
        'ma20','ma50','ma200','ema20','ema50','ema200','adx','atr','atr_percent',
        'bb_position','bb_width','trend_strength','market_volatility','volume_ratio','hour','weekday'}
FUNCTIONS={'min':min,'max':max,'abs':abs}

def canonical(value):
    def normalized(item):
        if isinstance(item,dict):return {k:normalized(v) for k,v in item.items()}
        if isinstance(item,list):return [normalized(v) for v in item]
        if isinstance(item,float) and item.is_integer():return int(item)
        return item
    return json.dumps(normalized(value),sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def number(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)>1e12:
        raise ValueError('state_numeric_value_invalid')
    return float(value)

@lru_cache(maxsize=512)
def parse(expression,names):
    if not isinstance(expression,str) or not 1<=len(expression)<=500:raise ValueError('state_expression_length')
    try:tree=ast.parse(expression,mode='eval')
    except (SyntaxError,RecursionError):raise ValueError('state_expression_invalid') from None
    nodes=list(ast.walk(tree))
    def depth(node):return 1+max([0]+[depth(c) for c in ast.iter_child_nodes(node)])
    if len(nodes)>96 or depth(tree)>12:raise ValueError('state_expression_complexity')
    allowed=(ast.Expression,ast.Load,ast.Constant,ast.Name,ast.BinOp,ast.UnaryOp,ast.IfExp,
             ast.Compare,ast.BoolOp,ast.Call,ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Mod,
             ast.USub,ast.UAdd,ast.Not,ast.And,ast.Or,ast.Lt,ast.LtE,ast.Gt,ast.GtE,ast.Eq,ast.NotEq)
    for node in nodes:
        if not isinstance(node,allowed):raise ValueError('state_expression_unsupported')
        if isinstance(node,ast.Constant):number(node.value)
        if isinstance(node,ast.Name) and node.id not in set(names)|FIELDS|set(FUNCTIONS):
            raise ValueError('state_name_undefined:'+node.id)
        if isinstance(node,ast.Call) and (not isinstance(node.func,ast.Name) or node.func.id not in FUNCTIONS or node.keywords or not 1<=len(node.args)<=8):
            raise ValueError('state_function_unsupported')
        if isinstance(node,ast.Call) and ((node.func.id=='abs' and len(node.args)!=1) or
                                         (node.func.id in {'min','max'} and len(node.args)<2)):
            raise ValueError('state_function_arguments')
        if isinstance(node,ast.Name) and node.id in FUNCTIONS and not any(isinstance(call,ast.Call) and call.func is node for call in nodes):
            raise ValueError('state_function_reference_unsupported')
    return tree.body

def validate(program):
    if not program:return []
    try:
        if not isinstance(program,dict) or set(program)!={'initial','updates'}:raise ValueError('state_program_invalid')
        initial,updates=program['initial'],program['updates']
        if not isinstance(initial,dict) or not 1<=len(initial)<=32 or not isinstance(updates,dict) or set(initial)!=set(updates):
            raise ValueError('state_declaration_update_mismatch')
        for key,value in initial.items():
            if not isinstance(key,str) or not NAME.fullmatch(key) or key in FIELDS|set(FUNCTIONS)|{'signal','confidence','price','current_price','sma20','sma50','sma200','volume_sma20'}:raise ValueError('state_name_invalid')
            number(value);parse(updates[key],tuple(sorted(initial)))
        return []
    except (ValueError,TypeError) as exc:return [str(exc)]

def fields(program):
    if validate(program):return set()
    return {n.id for expr in program.get('updates',{}).values() for n in ast.walk(parse(expr,tuple(sorted(program['initial']))))
            if isinstance(n,ast.Name) and n.id in FIELDS}

def calculate(node,values):
    if isinstance(node,ast.Constant):return number(node.value)
    if isinstance(node,ast.Name):return number(values.get(node.id))
    if isinstance(node,ast.IfExp):return calculate(node.body if calculate(node.test,values) else node.orelse,values)
    if isinstance(node,ast.BoolOp):
        if isinstance(node.op,ast.And):return all(calculate(n,values) for n in node.values)
        return any(calculate(n,values) for n in node.values)
    if isinstance(node,ast.UnaryOp):
        value=calculate(node.operand,values)
        return not value if isinstance(node.op,ast.Not) else number(-value if isinstance(node.op,ast.USub) else value)
    if isinstance(node,ast.Compare):
        left=calculate(node.left,values)
        for op,right_node in zip(node.ops,node.comparators):
            right=calculate(right_node,values)
            passed={ast.Lt:lambda:left<right,ast.LtE:lambda:left<=right,ast.Gt:lambda:left>right,
                    ast.GtE:lambda:left>=right,ast.Eq:lambda:left==right,ast.NotEq:lambda:left!=right}[type(op)]()
            if not passed:return False
            left=right
        return True
    if isinstance(node,ast.BinOp):
        a,b=calculate(node.left,values),calculate(node.right,values)
        value={ast.Add:lambda:a+b,ast.Sub:lambda:a-b,ast.Mult:lambda:a*b,ast.Div:lambda:a/b,ast.Mod:lambda:a%b}[type(node.op)]()
        return number(value)
    if isinstance(node,ast.Call):return number(FUNCTIONS[node.func.id](*(calculate(n,values) for n in node.args)))
    raise ValueError('state_expression_unsupported')

class NumericStateStore:
    def __init__(self,path=None):
        self.path=path;self.memory={};self.lock=threading.RLock()

    def advance(self,program,scope,bars):
        errors=validate(program)
        if errors:raise ValueError(errors[0])
        if not bars or len(bars)>400:raise ValueError('state_history_unavailable')
        stamps=[number(row.get('_bar_timestamp')) for row in bars]
        if any(a>=b for a,b in zip(stamps,stamps[1:])):raise ValueError('state_history_order_invalid')
        key=digest({'scope':scope,'program':program})
        used=fields(program)
        def fingerprint(row):return row.get('_state_source_digest') or digest({k:row.get(k) for k in sorted(used|{'_bar_timestamp'})})
        def advance_record(old):
            last=old.get('bar') if old else None
            if last is not None and last>stamps[-1]:raise ValueError('state_time_reversed')
            if last is not None:
                if last not in stamps:raise ValueError('state_history_gap')
                if fingerprint(bars[stamps.index(last)])!=old['input_digest']:raise ValueError('state_candle_revision')
            pending=[r for r in bars if last is None or r['_bar_timestamp']>last]
            # First activation starts at the latest completed candle, not a
            # secretly replayed history. Later missed observed bars catch up.
            if old is None:pending=pending[-1:]
            result=old
            for row in pending:
                prior=dict(result['values'] if result else program['initial'])
                environment={**{k:row.get(k) for k in used},**prior}
                for k in used:number(environment[k])
                after={k:number(calculate(parse(expr,tuple(sorted(prior))),environment)) for k,expr in program['updates'].items()}
                result={'bar':row['_bar_timestamp'],'before':prior,'values':after,'input_digest':fingerprint(row),
                        'inputs':{k:row.get(k) for k in sorted(used)}}
            return result
        with self.lock:
            if self.path is None:
                result=advance_record(self.memory.get(key));self.memory[key]=result
                return dict(result)
            with closing(sqlite3.connect(str(self.path),timeout=2)) as db, db:
                db.execute('CREATE TABLE IF NOT EXISTS numeric_strategy_state(id TEXT PRIMARY KEY,record TEXT NOT NULL)')
                db.execute('BEGIN IMMEDIATE')
                old=db.execute('SELECT record FROM numeric_strategy_state WHERE id=?',(key,)).fetchone()
                result=advance_record(json.loads(old[0]) if old else None)
                encoded=canonical(result)
                if not old and db.execute('SELECT COUNT(*) FROM numeric_strategy_state').fetchone()[0]>=100000:
                    raise ValueError('state_storage_limit')
                if not old or encoded!=old[0]:
                    db.execute('INSERT OR REPLACE INTO numeric_strategy_state VALUES(?,?)',(key,encoded))
                return dict(result)

def identity(rules,item=None):
    item=item or {}
    return digest({'rules':rules,'key':item.get('strategy_key',''),'version':item.get('version_id') or item.get('id') or ''})

def enrich_states(context,pool,scope=None,store=None):
    results={};direct=not isinstance(pool,list)
    for item in pool if isinstance(pool,list) else [pool]:
        if not isinstance(item,dict):continue
        rules=item.get('rules') or item
        program=rules.get('numeric_state')
        if not program:continue
        key=identity(rules,item if 'rules' in item else None)
        try:
            if store is None or not scope or any(not scope.get(k) for k in ('venue','symbol','mode')):raise ValueError('state_runtime_scope_required')
            tf=rules.get('decision_timeframe') or rules.get('timeframe')
            bars=(context.get('_strategy_timeframe_contexts',{}).get(tf) or {}).get('_closed_bar_contexts',[])
            result=store.advance(program,{**scope,'strategy':key},bars)
            results[key]={'status':'ready',**result}
        except (ValueError,ArithmeticError,TypeError,sqlite3.Error) as exc:
            results[key]={'status':'unavailable','reason':str(exc) if not isinstance(exc,sqlite3.Error) else 'state_storage_unavailable'}
        if direct:context['_numeric_state_identity']=key
    context['_numeric_state_results']=results
    return context

@lru_cache(maxsize=32)
def _runtime_store(path):return NumericStateStore(path+'.strategy-state.sqlite3')

def runtime_store(recorder):
    path=getattr(recorder,'db_path',None)
    return _runtime_store(str(path)) if path else None
