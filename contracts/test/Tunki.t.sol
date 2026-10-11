// SPDX-License-Identifier: MIT
pragma solidity ^0.8.17;

import "forge-std/Test.sol";
import { Tunki } from "../src/Tunki.sol";
import { FairMintNetERC721A } from "../src/FairMintNetERC721A.sol";
import { NetIntegratedERC721A } from "../src/NetIntegratedERC721A.sol";
import { LibString } from "solady/utils/LibString.sol";
import { MintFarmRegistry } from "../src/MintFarmRegistry.sol";
import { Base64 } from "solady/utils/Base64.sol";

contract NetStub {
    uint256 public count;
    function sendMessageViaApp(address, string calldata, string calldata, bytes calldata) external { count++; }
}

contract BatchMinter {
    function go(Tunki t) external { t.mint(1); }
}

contract TunkiTest is Test {
    Tunki t;
    address creator = address(0xC0FFEE);
    address alice = address(0xA11CE);
    address bob = address(0xB0B);
    uint256 signerPk = 0xA11CE5;

    function setUp() public {
        vm.warp(1_800_000_000);
        vm.etch(0x00000000B24D62781dB359b07880a105cD0b64e6, address(new NetStub()).code);
        t = new Tunki();
    }

    uint256 now_ = 1_800_000_000;
    function _tick(uint256 d) internal { now_ += d; vm.warp(now_); }
    function _open() internal { t.openSale(0); }

    function _mint(address w, uint256 n) internal {
        vm.prank(w, w);
        t.mint(n);
    }

    // ---------------------------------------------------------------- base behaviour
    function test_config() public view {
        assertEq(t.name(), "TUNKI");
        assertEq(t.symbol(), "TUNKI");
        assertEq(t.price(), 0);
        assertEq(t.maxSupply(), 3000);
        assertEq(t.maxMintsPerWallet(), 5);
        assertEq(t.creatorReserve(), 20);
    }

    function test_creatorPremintBeforeSaleAndBypassesGuards() public {
        t.mintToCreator(20, creator);
        assertEq(t.balanceOf(creator), 20);
        vm.expectRevert(NetIntegratedERC721A.CreatorReserveExceeded.selector);
        t.mintToCreator(1, creator);
    }

    function test_onlyDeployerPremints() public {
        vm.prank(alice);
        vm.expectRevert(NetIntegratedERC721A.NotDeployer.selector);
        t.mintToCreator(1, alice);
    }

    function test_publicMintClosedUntilOpen() public {
        vm.prank(alice, alice);
        vm.expectRevert(FairMintNetERC721A.SaleNotOpen.selector);
        t.mint(1);
    }

    function test_freeMintAndWalletCap() public {
        _open();
        _mint(alice, 5);
        assertEq(t.balanceOf(alice), 5);
        _tick(60);
        vm.prank(alice, alice);
        vm.expectRevert(NetIntegratedERC721A.MaxMintsPerWalletReached.selector);
        t.mint(1);
    }

    function test_priceIsZero() public {
        _open();
        vm.deal(alice, 1 ether);
        vm.prank(alice, alice);
        vm.expectRevert(NetIntegratedERC721A.IncorrectPayment.selector);
        t.mint{ value: 1 }(1);
    }

    function test_supplyCap() public {
        _open();
        t.mintToCreator(20, creator);
        uint256 n;
        for (uint160 i = 1; t.totalSupply() < 3000; ++i) {
            address w = address(i + 0x10000);
            _tick(1);
            _mint(w, 5);
            n++;
        }
        assertEq(t.totalSupply(), 3000);
        _tick(1);
        vm.prank(alice, alice);
        vm.expectRevert(NetIntegratedERC721A.MaxSupplyReached.selector);
        t.mint(1);
    }

    // ---------------------------------------------------------------- anti-farm guards
    function test_blocksContractCaller() public {
        _open();
        BatchMinter b = new BatchMinter();
        vm.prank(alice, alice);
        vm.expectRevert(FairMintNetERC721A.ContractOrDelegatedCaller.selector);
        b.go(t);
    }

    function test_blocksEip7702DelegatedEoa() public {
        _open();
        vm.etch(alice, abi.encodePacked(hex"ef0100", address(0x63c0c19a282a1B52b07dD5a65b58948A07DAE32B)));
        vm.prank(alice, alice);
        vm.expectRevert(FairMintNetERC721A.ContractOrDelegatedCaller.selector);
        t.mint(1);
    }

    function test_walletCooldown() public {
        _open();
        _mint(alice, 1);
        vm.prank(alice, alice);
        vm.expectRevert(FairMintNetERC721A.WalletCooldown.selector);
        t.mint(1);
        _tick(30);
        _mint(alice, 1);
        assertEq(t.balanceOf(alice), 2);
    }

    function test_perSecondCap() public {
        _open();
        for (uint160 i = 1; i <= 2; ++i) _mint(address(i + 0x5000), 5); // 10 this second
        vm.prank(bob, bob);
        vm.expectRevert(FairMintNetERC721A.BlockBusy.selector);
        t.mint(1);
        _tick(1);
        _mint(bob, 1);
    }

    function test_transferLockBreaksMintAndSweep() public {
        _open();
        _mint(alice, 3);
        vm.prank(alice);
        vm.expectRevert(FairMintNetERC721A.TransferLocked.selector);
        t.transferFrom(alice, bob, 1);
        // approved operator (marketplace / sweeper) is equally blocked
        vm.prank(alice);
        t.setApprovalForAll(bob, true);
        vm.prank(bob);
        vm.expectRevert(FairMintNetERC721A.TransferLocked.selector);
        t.transferFrom(alice, bob, 2);
        _tick(6 hours);
        vm.prank(bob);
        t.transferFrom(alice, bob, 2);
        assertEq(t.ownerOf(2), bob);
    }

    function test_creatorTokensTransferFreely() public {
        t.mintToCreator(5, creator);
        vm.prank(creator);
        t.transferFrom(creator, bob, 1);
        assertEq(t.ownerOf(1), bob);
    }

    function test_blocklistAndFreeze() public {
        address[] memory a = new address[](1);
        a[0] = alice;
        t.setBlocked(a, true);
        _open();
        vm.prank(alice, alice);
        vm.expectRevert(FairMintNetERC721A.BlockedAccount.selector);
        t.mint(1);
        _tick(1 hours);
        vm.expectRevert(FairMintNetERC721A.BlocklistFrozen.selector);
        t.setBlocked(a, false);
    }

    function test_guardsFrozenAfterOpen() public {
        _open();
        (bool e, uint32 c, uint16 p, uint32 l, uint96 m, address s) = t.guard();
        vm.expectRevert(FairMintNetERC721A.SaleAlreadyOpen.selector);
        t.setGuard(FairMintNetERC721A.Guard(e, c, p, l, m, s));
    }

    function test_transferLockCapped() public {
        vm.expectRevert(FairMintNetERC721A.LockTooLong.selector);
        t.setGuard(FairMintNetERC721A.Guard(true, 0, 0, 25 hours, 0, address(0)));
    }

    function test_minBalance() public {
        t.setGuard(FairMintNetERC721A.Guard(true, 0, 0, 0, 0.0002 ether, address(0)));
        _open();
        vm.prank(alice, alice);
        vm.expectRevert(FairMintNetERC721A.BalanceTooLow.selector);
        t.mint(1);
        vm.deal(alice, 0.0002 ether);
        _mint(alice, 1);
    }

    function test_signedPass() public {
        address signer = vm.addr(signerPk);
        t.setGuard(FairMintNetERC721A.Guard(true, 0, 0, 0, 0, signer));
        _open();
        // plain mint refused
        vm.prank(alice, alice);
        vm.expectRevert(FairMintNetERC721A.PassRequired.selector);
        t.mint(1);
        uint256 dl = now_ + 600;
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(signerPk, t.passDigest(alice, 2, dl));
        bytes memory sig = abi.encodePacked(r, s, v);
        // bob cannot use alice's pass
        vm.prank(bob, bob);
        vm.expectRevert(FairMintNetERC721A.BadPass.selector);
        t.mintWithPass(1, 2, dl, sig);
        vm.prank(alice, alice);
        t.mintWithPass(2, 2, dl, sig);
        assertEq(t.balanceOf(alice), 2);
        // pass amount is a lifetime cap for that wallet
        vm.prank(alice, alice);
        vm.expectRevert(NetIntegratedERC721A.MaxMintsPerWalletReached.selector);
        t.mintWithPass(1, 2, dl, sig);
        // expired
        _tick(601);
        vm.prank(bob, bob);
        vm.expectRevert(FairMintNetERC721A.PassExpired.selector);
        t.mintWithPass(1, 2, dl, sig);
    }

    function test_sharedFarmRegistry() public {
        MintFarmRegistry reg = new MintFarmRegistry();
        address[] memory w = new address[](2);
        uint8[] memory l = new uint8[](2);
        w[0] = alice; l[0] = 3;
        w[1] = bob; l[1] = 1;
        reg.publish(w, l, keccak256("evidence"), "https://example.invalid/evidence.json");
        t.setFarmRegistry(address(reg), 2);
        _open();
        vm.prank(alice, alice);
        vm.expectRevert(FairMintNetERC721A.FlaggedFarmWallet.selector);
        t.mint(1);
        _mint(bob, 1); // level 1 (signal only) is below the threshold
        assertEq(t.balanceOf(bob), 1);
        // wallet can request review; curator unlists; mint then works
        vm.prank(alice);
        reg.requestReview();
        assertTrue(reg.reviewRequested(alice));
        address[] memory w2 = new address[](1);
        uint8[] memory l2 = new uint8[](1);
        w2[0] = alice;
        reg.publish(w2, l2, bytes32(0), "");
        _mint(alice, 1);
        assertEq(t.balanceOf(alice), 1);
    }

    function test_registryFailsOpen() public {
        t.setFarmRegistry(address(0xDEAD), 1); // no code -> ignored
        _open();
        _mint(alice, 1);
        assertEq(t.balanceOf(alice), 1);
    }

    function test_registryOnlyCurator() public {
        MintFarmRegistry reg = new MintFarmRegistry();
        address[] memory w = new address[](1);
        uint8[] memory l = new uint8[](1);
        vm.prank(alice);
        vm.expectRevert(MintFarmRegistry.NotCurator.selector);
        reg.publish(w, l, bytes32(0), "");
    }

    // ---------------------------------------------------------------- art + metadata
    function test_tokenURIValidAndGas() public {
        t.mintToCreator(20, creator);
        uint256 maxGas;
        for (uint256 id = 1; id <= 20; ++id) {
            uint256 g0 = gasleft();
            string memory u = t.tokenURI(id);
            uint256 used = g0 - gasleft();
            if (used > maxGas) maxGas = used;
            assertTrue(LibString.startsWith(u, "data:application/json;base64,"));
            string memory json = string(Base64.decode(LibString.slice(u, 29)));
            assertTrue(LibString.contains(json, '"attributes":'));
            assertTrue(LibString.contains(json, t.traits(id)));
            string memory svg = t.art(id);
            assertTrue(LibString.contains(svg, 'viewBox="0 0 32 32"'));
            assertTrue(LibString.contains(svg, "crispEdges"));
            assertTrue(LibString.contains(svg, "animateTransform"));
            assertFalse(LibString.contains(svg, "Gradient"));
            assertFalse(LibString.contains(svg, "<text"));
            assertFalse(LibString.contains(svg, "filter"));
        }
        emit log_named_uint("max tokenURI gas", maxGas);
        assertLt(maxGas, 30_000_000);
    }

    /// Documents a real hazard in the published Net base: on a chain WITHOUT the Net contract,
    /// `try NET.sendMessageViaApp` reverts (Solidity checks extcodesize before the call, outside the catch),
    /// so every mint bricks. Net IS live on Robinhood 4663, so TUNKI is unaffected there.
    function test_netMissingBricksMints_documented() public {
        vm.etch(0x00000000B24D62781dB359b07880a105cD0b64e6, "");
        vm.expectRevert();
        t.mintToCreator(1, creator);
    }

    function test_nonexistentReverts() public {
        vm.expectRevert();
        t.tokenURI(1);
    }

    /// renders previews/<id>.svg for tokens 1..48 (run with --match-test test_writePreviews)
    function test_writePreviews() public {
        t.mintToCreator(20, creator);
        _open();
        for (uint160 i = 1; i <= 7; ++i) {
            _tick(31);
            _mint(address(i * 7919 + 0x777), 4);
        }
        for (uint256 id = 1; id <= 48; ++id) {
            vm.writeFile(string.concat("previews/", LibString.toString(id), ".svg"), t.art(id));
            vm.writeFile(string.concat("previews/", LibString.toString(id), ".json"), t.traits(id));
        }
    }
}
