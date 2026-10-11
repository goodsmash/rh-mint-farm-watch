# Copy-paste prompts (Bankr / any agent)

Every prompt below forces the agent to **prove** what it did by reading the contract back.
An agent claiming "deployed with anti-bot" means nothing until `guard()` is read on-chain.

---

## 1. Deploy a fair free mint (anti-farm on)

```
@bankrbot Deploy a new NFT collection on Robinhood Chain (4663) using Net Protocol
(https://netprotocol.app/skill.md), extending NetIntegratedERC721A.
Name: <NAME>  Symbol: <SYM>  Price: 0 ETH (free, gas only, do not set a price)
Max supply: <N>  Max per wallet: <K>  Creator reserve: <R> (premint all to my wallet after deploy)

Anti-farm, required:
- public mint goes to msg.sender only
- reject if msg.sender != tx.origin or msg.sender has code (blocks batch contracts + EIP-7702)
- a wallet that public-minted cannot transfer this collection for 6 hours (stops mint-and-sweep)
- 30 s cooldown per wallet, max 10 tokens per second collection-wide, use block.timestamp
- settings public and frozen once the sale opens

Art: <brief>
Verify on the explorer. Reply with address, deploy tx, explorer link, and the values of
guard(), saleStart(), maxMintsPerWallet() and price() read from the deployed contract.
```

## 2. Deploy with a shared farm blocklist

Add to prompt 1:
```
Also read MintFarmRegistry at <REGISTRY> with a low-level staticcall to levelOf(address,address)
that FAILS OPEN (no code / revert = allow). Refuse public mints when level >= 2.
```

## 3. Check a wallet before an airdrop / giveaway

```
Check these Robinhood Chain (4663) wallets for mint-farm patterns. For each, report: nonce,
whether it has code (0xef0100 = EIP-7702), how many NFTs it minted in the last 24h and across how
many collections, whether another wallet paid for its mints, and whether it sent minted NFTs on
to a wallet that 3+ other minters also send to. Give a tx link for every claim. Do not label
anyone a bot without a tx that shows the pattern.
<addresses>
```

## 4. Mint a free drop for me, the fair way

```
@bankrbot Mint 1 of <collection address> on Robinhood Chain to my own wallet. First read
price(), maxMintsPerWallet(), saleOpen() and guard() and tell me the values. Only mint if price
is 0. Do not mint to any other address and do not use a batch/multicall contract.
```

## 5. Audit a collection's mint after it sells out

```
For collection <address> on Robinhood Chain (4663): list every mint (Transfer from 0x0).
Report unique minters, the share the top 10 wallets took, how many mint txs sent tokens to a
different wallet than the payer, and the top 5 wallets that minted tokens were sent to within
24h. Link txs. Compare against the chain-wide 24h numbers in https://goodsmash.github.io/rh-mint-farm-watch/lookup.json.
```

---

## What these prompts deliberately avoid
- No "airdrop to these 500 wallets" in the public path. That is exactly the farm pattern.
- No price talk, no "guaranteed", no floor claims.
- The agent never asks for your private key. Bankr signs with its own custodial wallet; owner
  actions on contracts you own are signed by you.
