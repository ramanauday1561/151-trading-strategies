"""Chapter 6 – index strategies: dispersion (6.3, 6.3.1 – proxy) and volatility targeting (6.5)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from . import metrics as M
from .common import Ctx, entry, guarded
from .stocks_xs import stat_risk_model

CAT = "indexes"


def _weights(ctx: Ctx) -> pd.Series:
    mc = ctx.fund_series("marketCap")
    if mc.notna().sum() >= 0.7 * len(ctx.keys) and (mc > 0).sum() >= 0.7 * len(ctx.keys):
        w = mc.fillna(mc.median())
        src = "market-cap weights from Yahoo Finance"
    else:
        w = pd.Series(1.0, index=ctx.keys)
        src = "equal weights (market caps unavailable)"
    w = w / w.sum()
    w.attrs["src"] = src
    return w


def _corr_terms(Rwin: pd.DataFrame, w: pd.Series):
    """Returns sigma_i (annual), w normalised over valid stocks and the pieces of Eq. 423."""
    valid = Rwin.columns[Rwin.notna().all()]
    R = Rwin[valid]
    ww = w.reindex(valid)
    ww = ww / ww.sum()
    S = R.cov().values * C.TRADING_DAYS
    sig = np.sqrt(np.diag(S))
    wv = ww.values
    wsw = float(wv @ S @ wv)
    self_term = float(((wv * sig) ** 2).sum())
    sum_ws = float((wv * sig).sum())
    return valid, wv, sig, S, wsw, self_term, sum_ws


def s6_3(ctx: Ctx, win=63):
    w = _weights(ctx)
    vix = ctx.vix.reindex(ctx.dates)
    idx_dates = M.rebalance_dates(ctx.dates, "W")
    pos = {d: i for i, d in enumerate(ctx.dates)}
    start = max(win + 1, len(idx_dates) - 5 * 52)
    rows = []
    for d in idx_dates[start:]:
        i = pos[d]
        if i < win or pd.isna(vix.loc[d]):
            continue
        valid, wv, sig, S, wsw, self_t, sum_ws = _corr_terms(ctx.ret.iloc[i - win + 1:i + 1], w)
        if len(valid) < 10:
            continue
        denom = sum_ws ** 2 - self_t
        s_imp = vix.loc[d] / 100.0
        rho_imp = float(np.clip((s_imp ** 2 - self_t) / denom, -1, 1))
        rho_real = float(np.clip((wsw - self_t) / denom, -1, 1))
        rows.append((d, rho_imp, rho_real, s_imp, float(np.sqrt(wsw)), float(np.sqrt(self_t))))
    if len(rows) < 20:
        return entry("6.3", "Dispersion trading in equity indexes", CAT, "Long constituent volatility, short index volatility.", {"notes": ["Not enough data."]}, status="proxy")
    df = pd.DataFrame(rows, columns=["d", "rho_imp", "rho_real", "vix", "vol_theory", "vol_specific"]).set_index("d")
    cur = df.iloc[-1]
    spread = df["rho_imp"] - df["rho_real"]
    pct = float((spread <= spread.iloc[-1]).mean() * 100)
    if spread.iloc[-1] > 0.10 and pct >= 60:
        lab, bias = "DISPERSION ATTRACTIVE: index vol rich vs constituents", "short"
    elif spread.iloc[-1] < -0.05:
        lab, bias = "REVERSE DISPERSION: index vol cheap vs constituents", "long"
    else:
        lab, bias = "NO CLEAR EDGE", "neutral"
    charts = [
        {"title": "Implied vs realised average correlation", "type": "line", "x": [str(d.date()) for d in df.index],
         "series": [{"name": "Implied (from India VIX)", "data": [round(v, 3) for v in df.rho_imp]},
                    {"name": "Realised (63d)", "data": [round(v, 3) for v in df.rho_real]}], "yfmt": "num"},
        {"title": "Index volatility: India VIX vs constituent-implied theoretical", "type": "line", "x": [str(d.date()) for d in df.index],
         "series": [{"name": "India VIX", "data": [round(v * 100, 2) for v in df.vix]},
                    {"name": "Theoretical (realised vols & correlations)", "data": [round(v * 100, 2) for v in df.vol_theory]}], "yfmt": "pct"},
    ]
    top = w.sort_values(ascending=False).head(10)
    tab = M.table("Largest index weights", ["Stock", "Weight"], [[ctx.names[k], f"{v:.1%}"] for k, v in top.items()])
    blk = {
        "signal": M.signal(lab, bias, f"Implied corr {cur.rho_imp:.2f} vs realised {cur.rho_real:.2f}"),
        "metrics": {"implied_corr": round(cur.rho_imp, 3), "realised_corr": round(cur.rho_real, 3),
                    "corr_spread": round(float(spread.iloc[-1]), 3), "spread_percentile": round(pct, 1),
                    "vix": round(cur.vix * 100, 2), "theoretical_vol": round(cur.vol_theory * 100, 2)},
        "charts": charts, "tables": [tab],
        "notes": [
            "PROXY: the book's trade is long ATM straddles on every constituent and short an index straddle (Eq. 423-424), which needs single-stock implied volatilities. "
            "Yahoo Finance has none for Indian stocks, so constituents' trailing 63-day realised volatilities stand in for their implied vols.",
            f"Index implied vol = India VIX{' (also used for the SENSEX, which has no volatility index of its own)' if ctx.universe == 'SENSEX30' else ''}. "
            f"Implied correlation ρ = (σ²_VIX − Σw²σ²) / ((Σwσ)² − Σw²σ²). Weights: {w.attrs['src']}.",
            "Dispersion is attractive when the implied correlation sits well above what the constituents have actually realised (index options rich vs the basket). No P&L backtest is shown because it would need real option prices.",
        ],
    }
    return entry("6.3", "Dispersion trading in equity indexes", CAT,
                 "Sell index volatility and buy constituent volatility when index options imply more correlation than stocks actually deliver.", blk, status="proxy",
                 extra={"adapted_note": "Uses realised constituent vols in place of single-stock implied vols (not on Yahoo Finance)."})


def s6_3_1(ctx: Ctx, win=252, n_star=15):
    w = _weights(ctx)
    R = ctx.ret.iloc[-win:]
    valid = [k for k in R.columns if R[k].notna().all()]
    if len(valid) < 20:
        return entry("6.3.1", "Dispersion trading – subset portfolio", CAT, "Dispersion on a subset of constituents.", {"notes": ["Not enough data."]}, status="proxy")
    Rv = R[valid]
    Cm, sig, K, er, xi2 = stat_risk_model(Rv)
    ww = w.reindex(valid)
    ww = (ww / ww.sum()).values
    sig_a = sig * np.sqrt(C.TRADING_DAYS)
    sys_var = float(ww @ (Cm * C.TRADING_DAYS) @ ww)                   # Eq. 427 (full)
    spec = (ww * sig_a) ** 2 * xi2                                     # w_i^2 sigma_i^2 xi_i^2
    order = np.argsort(spec)
    chosen = [valid[i] for i in order[:n_star]]
    share = float(ww[order[:n_star]].sum())
    vix = float(ctx.vix.iloc[-1]) / 100.0
    rows = [[ctx.names[valid[i]], f"{ww[i]:.1%}", f"{sig_a[i]:.1%}", f"{np.sqrt(xi2[i]):.2f}", f"{spec[i] * 1e4:.2f}"] for i in order[:n_star]]
    blk = {
        "signal": M.signal(f"Trade {n_star}-stock dispersion basket ({share:.0%} of index weight)", "neutral",
                           f"Theoretical index vol {np.sqrt(sys_var) * 100:.1f}% vs VIX {vix * 100:.1f}%"),
        "metrics": {"risk_factors_K": K, "erank": round(er, 2), "theoretical_vol": round(float(np.sqrt(sys_var)) * 100, 2),
                    "vix": round(vix * 100, 2), "subset_weight_share": round(share, 3)},
        "tables": [M.table(f"Subset: {n_star} stocks with the lowest specific-risk contribution w²σ²ξ²",
                           ["Stock", "Index weight", "Volatility (252d)", "Specific risk ξ", "w²σ²ξ² (bp²)"], rows)],
        "notes": [
            f"PROXY (see 6.3). The 252-day correlation matrix is replaced by a statistical risk model ψ = diag(ξ²) + Σₐ λₐ VₐVₐ' with K = {K} principal components "
            f"(K from eRank = {er:.1f}; Eqs. 425-427). The long straddle book only contains the {n_star} names with the smallest specific-risk term w²σ²ξ², "
            "which cuts the number of option legs while keeping the dispersion bet.",
            f"Index volatility implied by the risk model: {np.sqrt(sys_var) * 100:.1f}% annualised vs India VIX {vix * 100:.1f}%. Weights: {w.attrs['src']}.",
        ],
    }
    return entry("6.3.1", "Dispersion trading – subset portfolio", CAT,
                 "Run the dispersion trade on only the few constituents with the lowest idiosyncratic risk, using a PCA risk model to keep the correlation matrix stable.",
                 blk, status="proxy", extra={"adapted_note": "Same proxy as 6.3."})


# --------------------------------------------------------------------- 6.5

def s6_5(ctx: Ctx, target=0.12, L=1.5, kappa=0.10):
    close = ctx.index.dropna()
    r = ctx.index_ret.reindex(close.index)
    vix = ctx.vix.reindex(close.index).ffill()
    sigma = (vix / 100.0).shift(1)
    dates = M.rebalance_dates(close.index, "W")
    w_cur = None
    rows = {}
    for d in dates:
        s = sigma.loc[d]
        if pd.isna(s) or s <= 0:
            continue
        w_new = min(L, target / s)
        if w_cur is None or abs(w_new - w_cur) / max(w_cur, 1e-9) > kappa:
            w_cur = w_new
        rows[d] = w_cur
    wser = pd.Series(rows)
    cash = pd.Series(C.RISK_FREE / C.TRADING_DAYS, index=close.index)
    ret2 = pd.DataFrame({"risky": r, CASH_COL: cash})
    W = pd.DataFrame({"risky": wser, CASH_COL: 1.0 - wser})
    net, gross, turn = M.run_weights(ret2, W, cost_bps=C.COST_BPS)
    # benchmark = buy & hold index
    w_now = float(wser.iloc[-1])
    ws = wser.reindex(close.index).ffill()
    mstep = max(1, len(ws) // 260)
    chart = {"title": f"Equity allocation (target vol {target:.0%}, cap {L:.1f}x)", "type": "line",
             "x": [str(d.date()) for d in ws.index[::mstep]], "series": [{"name": "Weight in index", "data": [round(float(v), 3) for v in ws.values[::mstep]]}], "yfmt": "num"}
    blk = M.block(
        net=net, gross=gross, turnover=turn, bench=r,
        signal=M.signal(f"Hold {w_now:.0%} {ctx.idx_name} / {max(0, 1 - w_now):.0%} cash" if w_now <= 1 else f"{w_now:.0%} {ctx.idx_name} (levered, funded at {C.RISK_FREE:.1%})",
                        "long" if w_now > 0.5 else "neutral", f"Implied vol (India VIX) {float(vix.iloc[-1]):.1f}% → w = {target:.0%}/{float(vix.iloc[-1]):.1f}%"),
        charts=[chart],
        notes=[f"Risky weight w = σ*/σ with σ* = {target:.0%} and σ = India VIX (implied, forward-looking; used for the SENSEX too). Rest in a risk-free asset earning {C.RISK_FREE:.1%} "
               f"(Yahoo Finance has no Indian T-bill series; this is an input in config.py). Max leverage {L:.1f}x. Checked weekly; rebalanced only if the weight changes by more than {kappa:.0%} (the book's κ threshold)."])
    return entry("6.5", "Index volatility targeting with risk-free asset", CAT,
                 "Hold the index at a weight inversely proportional to its volatility so portfolio risk stays near a constant target, parking the rest in a risk-free asset.", blk)


CASH_COL = "cash"


def run(ctx: Ctx):
    out = {}
    for fn, sid, nm in ((s6_3, "6.3", "Dispersion trading in equity indexes"), (s6_3_1, "6.3.1", "Dispersion trading \u2013 subset portfolio"),
                        (s6_5, "6.5", "Index volatility targeting with risk-free asset")):
        out[sid] = guarded(fn, sid, nm, CAT, ctx)
    return out
