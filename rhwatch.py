#!/usr/bin/env python3
"""rhwatch - Robinhood Chain (4663) mint-farm watch. A GoodsMash RIGS community drop.

Read-only. No keys. No signing. Python 3.9+, standard library only.

  python rhwatch.py doctor                        test your RPCs (speed, logs support)
  python rhwatch.py live [--minutes 15]           what is minting RIGHT NOW, ranked by real minters
  python rhwatch.py follow 0xabc... [--hours 24]    what has this wallet minted lately (copy real collectors)
  python rhwatch.py check 0xabc... [0xdef...]     is this wallet flagged? (+ live nonce / code)
  python rhwatch.py check --file entrants.txt --clean   strip flagged wallets from a giveaway list
  python rhwatch.py scan [--hours 24]             full scan -> analysis -> master list -> dashboard
  python rhwatch.py watch [--every 6]             re-scan every N hours, forever (keeps last good data)
  python rhwatch.py dashboard                     rebuild dashboard + master list from existing data
  python rhwatch.py update-list                   download the latest community master list

Use your own RPC on any command:
  python rhwatch.py --rpc https://my-node.example,https://backup.example live
  python rhwatch.py --logs-rpc https://my-archive-node.example scan --hours 168
or put them in rhwatch.config.json (see rhwatch.config.example.json), or env RH_RPCS / RH_LOGS_RPC.
"""
import argparse, json, os, re, subprocess, sys, time, urllib.request
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
LIST_URL = os.environ.get('RH_LIST_URL',
                          'https://raw.githubusercontent.com/goodsmash/rh-mint-farm-watch/main/master_list.json')


def _apply_rpc_flags(a):
    # must happen before rhlib is imported so every subprocess inherits it too
    if a.rpc:
        os.environ['RH_RPCS'] = a.rpc
    if a.logs_rpc:
        os.environ['RH_LOGS_RPC'] = a.logs_rpc


def _rhlib():
    sys.path.insert(0, BASE)
    import rhlib
    return rhlib


def _run(script, *args, env=None):
    r = subprocess.run([sys.executable, os.path.join(BASE, script), *args], cwd=BASE,
                       env={**os.environ, **(env or {})})
    if r.returncode != 0:
        raise SystemExit(f'{script} failed (exit {r.returncode})')


def _master():
    p = os.path.join(BASE, 'master_list.json')
    if not os.path.exists(p):
        return {}, None
    M = json.load(open(p))
    return {w['address']: w for w in M['wallets']}, M


# ---------------------------------------------------------------- doctor
def cmd_doctor(a):
    rh = _rhlib()
    print(f'RPCs: {rh.RPCS}\nlogs RPC: {rh.LOGS_RPC} (gap {rh.LOGS_GAP}s)\n')
    ok_any = False
    for u in rh.RPCS + ([rh.LOGS_RPC] if rh.LOGS_RPC not in rh.RPCS else []):
        line = f'{u}\n'
        try:
            t = time.time()
            r = rh._post({'jsonrpc': '2.0', 'id': 1, 'method': 'eth_chainId', 'params': []}, u, timeout=15)
            cid = int(r['result'], 16)
            hb = int(rh._post({'jsonrpc': '2.0', 'id': 1, 'method': 'eth_blockNumber', 'params': []}, u,
                              timeout=15)['result'], 16)
            line += f'  chain {cid} {"OK" if cid == rh.CHAIN_ID else "WRONG CHAIN"}  head {hb}  {int((time.time()-t)*1000)} ms\n'
            ok_any |= cid == rh.CHAIN_ID
            for span in (2000, 20000):
                try:
                    r = rh._post({'jsonrpc': '2.0', 'id': 1, 'method': 'eth_getLogs', 'params': [
                        {'fromBlock': hex(hb - span), 'toBlock': hex(hb), 'topics': [rh.TRANSFER, rh.ZERO_T]}]},
                        u, timeout=40)
                    line += (f'  getLogs {span} blocks: ' +
                             (f'OK ({len(r["result"])} mint logs)' if 'result' in r else f'ERROR {r.get("error")}') + '\n')
                except Exception as e:
                    line += f'  getLogs {span} blocks: FAIL {str(e)[:90]}\n'
            r = rh._post([{'jsonrpc': '2.0', 'id': i, 'method': 'eth_blockNumber', 'params': []} for i in range(5)],
                         u, timeout=15)
            line += f'  batch requests: {"OK" if isinstance(r, list) else "NOT SUPPORTED"}\n'
        except Exception as e:
            line += f'  FAIL {str(e)[:120]}\n'
        print(line)
    print('Tip: scan needs eth_getLogs over 2000+ block ranges. If your logs RPC fails that, set --logs-rpc.')
    return 0 if ok_any else 1


