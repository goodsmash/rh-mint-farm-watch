"""Bundle every data/<window>/report.json into dashboard/data.js + a master list. Static, no server needed."""
import json, os, csv, time
BASE = os.path.dirname(os.path.abspath(__file__))
reports = {}
for w in sorted(os.listdir(os.path.join(BASE, 'data'))):
    p = os.path.join(BASE, 'data', w, 'report.json')
    if os.path.exists(p):
        reports[w] = json.load(open(p))
DOCS = os.path.join(BASE, 'docs')  # GitHub Pages serves this folder
os.makedirs(DOCS, exist_ok=True)
# master list = union across windows, keep the highest score + all labels
master = {}
for w, r in reports.items():
    for x in r['wallets']:
        m = master.setdefault(x['address'], {'address': x['address'], 'score': 0, 'tier': 'WATCH', 'labels': set(),
                                             'windows': [], 'cluster': x.get('cluster')})
        m['windows'].append(w)
        m['labels'] |= set(x['labels'])
        if x['score'] > m['score']:
            m['score'], m['tier'] = x['score'], x['tier']
            m['evidence'] = x['evidence']
        m['cluster'] = m['cluster'] or x.get('cluster')
ml = sorted(master.values(), key=lambda m: -m['score'])
for m in ml:
    m['labels'] = sorted(m['labels'])
master_doc = {
    'name': 'Robinhood Chain (4663) mint-farm watchlist - GoodsMash RIGS community drop',
    'source': 'https://github.com/goodsmash/rh-mint-farm-watch',
    'generated': time.strftime('%Y-%m-%dT%H:%M:%S'),
    'chain_id': 4663,
    'method': 'Public RPC eth_getLogs replay of every ERC-721 / ERC-1155 mint, sampled tx senders, outflow tracing. '
              'Scores are evidence signals, not proof of identity. Tiers: CONFIRMED_PATTERN >=70, LIKELY 40-69, WATCH 20-39.',
    'windows': {w: r['summary'] for w, r in reports.items()},
    'count': len(ml),
    'wallets': ml,
}
json.dump(master_doc, open(os.path.join(BASE, 'master_list.json'), 'w'), indent=0)
with open(os.path.join(BASE, 'master_list.csv'), 'w', newline='') as f:
    wr = csv.writer(f)
    wr.writerow(['address', 'tier', 'score', 'labels', 'cluster', 'windows', 'tokens', 'collections'])
    for m in ml:
        e = m.get('evidence', {})
        wr.writerow([m['address'], m['tier'], m['score'], '|'.join(m['labels']), m.get('cluster') or '',
                     '|'.join(m['windows']), e.get('tokens'), e.get('collections')])
# plain address lists for blocklists / contracts
for tier in ('CONFIRMED_PATTERN', 'LIKELY'):
    with open(os.path.join(BASE, f'blocklist_{tier.lower()}.txt'), 'w') as f:
        f.write('\n'.join(m['address'] for m in ml if m['tier'] == tier) + '\n')
# dashboard data (trim per-report wallet list for size)
slim = {}
for w, r in reports.items():
    slim[w] = dict(r)
    slim[w]['wallets'] = r['wallets'][:3000]
with open(os.path.join(DOCS, 'data.js'), 'w') as f:
    f.write('window.REPORTS=' + json.dumps(slim) + ';\n')
# compact lookup for the browser wallet checker: address -> [tier, score, labels, tokens, collections, operated_for, example_tx]
look = {m['address']: [m['tier'], m['score'], m['labels'], m.get('evidence', {}).get('tokens'),
                       m.get('evidence', {}).get('collections'), m.get('evidence', {}).get('operated_for', 0),
                       (m.get('evidence', {}).get('example_tx') or [None])[0]] for m in ml}
with open(os.path.join(DOCS, 'lookup.json'), 'w') as f:
    json.dump({'generated': master_doc['generated'], 'wallets': look}, f, separators=(',', ':'))
import shutil
for fn in ('blocklist_confirmed_pattern.txt', 'blocklist_likely.txt', 'master_list.csv'):
    shutil.copy(os.path.join(BASE, fn), os.path.join(DOCS, fn))
print('windows', list(reports), 'master', len(ml), {t: sum(1 for m in ml if m['tier'] == t) for t in ('CONFIRMED_PATTERN', 'LIKELY', 'WATCH')})
