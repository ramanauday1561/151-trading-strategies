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
  sort: { key: 'm1', dir: -1 },
  filter: { cat: 'all', q: '' },
  optFilter: 'all',
};
if (!UNI_LABEL[state.uni]) state.uni = 'NIFTY50';

// ------------------------------------------------------------------ data
let VERSION = '';
async function getJSON(name, fresh = false) {
  let lastErr;
  for (let attempt = 0; attempt < 4; attempt++) {
    // first try uses the versioned URL (cacheable); retries bypass every cache
    const url = `data/${name}.json` + (fresh || !VERSION || attempt ? `?t=${Date.now()}` : `?v=${encodeURIComponent(VERSION)}`);
    try {
      const r = await fetch(url, fresh || attempt ? { cache: 'no-store' } : undefined);
      if (!r.ok) throw new Error(`${name}.json: HTTP ${r.status}`);
      return await r.json();
    } catch (e) {
      lastErr = e;
      await new Promise(res => setTimeout(res, 400 * (attempt + 1)));
    }
  }
  throw lastErr;
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
function recent(s, b) {
  const m = b?.metrics || {};
  let m1, m3, unit = '%';
  if (isNum(m.ret_1m)) { m1 = m.ret_1m * 100; m3 = m.ret_3m * 100; }
  else if (isNum(m.last)) { m1 = m.last; m3 = m.last3; if (/vol/i.test(b.curve_units || '')) unit = ' vp'; }
  else return null;
  const st = m1 > 0 && m3 > 0 ? 'working' : m1 < 0 && m3 < 0 ? 'struggling' : 'mixed';
  return { m1, m3, st, unit };
}
const REC_CHIP = { working: ['WORKING', 'up'], struggling: ['STRUGGLING', 'down'], mixed: ['MIXED', 'flat'] };
function recChip(s, b) { const r = recent(s, b); if (!r) return ''; const [t, c] = REC_CHIP[r.st]; return `<span class="chip ${c}" title="Last month ${fmt.sn(r.m1, 1)}${r.unit}, last 3 months ${fmt.sn(r.m3, 1)}${r.unit}">${t}</span>`; }
const saved = {
  set: new Set((() => { try { return JSON.parse(store.get('saved', '[]')); } catch (e) { return []; } })()),
  toggle(id) { this.set.has(id) ? this.set.delete(id) : this.set.add(id); store.set('saved', JSON.stringify([...this.set])); },
};
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
  const link = (h, label, count) => `<a href="${h}" ${cur === h || (h === '#/' && (cur === '' || cur === '#' || cur === '#/signal')) ? 'aria-current="page"' : ''}>${label}${count != null ? `<span class="count">${count}</span>` : ''}</a>`;
  $('#nav').innerHTML = `
    ${link('#/', 'Signal (CALL / PUT)')}
    ${link('#/board', 'Strategy board', m.counts.implemented)}
    ${link('#/play', "Today's playbook")}
    ${link('#/now', 'Working now')}
    ${link('#/market', 'Market now')}
    <div class="grp">Strategies</div>
    ${cats.map(c => link('#/c/' + c.id, esc(c.label), c.count)).join('')}
    <div class="grp">Reference</div>
    ${link('#/excluded', 'Not applicable', m.counts.excluded)}
    ${link('#/about', 'Method & data')}`;
  $('#nav').insertAdjacentHTML('beforeend', `<div class="navfoot">${$('#status').innerHTML}<br>Latest bar: ${esc(m.data_asof)}</div>`);
  $$('#nav a').forEach(a => a.addEventListener('click', () => closeMenu()));
  let r = location.hash.replace(/^#\/?/, '').split('/')[0] || 'home';
  if (r === 'signal') r = 'home';
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
  const pills = [['all', 'All'], ['saved', `★ Saved${saved.set.size ? ' (' + saved.set.size + ')' : ''}`]].concat(m.categories.map(c => [c.id, c.label]));
  const SORTS = [['m1', 'Last month'], ['sharpe', 'Sharpe'], ['perf', 'Backtest return'], ['dd', 'Max drawdown'], ['hit', 'Hit rate'], ['id', 'Book section']];
  setView(`
    <div class="page-head"><div><h1>Signal board · ${UNI_LABEL[state.uni]}</h1>
      <p>Every applicable strategy from <i>151 Trading Strategies</i> on live Yahoo Finance data. Tap one for its chart, portfolio and method.</p></div></div>
    <a class="promo" href="#/play"><b>Today's playbook</b><span>All strategies combined: stance, stocks, options, risk →</span></a>
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
    let rows = list.filter(x => (state.filter.cat === 'all' || (state.filter.cat === 'saved' ? saved.set.has(x.s.id) : x.s.category === state.filter.cat)) &&
      (!q || (x.s.id + ' ' + x.s.name + ' ' + (x.b.signal?.label || '')).toLowerCase().includes(q)));
    const key = state.sort.key, dir = state.sort.dir;
    const val = x => key === 'id' ? x.s.id.split('.').map(Number).reduce((a, n, i) => a + n / Math.pow(1000, i), 0)
      : key === 'name' ? x.s.name.toLowerCase() : key === 'perf' ? perfCell(x.s, x.b).val : key === 'dd' ? x.b.metrics?.max_dd
      : key === 'hit' ? x.b.metrics?.hit_rate : key === 'm1' ? (recent(x.s, x.b)?.unit === '%' ? recent(x.s, x.b).m1 : null) : x.b.metrics?.sharpe;
    rows = rows.slice().sort((a, b) => { const va = val(a), vb = val(b); if (va == null) return 1; if (vb == null) return -1; return va < vb ? -dir : va > vb ? dir : 0; });
    const shown = rows.slice(0, state.boardLimit);
    const th = (k, label, r) => `<th class="sortable ${r ? 'r' : ''}" data-k="${k}" aria-sort="${state.sort.key === k ? (dir > 0 ? 'ascending' : 'descending') : 'none'}">${label}${state.sort.key === k ? `<span class="arr">${dir > 0 ? '▲' : '▼'}</span>` : ''}</th>`;
    $('#board').innerHTML = `<thead><tr>${th('id', 'ID')}${th('name', 'Strategy')}<th>Signal now</th>${th('perf', 'Backtest return', 1)}${th('sharpe', 'Sharpe', 1)}${th('dd', 'Max DD', 1)}${th('hit', 'Hit rate', 1)}<th></th></tr></thead><tbody>${shown.map(x => {
      const p = perfCell(x.s, x.b), mm = x.b.metrics || {};
      return `<tr class="click" data-id="${x.s.id}" tabindex="0"><td><span class="chip id">${x.s.id}</span></td><td class="wrap">${saved.set.has(x.s.id) ? '<span class="star on">★</span> ' : ''}<b>${esc(x.s.name)}</b> ${statusChip(x.s)} ${recChip(x.s, x.b)}</td>
        <td class="sig">${x.b.signal ? biasChip(x.b.signal.bias) + ' ' + esc(x.b.signal.label.length > 90 ? x.b.signal.label.slice(0, 88) + '…' : x.b.signal.label) : '–'}</td>
        <td class="r ${p.cls}">${p.text}</td><td class="r ${cls(mm.sharpe)}">${fmt.n(mm.sharpe)}</td><td class="r">${ddCell(x.b)}</td><td class="r">${isNum(mm.hit_rate) ? fmt.pct(mm.hit_rate, 0) : '–'}</td>
        <td>${x.b.curve ? spark(x.b.curve.strategy, 80, 24) : ''}</td></tr>`;
    }).join('') || '<tr><td colspan="8" class="empty">No strategies match.</td></tr>'}</tbody>`;
    $('#blist').innerHTML = shown.map(x => {
      const p = perfCell(x.s, x.b), mm = x.b.metrics || {};
      const sg = x.b.signal ? esc(x.b.signal.label.length > 70 ? x.b.signal.label.slice(0, 68) + '…' : x.b.signal.label) : '';
      return `<a class="brow" href="#/s/${x.s.id}"><div class="l1"><span class="chip id">${x.s.id}</span><b>${esc(x.s.name)}</b>${saved.set.has(x.s.id) ? '<span class="star on">★</span>' : ''}${statusChip(x.s)}${recChip(x.s, x.b)}</div>
        <div class="l2">${x.b.signal ? biasChip(x.b.signal.bias) : ''}<span>${sg}</span></div>
        <div class="l3"><span><i>Sharpe</i><b class="${cls(mm.sharpe)}">${fmt.n(mm.sharpe)}</b></span><span><i>Return</i><b class="${p.cls}">${p.text}</b></span><span><i>Max DD</i><b>${ddCell(x.b)}</b></span>${x.b.curve ? spark(x.b.curve.strategy, 64, 22) : ''}</div></a>`;
    }).join('') || `<p class="empty">${state.filter.cat === 'saved' ? 'Nothing saved yet – open a strategy and tap ☆ Save.' : 'No strategies match.'}</p>`;
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
      return `<a class="scard" href="#/s/${s.id}"><div class="top"><span class="chip id">${s.id}</span><span>${statusChip(s)} ${recChip(s, b)} ${b.signal ? biasChip(b.signal.bias) : ''}</span></div>
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
    <div class="page-head"><div><h1>${esc(s.name)} ${statusChip(s)}</h1><p>${esc(s.desc)}</p><p style="margin-top:8px">${b ? recChip(s, b) : ''} <button type="button" class="btn" id="star-btn">${saved.set.has(s.id) ? '★ Saved' : '☆ Save'}</button></p>
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
// (star handler is attached in setView wiring below)


async function viewNow() {
  setView(loadingHTML);
  await loadAll();
  const list = allStrategies().map(s => ({ s, b: blockOf(s), r: null })).filter(x => x.b && !x.b.error).map(x => ({ ...x, r: recent(x.s, x.b) })).filter(x => x.r);
  const idx = (state.live?.indices || []).find(i => i.name === UNI_LABEL[state.uni]);
  const vix = (state.live?.indices || []).find(i => i.symbol === '^INDIAVIX');
  const up200 = isNum(idx?.vs_dma200) ? idx.vs_dma200 > 0 : null, up50 = isNum(idx?.vs_dma50) ? idx.vs_dma50 > 0 : null;
  const trend = up200 && up50 ? 'Uptrend' : up200 === false && up50 === false ? 'Downtrend' : 'Mixed / choppy';
  const vp = vix?.pctile_1y;
  const volr = !isNum(vp) ? '' : vp > 0.7 ? 'high' : vp < 0.3 ? 'low' : 'normal';
  const read = {
    Uptrend: 'Trend-following, momentum and bullish option structures tend to be in step; mean-reversion shorts of winners struggle.',
    Downtrend: 'Bearish and hedged structures, defensive rotation and cash/gold tilts tend to be in step.',
    'Mixed / choppy': 'No clear trend: range-bound, mean-reversion and premium-selling structures tend to be in step; trend rules whipsaw.',
  }[trend] + (volr === 'high' ? ' Volatility is elevated, so premium is rich but risk is large.' : volr === 'low' ? ' Volatility is low, so options are cheap to buy and thin to sell.' : '');
  const by = st => list.filter(x => x.r.st === st);
  const sortR = a => a.slice().sort((x, y) => (x.r.unit === '%' ? 0 : 1) - (y.r.unit === '%' ? 0 : 1) || y.r.m1 - x.r.m1);
  const row = x => `<a class="brow" href="#/s/${x.s.id}"><div class="l1"><span class="chip id">${x.s.id}</span><b>${esc(x.s.name)}</b>${statusChip(x.s)}</div>
    <div class="l2">${x.b.signal ? biasChip(x.b.signal.bias) : ''}<span>${esc(x.b.signal?.label || '')}</span></div>
    <div class="l3"><span><i>Last 21 days</i><b class="${cls(x.r.m1)}">${fmt.sn(x.r.m1, 1)}${x.r.unit}</b></span><span><i>Last 3 months</i><b class="${cls(x.r.m3)}">${fmt.sn(x.r.m3, 1)}${x.r.unit}</b></span><span><i>Category</i><b>${esc(state.meta.categories.find(c => c.id === x.s.category).label)}</b></span></div></a>`;
  const listHTML = (id, arr, empty) => `<div class="blist" id="${id}"></div><div class="center" id="${id}-more"></div>${arr.length ? '' : `<p class="empty">${empty}</p>`}`;
  const W = sortR(by('working')), S = sortR(by('struggling')).reverse().sort((a, b) => a.r.m1 - b.r.m1), O = list.filter(x => x.s.category === 'options' && x.b.fit?.label === 'favourable');
  const panels = [
    { id: 'w', label: `Working (${W.length})`, html: listHTML('lw', W, 'Nothing is positive over both horizons.'), init: () => paged('lw', W, row) },
    { id: 's', label: `Struggling (${S.length})`, html: listHTML('ls', S, 'Nothing is negative over both horizons.'), init: () => paged('ls', S, row) },
    { id: 'o', label: `Option fit (${O.length})`, html: listHTML('lo', O, 'No option structure is flagged favourable by today\'s regime.'), init: () => paged('lo', O, x => row(x).replace('</div></a>', `<span class="muted" style="font-size:12px">${esc(x.b.fit.why)}</span></div></a>`)) },
  ];
  setView(`<div class="page-head"><div><h1>Working now · ${UNI_LABEL[state.uni]}</h1><p class="fresh">${freshness()}</p><p>Which strategies the current market is rewarding. Each strategy is re-run on the latest data; “working” means it made money over both the last 21 trading days and the last 63 (3 months). It describes the recent past, not a forecast.</p></div></div>
    <div class="card" style="margin-bottom:14px"><h3>Market regime</h3>
      <div class="tiles" style="margin:10px 0"><div class="tile"><div class="k">${UNI_LABEL[state.uni]} trend</div><div class="v ${trend === 'Uptrend' ? 'up' : trend === 'Downtrend' ? 'down' : ''}" style="font-size:15px">${trend}</div><div class="s">vs 50 / 200-day: ${isNum(idx?.vs_dma50) ? fmt.spct(idx.vs_dma50) : '–'} / ${isNum(idx?.vs_dma200) ? fmt.spct(idx.vs_dma200) : '–'}</div></div>
      <div class="tile"><div class="k">Last 21 days</div><div class="v ${cls(idx?.ret_1m)}">${fmt.spct(idx?.ret_1m)}</div></div>
      <div class="tile"><div class="k">India VIX</div><div class="v">${vix ? fmt.n(vix.last, 1) : '–'}</div><div class="s">${isNum(vp) ? fmt.n(vp * 100, 0) + 'th pctile · ' + volr : ''}</div></div>
      <div class="tile"><div class="k">Working / struggling</div><div class="v"><span class="up">${W.length}</span> <span class="muted">/</span> <span class="down">${S.length}</span></div><div class="s">${by('mixed').length} mixed</div></div></div>
      <p class="muted" style="font-size:13px">${esc(read)}</p></div><a class="promo" href="#/play" style="margin-bottom:14px"><b>Today's playbook</b><span>Turn this into a stance, stock picks and an option idea →</span></a>${tabsHTML(panels)}`);
  wireTabs(panels);
}
function paged(id, arr, rowFn, step = 12) {
  let n = step;
  const draw = () => {
    $('#' + id).innerHTML = arr.slice(0, n).map(rowFn).join('');
    $('#' + id + '-more').innerHTML = arr.length > n ? `<button class="btn" type="button">Show ${Math.min(step, arr.length - n)} more <span class="muted">(${arr.length - n} left)</span></button>` : '';
    $('#' + id + '-more button')?.addEventListener('click', () => { n += step; draw(); });
  };
  draw();
}


// ------------------------------------------------------------------ Today's playbook
const PLAY_INDEX = ['3.11', '3.12', '3.13', '3.14', '3.15', '3.17', '18.2'];
const PLAY_STOCKS = {
  '3.1': 'Trend', '3.7': 'Trend', '10.4': 'Trend', '3.6': 'Factor', '3.4': 'Defensive', '3.3': 'Value',
  '3.9': 'Reversion', '3.9.1': 'Reversion', '3.10': 'Reversion', '3.18': 'Reversion', '3.18.1': 'Reversion', '10.3': 'Reversion', '3.20': 'Blend',
};
async function viewPlay() {
  setView(loadingHTML);
  await loadAll();
  const get = id => { const s = state.byId[id]; return s ? { s, b: blockOf(s) } : null; };
  const live = state.live?.indices || [];
  const idx = live.find(i => i.name === UNI_LABEL[state.uni]);
  const vix = live.find(i => i.symbol === '^INDIAVIX');

  // 1) index stance: each index-level rule votes
  const votes = [];
  PLAY_INDEX.forEach(id => {
    const x = get(id); if (!x || !x.b || x.b.error || !x.b.signal) return;
    votes.push({ id, name: x.s.name, bias: x.b.signal.bias === 'mixed' ? 'neutral' : x.b.signal.bias, why: x.b.signal.label });
  });
  if (isNum(idx?.vs_dma200)) votes.push({ id: '', name: 'Price vs 200-day average', bias: idx.vs_dma200 > 0 ? 'long' : 'short', why: fmt.spct(idx.vs_dma200) + ' vs 200-day' });
  if (isNum(idx?.vs_dma50)) votes.push({ id: '', name: 'Price vs 50-day average', bias: idx.vs_dma50 > 0 ? 'long' : 'short', why: fmt.spct(idx.vs_dma50) + ' vs 50-day' });
  const nL = votes.filter(v => v.bias === 'long').length, nS = votes.filter(v => v.bias === 'short').length, nN = votes.length - nL - nS;
  const net = votes.length ? (nL - nS) / votes.length : 0;
  const stance = net >= 0.4 ? 'Bullish' : net <= -0.4 ? 'Bearish' : 'Neutral / choppy';
  const stanceCls = net >= 0.4 ? 'up' : net <= -0.4 ? 'down' : 'flat';
  const agree = votes.length ? Math.max(nL, nS, nN) / votes.length : 0;
  const conf = agree >= 0.7 ? 'high' : agree >= 0.5 ? 'moderate' : 'low';

  // 2) stock picks: weighted votes across cross-sectional portfolios
  const wt = r => ({ working: 1, mixed: 0.6, struggling: 0.3 }[r?.st] ?? 0.6);
  const agg = {};
  let nStrat = 0;
  Object.keys(PLAY_STOCKS).forEach(id => {
    const x = get(id); const t = x?.b?.tables?.[0];
    if (!x || !x.b || x.b.error || !t || t.columns[0] !== 'Side' || t.columns[1] !== 'Stock') return;
    nStrat++;
    const w = wt(recent(x.s, x.b));
    // only a strategy's conviction positions: its largest 20% of the universe per side (weight-based books hold almost everything)
    const cap = Math.max(3, Math.round(0.2 * (state.meta.universes[state.uni]?.constituents || 30)));
    const wOf = r => Math.abs(parseFloat(String(r[r.length - 1]).replace('%', ''))) || 0;
    const keep = [];
    ['Long', 'Short'].forEach(side => keep.push(...t.rows.filter(r => r[0] === side).sort((a, b) => wOf(b) - wOf(a)).slice(0, cap)));
    keep.forEach(r => {
      const a = (agg[r[1]] ||= { name: r[1], long: 0, short: 0, nl: 0, ns: 0, fam: new Set(), by: [] });
      if (r[0] === 'Long') { a.long += w; a.nl++; } else if (r[0] === 'Short') { a.short += w; a.ns++; } else return;
      a.fam.add(PLAY_STOCKS[id]); a.by.push(id);
    });
  });
  const rows = Object.values(agg).map(a => ({ ...a, score: a.long - a.short }));
  const longs = rows.filter(a => a.score > 0).sort((a, b) => b.score - a.score || b.nl - a.nl).slice(0, 10);
  const shorts = rows.filter(a => a.score < 0).sort((a, b) => a.score - b.score || b.ns - a.ns).slice(0, 10);
  const stockRow = (a, side) => `<div class="prow"><div><b>${esc(a.name)}</b><div class="muted" style="font-size:11.5px">${[...a.fam].join(' · ')}</div></div><div class="num ${side === 'L' ? 'up' : 'down'}">${side === 'L' ? a.nl : a.ns} of ${nStrat}${(side === 'L' ? a.ns : a.nl) ? `<span class="muted"> (−${side === 'L' ? a.ns : a.nl})</span>` : ''}</div></div>`;

  // 3) option structures that match the stance and today's volatility
  const want = net >= 0.4 ? 'bullish' : net <= -0.4 ? 'bearish' : 'neutral';
  const optsAll = (state.cats.options?.strategies || []).map(s => ({ s, b: blockOf(s) })).filter(x => x.b && !x.b.error);
  const pool = optsAll.filter(x => x.s.outlook === want && x.b.fit?.label !== 'unfavourable');
  const rank = x => (x.b.fit?.label === 'favourable' ? 100 : 0) + (x.b.metrics?.sharpe || 0) * 10;
  const opts = pool.sort((a, b) => rank(b) - rank(a)).slice(0, 4);
  const ivr = opts[0]?.b.fit?.iv_rank ?? optsAll[0]?.b.fit?.iv_rank;
  const volTilt = isNum(ivr) ? (ivr >= 60 ? 'India VIX is rich: favour defined-risk premium selling (spreads, condors).' : ivr <= 30 ? 'India VIX is cheap: favour buying options / debit spreads.' : 'Volatility is mid-range: no strong edge from volatility alone.') : '';

  // 4) risk
  const vt = get('6.5'), hg = get('10.1'), vrp = get('7.4');
  const expo = vt?.b?.signal?.label || '';
  const beta = hg?.b?.metrics?.basket_beta;

  const chipB = b => biasChip(b === 'neutral' ? 'neutral' : b);
  const panels = [
    { id: 'st', label: 'Stance', html: `
      <div class="card stance ${stanceCls}"><div class="k">${UNI_LABEL[state.uni]} stance</div><div class="big ${stanceCls}">${stance}</div>
        <p class="muted">${nL} long · ${nS} short · ${nN} flat of ${votes.length} index signals. Agreement: <b>${conf}</b>. ${conf === 'low' ? 'Signals disagree, so keep size small.' : ''}</p>
        <div class="votebar"><i class="up" style="width:${votes.length ? nL / votes.length * 100 : 0}%"></i><i class="flat" style="width:${votes.length ? nN / votes.length * 100 : 0}%"></i><i class="down" style="width:${votes.length ? nS / votes.length * 100 : 0}%"></i></div></div>
      <div class="card" style="margin-top:12px"><h3>Who voted what</h3><div class="stack" style="gap:8px;margin-top:10px">${votes.map(v => `<${v.id ? `a href="#/s/${v.id}"` : 'div'} class="mrow"><span>${v.id ? `<span class="chip id">${v.id}</span> ` : ''}${esc(v.name)}</span>${chipB(v.bias)}</${v.id ? 'a' : 'div'}>`).join('')}</div></div>` },
    { id: 'sk', label: 'Stocks', html: `
      <p class="muted" style="margin-bottom:10px;font-size:13px">Stocks ranked by how many of the ${nStrat} stock strategies hold them today, weighting strategies that are working now more. Trend, factor and reversion strategies often disagree, so the count in brackets shows opposing votes.</p>
      <div class="grid cols-2 even"><div class="card"><h3>Most-held longs</h3><div class="plist">${longs.map(a => stockRow(a, 'L')).join('') || '<p class="muted">None</p>'}</div></div>
      <div class="card"><h3>Most-held shorts</h3><div class="plist">${shorts.map(a => stockRow(a, 'S')).join('') || '<p class="muted">None</p>'}</div></div></div>` },
    { id: 'op', label: 'Options', html: `
      <p class="muted" style="margin-bottom:10px;font-size:13px">Structures matching a ${want} view and not penalised by today's volatility. ${esc(volTilt)} Premiums are theoretical.</p>
      <div class="blist">${opts.map(x => `<a class="brow" href="#/s/${x.s.id}"><div class="l1"><span class="chip id">${x.s.id}</span><b>${esc(x.s.name)}</b>${recChip(x.s, x.b)}</div>
        <div class="l2"><span>${esc(x.b.fit.why)}</span></div>
        <div class="l3"><span><i>${x.b.stats.net_premium >= 0 ? 'Debit' : 'Credit'}</i><b>${fmt.n(Math.abs(x.b.stats.net_premium_pct), 2)}%</b></span><span><i>Max loss</i><b class="down">${x.b.stats.max_loss == null ? 'Unlimited' : x.b.stats.riskless ? 'None' : fmt.n(x.b.stats.max_loss / x.b.payoff.spot * 100, 1) + '%'}</b></span><span><i>Prob. profit</i><b>${fmt.pct(x.b.stats.pop, 0)}</b></span></div></a>`).join('') || '<p class="empty">No structure fits.</p>'}</div>` },
    { id: 'rk', label: 'Risk', html: `<div class="stack">
      <div class="card"><h3>How much index to hold</h3><p>${esc(expo || 'n/a')}</p><p class="muted" style="font-size:12.5px;margin-top:6px">Volatility targeting (6.5): size the position so portfolio volatility stays near 12%.</p></div>
      <div class="card"><h3>Hedge ratio</h3><p>${isNum(beta) ? `Short about <b>₹${fmt.n(beta * 100, 0)}</b> of index futures per ₹100 of ${UNI_LABEL[state.uni]} stocks` : 'n/a'}</p><p class="muted" style="font-size:12.5px;margin-top:6px">Minimum-variance hedge from strategy 10.1.</p></div>
      <div class="card"><h3>Volatility premium</h3><p>${esc(vrp?.b?.signal?.label || 'n/a')}</p><p class="muted" style="font-size:12.5px;margin-top:6px">Strategy 7.4: sell volatility only when India VIX ${vix ? '(' + fmt.n(vix.last, 1) + ')' : ''} exceeds recent realised volatility.</p></div></div>` },
  ];
  setView(`<div class="page-head"><div><h1>Today's playbook · ${UNI_LABEL[state.uni]}</h1><p>All strategies combined into one read of today's ${UNI_LABEL[state.uni]}: the market stance, the stocks most strategies hold, option structures that fit, and risk sizing. <span class="muted">${freshness()}</span></p></div></div>${tabsHTML(panels)}
    <p class="muted" style="font-size:12px;margin-top:14px">Many strategies are variants of the same ideas (momentum, mean-reversion), so agreement overstates independent evidence. Educational use only, not investment advice.</p>`);
  wireTabs(panels);
}


// ------------------------------------------------------------------ Signal: one of CALL / PUT / HOLD / SELL / NOTHING
const VERDICTS = {
  CALL: { cls: 'up', line: 'Buy a call option', sub: 'Strategies lean clearly bullish.' },
  PUT: { cls: 'down', line: 'Buy a put option', sub: 'Strategies lean clearly bearish.' },
  HOLD: { cls: 'mix', line: 'Hold what you have', sub: 'Mildly bullish: keep existing long positions, do not add.' },
  SELL: { cls: 'warn', line: 'Sell / reduce longs', sub: 'Mildly bearish: exit or cut long positions, avoid new buys.' },
  NOTHING: { cls: 'flat', line: 'Do nothing', sub: 'Signals disagree or there is no edge. Stay out.' },
};
function computeVerdict() {
  const get = id => { const s = state.byId[id]; return s ? { s, b: blockOf(s) } : null; };
  const idx = (state.live?.indices || []).find(i => i.name === UNI_LABEL[state.uni]);
  const vix = (state.live?.indices || []).find(i => i.symbol === '^INDIAVIX');
  const votes = [];
  const add = (name, v, w, id = '') => { if (isNum(v)) votes.push({ id, name, v: Math.max(-1, Math.min(1, v)), w }); };
  const adj = x => ({ working: 1, mixed: 0.75, struggling: 0.5 }[recent(x.s, x.b)?.st] ?? 0.75);
  const sgn = b => (b === 'long' ? 1 : b === 'short' ? -1 : 0);
  // index-level strategies
  ['3.11', '3.12', '3.13', '3.14', '3.15', '3.17', '18.2'].forEach(id => {
    const x = get(id); if (x?.b && !x.b.error && x.b.signal) add(x.s.name, sgn(x.b.signal.bias), adj(x), id);
  });
  // breadth: how many constituents the moving-average rules hold long
  const br = ['3.11', '3.13'].map(id => get(id)?.b?.signal?.label?.match(/(\d+) of (\d+) stocks long/)).filter(Boolean).map(m => +m[1] / +m[2]);
  if (br.length) add(`Breadth (${Math.round(br.reduce((a, b) => a + b, 0) / br.length * 100)}% of stocks above their trend)`, (br.reduce((a, b) => a + b, 0) / br.length - 0.5) * 2, 1.5);
  // risk-on / risk-off, trend-following portfolio, volatility targeting
  const d = get('4.1.2')?.b?.signal?.detail || '';
  if (/RISK-ON/.test(d)) add('Dual momentum: risk-on', 1, 1, '4.1.2'); else if (/RISK-OFF/.test(d)) add('Dual momentum: risk-off', -1, 1, '4.1.2');
  const vt = get('6.5')?.b?.signal?.label?.match(/(\d+)%/);
  if (vt) add(`Volatility targeting holds ${vt[1]}% index`, (+vt[1] - 60) / 40, 1, '6.5');
  // price regime
  if (isNum(idx?.vs_dma200)) add('Price vs 200-day average', idx.vs_dma200 > 0 ? 1 : -1, 1.5);
  if (isNum(idx?.vs_dma50)) add('Price vs 50-day average', idx.vs_dma50 > 0 ? 1 : -1, 1);
  if (isNum(idx?.ret_1m)) add('Last 21 days return', idx.ret_1m > 0.01 ? 1 : idx.ret_1m < -0.01 ? -1 : 0, 1);
  const W = votes.reduce((a, v) => a + v.w, 0);
  const score = W ? votes.reduce((a, v) => a + v.v * v.w, 0) / W * 100 : 0;
  const bull = votes.filter(v => v.v > 0.2).length, bear = votes.filter(v => v.v < -0.2).length;
  const vp = vix?.pctile_1y;
  let verdict = score >= 40 ? 'CALL' : score >= 15 ? 'HOLD' : score > -15 ? 'NOTHING' : score > -40 ? 'SELL' : 'PUT';
  let note = '';
  if (verdict === 'CALL' && isNum(vp) && vp >= 0.85) { verdict = 'HOLD'; note = `India VIX is at the ${Math.round(vp * 100)}th percentile, so options are expensive: hold instead of buying calls.`; }
  // option quote for CALL / PUT from the ATM straddle legs
  let quote = null;
  const st = get('2.22')?.b;
  const legs = st?.tables?.[0]?.rows || [];
  const leg = legs.find(r => r[0] === (verdict === 'PUT' ? 'Put' : 'Call'));
  if (leg && (verdict === 'CALL' || verdict === 'PUT')) quote = { strike: leg[2], expiry: leg[3], premium: leg[5], delta: leg[6], spot: st.payoff?.spot };
  return { verdict, score, votes, bull, bear, flat: votes.length - bull - bear, note, quote, vixPct: vp, W };
}
async function viewSignal() {
  setView(loadingHTML);
  await loadAll();
  const r = computeVerdict();
  const V = VERDICTS[r.verdict];
  const open = nseOpen();
  const m = state.meta;
  const ageMin = (Date.now() - Date.parse(m.generated_at)) / 60000;
  const stale = open && ageMin > 45;
  const lab = ['PUT', 'SELL', 'NOTHING', 'HOLD', 'CALL'];
  const pos = (r.score + 100) / 2;
  const conf = Math.abs(r.score) >= 55 ? 'strong' : Math.abs(r.score) >= 30 ? 'moderate' : 'weak';
  const sorted = r.votes.slice().sort((a, b) => b.v * b.w - a.v * a.w);
  const quote = r.quote ? `<div class="card" style="margin-top:12px"><h3>${r.verdict === 'CALL' ? 'Call' : 'Put'} to look at</h3>
      <div class="tiles"><div class="tile"><div class="k">Strike (ATM)</div><div class="v">${esc(r.quote.strike)}</div></div><div class="tile"><div class="k">Expiry</div><div class="v">${esc(r.quote.expiry)}</div></div>
      <div class="tile"><div class="k">Model premium</div><div class="v">${esc(r.quote.premium)}</div><div class="s">points, theoretical</div></div><div class="tile"><div class="k">Delta</div><div class="v">${esc(r.quote.delta)}</div></div></div>
      <p class="muted" style="font-size:12.5px;margin-top:8px">Model price from India VIX, not a market quote: check the real option chain. A defined-risk alternative is the <a href="#/s/${r.verdict === 'CALL' ? '2.6' : '2.9'}">${r.verdict === 'CALL' ? 'bull call spread' : 'bear put spread'}</a>.</p></div>` : '';
  setView(`
    <div class="page-head"><div><h1>Signal · ${UNI_LABEL[state.uni]}</h1>
      <p class="fresh">${stale ? '<span class="down">Refresh is running late, the signal may lag. </span>' : ''}<span class="muted">Based on daily bars through ${esc(m.data_asof)}${open ? ' (today’s bar is still forming)' : ''}, computed ${ago(m.generated_at)}.</span></p></div></div>
    <div class="verdict ${V.cls}"><div class="vk">${UNI_LABEL[state.uni]} today</div><div class="vw">${r.verdict}</div><div class="vl">${V.line}</div><div class="vs">${esc(r.note || V.sub)}</div></div>
    <div class="vstrip" role="img" aria-label="Signal scale from PUT to CALL">${lab.map(l => `<span class="${l === r.verdict ? 'on ' + VERDICTS[l].cls : ''}">${l}</span>`).join('')}</div>
    <div class="vgauge"><i style="left:${pos}%"></i></div>
    <p class="muted" style="font-size:13px;margin:8px 0 14px;text-align:center">Score ${fmt.sn(r.score, 0)} of ±100 · ${conf} · ${r.bull} bullish, ${r.bear} bearish, ${r.flat} neutral of ${r.votes.length} signals</p>
    ${quote}
    <details class="fold" style="margin-top:14px"><summary>Why: the ${r.votes.length} signals behind it</summary>
      <div class="stack" style="gap:8px;padding:4px 0 8px">${sorted.map(v => `<${v.id ? `a href="#/s/${v.id}"` : 'div'} class="mrow"><span>${v.id ? `<span class="chip id">${v.id}</span> ` : ''}${esc(v.name)}</span>${biasChip(v.v > 0.2 ? 'long' : v.v < -0.2 ? 'short' : 'neutral')}</${v.id ? 'a' : 'div'}>`).join('')}</div></details>
    <details class="fold" style="margin-top:10px"><summary>What the five answers mean</summary><div class="notes pad">
      <p><b>CALL</b> score ≥ +40: buy a call option.</p><p><b>HOLD</b> +15 to +40: keep longs, do not add.</p><p><b>NOTHING</b> −15 to +15: no trade.</p><p><b>SELL</b> −40 to −15: sell or reduce longs.</p><p><b>PUT</b> ≤ −40: buy a put option.</p>
      <p>The score is the weighted average of every signal (index trend rules, breadth, KNN, neural net, dual momentum, volatility targeting, price vs 50/200-day and 21-day trend), each weighted less if that strategy has been struggling lately. It is recomputed whenever the data refreshes, so it updates after the market opens.</p></div></details>
    <p class="muted" style="font-size:12px;margin-top:14px">Educational output of backtested rules, not investment advice. Many signals are variants of the same trend idea, so agreement is weaker evidence than it looks. Options can lose their full premium.</p>`);
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
  setView(`<div class="page-head"><div><h1>Market now</h1><p>Latest Yahoo Finance bars (delayed) as of ${esc(state.meta.data_asof)}, refreshed by GitHub Actions every 10 minutes while the NSE is open.</p></div></div>${tabsHTML(panels)}`);
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
      <p><b>Refresh:</b> a GitHub Actions workflow re-downloads everything every 10 minutes during NSE hours (and once after the close), recomputes every strategy and redeploys to GitHub Pages. The latest daily bar is the still-forming session bar while the market is open. Yahoo data is delayed.</p>
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
    if (!a || a === 'signal') await viewSignal();
    else if (a === 'board') await viewOverview();
    else if (a === 'play') await viewPlay();
    else if (a === 'now') await viewNow();
    else if (a === 'market') await viewMarket();
    else if (a === 'c' && b) await viewCategory(b);
    else if (a === 's' && b) await viewStrategy(decodeURIComponent(h.slice(2)));
    else if (a === 'excluded') viewExcluded();
    else if (a === 'about') viewAbout();
    else await viewOverview();
  } catch (e) {
    console.error(e);
    setView(`<div class="empty"><h2>Couldn't load this page</h2><p class="muted" style="margin:8px 0 14px">Check your connection and try again.<br><span style="font-size:12px">${esc(e.message)}</span></p><button class="btn" type="button" id="retry-btn">↻ Retry</button></div>`);
    $('#retry-btn')?.addEventListener('click', route);
  }
}


// ---- data freshness + best-effort live quotes straight from Yahoo (falls back silently if the browser is blocked)
function freshness() {
  const m = state.meta, open = nseOpen();
  const age = (Date.now() - Date.parse(m.generated_at)) / 60000;
  const q = (state.live?.indices || []).find(i => i.quote_time);
  const stale = open && age > 45;
  return `<span class="${stale ? 'down' : 'muted'}">Strategies computed ${ago(m.generated_at)} from daily bars through ${esc(m.data_asof)}${q ? ` · index quotes as of ${esc(q.quote_time)} IST` : ''}${state.liveQuotes ? ' · <b class="up">live prices on</b>' : ''}.${stale ? ' The refresh is running late; GitHub schedules can lag.' : ''}</span>`;
}
async function refreshQuotes() {
  if (!state.live) return;
  let ok = false;
  await Promise.all(state.live.indices.map(async i => {
    try {
      const r = await fetch(`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(i.symbol)}?range=1d&interval=1m`, { cache: 'no-store' });
      if (!r.ok) return;
      const meta = (await r.json())?.chart?.result?.[0]?.meta;
      if (!meta || !isNum(meta.regularMarketPrice) || !isNum(meta.chartPreviousClose)) return;
      i.last = meta.regularMarketPrice; i.prev = meta.chartPreviousClose; i.chg = i.last - i.prev; i.chg_pct = i.last / i.prev - 1;
      if (isNum(meta.regularMarketTime)) i.quote_time = new Date(meta.regularMarketTime * 1000).toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' });
      ok = true;
    } catch (e) { /* CORS or network: keep the snapshot */ }
  }));
  state.liveQuotes = ok;
  if (ok) renderChrome();
}

// ------------------------------------------------------------------ PWA: install, offline
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
    const st = e.target.closest('#star-btn');
    if (st) { const id = decodeURIComponent(location.hash.slice(4)); saved.toggle(id); st.textContent = saved.set.has(id) ? '★ Saved' : '☆ Save'; return; }
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
  refreshQuotes();
  setInterval(() => { if (nseOpen()) refreshQuotes(); }, 60000);
  setInterval(() => { if (state.meta) { renderChrome(); } }, 60000);
}
init();
})();
