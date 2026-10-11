// SPDX-License-Identifier: MIT
pragma solidity ^0.8.17;

/// @title MintFarmRegistry
/// @notice Public, on-chain list of wallets flagged for mint farming on Robinhood Chain.
///         Any collection can read `level(wallet)` and refuse public mints at or above a threshold.
///
/// Levels are EVIDENCE TIERS, not verdicts:
///   0 = not listed
///   1 = signal      (one heuristic fired, e.g. heavy minting)
///   2 = likely      (several independent signals)
///   3 = confirmed   (pattern proven on-chain: mint-and-sweep into a shared sink, operator minting
///                    for other wallets, or contract / EIP-7702 batch minting)
/// Each batch carries an evidence URI + content hash so anyone can check why a wallet is listed.
/// Any listed wallet can ask for review; curators can unlist. Nothing here moves funds or tokens.
contract MintFarmRegistry {
    address public owner;
    mapping(address => bool) public curator;
    mapping(address => uint8) public level;
    mapping(address => uint32) public batchOf;      // which evidence batch listed the wallet
    mapping(address => bool) public reviewRequested;

    struct Batch {
        bytes32 evidenceHash; // keccak256 of the evidence JSON
        string evidenceURI;   // where the JSON lives (site, IPFS, GitHub)
        uint64 at;
    }
    Batch[] public batches;

    event CuratorSet(address indexed curator, bool enabled);
    event BatchPublished(uint32 indexed batchId, bytes32 evidenceHash, string evidenceURI, uint256 count);
    event Listed(address indexed wallet, uint8 level, uint32 indexed batchId);
    event ReviewRequested(address indexed wallet);
    event OwnershipTransferred(address indexed from, address indexed to);

    error NotOwner();
    error NotCurator();
    error LengthMismatch();
    error BadLevel();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyCurator() {
        if (!curator[msg.sender] && msg.sender != owner) revert NotCurator();
        _;
    }

    constructor() {
        owner = msg.sender;
        emit OwnershipTransferred(address(0), msg.sender);
        batches.push(Batch(bytes32(0), "", uint64(block.timestamp))); // batch 0 = none
    }

    function transferOwnership(address to) external onlyOwner {
        emit OwnershipTransferred(owner, to);
        owner = to;
    }

    function setCurator(address c, bool enabled) external onlyOwner {
        curator[c] = enabled;
        emit CuratorSet(c, enabled);
    }

    /// @notice Publish a batch of flags. levels[i] = 0 unlists wallets[i].
    function publish(address[] calldata wallets, uint8[] calldata levels, bytes32 evidenceHash, string calldata evidenceURI)
        external
        onlyCurator
        returns (uint32 id)
    {
        if (wallets.length != levels.length) revert LengthMismatch();
        id = uint32(batches.length);
        batches.push(Batch(evidenceHash, evidenceURI, uint64(block.timestamp)));
        for (uint256 i; i < wallets.length; ++i) {
            uint8 l = levels[i];
            if (l > 3) revert BadLevel();
            level[wallets[i]] = l;
            batchOf[wallets[i]] = l == 0 ? 0 : id;
            if (l == 0) reviewRequested[wallets[i]] = false;
            emit Listed(wallets[i], l, id);
        }
        emit BatchPublished(id, evidenceHash, evidenceURI, wallets.length);
    }

    /// @notice A listed wallet asks curators to look again (free, no deposit).
    function requestReview() external {
        if (level[msg.sender] == 0) return;
        reviewRequested[msg.sender] = true;
        emit ReviewRequested(msg.sender);
    }

    /// @notice Highest level among two addresses (use for msg.sender + tx.origin).
    function levelOf(address a, address b) external view returns (uint8) {
        uint8 x = level[a];
        uint8 y = level[b];
        return x > y ? x : y;
    }

    function batchCount() external view returns (uint256) {
        return batches.length;
    }
}
