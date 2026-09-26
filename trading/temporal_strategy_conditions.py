"""Closed-bar, stateless temporal rules shared by replay/PAPER/LIVE.

Rebuilding from candle history makes restart and repeated polling deterministic.
No wall-clock counters, simulated signal history, or guessed missing indicators.
"""


def required_bars(value):
    if isinstance(value, dict):
        bars = value.get('bars',0)
        children = max([0] + [required_bars(v) for v in value.values()])
        if value.get('type') == 'temporal' and type(bars) is int and 1<=bars<=100:
            own = bars + (1 if value.get('operator') == 'after' else 0)
            return own + max(0, children - 1)
        return children
    if isinstance(value, list):
        return max([0] + [required_bars(v) for v in value])
    return 0


def required_fields(value, inside=False):
    """Retain only operands, not entire repeated analysis/XAI snapshots."""
    found = set()
    if isinstance(value,dict):
        inside = inside or value.get('type') == 'temporal'
        for key, item in value.items():
            if inside and key in {'field','value_field'} and isinstance(item,str):
                found.add(item)
            found.update(required_fields(item,inside))
    elif isinstance(value,list):
        for item in value: found.update(required_fields(item,inside))
    return found


def evaluate_temporal(engine, node, context, path):
    op, n = node['operator'], node['bars']
    needed = required_bars(node)
    history = context.get('_closed_bar_contexts') or []
    trace = {'type':'temporal','path':path,'operator':op,'bars':n,'passed':False}
    if len(history) < needed:
        return False, {**trace,'reason':'temporal_history_insufficient','available':len(history)}
    history = history[-needed:]
    stamps = [row.get('_bar_timestamp') for row in history]
    if any(s is None for s in stamps) or any(a >= b for a,b in zip(stamps,stamps[1:])):
        return False, {**trace,'reason':'temporal_history_invalid'}
    children = node['children']
    cache = context.get('_temporal_evaluation_cache')
    if cache is None:cache={}
    window = n + 1 if op == 'after' else n
    indices = range(len(history)-window,len(history))
    def at(child,index):
        # Each nested expression sees only the history available at its own bar.
        # Never hand it the parent's future suffix.
        key=(id(child),stamps[index])
        if key not in cache:
            row = {**history[index], '_closed_bar_contexts':history[:index+1],
                   '_temporal_evaluation_cache':cache}
            cache[key]=engine._evaluate_expression_node(child,row,path+'.history')
        return cache[key]
    evaluated = [at(children[0],i) for i in indices]
    def incomplete(result):
        if str(result.get('reason','')).startswith(('missing:', 'unsupported:', 'invalid:',
                'temporal_history_', 'temporal_indicator_')):
            return True
        return any(incomplete(child) for child in result.get('children',[]))
    extra = at(children[1],len(history)-1) if op=='after' else None
    resets = [at(children[1],i) for i in indices] if op=='latched' else []
    if any(incomplete(t) for _,t in evaluated+resets) or (extra and incomplete(extra[1])):
        return False, {**trace,'reason':'temporal_indicator_unavailable'}
    values = [v for v,_ in evaluated]
    if op=='latched':
        # Explicit bounded state: initially false at the window boundary;
        # reset wins if both events occur on a bar, set expires after N bars.
        state = False
        for set_value,(reset_value,_) in zip(values,resets):
            state = False if reset_value else state or set_value
        return state,{**trace,'passed':state,'reason':'temporal_matched' if state else 'temporal_not_met',
                      'first_bar':stamps[-window],'last_bar':stamps[-1],
                      'matches':values,'resets':[v for v,_ in resets],'reset_precedence':True}
    passed = (all(values) if op=='all_for' else any(values) if op=='any_within'
              else not values[-2] and values[-1] if op=='became_true'
              else values[-2] and not values[-1] if op=='became_false'
              else any(values[:-1]) and extra[0])
    return passed, {**trace,'passed':passed,'reason':'temporal_matched' if passed else 'temporal_not_met',
                   'first_bar':stamps[0],'last_bar':stamps[-1],'matches':values}