# ---------------------------------------------------------------- live
def cmd_live(a):
    rh = _rhlib()
    by, M = _master()
    H = rh.head()
    span = int(a.minutes * 60 / 0.1031)
    print(f'last {a.minutes} min = blocks {H-span}..{H}' + ('' if M else '   (no master_list.json: run update-list for bot flags)'))
    TS = '0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62'
    logs = rh.logs({'topics': [rh.TRANSFER, rh.ZERO_T]}, H - span, H, step=3000)
    logs = [l for l in logs if len(l['topics']) == 4]  # ERC-721 only (ERC-20 has 3 topics)
    logs += [dict(l, _1155=1) for l in rh.logs({'topics': [TS, None, rh.ZERO_T]}, H - span, H, step=3000)]
    C = defaultdict(lambda: {'n': 0, 'to': Counter(), 'tx': set(), 'last': 0})
    for l in logs:
        c = C[l['address'].lower()]
        to = rh.unpad(l['topics'][3]).lower()
        c['n'] += 1; c['to'][to] += 1; c['tx'].add(l['transactionHash']); c['last'] = max(c['last'], int(l['blockNumber'], 16))
    rows = []
    for addr, c in C.items():
        flagged = sum(n for w, n in c['to'].items() if by.get(w, {}).get('tier') in ('CONFIRMED_PATTERN', 'LIKELY'))
        real = [w for w in c['to'] if by.get(w, {}).get('tier') not in ('CONFIRMED_PATTERN', 'LIKELY')]
        rows.append({'contract': addr, 'minted': c['n'], 'wallets': len(c['to']), 'real_wallets': len(real),
                     'flagged_share': flagged / c['n'], 'example_tx': sorted(c['tx'])[0],
                     'secs_ago': int((H - c['last']) * 0.1031)})
    rows.sort(key=lambda r: (-r['real_wallets'], -r['minted']))
    rows = rows[:a.top * 3]
    names = {}
    calls = [('eth_call', [{'to': r['contract'], 'data': '0x06fdde03'}, 'latest']) for r in rows]
    for r, res in zip(rows, rh.batch(calls, size=4)):
        try:
            b = bytes.fromhex(res[2:]); ln = min(int.from_bytes(b[32:64], 'big'), 96, max(0, len(b) - 64)); names[r['contract']] = b[64:64+ln].decode(errors='replace') or '?'
        except Exception:
            names[r['contract']] = '?'
    hidden = 0
    if not a.include_lp:  # DEX liquidity-position NFTs (Uniswap, Ramses, ...) are not drops
        lp = re.compile(r'position|positions|liquidity|\bLP\b', re.I)
        before = len(rows); rows = [r for r in rows if not lp.search(names[r['contract']])]; hidden = before - len(rows)
    rows = rows[:a.top]
    if hidden:
        print(f'({hidden} DEX liquidity-position collections hidden; --include-lp to show)')
    print(f'\n{"collection":28} {"minted":>7} {"wallets":>7} {"real":>6} {"bots%":>6} {"last":>6}  contract / copy this mint tx')
    for r in rows:
        print(f'{names[r["contract"]][:28]:28} {r["minted"]:>7} {r["wallets"]:>7} {r["real_wallets"]:>6} '
              f'{r["flagged_share"]*100:>5.0f}% {r["secs_ago"]:>5}s  {r["contract"]}\n'
              f'{"":58}{rh.EXPLORER}/tx/{r["example_tx"]}')
    print('\nreal = recipients not on the confirmed/likely list. Ranked by real wallets, not raw volume.\n'
          'Open the example tx -> "Input data" shows the exact mint function + args to copy.\n'
          'ALWAYS check the contract is verified and the price is what you expect before you sign.')
    if a.json:
        json.dump([dict(r, name=names[r['contract']]) for r in rows], open(a.json, 'w'), indent=1)
        print('wrote', a.json)


