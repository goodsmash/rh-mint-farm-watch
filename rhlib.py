"""Shared Robinhood Chain (4663) RPC helpers. Read-only. No keys anywhere.

RPC configuration (first match wins):
  1. env  RH_RPCS="https://a,https://b"      (rhwatch --rpc sets this)
  2. file rhwatch.config.json  {"rpcs": [...], "logs_rpc": "...", "logs_gap": 0.35}
  3. built-in public defaults below
eth_getLogs goes to LOGS_RPC (env RH_LOGS_RPC / config "logs_rpc"), default = first RPC.
Free-tier providers often reject wide getLogs ranges; point RH_LOGS_RPC at one that doesn't.
"""
import json, os, time, urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')
CHAIN_ID = 4663
DEFAULT_RPCS = ['https://rpc.mainnet.chain.robinhood.com', 'https://robinhood.drpc.org']
EXPLORER = os.environ.get('RH_EXPLORER', 'https://robin.etherscan.io')


def _load_config():
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.environ.get('RH_CONFIG', ''), os.path.join(os.getcwd(), 'rhwatch.config.json'),
              os.path.join(here, 'rhwatch.config.json')):
        if p and os.path.isfile(p):
            with open(p) as f:
                return json.load(f)
    return {}


_CFG = _load_config()
_env = [u.strip() for u in os.environ.get('RH_RPCS', '').split(',') if u.strip()]
RPCS = _env or list(_CFG.get('rpcs') or DEFAULT_RPCS)
LOGS_RPC = os.environ.get('RH_LOGS_RPC') or _CFG.get('logs_rpc') or RPCS[0]
LOGS_GAP = float(os.environ.get('RH_LOGS_GAP') or _CFG.get('logs_gap') or 0.35)  # seconds between getLogs calls
TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
ZERO_T = '0x' + '0' * 64


def pad(a):
    return '0x' + '0' * 24 + a[2:].lower()


def unpad(t):
    return '0x' + t[-40:]


def _post(body, url, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={'content-type': 'application/json', 'user-agent': UA})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def rpc(method, params, tries=8):
    delay, last = 2.0, None
    for _ in range(tries):
        for u in RPCS:
            try:
                r = _post({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}, u)
                err = r.get('error')
                if err and ('rate' in str(err).lower() or 'too many' in str(err).lower()):
                    raise RuntimeError(err)
                return r
            except Exception as e:  # transport / 429 -> try next endpoint
                last = e
                if '400' in str(e) and u == RPCS[-1]:
                    raise RuntimeError(f'{method} bad request (400): {e}')  # deterministic, don't burn retries
        time.sleep(delay)
        delay *= 1.5
    raise RuntimeError(f'{method} failed after retries: {last}')


def batch(calls, size=50, tries=3):
    """calls = [(method, params)]. Returns list of results (None on per-call error)."""
    out = []
    for i in range(0, len(calls), size):
        chunk = calls[i:i + size]
        body = [{'jsonrpc': '2.0', 'id': j, 'method': m, 'params': p} for j, (m, p) in enumerate(chunk)]
        delay, last, res = 2.0, None, None
        for _ in range(tries):
            for u in RPCS:
                try:
                    res = _post(body, u)
                    if isinstance(res, dict):
                        raise RuntimeError(res.get('error'))
                    break
                except Exception as e:
                    last, res = e, None
            if res is not None:
                break
            time.sleep(delay)
            delay *= 1.5
        if res is None:
            if len(chunk) > 1:  # node 500s on some batches -> split and retry halves
                half = len(chunk) // 2
                out += batch(chunk[:half], size=half, tries=4)
                out += batch(chunk[half:], size=len(chunk) - half, tries=4)
                continue
            out.append(None)  # single call keeps failing -> mark missing, never fake
            continue
        res = sorted(res, key=lambda x: x['id'])
        out += [x.get('result') for x in res]
    return out


def head():
    return int(rpc('eth_blockNumber', [])['result'], 16)


def logs(flt, fr, to, step=4000):
    """Chunked eth_getLogs that shrinks the window on 'exceeds limit' and grows it back."""
    out = []
    step = min(step, 29000)
    while fr <= to:
        e = min(fr + step - 1, to)
        try:
            r = logs_rpc([dict(flt, fromBlock=hex(fr), toBlock=hex(e))])
        except RuntimeError as ex:
            if '400' in str(ex) and step > 500:  # response too large -> shrink the window
                step = max(500, step // 4)
                continue
            raise
        if 'error' in r:
            msg = str(r['error'])
            if step > 50 and ('exceed' in msg or 'span' in msg or 'too many' in msg.lower()):
                step = max(50, step // 2)
                continue
            raise RuntimeError(msg)
        out += r['result']
        fr = e + 1
        if len(r['result']) < 3000 and step < 29000:
            step = min(29000, int(step * 1.5))
    return out


import threading as _th
_LL = _th.Lock()
_lnext = [0.0]

def logs_rpc(params, tries=12):
    """eth_getLogs on LOGS_RPC, paced by LOGS_GAP, backoff on 429."""
    delay = 1.0
    last = None
    for _ in range(tries):
        with _LL:
            now = time.time(); w = max(0.0, _lnext[0] - now); _lnext[0] = max(now, _lnext[0]) + LOGS_GAP
        if w: time.sleep(w)
        try:
            return _post({'jsonrpc': '2.0', 'id': 1, 'method': 'eth_getLogs', 'params': params}, LOGS_RPC, timeout=40)
        except Exception as e:
            last = e
            time.sleep(delay); delay = min(delay * 1.7, 30)
    raise RuntimeError(f'eth_getLogs failed after retries: {last}')
