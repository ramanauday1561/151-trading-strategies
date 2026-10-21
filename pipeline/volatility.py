"""Chapter 7 – volatility strategies built on India VIX (7.4, 7.4.1, 7.6).

India VIX is a model-free 30-day implied volatility index for NIFTY.  It is also used as the
implied-volatility input for SENSEX (the two indexes are ~0.98 correlated).  All three strategies are
simulated monthly: enter on the first trading day of each month at VIX, settle on the first trading
day of the next month.  The simulation prices the options / variance swap theoretically, so costs,
skew and liquidity are not captured.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import config as C
from . import metrics as M
from .common import Ctx, entry, guarded
from .options import bs_price, bs_greeks

CAT = "volatility"


def _cycles(ctx: Ctx):
    close = ctx.index.dropna()
    vix = ctx.vix.reindex(close.index).ffill()
    lr = np.log(close).diff()
    rv21 = lr.rolling(21).std() * math.sqrt(C.TRADING_DAYS) * 100.0         # trailing realised vol, %
    starts = M.month_starts(close.index)
    rows = []
    for a, b in zip(starts[:-1], starts[1:]):
        if pd.isna(vix.get(a)) or pd.isna(rv21.get(a)):
            continue
        seg = lr.loc[(lr.index > a) & (lr.index <= b)]
        px = close.loc[a:b]
        rows.append({
            "start": a, "end": b, "S0": float(close[a]), "ST": float(close[b]), "vix": float(vix[a]),
            "rv_prev": float(rv21[a]), "rv_cycle": float(math.sqrt(C.TRADING_DAYS * (seg ** 2).mean()) * 100.0) if len(seg) else np.nan,
            "T": (b - a).days / 365.0, "path": px, "n": len(seg),
        })
    return rows, close, vix, rv21, lr


def _straddle(S, K, T, sig):
    return float(bs_price("C", S, K, T, sig) + bs_price("P", S, K, T, sig))


def _straddle_delta(S, K, T, sig):
    return bs_greeks("C", S, K, T, sig)[0] + bs_greeks("P", S, K, T, sig)[0]


def _live(ctx: Ctx, close, vix, rv21, lr):
    today = close.index[-1]
    cur_vix, cur_rv = float(vix.iloc[-1]), float(rv21.iloc[-1])
    spread = cur_vix - cur_rv
    m0 = M.month_starts(close.index)[-1]
    seg = lr.loc[lr.index > m0]
    rv_mtd = float(math.sqrt(C.TRADING_DAYS * (seg ** 2).mean()) * 100.0) if len(seg) >= 2 else None
    vix0 = float(vix.loc[m0])
    return {"vix": cur_vix, "rv21": cur_rv, "spread": spread, "rv_mtd": rv_mtd, "vix_month_start": vix0,
            "month_start": str(m0.date()), "S": float(close.iloc[-1]), "today": today}


def _curve(pnl: pd.Series, bench: pd.Series | None, extra: dict | None = None):
    series = {"strategy": pnl.cumsum()}
    if extra:
        series.update({k: v.cumsum() for k, v in extra.items()})
    if bench is not None:
        series["benchmark"] = bench.cumsum()
    return M.equity_curve(series, base=0.0, kind="cum")


def _cycle_table(rows, pnl_vals, label):
    out = []
    for r, p in list(zip(rows, pnl_vals))[-12:]:
        out.append([str(r["start"].date()), f"{r['vix']:.1f}", f"{r['rv_prev']:.1f}", f"{r['vix'] - r['rv_prev']:+.1f}",
                    f"{r['rv_cycle']:.1f}", "traded" if not np.isnan(p) else "skipped", "" if np.isnan(p) else f"{p:+.2f}"])
    return M.table(f"Last 12 monthly cycles ({label})", ["Entry", "VIX", "RV prev 21d", "Spread", "RV in cycle", "Action", "P&L"], out)


def _build(ctx: Ctx, sid, name, desc, pnl_fn, units, label, live_note):
    rows, close, vix, rv21, lr = _cycles(ctx)
    pnl_all, gated = [], []
    for r in rows:
        p = pnl_fn(r)
        pnl_all.append(p)
        gated.append(p if (r["vix"] - r["rv_prev"]) > 0 else np.nan)
    idx = pd.DatetimeIndex([r["end"] for r in rows])
    always = pd.Series(pnl_all, index=idx)
    gate = pd.Series(gated, index=idx)
    strat = gate.fillna(0.0)
    bench = pd.Series([(r["ST"] / r["S0"] - 1) * 100 for r in rows], index=idx)
    live = _live(ctx, close, vix, rv21, lr)
    S, v = live["S"], live["vix"] / 100.0
    atm = round(S / C.OPT_STRIKE_STEP[ctx.universe]) * C.OPT_STRIKE_STEP[ctx.universe]
    prem = _straddle(S, atm, C.OPT_HORIZON_DAYS / 365.0, v)
    go = live["spread"] > 0
    m = M.perf_monthly(strat)
    m["always_total"] = M._f(always.sum())
    m["always_sharpe"] = M._f(always.mean() / always.std() * math.sqrt(12)) if always.std() > 0 else None
    m["months_traded"] = int(gate.notna().sum())
    m["vix"] = round(live["vix"], 2)
    m["rv_21d"] = round(live["rv21"], 2)
    m["vrp_spread"] = round(live["spread"], 2)
    tables = [_cycle_table(rows, gated, label)]
    mtd = ""
    if live["rv_mtd"] is not None:
        mtd = f" Month-to-date realised vol {live['rv_mtd']:.1f}% vs {live['vix_month_start']:.1f}% implied at the start of the month ({live['month_start']})."
    blk = {
        "signal": M.signal(("SELL VOLATILITY" if go else "STAND ASIDE") + f" – VIX {live['vix']:.1f} vs realised {live['rv21']:.1f}",
                           "short" if go else "neutral",
                           f"ATM {C.OPT_HORIZON_DAYS}d straddle ({atm:,.0f}) ≈ {prem:,.0f} pts = {prem / S * 100:.2f}% of spot" + (" (premium to collect)" if go else "")),
        "metrics": m,
        "curve": _curve(strat, bench, {"always_sell": always.fillna(0.0)}),
        "curve_units": units,
        "tables": tables,
        "notes": [live_note,
                  "Rule: at the start of each month compare India VIX with the trailing 21-day realised volatility of the index; trade only if VIX is higher (positive volatility risk premium), otherwise stay out. "
                  "'Always sell' shows the un-gated version; the dashed line is the index's own monthly % move for scale." + mtd,
                  "Theoretical pricing: flat IV = India VIX at entry, Black-Scholes, no costs, no skew, no margin. This strategy has unlimited loss in a volatility spike – the worst month matters more than the average."],
    }
    return entry(sid, name, CAT, desc, blk, status="implemented")


def s7_4(ctx: Ctx):
    def pnl(r):
        K = r["S0"]
        sig = r["vix"] / 100.0
        prem = _straddle(r["S0"], K, r["T"], sig)
        return (prem - abs(r["ST"] - K)) / r["S0"] * 100.0
    return _build(ctx, "7.4", "Volatility risk premium",
                  "Implied volatility usually exceeds realised volatility, so sell ATM straddles when VIX is above recent realised volatility and hold to expiry.",
                  pnl, "cumulative % of index level", "short straddle, held to expiry",
                  "Short ATM straddle sold at the open of each month at VIX, held to expiry (payoff = premium − |Sₜ − K|), as % of the index level.")


def s7_4_1(ctx: Ctx):
    def pnl(r):
        path = r["path"].values
        dates = r["path"].index
        S0, K, sig = r["S0"], r["S0"], r["vix"] / 100.0
        end = dates[-1]
        v_prev = _straddle(S0, K, r["T"], sig)
        v0 = v_prev
        total = 0.0
        for t in range(1, len(path)):
            T_prev = (end - dates[t - 1]).days / 365.0
            delta = _straddle_delta(path[t - 1], K, T_prev, sig)
            total += delta * (path[t] - path[t - 1])             # hedge long delta units against the short straddle
        v_end = abs(path[-1] - K)
        return (v0 - v_end + total) / S0 * 100.0
    return _build(ctx, "7.4.1", "Volatility risk premium with Gamma hedging",
                  "Same volatility-risk-premium trade, but delta-hedge the short straddle every day (buy the index as it rises, sell as it falls) so the P&L comes from time decay rather than direction.",
                  pnl, "cumulative % of index level", "delta-hedged short straddle",
                  "Short ATM straddle with daily delta hedging in the index (Gamma scalping): P&L = premium − payoff + Σ Δₜ₋₁ (Sₜ − Sₜ₋₁); the hedge costs money when the market whipsaws, "
                  "so profit comes from implied volatility exceeding realised volatility.")


def s7_6(ctx: Ctx):
    def pnl(r):
        K = r["vix"]
        rv = r["rv_cycle"]
        return (K * K - rv * rv) / (2.0 * K)                      # short variance swap, per 1 vega-notional (vol points)
    return _build(ctx, "7.6", "Volatility trading with variance swaps",
                  "Express the volatility view with a variance swap instead of options: sell variance at the VIX strike when VIX exceeds recent realised volatility, collect the difference to realised variance.",
                  pnl, "cumulative volatility points (1 vega notional)", "short variance swap",
                  "Short variance swap, strike = India VIX² at entry, payoff P = N·(K² − v) with realised variance v = (252/T)ΣR² (Eqs. 434-436), quoted per 1 vol-point of vega notional "
                  "(≈ (K² − RV²)/(2K) vol points). No delta-hedging needed. Real variance swaps are OTC; this is a theoretical replication using VIX as the strike.")


def run(ctx: Ctx):
    out = {}
    for fn, sid, nm in ((s7_4, "7.4", "Volatility risk premium"), (s7_4_1, "7.4.1", "Volatility risk premium with Gamma hedging"),
                        (s7_6, "7.6", "Volatility trading with variance swaps")):
        out[sid] = guarded(fn, sid, nm, CAT, ctx)
    return out
