# Anti-farm mint contracts (Foundry)

Nothing here is deployed by this repo. Read the code, run the tests, deploy yourself.

| Contract | What it does |
|---|---|
| `src/NetIntegratedERC721A.sol` | ERC721A base that registers the collection with Net Protocol (`0x00000000B24D62781dB359b07880a105cD0b64e6`, live on chain 4663). On a chain without Net Protocol, mints will fail. |
| `src/FairMintNetERC721A.sol` | Reusable anti-farm layer on top. Public mint always goes to `msg.sender` (no minting for 50 other wallets). Rejects contracts and EIP-7702 delegated wallets. Per-wallet cooldown and a collection-wide per-block cap. Optional transfer lock after mint (breaks mint-then-sweep, also delays real buyers listing). Optional EIP-712 signed mint pass. Optional blocklist / registry check. All settings are public and lock when the sale opens. |
| `src/MintFarmRegistry.sol` | On-chain farm list any collection can check before a mint. Wallets are listed with an evidence tier and can call `requestReview()`. If the registry is missing or reverts, minting still works (fails open). |
| `src/Tunki.sol` | Example collection: TUNKI, a fully on-chain 32x32 SVG Andean cock-of-the-rock with an animated crest bob. Free mint, 3,000 supply, 5 per wallet. |

## Build and test

```bash
cd contracts
forge install chiru-labs/ERC721A@6f8a82a7b2833ad8b2fc7b54349281143a731fdd --no-git
forge install vectorized/solady@acd959aa4bd04720d640bf4e6a5c71037510cc4b --no-git
forge install foundry-rs/forge-std@0258fe875e1d8e207c1eb7175e542ea32356773c --no-git
forge test
python tools/render.py        # optional: renders previews/*.png + sheet.png (needs cairosvg + Pillow)
```

`via_ir = true` is required. 25 tests, including a tokenURI gas check (about 15.3M gas worst case, under the 30M eth_call ceiling).

## Honest limits

- A fresh wallet costs a fraction of a cent on this chain. Caps and blocklists are speed bumps. The signed mint pass and the transfer lock are what actually change a farm's economics.
- The transfer lock also stops real minters from listing for its duration. Say so on your mint page.
- Not audited. Rehearse on a fork before you deploy.
