"""
Turn scan.py output into: bot master list (json/csv), clusters, collection stats, dashboard data.

  python analyze.py --hours 24

Heuristics are EVIDENCE SIGNALS, not verdicts. Every flag carries the numbers that produced it.
"""
import argparse, csv, json, os, statistics, sys, time
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rhlib import batch

ap = argparse.ArgumentParser()
ap.add_argument('--hours', type=float, default=24)
args = ap.parse_args()
BASE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(BASE, 'data', f'{int(args.hours)}h')
meta = json.load(open(os.path.join(D, 'meta.json')))
H, START = meta['head'], meta['start']
BLOCK_S = 0.1031
T_HEAD = None

# mints rows: [block, tx, contract, to, std, count, firstId]
mints = [json.loads(x) for x in open(os.path.join(D, 'mints.jsonl'))]
# ERC-1155 'amount' is attacker/creator-controlled and some contracts emit junk (1e18+). Count 1155 as 1 per event.
for m in mints:
    if m[4] == 1155:
        m[5] = 1
txs = {}
for x in open(os.path.join(D, 'txs.jsonl')):
    t = json.loads(x); txs[t['h']] = t
outflows = {}
if os.path.exists(os.path.join(D, 'outflows.jsonl')):
    for x in open(os.path.join(D, 'outflows.jsonl')):
        o = json.loads(x); outflows[o['w']] = o['out']
wstate = {}
if os.path.exists(os.path.join(D, 'wallets.jsonl')):
    for x in open(os.path.join(D, 'wallets.jsonl')):
        w = json.loads(x); wstate[w['a']] = w

KNOWN_ROUTERS = {
    '0x00005ea00ac477b1030ce78506496e8c2de24bf5': 'OpenSea SeaDrop',
}
KNOWN_7702 = {
    '0x63c0c19a282a1b52b07dd5a65b58948a07dae32b': 'MetaMask 7702 delegator',
}

print('loaded', len(mints), len(txs), len(outflows), len(wstate), flush=True)
# ---------------------------------------------------------------- per-tx view
tx_info = {}
for m in mints:
    b, h, c, to, std, n, _ = m
    ti = tx_info.setdefault(h, {'block': b, 'contracts': set(), 'recips': set(), 'tokens': 0})
    ti['contracts'].add(c); ti['recips'].add(to); ti['tokens'] += n

# ---------------------------------------------------------------- per-wallet aggregation
# "operator" = tx sender (who paid gas and pushed the button). "recipient" = who got the NFT.
W = defaultdict(lambda: {'tokens_recv': 0, 'tokens_sent_as_op': 0, 'mint_txs': set(), 'colls': Counter(),
                         'blocks': [], 'recv_for_ops': Counter(), 'ops_for_recips': Counter(),
                         'via': Counter(), 'sels': Counter(), 'fees': Counter(), 'first_nonce': None})
coll = defaultdict(lambda: {'tokens': 0, 'recips': Counter(), 'ops': Counter(), 'txs': set(), 'first': None, 'last': None, 'std': None})
for m in mints:
    b, h, c, to, std, n, _ = m
    t = txs.get(h)
    op = t['from'] if t else None
    W[to]['tokens_recv'] += n
    W[to]['colls'][c] += n
    W[to]['mint_txs'].add(h)
    W[to]['blocks'].append(b)
    C = coll[c]
    C['tokens'] += n; C['recips'][to] += n; C['txs'].add(h); C['std'] = std
    C['first'] = b if C['first'] is None else min(C['first'], b)
    C['last'] = b if C['last'] is None else max(C['last'], b)
    if op:
        C['ops'][op] += n
        if op != to:
            W[to]['recv_for_ops'][op] += n
            W[op]['ops_for_recips'][to] += n
        W[op]['tokens_sent_as_op'] += n
        if op != to:
            W[op]['mint_txs'].add(h)
            W[op]['blocks'].append(b)
            W[op]['colls'][c] += 0
for h, t in txs.items():
    op = t['from']
    ti = tx_info.get(h)
    if not ti:
        continue
    via = 'direct' if t['to'] in ti['contracts'] else t['to']
    W[op]['via'][via] += 1
    W[op]['sels'][t['sel']] += 1
    W[op]['fees'][(t.get('mf'), t.get('mp'))] += 1
    if W[op]['first_nonce'] is None or t['nonce'] < W[op]['first_nonce']:
        W[op]['first_nonce'] = t['nonce']

