"""Offline compatibility repair for older shallow-merge clients.

Default is a read-only preview. --apply --offline-confirmed writes only a fully
inherited per-exchange profitability dictionary, preserving explicit overrides.
No KPI threshold, strict/limited choice, order authority or ledger is reset.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trading.advanced_layer_config import deep_merge_policy, policy_changes
from trading.exchanges.venue_capabilities import CRYPTO_VENUES


def repair_plan(settings, venue):
    if venue not in CRYPTO_VENUES or not isinstance(settings,dict):
        raise ValueError('invalid_settings_or_venue')
    root=settings.get('advanced_trading_layers') or {}
    overrides=root.get('exchange_overrides') or {}
    exchange=overrides.get(venue) or {}
    global_policy=root.get('profitability_validation') or {}
    if 'profitability_validation' not in exchange:
        return settings,[]  # No shallow replacement, so no repair needed.
    override=exchange['profitability_validation']
    if not isinstance(global_policy,dict) or not isinstance(override,dict):
        raise ValueError('invalid_policy_shape')
    effective=deep_merge_policy(global_policy,override)
    changes=policy_changes(override,effective)
    updated=deep_merge_policy(settings,{'advanced_trading_layers':{'exchange_overrides':{venue:{'profitability_validation':effective}}}})
    return updated,changes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings',required=True)
    parser.add_argument('--exchange',required=True,choices=sorted(CRYPTO_VENUES))
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--offline-confirmed',action='store_true',help='Confirm the trading app is fully closed before replacing its settings file.')
    args=parser.parse_args()
    path=Path(args.settings).expanduser().resolve()
    try:
        original=path.read_bytes()
        if len(original)>10*1024*1024:raise ValueError('settings_size_limit')
        updated,changes=repair_plan(json.loads(original),args.exchange)
        # Report keys only: unknown policy fields may contain private data.
        report={'exchange':args.exchange,'changed_fields':[c['path'] for c in changes], 'applied':False,
                'policy_choice_changed':False,'orders_submitted':False,'ledger_changed':False}
        if args.apply:
            if not args.offline_confirmed:raise ValueError('close_app_and_confirm_offline_first')
            if changes:
                encoded=json.dumps(updated,ensure_ascii=False,indent=2,allow_nan=False).encode()
                suffix=secrets.token_hex(8)
                backup=path.with_name(path.name+'.before-profitability-'+suffix+'.bak')
                temp=path.with_name(path.name+'.profitability-'+suffix+'.tmp')
                try:
                    with os.fdopen(os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as stream:
                        stream.write(original);stream.flush();os.fsync(stream.fileno())
                    with os.fdopen(os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as stream:
                        stream.write(encoded);stream.flush();os.fsync(stream.fileno())
                    if hashlib.sha256(path.read_bytes()).digest()!=hashlib.sha256(original).digest():
                        raise ValueError('settings_changed_retry_offline')
                    os.replace(temp,path)
                finally:temp.unlink(missing_ok=True)
                report.update(applied=True,backup_file=backup.name)
        print(json.dumps(report,ensure_ascii=False,indent=2))
    except (OSError,ValueError,TypeError,AttributeError):
        parser.exit(2,'Settings could not be safely processed. Check file format, close the app, and preview again. No credential values are printed.\n')

if __name__=='__main__':main()
