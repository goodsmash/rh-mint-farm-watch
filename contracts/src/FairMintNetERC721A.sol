// SPDX-License-Identifier: MIT
pragma solidity ^0.8.17;

import { NetIntegratedERC721A } from "./NetIntegratedERC721A.sol";
import { EIP712 } from "solady/utils/EIP712.sol";
import { ECDSA } from "solady/utils/ECDSA.sol";

/// @title FairMintNetERC721A
/// @notice Anti-mint-farm layer on top of Net Protocol's NetIntegratedERC721A (kept verbatim).
///
/// Built from what an on-chain audit of Robinhood Chain (4663) mints actually showed:
///   - one operator paying gas and minting to many recipient wallets      -> public mint always mints to msg.sender (base)
///   - contracts / EIP-7702 delegated wallets batch-minting                 -> eoaOnly: tx.origin == msg.sender AND no code
///   - fresh throwaway wallets that mint then sweep to one sink wallet      -> transferLock: a wallet that minted cannot move
///                                                                             ANY token of this collection for N seconds
///   - many wallets firing in the same instant with identical gas           -> perSecondCap + walletCooldown
///   - all of the above at scale                                            -> optional EIP-712 mint pass from a human check
///   - wallets already known to farm                                        -> pre-sale blocklist (public, evented)
///
/// Robinhood Chain is an Arbitrum Nitro chain: `block.number` is the L1 block number and
/// `block.prevrandao` is constant. All rate limits here therefore use `block.timestamp`, and the
/// art seed mixes the minter, timestamp, and a running hash rather than trusting prevrandao.
///
/// Every setting is public. Settings can only be changed BEFORE the sale opens; after that they
/// are frozen. The blocklist can be edited until one hour after the sale opens. Creator premint
/// (mintToCreator) bypasses the guards by design and stays capped by the immutable creatorReserve.
abstract contract FairMintNetERC721A is NetIntegratedERC721A, EIP712 {
    struct Guard {
        bool eoaOnly;            // msg.sender == tx.origin && msg.sender.code.length == 0
        uint32 walletCooldown;   // seconds between two mints from the same wallet
        uint16 perSecondCap;     // max tokens minted collection-wide in one second (0 = off)
        uint32 transferLock;     // seconds a minting wallet cannot transfer tokens out (max 24h)
        uint96 minBalanceWei;    // minter must hold at least this much ETH (0 = off)
        address passSigner;      // non-zero => only mintWithPass works
    }

    Guard public guard;
    /// @notice Unix time the public sale opens. 0 = not scheduled (closed).
    uint64 public saleStart;
    mapping(address => uint64) public lastMintAt;
    mapping(uint256 => uint16) public mintedInSecond;
    mapping(address => bool) public blocked;
    bytes32 private _entropy;
    /// @notice Optional shared MintFarmRegistry. 0 = off. Mints refused when levelOf(minter, origin) >= farmBlockLevel.
    address public farmRegistry;
    uint8 public farmBlockLevel;

    uint32 public constant MAX_TRANSFER_LOCK = 24 hours;
    uint32 public constant BLOCKLIST_GRACE = 1 hours;
    bytes32 public constant PASS_TYPEHASH = keccak256("MintPass(address minter,uint256 amount,uint256 deadline)");

    event GuardSet(Guard guard);
    event SaleScheduled(uint64 saleStart);
    event Blocked(address indexed account, bool blocked);
    event FarmRegistrySet(address registry, uint8 blockLevel);

    error SaleNotOpen();
    error SaleAlreadyOpen();
    error ContractOrDelegatedCaller();
    error WalletCooldown();
    error BlockBusy();
    error BalanceTooLow();
    error PassRequired();
    error BadPass();
    error PassExpired();
    error BlockedAccount();
    error TransferLocked();
    error LockTooLong();
    error BlocklistFrozen();
    error UnexpectedMintPath();
    error FlaggedFarmWallet();

    constructor(Guard memory g) {
        if (g.transferLock > MAX_TRANSFER_LOCK) revert LockTooLong();
        guard = g;
        emit GuardSet(g);
    }

    // ------------------------------------------------------------------ admin (pre-sale only)

    function saleOpen() public view returns (bool) {
        return saleStart != 0 && block.timestamp >= saleStart;
    }

    function setGuard(Guard calldata g) external onlyDeployer {
        if (saleOpen()) revert SaleAlreadyOpen();
        if (g.transferLock > MAX_TRANSFER_LOCK) revert LockTooLong();
        guard = g;
        emit GuardSet(g);
    }

    /// @notice Schedule the sale. Pass block.timestamp (or 0 -> now) to open immediately.
    function openSale(uint64 at) external onlyDeployer {
        if (saleOpen()) revert SaleAlreadyOpen();
        saleStart = at == 0 ? uint64(block.timestamp) : at;
        emit SaleScheduled(saleStart);
    }

    /// @notice Point at a shared farm registry (pre-sale only). blockLevel 3 = confirmed only, 2 = likely+.
    function setFarmRegistry(address registry, uint8 blockLevel) external onlyDeployer {
        if (saleOpen()) revert SaleAlreadyOpen();
        farmRegistry = registry;
        farmBlockLevel = blockLevel;
        emit FarmRegistrySet(registry, blockLevel);
    }

    /// @dev Low-level staticcall: a missing / reverting registry FAILS OPEN so it can never brick the mint.
    function _farmLevel(address a, address b) internal view returns (uint8 l) {
        address r = farmRegistry;
        if (r == address(0) || r.code.length == 0) return 0;
        (bool ok, bytes memory ret) = r.staticcall{ gas: 30_000 }(abi.encodeWithSignature("levelOf(address,address)", a, b));
        if (ok && ret.length >= 32) l = uint8(abi.decode(ret, (uint256)));
    }

    function setBlocked(address[] calldata accounts, bool isBlocked) external onlyDeployer {
        if (saleStart != 0 && block.timestamp >= uint256(saleStart) + BLOCKLIST_GRACE) revert BlocklistFrozen();
        for (uint256 i; i < accounts.length; ++i) {
            blocked[accounts[i]] = isBlocked;
            emit Blocked(accounts[i], isBlocked);
        }
    }

    // ------------------------------------------------------------------ signed-pass mint

    /// @notice Mint with an EIP-712 pass issued by `guard.passSigner` (e.g. after a human check).
    /// @dev The pass binds the minter, amount cap, deadline, this contract and the chain id.
    ///      Replay is bounded by maxMintsPerWallet, so no per-pass nonce is needed.
    function mintWithPass(uint256 amount, uint256 maxAmount, uint256 deadline, bytes calldata sig) external payable {
        Guard memory g = guard;
        if (g.passSigner == address(0)) revert BadPass();
        if (block.timestamp > deadline) revert PassExpired();
        bytes32 digest = _hashTypedData(keccak256(abi.encode(PASS_TYPEHASH, msg.sender, maxAmount, deadline)));
        if (ECDSA.recoverCalldata(digest, sig) != g.passSigner) revert BadPass();
        if (_numberMinted(msg.sender) + amount > maxAmount) revert MaxMintsPerWalletReached();
        if (msg.value != amount * price) revert IncorrectPayment();
        if (maxMintsPerWallet != 0 && _numberMinted(msg.sender) + amount > maxMintsPerWallet) {
            revert MaxMintsPerWalletReached();
        }
        _enforceSupply(amount);
        _seed(_nextTokenId(), amount);
        _mint(msg.sender, amount); // guards run in _beforeTokenTransfers
    }

    function _domainNameAndVersion() internal view virtual override returns (string memory, string memory) {
        return (name(), "1");
    }

    /// @notice Hash a pass off-chain signers must sign (helper for sites/tests).
    function passDigest(address minter, uint256 maxAmount, uint256 deadline) external view returns (bytes32) {
        return _hashTypedData(keccak256(abi.encode(PASS_TYPEHASH, minter, maxAmount, deadline)));
    }

    // ------------------------------------------------------------------ guards

    function _beforeTokenTransfers(address from, address to, uint256 startTokenId, uint256 quantity)
        internal
        virtual
        override
    {
        super._beforeTokenTransfers(from, to, startTokenId, quantity);
        if (from == address(0)) {
            bytes4 s = msg.sig;
            if (s == this.mintToCreator.selector) return; // creator reserve: capped, transparent
            if (s == this.mint.selector) {
                if (guard.passSigner != address(0)) revert PassRequired();
            } else if (s != this.mintWithPass.selector) {
                revert UnexpectedMintPath();
            }
            _checkPublicMint(to, quantity);
        } else if (to != address(0)) {
            uint32 lock = guard.transferLock;
            if (lock != 0 && block.timestamp < uint256(lastMintAt[from]) + lock) revert TransferLocked();
        }
    }

    function _checkPublicMint(address minter, uint256 quantity) internal {
        if (!saleOpen()) revert SaleNotOpen();
        Guard memory g = guard;
        if (blocked[minter] || blocked[tx.origin]) revert BlockedAccount();
        if (farmBlockLevel != 0 && _farmLevel(minter, tx.origin) >= farmBlockLevel) revert FlaggedFarmWallet();
        if (g.eoaOnly && (minter != tx.origin || minter.code.length != 0)) revert ContractOrDelegatedCaller();
        uint64 last = lastMintAt[minter];
        if (g.walletCooldown != 0 && last != 0 && block.timestamp < uint256(last) + g.walletCooldown) {
            revert WalletCooldown();
        }
        if (g.minBalanceWei != 0 && minter.balance < g.minBalanceWei) revert BalanceTooLow();
        if (g.perSecondCap != 0) {
            uint256 n = mintedInSecond[block.timestamp] + quantity;
            if (n > g.perSecondCap) revert BlockBusy();
            mintedInSecond[block.timestamp] = uint16(n);
        }
        lastMintAt[minter] = uint64(block.timestamp);
    }

    /// @dev prevrandao is constant on Arbitrum-based chains; mix in more state.
    function _seed(uint256 startTokenId, uint256 amount) internal virtual override {
        bytes32 e = keccak256(abi.encodePacked(_entropy, tx.origin, block.timestamp, gasleft(), startTokenId));
        _entropy = e;
        unchecked {
            for (uint256 i; i < amount; ++i) {
                _tokenToSeed[startTokenId + i] = keccak256(abi.encodePacked(e, startTokenId + i));
            }
        }
    }
}
