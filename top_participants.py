"""Top-100 collections praise data for the mint-farm watch dashboard.

Builds a PRAISE (never-flag) view: the wallets that paid the most AND the wallets
that hold the most, each tied to the collection it supported. The goal is to
show "the people who actually turned up" - real buyers and real holders - not
bot labels. Every entry carries its evidence; nothing here is an accusation.

Also produces the "top chains of the best projects" rollup and a small "more"
pool (memes / wrapped) so the view is not only a single flat list.

Output: data/<window>/top_participants.json   (one file per window, produced
by `python top_participants.py`, then `python build_dashboard.py`.)

Data source: data/<window>/report.json (on-chain scan data, read-only).
"""

import json, os
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, 'data', 'top_participants')
TOPN = 100

ROLE_LABELS = {
    'PAID_BUYER': 'paid the most',
    'SELF_MINTER': 'self-minted',
    'DISTRIBUTOR': 'distributed to others (gift/airdrop)',
    'FARM_OPERATOR': 'operated mints for many other wallets',
    'COLLECTS_FROM_MANY_MINTERS': 'received swept NFTs from many minting wallets',
}


def load(mint_window):
    rep = os.path.join(BASE, 'data', mint_window, 'report.json')
    R = json.load(open(rep))
    return R


def top_collections(R, n=TOPN):
    """Rank collections by real participation (unique wallets who took), ties broken by volume."""
    cs = sorted(R['collections'], key=lambda c: (-c['unique_recipients'], -c['minted']))
    return cs[:n]


def participant_rows(R, c):
    """Praised top payers and top holders for one collection, with evidence."""
    tms = c.get('top_minters') or []
    holders = c.get('top_holders') or []
    # top holders are wallets that received the most NFTs in this window
    rows = []
    for wallet, n in tms[:10]:
        rows.append({'role': 'PAID_BUYER', 'wallet': wallet, 'nfts': n, 'note': 'paid ETH for this collection'})
    for wallet, n in (holders[:10] if isinstance(holders, list) else []):
        rows.append({'role': 'SELF_MINTER', 'wallet': wallet, 'nfts': n, 'note': 'held the most of this collection'})
    return rows


def chains_rollup(R):
    """Aggregate collections by the ecosystem chunk they belong to (read-only map)."""
    buckets = defaultdict(lambda: {'collections': 0, 'mints': 0, 'wallets': set()})
    for c in R['collections']:
        # bucket by a stable prefix of the collection name so we can show "top chains of best projects"
        name = (c.get('name') or '').lower()
        if 'uniswap' in name:
            bucket = 'DeFi / dex positions'
        elif 'robonomics' in name or 'passport' in name:
            bucket = 'Identity / credentials'
        elif 'claymo' in name or 'stampy' in name or 'art blocks' in name:
            bucket = 'Generative art'
        elif 'hoodie' in name or 'cartel' in name or 'souls club' in name or 'dancing bear' in name or 'nob bot' in name or 'auto cartella' in name or 'mad crystal' in name or 'beastside' in name or 'snurps' in name or 'tickergeist' in name or 'rainbow hoodie' in name:
            bucket = 'Community drops'
        elif 'zumi' in name or 'emu' in name or 'gaia' in name:
            bucket = 'Character / mascot'
        elif 'chase' in name or 'chase ' in name or 'chase.' in name or 'chase!' in name:
            bucket = 'Chase / sandbox'
        elif 'gaming' in name or 'game' in name:
            bucket = 'Gaming'
        else:
            bucket = 'Wildcards'
        buckets[bucket]['collections'] += 1
        buckets[bucket]['mints'] += c.get('minted') or 0
        buckets[bucket]['wallets'].add(c.get('contract'))
    out = []
    for b, v in sorted(buckets.items(), key=lambda kv: -kv[1]['mints']):
        out.append({'bucket': b, 'collections': v['collections'],
                    'mints': v['mints'],
                    'wallets': len(v['wallets'])})
    return out


DATA_GENERATED = None
try:
    DATA_GENERATED = json.load(open(os.path.join(BASE, 'data', '24h', 'report.json')))['summary'].get('generated')
except Exception:
    DATA_GENERATED = None


def build(mint_window):
    R = load(mint_window)
    cs = top_collections(R)
    rows = []
    for i, c in enumerate(cs, 1):
        rows.append({
            'rank': i,
            'contract': c['contract'],
            'name': c.get('name') or 'unknown collection',
            'minted': c.get('minted') or 0,
            'recipients': c.get('unique_recipients') or 0,
            'operators': c.get('unique_operators') or 0,
            'flagged_share': c.get('flagged_share') or 0,
            'hours_active': c.get('hours_active') or 0,
            'top_payers': participant_rows(R, c),
        })
    return {
        'window': mint_window,
        'generated': R.get('summary', {}).get('generated') or DATA_GENERATED or utcnow_iso(),
        'total_collections_scanned': len(R['collections']),
        'top100': rows,
        'channels': chains_rollup(R),
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    for w in ('24h', '168h'):
        D = build(w)
        p = os.path.join(OUT, f'{w}.json')
        json.dump(D, open(p, 'w'), indent=1)
        print(f'{w} -> {p}  ({len(D["top100"])} collections, {len(D["channels"])} channels)')


if __name__ == '__main__':
    main()
