"""Bounded read-only Drive API collection; credentials never enter evidence.

Uses an explicitly supplied API key (public material) or short-lived access
token (authorized material). No cookie scraping, permission changes or writes.
"""
import hashlib
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests

ID = re.compile(r'^[A-Za-z0-9_-]{1,200}$')
FOLDER = 'application/vnd.google-apps.folder'
EXPORTS = {
    'application/vnd.google-apps.document': ('text/plain', '.txt'),
    'application/vnd.google-apps.spreadsheet': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx'),
    'application/vnd.google-apps.presentation': ('application/pdf', '.pdf'),
}
SUFFIXES = {'.txt','.md','.pine','.pinescript','.csv','.tsv','.xlsx','.docx','.pdf','.png','.jpg','.jpeg','.webp','.bmp'}
FIELDS = 'id,name,mimeType,size,md5Checksum,version,modifiedTime,resourceKey,capabilities(canDownload)'


def folder_id(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc != 'drive.google.com':
        raise ValueError('Drive의 https://drive.google.com/drive/folders/... 주소를 입력하세요.')
    match = re.fullmatch(r'/drive/(?:u/\d+/)?folders/([A-Za-z0-9_-]+)/*', parsed.path)
    if not match or not ID.fullmatch(match[1]):
        raise ValueError('Drive 폴더 주소가 필요합니다. 단일 파일은 내려받아 파일 입력을 이용하세요.')
    key = parse_qs(parsed.query).get('resourcekey',[''])[0]
    if key and not ID.fullmatch(key): raise ValueError('Drive 자료 키 형식이 올바르지 않습니다.')
    return match[1], key


class DriveCollector:
    def __init__(self, *, api_key='', access_token='', session=None):
        if any(any(ord(c)<33 or ord(c)>126 for c in secret) for secret in (api_key,access_token)):
            raise ValueError('Drive 인증값의 공백·줄바꿈을 확인하세요.')
        self.api_key, self.access_token = api_key, access_token
        self.session = session or requests.Session()
        self.calls, self.total = 0, 0
        self.deadline = time.monotonic() + 120

    def get(self, path, params, *, limit=1024*1024, resource=None, binary=False):
        if not self.api_key and not self.access_token:
            raise ValueError('Drive 연결 인증이 필요합니다. 공개 자료는 Drive API 키, 비공개 자료는 읽기 권한의 임시 액세스 토큰을 입력하거나 폴더를 내려받아 선택하세요.')
        if self.calls >= 150 or time.monotonic() >= self.deadline:
            raise ValueError('Drive 수집 한도에 도달했습니다. 폴더를 나누어 다시 분석하세요.')
        self.calls += 1
        headers = {}
        if self.access_token: headers['Authorization'] = 'Bearer '+self.access_token
        if self.api_key: headers['X-Goog-Api-Key'] = self.api_key
        if resource and resource[1]: headers['X-Goog-Drive-Resource-Keys'] = '/'.join(resource)
        try:
            with self.session.get('https://www.googleapis.com/drive/v3/files'+path,params=params,
                                  headers=headers,timeout=20,stream=True,allow_redirects=False) as response:
                if response.status_code != 200:
                    raise ValueError(f'Drive 조회 실패 ({response.status_code}). 읽기 권한·API 활성화·인증 만료를 확인하세요.')
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > limit or time.monotonic() >= self.deadline:
                        raise ValueError('Drive 응답 크기·시간 한도를 초과했습니다. 폴더를 나누어 입력하세요.')
                    chunks.append(chunk)
                raw = b''.join(chunks)
        except requests.RequestException:
            raise ValueError('Drive 통신에 실패했습니다. 연결을 확인한 뒤 다시 수집하세요.') from None
        if binary: return raw
        import json
        try: data = json.loads(raw)
        except (ValueError,UnicodeError): raise ValueError('Drive 응답 형식이 올바르지 않습니다.') from None
        if not isinstance(data,dict): raise ValueError('Drive 응답 형식이 올바르지 않습니다.')
        return data

    def extract(self, ingestor, url):
        from .strategy_source_bundle import extract_bundle
        root, root_key = folder_id(url)
        pending, seen, files, omissions = [(root,root_key,0)], set(), [], []
        while pending:
            fid, key, depth = pending.pop(0)
            if fid in seen: continue
            seen.add(fid)
            if depth > 5 or len(seen) > 40:
                omissions.append({'id':fid,'reason':'folder_depth_or_count_limit'}); continue
            cursor, cursors = '', set()
            while True:
                data = self.get('',{'q':f"'{fid}' in parents and trashed = false",'pageSize':100,
                    'fields':f'nextPageToken,incompleteSearch,files({FIELDS})', 'pageToken':cursor,
                    'supportsAllDrives':'true','includeItemsFromAllDrives':'true'},resource=(fid,key))
                if data.get('incompleteSearch'): omissions.append({'id':fid,'reason':'incomplete_search'})
                rows = data.get('files')
                if not isinstance(rows,list): raise ValueError('Drive 자료 목록을 확인할 수 없습니다.')
                for row in rows:
                    identity = str(row.get('id') or '')
                    if not ID.fullmatch(identity): raise ValueError('Drive 자료 ID가 올바르지 않습니다.')
                    if row.get('mimeType') == FOLDER:
                        pending.append((identity,str(row.get('resourceKey') or ''),depth+1))
                    elif all(f['id']!=identity for f in files):
                        files.append(row)
                    if len(files)>40 or len(pending)>40:
                        raise ValueError('Drive 폴더는 최대 40개 자료입니다. 폴더를 나누어 입력하세요.')
                next_cursor = data.get('nextPageToken') or ''
                if not next_cursor: break
                if next_cursor in cursors: raise ValueError('Drive 연속조회가 진행되지 않았습니다. 다시 수집하세요.')
                cursors.add(next_cursor); cursor = next_cursor
        items, provenance = [], []
        with tempfile.TemporaryDirectory(prefix='noah_drive_') as temporary:
            for row in files:
                fid, name = row['id'], str(row.get('name') or row['id'])
                resource = (fid,str(row.get('resourceKey') or ''))
                mime = row.get('mimeType')
                export = EXPORTS.get(mime)
                suffix = export[1] if export else Path(name).suffix.lower()
                if suffix not in SUFFIXES or row.get('capabilities',{}).get('canDownload') is False:
                    omissions.append({'id':fid,'name':name,'reason':'unsupported_or_download_forbidden'}); continue
                if int(row.get('size') or 0)>24*1024*1024:
                    omissions.append({'id':fid,'name':name,'reason':'file_size_limit'}); continue
                raw = self.get('/'+fid+('/export' if export else ''),
                    {'mimeType':export[0]} if export else {'alt':'media'},binary=True,limit=24*1024*1024,resource=resource)
                self.total += len(raw)
                if self.total>64*1024*1024: raise ValueError('Drive 자료 합계는 64MiB 이하입니다. 폴더를 나누세요.')
                if row.get('md5Checksum') and not export and hashlib.md5(raw).hexdigest()!=row['md5Checksum']:
                    raise ValueError('수집 도중 Drive 자료가 변경되었습니다. 다시 분석하세요.')
                latest = self.get('/'+fid,{'fields':'id,version,modifiedTime','supportsAllDrives':'true'},resource=resource)
                if any(latest.get(k)!=row.get(k) for k in ('id','version','modifiedTime')):
                    raise ValueError('수집 도중 Drive 자료가 변경되었습니다. 다시 분석하세요.')
                path = Path(temporary)/f'{len(items)}{suffix}'
                path.write_bytes(raw)
                items.append({'value':str(path),'name':name,'kind':'auto'})
                provenance.append({'id':fid,'name':name,'version':row.get('version'),
                                   'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'exported':bool(export)})
            if not items: raise ValueError('읽을 수 있는 Drive 자료가 없습니다. 접근 권한·파일 형식을 확인하세요.')
            result = extract_bundle(ingestor,items)
            # Do not retain deleted temporary paths or authentication in IR/evidence.
            def sanitize(value):
                if isinstance(value,dict): return {k:sanitize(v) for k,v in value.items()}
                if isinstance(value,list): return [sanitize(v) for v in value]
                return 'drive-downloaded-material' if isinstance(value,str) and temporary in value else value
            result.evidence = sanitize(result.evidence)
            result.reference = f'https://drive.google.com/drive/folders/{root}'
            result.evidence.update(drive_files=provenance,drive_omissions=omissions)
            if omissions:
                result.warnings.append('Drive 자료 일부가 누락되었습니다. 누락 목록을 확인하고 파일을 보완하세요.')
                result.evidence['coverage_complete'] = False
                reasons = {'folder_depth_or_count_limit':'하위 폴더 탐색 한도 초과',
                           'incomplete_search':'Google이 목록 검색 불완전으로 응답',
                           'unsupported_or_download_forbidden':'지원하지 않는 형식 또는 다운로드 권한 없음',
                           'file_size_limit':'파일 24MiB 한도 초과'}
                for index, item in enumerate(omissions,1):
                    result.evidence['sources'].append({'id':f'D{index}','name':item.get('name') or item['id'],
                        'included_characters':0,'extracted_characters':0,'truncated':True,'duplicate':False,
                        'warnings':[reasons.get(item['reason'],item['reason'])]})
            return result
