"""Classify every participant in a mint window by role, from the raw scan data.

Answers "who is actually minting" instead of lumping everyone into "flagged".
Roles (a wallet gets the strongest role that fits):

  PAID_BUYER      paid ETH for its own mints (value > 0) and kept them  -> a real buyer
  SELF_MINTER     minted for itself, kept them                          -> a real person
  DISTRIBUTOR     paid gas for mints sent to 3+ other wallets, and those wallets KEPT them
                  (a gift, an airdrop, a community drop - a person, not a farm)
  FARM_OPERATOR   paid for mints to 3+ other wallets AND swept their own out -> a farm
  COLLECTS_FROM_MANY_MINTERS  received swept NFTs from 2+ different minting wallets     -> a farm collector

  python participants.py            # writes report.json -> participants, per window
  python build_dashboard.py         # then rebuilds the dashboard
"""
import json, glob, os
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
ZERO = '0x0000000000000000000000000000000000000000'
DEAD = '0x000000000000000000000000000000000000dead'
ROLES = ['PAID_BUYER', 'SELF_MINTER', 'DISTRIBUTOR', 'FARM_OPERATOR', 'COLLECTS_FROM_MANY_MINTERS']


def classify(D, owners=frozenset()):
    mints = [json.loads(x) for x in open(os.path.join(D, 'mints.jsonl'))]
    txs = [json.loads(x) for x in open(os.path.join(D, 'txs.jsonl'))]
    txv = {t['h']: (int(t['val'], 16) if t.get('val') else 0) for t in txs}
    txfrom = {t['h']: t['from'] for t in txs}
    recv, paid_by, op_for = Counter(), Counter(), defaultdict(set)
    paid_eth = Counter(); colls = defaultdict(set)
    for r in mints:
        _, txh, c, to, std, amt = r[0], r[1], r[2], r[3], r[4], r[5]
        n = 1 if std == 1155 else amt
        recv[to] += n; colls[to].add(c)
        if txv.get(txh, 0) > 0:
            paid_by[to] += n
            paid_eth[to] += txv[txh]
        f = txfrom.get(txh)
        if f and f != to:
            op_for[f].add(to)
    op = os.path.join(D, 'outflows.jsonl')
    sinkc, sent_out = defaultdict(set), Counter()
    if os.path.exists(op):
        for o in (json.loads(x) for x in open(op)):
            n = 0
            for it in o['out']:
                if it[2] not in (ZERO, DEAD):
                    n += 1; sinkc[it[2]].add(o['w'])
            sent_out[o['w']] = n
    sinks = {s for s, v in sinkc.items() if len(v) >= 2}
    counts, tokens, ex = Counter(), Counter(), {}
    for w, n in recv.items():
        if w in sinks:
            role = 'COLLECTS_FROM_MANY_MINTERS'
        elif w in owners and len(op_for.get(w, ())) >= 3:
            role = 'DISTRIBUTOR'       # collection owner airdropping its own collection
        elif len(op_for.get(w, ())) >= 3 and sent_out.get(w, 0) >= 5:
            role = 'FARM_OPERATOR'
        elif len(op_for.get(w, ())) >= 3:
            role = 'DISTRIBUTOR'
        elif paid_by.get(w, 0) > 0:
            role = 'PAID_BUYER'
        else:
            role = 'SELF_MINTER'
        counts[role] += 1; tokens[role] += n
        if role in ('FARM_OPERATOR', 'COLLECTS_FROM_MANY_MINTERS') and len(ex.get(role, [])) < 12:
            ex.setdefault(role, []).append(w)
    total = sum(tokens.values()) or 1
    facts = {
        'total_wallets_that_received': len(recv),
        'total_nfts': total,
        'paid_mints': sum(paid_by.values()),
        'roles': {r: {'wallets': counts[r], 'nfts': tokens[r],
                      'wallets_share': round(counts[r] / max(1, len(recv)), 4),
                      'nfts_share': round(tokens[r] / total, 4)} for r in ROLES},
        'farm_examples': ex,
        # the good news, kept without any accusation: real buyers and top holders
        'top_buyers': [{'wallet': w, 'nfts': recv[w], 'paid_eth': round(paid_eth[w] / 1e18, 4),
                        'collections': len(colls[w])} for w, _ in paid_eth.most_common(25)],
        'top_holders': [{'wallet': w, 'nfts': n, 'collections': len(colls[w])}
                        for w, n in recv.most_common(25)],
    }
    return facts


for p in sorted(glob.glob(os.path.join(BASE, 'data', '*', 'report.json'))):
    R = json.load(open(p))
    D = os.path.dirname(p)
    if not os.path.exists(os.path.join(D, 'mints.jsonl')):
        print('skip (no raw data):', D); continue
    owners = {x['address'] for x in R['wallets'] if 'COLLECTION_OWNER' in x['labels']}
    R['participants'] = classify(D, owners)
    json.dump(R, open(p, 'w'))
    f = R['participants']['roles']
    print(os.path.basename(D), '->', {r: f'{f[r]["nfts_share"]*100:.1f}% NFTs' for r in ROLES})
print('now run: python build_dashboard.py')
