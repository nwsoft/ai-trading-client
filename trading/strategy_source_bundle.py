"""Bounded, provenance-preserving extraction. Documents are data, not instructions."""
import hashlib
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

MAX_FILES = 40
MAX_BYTES = 64 * 1024 * 1024


def office_text(path):
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 10000 or sum(i.file_size for i in entries) > MAX_BYTES:
            raise ValueError('Office 자료의 압축 해제 크기가 제한을 초과합니다.')
        def xml(name):
            raw = archive.read(name)
            if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
                raise ValueError('지원하지 않는 XML 선언입니다.')
            return ET.fromstring(raw)
        if path.suffix.lower() == '.docx':
            root = xml('word/document.xml')
            return '\n'.join(''.join(p.itertext()) for p in root.iter() if p.tag.endswith('}p'))
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(n.itertext()) for n in xml('xl/sharedStrings.xml')]
        sections = []
        for name in sorted(n for n in archive.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')):
            lines = []
            for row in xml(name).iter():
                if not row.tag.endswith('}row'): continue
                cells = []
                for cell in row:
                    value = next((n.text or '' for n in cell if n.tag.endswith('}v')), '')
                    if cell.get('t') == 's': value = strings[int(value)]
                    elif cell.get('t') == 'inlineStr': value = ''.join(cell.itertext())
                    formula = next((n.text for n in cell if n.tag.endswith('}f')), None)
                    cells.append(f"{cell.get('r','')}={value}" + (f' [formula:{formula}; cached value]' if formula else ''))
                lines.append('\t'.join(cells))
            sections.append(f'[{name}]\n'+'\n'.join(lines))
        return '\n\n'.join(sections)


def extract_bundle(ingestor, items):
    from trading.strategy_source_ingestor import ExtractedStrategySource
    if not 1 <= len(items) <= MAX_FILES:
        raise ValueError('자료는 1~40개까지 함께 분석할 수 있습니다.')
    sources, manifest, warnings = [], [], []
    seen = set()
    declared = {}
    quota = max(1, (ingestor.AI_CONTENT_CHAR_LIMIT - 4000) // len(items))
    for index, item in enumerate(items, 1):
        source = ingestor.extract(item['value'], item.get('kind', 'auto'))
        label = str(item.get('name') or source.title)[:200]
        digest = hashlib.sha256(source.text.encode()).hexdigest()
        duplicate = digest in seen
        seen.add(digest)
        included = '' if duplicate else source.text[:quota]
        clipped = not duplicate and len(source.text) > len(included)
        if not duplicate:
            # Different source rules are not an implicit AND, OR or override.
            # Require user clarification rather than silently taking the first.
            bounded = ExtractedStrategySource(source.kind,source.reference,source.title,included,[],{})
            rules = ingestor._heuristic_rules(bounded)
            checks = {key:rules.get(key) for key in ('executable_entry','executable_exit','entry_signal')}
            checks.update({f'engine_settings.{key}':value for key,value in (rules.get('engine_settings') or {}).items() if key!='_unit'})
            checks.update({f'risk_model.{key}':value for key,value in (rules.get('risk_model') or {}).items()})
            for key,value in checks.items():
                if not value or value=={'all':[]} or value=='auto': continue
                encoded=json.dumps(value,sort_keys=True,ensure_ascii=False)
                previous=declared.get(key)
                if previous and previous[0]!=encoded:
                    warnings.append(f'S{index} {label}: {previous[1]}와 {key} 조건이 다릅니다. 사용할 조건과 결합 방식을 직접 확인하세요.')
                else: declared[key]=(encoded,f'S{index}')
            warnings.extend(f'S{index} {label}: {issue}' for issue in rules.get('compiler_issues',[]))
        manifest.append({'id':f'S{index}', 'name':label, 'kind':source.kind,
                         'content_sha256':digest, 'extracted_characters':len(source.text),
                         'included_characters':len(included), 'duplicate':duplicate, 'truncated':clipped,
                         'warnings':source.warnings, 'evidence':source.evidence})
        warnings.extend(f'S{index} {label}: {w}' for w in source.warnings)
        if clipped: warnings.append(f'S{index} {label}: 추출 {len(source.text)}자 중 {len(included)}자만 포함. 자료를 나누어 재분석하세요.')
        if not source.text.strip(): warnings.append(f'S{index} {label}: 읽을 수 있는 본문이 없습니다.')
        if included: sources.append(f'[자료 S{index}: {label}]\n{included}')
    if not sources: raise ValueError('분석할 자료 본문이 없습니다.')
    return ExtractedStrategySource('bundle', 'user-selected-materials', '사용자 선택 자료 묶음',
        '\n\n'.join(sources), warnings, {'sources':manifest, 'source_count':len(items),
        'coverage_complete':not warnings, 'documents_are_untrusted_data':True})
