# RH Mint-Farm Watch

**A free GoodsMash RIGS community drop for Robinhood Chain (chain id 4663).**

Free mints on Robinhood Chain keep getting farmed. Over one 7-day scan, **about 2 of every 3 free-minted NFTs went to wallets showing bot or farm patterns**, and the top 1% of wallets took over half of everything minted. This tool shows you what is happening, lets you check any wallet, and gives creators what they need to make sure their mint reaches real people.

- **Read-only.** No keys, no wallet connection, no signing. It only reads public chain data.
- **No installs.** Python 3.9+ standard library. The dashboard is one HTML file.
- **Bring your own RPC.** Works with the public RPC, or any Robinhood Chain RPC you have.
- **Evidence, not accusations.** Every flag comes with the on-chain transactions behind it.

**Live dashboard:** https://goodsmash.github.io/rh-mint-farm-watch/

---

## What you can do

| I want to... | Dashboard | Command line |
|---|---|---|
| See what is minting **right now**, ranked by real wallets | "Minting now" tab | `python rhwatch.py live` |
| Check if a wallet is flagged | "Check a wallet" tab | `python rhwatch.py check 0xabc...` |
| Clean a giveaway / allowlist / airdrop list | Paste the list, click "Download clean list" | `python rhwatch.py check --file entrants.txt --clean` |
| See what a wallet minted lately (follow real collectors) | | `python rhwatch.py follow 0xabc...` |
| Find farms, operators, collector wallets | Farms / Operators / Swarms tabs | `python rhwatch.py scan` |
| Block farms in my own mint | "How to block" tab | [`contracts/`](contracts/) + [`skills/`](skills/) |
| Keep it updating on my own machine | | `python rhwatch.py watch --every 6 --weekly` |

## Quick start

```bash
git clone https://github.com/goodsmash/rh-mint-farm-watch
cd rh-mint-farm-watch
python rhwatch.py doctor          # tests your RPCs: chain id, speed, getLogs support
python rhwatch.py live            # last 15 minutes of mints
python rhwatch.py update-list     # pull the latest community master list
python rhwatch.py check 0xabc...
```

Full scan (all mints on the chain, the analysis, the master list and the dashboard):

```bash
python rhwatch.py scan --hours 24     # ~1 hour on the public RPC
python rhwatch.py scan --hours 168    # 7 days, ~2-3 hours
```
Then open `docs/index.html`. Scans are resumable: if one stops, run it again and it picks up where it left off.

## Using your own RPC

Pick whichever is easiest. The first one found wins.

```bash
# 1. a flag on any command
python rhwatch.py --rpc https://my-node.example,https://backup.example live

# 2. environment variables
export RH_RPCS="https://my-node.example,https://backup.example"
export RH_LOGS_RPC="https://my-archive-node.example"    # optional, used for eth_getLogs

# 3. a config file: copy rhwatch.config.example.json to rhwatch.config.json and edit it
```

`eth_getLogs` is the heavy call. Some free plans reject it over wide block ranges (for example, the drpc free plan rejects it here), so you can send it to a different RPC with `--logs-rpc`. `python rhwatch.py doctor` tells you which of your RPCs support it.

The dashboard's "Minting now" tab also lets you type your own RPC. It is saved only in your browser.

## How wallets are scored

| Signal | Meaning |
|---|---|
| `OPERATOR_FOR_OTHER_WALLETS` | Sent and paid for mint transactions where the NFTs went to *other* wallets. One wallet minting for many is the clearest farm signal. |
| `MINTED_BY_SOMEONE_ELSE` | This wallet's mints were sent and paid for by a different wallet (the other side of the line above). |
| `FARM_SINK` | Received NFTs swept in from 3 or more different minting wallets. |
| `MINT_AND_SWEEP` | Minted, then quickly sent the NFTs on to a collector wallet. |
| `EIP7702_DELEGATED` | The wallet has delegated code (EIP-7702), which is used to run automated or batched mints. |
| `CONTRACT_RECIPIENT` | Mints went to a contract, not a normal wallet. |
| `FRESH_THROWAWAY` | Very few transactions ever, apart from minting. |
| `HEAVY_MINTER` / `HIGH_VOLUME` | Received far more mints than normal in the window. |
| `SPRAY_ALL_DROPS` / `MANY_DROPS` | Minted from a very large number of different collections. |
| `MACHINE_CADENCE` | Mint timing too regular for a person. |
| `FEE_FINGERPRINT_SWARM` | Five or more wallets sent byte-identical gas settings to the same mint (one script). |
| `CLUSTER_MEMBER` | Linked to a farm through a shared operator or collector wallet. |

| Tier | Rule | Use it for |
|---|---|---|
| **CONFIRMED_PATTERN** (score 70+) | Structural on-chain proof (minting for others, feeding a collector wallet, automated-mint code) plus volume | Safe to block |
| **LIKELY** (40-69) | Several signals together | Block with care; some heavy real collectors land here |
| **WATCH** (20-39) | One weak signal | Never block on this alone |

**Limits, honestly:**
- A fresh wallet costs a fraction of a cent on this chain. A blocklist raises the cost of farming, but it is not a wall. Contract rules (see `contracts/`) do more.
- Burns (sends to 0x0 / 0xdead) are excluded from farm detection.
- Collections with very few minters (creator self-mints, tests) can show "100% flagged". Judge flagged share only on collections with hundreds of minters.
- The 7-day scan samples the heaviest 1,200 wallets for transaction details, so the long tail is less covered.

**Please don't publicly name or shame wallets.** If you think your wallet is listed wrongly, open an issue with the address. Flags are re-computed from fresh chain data every refresh, so a wallet that stops farming drops off.

## Files

| File | What it is |
|---|---|
| `rhwatch.py` | The one command: doctor, live, follow, check, scan, watch, dashboard, update-list |
| `rhlib.py` | RPC helpers: config, retries, batching, rate limiting |
| `scan.py`, `phase_d.py`, `analyze.py`, `build_dashboard.py` | The scan pipeline (rhwatch runs these for you) |
| `master_list.json` / `.csv` | Every flagged wallet with tier, score, labels and proof transactions |
| `blocklist_confirmed_pattern.txt`, `blocklist_likely.txt` | One address per line, for contracts and sites |
| `docs/` | The dashboard (GitHub Pages), plus `lookup.json` for sites and bots |
| `data/<window>/report.json` | Full analysis per window |
| `contracts/` | Anti-farm mint base contract, an on-chain farm registry, and TUNKI (an example collection). Foundry, with tests |
| `skills/` | Agent skills and copy-paste Bankr prompts for fair free mints and farm checks |

## Auto-refresh

The GitHub Action in `.github/workflows/refresh.yml` re-scans the last 24 hours every 6 hours and the last 7 days once a week, then commits the new master list and dashboard. Fork the repo and it runs for you too. Set the repo secrets `RH_RPCS` / `RH_LOGS_RPC` if you want it to use your own RPC.

## For sites and bots

```js
const L = await (await fetch('https://goodsmash.github.io/rh-mint-farm-watch/lookup.json')).json();
const [tier, score, labels] = L.wallets[address.toLowerCase()] || ['NOT_LISTED'];
```

---

Built and given away by the GoodsMash RIGS community. MIT licensed. Use it, fork it, improve it.
