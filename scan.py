"""
RH Chain (4663) mint-bot scanner. Read-only, resumable.

  python scan.py --hours 24          # last 24h
  python scan.py --hours 168         # last 7 days

Phases (each cached under data/<window>/):
  A  mint logs     ERC-721 Transfer(from=0) + ERC-1155 TransferSingle/Batch(from=0)
  B  mint txs      eth_getTransactionByHash for each unique mint tx (from, to, selector, gas)
  C  outflows      Transfer logs OUT of the top minting wallets (consolidation sinks)
  D  wallet state  nonce + balance + code for every minter/recipient flagged
Then analyze.py turns it into the master list + dashboard data.
"""
import sys, argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rhlib import rpc, batch, head, logs, TRANSFER, ZERO_T, pad, unpad

TS1155 = '0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62'
TB1155 = '0x4a39dc06d4c0dbc64b70af90fd698a233a518aa5d07e595d983b8c0526c8f7fb'

ap = argparse.ArgumentParser()
ap.add_argument('--hours', type=float, default=24)
ap.add_argument('--head', type=int, default=0)
ap.add_argument('--top-wallets', type=int, default=1500)
ap.add_argument('--per-wallet', type=int, default=3)
args = ap.parse_args()

BLOCK_S = 0.1031
H = args.head or head()
span = int(args.hours * 3600 / BLOCK_S)
START = H - span
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', f'{int(args.hours)}h')
os.makedirs(OUT, exist_ok=True)
meta_p = os.path.join(OUT, 'meta.json')
if os.path.exists(meta_p):
    meta = json.load(open(meta_p))
    H, START = meta['head'], meta['start']
else:
    meta = {'head': H, 'start': START, 'hours': args.hours, 'created': time.time()}
    json.dump(meta, open(meta_p, 'w'))
print(f'window {START}..{H} ({H-START} blocks, {args.hours}h)', flush=True)


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


# ---------------- Phase A: mint logs, chunked files ----------------
CH = 50000
mints_p = os.path.join(OUT, 'mints.jsonl')
doneA = os.path.join(OUT, 'A.done')
if not os.path.exists(doneA):
    partdir = os.path.join(OUT, 'A_parts'); os.makedirs(partdir, exist_ok=True)
    fr = START
    while fr <= H:
        to = min(fr + CH - 1, H)
        pp = os.path.join(partdir, f'{fr}.jsonl')
        if not os.path.exists(pp):
            rows = []
            for l in logs({'topics': [TRANSFER, ZERO_T]}, fr, to, step=6000):
                if len(l['topics']) != 4:
                    continue  # ERC-20 mint, skip
                rows.append([int(l['blockNumber'], 16), l['transactionHash'], int(l['logIndex'], 16),
                             l['address'].lower(), unpad(l['topics'][2]), str(int(l['topics'][3], 16)), 721, 1])
            for topic in (TS1155, TB1155):
                for l in logs({'topics': [topic, None, ZERO_T]}, fr, to, step=29000):
                    d = l['data'][2:]
                    amt = 1
                    if topic == TS1155 and len(d) >= 128:
                        amt = int(d[64:128], 16)
                    rows.append([int(l['blockNumber'], 16), l['transactionHash'], int(l['logIndex'], 16),
                                 l['address'].lower(), unpad(l['topics'][3]), '1155', 1155, amt])
            # aggregate per (tx, contract, recipient): [block, tx, contract, to, std, count, firstId]
            agg = {}
            for r in rows:
                k = (r[1], r[3], r[4])
                if k in agg:
                    agg[k][5] += r[7]
                else:
                    agg[k] = [r[0], r[1], r[3], r[4], r[6], r[7], r[5]]
            with open(pp + '.tmp', 'w') as f:
                for r in agg.values():
                    f.write(json.dumps(r) + '\n')
            os.replace(pp + '.tmp', pp)
            log(f'A {fr}-{to} mints={len(rows)}  {100*(to-START)/(H-START):.1f}%')
        fr = to + 1
    with open(mints_p, 'w') as f:
        for name in sorted(os.listdir(partdir), key=lambda n: int(n.split('.')[0])):
            if name.endswith('.jsonl'):
                f.write(open(os.path.join(partdir, name)).read())
    open(doneA, 'w').write('ok')
