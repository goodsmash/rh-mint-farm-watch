---
name: fair-free-mint
description: Use when deploying a FREE or cheap NFT mint on Robinhood Chain (4663) and you want it to reach people instead of mint farms. Gives the contract settings, the deploy prompt for an agent (Bankr / Net Protocol), and the post-launch checks.
metadata: {"chain":"robinhood-4663","requires":{"bins":["forge"]}}
---

# Fair Free Mint (Robinhood Chain)

Free mints on Robinhood Chain get farmed. In a 24-hour on-chain audit (Oct 2026):
- **273,038 NFTs minted** to 30,601 wallets. The **top 500 wallets took 41%**.
- **373 transactions minted to several wallets at once** (one payer, many recipients).
- Fresh wallets mint and then **sweep everything into one collector wallet**.
- Gas is ~0.02 gwei, so 1,000 throwaway wallets cost almost nothing.

A per-wallet cap alone does not stop this. It only makes the farm use more wallets.

## What actually stops farms (contract level)

Use `FairMintNetERC721A` (extends Net Protocol's `NetIntegratedERC721A`).
Source: `tunki-nft/src/FairMintNetERC721A.sol`.

| Setting | Stops | Recommended for a free mint |
|---|---|---|
| `eoaOnly` | Contract batch-minters and EIP-7702 delegated wallets (`0xef0100…` code) | `true` |
| Public mint always goes to `msg.sender` | One payer minting to 50 recipient wallets | built in |
| `transferLock` | Mint-then-sweep to one collector wallet. Lock covers ALL of the wallet's tokens, including via approved operators. | `6 hours` (max 24h) |
| `walletCooldown` | Scripted repeat mints from the same wallet | `30` seconds |
| `perSecondCap` | A swarm firing hundreds of wallets in the same second | `10` tokens / second |
| `minBalanceWei` | Wallets funded with exactly one mint's worth of gas | `0` or a small amount, e.g. `0.0002 ether` |
| `passSigner` | Everything above at scale. The mint requires an EIP-712 pass from your site after a human check. | Use for high-demand drops |
| `setFarmRegistry(reg, 2)` | Wallets already flagged on the shared `MintFarmRegistry` | Level 2 (likely) or 3 (confirmed only) |
| `setBlocked([...])` | Your own pre-sale blocklist | Editable until 1 hour after sale opens |

Settings are public and **freeze when the sale opens**. The creator reserve (`mintToCreator`) is capped and bypasses the guards by design.

Robinhood Chain is Arbitrum Nitro: `block.number` is the L1 block and `prevrandao` is constant. All limits use `block.timestamp`. The art seed mixes `tx.origin`, timestamp, gas, and a running hash.

## Honest limits

- A determined farmer with many funded wallets that each wait out the lock can still mint. These settings raise the cost from ~free to real time and gas, and make the pattern visible.
- `transferLock` also delays real buyers listing for 6 hours. Say that on the mint page.
- `minBalanceWei` excludes brand-new real users with empty wallets. Keep it off for "anyone can mint".
- The registry is evidence tiers, not verdicts. Any listed wallet can call `requestReview()`.

## Deploy prompt for an agent (Bankr / Net Protocol)

Paste and fill in. Keep the anti-farm block. It is the part default deploys skip.

```
Deploy a new NFT collection on Robinhood Chain (chain id 4663). Use Net Protocol
(https://netprotocol.app/skill.md) and extend NetIntegratedERC721A.

Name: <NAME>   Symbol: <SYMBOL>
Mint price: 0 ETH (free, gas only). Do not set a price.
Max supply: <N>. Max mints per wallet: <K>. Creator reserve: <R>, premint all <R> to my wallet right after deploy.

Anti-farm (required, do not drop these to save gas):
- Public mint mints to msg.sender only. No mintTo / airdrop-to-others in the public path.
- Reject callers where msg.sender != tx.origin OR msg.sender.code.length != 0
  (blocks contract batch minters and EIP-7702 delegated wallets).
- Transfer lock: a wallet that public-minted cannot transfer any token of this collection
  for 6 hours (blocks mint-and-sweep into one collector wallet).
- Per-wallet cooldown 30 seconds. Collection-wide cap 10 tokens per block.timestamp second.
- Use block.timestamp, not block.number (Robinhood Chain is Arbitrum Nitro).
- Optional: read MintFarmRegistry at <REGISTRY_ADDRESS> via a low-level staticcall that FAILS OPEN,
  and refuse mints when levelOf(msg.sender, tx.origin) >= 2.
- All guard settings public and frozen once the sale opens.

Art: <ART BRIEF>
Verify the contract on the explorer, then reply with contract address, deploy tx, and explorer link.
Then show me guard() and saleStart() read from the deployed contract as proof the settings are live.
```

## After launch (prove it worked)

```bash
cd rh-mint-farm-watch
python rhwatch.py scan --hours 24   # pulls every mint on the chain, resumable
python phase_d.py --hours 24  # wallet age / code / balance
python analyze.py --hours 24  # scores wallets, writes data/24h/report.json

```

Open `docs/index.html` (or https://goodsmash.github.io/rh-mint-farm-watch/) and filter Collections by your contract address. Compare the
top-500 share and the multi-recipient count against the chain-wide numbers above.

## Rules
- The agent never holds keys or signs mainnet transactions. The owner signs.
- Rehearse on a fork first: `anvil --fork-url https://rpc.mainnet.chain.robinhood.com --chain-id 4663`.
- Net Protocol's base uses `try NET.sendMessageViaApp`. On a chain without Net deployed, that reverts
  before the catch and **bricks every mint**. Net is live on 4663 (`0x00000000B24D62781dB359b07880a105cD0b64e6`).
  Check `eth_getCode` before deploying anywhere else.
