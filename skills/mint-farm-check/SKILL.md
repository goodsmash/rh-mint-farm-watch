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
   Each entry: `address, level (1 signal / 2 likely / 3 confirmed), score, signals[], mints, collections,
   sink (where it sweeps to), operator (who paid for its mints), cluster id`.
2. **On-chain registry** (when deployed): `MintFarmRegistry.level(address)`. Read-only, free.
3. **Live chain** for anything not in the list: `eth_getTransactionCount`, `eth_getCode`, `eth_getBalance`,
   and ERC-721 `Transfer` logs with `topic1 = 0x0` (mints) and `topic1 = wallet` (outflows).

## What each signal means (exact labels from analyze.py)
| Label | Meaning | Points |
|---|---|---|
| `FARM_SINK` | Collector wallet: received minted NFTs from 3+ different minting wallets in the window | 40 |
| `OPERATOR_FOR_OTHER_WALLETS` | Paid gas and minted to 3+ other wallets | 30 |
| `HEAVY_MINTER` / `HIGH_VOLUME` | 200+ / 50+ tokens in the window | 35 / 20 |
| `SPRAY_ALL_DROPS` / `MANY_DROPS` | Minted 25+ / 10+ different collections | 25 / 12 |
| `MACHINE_CADENCE` | 30+ mint txs with median gap under 20 s | 15 |
| `MINT_AND_SWEEP` | Sent on at least half of what it minted (5+ tokens) | 15 |
| `FEE_FINGERPRINT_SWARM` | Same collection + selector + maxFee + priority + gas limit as 5+ other senders | 15 |
| `MINTED_BY_SOMEONE_ELSE` | Received 5+ mints paid for by another wallet | 10 |
| `FRESH_THROWAWAY` | Nonce 15 or less and 5+ tokens | 10 |
| `CONTRACT_RECIPIENT` / `EIP7702_DELEGATED` | Has contract code / `0xef0100` delegation | 10 / 5 |
| `CLUSTER_MEMBER` | Belongs to a farm or operator cluster but no other signal fired | fixed 25 |

Tiers: **CONFIRMED_PATTERN** = score 70+, **LIKELY** = 40-69, **WATCH** = 20-39.
Registry levels map as CONFIRMED_PATTERN -> 3, LIKELY -> 2, WATCH -> 1.

Only `FARM_SINK`, `OPERATOR_FOR_OTHER_WALLETS`, `MINT_AND_SWEEP` and contract code are structural proof.
Volume and drop-count labels alone describe heavy collectors, and plenty of real people mint a lot.
Recommend blocking at LIKELY or above only when at least one structural label is present.

## Output format
For each wallet:
```
0xabc…  LEVEL 3 (confirmed)
  - swept 41 NFTs to 0xsink… (fed by 212 wallets)   tx: https://robin.etherscan.io/tx/0x…
  - minted 9 collections in 24h, 45 tokens
  Recommendation: exclude from free allowlist. Can request review via MintFarmRegistry.requestReview().
```

## Rules
- Facts first. Every claim gets a tx or address link.
- Never name or shame wallets publicly. The list is for blocking mints, not for call-outs.
- Use the explorer at `robin.etherscan.io` or `robinhoodchain.blockscout.com`. Blockscout needs a Chrome User-Agent.
- Public RPC rate limits: about 5 calls per batch and 4 per second, then back off on 429.