mints = [json.loads(x) for x in open(mints_p)]
log(f'A done: {len(mints)} mint rows, {sum(m[5] for m in mints)} tokens')

# ---------------- Phase B: tx details (prioritised, threaded, both RPCs) ----------------
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
import rhlib
for m in mints:
    if m[4] == 1155:
        m[5] = 1
recv = Counter()
txr = defaultdict(set)
for m in mints:
    recv[m[3]] += m[5]; txr[m[1]].add(m[3])
rank = {a: i for i, (a, _) in enumerate(recv.most_common())}
txs_p = os.path.join(OUT, 'txs.jsonl')
have = set()
if os.path.exists(txs_p):
    for x in open(txs_p):
        try: have.add(json.loads(x)['h'])
        except Exception: pass
# Sampling: every multi-recipient tx + up to --per-wallet txs (spread over the window) for each wallet
# that received >= 5 tokens. Public RPC is ~900 tx/min, so a full fetch of 100k+ txs is not practical.
by_w = defaultdict(list)
for m in mints:
    by_w[m[3]].append(m[1])
pick = {h for h, rs in txr.items() if len(rs) > 1}
for a, n in recv.items():
    if n < 5:
        continue
    lst = sorted(set(by_w[a]))
    k = args.per_wallet
    if len(lst) <= k:
        pick.update(lst)
    else:
        step = len(lst) / k
        pick.update(lst[int(i * step)] for i in range(k))
need = [h for h in pick if h not in have]
need.sort(key=lambda h: (0 if len(txr[h]) > 1 else 1, min(rank[a] for a in txr[h])))
log(f'B: {len(have)} cached, {len(need)} to fetch (heaviest wallets first)')
lock = threading.Lock()
fB = open(txs_p, 'a')
def fetch(chunk, k):
    order = rhlib.RPCS if k % 2 == 0 else rhlib.RPCS[::-1]
    body = [{'jsonrpc': '2.0', 'id': j, 'method': 'eth_getTransactionByHash', 'params': [h]} for j, h in enumerate(chunk)]
    delay = 1.5
    for attempt in range(12):
        u = order[attempt % 2]
        try:
            res = rhlib._post(body, u, timeout=40)
            if isinstance(res, list):
                break
        except Exception:
            pass
        time.sleep(delay); delay = min(delay * 1.5, 20)
    else:
        return 0
    n = 0
    with lock:
        for x in res:
            t = x.get('result')
            if not t: continue
            h = chunk[x['id']]
            fB.write(json.dumps({'h': h, 'from': t['from'].lower(), 'to': (t.get('to') or '').lower(),
                                 'sel': t['input'][:10], 'inlen': (len(t['input']) - 2) // 2,
                                 'val': t.get('value', '0x0'), 'gas': t.get('gas'),
                                 'mf': t.get('maxFeePerGas') or t.get('gasPrice'),
                                 'mp': t.get('maxPriorityFeePerGas'), 'nonce': int(t['nonce'], 16),
                                 'type': t.get('type')}) + '\n'); n += 1
        fB.flush()
    return n
chunks = [need[i:i + 10] for i in range(0, len(need), 10)]
done = 0
with ThreadPoolExecutor(6) as pool:
    futs = [pool.submit(fetch, c, k) for k, c in enumerate(chunks)]
    for k, f in enumerate(as_completed(futs)):
        done += f.result()
        if k % 300 == 0:
            log(f'B {done}/{len(need)}')
fB.close()
log(f'B done ({done} fetched this run)')
open(os.path.join(OUT, 'B.done'), 'w').write('ok')

# ---------------- Phase C: outflows of top recipients (100 wallets OR'd per query) ----------------
top = [a for a, n in recv.most_common(args.top_wallets) if n >= 5]
out_p = os.path.join(OUT, 'outflows.jsonl')
doneC = set()
if os.path.exists(out_p):
    for x in open(out_p): doneC.add(json.loads(x)['w'])