# ---------------------------------------------------------------- follow
def cmd_follow(a):
    """What has this wallet minted lately? Use it to follow real collectors (or see what a farm targets)."""
    rh = _rhlib()
    by, M = _master()
    H = rh.head(); span = int(a.hours * 3600 / 0.1031)
    for w in [x.lower() for x in a.addrs]:
        t = by.get(w, {}).get('tier', 'NOT_LISTED')
        logs = rh.logs({'topics': [rh.TRANSFER, rh.ZERO_T, None, rh.pad(w)]}, H - span, H, step=29000)
        logs = [l for l in logs if len(l['topics']) == 4]
        C = defaultdict(lambda: [0, None, 0])
        for l in logs:
            c = C[l['address'].lower()]; c[0] += 1; b = int(l['blockNumber'], 16)
            if b >= c[2]: c[1], c[2] = l['transactionHash'], b
        print(f'\n{w}  [{t}]  minted {len(logs)} NFTs from {len(C)} collections in the last {a.hours}h')
        if t in ('CONFIRMED_PATTERN', 'LIKELY'):
            print('  note: this wallet is flagged - following it means following a farm')
        for c, (n, tx, b) in sorted(C.items(), key=lambda kv: -kv[1][2])[:a.top]:
            print(f'  {int((H-b)*0.1031/60):>5} min ago  x{n:<4} {c}  {rh.EXPLORER}/tx/{tx}')

# ---------------------------------------------------------------- check
def cmd_check(a):
    rh = _rhlib()
    by, M = _master()
    if not M:
        print('no master_list.json yet. Run:  python rhwatch.py update-list   (or scan)')
        return 1
    addrs = [x.lower() for x in a.addrs]
    if a.file:
        addrs += [m.lower() for m in re.findall(r'0x[0-9a-fA-F]{40}', open(a.file, errors='replace').read())]
    addrs = list(dict.fromkeys(addrs))
    if not addrs:
        print('give addresses or --file'); return 1
    print(f'master list: {M["count"]} wallets, generated {M["generated"]}\n')
    live = {}
    if len(addrs) <= a.live_max:
        calls = []
        for x in addrs:
            calls += [('eth_getTransactionCount', [x, 'latest']), ('eth_getCode', [x, 'latest'])]
        res = rh.batch(calls, size=4)
        for i, x in enumerate(addrs):
            live[x] = (res[2*i], res[2*i+1])
    keep, hits = [], Counter()
    for x in addrs:
        w = by.get(x)
        tier = w['tier'] if w else 'NOT_LISTED'
        hits[tier] += 1
        if not a.quiet or tier in ('CONFIRMED_PATTERN', 'LIKELY'):
            print(f'{x}  {tier}' + (f'  score {w["score"]}' if w else ''))
            if x in live and live[x][0] is not None:
                code = live[x][1] or '0x'
                kind = 'normal wallet' if code == '0x' else ('EIP-7702 automated' if code.startswith('0xef0100') else 'CONTRACT')
                print(f'   live: {int(live[x][0], 16)} txs sent, {kind}')
            if w:
                e = w.get('evidence', {})
                print(f'   why: {", ".join(w["labels"])}')
                print('   proof: ' + ('STRUCTURAL - paid for other wallets / farm sink / automated mints'
                                      if e.get('structural_proof') else
                                      'activity only, no farm proof (real heavy collectors look like this)'))
                print(f'   minted {e.get("tokens")} NFTs / {e.get("collections")} collections, '
                      f'paid for others: {e.get("operated_for", 0)}, sent on: {e.get("swept_out", 0)}')
                for h in (e.get('example_tx') or [])[:2]:
                    print(f'   proof: {rh.EXPLORER}/tx/{h}')
        if tier not in ('CONFIRMED_PATTERN', 'LIKELY') or (tier == 'LIKELY' and a.keep_likely):
            keep.append(x)
    print(f'\n{len(addrs)} checked: {dict(hits)}')
    if a.clean and a.file:
        out = os.path.splitext(a.file)[0] + '.clean.txt'
        open(out, 'w').write('\n'.join(keep) + '\n')
        print(f'wrote {out}  ({len(keep)} kept, {len(addrs)-len(keep)} removed)')
    return 0


