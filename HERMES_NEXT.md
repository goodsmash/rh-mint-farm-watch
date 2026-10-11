# Hand-off to Hermes (from Claude, 2026-10-11 ~03:40 ET)

## 1. Commit and push these fixes (already applied in this folder, tested)

```bash
git add owners.py data/owners_cache.json participants.py rhwatch.py README.md \
        skills/mint-farm-check/SKILL.md .github/workflows/refresh.yml \
        docs master_list.json master_list.csv flagged_*.txt data/*/report.json HERMES_NEXT.md
git commit -m "fix: collection owners airdropping their own drop are not farms; repair Mint operators + Who-is-minting tabs after label rename; auto-refresh now runs owners.py + participants.py"
git push
```

What was wrong (people reported "something wrong with the owner"):

| Problem | Cause | Fix |
|---|---|---|
| Creators flagged as farms | A collection owner paying gas to airdrop its own collection = `PAID_FOR_OTHER_MINTS` (structural proof). 54 owners flagged, 25 in STRONG. ~7,000 airdrop recipients tagged `LINKED_GROUP` / `MINT_PAID_BY_OTHER` | New `owners.py`: reads `owner()` on the collections each operator paid for. Owner of >=50% of those mints -> `COLLECTION_OWNER`, drops `PAID_FOR_OTHER_MINTS` + `REGULAR_TIMING`, tier capped at MIXED, recipients cleared. Master list 31,513 -> 25,976, STRONG 470 -> 445 |
| "Mint operators" tab empty | `index.html` still filtered on old label `OPERATOR_FOR_OTHER_WALLETS` | filters `PAID_FOR_OTHER_MINTS` / `COLLECTION_OWNER` |
| "Who is minting" showed 0 farm collectors | `participants.py` role renamed to `COLLECTS_FROM_MANY_MINTERS`, dashboard still keyed `FARM_SINK` | dashboard key fixed (24h: 162, 7d: 942) |
| Next auto-refresh would wipe Who-is-minting + Top participants | `rhwatch.py _scan` never ran `participants.py` | `_scan` now runs analyze -> owners -> participants -> build_dashboard |
| Bankr skill out of date | `skills/mint-farm-check/SKILL.md` used CONFIRMED/LIKELY/FARM_SINK | rewritten with current labels + owner rule |

Also check: the 6-hourly scheduled refresh did not fire at 06:17 UTC (only the manual 03:17 run exists).
Open Actions -> "refresh master list" and confirm schedules are enabled; run it once by hand after this push.

Owner cache note: `data/owners_cache.json` only covers collections checked from the browser so far.
In GitHub Actions (has RPC) `owners.py` fills in the rest automatically. Unknown owner = not cleared (conservative).

## 2. v2 market engine: verified facts (live, chain 4663)

- Seaport 1.6 `0x0000000000000068F116a894984e2DB1123eB395` and 1.5 `0x00000000000000ADc04C56Bf30aC9d3c0aAF14dC` are deployed. All recent volume is on 1.6.
- RPC getLogs limits: no address = 30k blocks; address array = 100k; **single address = 10M blocks**. Block time ~0.1045 s.
- 24h: 14,154 Seaport sales, 486 collections, pulled in ~6 s in the browser (one address per query).
- Currencies: ETH, WETH `0x0bd7d308f8e1639fab988df18a8011f41eacad73` (18 dec), USDG `0x5fc5360d0400a0fd4f2af552add042d716f1d168` (6 dec).
- Top 24h by ETH volume: QUOTRONS, Snurps, RH MACHINES, Rekt Tradooors, Robin Simpson, Slippy Club.
- Full holder map from Transfer replay: Snurps 1,544 holders (5,934 logs, 3 s), Snouts Club 221.
- Images: tokenURI works on some collections only; OpenSea API key needed for the rest (free 7-day key: `POST https://api.opensea.io/api/v2/auth/keys`; permanent: opensea.io/settings/developer). Put it in a repo secret `OPENSEA_API_KEY`, never in code.
- ETH/USD with CORS: `https://api.coinbase.com/v2/prices/ETH-USD/spot`.
- Engine code: `docs/market.js` (sales decode, holders, images, wash/holder stats). Not wired into the dashboard yet.

## 3. Next to build
1. Market tab (top collections by volume with image, sales, buyers, floor-ish, wash share, % held by flagged wallets).
2. Collection page (holders, distribution, top holders tagged, recent moves joined to sales).
3. Whales tab (biggest buyers/sellers across the window, flagged tags).
4. rh-market: on-chain blocklist contract + marketplace UI.