# ---------------------------------------------------------------- consolidation sinks
# a sink = address receiving minted-collection tokens from >=3 distinct minting wallets inside the window
BURN = {'0x0000000000000000000000000000000000000000', '0x000000000000000000000000000000000000dead'}
sink_srcs = defaultdict(Counter)
swept = Counter()
for w, rows in outflows.items():
    for (b, c, dst, h) in rows:
        if dst in BURN: continue  # burns are not consolidation
        if c in coll:  # only count tokens from collections minted in window
            sink_srcs[dst][w] += 1
            swept[w] += 1
SINKS = {s: srcs for s, srcs in sink_srcs.items() if len(srcs) >= 3}

# fee-fingerprint swarms: identical (maxFee, priority) + same selector + same collection,
# shared by >=5 distinct operators within the window
swarm = defaultdict(set)
for h, t in txs.items():
    ti = tx_info.get(h)
    if not ti:
        continue
    for c in ti['contracts']:
        key = (c, t['sel'], t.get('mf'), t.get('mp'), t.get('gas'))
        swarm[key].add(t['from'])
SWARMS = {k: v for k, v in swarm.items() if len(v) >= 5}
in_swarm = defaultdict(list)
for k, v in SWARMS.items():
    for a in v:
        in_swarm[a].append(len(v))

print('aggregated', len(W), flush=True)
# ---------------------------------------------------------------- score
def cadence(blocks):
    bs = sorted(set(blocks))
    if len(bs) < 10:
        return None
    gaps = [(b2 - b1) * BLOCK_S for b1, b2 in zip(bs, bs[1:])]
    return statistics.median(gaps)

rows = []
for a, w in W.items():
    if a in ('0x0000000000000000000000000000000000000000',):
        continue
    st = wstate.get(a, {})
    tokens = max(w['tokens_recv'], w['tokens_sent_as_op'])
    ncoll = len([c for c, n in w['colls'].items()])
    ntx = len(w['mint_txs'])
    med = cadence(w['blocks'])
    labels, ev, score = [], {}, 0
    if tokens >= 200:
        score += 35; labels.append('HIGH_MINT_COUNT')
    elif tokens >= 50:
        score += 20; labels.append('ACTIVE_MINTER')
    if ncoll >= 25:
        score += 25; labels.append('MINTS_MANY_COLLECTIONS')
    elif ncoll >= 10:
        score += 12; labels.append('SEVERAL_COLLECTIONS')
    if med is not None and med < 20 and ntx >= 30:
        score += 15; labels.append('REGULAR_TIMING')
    if len(w['ops_for_recips']) >= 3:
        score += 30; labels.append('PAID_FOR_OTHER_MINTS')
    if len(w['recv_for_ops']) >= 1 and w['tokens_recv'] >= 5:
        score += 10; labels.append('MINT_PAID_BY_OTHER')
    if swept.get(a, 0) >= 5 and w['tokens_recv'] and swept[a] >= 0.5 * w['tokens_recv']:
        score += 15; labels.append('SENT_ON_AFTER_MINT')
    if a in SINKS:
        score += 40; labels.append('COLLECTS_FROM_MANY_MINTERS')
    if in_swarm.get(a):
        score += 15; labels.append('SAME_GAS_GROUP')
    code = st.get('code') or ''
    if code.startswith('0xef0100'):
        score += 5; labels.append('SMART_WALLET_7702')
    elif st.get('codelen', 0) > 0:
        score += 10; labels.append('MINTED_TO_CONTRACT')
    nonce = st.get('nonce')
    if nonce is not None and nonce <= 15 and tokens >= 5:
        score += 10; labels.append('NEW_WALLET')
    routers = {k: v for k, v in w['via'].items() if k != 'direct'}
    if routers:
        ev['via'] = {KNOWN_ROUTERS.get(k, k): v for k, v in routers.items()}
    if score < 20:
        continue
    ev.update({'tokens': tokens, 'collections': ncoll, 'mint_txs': ntx,
               'median_gap_s': round(med, 1) if med else None,
               'nonce': nonce, 'balance_eth': round(int(st['bal']) / 1e18, 6) if st.get('bal') else None,
               'swept_out': swept.get(a, 0),
               'operated_for': len(w['ops_for_recips']), 'minted_by_others': len(w['recv_for_ops']),
               'sink_sources': len(SINKS.get(a, {})), 'swarm_size': max(in_swarm.get(a, [0])),
               'code': code[:48] if code.startswith('0xef0100') else None,
               'top_collections': [c for c, _ in w['colls'].most_common(5)],
               'example_tx': sorted(w['mint_txs'])[:3]})
    # STRONG_SIGNAL must rest on real farm evidence, not on activity alone.
    # Activity (heavy/high volume, many drops, fresh wallet) describes a HABIT a real
    # collector can have. Only these signals prove someone is minting FOR other people:
    STRUCTURAL = {'PAID_FOR_OTHER_MINTS', 'COLLECTS_FROM_MANY_MINTERS', 'SENT_ON_AFTER_MINT',
                  'SMART_WALLET_7702', 'REGULAR_TIMING'}
    ev['structural_proof'] = bool(STRUCTURAL & set(labels))
    if score >= 70 and ev['structural_proof']:
        tier = 'STRONG_SIGNAL'
    else:
        tier = 'MIXED_SIGNAL' if score >= 40 else 'LOW_SIGNAL'
    rows.append({'address': a, 'score': min(score, 100), 'tier': tier, 'labels': labels, 'evidence': ev})

