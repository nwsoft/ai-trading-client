"""Bounded source-to-existing-IR compiler. No eval, implicit conditions or orders.

Named boolean definitions and explicit ENTRY/EXIT sections only. Unknown syntax
is retained as a line-level gap; one unresolved clause invalidates that section.
"""
import ast
import math
import re
from copy import deepcopy

from .declarative_strategy_engine import DeclarativeStrategyEngine as Engine


class ConditionCompiler:
    def __init__(self, definitions=None, state_names=()):
        self.definitions = definitions or {}
        self.state_names=set(state_names)
        self.stack = []
        self.count = 0

    def compile(self, expression):
        if len(expression) > 4000:
            raise ValueError('condition_length_limit')
        normalized = re.sub(r'\b(AND|OR)\b', lambda m: m[0].lower(), expression)
        try:
            tree = ast.parse(normalized, mode='eval')
        except (SyntaxError, RecursionError):
            raise ValueError('condition_syntax_unsupported') from None
        if len(list(ast.walk(tree))) > 384:
            raise ValueError('condition_complexity_limit')
        result = self.visit(tree.body, 1)
        validation = Engine.validate_expression_graph(result)
        if not validation['valid']:
            raise ValueError('condition_complexity_or_contract_invalid')
        return result

    def visit(self, node, depth):
        self.count += 1
        if depth > 8 or self.count > 96:
            raise ValueError('condition_complexity_limit')
        if isinstance(node, ast.Name):
            name = node.id.lower()
            if name not in self.definitions:
                raise ValueError(f'condition_definition_required:{name}')
            if name in self.stack:
                raise ValueError(f'condition_circular_reference:{name}')
            self.stack.append(name)
            try:
                text = self.definitions[name]
                if len(text) > 4000:
                    raise ValueError('condition_length_limit')
                text = re.sub(r'\b(AND|OR)\b', lambda m: m[0].lower(), text)
                return self.visit(ast.parse(text, mode='eval').body, depth+1)
            except (SyntaxError, RecursionError):
                raise ValueError(f'condition_definition_unsupported:{name}') from None
            finally:
                self.stack.pop()
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            return {'type':'group','operator':'and' if isinstance(node.op,ast.And) else 'or',
                    'children':[self.visit(child,depth+1) for child in node.values]}
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name = node.func.id.lower()
            if name in {'all_for', 'any_within', 'became_true', 'became_false', 'after', 'latched'}:
                arity = 1 if name.startswith('became_') else 3 if name in {'after','latched'} else 2
                if len(node.args) != arity:
                    raise ValueError('temporal_argument_count_invalid')
                try:
                    bars = 2 if name.startswith('became_') else ast.literal_eval(node.args[-1])
                except (ValueError, TypeError):
                    raise ValueError('temporal_bars_must_be_literal') from None
                if type(bars) is not int or not 1 <= bars <= 100:
                    raise ValueError('temporal_bars_out_of_range')
                args = node.args if name.startswith('became_') else node.args[:-1]
                return {'type':'temporal', 'operator':name, 'bars':bars,
                        'children':[self.visit(arg,depth+1) for arg in args]}
        if not isinstance(node, ast.Compare):
            raise ValueError('condition_syntax_unsupported')
        children = []
        left = node.left
        for op, right in zip(node.ops, node.comparators):
            if not isinstance(left,ast.Name) or left.id.lower() not in Engine.ALLOWED_FIELDS|self.state_names:
                raise ValueError('condition_field_unsupported')
            field = left.id.lower()
            # A document's custom alias cannot silently shadow a built-in field.
            if field in self.definitions:
                raise ValueError(f'condition_field_redefined:{field}')
            operators = {ast.Lt:'lt',ast.LtE:'lte',ast.Gt:'gt',ast.GtE:'gte',ast.Eq:'eq',ast.NotEq:'ne'}
            operator = operators.get(type(op))
            if not operator:
                raise ValueError('condition_operator_unsupported')
            condition = {'field':({'state_variable':field} if field in self.state_names else field),'operator':operator}
            if isinstance(right,ast.Name) and right.id.lower() in Engine.ALLOWED_FIELDS|self.state_names:
                target = right.id.lower()
                if target in self.definitions or field == 'signal' or target == 'signal':
                    raise ValueError('condition_field_comparison_unsupported')
                condition.update(operator=operator+'_field', value_field=({'state_variable':target} if target in self.state_names else target))
            else:
                if isinstance(right,ast.Name) and right.id.upper() in {'LONG','SHORT','HOLD'}:
                    value = right.id.upper()
                else:
                    try:
                        value = ast.literal_eval(right)
                    except (ValueError,TypeError):
                        raise ValueError('condition_value_unsupported') from None
                if field == 'signal':
                    if not isinstance(value,str) or value not in {'LONG','SHORT','HOLD'} or operator not in {'eq','ne'}:
                        raise ValueError('condition_signal_invalid')
                elif isinstance(value,bool) or not isinstance(value,(int,float)) or abs(value) > 1e12 or not math.isfinite(value):
                    raise ValueError('condition_numeric_value_required')
                condition['value'] = value
            valid, reason = Engine.validate_condition_spec(condition)
            if not valid:
                raise ValueError(reason)
            children.append({'type':'condition','condition':condition})
            left = right
        return children[0] if len(children)==1 else {'type':'group','operator':'and','children':children}


