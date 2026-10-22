/* 151 Trading Strategies · NIFTY 50 & SENSEX – single-page dashboard (no build step). */
(() => {
'use strict';

// ------------------------------------------------------------------ helpers
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const isNum = v => typeof v === 'number' && isFinite(v);
const store = {
  get(k, d) { try { return localStorage.getItem(k) ?? d; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } },
};
const fmt = {
  pct: (v, d = 1) => isNum(v) ? (v * 100).toFixed(d) + '%' : '–',
  spct: (v, d = 1) => isNum(v) ? (v >= 0 ? '+' : '') + (v * 100).toFixed(d) + '%' : '–',
  n: (v, d = 2) => isNum(v) ? v.toFixed(d) : '–',
  sn: (v, d = 2) => isNum(v) ? (v >= 0 ? '+' : '') + v.toFixed(d) : '–',
  big: (v, d = 0) => isNum(v) ? v.toLocaleString('en-IN', { maximumFractionDigits: d, minimumFractionDigits: d }) : '–',
  cr: v => isNum(v) ? '₹' + (v / 1e7).toLocaleString('en-IN', { maximumFractionDigits: 0 }) + ' Cr' : '–',
};
const cls = v => (!isNum(v) || v === 0) ? 'flat' : v > 0 ? 'up' : 'down';
const UNI_LABEL = { NIFTY50: 'NIFTY 50', SENSEX30: 'SENSEX' };
const BIAS = { long: ['LONG', 'up'], short: ['SHORT', 'down'], mixed: ['LONG / SHORT', 'mix'], neutral: ['NEUTRAL', 'flat'] };
const STATUS_CHIP = { adapted: ['ADAPTED', 'adapted'], proxy: ['PROXY DATA', 'proxy'] };
const CURVE_STYLE = {
  strategy: { label: 'Strategy', color: '#2dd4bf', width: 2.4 },
  benchmark: { label: 'Index', color: '#7f8da1', width: 1.6, dash: [5, 4] },
  long_only: { label: 'Long leg only', color: '#60a5fa', width: 1.6 },
  constituents_avg: { label: 'Constituents (avg of single-stock runs)', color: '#fbbf24', width: 1.6 },
  always_sell: { label: 'Always sell (no filter)', color: '#fbbf24', width: 1.6 },
  equal_weight_alphas: { label: 'Equal-weight alphas', color: '#a78bfa', width: 1.6 },
};

const state = {
  uni: store.get('uni', 'NIFTY50'),
  meta: null, live: null, registry: null,
  cats: {}, byId: {}, charts: [],
  sort: { key: 'sharpe', dir: -1 },
  filter: { cat: 'all', q: '' },
  optFilter: 'all',
};
if (!UNI_LABEL[state.uni]) state.uni = 'NIFTY50';

// ------------------------------------------------------------------ data
let VERSION = '';
async function getJSON(name, fresh = false) {
  const url = `data/${name}.json` + (fresh || !VERSION ? `?t=${Date.now()}` : `?v=${encodeURIComponent(VERSION)}`);
  const r = await fetch(url, fresh ? { cache: 'no-store' } : undefined);
  if (!r.ok) throw new Error(`${name}.json: HTTP ${r.status}`);
  return r.json();
}
async function loadCat(cat) {
  if (state.cats[cat]) return state.cats[cat];
  const d = await getJSON(cat);
  state.cats[cat] = d;
  d.strategies.forEach(s => { state.byId[s.id] = s; });
  return d;
}
async function loadAll() {
  await Promise.all(state.meta.categories.map(c => loadCat(c.id)));
}
const allStrategies = () => state.meta.categories.flatMap(c => (state.cats[c.id]?.strategies || []));
const blockOf = s => s.universes?.[state.uni];

// ------------------------------------------------------------------ charts
function clearCharts() { state.charts.forEach(c => { try { c.destroy(); } catch (e) { /* ignore */ } }); state.charts = []; }
function setupChartDefaults() {
  const C = Chart.defaults;
  C.color = '#7f8da1';
  C.borderColor = '#1b2433';
  C.font.family = getComputedStyle(document.body).fontFamily;
  C.font.size = 11;
  C.animation = false;
  C.maintainAspectRatio = false;
  C.plugins.legend.labels.usePointStyle = true;
  C.plugins.legend.labels.pointStyle = 'line';
  C.plugins.legend.labels.boxWidth = 22;
  C.plugins.tooltip.backgroundColor = '#0d121a';
  C.plugins.tooltip.borderColor = '#2b384b';
  C.plugins.tooltip.borderWidth = 1;
  C.plugins.tooltip.titleColor = '#e7edf5';
  C.plugins.tooltip.bodyColor = '#b4c0cf';
  C.plugins.tooltip.padding = 10;
}
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const dateTick = s => { const p = String(s).split('-'); return p.length === 3 ? `${MON[+p[1] - 1]} ’${p[0].slice(2)}` : s; };

function mkChart(canvas, cfg) {
  const ch = new Chart(canvas, cfg);
  state.charts.push(ch);
  return ch;
}
function lineConfig(labels, datasets, { yfmt = v => v, log = false, ytitle = '' } = {}) {
  return {
    type: 'line',
    data: { labels, datasets },
    options: {
      interaction: { mode: 'index', intersect: false },
      elements: { point: { radius: 0, hoverRadius: 4 } },
      plugins: {
        legend: { position: 'bottom' },
        tooltip: { callbacks: { title: it => it[0].label, label: c => ` ${c.dataset.label}: ${yfmt(c.parsed.y)}` } },
      },
      scales: {
        x: { ticks: { maxTicksLimit: 8, maxRotation: 0, callback(v) { return dateTick(this.getLabelForValue(v)); } }, grid: { display: false } },
        y: { type: log ? 'logarithmic' : 'linear', ticks: { callback: v => yfmt(v), maxTicksLimit: 7 }, title: { display: !!ytitle, text: ytitle } },
      },
    },
  };
}
function drawEquity(canvas, curve, { units, benchLabel, log = false, neutral = false }) {
  const keys = Object.keys(curve).filter(k => k !== 'dates');
  const ds = keys.map(k => {
    const st = CURVE_STYLE[k] || { label: k, color: '#999', width: 1.5 };
    return {
      label: k === 'benchmark' && benchLabel ? benchLabel : st.label,
      data: curve[k], borderColor: st.color, borderWidth: st.width, borderDash: st.dash || [], tension: 0.1, hidden: neutral && (k === 'benchmark' || k === 'long_only'), _key: k,
    };
  });
  const isCum = /cumul/i.test(units || '');
  return mkChart(canvas, lineConfig(curve.dates, ds, {
    log: log && !isCum,
    yfmt: v => isCum ? fmt.n(v, 1) : fmt.n(v, 0),
  }));
}

const vlines = {
  id: 'vlines',
  afterDatasetsDraw(chart, _a, opts) {
    const { ctx, chartArea: ca, scales: { x } } = chart;
    const drawn = {};
    (opts.lines || []).forEach(l => {
      const px = x.getPixelForValue(l.x);
      if (px < ca.left || px > ca.right) return;
      const row = l.bottom ? 'b' : 't';
      const tooClose = (drawn[row] || []).some(q => Math.abs(q - px) < 72);   // avoid overlapping labels on narrow screens
      (drawn[row] = drawn[row] || []).push(px);
      ctx.save();
      ctx.strokeStyle = l.color; ctx.lineWidth = 1; ctx.setLineDash(l.dash || [4, 4]);
      ctx.beginPath(); ctx.moveTo(px, ca.top); ctx.lineTo(px, ca.bottom); ctx.stroke();
      ctx.setLineDash([]); ctx.fillStyle = l.color; ctx.font = '11px ' + Chart.defaults.font.family;
      ctx.textAlign = 'center'; if (!tooClose) ctx.fillText(l.label, Math.min(Math.max(px, ca.left + 30), ca.right - 30), l.bottom ? ca.bottom - 6 : ca.top + 12);
      ctx.restore();
    });
  },
};
function drawPayoff(canvas, p) {
  const pts = k => p.x.map((x, i) => ({ x, y: p[k][i] }));
  const lines = [{ x: p.spot, color: '#e7edf5', label: 'Spot ' + fmt.big(p.spot) }]
    .concat((p.breakevens || []).map(b => ({ x: b, color: '#fbbf24', label: 'BE ' + fmt.big(b), bottom: true })));
  return mkChart(canvas, {
    type: 'line', plugins: [vlines],
    data: {
      datasets: [
        { label: 'At expiry', data: pts('expiry'), borderColor: '#2dd4bf', borderWidth: 2.4, pointRadius: 0, fill: { target: 'origin', above: 'rgba(52,211,153,.14)', below: 'rgba(248,113,113,.14)' } },
        { label: 'Half-way to expiry (model)', data: pts('mid'), borderColor: '#60a5fa', borderWidth: 1.6, borderDash: [5, 4], pointRadius: 0 },
      ],
    },
    options: {
      parsing: false, interaction: { mode: 'nearest', axis: 'x', intersect: false },
      plugins: { vlines: { lines }, legend: { position: 'bottom' },
        tooltip: { callbacks: { title: it => 'Index at expiry: ' + fmt.big(it[0].parsed.x), label: c => ` ${c.dataset.label}: ${fmt.big(c.parsed.y, 1)} pts` } } },
      scales: {
        x: { type: 'linear', ticks: { maxTicksLimit: 9, callback: v => fmt.big(v) }, grid: { display: false } },
        y: { ticks: { callback: v => fmt.big(v) }, title: { display: true, text: 'P&L (index points)' } },
      },
    },
  });
}
function drawGeneric(canvas, c) {
  const palette = ['#2dd4bf', '#fbbf24', '#60a5fa', '#a78bfa', '#f87171'];
  const ds = c.series.map((s, i) => ({ label: s.name, data: s.data, borderColor: palette[i % palette.length], borderWidth: 1.8, tension: 0.15 }));
  const yfmt = c.yfmt === 'pct' ? v => fmt.n(v, 1) + '%' : v => fmt.n(v, 2);
  return mkChart(canvas, lineConfig(c.x, ds, { yfmt }));
}

// ------------------------------------------------------------------ small renderers
function spark(vals, w = 96, h = 28) {
  if (!vals || vals.length < 2) return '';
  const step = Math.ceil(vals.length / 70);
  const v = vals.filter((_, i) => i % step === 0 || i === vals.length - 1);
  const mn = Math.min(...v), mx = Math.max(...v), rg = mx - mn || 1;
  const pts = v.map((y, i) => `${((i / (v.length - 1)) * w).toFixed(1)},${(h - 2 - ((y - mn) / rg) * (h - 4)).toFixed(1)}`).join(' ');
  const up = v[v.length - 1] >= v[0];
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline points="${pts}" fill="none" style="stroke:var(--${up ? 'up' : 'down'})" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}
function biasChip(b) { const [t, c] = BIAS[b] || BIAS.neutral; return `<span class="chip ${c}">${t}</span>`; }
function statusChip(s) { const x = STATUS_CHIP[s.status]; return x ? `<span class="chip ${x[1]}" title="${esc(s.adapted_note || '')}">${x[0]}</span>` : ''; }

function perfCell(s, b) {
  const m = b?.metrics || {};
  if (isNum(m.cagr)) return { text: fmt.spct(m.cagr) + ' <span class="muted">CAGR</span>', val: m.cagr, cls: cls(m.cagr) };
  if (isNum(m.avg)) { const u = /vol/i.test(b.curve_units || '') ? ' vp' : '%'; return { text: fmt.sn(m.avg) + u + ' <span class="muted">/ mo</span>', val: m.avg, cls: cls(m.avg) }; }
  return { text: '–', val: null, cls: 'flat' };
}
function ddCell(b) {
  const m = b?.metrics || {};
  if (!isNum(m.max_dd)) return '–';
  return isNum(m.cagr) ? fmt.pct(m.max_dd) : fmt.n(m.max_dd, 1) + (/vol/i.test(b.curve_units || '') ? ' vp' : '%');
}

function renderTable(t, small = true, limit = 8) {
  const num = /^[+\-−]?[\d,.]+(%|x|d)?$|^₹|^[+\-]?\d/;
  const head = t.columns.map(c => `<th>${esc(c)}</th>`).join('');
  const rows = t.rows.map((r, n) => `<tr${n >= limit ? ' class="more" hidden' : ''}>` + r.map((c, i) => {
    const s = String(c ?? '');
    let k = '';
    if (i === 0 && /^(Long|Short)$/.test(s)) k = s === 'Long' ? 'up' : 'down';
    else if (/^(Long|Short)$/.test(s) || s === 'traded') k = /Long|traded/.test(s) ? 'up' : 'down';
    else if (/^\+[\d.]/.test(s)) k = 'up';
    else if (/^[-−][\d.]/.test(s)) k = 'down';
    const right = i > 0 && num.test(s) ? ' r' : '';
    return `<td class="${right} ${k}">${esc(s)}</td>`;
  }).join('') + '</tr>').join('');
  const more = t.rows.length > limit ? `<div class="tbl-foot"><button class="btn show-all" type="button">Show all ${t.rows.length} rows</button></div>` : '';
  return `<div class="tbl-wrap ${small ? 'small' : ''}"><div class="cap">${esc(t.title)}</div><div class="tbl-scroll"><table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>${more}</div>`;
}

// ---- tabs: all panels are rendered, charts inside are drawn lazily when a tab is first shown
function tabsHTML(panels) {
  if (panels.length < 2) return panels.map(p => `<section class="panel" id="panel-${p.id}">${p.html}</section>`).join('');
  return `<div class="tabs" role="tablist">${panels.map((p, i) => `<button role="tab" type="button" class="tab" data-t="${p.id}" aria-selected="${i === 0}">${p.label}</button>`).join('')}</div>` +
    panels.map((p, i) => `<section class="panel" role="tabpanel" id="panel-${p.id}" ${i ? 'hidden' : ''}>${p.html}</section>`).join('');
}
function wireTabs(panels) {
  const done = new Set();
  const show = id => {
    panels.forEach(p => { const el = $('#panel-' + p.id); if (el) el.hidden = p.id !== id; });
    $$('.tab').forEach(t => t.setAttribute('aria-selected', t.dataset.t === id));
    if (!done.has(id)) { done.add(id); const p = panels.find(x => x.id === id); if (p && p.init) p.init(); }
  };
  $$('.tab').forEach(t => t.addEventListener('click', () => show(t.dataset.t)));
  show(panels[0].id);
}
const isMobile = () => window.matchMedia('(max-width: 860px)').matches;

const METRIC = {
  cagr: ['CAGR', fmt.spct, true], sharpe: ['Sharpe', v => fmt.n(v), true], vol: ['Volatility', fmt.pct], max_dd: ['Max drawdown', fmt.pct, true],
  hit_rate: ['Hit rate', v => fmt.pct(v, 0)], ret_1y: ['Last 12 months', fmt.spct, true], total_return: ['Total return', fmt.spct, true],
  sharpe_gross: ['Sharpe before costs', v => fmt.n(v), true], turnover_ann: ['Turnover / year', v => fmt.n(v, 1) + '×'], beta: ['Beta to index', v => fmt.n(v)],
  bench_cagr: ['Index CAGR', fmt.spct, true], bench_sharpe: ['Index Sharpe', v => fmt.n(v), true], calmar: ['Calmar', v => fmt.n(v)],
  long_only_cagr: ['Long-leg CAGR', fmt.spct, true], long_only_sharpe: ['Long-leg Sharpe', v => fmt.n(v), true], long_only_max_dd: ['Long-leg max DD', fmt.pct],
  direction_accuracy: ['Direction accuracy', v => fmt.pct(v, 1)],
  coverage: ['Stocks with data', v => fmt.n(v, 0)],
  implied_corr: ['Implied correlation', v => fmt.n(v)], realised_corr: ['Realised correlation', v => fmt.n(v)], corr_spread: ['Implied − realised', v => fmt.sn(v)],
  spread_percentile: ['Spread percentile (5y)', v => fmt.n(v, 0) + 'th'], theoretical_vol: ['Theoretical index vol', v => fmt.n(v, 1) + '%'],
  risk_factors_K: ['Risk factors K', v => fmt.n(v, 0)], erank: ['eRank', v => fmt.n(v, 1)], subset_weight_share: ['Subset weight share', v => fmt.pct(v, 0)],
  basket_beta: ['Basket beta (hedge ratio)', v => fmt.n(v)], vol_unhedged: ['Vol unhedged', fmt.pct], vol_hedged: ['Vol hedged', fmt.pct], avg_variance_cut: ['Avg variance cut', v => fmt.pct(v, 0)],
  vix: ['India VIX', v => fmt.n(v, 1)], rv_21d: ['Realised vol 21d', v => fmt.n(v, 1) + '%'], vrp_spread: ['VIX − realised', v => fmt.sn(v, 1)],
  months_traded: ['Months traded', v => fmt.n(v, 0)],
};
const CYC = (unit) => ({
  avg: ['Avg / cycle', v => fmt.sn(v) + unit, true], total: ['Cumulative', v => fmt.sn(v, 1) + unit, true], sharpe: ['Sharpe (monthly)', v => fmt.n(v), true],
  hit_rate: ['Hit rate', v => fmt.pct(v, 0)], worst: ['Worst cycle', v => fmt.sn(v) + unit, true], best: ['Best cycle', v => fmt.sn(v) + unit, true],
  max_dd: ['Max drawdown', v => fmt.n(v, 1) + unit, true], n: ['Cycles', v => fmt.n(v, 0)],
  always_total: ['Cumulative if always sold', v => fmt.sn(v, 1) + unit, true], always_sharpe: ['Sharpe if always sold', v => fmt.n(v), true],
});
const ORDER_RET = ['cagr', 'sharpe', 'vol', 'max_dd', 'hit_rate', 'ret_1y', 'sharpe_gross', 'turnover_ann', 'beta', 'bench_cagr', 'bench_sharpe', 'long_only_cagr', 'long_only_sharpe', 'long_only_max_dd', 'direction_accuracy', 'calmar', 'total_return'];
const ORDER_CYC = ['avg', 'total', 'sharpe', 'hit_rate', 'worst', 'best', 'max_dd', 'n', 'always_total', 'always_sharpe', 'vix', 'rv_21d', 'vrp_spread', 'months_traded'];
const ORDER_OTHER = ['coverage', 'implied_corr', 'realised_corr', 'corr_spread', 'spread_percentile', 'vix', 'theoretical_vol', 'risk_factors_K', 'erank', 'subset_weight_share', 'basket_beta', 'vol_unhedged', 'vol_hedged', 'avg_variance_cut'];

function metricTiles(b, compact) {
  const m = b.metrics || {};
  const unit = /vol/i.test(b.curve_units || '') ? ' vp' : '%';
  const isRet = isNum(m.cagr), isCyc = isNum(m.avg);
  const defs = isRet ? { ...METRIC } : isCyc ? { ...METRIC, ...CYC(unit) } : { ...METRIC };
  const order = isRet ? ORDER_RET.concat(ORDER_OTHER) : isCyc ? ORDER_CYC : ORDER_OTHER;
  const tiles = [];
  order.forEach(k => {
    if (!(k in m) || !isNum(m[k]) || !defs[k]) return;
    const [label, f, signed] = defs[k];
    tiles.push(`<div class="tile"><div class="k">${label}</div><div class="v ${signed ? cls(m[k]) : ''}">${f(m[k])}</div></div>`);
  });
  if (isRet && m.start) tiles.push(`<div class="tile"><div class="k">Backtest start</div><div class="v" style="font-size:15px">${esc(m.start)}</div><div class="s">${fmt.big(m.n)} trading days</div></div>`);
  if (isCyc && m.start) tiles.push(`<div class="tile"><div class="k">Backtest start</div><div class="v" style="font-size:15px">${esc(m.start)}</div></div>`);
  if (!tiles.length) return '<p class="muted">No backtest metrics for this strategy.</p>';
  const cl = `tiles ${compact ? 'compact' : ''}`;
  if (tiles.length <= 6) return `<div class="${cl}">${tiles.join('')}</div>`;
  return `<div class="${cl}">${tiles.slice(0, 6).join('')}</div><details class="fold inner"><summary>All metrics (${tiles.length - 6} more)</summary><div class="${cl}">${tiles.slice(6).join('')}</div></details>`;
}

// ------------------------------------------------------------------ chrome (header / nav)
function renderChrome() {
  const m = state.meta;
  $('#banner').innerHTML = m.synthetic
    ? '<div class="banner synthetic">⚠ SYNTHETIC TEST DATA – generated for development, not real market data.</div>'
    : (daysOld(m.generated_at) > 5 ? `<div class="banner stale">Data is ${Math.floor(daysOld(m.generated_at))} days old – the GitHub Actions refresh may be failing.</div>` : '');
  $('#uni-seg').innerHTML = Object.keys(UNI_LABEL).map(u =>
    `<button type="button" data-uni="${u}" aria-pressed="${u === state.uni}">${UNI_LABEL[u]}</button>`).join('');
  $$('#uni-seg button').forEach(b => b.addEventListener('click', () => { state.uni = b.dataset.uni; store.set('uni', state.uni); renderChrome(); route(); }));
  const q = (state.live?.indices || []).map(i => {
    const isV = i.symbol === '^INDIAVIX';
    return `<div class="chip-q" title="${esc(i.name)}"><b>${esc(i.name)}</b><span class="px">${fmt.big(i.last, 2)}</span><span class="ch ${isV ? (i.chg_pct > 0 ? 'down' : 'up') : cls(i.chg_pct)}">${fmt.spct(i.chg_pct, 2)}</span></div>`;
  }).join('');
  $('#ticker').innerHTML = q;
  const open = nseOpen();
  $('#status').innerHTML = `<span class="dot ${open ? '' : 'off'}"></span><span title="Latest bar: ${esc(m.data_asof)}">${open ? 'NSE open' : 'NSE closed'} · updated ${ago(m.generated_at)}</span>`;
  const cats = m.categories;
  const cur = location.hash;
  const link = (h, label, count) => `<a href="${h}" ${cur === h || (h === '#/' && (cur === '' || cur === '#')) ? 'aria-current="page"' : ''}>${label}${count != null ? `<span class="count">${count}</span>` : ''}</a>`;
  $('#nav').innerHTML = `
    ${link('#/', 'Signal board', m.counts.implemented)}
    ${link('#/market', 'Market now')}
    <div class="grp">Strategies</div>
    ${cats.map(c => link('#/c/' + c.id, esc(c.label), c.count)).join('')}
    <div class="grp">Reference</div>
    ${link('#/excluded', 'Not applicable', m.counts.excluded)}
    ${link('#/about', 'Method & data')}`;
  $('#nav').insertAdjacentHTML('beforeend', `<div class="navfoot">${$('#status').innerHTML}<br>Latest bar: ${esc(m.data_asof)}</div>`);
  $$('#nav a').forEach(a => a.addEventListener('click', () => closeMenu()));
  const r = location.hash.replace(/^#\/?/, '').split('/')[0] || 'home';
  $$('#tabbar a[data-r]').forEach(a => { if (a.dataset.r === r) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  const mb = $('#menu-btn'); if (['c', 's', 'excluded'].includes(r)) mb.setAttribute('aria-current', 'page'); else mb.removeAttribute('aria-current');
}
function daysOld(iso) { return (Date.now() - Date.parse(iso)) / 864e5; }
function ago(iso) {
  const mins = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
  if (mins < 2) return 'just now';
  if (mins < 90) return `${mins} min ago`;
  const h = mins / 60;
  return h < 36 ? `${Math.round(h)} h ago` : `${Math.round(h / 24)} d ago`;
}
function nseOpen() {
  const ist = new Date(Date.now() + (330 + new Date().getTimezoneOffset()) * 60000);
  const d = ist.getDay(), t = ist.getHours() * 60 + ist.getMinutes();
  return d >= 1 && d <= 5 && t >= 9 * 60 + 15 && t <= 15 * 60 + 30;
}
function closeMenu() { $('#nav').classList.remove('open'); $('#scrim').hidden = true; $('#menu-btn').setAttribute('aria-expanded', 'false'); }

// ------------------------------------------------------------------ views
function setView(html) { const v = $('#view'); v.innerHTML = html; v.focus({ preventScroll: true }); window.scrollTo(0, 0); }
const loadingHTML = '<div class="loading"><div><div class="spin"></div>Loading…</div></div>';

async function viewOverview() {
  setView(loadingHTML);
  await loadAll();
  const list = allStrategies().map(s => ({ s, b: blockOf(s) })).filter(x => x.b && !x.b.error && (x.b.signal || x.b.metrics));
  const longs = list.filter(x => x.b.signal?.bias === 'long').length;
  const shorts = list.filter(x => x.b.signal?.bias === 'short').length;
  const vix = (state.live?.indices || []).find(i => i.symbol === '^INDIAVIX');
  const idx = (state.live?.indices || []).find(i => i.name === UNI_LABEL[state.uni]);
  const m = state.meta;
  const hero = `
  <div class="hero">
    <div class="tile"><div class="k">Strategies live</div><div class="v">${m.counts.implemented}</div><div class="s">${m.counts.excluded} of the book's ${m.counts.book_sections} not applicable</div></div>
    <div class="tile"><div class="k">${UNI_LABEL[state.uni]}</div><div class="v">${idx ? fmt.big(idx.last, 2) : '–'}</div><div class="s ${cls(idx?.chg_pct)}">${idx ? fmt.spct(idx.chg_pct, 2) + ' today' : ''}</div></div>
    <div class="tile"><div class="k">India VIX</div><div class="v">${vix ? fmt.n(vix.last, 2) : '–'}</div><div class="s">${vix && isNum(vix.pctile_1y) ? fmt.n(vix.pctile_1y * 100, 0) + 'th pctile (1y)' : ''}</div></div>
    <div class="tile"><div class="k">Signals long / short</div><div class="v"><span class="up">${longs}</span> <span class="muted">/</span> <span class="down">${shorts}</span></div><div class="s">strategies leaning each way</div></div>
  </div>`;
  const nonOpt = list.filter(x => x.s.category !== 'options' && isNum(x.b.metrics?.sharpe)).sort((a, b) => b.b.metrics.sharpe - a.b.metrics.sharpe).slice(0, 5);
  const opts = list.filter(x => x.s.category === 'options' && x.b.fit?.label === 'favourable').slice(0, 5);
  const mini = (rows, fn) => rows.length ? `<div class="stack" style="gap:8px">${rows.map(fn).join('')}</div>` : '<p class="muted">Nothing flagged right now.</p>';
  const rowL = (x, right) => `<a class="mrow" href="#/s/${x.s.id}"><span><span class="chip id">${x.s.id}</span> ${esc(x.s.name)}</span>${right}</a>`;
  const hi = `
  <details class="fold" id="hl" ${isMobile() ? '' : 'open'}><summary>Highlights</summary>
    <div class="grid cols-2 even">
      <div class="card"><h3>Best backtested risk-adjusted returns</h3>${mini(nonOpt, x => rowL(x, `<span class="num up">Sharpe ${fmt.n(x.b.metrics.sharpe)}</span>`))}</div>
      <div class="card"><h3>Option setups favoured by today's regime</h3>${mini(opts, x => rowL(x, biasChip(x.b.signal.bias)))}</div>
    </div></details>`;
  const pills = [['all', 'All']].concat(m.categories.map(c => [c.id, c.label]));
  const SORTS = [['sharpe', 'Sharpe'], ['perf', 'Backtest return'], ['dd', 'Max drawdown'], ['hit', 'Hit rate'], ['id', 'Book section']];
  setView(`
    <div class="page-head"><div><h1>Signal board · ${UNI_LABEL[state.uni]}</h1>
      <p>Every applicable strategy from <i>151 Trading Strategies</i> on live Yahoo Finance data. Tap one for its chart, portfolio and method.</p></div></div>
    ${hero}${hi}
    <div class="toolbar">
      <input type="search" id="q" placeholder="Search strategies…" value="${esc(state.filter.q)}" aria-label="Search strategies">
      <select id="sortsel" class="only-m" aria-label="Sort by">${SORTS.map(([k, l]) => `<option value="${k}" ${state.sort.key === k ? 'selected' : ''}>Sort: ${l}</option>`).join('')}</select>
    </div>
    <div class="pills scroll" id="cat-pills">${pills.map(([id, l]) => `<button class="pill" type="button" data-cat="${id}" aria-pressed="${state.filter.cat === id}">${esc(l)}</button>`).join('')}</div>
    <div class="tbl-wrap only-d" style="margin-top:12px"><table id="board"></table></div>
    <div class="blist only-m" id="blist"></div>
    <div class="center" id="boardmore"></div>
    <div class="legend"><span>vp = volatility points</span><span>Sharpe is annualised</span><span>Option rows: monthly-roll backtest on theoretical prices</span></div>`);
  state.boardLimit = 20;
  const draw = () => {
    const q = state.filter.q.trim().toLowerCase();
    let rows = list.filter(x => (state.filter.cat === 'all' || x.s.category === state.filter.cat) &&
      (!q || (x.s.id + ' ' + x.s.name + ' ' + (x.b.signal?.label || '')).toLowerCase().includes(q)));
    const key = state.sort.key, dir = state.sort.dir;
    const val = x => key === 'id' ? x.s.id.split('.').map(Number).reduce((a, n, i) => a + n / Math.pow(1000, i), 0)
      : key === 'name' ? x.s.name.toLowerCase() : key === 'perf' ? perfCell(x.s, x.b).val : key === 'dd' ? x.b.metrics?.max_dd
      : key === 'hit' ? x.b.metrics?.hit_rate : x.b.metrics?.sharpe;
    rows = rows.slice().sort((a, b) => { const va = val(a), vb = val(b); if (va == null) return 1; if (vb == null) return -1; return va < vb ? -dir : va > vb ? dir : 0; });
    const shown = rows.slice(0, state.boardLimit);
    const th = (k, label, r) => `<th class="sortable ${r ? 'r' : ''}" data-k="${k}" aria-sort="${state.sort.key === k ? (dir > 0 ? 'ascending' : 'descending') : 'none'}">${label}${state.sort.key === k ? `<span class="arr">${dir > 0 ? '▲' : '▼'}</span>` : ''}</th>`;
    $('#board').innerHTML = `<thead><tr>${th('id', 'ID')}${th('name', 'Strategy')}<th>Signal now</th>${th('perf', 'Backtest return', 1)}${th('sharpe', 'Sharpe', 1)}${th('dd', 'Max DD', 1)}${th('hit', 'Hit rate', 1)}<th></th></tr></thead><tbody>${shown.map(x => {
      const p = perfCell(x.s, x.b), mm = x.b.metrics || {};
      return `<tr class="click" data-id="${x.s.id}" tabindex="0"><td><span class="chip id">${x.s.id}</span></td><td class="wrap"><b>${esc(x.s.name)}</b> ${statusChip(x.s)}</td>
        <td class="sig">${x.b.signal ? biasChip(x.b.signal.bias) + ' ' + esc(x.b.signal.label.length > 90 ? x.b.signal.label.slice(0, 88) + '…' : x.b.signal.label) : '–'}</td>
        <td class="r ${p.cls}">${p.text}</td><td class="r ${cls(mm.sharpe)}">${fmt.n(mm.sharpe)}</td><td class="r">${ddCell(x.b)}</td><td class="r">${isNum(mm.hit_rate) ? fmt.pct(mm.hit_rate, 0) : '–'}</td>
        <td>${x.b.curve ? spark(x.b.curve.strategy, 80, 24) : ''}</td></tr>`;
    }).join('') || '<tr><td colspan="8" class="empty">No strategies match.</td></tr>'}</tbody>`;
    $('#blist').innerHTML = shown.map(x => {
      const p = perfCell(x.s, x.b), mm = x.b.metrics || {};
      const sg = x.b.signal ? esc(x.b.signal.label.length > 70 ? x.b.signal.label.slice(0, 68) + '…' : x.b.signal.label) : '';
      return `<a class="brow" href="#/s/${x.s.id}"><div class="l1"><span class="chip id">${x.s.id}</span><b>${esc(x.s.name)}</b>${statusChip(x.s)}</div>
        <div class="l2">${x.b.signal ? biasChip(x.b.signal.bias) : ''}<span>${sg}</span></div>
        <div class="l3"><span><i>Sharpe</i><b class="${cls(mm.sharpe)}">${fmt.n(mm.sharpe)}</b></span><span><i>Return</i><b class="${p.cls}">${p.text}</b></span><span><i>Max DD</i><b>${ddCell(x.b)}</b></span>${x.b.curve ? spark(x.b.curve.strategy, 64, 22) : ''}</div></a>`;
    }).join('') || '<p class="empty">No strategies match.</p>';
    $('#boardmore').innerHTML = rows.length > shown.length
      ? `<button class="btn" type="button" id="more-btn">Show ${Math.min(20, rows.length - shown.length)} more <span class="muted">(${rows.length - shown.length} left)</span></button>` : (rows.length ? `<span class="muted">${rows.length} strategies</span>` : '');
    $('#more-btn')?.addEventListener('click', () => { state.boardLimit += 20; draw(); });
    $$('#board th.sortable').forEach(h => h.addEventListener('click', () => {
      const k = h.dataset.k; state.sort = state.sort.key === k ? { key: k, dir: -state.sort.dir } : { key: k, dir: k === 'id' || k === 'name' ? 1 : -1 }; state.boardLimit = 20; draw();
    }));
    $$('#board tr.click').forEach(r => {
      const go = () => { location.hash = '#/s/' + r.dataset.id; };
      r.addEventListener('click', go); r.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
    });
  };
  draw();
  $('#q').addEventListener('input', e => { state.filter.q = e.target.value; state.boardLimit = 20; draw(); });
  $('#sortsel').addEventListener('change', e => { const k = e.target.value; state.sort = { key: k, dir: k === 'id' ? 1 : -1 }; state.boardLimit = 20; draw(); });
  $$('#cat-pills .pill').forEach(p => p.addEventListener('click', () => { state.filter.cat = p.dataset.cat; state.boardLimit = 20; $$('#cat-pills .pill').forEach(x => x.setAttribute('aria-pressed', x === p)); draw(); }));
}

async function viewCategory(cat) {
  setView(loadingHTML);
  const d = await loadCat(cat);
  const c = state.meta.categories.find(x => x.id === cat);
  const items = d.strategies;
  const isOpt = cat === 'options';
  const OUT = [['all', 'All'], ['bullish', 'Bullish'], ['bearish', 'Bearish'], ['neutral', 'Neutral'], ['long', 'Long vol'], ['short', 'Short vol'], ['fav', 'Favoured now']];
  let limit = 12;
  const draw = () => {
    let rows = items;
    if (isOpt && state.optFilter !== 'all') {
      const f = state.optFilter;
      rows = rows.filter(s => f === 'bullish' || f === 'bearish' || f === 'neutral' ? s.outlook === f : f === 'long' || f === 'short' ? s.vol_view === f : blockOf(s)?.fit?.label === 'favourable');
    }
    const shown = rows.slice(0, limit);
    $('#cards').innerHTML = shown.map(s => {
      const b = blockOf(s) || {}, m = b.metrics || {}, p = perfCell(s, b);
      return `<a class="scard" href="#/s/${s.id}"><div class="top"><span class="chip id">${s.id}</span><span>${statusChip(s)} ${b.signal ? biasChip(b.signal.bias) : ''}</span></div>
        <div class="nm">${esc(s.name)}</div><div class="sg">${esc(b.error ? 'Failed to compute in the latest run' : (b.signal?.label || (b.notes?.[0] || 'No data')))}</div>
        <div class="row"><div class="kv"><div><span>Return</span><b class="${p.cls}">${p.val == null ? '–' : (isNum(m.cagr) ? fmt.spct(m.cagr) : fmt.sn(m.avg) + '/mo')}</b></div><div><span>Sharpe</span><b class="${cls(m.sharpe)}">${fmt.n(m.sharpe)}</b></div></div>${b.curve ? spark(b.curve.strategy) : ''}</div></a>`;
    }).join('') || '<p class="empty">No strategies in this view.</p>';
    $('#more').innerHTML = rows.length > shown.length ? `<button class="btn" type="button" id="more-btn">Show ${Math.min(12, rows.length - shown.length)} more <span class="muted">(${rows.length - shown.length} left)</span></button>` : `<span class="muted">${rows.length} strategies</span>`;
    $('#more-btn')?.addEventListener('click', () => { limit += 12; draw(); });
  };
  setView(`<div class="page-head"><div><h1>${esc(c.label)} · ${UNI_LABEL[state.uni]}</h1><p>${esc(c.blurb)}</p></div></div>
    ${isOpt ? `<div class="pills scroll" id="opt-pills">${OUT.map(([id, l]) => `<button class="pill" data-f="${id}" aria-pressed="${state.optFilter === id}" type="button">${l}</button>`).join('')}</div>` : ''}
    <div class="cards" id="cards" style="margin-top:12px"></div><div class="center" id="more"></div>`);
  draw();
  $$('#opt-pills .pill').forEach(p => p.addEventListener('click', () => { state.optFilter = p.dataset.f; limit = 12; $$('#opt-pills .pill').forEach(x => x.setAttribute('aria-pressed', x === p)); draw(); }));
}

async function viewStrategy(id) {
  setView(loadingHTML);
  let s = state.byId[id];
  if (!s) {
    const r = state.registry.items.find(x => x.id === id);
    if (!r || !r.category) { location.hash = '#/excluded'; return; }
    await loadCat(r.category);
    s = state.byId[id];
  }
  if (!s) { setView('<p class="empty">Strategy not found.</p>'); return; }
  const cat = state.meta.categories.find(c => c.id === s.category);
  const siblings = state.cats[s.category].strategies;
  const i = siblings.findIndex(x => x.id === id);
  const prev = siblings[i - 1], next = siblings[i + 1];
  const b = blockOf(s);
  const head = `
    <div class="crumbs"><a href="#/c/${s.category}">${esc(cat.label)}</a> › <span class="chip id">${s.id}</span>
      <span style="margin-left:auto" class="nav-btns">${prev ? `<a class="btn" href="#/s/${prev.id}" aria-label="Previous strategy">← ${prev.id}</a>` : ''}${next ? `<a class="btn" href="#/s/${next.id}" aria-label="Next strategy">${next.id} →</a>` : ''}</span></div>
    <div class="page-head"><div><h1>${esc(s.name)} ${statusChip(s)}</h1><p>${esc(s.desc)}</p>
      ${s.adapted_note ? `<p style="margin-top:6px"><span class="chip ${s.status}">${s.status === 'proxy' ? 'PROXY DATA' : 'ADAPTED'}</span> <span class="muted">${esc(s.adapted_note)}</span></p>` : ''}</div>
      <div class="muted">${UNI_LABEL[state.uni]}${s.outlook ? ` · ${esc(s.outlook)} · ${esc(s.style)}` : ''}</div></div>`;
  if (!b) { setView(head + `<p class="err">No results for ${UNI_LABEL[state.uni]} (module error – see Method &amp; data).</p>`); return; }
  if (b.error) { setView(head + `<p class="err">This strategy failed to compute in the latest run for ${UNI_LABEL[state.uni]}: ${esc(b.error)}</p>`); return; }

  const sig = b.signal;
  const sigHTML = sig ? `<div class="signalbar ${(BIAS[sig.bias] || BIAS.neutral)[1]}">${biasChip(sig.bias)}<div><div class="lbl">${esc(sig.label)}</div>${sig.detail ? `<div class="det">${esc(sig.detail)}</div>` : ''}</div></div>` : '';
  const isOpt = !!b.payoff;
  const benchLabel = isOpt ? 'Index monthly % move (cumulative)' : `${UNI_LABEL[state.uni]} buy & hold`;
  const neutral = isNum(b.metrics?.beta) && Math.abs(b.metrics.beta) < 0.3 && !isOpt;
  const panels = [];

  const eqCard = (hint) => `<div class="card"><div class="chart-head"><h3>${isOpt ? 'Historical monthly-roll backtest' : 'Backtest'}</h3>
      <div class="toggles">${/cumul/i.test(b.curve_units || '') ? '' : '<label><input type="checkbox" id="logscale"> Log scale</label>'}<span class="sub">${esc(b.curve_units || 'growth of 100')}${hint}</span></div></div>
      <div class="chartbox"><canvas id="c-eq" role="img" aria-label="Strategy equity curve"></canvas></div></div>`;
  const initEq = () => {
    if (!b.curve) return;
    const cv = $('#c-eq');
    let ch = drawEquity(cv, b.curve, { units: b.curve_units, benchLabel, neutral });
    const lg = $('#logscale');
    if (lg) lg.addEventListener('change', () => { state.charts = state.charts.filter(c => c !== ch); ch.destroy(); ch = drawEquity(cv, b.curve, { units: b.curve_units, benchLabel, neutral, log: lg.checked }); });
  };

  if (isOpt) {
    const st = b.stats;
    const T = (k, v, sub, c = '') => `<div class="tile"><div class="k">${k}</div><div class="v ${c}">${v}</div>${sub ? `<div class="s">${sub}</div>` : ''}</div>`;
    const prem = st.net_premium;
    panels.push({
      id: 'payoff', label: 'Payoff',
      html: `<div class="grid cols-2"><div class="card"><div class="chart-head"><h3>Payoff at expiry (${state.meta.assumptions.option_horizon_days}d)</h3><span class="sub">Black-Scholes · IV = India VIX ${fmt.n(b.fit.vix, 1)}%</span></div><div class="chartbox"><canvas id="c-payoff" role="img" aria-label="Option payoff diagram"></canvas></div></div>
      <div class="card"><h3>Setup now</h3><div class="tiles compact">
        ${T(prem >= 0 ? 'Net debit' : 'Net credit', fmt.big(Math.abs(prem), 0), 'pts · ' + fmt.n(Math.abs(st.net_premium_pct), 2) + '% of spot')}
        ${T('Max profit', st.max_profit == null ? 'Unlimited' : fmt.big(st.max_profit), st.max_profit == null ? '' : 'pts · ' + fmt.n(st.max_profit / b.payoff.spot * 100, 2) + '% of spot', 'up')}
        ${T('Max loss', st.max_loss == null ? 'Unlimited' : (st.riskless ? 'None' : fmt.big(st.max_loss)), st.max_loss == null || st.riskless ? '' : 'pts · ' + fmt.n(st.max_loss / b.payoff.spot * 100, 2) + '% of spot', 'down')}
        ${T('Breakeven' + (st.breakevens.length > 1 ? 's' : ''), st.breakevens.length ? st.breakevens.map(x => fmt.big(x)).join('<br>') : '–')}
        ${T('Prob. of profit', fmt.pct(st.pop, 0), 'risk-neutral')}
        ${T('Delta', fmt.sn(st.delta), 'per index unit')}
      </div><details class="fold inner"><summary>Greeks &amp; regime</summary><div class="tiles compact">
        ${T('Gamma', fmt.sn(st.gamma, 3), 'Δ per +1% move')}
        ${T('Vega', fmt.sn(st.vega, 1), 'pts / vol point')}
        ${T('Theta', fmt.sn(st.theta, 1), 'pts / day')}
        ${T('IV rank', fmt.n(b.fit.iv_rank, 0) + '%', 'VIX vs 1y range')}
        ${T('Trend', esc(b.fit.trend), 'vs 50/200-day avg')}
      </div></details></div></div>`,
      init: () => drawPayoff($('#c-payoff'), b.payoff),
    });
    if (b.tables?.length) panels.push({ id: 'legs', label: 'Legs', html: b.tables.map(t => renderTable(t, true, 12)).join('') });
    if (b.curve) panels.push({ id: 'bt', label: 'Backtest', html: `<div class="stack">${eqCard(' · IV = India VIX at entry')}<div class="card"><h3>Backtest statistics</h3>${metricTiles(b)}</div></div>`, init: initEq });
  } else {
    if (b.curve) {
      panels.push({
        id: 'perf', label: 'Performance',
        html: `<div class="grid cols-2">${eqCard(' · click legend to show/hide lines')}<div class="card"><h3>Key metrics</h3>${metricTiles(b, true)}</div></div>`,
        init: initEq,
      });
    } else if (b.metrics) {
      panels.push({ id: 'perf', label: 'Metrics', html: `<div class="card"><h3>Live metrics</h3>${metricTiles(b)}</div>` });
    }
    if (b.tables?.length) panels.push({ id: 'port', label: 'Portfolio', html: `<div class="stack">${b.tables.map(t => renderTable(t)).join('')}</div>` });
    if (b.charts?.length) panels.push({
      id: 'charts', label: 'Charts',
      html: `<div class="stack">${b.charts.map((c, k) => `<div class="card"><div class="chart-head"><h3>${esc(c.title)}</h3></div><div class="chartbox sm"><canvas id="c-x${k}"></canvas></div></div>`).join('')}</div>`,
      init: () => b.charts.forEach((c, k) => drawGeneric($('#c-x' + k), c)),
    });
  }
  if (b.notes?.length) panels.push({ id: 'how', label: 'How it works', html: `<div class="card"><h3>Method &amp; caveats</h3><div class="notes">${b.notes.map(n => `<p>${esc(n)}</p>`).join('')}</div></div>` });

  setView(head + `<div class="stack">${sigHTML}<div>${tabsHTML(panels)}</div></div>`);
  if (panels.length) wireTabs(panels);
}

async function viewMarket() {
  const live = state.live;
  if (!live) { setView('<p class="err">Live snapshot unavailable.</p>'); return; }
  const card = i => {
    const isV = i.symbol === '^INDIAVIX';
    const sp = i.intraday?.c?.length > 5 ? i.intraday.c : i.spark;
    const rr = (l, v) => `<div style="display:flex;justify-content:space-between"><span class="muted">${l}</span><span class="num ${isV ? '' : cls(v)}">${isV ? fmt.n(v * 100, 1) + '%' : fmt.spct(v)}</span></div>`;
    return `<div class="card idx-card"><div style="display:flex;justify-content:space-between;align-items:center"><h3>${esc(i.name)}</h3><span class="muted" style="font-size:11px">${i.intraday?.c?.length > 5 ? 'intraday' : 'last 90 days'}</span></div>
      <div><div class="big">${fmt.big(i.last, 2)}</div><div class="num ${isV ? (i.chg_pct > 0 ? 'down' : 'up') : cls(i.chg_pct)}">${fmt.sn(i.chg, 2)} (${fmt.spct(i.chg_pct, 2)})</div></div>
      ${spark(sp, 260, 56)}
      <div class="stack" style="gap:3px;font-size:12.5px">${rr('1 week', i.ret_1w)}${rr('1 month', i.ret_1m)}${rr('6 months', i.ret_6m)}${rr('1 year', i.ret_1y)}${rr('From 52-week high', i.from_hi)}
      ${isNum(i.vs_dma200) ? rr('vs 200-day average', i.vs_dma200) : ''}${isV && isNum(i.pctile_1y) ? `<div style="display:flex;justify-content:space-between"><span class="muted">1-year percentile</span><span class="num">${fmt.n(i.pctile_1y * 100, 0)}th</span></div>` : ''}</div></div>`;
  };
  const inU = s => state.uni === 'NIFTY50' ? s.in_nifty : s.in_sensex;
  const stocks = live.stocks.filter(inU);
  const col = v => {
    const t = Math.max(-1, Math.min(1, v / 0.03));
    return t >= 0 ? `rgba(16,185,129,${0.18 + 0.62 * t})` : `rgba(239,68,68,${0.18 + 0.62 * -t})`;
  };
  const bySec = {};
  stocks.forEach(s => (bySec[s.sector] ||= []).push(s));
  const heat = Object.keys(bySec).sort().map(sec => `<div class="sec-h">${esc(sec)}</div><div class="heat">${bySec[sec].sort((a, b) => b.chg_pct - a.chg_pct).map(s =>
    `<div class="hcell" style="background:${col(s.chg_pct)}" title="${esc(s.name)} · ${fmt.big(s.last, 2)}"><b>${esc(s.key)}</b><span>${fmt.spct(s.chg_pct, 2)}</span></div>`).join('')}</div>`).join('');
  state.mktSort = state.mktSort || { k: 'chg_pct', d: -1 };
  const drawStocks = () => {
    const { k, d } = state.mktSort;
    const rows = stocks.slice().sort((a, b) => { const x = a[k], y = b[k]; if (x == null) return 1; if (y == null) return -1; return typeof x === 'string' ? d * x.localeCompare(y) : d * (x - y); });
    const th = (key, l, r, hm) => `<th class="sortable ${r ? 'r' : ''} ${hm ? 'hide-m' : ''}" data-k="${key}">${l}${k === key ? `<span class="arr">${d > 0 ? '▲' : '▼'}</span>` : ''}</th>`;
    $('#stk').innerHTML = `<thead><tr>${th('name', 'Stock')}${th('sector', 'Sector', 0, 1)}${th('last', 'Price ₹', 1)}${th('chg_pct', '1D', 1)}${th('ret_1m', '1M', 1)}${th('ret_6m', '6M', 1, 1)}${th('ret_1y', '1Y', 1, 1)}${th('pb', 'P/B', 1, 1)}${th('mcap', 'Mkt cap', 1, 1)}</tr></thead><tbody>${rows.map(s =>
      `<tr><td><b>${esc(s.name)}</b> <span class="muted hide-m">${esc(s.symbol)}</span></td><td class="hide-m">${esc(s.sector)}</td><td class="r">${fmt.big(s.last, 2)}</td><td class="r ${cls(s.chg_pct)}">${fmt.spct(s.chg_pct)}</td><td class="r ${cls(s.ret_1m)}">${fmt.spct(s.ret_1m)}</td>
      <td class="r hide-m ${cls(s.ret_6m)}">${fmt.spct(s.ret_6m)}</td><td class="r hide-m ${cls(s.ret_1y)}">${fmt.spct(s.ret_1y)}</td><td class="r hide-m">${fmt.n(s.pb, 2)}</td><td class="r hide-m">${fmt.cr(s.mcap)}</td></tr>`).join('')}</tbody>`;
    $$('#stk th.sortable').forEach(h => h.addEventListener('click', () => { const kk = h.dataset.k; state.mktSort = state.mktSort.k === kk ? { k: kk, d: -state.mktSort.d } : { k: kk, d: kk === 'name' || kk === 'sector' ? 1 : -1 }; drawStocks(); }));
  };
  const panels = [
    { id: 'idx', label: 'Indexes', html: `<div class="grid cols-3">${live.indices.map(card).join('')}</div>` },
    { id: 'heat', label: 'Heatmap', html: `<div class="card"><h3>${UNI_LABEL[state.uni]} constituents · today's move</h3>${heat}</div>` },
    { id: 'stk', label: 'Stocks', html: `<div class="tbl-wrap"><div class="tbl-scroll"><table id="stk"></table></div></div>`, init: drawStocks },
  ];
  setView(`<div class="page-head"><div><h1>Market now</h1><p>Latest Yahoo Finance bars (delayed) as of ${esc(state.meta.data_asof)}, refreshed by GitHub Actions every 30 minutes while the NSE is open.</p></div></div>${tabsHTML(panels)}`);
  wireTabs(panels);
}

function viewExcluded() {
  const items = state.registry.items;
  const chs = state.registry.chapters;
  const byCh = {};
  items.forEach(i => (byCh[i.chapter] ||= []).push(i));
  const total = items.length, ex = items.filter(i => i.status === 'excluded').length;
  const full = [];
  const blocks = Object.keys(byCh).map(Number).sort((a, b) => a - b).map(ch => {
    const its = byCh[ch], bad = its.filter(i => i.status === 'excluded'), n = its.length - bad.length;
    if (!bad.length) { full.push(`${ch}. ${chs[ch]} (${n})`); return ''; }
    return `<details class="fold"><summary>${ch}. ${esc(chs[ch])} <span class="muted">· ${bad.length} not applicable${n ? `, ${n} applied` : ''}</span></summary>
      <div class="exlist">${bad.map(i => `<div class="exrow"><div><span class="chip id">${i.id}</span> <b>${esc(i.name)}</b></div><p>${esc(i.reason)}</p></div>`).join('')}</div></details>`;
  }).join('');
  setView(`<div class="page-head"><div><h1>Not applicable</h1><p>The book covers ${total} sections. ${ex} cannot be run against the NIFTY 50 / SENSEX with Yahoo Finance data, so they are <b>not</b> included – each with its reason. The other ${total - ex} are live${full.length ? ` (fully covered: ${full.map(esc).join(', ')})` : ''}.</p></div></div>
    <div class="legend"><span><span class="chip adapted">ADAPTED</span> method kept, factors/asset adjusted for India</span><span><span class="chip proxy">PROXY DATA</span> related series stands in for data Yahoo lacks</span></div>
    <div class="stack">${blocks}</div>`);
}

function viewAbout() {
  const m = state.meta, a = m.assumptions;
  const fails = m.failed_tickers?.length ? `<p class="err">Tickers Yahoo Finance did not return this run: ${m.failed_tickers.map(esc).join(', ')}.</p>` : '';
  const errs = m.errors?.length ? `<p class="err">Strategy errors: ${m.errors.map(e => esc(e.module + '/' + e.universe + ': ' + e.error)).join('; ')}</p>` : '';
  const sec = (title, html, open) => `<details class="fold" ${open ? 'open' : ''}><summary>${title}</summary><div class="notes pad">${html}</div></details>`;
  setView(`<div class="page-head"><div><h1>Method &amp; data</h1><p>How the numbers on this site are produced.</p></div></div>
  <div class="stack">
    ${sec('Run status', `<dl class="kvlist"><dt>Generated</dt><dd>${esc(m.generated_at)}</dd><dt>Latest bar</dt><dd>${esc(m.data_asof)}</dd><dt>Strategies implemented</dt><dd>${m.counts.implemented}</dd>
      <dt>of which adapted / proxy</dt><dd>${m.counts.adapted_or_proxy}</dd><dt>Not applicable</dt><dd>${m.counts.excluded}</dd><dt>Synthetic data?</dt><dd>${m.synthetic ? 'YES (test only)' : 'no'}</dd></dl>${fails}${errs}`, true)}
    ${sec('Data & refresh', `<p><b>Source:</b> Yahoo Finance via <code>yfinance</code> — daily adjusted OHLCV for ${m.universes.NIFTY50.constituents} NIFTY 50 and ${m.universes.SENSEX30.constituents} SENSEX stocks, both indexes, India VIX, NSE sector indexes and gold/silver/Nasdaq ETFs, plus P/B and market cap snapshots (about ${a.history_years} years of history).</p>
      <p><b>Refresh:</b> a GitHub Actions workflow re-downloads everything every 30 minutes during NSE hours (and once after the close), recomputes every strategy and redeploys to GitHub Pages. The latest daily bar is the still-forming session bar while the market is open. Yahoo data is delayed.</p>
      <p><b>Universe:</b> constituent lists are a static snapshot in <code>pipeline/universe.py</code>; edit it when the indexes rebalance. Delisted or renamed tickers are skipped automatically.</p>`)}
    ${sec('Backtest rules', `<p>Positions are decided at a close and held from the next day. Cross-sectional portfolios use the top/bottom ${(a.xs_fraction * 100).toFixed(0)}% of names and are dollar-neutral where the book says so. Costs: ${a.cost_bps} bps one-way. No slippage, borrow, margin or tax. Results are walk-forward; fundamentals (P/B) have no history on Yahoo so Value is a live ranking only.</p>`)}
    ${sec('Options & futures', `<p><b>Options:</b> Yahoo has no Indian index option chains, so every option strategy is priced with Black-Scholes using spot, a flat implied volatility equal to India VIX (also used for SENSEX), r = ${(a.risk_free * 100).toFixed(1)}% and dividend yield ${(a.dividend_yield * 100).toFixed(1)}%. Strikes are multiples of 50 (NIFTY) / 100 (SENSEX); offsets are about 1% of spot; expiry ${a.option_horizon_days} days (60 for the far leg of calendar/diagonal spreads). The backtest rolls each structure monthly. These are model prices, not tradable quotes.</p>
      <p><b>Futures:</b> no futures prices on Yahoo, so hedging and futures strategies use the cash series as proxy (marked <span class="chip proxy">PROXY DATA</span>).</p>`)}
    ${sec('Disclaimer', `<p>Educational research project, not investment advice, and not affiliated with the book's authors or any exchange. Simulated results are hypothetical; real trading involves costs, taxes, liquidity limits and risks not captured here. Shorting and derivatives can lose more than the capital invested.</p>`)}
  </div>`);
}

// ------------------------------------------------------------------ router
async function route() {
  clearCharts();
  renderChrome();
  const h = location.hash.replace(/^#\/?/, '');
  const [a, b] = h.split('/');
  try {
    if (!a) await viewOverview();
    else if (a === 'market') await viewMarket();
    else if (a === 'c' && b) await viewCategory(b);
    else if (a === 's' && b) await viewStrategy(decodeURIComponent(h.slice(2)));
    else if (a === 'excluded') viewExcluded();
    else if (a === 'about') viewAbout();
    else await viewOverview();
  } catch (e) {
    console.error(e);
    setView(`<p class="err">Something went wrong loading this view: ${esc(e.message)}</p>`);
  }
}

// ------------------------------------------------------------------ PWA: install, share, offline
let deferredInstall = null;
function toast(msg) {
  const t = document.createElement('div'); t.className = 'toast'; t.setAttribute('role', 'status'); t.textContent = msg;
  document.body.appendChild(t); setTimeout(() => t.remove(), 4500);
}
function setupPWA() {
  const standalone = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone;
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream;
  const inst = $('#install-btn');
  if (!standalone && ios) inst.hidden = false;           // iOS has no install prompt: show the manual hint
  window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); deferredInstall = e; if (!standalone) inst.hidden = false; });
  window.addEventListener('appinstalled', () => { inst.hidden = true; deferredInstall = null; toast('Installed – find it on your home screen'); });
  inst.addEventListener('click', async () => {
    if (deferredInstall) { deferredInstall.prompt(); await deferredInstall.userChoice; deferredInstall = null; inst.hidden = true; }
    else toast('On iPhone/iPad: tap the Share icon in Safari, then “Add to Home Screen”.');
  });
  $('#share-btn').addEventListener('click', async () => {
    const data = { title: '151 Trading Strategies · NIFTY & SENSEX', text: document.title, url: location.href };
    try {
      if (navigator.share) await navigator.share(data);
      else { await navigator.clipboard.writeText(location.href); toast('Link copied'); }
    } catch (e) { if (e.name !== 'AbortError') toast('Could not share – copy the address bar link instead'); }
  });
  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
    navigator.serviceWorker.register('sw.js').catch(e => console.warn('service worker failed', e));
  }
  window.addEventListener('offline', () => toast('You are offline – showing the last saved data'));
}

async function init() {
  setupChartDefaults();
  setupPWA();
  $('#menu-btn').addEventListener('click', () => { const o = $('#nav').classList.toggle('open'); $('#scrim').hidden = !o; $('#menu-btn').setAttribute('aria-expanded', o); });
  $('#scrim').addEventListener('click', closeMenu);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeMenu(); });
  document.addEventListener('click', e => {
    const b = e.target.closest('.show-all'); if (!b) return;
    b.closest('.tbl-wrap').querySelectorAll('tr.more').forEach(r => { r.hidden = false; }); b.closest('.tbl-foot').remove();
  });
  try {
    state.meta = await getJSON('meta', true);
    VERSION = state.meta.generated_at;
    [state.live, state.registry] = await Promise.all([getJSON('live'), getJSON('registry')]);
  } catch (e) {
    $('#view').innerHTML = `<div class="empty"><h2>No data yet</h2><p style="margin-top:8px">The data files have not been generated. Run <code>python -m pipeline.run</code> or trigger the <b>Refresh &amp; Deploy</b> GitHub Actions workflow.</p><p class="muted" style="margin-top:8px">${esc(e.message)}</p></div>`;
    return;
  }
  window.addEventListener('hashchange', route);
  route();
  setInterval(() => { if (state.meta) { renderChrome(); } }, 60000);
}
init();
})();
