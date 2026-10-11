"""Collection owners are not farms.

A creator who pays the gas to airdrop their OWN collection to their holders looks, on chain,
exactly like "one wallet paying for mints sent to many other wallets". Before this step those
creators were scored PAID_FOR_OTHER_MINTS (structural proof) and could land in STRONG_SIGNAL, and
every holder who received their airdrop picked up MINT_PAID_BY_OTHER / LINKED_GROUP.

This step runs after analyze.py and fixes that, without rescanning:
  1. For each wallet labelled PAID_FOR_OTHER_MINTS, find the collections it paid mints for.
  2. Read owner() on those collections (cached in data/owners_cache.json).
  3. If the wallet owns the collections behind most of those mints, it is the creator:
       - PAID_FOR_OTHER_MINTS and REGULAR_TIMING are removed (an airdrop script is regular by design)
       - label COLLECTION_OWNER is added, score drops by those weights, tier is capped at MIXED_SIGNAL
  4. Wallets that were only linked to that creator (its airdrop recipients) lose LINKED_GROUP /
     MINT_PAID_BY_OTHER, and are dropped from the list if nothing else is left.

  python owners.py            # all windows in data/
  python owners.py --offline  # cache only, no RPC calls
"""
import json, os, glob, sys
from collections import defaultdict, Counter

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE_P = os.path.join(BASE, 'data', 'owners_cache.json')
STRUCTURAL = {'PAID_FOR_OTHER_MINTS', 'COLLECTS_FROM_MANY_MINTERS', 'SENT_ON_AFTER_MINT',
              'SMART_WALLET_7702', 'REGULAR_TIMING'}
WEIGHT = {'PAID_FOR_OTHER_MINTS': 30, 'REGULAR_TIMING': 15, 'MINT_PAID_BY_OTHER': 10}
OWNER_SHARE = 0.5          # creator if it owns the collections behind >= half of the mints it paid for others
OFFLINE = '--offline' in sys.argv


def load_cache():
    if os.path.exists(CACHE_P):
        c = json.load(open(CACHE_P))
        return {('0x' + k if not k.startswith('0x') else k).lower(): ('0x' + v if not v.startswith('0x') else v).lower()
                for k, v in c.items()}
    return {}


def fetch_owners(cols, cache):
    """owner() for collections not in the cache. Unknown stays unknown (never guessed)."""
    todo = [c for c in cols if c not in cache]
    if not todo or OFFLINE:
        return
    try:
        sys.path.insert(0, BASE)
        import rhlib
        res = rhlib.batch([('eth_call', [{'to': c, 'data': '0x8da5cb5b'}, 'latest']) for c in todo], size=4)
    except Exception as e:  # no RPC here: keep going with what the cache knows
        print('owner() lookups skipped:', e)
        return
    for c, r in zip(todo, res):
        if isinstance(r, str) and len(r) == 66:
            cache[c] = '0x' + r[-40:]
        elif r is not None:
            cache[c] = ''          # no owner() on this contract


def tier_of(score, labels, cap_mixed=False):
    structural = bool(STRUCTURAL & set(labels))
    if score >= 70 and structural and not cap_mixed:
        return 'STRONG_SIGNAL'
    return 'MIXED_SIGNAL' if score >= 40 else 'LOW_SIGNAL'


def paid_for_others(D, wallets):
    """wallet -> Counter(collection -> mints it paid for that went to OTHER wallets), plus recipient -> payers."""
    op_cols, payers = defaultdict(Counter), defaultdict(set)
    mp, tp = os.path.join(D, 'mints.jsonl'), os.path.join(D, 'txs.jsonl')
    if not (os.path.exists(mp) and os.path.exists(tp)):
        return None, None
    txfrom = {}
    for line in open(tp):
        t = json.loads(line)
        txfrom[t['h']] = t['from']
    for line in open(mp):
        r = json.loads(line)
        f = txfrom.get(r[1])
        if f and f != r[3]:
            payers[r[3]].add(f)
            if f in wallets:
                op_cols[f][r[2]] += 1
    return op_cols, payers