todo = [w for w in top if w not in doneC]
log(f'C: outflows for {len(todo)} wallets')
groups = [todo[i:i + 40] for i in range(0, len(todo), 40)]
def _outlogs(g):
    try:
        return logs({'topics': [TRANSFER, [pad(w) for w in g]]}, START, H, step=9000)
    except RuntimeError:
        if len(g) == 1:
            log(f'C skip {g[0]} (logs keep failing)'); return []
        h = len(g) // 2
        return _outlogs(g[:h]) + _outlogs(g[h:])
def outq(g):
    res = defaultdict(list)
    for l in _outlogs(g):
        if len(l['topics']) != 4: continue
        res[unpad(l['topics'][1])].append([int(l['blockNumber'], 16), l['address'].lower(), unpad(l['topics'][2]), l['transactionHash']])
    return g, res
with open(out_p, 'a') as f, ThreadPoolExecutor(2) as pool:
    for k, (g, res) in enumerate(pool.map(outq, groups)):
        for w in g:
            f.write(json.dumps({'w': w, 'out': res.get(w, [])}) + '\n')
        f.flush()
        log(f'C group {k+1}/{len(groups)}')
open(os.path.join(OUT, 'C.done'), 'w').write('ok')

if os.environ.get('SKIP_D'):
    log('stopping before D (run phase_d.py)'); sys.exit(0)
# ---------------- Phase D: wallet state for candidates ----------------
txs = {}
for x in open(txs_p):
    t = json.loads(x); txs[t['h']] = t
cand = {a for a, n in recv.items() if n >= 5}
opc = Counter()
for h, t in txs.items():
    for r in txr.get(h, ()):
        if r != t['from']: opc[t['from']] += 1
cand |= set(opc)
sinkc = defaultdict(set)
for x in open(out_p):
    o = json.loads(x)
    for r in o['out']: sinkc[r[2]].add(o['w'])
cand |= {s for s, v in sinkc.items() if len(v) >= 2}
st_p = os.path.join(OUT, 'wallets.jsonl')
haveD = set()
if os.path.exists(st_p):
    for x in open(st_p): haveD.add(json.loads(x)['a'])
needD = sorted(cand - haveD)
log(f'D: {len(needD)} wallets to read')
def wq(ch, k):
    order = rhlib.RPCS if k % 2 == 0 else rhlib.RPCS[::-1]
    body = []
    for j, a in enumerate(ch):
        body += [{'jsonrpc': '2.0', 'id': 3*j, 'method': 'eth_getTransactionCount', 'params': [a, 'latest']},
                 {'jsonrpc': '2.0', 'id': 3*j+1, 'method': 'eth_getBalance', 'params': [a, 'latest']},
                 {'jsonrpc': '2.0', 'id': 3*j+2, 'method': 'eth_getCode', 'params': [a, 'latest']}]
    delay = 1.5
    for attempt in range(12):
        try:
            res = rhlib._post(body, order[attempt % 2], timeout=40)
            if isinstance(res, list): break
        except Exception: pass
        time.sleep(delay); delay = min(delay * 1.5, 20)
    else:
        return []
    r = {x['id']: x.get('result') for x in res}
    out = []
    for j, a in enumerate(ch):
        n, b, c = r.get(3*j), r.get(3*j+1), r.get(3*j+2)
        if n is None: continue
        out.append({'a': a, 'nonce': int(n, 16), 'bal': str(int(b, 16)) if b else None,
                    'code': (c or '0x')[:48], 'codelen': (len(c or '0x') - 2) // 2})
    return out
with open(st_p, 'a') as f, ThreadPoolExecutor(10) as pool:
    chs = [needD[i:i + 8] for i in range(0, len(needD), 8)]
    for k, res in enumerate(pool.map(lambda kc: wq(kc[1], kc[0]), enumerate(chs))):
        for w in res: f.write(json.dumps(w) + '\n')
        if k % 200 == 0:
            f.flush(); log(f'D {k*8}/{len(needD)}')
open(os.path.join(OUT, 'D.done'), 'w').write('ok')
log('ALL PHASES DONE')
