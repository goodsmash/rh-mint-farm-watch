/* RH Mint-Farm Watch v2 - on-chain market engine (browser).
 * Read-only. Reads Robinhood Chain (4663) through any JSON-RPC you give it.
 *   - Sales:   replays Seaport 1.5 / 1.6 OrderFulfilled logs (OpenSea's on-chain marketplace)
 *   - Holders: replays a collection's full ERC-721 / ERC-1155 transfer history
 *   - Images:  tokenURI / uri -> metadata -> image (data:, ipfs://, ar://, https)
 * No keys required. OpenSea API enrichment is optional and lives in the page, not here.
 */
(function (G) {
  'use strict';
  const T721 = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef';
  const T1155S = '0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62';
  const T1155B = '0x4a39dc06d4c0dbc64b70af90fd698a233a518aa5d07e595d983b8c0526c8f7fb';
  const ORDER_FULFILLED = '0x9d9af8e38d66c62e2c12f0225249fd9d721c54b83f48d9352c97c6cacdcb6f31';
  /* per-chain Seaport addresses (Official OpenSea Seaport that chain) */
  const SEAPORTS_BY_CHAIN = {
    robinhood: ['0x0000000000000068f116a894984e2db1123eb395','0x00000000000000adc04c56bf30ac9d3c0aaf14dc'],
    ethereum:  ['0x0000000000000068f116a894984e2db1123eb395','0x00000000000000adc04c56bf30ac9d3c0aaf14dc'],
    base:      ['0x00000000000000adc04c56bf30ac9d3c0aaf14dc'],   // Seaport 1.6 – Base native CAs confirmed
    apechain:  ['0x0000000000000068f116a894984e2db1123eb395','0x00000000000000adc04c56bf30ac9d3c0aaf14dc'],
    ink:       ['0x0000000000000068f116a894984e2db1123eb395','0x00000000000000adc04c56bf30ac9d3c0aaf14dc']   // Ink = Seaport on Ethereum L2
  };
  let SEAPORTS = SEAPORTS_BY_CHAIN[chain] || SEAPORTS_BY_CHAIN.robinhood;
  const ZERO = '0x0000000000000000000000000000000000000000';
  const SPAN_ONE_ADDR = 9000000;
  const IPFS = 'https://ipfs.io/ipfs/';

  const CHAINS = {
    robinhood: { id: 4663,  rpc: 'https://rpc.mainnet.chain.robinhood.com',  bs: 0.1045, label: 'Robinhood', opensea: 'robinhood' },
    ethereum:  { id: 1,     rpc: 'https://ethereum-rpc.publicnode.com',       bs: 12.0,   label: 'Ethereum',  opensea: 'ethereum'  },
    base:      { id: 8453,  rpc: 'https://base-rpc.publicnode.com',           bs: 2.0,    label: 'Base',      opensea: 'base'      },
    apechain:  { id: 33139, rpc: 'https://rpc.apechain.com',                  bs: 2.0,    label: 'ApeChain',  opensea: 'apechain'  },
    ink:       { id: 11111, rpc: 'https://rpc-gel.inkonchain.com',               bs: 2.0,    label: 'Ink',       opensea: 'ink'       }
  };
  let chain = 'robinhood';
  let RPC = CHAINS[chain].rpc;
  let BLOCK_S = CHAINS[chain].bs;
  const SPAN_ONE_ADDR_local = SPAN_ONE_ADDR;

  function setChain(c) {
    if (!CHAINS[c]) return;
    chain = c;
    const meta = CHAINS[c];
    RPC = meta.rpc;
    BLOCK_S = meta.bs;
    SEAPORTS = SEAPORTS_BY_CHAIN[c] || SEAPORTS_BY_CHAIN.robinhood;
    if (typeof rpcLabel !== 'undefined' && rpcLabel) rpcLabel.textContent = meta.label + ' · ' + meta.rpc.replace(/^https?:\/\//, '').split('/')[0];
    return meta;
  }
  const chainName = () => chain;
  const getChainMeta = c => CHAINS[c || chain];
  const hx = n => '0x' + n.toString(16);
  const addrOf = w => '0x' + w.slice(-40).toLowerCase();
  const big = h => BigInt(h.startsWith('0x') ? h : '0x' + h);
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  async function rpc(method, params, tries = 4) {
    let last;
    for (let i = 0; i < tries; i++) {
      try {
        const r = await fetch(RPC, { method: 'POST', headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }) });
        if (r.status === 429 || r.status >= 500) throw new Error('HTTP ' + r.status);
        const j = await r.json();
        if (j.error) { const e = new Error(j.error.message || JSON.stringify(j.error)); e.rpc = true; throw e; }
        return j.result;
      } catch (e) {
        last = e;
        if (e.rpc && !/rate|too many|timeout/i.test(e.message)) throw e;   // deterministic error: don't retry
        await sleep(600 * (i + 1));
      }
    }
    throw last;
  }

  async function rpcBatch(calls) {           // [[method, params]] -> results (null on error)
    const out = [];
    for (let i = 0; i < calls.length; i += 40) {
      const chunk = calls.slice(i, i + 40);
      try {
        const r = await fetch(RPC, { method: 'POST', headers: { 'content-type': 'application/json' },
          body: JSON.stringify(chunk.map(([m, p], j) => ({ jsonrpc: '2.0', id: j, method: m, params: p }))) });
        const j = await r.json();
        if (!Array.isArray(j)) throw new Error('batch not supported');
        j.sort((a, b) => a.id - b.id).forEach(x => out.push(x.error ? null : x.result));
      } catch (e) {
        for (const [m, p] of chunk) { try { out.push(await rpc(m, p, 2)); } catch (_) { out.push(null); } }
      }
    }
    return out;
  }

  /* eth_getLogs over [from, to], splitting the range whenever the node says it's too wide or too big. */
  async function getLogs(filter, from, to, span, onProgress) {
    const out = [];
    let step = span;
    let fr = from;
    while (fr <= to) {
      const e = Math.min(fr + step - 1, to);
      try {
        const r = await rpc('eth_getLogs', [Object.assign({}, filter, { fromBlock: hx(fr), toBlock: hx(e) })]);
        for (const l of r) out.push(l);
        fr = e + 1;
        if (onProgress) onProgress((fr - from) / (to - from + 1), out.length);
        if (r.length < 2000 && step < span) step = Math.min(span, step * 2);
      } catch (err) {
        const m = String(err.message || err);
        const allowed = m.match(/only (\d+) are allowed/);
        if (allowed && +allowed[1] < step) { step = +allowed[1] - 5; continue; }
        if (step > 200 && /span|exceed|too many|limit|size|range|timeout|HTTP/i.test(m)) { step = Math.floor(step / 4); continue; }
        throw err;
      }
    }
    return out;
  }

  const head = async () => parseInt(await rpc('eth_blockNumber', []), 16);

  /* ---------------------------------------------------------------- sales (Seaport) */
  function words(data) { const d = data.slice(2); const w = []; for (let i = 0; i < d.length; i += 64) w.push(d.slice(i, i + 64)); return w; }

  function decodeOrderFulfilled(log) {
    const w = words(log.data);
    const recipient = addrOf(w[1]);
    const offOffer = Number(big(w[2])) / 32, offCons = Number(big(w[3])) / 32;
    const nOffer = Number(big(w[offOffer])), nCons = Number(big(w[offCons]));
    const offer = [], cons = [];
    for (let i = 0; i < nOffer; i++) { const b = offOffer + 1 + i * 4;
      offer.push({ type: Number(big(w[b])), token: addrOf(w[b + 1]), id: big(w[b + 2]).toString(), amount: big(w[b + 3]) }); }
    for (let i = 0; i < nCons; i++) { const b = offCons + 1 + i * 5;
      cons.push({ type: Number(big(w[b])), token: addrOf(w[b + 1]), id: big(w[b + 2]).toString(), amount: big(w[b + 3]), to: addrOf(w[b + 4]) }); }
    return { offerer: addrOf(log.topics[1]), recipient, offer, cons };
  }

  /* One sale per (tx, collection, tokenId). Listing fills (NFT offered) win over the mirrored bid side. */
  function salesFromLogs(logs) {
    const seen = new Map();
    for (const l of logs) {
      let o; try { o = decodeOrderFulfilled(l); } catch (e) { continue; }
      const isNft = x => x.type >= 2;
      const isPay = x => x.type <= 1;
      let nfts, pay, buyer, seller, kind;
      if (o.offer.some(isNft)) {                 // listing filled: offerer sells
        nfts = o.offer.filter(isNft); pay = o.cons.filter(isPay);
        seller = o.offerer; buyer = o.recipient; kind = 'listing';
      } else if (o.cons.some(isNft)) {           // offer/bid accepted: offerer buys
        nfts = o.cons.filter(isNft); pay = o.offer.filter(isPay);
        buyer = o.offerer; seller = o.recipient; kind = 'offer';
      } else continue;
      if (!nfts.length) continue;
      const cur = {};
      for (const p of pay) { const k = p.type === 0 ? 'ETH' : p.token; cur[k] = (cur[k] || 0n) + p.amount; }
      const curs = Object.keys(cur);
      const currency = curs.length ? curs.sort((a, b) => (cur[b] > cur[a] ? 1 : -1))[0] : 'ETH';
      const total = cur[currency] || 0n;
      const each = total / BigInt(nfts.length);
      for (const n of nfts) {
        const key = l.transactionHash + ':' + n.token + ':' + n.id;
        const prev = seen.get(key);
        const rec = { tx: l.transactionHash, block: parseInt(l.blockNumber, 16), collection: n.token, id: n.id,
          std: n.type === 3 ? 1155 : 721, qty: Number(n.amount), buyer, seller, currency, price: each, kind,
          market: l.address.toLowerCase() };
        if (!prev) { seen.set(key, rec); continue; }
        // matched orders emit two mirrored events and leave a 0x0 on each side: merge them
        const keep = prev.kind === 'listing' || kind !== 'listing' ? prev : rec, other = keep === prev ? rec : prev;
        if (keep.buyer === ZERO) keep.buyer = other.buyer;
        if (keep.seller === ZERO) keep.seller = other.seller;
        if (!keep.price && other.price) { keep.price = other.price; keep.currency = other.currency; }
        seen.set(key, keep);
      }
    }
    return [...seen.values()];
  }

  async function scanSales({ hours = 24, toBlock, onProgress } = {}) {
    const H = toBlock || await head();
    const from = H - Math.round(hours * 3600 / BLOCK_S);
    let logs = [];
    for (let i = 0; i < SEAPORTS.length; i++) {
      const part = await getLogs({ address: SEAPORTS[i], topics: [ORDER_FULFILLED] }, from, H, SPAN_ONE_ADDR,
        onProgress && ((p, n) => onProgress((i + p) / SEAPORTS.length, logs.length + n)));
      logs = logs.concat(part);
    }
    return { head: H, from, sales: salesFromLogs(logs), rawLogs: logs.length };
  }

  /* ---------------------------------------------------------------- token info */
  function decodeString(h) {
    if (!h || h === '0x') return '';
    try {
      const w = h.slice(2);
      if (w.length === 64) {   // bytes32 style
        let s = ''; for (let i = 0; i < 64; i += 2) { const c = parseInt(w.substr(i, 2), 16); if (c) s += String.fromCharCode(c); }
        return s;
      }
      const off = Number(big(w.slice(0, 64))) * 2;
      const len = Number(big(w.slice(off, off + 64)));
      if (len > 200000 || off + 64 + len * 2 > w.length) return '';
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) bytes[i] = parseInt(w.substr(off + 64 + i * 2, 2), 16);
      return new TextDecoder().decode(bytes);
    } catch (e) { return ''; }
  }
  const pad32 = n => BigInt(n).toString(16).padStart(64, '0');
  const ERC20 = {};
  async function tokenInfo(addr) {
    if (addr === 'ETH') return { symbol: 'ETH', decimals: 18 };
    if (ERC20[addr]) return ERC20[addr];
    const [s, d] = await rpcBatch([['eth_call', [{ to: addr, data: '0x95d89b41' }, 'latest']], ['eth_call', [{ to: addr, data: '0x313ce567' }, 'latest']]]);
    ERC20[addr] = { symbol: decodeString(s).replace(/[^\x20-\x7e]/g, '').slice(0, 12) || addr.slice(0, 8), decimals: d && d !== '0x' ? Number(big(d)) : 18 };
    return ERC20[addr];
  }
  const META = {};
  async function collectionMeta(addr) {
    if (META[addr]) return META[addr];
    const r = await rpcBatch([
      ['eth_call', [{ to: addr, data: '0x06fdde03' }, 'latest']],   // name()
      ['eth_call', [{ to: addr, data: '0x95d89b41' }, 'latest']],   // symbol()
      ['eth_call', [{ to: addr, data: '0x18160ddd' }, 'latest']],   // totalSupply()
      ['eth_call', [{ to: addr, data: '0xe8a3d485' }, 'latest']],   // contractURI()
      ['eth_call', [{ to: addr, data: '0x01ffc9a7d9b67a26' + '0'.repeat(56) }, 'latest']],  // supportsInterface(1155)
    ]);
    const clean = s => s.replace(/[^\x20-\x7e -￿]/g, '').slice(0, 80);
    META[addr] = { name: clean(decodeString(r[0])), symbol: clean(decodeString(r[1])),
      supply: r[2] && r[2].length === 66 ? Number(big(r[2])) : null, contractURI: decodeString(r[3]),
      is1155: !!(r[4] && r[4].length === 66 && big(r[4]) === 1n) };
    return META[addr];
  }

  function resolveUri(u) {
    if (!u) return '';
    u = u.trim();
    if (u.startsWith('ipfs://ipfs/')) return IPFS + u.slice(12);
    if (u.startsWith('ipfs://')) return IPFS + u.slice(7);
    if (u.startsWith('ar://')) return 'https://arweave.net/' + u.slice(5);
    if (/^Qm[1-9A-Za-z]{44}/.test(u) || /^baf[a-z0-9]{50,}/.test(u)) return IPFS + u;
    return u;
  }
  async function readJsonUri(u) {
    if (!u) return null;
    if (u.startsWith('data:')) {
      const comma = u.indexOf(',');
      const head_ = u.slice(5, comma), body = u.slice(comma + 1);
      const txt = /;base64/i.test(head_) ? new TextDecoder().decode(Uint8Array.from(atob(body), c => c.charCodeAt(0))) : decodeURIComponent(body);
      try { return JSON.parse(txt); } catch (e) { return null; }
    }
    const url = resolveUri(u);
    if (!/^https:/.test(url)) return null;
    const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 9000);
    try { const r = await fetch(url, { signal: ctl.signal }); return await r.json(); } catch (e) { return null; } finally { clearTimeout(t); }
  }
  const IMG = {};
  async function tokenMeta(addr, id, is1155) {
    const k = addr + ':' + id;
    if (k in IMG) return IMG[k];
    let uri = '';
    try {
      const sel = is1155 ? '0x0e89341c' : '0xc87b56dd';
      uri = decodeString(await rpc('eth_call', [{ to: addr, data: sel + pad32(id) }, 'latest'], 2));
      if (is1155) uri = uri.replace('{id}', BigInt(id).toString(16).padStart(64, '0'));
    } catch (e) { }
    const j = await readJsonUri(uri);
    const img = j ? resolveUri(j.image || j.image_url || j.image_data && ('data:image/svg+xml;utf8,' + encodeURIComponent(j.image_data)) || '') : '';
    IMG[k] = { name: j && j.name ? String(j.name).slice(0, 80) : '', image: /^(https:|data:image)/.test(img) ? img : '',
      attributes: j && Array.isArray(j.attributes) ? j.attributes.slice(0, 20) : [] };
    return IMG[k];
  }

  /* ---------------------------------------------------------------- holders (full transfer replay) */
  async function holders(addr, { is1155, toBlock, fromBlock = 0, onProgress } = {}) {
    const H = toBlock || await head();
    const topics = is1155 ? [[T1155S, T1155B]] : [T721];
    const logs = await getLogs({ address: addr, topics }, fromBlock, H, SPAN_ONE_ADDR, onProgress);
    const bal = new Map();                     // owner -> count (721) or units (1155)
    const owner = new Map();                   // 721 tokenId -> owner
    const firstSeen = new Map(), lastMove = new Map();
    const moves = [];                          // all transfers, oldest first
    const add = (a, n) => { if (a === ZERO) return; const v = (bal.get(a) || 0) + n; if (v) bal.set(a, v); else bal.delete(a); };
    for (const l of logs) {
      const b = parseInt(l.blockNumber, 16);
      if (!is1155) {
        if (l.topics.length !== 4) continue;   // ERC-20 Transfer on the same topic: skip
        const from = addrOf(l.topics[1]), to = addrOf(l.topics[2]), id = big(l.topics[3]).toString();
        add(from, -1); add(to, 1); owner.set(id, to);
        moves.push({ b, tx: l.transactionHash, from, to, id, qty: 1 });
        if (!firstSeen.has(to)) firstSeen.set(to, b); lastMove.set(to, b); lastMove.set(from, b);
      } else {
        const from = addrOf(l.topics[2]), to = addrOf(l.topics[3]);
        const w = words(l.data);
        let pairs = [];
        if (l.topics[0] === T1155S) pairs = [[big(w[0]).toString(), Number(big(w[1]))]];
        else { const oi = Number(big(w[0])) / 32, ov = Number(big(w[1])) / 32, n = Number(big(w[oi]));
          for (let i = 0; i < n; i++) pairs.push([big(w[oi + 1 + i]).toString(), Number(big(w[ov + 1 + i]))]); }
        for (const [id, q] of pairs) { add(from, -q); add(to, q); moves.push({ b, tx: l.transactionHash, from, to, id, qty: q }); }
        if (!firstSeen.has(to)) firstSeen.set(to, b); lastMove.set(to, b); lastMove.set(from, b);
      }
    }
    return { head: H, logs: logs.length, bal, owner, moves, firstSeen, lastMove };
  }

  /* ---------------------------------------------------------------- analytics */
  function holderStats(h, flagged) {
    const arr = [...h.bal.entries()].filter(([a]) => a !== ZERO && a !== '0x000000000000000000000000000000000000dead').sort((a, b) => b[1] - a[1]);
    const total = arr.reduce((s, x) => s + x[1], 0) || 1;
    const buckets = { '1': 0, '2-5': 0, '6-20': 0, '21-100': 0, '100+': 0 };
    let flaggedUnits = 0, flaggedHolders = 0;
    for (const [a, n] of arr) {
      buckets[n === 1 ? '1' : n <= 5 ? '2-5' : n <= 20 ? '6-20' : n <= 100 ? '21-100' : '100+']++;
      const t = flagged && flagged(a);
      if (t === 'CONFIRMED_PATTERN' || t === 'LIKELY') { flaggedUnits += n; flaggedHolders++; }
    }
    const top10 = arr.slice(0, 10).reduce((s, x) => s + x[1], 0);
    // Gini coefficient of holdings (0 = everyone equal, 1 = one wallet holds all)
    let g = 0; const asc = arr.map(x => x[1]).reverse(); let cum = 0;
    asc.forEach((v, i) => { cum += v; g += (i + 1) * v; });
    const n = asc.length; const gini = n ? (2 * g) / (n * cum) - (n + 1) / n : 0;
    return { holders: arr.length, units: total, top: arr.slice(0, 100), top10Share: top10 / total, gini,
      buckets, flaggedUnitsShare: flaggedUnits / total, flaggedHolders };
  }

  function salesStats(sales, prices) {        // prices: currency -> {symbol, decimals, eth}  (eth = value of 1 unit in ETH)
    const C = new Map();
    for (const s of sales) {
      const p = prices[s.currency]; if (!p) continue;
      const v = Number(s.price) / 10 ** p.decimals * (p.eth || 0);
      const c = C.get(s.collection) || { collection: s.collection, sales: 0, volume: 0, buyers: new Set(), sellers: new Set(),
        prices: [], last: 0, pairs: new Map(), tokens: new Map(), byBlock: [] };
      c.sales++; c.volume += v; c.buyers.add(s.buyer); c.sellers.add(s.seller); if (v > 0) c.prices.push(v);
      c.last = Math.max(c.last, s.block); c.byBlock.push([s.block, v]);
      const pk = [s.buyer, s.seller].sort().join('|'); c.pairs.set(pk, (c.pairs.get(pk) || 0) + 1);
      c.tokens.set(s.id, (c.tokens.get(s.id) || 0) + 1);
      C.set(s.collection, c);
    }
    const out = [];
    for (const c of C.values()) {
      const ps = c.prices.sort((a, b) => a - b);
      const q = f => ps.length ? ps[Math.min(ps.length - 1, Math.floor(f * ps.length))] : 0;
      const repeatPairs = [...c.pairs.values()].filter(n => n >= 3).reduce((s, n) => s + n, 0);
      const churned = [...c.tokens.values()].filter(n => n >= 3).reduce((s, n) => s + n, 0);
      out.push({ collection: c.collection, sales: c.sales, volume: c.volume, buyers: c.buyers.size, sellers: c.sellers.size,
        floorish: q(0.05), median: q(0.5), high: ps[ps.length - 1] || 0, last: c.last,
        washShare: c.sales ? Math.min(1, (repeatPairs + churned) / (2 * c.sales)) : 0, series: c.byBlock });
    }
    return out.sort((a, b) => b.volume - a.volume);
  }

  G.RHMarket = { setRpc: u => { RPC = u; }, rpc, rpcBatch, head, getLogs, scanSales, salesFromLogs, decodeOrderFulfilled,
    tokenInfo, collectionMeta, tokenMeta, holders, holderStats, salesStats, resolveUri, BLOCK_S, SEAPORTS, ZERO };
})(typeof window !== 'undefined' ? window : globalThis);