# cluster ids: sink -> its feeder wallets; operator -> its recipients
cluster = {}
cid = 0
for s, srcs in sorted(SINKS.items(), key=lambda kv: -len(kv[1])):
    cid += 1
    for a in [s, *srcs]:
        cluster.setdefault(a, f'farm-{cid:03d}')
for a, w in W.items():
    if len(w['ops_for_recips']) >= 3:
        cid += 1
        for b in [a, *w['ops_for_recips']]:
            cluster.setdefault(b, f'op-{cid:03d}')
by_addr = {r['address']: r for r in rows}
for a, c in cluster.items():
    if a in by_addr:
        by_addr[a]['cluster'] = c
    else:
        # cluster member not otherwise flagged -> add as LOW_SIGNAL with cluster evidence
        by_addr[a] = {'address': a, 'score': 25, 'tier': 'LOW_SIGNAL', 'labels': ['LINKED_GROUP'],
                      'cluster': c, 'evidence': {'tokens': max(W[a]['tokens_recv'], W[a]['tokens_sent_as_op']),
                                                 'collections': len(W[a]['colls'])}}
rows = sorted(by_addr.values(), key=lambda r: (-r['score'], -r['evidence'].get('tokens', 0)))

# ---------------------------------------------------------------- collection names
top_colls = sorted(coll, key=lambda c: -coll[c]['tokens'])[:300]
print('names...', flush=True)
NC_P = os.path.join(BASE, 'data', 'names_cache.json')
ncache = json.load(open(NC_P)) if os.path.exists(NC_P) else {}
missing = [c for c in top_colls if c not in ncache]
import rhlib
for i in range(0, len(missing), 4):  # public RPC 429s/500s on batches >= ~5
    ch = missing[i:i + 4]
    body = [{'jsonrpc': '2.0', 'id': j, 'method': 'eth_call', 'params': [{'to': c, 'data': '0x06fdde03'}, 'latest']} for j, c in enumerate(ch)]
    res = None
    time.sleep(0.15)
    for attempt in range(6):
        try:
            res = rhlib._post(body, rhlib.RPCS[(i // 4 + attempt) % len(rhlib.RPCS)], timeout=15)
            if isinstance(res, list): break
        except Exception:
            pass
        res = None
        time.sleep(1 + attempt)
    if isinstance(res, list):
        for x in res:
            ncache[ch[x['id']]] = x.get('result')
json.dump(ncache, open(NC_P, 'w'))
names = [ncache.get(c) for c in top_colls]
def dec_str(h):
    try:
        b = bytes.fromhex(h[2:])
        ln = int.from_bytes(b[32:64], 'big')
        return b[64:64 + ln].decode('utf-8', 'replace')
    except Exception:
        return None
flagged = {r['address'] for r in rows if r['tier'] in ('STRONG_SIGNAL', 'MIXED_SIGNAL')}
colls_out = []
for c, nm in zip(top_colls, names):
    C = coll[c]
    total = C['tokens']
    botish = sum(n for a, n in C['recips'].items() if a in flagged) 
    top10 = sum(n for _, n in C['recips'].most_common(10))
    colls_out.append({'contract': c, 'name': dec_str(nm) if nm else None, 'std': C['std'], 'minted': total,
                      'unique_recipients': len(C['recips']), 'unique_operators': len(C['ops']),
                      'flagged_share': round(botish / total, 3) if total else 0,
                      'top10_share': round(top10 / total, 3) if total else 0,
                      'top_minters': [[a, n] for a, n in C['recips'].most_common(8)],
                      'mint_txs': len(C['txs']),
                      'hours_active': round((C['last'] - C['first']) * BLOCK_S / 3600, 2)})

# ---------------------------------------------------------------- summary
all_recips = Counter()
for m in mints:
    all_recips[m[3]] += m[5]
tot = sum(all_recips.values())
flag_tokens = sum(n for a, n in all_recips.items() if a in flagged)
summary = {
    'window_hours': args.hours, 'head_block': H, 'start_block': START, 'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
    'nft_tokens_minted': tot, 'mint_txs': len(tx_info), 'unique_recipients': len(all_recips),
    'unique_operators': len({t['from'] for t in txs.values()}), 'collections_minting': len(coll),
    'flagged_wallets': {t: sum(1 for r in rows if r['tier'] == t) for t in ('STRONG_SIGNAL', 'MIXED_SIGNAL', 'LOW_SIGNAL')},
    'tokens_to_confirmed_or_likely': flag_tokens, 'share_to_confirmed_or_likely': round(flag_tokens / tot, 3) if tot else 0,
    'top1pct_wallet_share': round(sum(n for _, n in all_recips.most_common(max(1, len(all_recips) // 100))) / tot, 3) if tot else 0,
    'farm_sinks': len(SINKS), 'fee_swarms': len(SWARMS),
    'eip7702_wallets_flagged': sum(1 for r in rows if 'SMART_WALLET_7702' in r['labels']),
    'routers': Counter(KNOWN_ROUTERS.get(t['to'], 'other') for h, t in txs.items() if h in tx_info and t['to'] not in tx_info[h]['contracts']).most_common(10),
    'wallets_with_wallet_state': len(wstate),
}
farms = []
for s, srcs in sorted(SINKS.items(), key=lambda kv: -sum(kv[1].values()))[:200]:
    farms.append({'sink': s, 'feeder_wallets': len(srcs), 'tokens_received': sum(srcs.values()),
                  'feeders': [[a, n] for a, n in srcs.most_common(50)],
                  'sink_code': (wstate.get(s, {}).get('code') or '')[:12], 'sink_nonce': wstate.get(s, {}).get('nonce')})
swarms = [{'contract': k[0], 'selector': k[1], 'maxFee': k[2], 'priority': k[3], 'gas': k[4], 'operators': len(v),
           'members': sorted(v)[:60]} for k, v in sorted(SWARMS.items(), key=lambda kv: -len(kv[1]))[:150]]

out = {'summary': summary, 'wallets': rows, 'collections': colls_out, 'farms': farms, 'swarms': swarms}
json.dump(out, open(os.path.join(D, 'report.json'), 'w'))
with open(os.path.join(D, 'bots.csv'), 'w', newline='') as f:
    wr = csv.writer(f)
    wr.writerow(['address', 'tier', 'score', 'labels', 'cluster', 'tokens', 'collections', 'mint_txs', 'nonce', 'swept_out', 'example_tx'])
    for r in rows:
        e = r['evidence']
        wr.writerow([r['address'], r['tier'], r['score'], '|'.join(r['labels']), r.get('cluster', ''), e.get('tokens'),
                     e.get('collections'), e.get('mint_txs'), e.get('nonce'), e.get('swept_out'), ' '.join(e.get('example_tx') or [])])
print(json.dumps(summary, indent=1))
print('top wallets:')
for r in rows[:15]:
    print(r['address'], r['tier'], r['score'], r['labels'], r['evidence'].get('tokens'), r['evidence'].get('collections'))
print('farms', len(farms), 'swarms', len(swarms))