def compile_sections(text):
    definitions, sections, gaps = {}, {'entry':[], 'exit':[]}, []
    numeric={'initial':{},'updates':{}}
    state_seen=False
    section = ''
    seen = False
    declared = set()
    timeframe = ''
    for number, raw in enumerate(text.splitlines(),1):
        line = raw.strip()
        if not line or line.startswith(('#','//')):
            continue
        state_line=re.fullmatch(r'(STATE|UPDATE)\s+([a-z][a-z0-9_]{0,31})\s*=\s*(.+)',line)
        if state_line:
            state_seen=True
            section='';kind='initial' if state_line[1]=='STATE' else 'updates';key=state_line[2]
            try:
                if key in numeric[kind]:raise ValueError('state_duplicate_declaration')
                numeric[kind][key]=ast.literal_eval(state_line[3]) if kind=='initial' else state_line[3]
            except (ValueError,SyntaxError):gaps.append({'line':number,'section':'definition','text':line,'reason':'state_declaration_invalid'})
            continue
        if re.match(r'^(STATE|UPDATE)\b',line):
            state_seen=True;section=''
            gaps.append({'line':number,'section':'definition','text':line,'reason':'state_declaration_invalid'})
            continue
        tf = re.fullmatch(r'(?:TIMEFRAME|판단 시간봉)\s*[:：]\s*(\S+)',line,re.I)
        if tf:
            value = tf[1].lower()
            if value not in Engine.ALLOWED_TIMEFRAMES or (timeframe and timeframe != value):
                gaps.append({'line':number,'section':'definition','text':line,'reason':'timeframe_definition_required'})
            else: timeframe = value
            section = ''
            continue
        heading = re.fullmatch(r'(ENTRY|EXIT|진입 조건|청산 조건)\s*[:：]\s*(.*)',line,re.I)
        if heading:
            section = 'entry' if heading[1].lower() in {'entry','진입 조건'} else 'exit'
            seen = True
            declared.add(section)
            if heading[2]: sections[section].append((number,heading[2]))
            continue
        assignment = re.fullmatch(r'([A-Za-z_]\w*)\s*=\s*(.+)',line)
        if assignment and not section:
            key = assignment[1].lower()
            if key in definitions:
                gaps.append({'line':number,'section':'definition','text':line,'reason':'condition_duplicate_definition'})
            definitions[key] = assignment[2]
            continue
        # Explicit metadata/risk headings end a section. Unknown named headings
        # inside a section are kept and rejected, not silently skipped.
        if re.match(r'^(FILTERS?|CONTEXT)\s*:',line,re.I):
            gaps.append({'line':number,'section':'definition','text':line,'reason':'condition_scope_definition_required'})
            section = ''
            continue
        if re.match(r'^(RISK|EXECUTION|METADATA|HARD_GUARDRAIL|END)\b|^\[',line,re.I):
            section = ''
            continue
        if section:
            clause = re.sub(r'^[-*•]\s+', '', line).strip()
            sections[section].append((number,clause))
    result = {'present':seen or state_seen, 'gaps':gaps, 'sections':sections, 'declared':declared, 'timeframe':timeframe}
    if state_seen:
        from .numeric_strategy_state import validate
        for reason in validate(numeric):gaps.append({'line':0,'section':'definition','text':'STATE/UPDATE','reason':reason})
        if set(definitions)&set(numeric['initial']):gaps.append({'line':0,'section':'definition','text':'STATE','reason':'state_name_redefined'})
        if not timeframe:gaps.append({'line':0,'section':'definition','text':'STATE','reason':'state_timeframe_required'})
        if 'entry' not in declared:gaps.append({'line':0,'section':'definition','text':'STATE','reason':'state_entry_section_required'})
        if set(numeric['initial'])&Engine.ALLOWED_FIELDS:gaps.append({'line':0,'section':'definition','text':'STATE','reason':'state_builtin_name_conflict'})
        result['numeric_state']=numeric
    if not seen: return result
    for section, clauses in sections.items():
        nodes = []
        for number, clause in clauses:
            if clause == 'AND': continue
            try:
                nodes.append(ConditionCompiler(definitions,numeric['initial']).compile(clause))
            except ValueError as exc:
                gaps.append({'line':number,'section':section,'text':clause,'reason':str(exc)})
        if nodes:
            root = nodes[0] if len(nodes)==1 else {'type':'group','operator':'and','children':nodes}
            if not Engine.validate_expression_graph(root)['valid']:
                gaps.append({'line':clauses[0][0],'section':section,'text':'section','reason':'condition_complexity_limit'})
            if not any(g['section'] in {section,'definition'} for g in gaps):
                # Preserve the existing serialized shape for a simple clause.
                result[section] = ({'all':[deepcopy(root['condition'])], 'any':[]}
                    if root['type']=='condition' else {'expression':deepcopy(root)})
    return result
