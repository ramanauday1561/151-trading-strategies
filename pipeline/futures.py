"""Chapter 10 – futures: hedging (10.1, 10.1.1), contrarian (10.3) and trend following (10.4).

Yahoo Finance has no NIFTY / SENSEX / single-stock futures prices, so the cash index (or stock)
return is used as the proxy for the futures return.  Futures carry (basis) is therefore ignored;
hedge ratios and hedge effectiveness are unaffected to first order because futures track spot.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import config as C
from . import metrics as M
from . import universe as U
from .common import Ctx, entry, guarded, weights_result, norm_abs

CAT = "futures"


def _ols(y: np.ndarray, x: np.ndarray):
    xc = x - x.mean()
    beta = float((xc * (y - y.mean())).sum() / (xc ** 2).sum())
    resid = y - y.mean() - beta * xc
    r2 = 1 - float((resid ** 2).sum() / ((y - y.mean()) ** 2).sum())
    return beta, r2


def s10_1(ctx: Ctx, win=252):
    m = ctx.index_ret
    rows = []
    for k in ctx.keys:
        d = pd.concat([ctx.ret[k], m], axis=1).dropna().iloc[-win:]
        if len(d) < win * 0.8:
            continue
        beta, r2 = _ols(d.iloc[:, 0].values, d.iloc[:, 1].values)
        sd = d.iloc[:, 0].std() * math.sqrt(C.TRADING_DAYS)
        hv = sd * math.sqrt(max(1 - r2, 0))
        rows.append((k, beta, math.sqrt(max(r2, 0)), r2, sd, hv, 1 - hv / sd))
    rows.sort(key=lambda r: -r[6])
    tab = M.table(f"Minimum-variance hedge of each stock with {ctx.idx_name} futures (252d)",
                  ["Stock", "Hedge ratio β", "Correlation", "R²", "Vol unhedged", "Vol hedged", "Variance cut", "Futures notional per ₹1L stock"],
                  [[ctx.names[k], f"{b:.2f}", f"{c:.2f}", f"{r2:.2f}", f"{sd:.1%}", f"{hv:.1%}", f"{1 - (hv / sd) ** 2:.0%}", f"₹{b * 1e5:,.0f}"]
                   for k, b, c, r2, sd, hv, he in rows])
    # portfolio demo: equal-weight basket hedged with rolling OOS beta
    basket = ctx.ret.mean(axis=1)
    cov = basket.rolling(win).cov(m)
    var = m.rolling(win).var()
    beta_t = (cov / var).shift(1)
    hedged = (basket - beta_t * m).dropna()
    unh = basket.reindex(hedged.index)
    blk = M.block(
        net=hedged, bench=unh,
        signal=M.signal(f"Hedge a ₹100 portfolio of {ctx.idx_name} stocks with ≈ ₹{float(beta_t.iloc[-1]) * 100:.0f} of index futures short" if not np.isnan(beta_t.iloc[-1]) else "n/a",
                        "neutral", "Short futures notional = β × portfolio value (minimum-variance hedge ratio h* = ρσₛ/σₐ)"),
        tables=[tab],
        extra_metrics={"basket_beta": M._f(beta_t.iloc[-1]), "vol_unhedged": M._f(unh.std() * math.sqrt(C.TRADING_DAYS)),
                       "vol_hedged": M._f(hedged.std() * math.sqrt(C.TRADING_DAYS))},
        notes=[f"Strategy curve = equal-weight basket of all {len(ctx.keys)} constituents minus a short in {ctx.idx_name} futures sized at the rolling 252-day regression β (estimated out-of-sample, lagged one day). "
               "The benchmark curve is the unhedged basket. The hedged line keeps the stock-selection residual but removes market direction.",
               "Spot index returns proxy the futures returns (no futures data on Yahoo Finance); contract lot sizes, basis and roll costs are not modelled."])
    return entry("10.1", "Hedging risk with futures", CAT,
                 "Offset market risk in a stock or portfolio by shorting index futures in proportion to its beta (the minimum-variance hedge ratio).",
                 blk, status="proxy", extra={"adapted_note": "Index spot returns proxy futures returns."})


def s10_1_1(ctx: Ctx, win=252):
    m = ctx.index_ret
    mapping = dict(U.SECTOR_INDICES)
    other = [k for k in U.BROAD_INDICES if k != ctx.idx_sym][0]
    mapping[other] = U.BROAD_INDICES[other]
    rows, oos = [], {}
    for sym, nm in mapping.items():
        if sym not in ctx.md.close.columns or ctx.md.close[sym].notna().sum() < win + 50:
            continue
        r = ctx.md.close[sym].pct_change(fill_method=None)
        d = pd.concat([r, m], axis=1).dropna()
        b, r2 = _ols(d.iloc[-win:, 0].values, d.iloc[-win:, 1].values)
        beta_t = (r.rolling(win).cov(m) / m.rolling(win).var()).shift(1)
        res = (r - beta_t * m).dropna()
        base = r.reindex(res.index)
        cut = 1 - (res.var() / base.var())
        rows.append((nm, b, r2, float(cut), sym))
        oos[sym] = (res, base)
    if not rows:
        return entry("10.1.1", "Cross-hedging", CAT, "Hedge with a related futures contract.", {"notes": ["No sector index data."]}, status="proxy")
    rows.sort(key=lambda r: -r[3])
    show = "^NSEBANK"
    sym = show if show in oos else rows[0][4]
    res, base = oos[sym]
    nm = dict((r[4], r[0]) for r in rows)[sym]
    tab = M.table(f"Cross-hedging assets that have no liquid futures, using {ctx.idx_name} futures",
                  ["Asset", "Hedge ratio β (252d)", "R²", "Out-of-sample variance cut (all years)"],
                  [[n, f"{b:.2f}", f"{r2:.2f}", f"{c:.0%}"] for n, b, r2, c, _ in rows])
    blk = M.block(
        net=res, bench=base,
        signal=M.signal(f"Hedge {nm} with β = {rows[[r[4] for r in rows].index(sym)][1]:.2f} × {ctx.idx_name} futures", "neutral",
                        "Optimal hedge ratio estimated by regression; basis risk = unexplained residual"),
        tables=[tab],
        extra_metrics={"avg_variance_cut": M._f(float(np.mean([r[3] for r in rows]))), "showcase": nm},
        notes=[f"Strategy curve = {nm} minus βₜ₋₁ × {ctx.idx_name} (rolling 252-day β, out-of-sample); benchmark = unhedged {nm}. Cross-hedging (Eq. 463) uses futures on a different but correlated underlying, "
               "so a basis-risk residual remains. Sector indices (and the other broad index) have no or thin futures, so the NIFTY/SENSEX futures are the practical hedge.",
               "Spot returns proxy futures returns; lot-size rounding, basis and rolls are not modelled."])
    return entry("10.1.1", "Cross-hedging", CAT,
                 "Hedge an exposure that has no futures of its own (sector index, other broad index) using index futures on a correlated underlying, with the hedge ratio from regression.",
                 blk, status="proxy", extra={"adapted_note": "Index spot returns proxy futures returns."})


def s10_3(ctx: Ctx, lookback=5):
    R = ctx.close.pct_change(lookback, fill_method=None)
    vol = ctx.ret.rolling(126, min_periods=100).std()
    dates = M.rebalance_dates(ctx.dates, "W")
    rows, last = {}, None
    for d in dates:
        r = R.loc[d].dropna()
        if len(r) < 8:
            continue
        sig = vol.loc[d].reindex(r.index)
        raw = -(r - r.mean()) / sig.where(sig > 0)
        w = norm_abs(raw.dropna())
        rows[d] = w.reindex(ctx.keys).fillna(0.0)
        last = (r - r.mean())
    W = pd.DataFrame(rows).T if rows else pd.DataFrame()
    blk = weights_result(ctx, W, score_last=last, score_label="Weekly return vs market", fmt="{:+.1%}", notes=[
        "Contrarian weights wᵢ = −γ (Rᵢ − Rₘ)/σᵢ on 1-week returns, where Rₘ is the equal-weighted market return of the universe (Eqs. 469-471). "
        "The book's suggested 1/σ suppression is applied so volatile names are not over-invested. Applied to the constituents' single-stock futures (spot returns as proxy). "
        "This is the futures-market twin of 3.9, with volatility scaling."], freq_label="weekly")
    return entry("10.3", "Contrarian trading (mean-reversion)", CAT,
                 "Within a universe of futures, buy last week's relative losers and sell last week's relative winners, scaling positions by 1/volatility.",
                 blk, status="proxy", extra={"adapted_note": "Single-stock futures proxied by spot stock returns."})


def s10_4(ctx: Ctx, T=126):
    R = ctx.close.pct_change(T, fill_method=None)
    vol = ctx.ret.rolling(T, min_periods=int(T * 0.8)).std()
    dates = M.rebalance_dates(ctx.dates, "M")
    rows, last = {}, None
    for d in dates:
        r = R.loc[d].dropna()
        s = vol.loc[d].reindex(r.index)
        ok = s.notna() & (s > 0)
        r, s = r[ok], s[ok]
        if len(r) < 8:
            continue
        rt = r - r.mean()                                     # demeaned returns (Rtilde)
        eta = np.sign(rt)
        inv = 1.0 / s
        w = pd.Series(0.0, index=r.index)
        lp, sp = eta > 0, eta < 0
        if lp.any() and sp.any():
            w[lp] = 0.5 * inv[lp] / inv[lp].sum()             # gamma+ ; Eq. 478
            w[sp] = -0.5 * inv[sp] / inv[sp].sum()            # gamma- ; Eq. 479, sum w = 0, sum |w| = 1
        rows[d] = w.reindex(ctx.keys).fillna(0.0)
        last = rt
    W = pd.DataFrame(rows).T if rows else pd.DataFrame()
    blk = weights_result(ctx, W, score_last=last, score_label=f"{T}d return vs market", fmt="{:+.1%}", notes=[
        f"Trend following with wᵢ = γ± ηᵢ/σᵢ, ηᵢ = sign(Rᵢ − Rₘ) over the past {T} trading days (Eqs. 474-480): long the stocks beating the market, short those lagging, "
        "weighted by inverse volatility with separate long and short normalisation so the book is dollar-neutral. Applied to constituents' single-stock futures (spot returns as proxy)."], freq_label="monthly")
    return entry("10.4", "Trend following (momentum)", CAT,
                 "Go long the futures that have been trending up relative to the market and short those trending down, sizing each by 1/volatility, rebalanced monthly.",
                 blk, status="proxy", extra={"adapted_note": "Single-stock futures proxied by spot stock returns."})


def run(ctx: Ctx):
    out = {}
    for fn, sid, nm in ((s10_1, "10.1", "Hedging risk with futures"), (s10_1_1, "10.1.1", "Cross-hedging"),
                        (s10_3, "10.3", "Contrarian trading (mean-reversion)"), (s10_4, "10.4", "Trend following (momentum)")):
        out[sid] = guarded(fn, sid, nm, CAT, ctx)
    return out
