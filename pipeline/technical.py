"""Chapter 3 – single-instrument technical strategies (3.11 - 3.15).

Each strategy is a function (close, high, low) -> position series in {-1, 0, +1} decided at the
close of day t and held over day t+1.  It is backtested on the index and its signal is also
evaluated for every constituent (breadth table + equal-weight basket of single-stock runs).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from . import metrics as M
from .common import Ctx, entry, guarded

CAT = "stocks"


# --------------------------------------------------------------------- position rules

def pos_single_ma(close, high, low, T=50):
    ma = close.rolling(T).mean()
    return np.sign(close - ma).where(ma.notna(), 0.0)


def pos_two_ma(close, high, low, a=10, b=30, delta=0.02):
    ma_a, ma_b = close.rolling(a).mean(), close.rolling(b).mean()
    up, dn = (ma_a > ma_b).values, (ma_a < ma_b).values
    ok = ma_b.notna().values
    r1 = close.pct_change().values
    out = np.zeros(len(close))
    pos = 0
    blocked = 0
    for i in range(len(close)):
        if not ok[i]:
            continue
        des = 1 if up[i] else (-1 if dn[i] else pos)
        if blocked and des != blocked:
            blocked = 0
        if pos == 1 and r1[i] < -delta:
            blocked = 1                       # stop-loss: liquidate until a fresh signal
        elif pos == -1 and r1[i] > delta:
            blocked = -1
        pos = 0 if (blocked and des == blocked) else des
        out[i] = pos
    return pd.Series(out, index=close.index)


def pos_three_ma(close, high, low, a=3, b=10, c=21):
    m1, m2, m3 = (close.rolling(x).mean() for x in (a, b, c))
    lo, sh = ((m1 > m2) & (m2 > m3)).values, ((m1 < m2) & (m2 < m3)).values
    ex_lo, ex_sh = (m1 <= m2).values, (m1 >= m2).values
    ok = m3.notna().values
    out = np.zeros(len(close))
    pos = 0
    for i in range(len(close)):
        if not ok[i]:
            continue
        if lo[i]:
            pos = 1
        elif sh[i]:
            pos = -1
        elif pos == 1 and ex_lo[i]:
            pos = 0
        elif pos == -1 and ex_sh[i]:
            pos = 0
        out[i] = pos
    return pd.Series(out, index=close.index)


def pos_pivot(close, high, low):
    c_prev, h_prev, l_prev = close.shift(1), high.shift(1), low.shift(1)
    pv = (h_prev + l_prev + c_prev) / 3.0
    R = 2 * pv - l_prev
    S = 2 * pv - h_prev
    P, PV, RR, SS = close.values, pv.values, R.values, S.values
    out = np.zeros(len(close))
    pos, cool = 0, 0
    for i in range(len(close)):
        if np.isnan(PV[i]) or np.isnan(P[i]):
            continue
        if cool == 1 and P[i] <= PV[i]:
            cool = 0
        if cool == -1 and P[i] >= PV[i]:
            cool = 0
        des = 1 if P[i] > PV[i] else (-1 if P[i] < PV[i] else pos)
        if des == 1 and P[i] >= RR[i]:       # reached resistance: take profit, stay out until price falls back to the pivot
            cool = 1
        elif des == -1 and P[i] <= SS[i]:    # reached support: cover the short
            cool = -1
        pos = 0 if (cool and des == cool) else des
        out[i] = pos
    return pd.Series(out, index=close.index)


def pos_channel(close, high, low, T=20):
    lo, hi = close.rolling(T).min(), close.rolling(T).max()
    at_floor, at_ceiling = (close <= lo).values, (close >= hi).values
    ok = lo.notna().values
    out = np.zeros(len(close))
    pos = 0
    for i in range(len(close)):
        if not ok[i]:
            continue
        if at_floor[i] and not at_ceiling[i]:
            pos = 1
        elif at_ceiling[i] and not at_floor[i]:
            pos = -1
        out[i] = pos
    return pd.Series(out, index=close.index)


# -------------------------------------------------------------------------- driver

def _safe_hl(ctx: Ctx):
    close = ctx.index.dropna()
    h = ctx.index_high.reindex(close.index)
    l = ctx.index_low.reindex(close.index)
    bad = h.isna() | l.isna() | (h <= l)
    h = h.where(~bad, close)
    l = l.where(~bad, close)
    return close, h, l


def ts_entry(ctx: Ctx, sid, name, desc, fn, rule_note):
    close, h, l = _safe_hl(ctx)
    pos = fn(close, h, l)
    r = ctx.index_ret.reindex(close.index)
    net, gross, turn = M.run_positions(r, pos)
    lo_net, _, _ = M.run_positions(r, pos.clip(lower=0))
    # constituents: signal breadth + equal-weight basket of single-stock runs
    rows, basket, nl, ns = [], [], 0, 0
    for k in ctx.keys:
        c = ctx.close[k]
        if c.notna().sum() < 250:
            continue
        cc = c.dropna()
        hh = ctx.high[k].reindex(cc.index)
        ll = ctx.low[k].reindex(cc.index)
        bad = hh.isna() | ll.isna() | (hh <= ll)
        hh, ll = hh.where(~bad, cc), ll.where(~bad, cc)
        p = fn(cc, hh, ll)
        n_, _, _ = M.run_positions(ctx.ret[k].reindex(cc.index), p)
        basket.append(n_.reindex(ctx.dates).fillna(0.0))
        last = int(p.iloc[-1])
        nl += last > 0
        ns += last < 0
        rows.append([ctx.names[k], {1: "Long", -1: "Short", 0: "Flat"}[last]])
    extra = {}
    tables = []
    if rows:
        rows.sort(key=lambda r: {"Long": 0, "Short": 1, "Flat": 2}[r[1]])
        tables.append(M.table(f"Signal for each constituent ({nl} long / {ns} short of {len(rows)})", ["Stock", "Signal"], rows))
        bk = pd.concat(basket, axis=1).mean(axis=1)
        bk = bk.loc[net.index[0]:]
        extra["constituents_avg"] = bk
    last_pos = int(pos.iloc[-1])
    lab = {1: "LONG", -1: "SHORT", 0: "FLAT"}[last_pos]
    blk = M.block(
        net=net, gross=gross, turnover=turn, bench=r, extra_curves={"long_only": lo_net, **extra},
        signal=M.signal(f"{lab} {ctx.idx_name} – {nl} of {len(rows)} stocks long" if rows else f"{lab} {ctx.idx_name}",
                        {1: "long", -1: "short", 0: "neutral"}[last_pos]),
        tables=tables,
        notes=[rule_note,
               f"Backtest is on the {ctx.idx_name} index (trade via index futures or ETF), position taken at the close and held the next day, {C.COST_BPS:.0f} bps cost per side. "
               "'Long only' keeps only the long signals; 'constituents avg' is the equal-weight average of the same rule run on each stock separately."])
    return entry(sid, name, CAT, desc, blk)


def run(ctx: Ctx):
    specs = [
        ("3.11", "Single moving average",
         "Go long when the price is above its 50-day moving average and short when below.",
         lambda c, h, l: pos_single_ma(c, h, l, 50),
         "Signal = sign(P − SMA(50)) (Eq. 321)."),
        ("3.12", "Two moving averages",
         "Go long when the 10-day average is above the 30-day average, short when below, with a 2% daily stop-loss.",
         lambda c, h, l: pos_two_ma(c, h, l, 10, 30, 0.02),
         "Long if MA(10) > MA(30), short if below. A position is liquidated after a daily move of more than Δ = 2% against it and re-entered only on a fresh MA signal (Eq. 323)."),
        ("3.13", "Three moving averages",
         "Enter long only when MA(3) > MA(10) > MA(21), short when reversed; exit when the two shortest averages cross back.",
         lambda c, h, l: pos_three_ma(c, h, l, 3, 10, 21),
         "Establish long if MA(3) > MA(10) > MA(21), liquidate if MA(3) ≤ MA(10); mirror for shorts (Eq. 324)."),
        ("3.14", "Support and resistance",
         "Use yesterday's pivot point to go long above it and short below it, taking profit at the resistance / support levels.",
         pos_pivot,
         "Pivot C = (H+L+C)/3 of the previous day, R = 2C − L, S = 2C − H. Long if P > C (take profit at P ≥ R); short if P < C (cover at P ≤ S) (Eq. 328). After a take-profit the position stays flat until the price returns to the pivot."),
        ("3.15", "Channel",
         "Buy when the price touches the floor of its 20-day Donchian channel and sell/short when it touches the ceiling (mean-reversion inside the channel).",
         lambda c, h, l: pos_channel(c, h, l, 20),
         "Donchian channel over T = 20 days: long when P equals the channel floor, short when it equals the ceiling (Eq. 331). The book notes a breakout of the channel may instead signal a new trend."),
    ]
    out = {}
    for sid, name, desc, fn, note in specs:
        out[sid] = guarded(ts_entry, sid, name, CAT, ctx, sid, name, desc, fn, note)
    return out