def process(p, cache):
    R = json.load(open(p))
    D = os.path.dirname(p)
    rows = R['wallets']
    by = {r['address']: r for r in rows}
    pfo = {r['address'] for r in rows if 'PAID_FOR_OTHER_MINTS' in r['labels']}
    op_cols, payers = paid_for_others(D, pfo)
    if op_cols is None:  # no raw data (e.g. a published report): fall back to the top collections
        op_cols = {a: Counter({c: 1 for c in (by[a]['evidence'].get('top_collections') or [])}) for a in pfo}
    fetch_owners({c for cs in op_cols.values() for c in cs}, cache)

    creators = {}
    for a in pfo:
        cs = op_cols.get(a) or Counter()
        total = sum(cs.values())
        owned = [c for c in cs if cache.get(c) == a]
        if total and sum(cs[c] for c in owned) / total >= OWNER_SHARE:
            creators[a] = owned

    moved = Counter()
    for a, owned in creators.items():
        r = by[a]
        old = r['tier']
        for l in ('PAID_FOR_OTHER_MINTS', 'REGULAR_TIMING'):
            if l in r['labels']:
                r['labels'].remove(l); r['score'] -= WEIGHT[l]
        r['labels'].append('COLLECTION_OWNER')
        r['score'] = max(0, r['score'])
        r['tier'] = tier_of(r['score'], r['labels'], cap_mixed=True)
        ev = r.setdefault('evidence', {})
        ev['owner_of'] = owned[:10]
        ev['structural_proof'] = bool(STRUCTURAL & set(r['labels']))
        ev['note'] = ('Pays for mints sent to other wallets, but owns the collection: '
                      'a creator airdrop / distribution, not a farm.')
        moved[f'{old}->{r["tier"]}'] += 1

    # the creators' airdrop recipients
    creator_clusters = {by[a].get('cluster') for a in creators if (by[a].get('cluster') or '').startswith('op-')}
    drop = set()
    for r in rows:
        a = r['address']
        if a in creators:
            if r.get('cluster') in creator_clusters:
                r['cluster'] = None
            continue
        changed = False
        if r.get('cluster') in creator_clusters:
            r['cluster'] = None
            if 'LINKED_GROUP' in r['labels']:
                r['labels'].remove('LINKED_GROUP'); changed = True
                if r['score'] == 25 and not r['labels']:
                    r['score'] = 0
        if 'MINT_PAID_BY_OTHER' in r['labels'] and payers is not None:
            ps = payers.get(a) or set()
            if ps and ps <= set(creators):
                r['labels'].remove('MINT_PAID_BY_OTHER'); r['score'] -= WEIGHT['MINT_PAID_BY_OTHER']; changed = True
        if changed:
            if not r['labels'] or r['score'] < 20:
                drop.add(a); moved['dropped (creator airdrop recipient)'] += 1
            else:
                old = r['tier']
                r['tier'] = tier_of(r['score'], r['labels'])
                if old != r['tier']:
                    moved[f'{old}->{r["tier"]} (recipient)'] += 1
    R['wallets'] = sorted((r for r in rows if r['address'] not in drop),
                          key=lambda r: (-r['score'], -((r.get('evidence') or {}).get('tokens') or 0)))
    s = R['summary']
    s['flagged_wallets'] = {t: sum(1 for r in R['wallets'] if r['tier'] == t)
                            for t in ('STRONG_SIGNAL', 'MIXED_SIGNAL', 'LOW_SIGNAL')}
    s['collection_owners_cleared'] = sum(1 for r in R['wallets'] if 'COLLECTION_OWNER' in r['labels'])  # idempotent on re-runs
    # recompute the "share of mints to flagged wallets" headline from raw data when we have it
    mp = os.path.join(D, 'mints.jsonl')
    if os.path.exists(mp):
        flagged = {r['address'] for r in R['wallets'] if r['tier'] in ('STRONG_SIGNAL', 'MIXED_SIGNAL')}
        tot = fl = 0
        per_coll = defaultdict(lambda: [0, 0])
        for line in open(mp):
            m = json.loads(line)
            n = 1 if m[4] == 1155 else m[5]
            tot += n; per_coll[m[2]][0] += n
            if m[3] in flagged:
                fl += n; per_coll[m[2]][1] += n
        if tot:
            s['tokens_to_confirmed_or_likely'] = fl
            s['share_to_confirmed_or_likely'] = round(fl / tot, 3)
            for c in R.get('collections', []):
                t, f = per_coll.get(c['contract'], (0, 0))
                if t:
                    c['flagged_share'] = round(f / t, 3)
    json.dump(R, open(p, 'w'))
    return len(creators), dict(moved), s['flagged_wallets']


if __name__ == '__main__':
    cache = load_cache()
    for p in sorted(glob.glob(os.path.join(BASE, 'data', '*', 'report.json'))):
        n, moved, fw = process(p, cache)
        print(os.path.basename(os.path.dirname(p)), f'collection owners cleared: {n}', moved, fw)
    json.dump({k: v for k, v in sorted(cache.items())}, open(CACHE_P, 'w'), indent=0)
