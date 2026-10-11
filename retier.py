"""Re-tier an existing report.json without rescanning.

CONFIRMED_PATTERN requires real farm evidence (a structural signal), not activity alone.
Run after changing the tier rule in analyze.py, then: python build_dashboard.py

  python retier.py
"""
import json, os, glob
BASE = os.path.dirname(os.path.abspath(__file__))
STRUCTURAL = {'OPERATOR_FOR_OTHER_WALLETS', 'FARM_SINK', 'MINT_AND_SWEEP',
              'EIP7702_DELEGATED', 'MACHINE_CADENCE'}
STRONG_ONLY = 'a real collector can hit this on activity alone'
for p in glob.glob(os.path.join(BASE, 'data', '*', 'report.json')):
    R = json.load(open(p))
    moved = 0
    for x in R['wallets']:
        ev = x.setdefault('evidence', {})
        ev['structural_proof'] = bool(STRUCTURAL & set(x['labels']))
        old = x['tier']
        if x['score'] >= 70 and ev['structural_proof']:
            x['tier'] = 'CONFIRMED_PATTERN'
        else:
            x['tier'] = 'LIKELY' if x['score'] >= 40 else 'WATCH'
        if old != x['tier']:
            moved += 1
        if old == 'CONFIRMED_PATTERN' and x['tier'] != 'CONFIRMED_PATTERN':
            ev['note'] = 'was CONFIRMED on activity alone; ' + STRONG_ONLY
    s = R['summary']
    for t in ('CONFIRMED_PATTERN', 'LIKELY', 'WATCH'):
        s['flagged_wallets'][t] = sum(1 for x in R['wallets'] if x['tier'] == t)
    conf = [x for x in R['wallets'] if x['tier'] == 'CONFIRMED_PATTERN']
    total = s.get('nft_tokens_minted') or 1
    # share is recomputed in analyze.py from mints; keep the report's own count of flagged mints
    print(os.path.basename(os.path.dirname(p)), 'retiered', moved, dict(s['flagged_wallets']))
    json.dump(R, open(p, 'w'))
