"""Compile explicitly labelled directional clauses without guessing missing rules.

Known comparisons are retained as review evidence. Any unknown clause blocks
execution; an ATR description or risk/reward target never becomes a fixed rate.
"""
import re
from .source_condition_compiler import ConditionCompiler


def _clauses(text):
    # A field-pair crossing call contains an argument comma; only outer
    # commas separate prose conditions. Invalid parentheses still fail AST parsing.
    depth = 0
    start = 0
    for index, char in enumerate(text):
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        elif char in ',，' and depth == 0:
            yield text[start:index]
            start = index + 1
    yield text[start:]


def _expression(clause):
    text = clause.strip().rstrip('.。').strip()
    text = re.sub(r'현재\s*가격', 'current_price', text)
    text = re.sub(r'\b(RSI)(?:는|가|값이)?\s*(\d+(?:\.\d+)?)\s*이상\s*(\d+(?:\.\d+)?)\s*이하',
                  r'rsi >= \2 AND rsi <= \3', text, flags=re.I)
    text = re.sub(r'\b(RSI)(?:는|가|값이)?\s*(\d+(?:\.\d+)?)\s*(이상|이하)',
                  lambda m: 'rsi '+('>=' if m[3]=='이상' else '<=')+' '+m[2], text, flags=re.I)
    text = re.sub(r'\b(EMA20|EMA50|EMA200|RSI|ADX|CLOSE)\b', lambda m:m[0].lower(), text, flags=re.I)
    return ConditionCompiler().compile(text)


def compile_directional_source(text):
    entries, exits, gaps = {}, [], []
    present = False
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        heading = re.fullmatch(r'(LONG|SHORT)\s*진입\s*[:：]\s*(.*)', line, re.I)
        if heading:
            present = True
            direction, body = heading[1].upper(), heading[2]
            if direction in entries:
                gaps.append(dict(line=number, section='entry', text=line, reason='direction_duplicate_definition'))
            nodes = []
            for clause in _clauses(body):
                try:
                    nodes.append(_expression(clause))
                except ValueError as exc:
                    reason = ('volume_average_period_required' if re.search(r'거래량.*평균', clause)
                              else str(exc))
                    gaps.append(dict(line=number, section='entry', text=clause.strip(), reason=reason))
            if nodes:
                entries[direction] = {'expression': nodes[0] if len(nodes)==1 else
                                      {'type':'group','operator':'and','children':nodes}}
            else:
                gaps.append(dict(line=number, section='entry', text=line, reason='direction_entry_definition_required'))
    if not present:
        return {'present':False}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        exit_line = re.fullmatch(r'청산\s*[:：]\s*(.*)', line)
        if exit_line:
            body = exit_line[1].strip().rstrip('.。')
            # This exact label explicitly delegates only to the stated TP/SL.
            if body == '전략 자체 고정 익절·손절':
                continue
            try:
                exits.append(_expression(body))
            except ValueError:
                gaps.append(dict(line=number, section='exit', text=body, reason='direction_exit_definition_required'))
        if re.search(r'\bHIGH\b', line, re.I) and re.search(r'진입하지|HOLD|금지', line, re.I):
            gaps.append(dict(line=number, section='guard', text=line, reason='volatility_scope_definition_required'))
        if re.match(r'공통\s*안전\s*[:：]', line):
            gaps.append(dict(line=number, section='guard', text=line, reason='safety_thresholds_require_definition'))
    return {'present':True, 'entries':entries, 'exit':({'expression':exits[0] if len(exits)==1 else
            {'type':'group','operator':'and','children':exits}} if exits else {'all':[], 'any':[]}), 'gaps':gaps}
