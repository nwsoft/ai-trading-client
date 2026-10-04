"""Account-encrypted consultation workflow; transport is explicit and replaceable."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import secrets
import time
from trading.finance_connections import RecipientRegistry, FinanceConnectionError, api_transport, digest
from trading.finance_product_intelligence import ProductCatalog, compare_scenario

SCOPES = {'summary', 'comparison', 'profile', 'contact'}
PROFILE_FIELDS = {'amount', 'months', 'method', 'insurance_state', 'insurance_kind', 'insurance_budget', 'required_coverages', 'target_amount', 'monthly_income', 'monthly_expenses', 'other_repayments', 'monthly_saving'}
RECEIPT_STATES = {'received', 'in_consultation', 'closed', 'withdrawn', 'deleted'}


def now():
    return datetime.now(timezone.utc).isoformat()


def text(value, limit=1000):
    if not isinstance(value, str) or len(value) > limit or '\x00' in value:
        raise FinanceConnectionError('finance_handoff_invalid_text')
    return value.strip()


class FinanceHandoff:
    def __init__(self, workspace, transport=None):
        self.workspace = workspace
        self.directory = workspace.directory.parents[1]
        self.registry = RecipientRegistry(self.directory)
        self.transport = transport or api_transport

    def recipients(self):
        return {'recipients': self.registry.public(), 'live_connection_required': True}

    def _packet(self, scenario, scopes, contact, note):
        if not isinstance(scopes, list) or not scopes or len(scopes) != len(set(scopes)) or set(scopes) - SCOPES:
            raise FinanceConnectionError('finance_handoff_scope_required')
        result = compare_scenario(scenario, ProductCatalog(self.directory / 'finance_product_catalog.sqlite3').snapshot())
        packet = {'schema': 'noah-consultation-v1', 'kind': scenario['kind'], 'scopes': scopes}
        if 'summary' in scopes:
            packet['summary'] = {'note': text(note, 3000), 'questions': result['questions'], 'rule_version': result['rule_version']}
        if 'comparison' in scopes:
            packet['comparison'] = {k: result[k] for k in ('candidates', 'excluded', 'best', 'status')}
            if result.get('reference_products'):
                packet['comparison']['reference_products']=[{k:r.get(k) for k in ('id','name','provider','source_url','version','observed_at','review_due','evidence_status')} for r in result['reference_products']]
            # Hundreds of amortization rows do not belong in a lead payload.
            for row in packet['comparison']['candidates']:
                if 'estimate' in row:
                    row['estimate'].pop('schedule', None)
        if 'profile' in scopes:
            packet['profile'] = {k: v for k, v in scenario.get('profile', {}).items() if k in PROFILE_FIELDS}
        if 'contact' in scopes:
            if not isinstance(contact, dict) or set(contact) - {'name', 'phone', 'email', 'preferred_time'}:
                raise FinanceConnectionError('finance_contact_invalid')
            clean = {k: text(v, 200) for k, v in contact.items()}
            if not clean.get('name') or not (clean.get('phone') or clean.get('email')):
                raise FinanceConnectionError('finance_contact_required')
            packet['contact'] = clean
        if len(json.dumps(packet, ensure_ascii=False, allow_nan=False).encode()) > 110 * 1024:
            raise FinanceConnectionError('finance_packet_limit')
        return packet

    def dispatch(self, operation='list', **args):
        if operation == 'recipients':
            return self.recipients()
        vault = self.workspace
        with vault._mutex:
            vault._require()
            data = deepcopy(vault._data)
            rows = data.setdefault('finance_handoffs', {})
            if operation == 'list':
                return {'requests': list(rows.values()), **self.recipients()}
            if operation == 'prepare':
                if len(rows) >= 100:
                    raise FinanceConnectionError('finance_handoff_limit')
                scenario = args['scenario']
                recipient_id = args.get('recipient_id') or None
                recipient = self.registry.get(recipient_id) if recipient_id else None
                if recipient and scenario.get('kind') not in recipient['kinds']:
                    raise FinanceConnectionError('finance_recipient_kind_mismatch')
                packet = self._packet(scenario, args.get('scopes'), args.get('contact', {}), args.get('note', ''))
                request_id = secrets.token_hex(16)
                packet['request_id'] = request_id
                packet['recipient_id'] = recipient_id
                row = {'id': request_id, 'state': 'prepared', 'created_at': now(), 'packet': packet,
                       'payload_hash': digest(packet), 'recipient_id': recipient_id,
                       'recipient_hash': digest(recipient) if recipient else None,
                       'recipient_name': recipient['name'] if recipient else '수신처 미지정',
                       'recipient_snapshot':{k:recipient[k] for k in ('id','name','organization','mode','privacy_url','contact_url','contract_version','retention_days')} if recipient else None,
                       'consent': None, 'receipt': None, 'attempts': 0, 'next_attempt': 0,
                       'events': [{'state': 'prepared', 'at': now()}], 'external_delivery': False}
                rows[request_id] = row
                vault._persist(data)
                return {'request': deepcopy(row)}
            row = rows.get(args.get('request_id'))
            if row is None:
                raise FinanceConnectionError('finance_handoff_not_found')

            def save(state):
                row['state'] = state
                row['updated_at'] = now()
                row['events'] = [*row['events'][-49:], {'state': state, 'at': now()}]
                vault._persist(data)
                return {'request': deepcopy(row)}

            if operation == 'delete':
                if args.get('confirmed') is not True or row['state'] not in {'prepared', 'consented', 'withdrawn', 'deleted', 'closed'}:
                    raise FinanceConnectionError('finance_withdraw_before_delete')
                del rows[row['id']]
                vault._persist(data)
                return {'deleted_locally': True, 'external_deletion_confirmed': row['state'] == 'deleted'}
            if operation == 'withdraw' and row['state'] in {'prepared', 'consented'}:
                row['consent'] = None
                return save('withdrawn')
            # Viewing/downloading an unassigned preparation is possible without a recipient.
            if operation == 'preview':
                return {'request': deepcopy(row)}
            if operation == 'withdraw':
                row['consent'] = None
                save('withdrawal_requested')
            try:
                recipient = self.registry.get(row['recipient_id'])
            except FinanceConnectionError:
                if operation == 'withdraw':return {'request':deepcopy(row)}
                raise
            if digest(recipient) != row['recipient_hash']:
                if operation == 'withdraw':return {'request':deepcopy(row)}
                raise FinanceConnectionError('finance_recipient_changed_prepare_again')
            if operation == 'consent':
                if row['state'] != 'prepared' or args.get('confirmed') is not True or args.get('payload_hash') != row['payload_hash']:
                    raise FinanceConnectionError('finance_consent_preview_required')
                row['consent'] = {'at': now(), 'expires_at': (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                                  'version': recipient['contract_version'], 'payload_hash': row['payload_hash'],
                                  'recipient_hash': row['recipient_hash'], 'scopes': row['packet']['scopes'],
                                  'purpose': '사용자가 선택한 금융상품 비교·견적 상담', 'retention_days': recipient['retention_days']}
                return save('consented')
            if operation == 'manual_packet':
                self._consent(row)
                if recipient['mode'] != 'manual' or row['state'] not in {'consented', 'package_prepared'}:
                    raise FinanceConnectionError('finance_manual_packet_unavailable')
                row['external_delivery'] = None
                result = save('package_prepared')
                result['download'] = {'recipient': recipient['name'], 'contact_url': recipient['contact_url'], 'packet': row['packet'], 'consent': row['consent'], 'receipt_confirmed': False}
                return result
            if operation == 'record_manual_receipt':
                if recipient['mode'] != 'manual' or row['state'] != 'package_prepared' or args.get('confirmed') is not True:
                    raise FinanceConnectionError('finance_manual_receipt_unavailable')
                receipt_id = text(args.get('receipt_id', ''), 200)
                if not receipt_id:
                    raise FinanceConnectionError('finance_receipt_required')
                row['receipt'] = {'id': receipt_id, 'basis': 'user_reported', 'at': now()}
                return save('receipt_reported')
            if operation == 'record_manual_outcome':
                state=args.get('outcome')
                if recipient['mode']!='manual' or row['state'] not in {'receipt_reported','withdrawal_requested'} or state not in {'closed','withdrawn'} or args.get('confirmed') is not True:
                    raise FinanceConnectionError('finance_manual_outcome_unavailable')
                receipt_id=text(args.get('receipt_id',''),200)
                if not receipt_id:raise FinanceConnectionError('finance_receipt_required')
                row['consent']=None
                row['receipt']={'id':receipt_id,'basis':'user_reported','at':now()}
                return save(state)
            if operation == 'withdraw' and recipient['mode'] == 'manual':
                row['consent'] = None
                return save('withdrawal_requested')
            if recipient['mode'] != 'api' or operation not in {'submit', 'status', 'withdraw'}:
                raise FinanceConnectionError('finance_handoff_operation_unavailable')
            if operation == 'submit':
                if row['state'] in RECEIPT_STATES:
                    return {'request': deepcopy(row)}
                self._consent(row)
                if row['state'] != 'consented':
                    raise FinanceConnectionError('finance_query_status_before_retry')
                if 'contact' not in row['packet']['scopes']:
                    raise FinanceConnectionError('finance_contact_scope_required')
            elif operation == 'status' and row['state'] in {'prepared', 'consented'}:
                return {'request': deepcopy(row)}
            if time.time() < row['next_attempt']:
                if operation == 'withdraw':
                    return {'request':deepcopy(row)}
                raise FinanceConnectionError('finance_handoff_retry_later')
            if operation == 'withdraw':
                row['consent'] = None
            prior_state = row['state']
            if operation=='submit':row['external_delivery']=None
            row['attempts'] += 1
            row['next_attempt'] = time.time() + min(3600, 5 * 2 ** min(row['attempts'], 9))
            save('submitting' if operation == 'submit' else 'withdrawal_requested' if operation == 'withdraw' else prior_state)
            payload = row['packet'] if operation == 'submit' else {'request_id': row['id'], 'receipt_id': (row['receipt'] or {}).get('id')}
            try:
                response = self.transport(recipient, operation, payload, row['id'] + (':withdraw' if operation == 'withdraw' else ''))
                if not isinstance(response, dict) or response.get('request_id') != row['id']:
                    raise FinanceConnectionError('finance_receipt_mismatch')
                state = response.get('status')
                if state == 'not_found' and operation == 'status' and prior_state in {'delivery_unknown', 'submitting'}:
                    # The same idempotency key is reused. Consent is rechecked on submit.
                    row['next_attempt'] = time.time() + 5
                    return save('consented')
                if state not in RECEIPT_STATES or not isinstance(response.get('receipt_id'), str) or not 1 <= len(response['receipt_id']) <= 200:
                    raise FinanceConnectionError('finance_receipt_required')
                if operation == 'submit' and state not in {'received', 'in_consultation', 'closed'}:
                    raise FinanceConnectionError('finance_receipt_invalid_state')
                if prior_state=='deleted' or (prior_state=='withdrawn' and state!='deleted'):
                    return save(prior_state)
                if prior_state == 'withdrawal_requested' or operation == 'withdraw':
                    if state not in {'withdrawn', 'deleted'}:
                        return save('withdrawal_requested')
                if prior_state in {'closed','withdrawn','deleted'} and state not in {'withdrawn','deleted'}:
                    return save(prior_state)
                row['external_delivery'] = True
                row['receipt'] = {'id': response['receipt_id'], 'basis': 'recipient_api', 'at': now()}
                row['next_attempt'] = time.time() + 5
                return save(state)
            except Exception:
                return save('withdrawal_requested' if operation == 'withdraw' or prior_state == 'withdrawal_requested' else 'delivery_unknown' if operation == 'submit' else prior_state)

    @staticmethod
    def _consent(row):
        consent = row.get('consent')
        if not consent or consent['payload_hash'] != digest(row['packet']) or datetime.fromisoformat(consent['expires_at']) <= datetime.now(timezone.utc):
            raise FinanceConnectionError('finance_consent_required')
