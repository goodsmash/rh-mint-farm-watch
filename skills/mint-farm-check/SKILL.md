---
name: mint-farm-check
description: Use when someone asks "is this wallet a bot / farm / side wallet?" on Robinhood Chain (4663), or before an airdrop, allowlist, or giveaway draw. Checks the wallet against the master list and the live chain, and returns the evidence, not a verdict.
metadata: {"chain":"robinhood-4663"}
---

# Mint Farm Check

## Inputs
- A wallet address, a list of addresses (allowlist / giveaway entrants), or a collection address.

## Sources (in order)
1. **Master list**: `master_list.json` in https://github.com/goodsmash/rh-mint-farm-watch (or https://goodsmash.github.io/rh-mint-farm-watch/lookup.json) (every flagged wallet with its signals and evidence).
   Each entry: `address, tier (LOW_SIGNAL / MIXED_SIGNAL / STRONG_SIGNAL), score, signals[], mints, collections,
   sink (where it sweeps to), operator (who paid for its mints), cluster id`.
2. **On-chain registry** (when deployed): `MintFarmRegistry.level(address)`. Read-only, free.
3. **Live chain** for anything not in the list: `eth_getTransactionCount`, `eth_getCode`, `eth_getBalance`,
   and ERC-721 `Transfer` logs with `topic1 = 0x0` (mints) and `topic1 = wallet` (outflows).

## What each signal means (exact labels from analyze.py + owners.py)
| Label | Meaning | Points |
|---|---|---|
| `COLLECTS_FROM_MANY_MINTERS` | Collector wallet: received minted NFTs from 3+ different minting wallets in the window | 40 |
| `PAID_FOR_OTHER_MINTS` | Paid gas for mints delivered to 3+ other wallets | 30 |
| `HIGH_MINT_COUNT` / `ACTIVE_MINTER` | 200+ / 50+ tokens in the window | 35 / 20 |
| `MINTS_MANY_COLLECTIONS` / `SEVERAL_COLLECTIONS` | Minted 25+ / 10+ different collections | 25 / 12 |
| `REGULAR_TIMING` | 30+ mint txs with median gap under 20 s | 15 |
| `SENT_ON_AFTER_MINT` | Sent on at least half of what it minted (5+ tokens) | 15 |
| `SAME_GAS_GROUP` | Same collection + selector + maxFee + priority + gas limit as 5+ other senders | 15 |
| `MINT_PAID_BY_OTHER` | Received 5+ mints paid for by another wallet | 10 |
| `NEW_WALLET` | Nonce 15 or less and 5+ tokens | 10 |
| `MINTED_TO_CONTRACT` / `SMART_WALLET_7702` | Has contract code / `0xef0100` delegation | 10 / 5 |
| `LINKED_GROUP` | Belongs to a collector or operator group but no other signal fired | fixed 25 |
| `COLLECTION_OWNER` | Paid for mints sent to others, **but owns the collection** (creator airdrop). `PAID_FOR_OTHER_MINTS` and `REGULAR_TIMING` are removed and the tier is capped at MIXED | -30 / -15 |

Tiers: **STRONG_SIGNAL** = score 70+ **and** structural proof, **MIXED_SIGNAL** = 40+, **LOW_SIGNAL** = 20-39.
Registry levels map as STRONG_SIGNAL -> 3, MIXED_SIGNAL -> 2, LOW_SIGNAL -> 1.

Structural proof = `PAID_FOR_OTHER_MINTS`, `COLLECTS_FROM_MANY_MINTERS`, `SENT_ON_AFTER_MINT`, `SMART_WALLET_7702`, `REGULAR_TIMING`.
Volume and drop-count labels alone describe heavy collectors, and plenty of real people mint a lot.
A collection's own owner airdropping to holders is never a farm. Check `COLLECTION_OWNER` before you say anything.
Recommend blocking only STRONG_SIGNAL.

## Output format
For each wallet:
```
0xabc…  LEVEL 3 (STRONG_SIGNAL)
  - swept 41 NFTs to 0xsink… (fed by 212 wallets)   tx: https://robin.etherscan.io/tx/0x…
  - minted 9 collections in 24h, 45 tokens
  Recommendation: exclude from free allowlist. Can request review via MintFarmRegistry.requestReview().
```

## Rules
- Facts first. Every claim gets a tx or address link.
- Never name or shame wallets publicly. The list is for blocking mints, not for call-outs.
- Use the explorer at `robin.etherscan.io` or `robinhoodchain.blockscout.com`. Blockscout needs a Chrome User-Agent.
- Public RPC rate limits: about 5 calls per batch and 4 per second, then back off on 429.
