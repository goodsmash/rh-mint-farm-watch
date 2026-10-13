// Headless harness: simulates the dashboard's window/helpers and runs the real
// topp() from docs/top_participants_tab.js, then asserts the praise output.
import fs from 'node:fs';
import vm from 'node:vm';

// ---- 1. Load the embedded top-participants data (as window.TOP_PARTICIPANTS) ----
const tpRaw = fs.readFileSync(new URL('./docs/top_participants.js', import.meta.url), 'utf8');
// window.TOP_PARTICIPANTS={"24h":{...}}
const json = tpRaw.slice(tpRaw.indexOf('{'), tpRaw.lastIndexOf('};')+1);
const TOP_PARTICIPANTS = JSON.parse(json);
const WIN = '24h';

// ---- 2. Simulate the dashboard helpers ($ , esc, short, fmt, pct, addrLink) ----
const els = {};
global.window = {
  TOP_PARTICIPANTS,
  win: WIN,
  topp: null,
};
global.document = {
  querySelector: () => {
    const el = {
      innerHTML: '',
      innerText: '',
      onclick: null,
      style: {},
      dataset: {},
      addEventListener: () => {},
      classList: { add: () => {}, remove: () => {}, toggle: () => {} },
      appendChild: () => {},
      removeChild: () => {},
    };
    return el;
  },
};
global.esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
global.short = (a) => (a ? a.slice(0, 6) + '…' + a.slice(-4) : '');
global.fmt = (n) => (n == null ? '—' : Number(n).toLocaleString());
global.pct = (n) => (n == null ? '—' : (n * 100).toFixed(1) + '%');
global.addrLink = (a) => `<a class="mono" href="https://robin.etherscan.io/address/${a}" target="_blank" rel="noopener">${global.short(a)}</a><span class="copy" data-copy="${a}">copy</span> <a class="sub" href="https://opensea.io/${a}" target="_blank" rel="noopener">OS</a>`;

// ---- 3. Run the actual tab script in this (browser-like) context ----
vm.runInThisContext(fs.readFileSync(new URL('./docs/top_participants_tab.js', import.meta.url), 'utf8'), 'docs/top_participants_tab.js');

// ---- 4. Run topp() and capture the rendered HTML ----
const el = global.document.querySelector('#view');
global._capturedHTML = null;
// intercept innerHTML writes to #view
const orig = el.innerHTML;
// re-implement topp() body but capture html instead of writing:
// easiest: read the function and call with a patched capture. Instead:
const toppFn = global.window.topp;
// monkeypatch the view element to record html
const recorder = {
  innerHTML: '',
  set innerHTML(v) { this._html = v; },
  get innerHTML() { return this._html; },
};
Object.defineProperty(el, 'innerHTML', {
  configurable: true,
  enumerable: false,
  get: () => recorder.innerHTML,
  set: (v) => { recorder.innerHTML = v; },
});
global._recorder = recorder;

global.window.topp();

// ---- 5. Assertions ----
const html = recorder.innerHTML;
const checks = [];
const ok = (name, cond) => { checks.push({ name, pass: !!cond, detail: cond && html.slice(0, 120) + '...' }); };

ok('window.TOP_PARTICIPANTS loaded for 24h', !!global.window.TOP_PARTICIPANTS['24h']);
ok('top100 present', Array.isArray(global.window.TOP_PARTICIPANTS['24h']?.top100) && global.window.TOP_PARTICIPANTS['24h'].top100.length === 100);
ok('rank-1 collection = Uniswap v4 Positions NFT (praise data)', global.window.TOP_PARTICIPANTS['24h']?.top100?.[0]?.name === 'Uniswap v4 Positions NFT');
ok('top payers (PAID_BUYER) present', (global.window.TOP_PARTICIPANTS['24h']?.top100?.[0]?.top_payers || []).some(p => p.role === 'PAID_BUYER'));
ok('top holders (SELF_MINTER) present', (global.window.TOP_PARTICIPANTS['24h']?.top100?.[0]?.top_holders || []).some(p => p.role === 'SELF_MINTER'));
ok('no bot labels (PAID_BUYER/SELF_MINTER only)', !html.includes('bot') && !html.includes('BOT') && !html.includes('flag'));
ok('praise line present', html.includes('praise, not a flag'));
ok('top-100 collections tie-in present', html.includes('top 100 collections on Robinhood'));
ok('biggest payers table present', html.includes('Biggest payers across the top collections'));
ok('top chains visible (chains bucket)', html.includes('Top chains of the best projects'));
ok('more data visible (memes/wrapped)', html.includes('More collections (memes / wrapped / wild cards)'));
ok('no accusation/flags wording', !html.includes('blocked') && !html.includes('honeypot'));

console.log('\n===== TOP PARTICIPANTS PRAYER VIEW (harness render) =====');
console.log(html.slice(0, 2600));
console.log('\n===== ASSERTIONS =====');
let allPass = true;
for (const c of checks) {
  console.log(`${c.pass ? 'PASS' : 'FAIL'}  ${c.name}`);
  if (!c.pass) allPass = false;
}
console.log(`\nRESULT: ${allPass ? 'ALL PASS' : 'SOME FAILED'} (${checks.length} checks)`);
process.exit(allPass ? 0 : 1);
