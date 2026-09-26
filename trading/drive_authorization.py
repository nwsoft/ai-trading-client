"""Optional Drive read authorization; never a NoahAI login provider.

Desktop loopback + PKCE. Tokens stay in this account-scoped service's memory;
restart requires reconnect, and no Google credential enters strategy/AI data.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse
from pathlib import Path

import requests

SCOPE = 'https://www.googleapis.com/auth/drive.readonly'


def deployment_config():
    config = {}
    public_key=''
    packaged=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'config'/'drive_client.json'
    path = os.environ.get('NOAHAI_DRIVE_CLIENT_CONFIG') or (str(packaged) if packaged.is_file() else '')
    if path:
        try:
            with open(path,encoding='utf-8') as stream:
                raw=stream.read(262145)
                if len(raw)>262144:raise ValueError('config_too_large')
                document=json.loads(raw)
                config = document.get('installed',{})
                public_key=document.get('public_api_key','')
                if not isinstance(config,dict) or not isinstance(public_key,str):
                    raise ValueError('invalid_config')
                if any(not isinstance(config.get(key,''),str) for key in ('client_id','client_secret')):
                    raise ValueError('invalid_config')
        except (OSError,ValueError,AttributeError):
            raise ValueError('Drive 운영자 연결 설정 파일을 확인하세요.') from None
    return {'client_id':os.environ.get('NOAHAI_DRIVE_OAUTH_CLIENT_ID') or config.get('client_id',''),
            'client_secret':os.environ.get('NOAHAI_DRIVE_OAUTH_CLIENT_SECRET') or config.get('client_secret',''),
            'api_key':os.environ.get('NOAHAI_DRIVE_API_KEY') or public_key}


class DriveAuthorization:
    def __init__(self,config=None,session=None):
        self.config = deployment_config() if config is None else config
        self.session = session or requests.Session()
        self.lock = threading.RLock()
        self.tokens = {}
        self.pending = None
        self.last_result = ''
        self.generation = 0

    def status(self):
        with self.lock:
            return {'public_ready':bool(self.config.get('api_key')),
                    'authorization_ready':bool(self.config.get('client_id')),
                    'connected':bool(self.tokens), 'pending':self.pending is not None,
                    'result':self.last_result,'scope':'Drive 전체 읽기 전용',
                    'persistent':False}

    def _token_request(self,payload):
        try:
            response = self.session.post('https://oauth2.googleapis.com/token',
                data={**payload,'client_id':self.config['client_id'],
                      'client_secret':self.config.get('client_secret','')},
                timeout=20,allow_redirects=False)
            if response.status_code != 200: raise ValueError('drive_reconnect_required')
            data = response.json()
            if not isinstance(data,dict) or not isinstance(data.get('access_token'),str) or not data['access_token']:
                raise ValueError('drive_reconnect_required')
            if str(data.get('token_type','')).lower()!='bearer': raise ValueError('drive_reconnect_required')
            if SCOPE not in str(data.get('scope') or SCOPE).split(): raise ValueError('drive_read_permission_required')
            ttl = float(data['expires_in'])
            if not 0 < ttl <= 86400: raise ValueError('drive_reconnect_required')
            return {**data,'expires_at':time.time()+ttl}
        except (requests.RequestException,KeyError,TypeError,ValueError):
            raise ValueError('Google Drive 연결이 만료되었거나 승인되지 않았습니다. 다시 연결하세요.') from None

    def access_token(self):
        with self.lock:
            if not self.tokens: return ''
            if self.tokens['expires_at']>time.time()+60: return self.tokens['access_token']
            refresh = self.tokens.get('refresh_token')
            if not refresh:
                self.tokens={}; self.last_result='reconnect_required'
                raise ValueError('Google Drive를 다시 연결하세요.')
            try:
                data = self._token_request({'grant_type':'refresh_token','refresh_token':refresh})
                self.tokens={**data,'refresh_token':data.get('refresh_token') or refresh}
            except ValueError:
                self.tokens={}; self.last_result='reconnect_required'
                raise
            return self.tokens['access_token']

    def disconnect(self):
        with self.lock:
            self.generation+=1
            self.tokens={}; self.pending=None; self.last_result='disconnected'
        return self.status()

    def complete(self,state,code,error,generation):
        with self.lock:
            pending=self.pending
            if not pending or generation!=self.generation or time.monotonic()>pending['deadline']:
                return False
            if not isinstance(state,str) or not hmac.compare_digest(state,pending['state']): return False
            self.pending=None
            if error or not code:
                self.last_result='cancelled'; return False
            try:
                self.tokens=self._token_request({'grant_type':'authorization_code','code':code,
                    'redirect_uri':pending['redirect'],'code_verifier':pending['verifier']})
                self.last_result='connected'; return True
            except ValueError:
                self.last_result='reconnect_required'; return False

    def start(self,opener=webbrowser.open):
        with self.lock:
            if not self.config.get('client_id'):
                raise ValueError('운영자의 Google Drive 앱 등록이 필요합니다. 내려받은 파일·폴더 입력은 이용할 수 있습니다.')
            if self.pending: return self.status()
            owner=self
            generation=self.generation
            class Callback(BaseHTTPRequestHandler):
                def setup(self):
                    super().setup()
                    self.connection.settimeout(5)
                def log_message(self,*args): pass  # Never log authorization code.
                def do_GET(self):
                    if len(self.path)>8192:
                        self.send_error(414);return
                    parsed=urlparse(self.path)
                    if parsed.path!='/drive-callback' or self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}':
                        self.send_error(404); return
                    query=parse_qs(parsed.query)
                    ok=owner.complete(query.get('state',[''])[0],query.get('code',[''])[0],query.get('error',[''])[0],generation)
                    body=('Drive connected. You may close this tab.' if ok else 'Authorization not completed. Return to NoahAI.').encode()
                    self.send_response(200 if ok else 400)
                    self.send_header('Content-Type','text/plain; charset=utf-8')
                    self.send_header('Cache-Control','no-store')
                    self.send_header('Referrer-Policy','no-referrer')
                    self.end_headers(); self.wfile.write(body)
            server=HTTPServer(('127.0.0.1',0),Callback)
            server.timeout=0.5
            verifier=secrets.token_urlsafe(48)
            redirect=f'http://127.0.0.1:{server.server_port}/drive-callback'
            self.pending={'state':secrets.token_urlsafe(32),'verifier':verifier,'redirect':redirect,
                          'deadline':time.monotonic()+180}
            query={'client_id':self.config['client_id'],'redirect_uri':redirect,'response_type':'code',
                   'scope':SCOPE,'state':self.pending['state'],'code_challenge_method':'S256',
                   'code_challenge':base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode(),
                   'access_type':'offline','prompt':'consent'}
            def listen():
                try:
                    while True:
                        with owner.lock:
                            current=owner.pending
                            active=current and generation==owner.generation and time.monotonic()<current['deadline']
                        if not active:break
                        server.handle_request()
                finally:
                    server.server_close()
                    with owner.lock:
                        if generation==owner.generation and owner.pending:
                            owner.pending=None; owner.last_result='timed_out'
            threading.Thread(target=listen,daemon=True,name='drive-read-authorization').start()
            try: opened=opener('https://accounts.google.com/o/oauth2/v2/auth?'+urlencode(query))
            except Exception: opened=False
            if not opened:
                self.pending=None; self.last_result='browser_open_failed'
                raise ValueError('기본 브라우저를 열지 못했습니다. 브라우저 설정을 확인하세요.')
            self.last_result='awaiting_consent'
            return self.status()
