// SPDX-License-Identifier: MIT
pragma solidity ^0.8.17;

import { NetIntegratedERC721A } from "./NetIntegratedERC721A.sol";
import { FairMintNetERC721A } from "./FairMintNetERC721A.sol";
import { LibString } from "solady/utils/LibString.sol";
import { LibPRNG } from "solady/utils/LibPRNG.sol";
import { Base64 } from "solady/utils/Base64.sol";
import { DynamicBufferLib } from "solady/utils/DynamicBufferLib.sol";

/// @title TUNKI
/// @notice Andean cock-of-the-rock (Rupicola peruvianus), male in lek, Peruvian cloud forest.
///         32x32, every drawn pixel a 1x1 <rect>, crispEdges, no gradients, no text.
///         One dynamic bit: the head/crest group bobs (lek dance) with a discrete animateTransform.
///         Traits and art both come from _traits(tokenId); decorative scatter uses a PRNG seeded
///         from the same token seed.
contract Tunki is FairMintNetERC721A {
    using LibString for uint256;
    using LibPRNG for LibPRNG.PRNG;
    using DynamicBufferLib for DynamicBufferLib.DynamicBuffer;

    struct Traits {
        uint8 hour;      // 0 Dawn Fog, 1 Shaft of Light, 2 Midday Rain, 3 Dusk, 4 Backlit
        uint8 fire;      // 0 Scarlet, 1 Flame, 2 Ember, 3 Blood Orange, 4 Molten
        uint8 crop;      // 0 Full Lek, 1 Close, 2 Plate Only
        bool halfPlate;  // flat-bottom crest
        bool tipped;     // head bob caught forward
        uint8 eye;       // 0 Ice, 1 Bone, 2 Pale Gold
        uint8 wing;      // 0 Jet, 1 Jet Scapular, 2 Sooted
        uint8 branch;    // 0 Wet Moss, 1 Thick Moss, 2 Vine Wrapped, 3 Bare Wet
        uint8 forest;    // 0 Deep Canopy, 1 Hanging Moss, 2 Swallowed, 3 Fern Wall, 4 Stream
        bool mirror;     // facing left
        int256 cx;       // crest centre
        int256 cy;
        int256 r;        // crest radius
        int256 bx;       // body centre
        int256 by;
        int256 rx;       // body radii
        int256 ry;
        int256 fy;       // branch top row
    }

    // palette slots
    uint8 internal constant SKY = 0;
    uint8 internal constant FAR = 1;
    uint8 internal constant NEAR = 2;
    uint8 internal constant LIGHT = 3;
    uint8 internal constant MOSS = 4;
    uint8 internal constant MIST = 5;
    uint8 internal constant BRANCH = 6;
    uint8 internal constant SHAFT = 7;
    uint8 internal constant FIRE = 8;
    uint8 internal constant FIRE_HI = 9;
    uint8 internal constant FIRE_LO = 10;
    uint8 internal constant WING = 11;
    uint8 internal constant SCAP = 12;
    uint8 internal constant IRIS = 13;
    uint8 internal constant PUPIL = 14;
    uint8 internal constant FEET = 15;
    uint8 internal constant WATER = 16;
    uint8 internal constant NCOL = 17;

    constructor()
        NetIntegratedERC721A("TUNKI", "TUNKI", 0, 3000, 5, 20)
        FairMintNetERC721A(
            Guard({
                eoaOnly: true,
                walletCooldown: 30,
                perSecondCap: 10,
                transferLock: 6 hours,
                minBalanceWei: 0,
                passSigner: address(0)
            })
        )
    {}

    // ------------------------------------------------------------------ traits

    function _traits(uint256 tokenId) internal view returns (Traits memory t) {
        LibPRNG.PRNG memory p;
        p.seed(uint256(_tokenToSeed[tokenId]));
        t.hour = uint8(p.uniform(5));
        t.fire = uint8(p.uniform(5));
        uint256 c = p.uniform(100);
        t.crop = c < 10 ? 2 : c < 32 ? 1 : 0;
        t.halfPlate = p.uniform(100) < 40;
        t.tipped = p.uniform(100) < 25;
        t.eye = uint8(p.uniform(3));
        t.wing = uint8(p.uniform(3));
        t.branch = uint8(p.uniform(4));
        t.forest = uint8(p.uniform(5));
        t.mirror = p.uniform(100) < 30;
        // layout: body anchored on the branch, crest sits forward over the head and eats the top half
        int256 fy; // branch top row
        if (t.crop == 0) {
            t.r = int256(6 + p.uniform(3));            // 6..8
            t.rx = 6;
            t.ry = int256(5 + p.uniform(2));
            fy = int256(26 + p.uniform(3));
            t.bx = int256(11 + p.uniform(4));
        } else if (t.crop == 1) {
            t.r = int256(8 + p.uniform(2));            // 8..9
            t.rx = 8;
            t.ry = 7;
            fy = 30;
            t.bx = int256(10 + p.uniform(3));
        } else {
            t.r = int256(10 + p.uniform(2));           // 10..11 : crest dominates, bird still on the branch
            t.rx = 7;
            t.ry = 5;
            fy = 30;
            t.bx = int256(9 + p.uniform(3));
        }
        t.fy = fy;
        t.by = fy - 2 - t.ry;
        // crest pushed forward of the body so chest + back show behind/below it
        t.cx = t.bx + t.rx / 2 + t.r / 3;
        // half plate: flat bottom sits ON the body top (never floats); full plate overlaps the shoulder
        t.cy = t.halfPlate ? t.by - t.ry + 2 - t.r / 4 : t.by - t.ry - t.r / 2 + 3;
        // keep the eye and most of the plate inside the frame
        if (t.cx + t.r / 2 > 29) t.cx = 29 - t.r / 2;
        if (t.cy - t.r < -3) t.cy = t.r - 3;
    }

    // ------------------------------------------------------------------ palette

    function _palette(Traits memory t) internal pure returns (bytes6[17] memory c) {
        bytes6[8][5] memory H = [
            [bytes6("9fb3b0"), "5f7a6e", "2f4a3a", "8fae7a", "7a9a3a", "dfe7e2", "4a3a2a", "f3e3b0"],
            [bytes6("22331f"), "1d3022", "102016", "4f7a3a", "6f8f2a", "7f978a", "3a2b1e", "ffe9a8"],
            [bytes6("6f8f86"), "3f6650", "24442f", "79a35a", "8aaa3c", "b9c9c2", "4b3b2b", "cfe0d8"],
            [bytes6("4a3e5a"), "2e3a3a", "1c2a26", "4e6a48", "5f7a2e", "8a7f9c", "2e241c", "e0905a"],
            [bytes6("0c1410"), "17251c", "0f1a13", "24402a", "2f4a1e", "1e2a24", "1a140f", "ff8a2a"]
        ];
        bytes6[3][5] memory F = [
            [bytes6("f2481a"), "ff7a3a", "b02a10"],
            [bytes6("ff5a12"), "ff9a3a", "c2360a"],
            [bytes6("f05a1e"), "ffb04a", "a8340e"],
            [bytes6("e8401c"), "ff6e3a", "9c2410"],
            [bytes6("ff6a0a"), "ffc04d", "c24400"]
        ];
        bytes6[3] memory E = [bytes6("e6f2f5"), "efe8d6", "f2df9a"];
        for (uint256 i; i < 8; ++i) c[i] = H[t.hour][i];
        c[FIRE] = F[t.fire][0];
        c[FIRE_HI] = t.hour == 4 ? bytes6("ffd060") : F[t.fire][1];
        c[FIRE_LO] = F[t.fire][2];
        c[WING] = t.wing == 2 ? bytes6("15120f") : bytes6("050505");
        c[SCAP] = t.wing == 2 ? bytes6("7d8285") : bytes6("9aa0a3");
        c[IRIS] = E[t.eye];
        c[PUPIL] = "120c08";
        c[FEET] = "f2c230";
        c[WATER] = "5aa6c8";
    }

    // ------------------------------------------------------------------ drawing helpers

    function _set(bytes memory g, int256 x, int256 y, uint8 v) internal pure {
        if (x < 0 || y < 0 || x > 31 || y > 31) return;
        g[uint256(y) * 32 + uint256(x)] = bytes1(v + 1); // 0 = empty
    }

    function _get(bytes memory g, int256 x, int256 y) internal pure returns (uint8) {
        if (x < 0 || y < 0 || x > 31 || y > 31) return 0;
        return uint8(g[uint256(y) * 32 + uint256(x)]);
    }

    function _blob(bytes memory g, int256 cx, int256 cy, int256 rx, int256 ry, uint8 v) internal pure {
        for (int256 y = cy - ry; y <= cy + ry; ++y) {
            for (int256 x = cx - rx; x <= cx + rx; ++x) {
                int256 dx = x - cx;
                int256 dy = y - cy;
                if (dx * dx * ry * ry + dy * dy * rx * rx <= rx * rx * ry * ry + rx * ry) _set(g, x, y, v);
            }
        }
    }

    // ------------------------------------------------------------------ layers

    /// @dev back = forest + body + branch, head = crest + eye (animated), front = swallowing leaves.
    function _layers(uint256 tokenId)
        internal
        view
        returns (Traits memory t, bytes memory back, bytes memory head, bytes memory front)
    {
        t = _traits(tokenId);
        back = new bytes(1024);
        head = new bytes(1024);
        front = new bytes(1024);
        LibPRNG.PRNG memory p;
        p.seed(uint256(keccak256(abi.encode(_tokenToSeed[tokenId], "scatter"))));
        _forest(t, back, p);
        _bird(t, back, head, p);
        if (t.forest == 2) _swallow(t, front, p);
    }

    function _forest(Traits memory t, bytes memory g, LibPRNG.PRNG memory p) internal pure {
        // light shaft (dawn / shaft hour): one solid stepped diagonal beam, behind the canopy
        if (t.hour == 0 || t.hour == 1) {
            int256 sx = p.uniform(2) == 0 ? int256(p.uniform(4)) : int256(24 + p.uniform(5));
            for (int256 y; y < 32; ++y) {
                int256 x0 = sx + y / 5;
                _set(g, x0, y, SHAFT);
                _set(g, x0 + 1, y, SHAFT);
                if (t.hour == 1) _set(g, x0 + 2, y, SHAFT);
            }
        }
        // far canopy masses along the top
        uint256 n = 6 + p.uniform(5);
        for (uint256 i; i < n; ++i) {
            _blob(g, int256(p.uniform(32)), int256(p.uniform(10)), 2 + int256(p.uniform(4)), 1 + int256(p.uniform(2)), FAR);
        }
        // mist: flat ragged bands (dawn / rain / dusk)
        if (t.hour == 0 || t.hour == 2 || t.hour == 3) {
            int256 y0 = int256(5 + p.uniform(8));
            for (int256 band; band < 2; ++band) {
                int256 y = y0 + band * 4;
                int256 a = int256(p.uniform(8));
                int256 b = 24 + int256(p.uniform(8));
                for (int256 x = a; x <= b; ++x) {
                    _set(g, x, y, MIST);
                    if (x > a + 2 && x < b - 2) _set(g, x, y + 1, MIST);
                }
            }
        }
        // near leaves at the sides
        n = (t.forest == 3 ? 9 : 4) + p.uniform(3);
        for (uint256 i; i < n; ++i) {
            int256 x = p.uniform(2) == 0 ? int256(p.uniform(7)) : int256(25 + p.uniform(7));
            int256 y = int256(6 + p.uniform(24));
            _blob(g, x, y, 1 + int256(p.uniform(3)), 1 + int256(p.uniform(2)), NEAR);
            if (p.uniform(3) == 0) _set(g, x, y - 1, LIGHT); // wet glint
        }
        // hanging moss strands
        n = (t.forest == 1 ? 8 : 2) + p.uniform(3);
        for (uint256 i; i < n; ++i) {
            int256 x = int256(p.uniform(32));
            int256 len = 3 + int256(p.uniform(t.forest == 1 ? 13 : 6));
            for (int256 y; y < len; ++y) _set(g, x + (y > len / 2 ? int256(1) : int256(0)), y, MOSS);
        }
        // one vine
        if (p.uniform(2) == 0) {
            int256 x = int256(p.uniform(32));
            for (int256 y; y < 32; ++y) {
                if (p.uniform(5) == 0) x += p.uniform(2) == 0 ? int256(-1) : int256(1);
                _set(g, x, y, NEAR);
            }
        }
        // stream: a few water pixels on the bottom row
        if (t.forest == 4) {
            for (int256 x; x < 32; ++x) {
                _set(g, x, 31, WATER);
                if (p.uniform(6) == 0) _set(g, x, 30, WATER);
            }
        }
    }

    function _bird(Traits memory t, bytes memory back, bytes memory head, LibPRNG.PRNG memory p) internal pure {
        bytes memory m = new bytes(1024); // bird mask, for the dark-hour halo
        // ---- branch first (bird stands on it)
        int256 slope = int256(p.uniform(5)) - 2;
        for (int256 x; x < 32; ++x) {
            int256 y = t.fy + (slope * (x - t.bx)) / 16;
            _set(back, x, y, BRANCH);
            _set(back, x, y + 1, BRANCH);
            if (t.branch != 3 && p.uniform(t.branch == 1 ? 2 : 3) != 0) _set(back, x, y, MOSS);
            if (t.branch == 1 && p.uniform(2) == 0) _set(back, x, y - 1, MOSS);
            if (t.branch == 2 && (x % 4) == 0) _set(back, x, y + 1, NEAR);
            if (t.branch != 3 && p.uniform(8) == 0) _set(back, x, y + 2, MOSS); // hanging drip of moss
        }
        // ---- body: fire, chest puffed forward (+x)
        _body(t, back, m);
        // ---- wing: solid black ellipse over the back half, tail down-back
        int256 wcx = t.bx - t.rx / 4;
        int256 wcy = t.by + t.ry / 5;
        int256 wrx = (t.rx * 3) / 4 + 1;
        int256 wry = t.ry / 2 + 1;
        for (int256 y = wcy - wry; y <= wcy + wry; ++y) {
            int256 shear = (y - wcy) / 2; // fold slopes down toward the tail
            for (int256 x = wcx - wrx - 2; x <= wcx + wrx + 2; ++x) {
                int256 dx = x - wcx + shear;
                int256 dy = y - wcy;
                if (dx * dx * wry * wry + dy * dy * wrx * wrx <= wrx * wrx * wry * wry + wrx * wry) {
                    _set(back, x, y, WING);
                    _set(m, x, y, 2);
                }
            }
        }
        int256 tl = 4 + t.r / 3;
        for (int256 k; k < tl; ++k) {
            int256 tx = wcx - wrx - wry / 2 - k / 2;
            int256 ty = wcy + wry - 1 + k;
            _set(back, tx, ty, WING); _set(m, tx, ty, 2);
            _set(back, tx + 1, ty, WING); _set(m, tx + 1, ty, 2);
        }
        // scapulars: a short contiguous grey run where the wing meets the back (front-top of the wing)
        {
            int256 n = t.wing == 1 ? int256(5) : int256(3);
            int256 sy = wcy - wry + 1;
            int256 sx = wcx + wrx / 2 - wry / 2;
            for (int256 k; k < n; ++k) {
                if (_get(back, sx - k, sy) == WING + 1) _set(back, sx - k, sy, SCAP);
            }
        }
        // feet: leg + three toes forward, gripping the branch
        for (int256 f; f < 2; ++f) {
            int256 fx = t.bx - 1 + f * 3;
            int256 y = t.fy + (slope * (fx - t.bx)) / 16;
            _set(back, fx, y - 2, FEET);
            _set(back, fx, y - 1, FEET);
            _set(back, fx + 1, y - 1, FEET);
            _set(back, fx + 2, y - 1, FEET);
            _set(back, fx + 1, y, FEET);
        }
        // dark hours: a 1px grey rim around the black wing + tail only, so black never sinks into the forest
        if (t.hour == 1 || t.hour == 3 || t.hour == 4) {
            for (int256 y; y < 32; ++y) {
                for (int256 x; x < 32; ++x) {
                    if (_get(m, x, y) != 0) continue;
                    if (_get(m, x, y + 1) == 3 || _get(m, x, y - 1) == 3 || _get(m, x + 1, y) == 3 || _get(m, x - 1, y) == 3) {
                        _set(back, x, y, SCAP);
                    }
                }
            }
        }
        // ---- crest disk (head layer, animated): sits forward, covers the beak
        _crest(t, head);
    }

    function _body(Traits memory t, bytes memory back, bytes memory m) internal pure {
        int256 rx = t.rx;
        int256 ry = t.ry;
        for (int256 y = t.by - ry; y <= t.by + ry; ++y) {
            for (int256 x = t.bx - rx; x <= t.bx + rx + 1; ++x) {
                int256 dx = x - t.bx;
                int256 dy = y - t.by;
                int256 erx = dx > 0 ? rx + 1 : rx; // puffed chest
                if (dx * dx * ry * ry + dy * dy * erx * erx > erx * erx * ry * ry + erx * ry) continue;
                _set(back, x, y, dy > (ry * 2) / 3 ? FIRE_LO : FIRE);
                _set(m, x, y, 1);
            }
        }
    }

    function _crest(Traits memory t, bytes memory head) internal pure {
        int256 r = t.r;
        int256 cx = t.cx;
        int256 cy = t.cy;
        int256 bottom = t.halfPlate ? cy + r / 4 : cy + r;
        int256 rim = (r - 1) * (r - 1) + (r - 1);
        for (int256 y = cy - r; y <= bottom; ++y) {
            for (int256 x = cx - r; x <= cx + r; ++x) {
                int256 dx = x - cx;
                int256 dy = y - cy;
                int256 d = dx * dx + dy * dy;
                if (d > r * r + r) continue;
                uint8 v = FIRE;
                if (d > rim) {
                    if (t.hour == 4) v = dy < r / 2 ? FIRE_HI : FIRE; // backlit: the plate edge burns
                    else if (dy < 0 && dx > -r / 3) v = FIRE_HI;      // top-front catches the light
                    else if (dx < 0 && dy > 0) v = FIRE_LO;
                }
                _set(head, x, y, v);
            }
        }
        // eye: round, pale iris, dark pupil, low-forward in the disk
        int256 ex = cx + (r * 2) / 5 + 1;
        int256 ey = cy + r / 6;
        if (r >= 10) {
            for (int256 y = -1; y <= 1; ++y) {
                for (int256 x = -1; x <= 1; ++x) _set(head, ex + x, ey + y, IRIS);
            }
            _set(head, ex, ey - 2, IRIS);
            _set(head, ex, ey + 2, IRIS);
            _set(head, ex - 2, ey, IRIS);
            _set(head, ex + 2, ey, IRIS);
            _set(head, ex, ey, PUPIL);
        } else {
            _set(head, ex, ey - 1, IRIS);
            _set(head, ex - 1, ey, IRIS);
            _set(head, ex + 1, ey, IRIS);
            _set(head, ex, ey + 1, IRIS);
            _set(head, ex, ey, PUPIL);
        }
    }

    function _swallow(Traits memory t, bytes memory g, LibPRNG.PRNG memory p) internal pure {
        // big foreground leaves along one side and the bottom; never over the eye/centre of the disk
        uint256 n = 3 + p.uniform(3);
        for (uint256 i; i < n; ++i) {
            int256 x = p.uniform(2) == 0 ? int256(p.uniform(9)) : int256(p.uniform(32));
            int256 y = x < 9 ? int256(p.uniform(32)) : int256(22 + p.uniform(10));
            int256 dx = x - t.cx;
            int256 dy = y - t.cy;
            if (dx * dx + dy * dy < (t.r * t.r) / 3) continue;
            // never cover the feet / chest: leaves stay outside the body's box
            if (x > t.bx - t.rx - 3 && x < t.bx + t.rx + 3 && y > t.by - t.ry - 2) continue;
            _blob(g, x, y, 2 + int256(p.uniform(4)), 1 + int256(p.uniform(3)), i % 2 == 0 ? NEAR : FAR);
            _set(g, x, y - 1, LIGHT);
        }
    }

    // ------------------------------------------------------------------ svg

    /// @dev "0".."31" as fixed 2-byte cells; avoids toString in the hot loop.
    bytes internal constant NUMS = "0 1 2 3 4 5 6 7 8 9 10111213141516171819202122232425262728293031";

    function _emit(DynamicBufferLib.DynamicBuffer memory b, bytes memory g, bool mirror, uint8 skip) internal pure {
        bytes memory nums = NUMS;
        // one rect = '<rect x="NN" y="NN" width="1" height="1" class="cNN"/>' built in a 64-byte scratch
        bytes memory r = new bytes(128); // 32-byte mstores overshoot; keep slack
        for (uint256 i; i < 1024; ++i) {
            uint8 v = uint8(g[i]);
            if (v == 0 || v == skip) continue;
            uint256 x = i & 31;
            if (mirror) x = 31 - x;
            uint256 len;
            assembly {
                function num(ptr, tbl, n) -> np {
                    let a := byte(0, mload(add(add(tbl, 32), mul(n, 2))))
                    let c := byte(1, mload(add(add(tbl, 32), mul(n, 2))))
                    mstore8(ptr, a)
                    np := add(ptr, 1)
                    if iszero(eq(c, 0x20)) {
                        mstore8(np, c)
                        np := add(np, 1)
                    }
                }
                let o := add(r, 32)
                let p := o
                mstore(p, "<rect x=\"")
                p := add(p, 9)
                p := num(p, nums, x)
                mstore(p, "\" y=\"")
                p := add(p, 5)
                p := num(p, nums, shr(5, i))
                mstore(p, "\" width=\"1\" height=\"1\" class=\"c")
                p := add(p, 31)
                p := num(p, nums, sub(v, 1))
                mstore(p, "\"/>")
                p := add(p, 3)
                len := sub(p, o)
            }
            assembly { mstore(r, len) }
            b.p(r);
            assembly { mstore(r, 128) }
        }
    }

    function art(uint256 tokenId) public view returns (string memory) {
        if (!_exists(tokenId)) revert URIQueryForNonexistentToken();
        (Traits memory t, bytes memory back, bytes memory head, bytes memory front) = _layers(tokenId);
        bytes6[17] memory c = _palette(t);
        DynamicBufferLib.DynamicBuffer memory b;
        b.p(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="100%" height="100%" '
            'shape-rendering="crispEdges" style="image-rendering:pixelated;background:#',
            abi.encodePacked(c[SKY]),
            '"><style>'
        );
        for (uint256 i; i < NCOL; ++i) {
            b.p(".c", bytes(i.toString()), "{fill:#", abi.encodePacked(c[i]), "}");
        }
        b.p("</style>");
        _emit(b, back, t.mirror, SKY + 1);
        // lek bob: head tips forward-down and back, discrete steps keep pixels hard
        string memory f = t.mirror ? "-1" : "1";
        string memory f2 = t.mirror ? "-2" : "2";
        b.p('<g transform="translate(', bytes(t.tipped ? f : "0"), t.tipped ? bytes(' 1)"><g') : bytes(' 0)"><g'));
        b.p('><animateTransform attributeName="transform" type="translate" calcMode="discrete" dur="1.6s" repeatCount="indefinite" values="0 0;');
        b.p(bytes(f), " 1;", bytes(f2), " 1;");
        b.p(bytes(f), ' 0;0 0;0 -1;0 0"/>');
        _emit(b, head, t.mirror, 0);
        b.p("</g></g>");
        _emit(b, front, t.mirror, 0);
        b.p("</svg>");
        return b.s();
    }

    // ------------------------------------------------------------------ metadata

    function _crestName(Traits memory t) internal pure returns (string memory) {
        if (t.crop == 2) return t.tipped ? "Plate Only Tipped" : "Plate Only";
        string memory s = t.halfPlate ? "Half Plate" : "Full Plate";
        return t.tipped ? string.concat(s, " Tipped") : s;
    }

    function _attributes(Traits memory t) internal pure returns (string memory) {
        string[5] memory hour = ["Dawn Fog", "Shaft of Light", "Midday Rain", "Dusk", "Backlit"];
        string[5] memory fire = ["Scarlet", "Flame", "Ember", "Blood Orange", "Molten"];
        string[3] memory eye = ["Ice", "Bone", "Pale Gold"];
        string[3] memory wing = ["Jet", "Jet Scapular", "Sooted"];
        string[4] memory branch = ["Wet Moss", "Thick Moss", "Vine Wrapped", "Bare Wet"];
        string[5] memory forest = ["Deep Canopy", "Hanging Moss", "Swallowed", "Fern Wall", "Stream"];
        return string.concat(
            '[{"trait_type":"Crest","value":"', _crestName(t),
            '"},{"trait_type":"Eye","value":"', eye[t.eye],
            '"},{"trait_type":"Fire","value":"', fire[t.fire],
            '"},{"trait_type":"Wing","value":"', wing[t.wing],
            string.concat(
                '"},{"trait_type":"Branch","value":"', branch[t.branch],
                '"},{"trait_type":"Forest","value":"', forest[t.forest],
                '"},{"trait_type":"Hour","value":"', hour[t.hour], '"}]'
            )
        );
    }

    function traits(uint256 tokenId) external view returns (string memory) {
        if (!_exists(tokenId)) revert URIQueryForNonexistentToken();
        return _attributes(_traits(tokenId));
    }

    function tokenURI(uint256 tokenId) public view virtual override returns (string memory) {
        if (!_exists(tokenId)) revert URIQueryForNonexistentToken();
        string memory img = Base64.encode(bytes(art(tokenId)));
        string memory json = string.concat(
            '{"name":"TUNKI #', tokenId.toString(),
            '","description":"Tunki. Andean cock-of-the-rock, national bird of Peru, a male in lek in the cloud forest. Fully onchain, 32x32, the crest bobs.",',
            '"image":"data:image/svg+xml;base64,', img,
            '","attributes":', _attributes(_traits(tokenId)), "}"
        );
        return string.concat("data:application/json;base64,", Base64.encode(bytes(json)));
    }
}
