# RH Mint-Farm Watch

**A free GoodsMash RIGS community drop for Robinhood Chain (chain id 4663).**

Free mints on Robinhood Chain get farmed, but **most minters are ordinary people.** In one 7-day scan of every mint:

| Role | Wallets | Share of NFTs |
|---|---|---|
| Paid buyers (paid ETH for their own mint) | 13,080 | 11.3% |
| Self-minters (minted for themselves, kept them) | 118,584 | 79.6% |
| Distributors (paid for other wallets' mints, which were kept) | 193 | 0.7% |
| Farm operators (paid for other wallets AND swept) | 6 | 0.5% |
| Farm sinks (received swept NFTs from 2+ wallets) | 942 | 7.9% |

**About 91% of all minted NFTs went to people minting for themselves or paying for their own.** The concentrated farm share is the farm sinks, around **8%**. An earlier version of this tool over-flagged (it counted weak gas/timing signals as bots and could reach the top tier on activity alone); that is fixed.

This tool shows you that picture, lets you check any wallet, and gives creators what they need to make sure their mint reaches real people.

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
| `PAID_FOR_OTHER_MINTS` | Sent and paid for mint transactions where the NFTs went to *other* wallets. One wallet minting for many is the clearest farm signal. |
| `MINT_PAID_BY_OTHER` | This wallet's mints were sent and paid for by a different wallet (the other side of the line above). |
| `COLLECTS_FROM_MANY_MINTERS` | Received NFTs swept in from 3 or more different minting wallets. |
| `SENT_ON_AFTER_MINT` | Minted, then quickly sent the NFTs on to a collector wallet. |
| `SMART_WALLET_7702` | The wallet has delegated code (EIP-7702), which is used to run automated or batched mints. |
| `MINTED_TO_CONTRACT` | Mints went to a contract, not a normal wallet. |
| `NEW_WALLET` | Very few transactions ever, apart from minting. |
| `HIGH_MINT_COUNT` / `ACTIVE_MINTER` | Received far more mints than normal in the window. |
| `MINTS_MANY_COLLECTIONS` / `SEVERAL_COLLECTIONS` | Minted from a very large number of different collections. |
| `REGULAR_TIMING` | Mint timing too regular for a person. |
| `SAME_GAS_GROUP` | Five or more wallets sent byte-identical gas settings to the same mint (one script). |
| `LINKED_GROUP` | Linked to a farm through a shared operator or collector wallet. |

| Tier | Rule | Use it for |
|---|---|---|
| **STRONG_SIGNAL** (score 70+) | **Structural proof required**: paid for mints sent to other wallets, swept NFTs into a collector wallet, runs automated (EIP-7702) mints, or mints on machine timing. Score alone is not enough | The only tier safe to block |
| **MIXED_SIGNAL** (40-69, or 70+ on activity alone) | Several signals together. **A real person who mints a lot can land here** | Look, don't block |
| **LOW_SIGNAL** (20-39) | One weak signal. Normal collectors are in here | Never block on this alone |

### Who is minting (the honest breakdown)

`python participants.py` classifies every wallet that received a mint into one role, strongest-first:

- **PAID_BUYER** - paid ETH for its own mints and kept them. A real buyer. **Buying a paid mint is never a flag.**
- **SELF_MINTER** - minted for itself and kept them. A real person. Minting a lot is a habit, not guilt.
- **DISTRIBUTOR** - paid gas for mints sent to other wallets, and those wallets kept them. Looks like a gift, airdrop or community drop: a person, not a farm.
- **FARM_OPERATOR** - paid for other wallets' mints **and** swept its own out. A farm.
- **COLLECTS_FROM_MANY_MINTERS** - received swept NFTs from 2+ different minting wallets. One wallet holding many people's mints.

### These are people, not just bots

Read this before you use the list for anything.

- A flag is a signal about **wallet behaviour**, not a verdict and not a statement about the person behind it.
- **Most flagged wallets are real people.** A collector who mints every drop, or a newer wallet, trips the activity signals. Activity is a habit, not proof.
- **Buying a paid mint is not a flag.** Nothing in the scoring looks at price. If someone bought a paid mint and is on the list, they are on it for something else, or for volume alone (which is MIXED_SIGNAL at most, never CONFIRMED).
- Only `STRONG_SIGNAL` carries structural proof, and even that is **evidence, not identity**. It does not name, dox or shame anyone.
- **Never publish, name, or publicly shame a wallet.** Use the list to protect a mint, not to accuse people.
- If someone believes they are listed wrongly, open an issue. Flags are recomputed from fresh chain data every refresh, so a wallet that stops showing the pattern drops off.

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
| `flagged_strong.txt`, `flagged_mixed.txt` | One address per line, for contracts and sites |
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
