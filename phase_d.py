"""Phase D standalone: read nonce/balance/code for candidate wallets. Resumable, hard timeouts.
  python phase_d.py --hours 24
"""
import sys, os, json, time, argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rhlib

ap = argparse.ArgumentParser(); ap.add_argument('--hours', type=int, default=24)
A = ap.parse_args()
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', f'{A.hours}h')
def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)

recv = Counter(); txr = defaultdict(set)
with open(os.path.join(D, 'mints.jsonl')) as f:
    for x in f:
        m = json.loads(x)
        recv[m[3]] += 1 if m[4] == 1155 else m[5]
        txr[m[1]].add(m[3])
log('mints loaded', len(recv))
cand = {a for a, n in recv.items() if n >= 5}
opc = Counter()
with open(os.path.join(D, 'txs.jsonl')) as f:
    for x in f:
        t = json.loads(x)
        fr = t.get('from')
        for r in txr.get(t['h'], ()):
            if r != fr: opc[fr] += 1
cand |= set(opc)
log('after operators', len(cand))
sinkc = defaultdict(set)
op = os.path.join(D, 'outflows.jsonl')
if os.path.exists(op):
    with open(op) as f:
        for x in f:
            o = json.loads(x)
            for r in o['out']: sinkc[r[2]].add(o['w'])
cand |= {s for s, v in sinkc.items() if len(v) >= 2}
cand.discard(None)
st_p = os.path.join(D, 'wallets.jsonl')
have = set()
if os.path.exists(st_p):
    with open(st_p) as f:
        for x in f:
            have.add(json.loads(x)['a'])
need = sorted(cand - have)
log('candidates', len(cand), 'to read', len(need))

import threading
_lock = threading.Lock()
_next = {u: 0.0 for u in rhlib.RPCS}
_gap = {u: 0.25 for u in rhlib.RPCS}  # adaptive per-endpoint spacing

def _paced_post(body, u):
    with _lock:
        now = time.time()
        wait = max(0.0, _next[u] - now)
        _next[u] = max(now, _next[u]) + _gap[u]
    if wait: time.sleep(wait)
    try:
        r = rhlib._post(body, u, timeout=15)
        with _lock: _gap[u] = max(0.12, _gap[u] * 0.97)
        return r
    except Exception as e:
        with _lock: _gap[u] = min(3.0, _gap[u] * 1.6)
        raise

def wq(a, k):
    body = [{'jsonrpc': '2.0', 'id': 0, 'method': 'eth_getTransactionCount', 'params': [a, 'latest']},
            {'jsonrpc': '2.0', 'id': 1, 'method': 'eth_getBalance', 'params': [a, 'latest']},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'eth_getCode', 'params': [a, 'latest']}]
    for att in range(10):
        with _lock:
            u = min(rhlib.RPCS, key=lambda x: _next[x])  # least-backlogged endpoint
        try:
            res = _paced_post(body, u)
            if isinstance(res, list) and len(res) == 3:
                r = {x['id']: x.get('result') for x in res}
                n, b, c = r.get(0), r.get(1), r.get(2)
                if n is None: continue
                return {'a': a, 'nonce': int(n, 16), 'bal': str(int(b, 16)) if b else None,
                        'code': (c or '0x')[:48], 'codelen': (len(c or '0x') - 2) // 2}
        except Exception:
            time.sleep(0.5 + att * 0.5)
    return None

done = miss = 0
with open(st_p, 'a') as f, ThreadPoolExecutor(10) as pool:
    futs = [pool.submit(wq, a, k) for k, a in enumerate(need)]
    for k, fu in enumerate(as_completed(futs)):
        w = fu.result()
        if w: f.write(json.dumps(w) + '\n'); done += 1
        else: miss += 1
        if k % 250 == 0:
            f.flush(); log(f'D {done}/{len(need)} miss {miss} gaps', {u[8:20]: round(g, 2) for u, g in _gap.items()})
open(os.path.join(D, 'D.done'), 'w').write('ok')
log('D DONE', done, 'of', len(need))
