// SPDX-License-Identifier: MIT
pragma solidity ^0.8.17;

import { ERC721A } from "erc721a/contracts/ERC721A.sol";
import { LibString } from "solady/utils/LibString.sol";

interface INet {
    function sendMessageViaApp(
        address sender,
        string calldata text,
        string calldata topic,
        bytes calldata data
    ) external;
}

/// @title NetIntegratedERC721A
/// @notice ERC721A base that auto-posts mint & transfer activity to Net Protocol.
/// @dev The collection contract IS the Net "app": messages it emits are indexed
///      under this contract's address. Extend this contract and implement the
///      generative art() + tokenURI().
abstract contract NetIntegratedERC721A is ERC721A {
    using LibString for uint256;
    using LibString for address;

    /// @notice Net Protocol contract — same address on all supported chains.
    INet public constant NET = INet(0x00000000B24D62781dB359b07880a105cD0b64e6);

    string internal constant TOPIC_MINT = "mint";
    string internal constant TOPIC_TRANSFER = "transfer";
    string internal constant TOPIC_BURN = "burn";

    /// @notice Mint price per token, in wei.
    uint256 public immutable price;
    /// @notice Hard cap on total supply. 0 = unlimited.
    uint256 public immutable maxSupply;
    /// @notice Max tokens a single wallet may mint via public mint(). 0 = unlimited.
    uint256 public immutable maxMintsPerWallet;
    /// @notice Max tokens the deployer may ever mint via mintToCreator(). 0 = none.
    uint256 public immutable creatorReserve;
    /// @notice Tokens minted so far via mintToCreator().
    uint256 public creatorMinted;

    address internal immutable _deployer;

    /// @notice Per-token entropy for generative art.
    mapping(uint256 => bytes32) internal _tokenToSeed;

    error IncorrectPayment();
    error MaxSupplyReached();
    error MaxMintsPerWalletReached();
    error CreatorReserveExceeded();
    error NotDeployer();

    modifier onlyDeployer() {
        if (msg.sender != _deployer) revert NotDeployer();
        _;
    }

    constructor(
        string memory name_,
        string memory symbol_,
        uint256 price_,
        uint256 maxSupply_,
        uint256 maxMintsPerWallet_,
        uint256 creatorReserve_
    ) ERC721A(name_, symbol_) {
        _deployer = msg.sender;
        price = price_;
        maxSupply = maxSupply_;
        maxMintsPerWallet = maxMintsPerWallet_;
        creatorReserve = creatorReserve_;
    }

    /// @dev Token IDs start at 1.
    function _startTokenId() internal pure virtual override returns (uint256) {
        return 1;
    }

    // ---------------------------------------------------------------- minting

    /// @notice Public paid mint.
    function mint(uint256 amount) external payable {
        if (msg.value != amount * price) revert IncorrectPayment();
        if (
            maxMintsPerWallet != 0 &&
            _numberMinted(msg.sender) + amount > maxMintsPerWallet
        ) revert MaxMintsPerWalletReached();

        _mintSeeded(msg.sender, amount);
    }

    /// @notice Free premint controlled by the deployer, capped at creatorReserve
    ///         over the contract's lifetime (across all calls).
    /// @dev Not payment-gated and not subject to maxMintsPerWallet, but still
    ///      respects maxSupply. The reserve is immutable, so buyers can read
    ///      exactly how many free tokens the deployer can ever mint. Routes
    ///      through _afterTokenTransfers, so the premint is posted to Net like
    ///      any other mint (fully transparent).
    function mintToCreator(uint256 amount, address to) external onlyDeployer {
        if (creatorMinted + amount > creatorReserve) revert CreatorReserveExceeded();
        creatorMinted += amount;
        _mintSeeded(to, amount);
    }

    /// @dev Shared mint mechanic: supply check, seed, mint. Callers gate
    ///      access/payment before calling.
    function _mintSeeded(address to, uint256 amount) private {
        _enforceSupply(amount);
        _seed(_nextTokenId(), amount);
        _mint(to, amount);
    }

    function _enforceSupply(uint256 amount) internal view {
        if (maxSupply != 0 && _totalMinted() + amount > maxSupply) {
            revert MaxSupplyReached();
        }
    }

    /// @dev Assign per-token seeds. Override for a different entropy source.
    function _seed(uint256 startTokenId, uint256 amount) internal virtual {
        unchecked {
            for (uint256 i; i < amount; ++i) {
                _tokenToSeed[startTokenId + i] =
                    keccak256(abi.encodePacked(block.prevrandao, startTokenId + i));
            }
        }
    }

    // ------------------------------------------------------------ withdrawals

    /// @notice Withdraw collected ETH to the deployer.
    function withdraw() external {
        (bool ok, ) = _deployer.call{ value: address(this).balance }("");
        require(ok);
    }

    // ------------------------------------------------------- Net integration

    /// @dev Fires once per batch for mint (from == 0), transfer, and burn
    ///      (to == 0). All transfer paths (transferFrom + both safeTransferFrom)
    ///      route through here — this is why we DON'T override transferFrom.
    function _afterTokenTransfers(
        address from,
        address to,
        uint256 startTokenId,
        uint256 quantity
    ) internal virtual override {
        uint256 endTokenId = startTokenId + quantity - 1;

        address msgSender;
        string memory topic;
        string memory text;
        if (from == address(0)) {
            msgSender = to;
            topic = TOPIC_MINT;
            text = _mintText(to, startTokenId, endTokenId);
        } else if (to == address(0)) {
            msgSender = from;
            topic = TOPIC_BURN;
            text = _burnText(from, startTokenId, endTokenId);
        } else {
            msgSender = from;
            topic = TOPIC_TRANSFER;
            text = _transferText(from, to, startTokenId, endTokenId);
        }

        // Best-effort: a Net revert or out-of-gas must NEVER brick a mint/transfer/burn.
        try NET.sendMessageViaApp(msgSender, text, topic, "") {} catch {}
    }

    /// @dev Keep short — text length is the gas-scaling part of the Net write.
    function _mintText(address to, uint256 startId, uint256 endId)
        internal
        view
        virtual
        returns (string memory)
    {
        return string.concat(
            "Minted #", startId.toString(), "-#", endId.toString(),
            " to ", to.toHexString()
        );
    }

    function _transferText(address from, address to, uint256 startId, uint256 endId)
        internal
        view
        virtual
        returns (string memory)
    {
        return string.concat(
            "Transferred #", startId.toString(), "-#", endId.toString(),
            " from ", from.toHexString(), " to ", to.toHexString()
        );
    }

    function _burnText(address from, uint256 startId, uint256 endId)
        internal
        view
        virtual
        returns (string memory)
    {
        return string.concat(
            "Burned #", startId.toString(), "-#", endId.toString(),
            " by ", from.toHexString()
        );
    }
}
