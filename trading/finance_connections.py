"""Operator-reviewed recipient registry and a bounded, future API contract.

No recipient is bundled or enabled automatically. Credentials are environment
references, not part of a client response or a consultation packet.
"""
import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
from pathlib import Path
from urllib.parse import urlsplit, urlencode


class FinanceConnectionError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def https_url(value):
    p = urlsplit(str(value))
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.fragment or p.port not in (None, 443):
        raise FinanceConnectionError('finance_https_required')
    return str(value)


def validate_recipient(row):
    if not isinstance(row, dict):
        raise FinanceConnectionError('finance_recipient_invalid')
    allowed = {'id', 'name', 'organization', 'role', 'kinds', 'mode', 'enabled', 'review_reference', 'contract_version', 'privacy_url', 'contact_url', 'retention_days', 'endpoints', 'token_env', 'commercial_notice'}
    if set(row) - allowed or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', str(row.get('id', ''))):
        raise FinanceConnectionError('finance_recipient_invalid')
    for field in ('name', 'organization', 'role', 'review_reference', 'contract_version'):
        if not isinstance(row.get(field), str) or not 1 <= len(row[field]) <= 500:
            raise FinanceConnectionError('finance_recipient_review_required')
    if row.get('mode') not in ('manual', 'api') or not isinstance(row.get('kinds'), list) or not row['kinds'] or set(row['kinds']) - {'loan', 'insurance', 'savings'}:
        raise FinanceConnectionError('finance_recipient_invalid')
    if type(row.get('enabled')) is not bool or type(row.get('retention_days')) is not int or not 1 <= row['retention_days'] <= 365:
        raise FinanceConnectionError('finance_recipient_invalid')
    https_url(row.get('privacy_url'))
    https_url(row.get('contact_url'))
    if row['mode'] == 'api':
        endpoints = row.get('endpoints')
        if not isinstance(endpoints, dict) or set(endpoints) != {'submit', 'status', 'withdraw'}:
            raise FinanceConnectionError('finance_endpoint_contract_required')
        hosts = {urlsplit(https_url(v)).hostname for v in endpoints.values()}
        if len(hosts) != 1 or not re.fullmatch(r'NOAHAI_FINANCE_[A-Z0-9_]{1,100}', str(row.get('token_env', ''))):
            raise FinanceConnectionError('finance_endpoint_contract_required')
    return dict(row)


class RecipientRegistry:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / 'finance_recipients.json'

    def all(self):
        if not self.path.exists():
            return []
        with self.path.open('rb') as stream:
            raw = stream.read(256 * 1024 + 1)
        if len(raw) > 256 * 1024:
            raise FinanceConnectionError('finance_registry_limit')
        value = json.loads(raw)
        if not isinstance(value, list) or len(value) > 100:
            raise FinanceConnectionError('finance_registry_invalid')
        rows = [validate_recipient(row) for row in value]
        if len({r['id'] for r in rows}) != len(rows):
            raise FinanceConnectionError('finance_registry_duplicate')
        return rows

    def get(self, recipient_id):
        row = next((r for r in self.all() if r['id'] == recipient_id and r['enabled']), None)
        if row is None:
            raise FinanceConnectionError('finance_recipient_unavailable')
        return row

    def public(self):
        return [{k: v for k, v in row.items() if k not in {'endpoints', 'token_env', 'review_reference'}} for row in self.all() if row['enabled']]


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, hostname, address):
        super().__init__(hostname, port=443, timeout=10, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Connect to the address already checked, retaining TLS hostname validation.
        sock = socket.create_connection((self.address, 443), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def api_transport(recipient, action, packet, key):
    """Fixed reviewed host, no redirects, pinned public DNS, bounded response."""
    url = https_url(recipient['endpoints'][action])
    parsed = urlsplit(url)
    addresses = sorted({a[4][0] for a in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)})
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise FinanceConnectionError('finance_endpoint_not_public')
    token = os.environ.get(recipient['token_env'])
    if not token or len(token) > 8192 or '\r' in token or '\n' in token:
        raise FinanceConnectionError('finance_connection_not_configured')
    path = parsed.path or '/'
    query = parsed.query
    method = 'GET' if action == 'status' else 'POST'
    if method == 'GET':
        query = '&'.join(filter(None, [query, urlencode({'request_id': packet['request_id']})]))
    if query:
        path += '?' + query
    body = None if method == 'GET' else json.dumps(packet, ensure_ascii=False, allow_nan=False).encode()
    if body and len(body) > 128 * 1024:
        raise FinanceConnectionError('finance_packet_limit')
    connection = _PinnedHTTPS(parsed.hostname, addresses[0])
    try:
        connection.request(method, path, body=body, headers={'Authorization': 'Bearer ' + token, 'Idempotency-Key': key, 'Content-Type': 'application/json'})
        response = connection.getresponse()
        data = response.read(128 * 1024 + 1)
        if response.status not in (200, 201, 202) or len(data) > 128 * 1024:
            raise FinanceConnectionError('finance_delivery_unconfirmed')
        result = json.loads(data)
        if not isinstance(result, dict) or result.get('request_id') != packet['request_id']:
            raise FinanceConnectionError('finance_receipt_mismatch')
        return result
    finally:
        connection.close()
