"""Read every exported text log/archive; emit finite categories, never raw messages."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

CATEGORIES = {
    'catalogue_unavailable': r'trading_candidate_catalogue_unavailable',
    'tickers_unavailable': r'trading_candidate_tickers_unavailable',
    'candidate_empty': r'후보 종목이 없습니다|trading_candidate_markets_unavailable|trading_candidate_filters_excluded',
    'paper_funds_unverified': r'paper_funds_unverified|PAPER 청산 기록|paper_ledger_',
    'confidence_low': r'AI 신뢰도 부족',
    'loss_rate_high': r'높은 손실률',
    'consensus_low': r'consensus_low',
    'strategy_guardrail': r'전략 가드레일|guardrail',
    'position_query_error': r'positions_status["\s:]+error|포지션.*조회.*실패',
    'network_timeout': r'RequestTimeout|ReadTimeout|ConnectTimeout|timed out|시간 초과|TimeoutError',
    'network_connection': r'ConnectionError|NetworkError|연결 실패|Failed to establish|NameResolutionError',
    'authentication': r'AuthenticationError|Invalid API|invalid api|인증 실패|권한.*없|PermissionDenied',
    'rate_limit': r'RateLimit|Too many requests|요청 제한|429',
    'clock_error': r'10002|recv_window|Timestamp.*outside|시간 동기화.*실패',
    'unsupported_symbol': r'BadSymbol|does not have market symbol|미지원 심볼',
    'quantity_precision': r'precision|최소 주문|최소 수량|최소.*금액',
    'strategy_missing': r'전략.*없|strategy.*not found',
    'runtime_exception': r'Traceback|Exception|Error:',
}
PATTERNS = {k: re.compile(v, re.I) for k, v in CATEGORIES.items()}
FAST_TOKENS = ('WARNING','ERROR','CRITICAL','FATAL','실패','부족','unverified','unavailable',
               'Traceback','손실률','guardrail','consensus_low','Exception','Error','후보 종목이 없습니다','미지원','최소 주문')


def audit(root, output):
    paths = sorted(p for folder in ('logs', 'log_archives') for p in (root/folder).rglob('*')
                   if p.is_file() and ('.log' in p.name or '.jsonl' in p.name))
    report = dict(scope='all exported logs and gzip log archives; no learning archives',
                  recent_since_kst='2026-10-06', files=[], categories={}, error_shapes={}, failures=[])
    groups = collections.defaultdict(collections.Counter)
    shapes = collections.Counter()
    references = {}
    for path in paths:
        venue_match = re.search(r'trading_([a-z]+)', path.name)
        venue = venue_match[1] if venue_match else path.stem
        first = last = ''
        lines = recent = errors = unknown = 0
        try:
            opener = gzip.open if path.suffix == '.gz' else open
            with opener(path, 'rt', encoding='utf-8-sig', errors='replace') as handle:
                for line in handle:
                    lines += 1
                    if line.startswith('2026-'):
                        stamp = line[:19]
                    else:
                        match = re.search(r'2026-\d\d-\d\d[ T]\d\d:\d\d:\d\d', line[:180])
                        stamp = match[0].replace('T', ' ') if match else ''
                    if stamp:
                        first = first or stamp
                        last = stamp
                    is_recent = bool(stamp and stamp[:10] >= '2026-10-06')
                    recent += is_recent
                    if not any(token in line for token in FAST_TOKENS):
                        continue
                    is_error = bool(re.search(r'\b(ERROR|CRITICAL|FATAL)\b|Traceback', line))
                    errors += is_error
                    codes = [code for code, pattern in PATTERNS.items() if pattern.search(line)]
                    for code in codes:
                        groups[venue][code + ('_recent' if is_recent else '_older_or_undated')] += 1
                    if is_error and not codes:
                        unknown += 1
                        # A digest identifies an unclassified line without exporting it.
                        normalized = re.sub(r'\d+', '#', line)
                        key = (venue,hashlib.sha256(normalized.encode()).hexdigest()[:16])
                        shapes[key] += 1
                        references.setdefault(key,dict(path=str(path.relative_to(root)),line=lines))
            report['files'].append(dict(path=str(path.relative_to(root)), lines=lines, recent_lines=recent,
                                        errors=errors, unclassified_errors=unknown, first=first, last=last))
        except Exception as exc:
            report['failures'].append(dict(path=str(path.relative_to(root)), type=type(exc).__name__))
    report['categories'] = {k:dict(v) for k,v in groups.items()}
    report['error_shapes'] = [dict(source=k[0],digest=k[1],count=v,**references[k]) for k,v in shapes.most_common(100)]
    report['totals'] = dict(files=len(paths),lines=sum(x['lines'] for x in report['files']),
                            errors=sum(x['errors'] for x in report['files']),
                            unclassified_errors=sum(x['unclassified_errors'] for x in report['files']))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(output=str(output),**report['totals'],failed_files=len(report['failures']))))


if __name__ == '__main__':
    audit(Path(sys.argv[1]),Path(sys.argv[2]))