# ---------------------------------------------------------------- scan / watch / dashboard
def _scan(hours):
    D = os.path.join(BASE, 'data', f'{hours}h')
    prev = D + '.prev'
    import shutil
    if os.path.exists(D):
        shutil.rmtree(prev, ignore_errors=True); os.rename(D, prev)
    extra = ['--per-wallet', '2', '--top-wallets', '1200'] if hours > 24 else []
    try:
        _run('scan.py', '--hours', str(hours), *extra, env={'SKIP_D': '1'})
        _run('phase_d.py', '--hours', str(hours))
        _run('analyze.py', '--hours', str(hours))
    except SystemExit:
        shutil.rmtree(D, ignore_errors=True)
        if os.path.exists(prev):
            os.rename(prev, D)
            print('scan failed: kept previous good data')
        raise
    shutil.rmtree(prev, ignore_errors=True)
    _run('build_dashboard.py')


def cmd_scan(a):
    _scan(a.hours)
    print('done. open dashboard/index.html')


def cmd_watch(a):
    n = 0
    while True:
        n += 1
        print(time.strftime('%F %T'), f'watch run {n}: scanning last {a.hours}h', flush=True)
        try:
            _scan(a.hours)
            if a.weekly and n % max(1, int(168 / a.every)) == 0:
                _scan(168)
        except SystemExit as e:
            print('run failed:', e, '- will retry next cycle', flush=True)
        print(time.strftime('%F %T'), f'sleeping {a.every}h', flush=True)
        time.sleep(a.every * 3600)


def cmd_dashboard(a):
    _run('build_dashboard.py')


def cmd_update_list(a):
    url = a.url or LIST_URL
    req = urllib.request.Request(url, headers={'user-agent': 'rhwatch'})
    data = urllib.request.urlopen(req, timeout=60).read()
    M = json.loads(data)
    assert M.get('chain_id') == 4663 and isinstance(M.get('wallets'), list), 'not a 4663 master list'
    open(os.path.join(BASE, 'master_list.json'), 'wb').write(data)
    for tier in ('CONFIRMED_PATTERN', 'LIKELY'):
        open(os.path.join(BASE, f'blocklist_{tier.lower()}.txt'), 'w').write(
            '\n'.join(w['address'] for w in M['wallets'] if w['tier'] == tier) + '\n')
    print(f'master list updated: {M["count"]} wallets, generated {M["generated"]}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rpc', help='comma-separated RPC URLs (overrides config/env)')
    ap.add_argument('--logs-rpc', help='RPC used for eth_getLogs (needs wide block ranges)')
    sp = ap.add_subparsers(dest='cmd', required=True)
    sp.add_parser('doctor', help='test RPCs')
    p = sp.add_parser('live', help='what is minting right now')
    p.add_argument('--minutes', type=float, default=15); p.add_argument('--top', type=int, default=20)
    p.add_argument('--json', help='also write results to this file')
    p.add_argument('--include-lp', action='store_true', help='also show DEX liquidity-position NFTs')
    p = sp.add_parser('follow', help='what a wallet minted lately')
    p.add_argument('addrs', nargs='+'); p.add_argument('--hours', type=float, default=24); p.add_argument('--top', type=int, default=25)
    p = sp.add_parser('check', help='check wallets against the master list')
    p.add_argument('addrs', nargs='*'); p.add_argument('--file'); p.add_argument('--clean', action='store_true')
    p.add_argument('--quiet', action='store_true', help='only print flagged wallets')
    p.add_argument('--keep-likely', action='store_true', help='with --clean, only remove CONFIRMED_PATTERN')
    p.add_argument('--live-max', type=int, default=200, help='skip live RPC lookups above this many addresses')
    p = sp.add_parser('scan', help='full scan + analysis + dashboard'); p.add_argument('--hours', type=int, default=24)
    p = sp.add_parser('watch', help='re-scan forever')
    p.add_argument('--every', type=float, default=6); p.add_argument('--hours', type=int, default=24)
    p.add_argument('--weekly', action='store_true', help='also run a 7-day scan once a week')
    sp.add_parser('dashboard', help='rebuild dashboard from existing data')
    p = sp.add_parser('update-list', help='download latest community master list'); p.add_argument('--url')
    a = ap.parse_args()
    _apply_rpc_flags(a)
    fn = {'doctor': cmd_doctor, 'live': cmd_live, 'follow': cmd_follow, 'check': cmd_check, 'scan': cmd_scan, 'watch': cmd_watch,
          'dashboard': cmd_dashboard, 'update-list': cmd_update_list}[a.cmd]
    sys.exit(fn(a) or 0)


if __name__ == '__main__':
    main()
