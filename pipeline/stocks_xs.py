"""Chapter 3 – cross-sectional stock strategies (momentum, value, low-vol, multifactor,
residual momentum, pairs, mean-reversion family, statistical arbitrage, alpha combos)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import config as C
from . import metrics as M
from . import universe as U
from .common import (Ctx, entry, guarded, xs_result, weights_result, position_table, norm_abs, ls_return_series)

CAT = "stocks"


# ----------------------------------------------------------------- shared helpers

def _rows_to_df(rows: dict, columns) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows).T.reindex(columns=columns).sort_index()


def momentum_score(ctx: Ctx, T=252, S=21) -> pd.DataFrame:
    """R^cum = P(S) / P(S+T) - 1  (Eq. 267): formation period T, skipping the latest S days."""
    return ctx.close.shift(S) / ctx.close.shift(T) - 1.0


def lowvol_score(ctx: Ctx, window=126) -> pd.DataFrame:
    return -ctx.ret.rolling(window, min_periods=window).std()


def stat_risk_model(R: pd.DataFrame):
    """Statistical risk model of Kakushadze & Yu: PCA of the correlation matrix, K from eRank,
    specific risk on the diagonal.  Returns (C, sigma)."""
    S = R.cov().values
    sig = np.sqrt(np.diag(S))
    corr = S / np.outer(sig, sig)
    vals, vecs = np.linalg.eigh(corr)
    order = np.argsort(vals)[::-1]
    vals, vecs = np.clip(vals[order], 0, None), vecs[:, order]
    p = vals / vals.sum()
    erank = math.exp(-np.sum(p[p > 0] * np.log(p[p > 0])))
    K = int(min(max(round(erank), 1), len(vals) - 1, len(R) - 2))
    V = vecs[:, :K]
    lam = vals[:K]
    xi2 = np.clip(1.0 - (V ** 2 * lam).sum(axis=1), 1e-4, None)
    psi = (V * lam) @ V.T + np.diag(xi2)
    return psi * np.outer(sig, sig), sig, K, erank, xi2


def _beta_to_index(ctx: Ctx, end_pos: int, window=252) -> pd.Series:
    r = ctx.ret.iloc[max(0, end_pos - window + 1):end_pos + 1]
    m = ctx.index_ret.iloc[max(0, end_pos - window + 1):end_pos + 1]
    mc = m - m.mean()
    ok = r.notna().all()
    b = ((r.loc[:, ok] - r.loc[:, ok].mean()).mul(mc, axis=0)).sum() / (mc ** 2).sum()
    return b.reindex(r.columns)


# --------------------------------------------------------------------- 3.1 - 3.7

def s3_1(ctx: Ctx):
    mom = momentum_score(ctx)
    blk = xs_result(ctx, mom, freq="M", score_label="12-1m return", fmt="{:+.1%}", notes=[
        "Score = cumulative return over the last 12 months skipping the most recent month (Eq. 267, T = 12, S = 1)."])
    return entry("3.1", "Price-momentum", CAT,
                 "Buy the best performers and short the worst performers over the past 12 months (skipping the latest month), holding for a month.", blk)


def s3_3(ctx: Ctx):
    pb = ctx.fund_series("priceToBook")
    pb = pb.where(pb > 0)
    bp = 1.0 / pb
    cov = int(bp.notna().sum())
    if cov < 10:
        blk = {"notes": [f"Yahoo Finance returned price-to-book for only {cov} stocks, not enough for a decile sort."]}
        return entry("3.3", "Value", CAT, "Buy high book-to-price stocks and short low book-to-price stocks.", blk)
    s = bp.dropna().sort_values(ascending=False)
    k = max(1, int(round(len(s) * C.XS_FRACTION)))
    longs, shorts = list(s.index[:k]), list(s.index[-k:])
    rows = [["Long" if i in longs else "Short" if i in shorts else "", ctx.names[i], f"{pb[i]:.2f}", f"{bp[i]:.3f}",
             int(r + 1)] for r, i in enumerate(s.index)]
    blk = {
        "signal": M.xs_signal([ctx.names[i] for i in longs], [ctx.names[i] for i in shorts]),
        "tables": [M.table("Value ranking (live from Yahoo Finance)", ["Side", "Stock", "P/B", "B/P", "Rank"], rows)],
        "metrics": {"coverage": cov},
        "notes": [
            "Value = Book-to-Price (B/P), the inverse of Yahoo's current price-to-book. Top quintile long, bottom quintile short.",
            "No historical backtest: Yahoo Finance only exposes today's book value, so a back-dated value sort would use information that was not available at the time (look-ahead bias).",
        ],
    }
    return entry("3.3", "Value", CAT,
                 "Buy high book-to-price (cheap) stocks and short low book-to-price (expensive) stocks.", blk)


def s3_4(ctx: Ctx):
    blk = xs_result(ctx, lowvol_score(ctx), freq="M", score_label="-Volatility (126d)", fmt="{:.4f}", notes=[
        "Score = minus the 126-day daily return volatility; long the calmest stocks, short the most volatile."])
    return entry("3.4", "Low-volatility anomaly", CAT,
                 "Low-risk stocks have historically earned better risk-adjusted returns than high-risk stocks: buy the lowest-volatility names, short the highest.", blk)


def _rank_demeaned(df: pd.DataFrame) -> pd.DataFrame:
    r = df.rank(axis=1)
    return r.sub(r.mean(axis=1), axis=0)


def s3_6(ctx: Ctx):
    mom, lv = momentum_score(ctx), lowvol_score(ctx)
    score = (_rank_demeaned(mom) + _rank_demeaned(lv)) / 2.0
    extra = []
    pb = ctx.fund_series("priceToBook")
    pb = pb.where(pb > 0)
    if pb.notna().sum() >= 0.7 * len(ctx.keys):
        r_val = (1 / pb).rank()
        r_val = r_val - r_val.mean()
        last = score.iloc[-1]
        three = ((last.fillna(0) * 2 + r_val.reindex(last.index).fillna(0)) / 3.0).where(last.notna())
        o = three.dropna().sort_values(ascending=False)
        rows = [[i + 1, ctx.names[k], f"{v:+.1f}"] for i, (k, v) in enumerate(o.items())]
        extra.append(M.table("Live 3-factor ranking (momentum + low-vol + value)", ["Rank", "Stock", "Combined rank score"], rows))
    blk = xs_result(ctx, score, freq="M", score_label="Avg demeaned rank", fmt="{:+.1f}", extra_tables=extra, notes=[
        "Factors combined by averaging demeaned cross-sectional ranks (Eqs. 276-277): momentum (12-1m) and low volatility. "
        "Value is shown in the live 3-factor table only, because Yahoo has no point-in-time book values to backtest it."])
    return entry("3.6", "Multifactor portfolio", CAT,
                 "Blend several factors (momentum, low-volatility, value) by averaging their demeaned ranks, then go long the best blended scores and short the worst.", blk)


def s3_7(ctx: Ctx, T_form=252, T_reg=756, skip=21):
    ret, mkt = ctx.ret, ctx.index_ret
    dates = M.rebalance_dates(ret.index, "M")
    pos = {d: i for i, d in enumerate(ret.index)}
    rows = {}
    R = ret.values
    m = mkt.values
    for d in dates:
        i = pos[d]
        if i < T_reg + skip + 5:
            continue
        reg = slice(i - skip - T_reg + 1, i - skip + 1)
        Rr, mr = R[reg], m[reg]
        ok = ~np.isnan(Rr).any(axis=0) & ~np.isnan(mr).any()
        if ok.sum() < 8:
            continue
        mc = mr - mr.mean()
        beta = np.full(R.shape[1], np.nan)
        beta[ok] = ((Rr[:, ok] - Rr[:, ok].mean(axis=0)) * mc[:, None]).sum(axis=0) / (mc ** 2).sum()
        form = slice(i - skip - T_form + 1, i - skip + 1)
        eps = R[form] - np.outer(m[form], beta)            # alpha excluded (Eq. 279)
        mu, sd = np.nanmean(eps, axis=0), np.nanstd(eps, axis=0, ddof=1)
        sc = np.where(sd > 0, mu / sd, np.nan)
        sc[~ok] = np.nan
        rows[d] = pd.Series(sc, index=ret.columns)
    score = _rows_to_df(rows, ret.columns)
    blk = xs_result(ctx, score, freq="M", score_label="Risk-adj. residual", fmt="{:+.3f}", notes=[
        f"Residuals from a 36-month regression of each stock on the {ctx.idx_name} (the only broad market factor available for India on Yahoo; "
        "the book also uses Fama-French SMB/HML, which are not published for the Indian market). Residuals are computed over the 12-month formation period "
        "skipping 1 month, then risk-adjusted (Eqs. 279-282)."])
    return entry("3.7", "Residual momentum", CAT,
                 "Momentum computed on the part of each stock's return that is NOT explained by the market, so the bet is on stock-specific trends rather than market beta.",
                 blk, status="adapted",
                 extra={"adapted_note": "Uses a single market factor (index) instead of Fama-French 3 factors."})


# ----------------------------------------------------------------------- 3.8 pairs

def s3_8(ctx: Ctx, form=252, hold=126, zwin=60, K=8, z_in=2.0, z_out=0.5):
    lr = np.log(ctx.close)
    lrets = ctx.logret
    n = len(ctx.dates)
    port = np.zeros(n)
    turn = np.zeros(n)
    ret = ctx.ret.values
    col = {k: i for i, k in enumerate(ctx.keys)}
    z_cache = {}

    def zscore(a, b):
        if (a, b) not in z_cache:
            sp = lr[a] - lr[b]
            z_cache[(a, b)] = ((sp - sp.rolling(zwin).mean()) / sp.rolling(zwin).std()).values
        return z_cache[(a, b)]

    def select(end_pos):
        win = lrets.iloc[end_pos - form:end_pos]
        valid = [k for k in win.columns if win[k].notna().all()]
        cor = win[valid].corr()
        cands = []
        for sec in ctx.sector_names:
            mem = [k for k in valid if ctx.sector[k] == sec]
            for i in range(len(mem)):
                for j in range(i + 1, len(mem)):
                    cands.append((cor.loc[mem[i], mem[j]], mem[i], mem[j]))
        cands.sort(reverse=True)
        return cands[:K]

    start = form + zwin
    first_active = None
    while start + 2 < n:
        sel = select(start)
        end = min(n, start + hold)
        for _c, a, b in sel:
            z = zscore(a, b)
            pos = 0
            posarr = np.zeros(n)
            for i in range(start, end):
                zi = z[i]
                if np.isnan(zi):
                    pos = 0
                elif pos == 0:
                    pos = -1 if zi > z_in else (1 if zi < -z_in else 0)
                elif pos == 1 and zi > -z_out:
                    pos = 0
                elif pos == -1 and zi < z_out:
                    pos = 0
                posarr[i] = pos
            posarr[end - 1] = 0
            prev = np.concatenate([[0], posarr[:-1]])
            ra, rb = np.nan_to_num(ret[:, col[a]]), np.nan_to_num(ret[:, col[b]])
            # position decided at close i is held over day i+1
            held = np.concatenate([[0], posarr[:-1]])
            port += held * (ra - rb) / 2.0 / K
            turn += np.abs(held - np.concatenate([[0], held[:-1]])) / K
            if first_active is None and posarr.any():
                first_active = start
        start += hold
    idx = ctx.dates
    gross = pd.Series(port, index=idx)
    net = gross - pd.Series(turn, index=idx) * C.COST_BPS / 1e4
    if first_active is None:
        return entry("3.8", "Pairs trading", CAT, "Trade the spread between two historically correlated stocks.", {"notes": ["No pair triggered a trade."]})
    net, gross = net.iloc[first_active:], gross.iloc[first_active:]
    # live view
    sel = select(n - 1)
    rows, active = [], []
    for c, a, b in sel:
        z = zscore(a, b)[-1]
        if z > z_in:
            act = f"Short {ctx.names[a]} / Long {ctx.names[b]}"; active.append(act)
        elif z < -z_in:
            act = f"Long {ctx.names[a]} / Short {ctx.names[b]}"; active.append(act)
        else:
            act = "Wait"
        rows.append([ctx.names[a], ctx.names[b], U.sector_name(ctx.sector[a]), f"{c:.2f}", f"{z:+.2f}", act])
    blk = M.block(
        net=net, gross=gross, turnover=pd.Series(turn, index=idx).iloc[first_active:], bench=ctx.index_ret,
        signal=M.signal(f"{len(active)} of {len(sel)} pairs actionable" if active else "No pair beyond ±2σ",
                        "mixed" if active else "neutral", "; ".join(active) if active else None),
        tables=[M.table("Top correlated same-sector pairs (formed on last 252 days)",
                        ["Stock A", "Stock B", "Sector", "Correlation", "Spread z-score", "Action"], rows)],
        notes=[f"Each {hold} trading days the {K} most correlated same-sector pairs are selected on the prior {form} days. "
               f"The log-price spread z-score (rolling {zwin}d) triggers a dollar-neutral trade at |z| > {z_in:g} and exits at |z| < {z_out:g} (long the cheap, short the rich stock). "
               "Pairs are re-selected every period and any open trade is closed.",
               "Shorting single stocks in India is done through stock futures (F&O stocks) or intraday; borrow, margin and slippage are not modelled."])
    return entry("3.8", "Pairs trading", CAT,
                 "Find two historically highly-correlated stocks; when their prices diverge, short the rich one and buy the cheap one, expecting convergence.", blk)


# ------------------------------------------------------- 3.9 / 3.9.1 / 3.10 / 3.18

def mr_weights(R: pd.Series, Omega: pd.DataFrame | None = None, z: pd.Series | None = None) -> pd.Series:
    """Cluster-neutral mean-reversion weights D_i = -R~_i normalised to sum |w| = 1.
    Omega=None: demean by the cross-sectional mean (3.9).  Otherwise weighted regression (3.10)."""
    v = R.dropna()
    if len(v) < 6:
        return pd.Series(0.0, index=R.index)
    if Omega is None:
        Rt = v - v.mean()
    else:
        Om = Omega.loc[v.index].values
        if z is None:
            Z = np.ones(len(v))
        else:
            zz = z.reindex(v.index).replace([np.inf, -np.inf], np.nan)
            if zz.notna().sum() < 6:
                return pd.Series(0.0, index=R.index)
            Z = zz.fillna(zz.median()).values
        Q = Om.T @ (Om * Z[:, None])
        f = np.linalg.pinv(Q) @ (Om.T @ (Z * v.values))
        eps = v.values - Om @ f
        Rt = pd.Series(Z * eps if z is not None else eps, index=v.index)
    D = -Rt
    w = norm_abs(D)
    return w.reindex(R.index).fillna(0.0)


def _weekly_mr(ctx: Ctx, make_w, lookback=5):
    rets = ctx.logret.rolling(lookback).sum()
    dates = M.rebalance_dates(ctx.dates, "W")
    rows, last_R = {}, None
    for d in dates:
        R = rets.loc[d]
        if R.notna().sum() < 8:
            continue
        rows[d] = make_w(R, d)
        last_R = R
    return _rows_to_df(rows, ctx.keys), last_R


def s3_9(ctx: Ctx):
    W, R = _weekly_mr(ctx, lambda R, d: mr_weights(R))
    blk = weights_result(ctx, W, score_last=-(R - R.mean()) if R is not None else None, score_label="Reversal signal",
                         fmt="{:+.3f}", notes=[
        "All stocks form one cluster. Weights Dᵢ = −γ(Rᵢ − mean R) on 5-day log returns (Eqs. 294-298): short the stocks that rose most, buy those that fell most."])
    return entry("3.9", "Mean-reversion – single cluster", CAT,
                 "Treat the whole universe as one cluster: short stocks that outperformed the cluster average over the past week and buy those that underperformed.", blk)


def s3_9_1(ctx: Ctx):
    groups = pd.Series(ctx.sector)

    def mk(R, d):
        v = R.dropna()
        Rt = v - v.groupby(groups.reindex(v.index)).transform("mean")
        return norm_abs(-Rt).reindex(R.index).fillna(0.0)

    W, R = _weekly_mr(ctx, mk)
    last = None
    if R is not None:
        v = R.dropna()
        last = -(v - v.groupby(groups.reindex(v.index)).transform("mean"))
    blk = weights_result(ctx, W, score_last=last, score_label="Reversal vs sector", fmt="{:+.3f}", notes=[
        "Clusters are the sectors defined in universe.py; each stock's 5-day return is demeaned against its sector average (Eqs. 303-309), so the book is sector-neutral."])
    return entry("3.9.1", "Mean-reversion – multiple clusters", CAT,
                 "Run mean-reversion inside each sector: short a sector's recent outperformers and buy its laggards, keeping the portfolio sector-neutral.", blk)


def s3_10(ctx: Ctx):
    vol = ctx.ret.rolling(126, min_periods=126).std()
    pos = {d: i for i, d in enumerate(ctx.dates)}

    def mk(R, d):
        beta = _beta_to_index(ctx, pos[d]).reindex(R.index)
        Om = ctx.omega_sector.copy()
        sd = beta.std()
        Om["beta"] = ((beta - beta.mean()) / sd) if sd and sd > 0 else 0.0
        Om = Om.fillna(0.0)
        z = 1.0 / vol.loc[d] ** 2
        return mr_weights(R, Om, z)

    W, R = _weekly_mr(ctx, mk)
    last = None
    if R is not None and not W.empty:
        last = W.iloc[-1]
    blk = weights_result(ctx, W, score_last=last, score_label="Weight", fmt="{:+.3f}", notes=[
        "Weighted regression of 5-day returns on sector dummies plus the stock's market beta (a non-binary loading), with regression weights zᵢ = 1/σᵢ² (Eqs. 313-317). "
        "The twiddled returns R~ = Zε are orthogonal to every loading column, so the book is sector- and beta-neutral."])
    return entry("3.10", "Mean-reversion – weighted regression", CAT,
                 "Generalised mean-reversion: regress returns on sector and style loadings with 1/variance weights and bet against the residual, neutralising every risk factor.", blk)


def _statarb(ctx: Ctx, neutral: bool):
    groups = pd.Series(ctx.sector)
    rets5 = ctx.logret.rolling(5).sum()
    dates = M.rebalance_dates(ctx.dates, "W")
    pos = {d: i for i, d in enumerate(ctx.dates)}
    rows, last_info = {}, None
    for d in dates:
        i = pos[d]
        if i < 300:
            continue
        win = ctx.ret.iloc[i - 251:i + 1]
        valid = [k for k in win.columns if win[k].notna().all()]
        if len(valid) < 12:
            continue
        R5 = rets5.loc[d, valid]
        Rt = R5 - R5.groupby(groups.reindex(valid)).transform("mean")
        E = (-Rt).values                                  # mean-reversion expected returns
        Cm, sig, K, er, _xi2 = stat_risk_model(win[valid])
        ones = np.ones(len(valid))
        x = np.linalg.solve(Cm, E)
        if neutral:
            y = np.linalg.solve(Cm, ones)
            x = x - y * (ones @ x) / (ones @ y)
        w = pd.Series(x, index=valid)
        w = norm_abs(w).reindex(ctx.keys).fillna(0.0)
        rows[d] = w
        last_info = (K, er)
    W = _rows_to_df(rows, ctx.keys)
    return W, last_info


def s3_18(ctx: Ctx):
    W, info = _statarb(ctx, False)
    blk = weights_result(ctx, W, score_label="Weight", score_last=W.iloc[-1] if not W.empty else None, fmt="{:+.3f}", notes=[
        "Mean-variance optimisation w ∝ C⁻¹E (Eq. 350) with E = sector-neutral 5-day mean-reversion forecast and C = statistical risk model "
        f"(PCA of the 252-day correlation matrix, K = {info[0] if info else '?'} factors from eRank, specific risk on the diagonal). Not dollar-neutral."])
    return entry("3.18", "Statistical arbitrage – optimization", CAT,
                 "Turn expected returns into portfolio weights by maximising the Sharpe ratio w = C⁻¹E using a stable model covariance matrix.", blk)


def s3_18_1(ctx: Ctx):
    W, info = _statarb(ctx, True)
    blk = weights_result(ctx, W, score_label="Weight", score_last=W.iloc[-1] if not W.empty else None, fmt="{:+.3f}", notes=[
        "Same optimiser as 3.18 with a Lagrange multiplier enforcing Σw = 0 (Eq. 358): the portfolio is exactly dollar-neutral and risk-managed through C⁻¹."])
    return entry("3.18.1", "Dollar-neutrality", CAT,
                 "Add the dollar-neutrality constraint Σw = 0 to the Sharpe-maximising optimiser so the book is long and short in equal dollars.", blk)


# --------------------------------------------------------------------- 3.20 combos

def _alpha_scores(ctx: Ctx) -> dict[str, pd.DataFrame]:
    c, h, l = ctx.close, ctx.high, ctx.low
    lg = ctx.logret
    sc: dict[str, pd.DataFrame] = {}
    for L in (21, 42, 63, 126, 189, 252):
        for s in (0, 5, 21):
            if s < L:
                sc[f"Momentum {L}d skip {s}"] = c.shift(s) / c.shift(L) - 1
    for w in (21, 63, 126, 252):
        sc[f"Low-vol {w}d"] = -ctx.ret.rolling(w).std()
    Om = ctx.omega_sector.values
    cnt = Om.sum(axis=0)
    for L in (1, 2, 3, 5, 10, 15, 20):
        base = -lg.rolling(L).sum()
        sc[f"Reversal {L}d"] = base.sub(base.mean(axis=1), axis=0)
        sec_mean = (base.fillna(0).values @ (Om / cnt)) @ Om.T
        sc[f"Sector reversal {L}d"] = base - sec_mean
    for a, b in ((5, 20), (10, 30), (20, 60), (20, 100), (50, 200)):
        sc[f"MA {a}/{b}"] = c.rolling(a).mean() / c.rolling(b).mean() - 1
    for w in (20, 60, 120):
        mn, mx = c.rolling(w).min(), c.rolling(w).max()
        sc[f"Range reversion {w}d"] = 1 - (c - mn) / (mx - mn)
    ibs = (c - l) / (h - l)
    sc["IBS reversal"] = -ibs.where((h - l) > 0)
    sc["52-week high"] = c / c.rolling(252).max()
    return sc


def alpha_combo_weights(Rwin: np.ndarray, d: int = 21):
    """Steps 1-11 of Section 3.20 for a (M+1) x N matrix of alpha returns (oldest row first)."""
    R = Rwin[::-1]
    M_ = R.shape[0] - 1
    X = R - R.mean(axis=0)
    sig = np.sqrt((X ** 2).sum(axis=0) / M_)
    sig = np.where(sig > 0, sig, np.nan)
    Y = (X / sig)[:M_]
    Lam = (Y - Y.mean(axis=1, keepdims=True))[: M_ - 1]
    E = R[:d].mean(axis=0) / sig
    A = Lam.T
    coef, *_ = np.linalg.lstsq(A, E, rcond=None)
    eps = E - A @ coef
    w = eps / sig
    s = np.abs(w).sum()
    return w / s if s > 0 else w


def s3_20(ctx: Ctx, Mwin=30, d=21):
    scores = _alpha_scores(ctx)
    A = pd.DataFrame({k: ls_return_series(v, ctx.ret) for k, v in scores.items()})
    last_w = {}
    for k, v in scores.items():
        row = v.iloc[-1]
        dm = row - row.mean()
        s = dm.abs().sum()
        last_w[k] = (dm / s).fillna(0.0) if s > 0 else dm.fillna(0.0)
    dates = M.rebalance_dates(A.index, "M")
    pos = {dt: i for i, dt in enumerate(A.index)}
    combo = pd.Series(np.nan, index=A.index)
    ew = pd.Series(np.nan, index=A.index)
    latest = None
    for j, dt in enumerate(dates):
        i = pos[dt]
        if i < 300:
            continue
        win = A.iloc[i - Mwin: i + 1]
        cols = [c for c in A.columns if win[c].notna().all()]
        if len(cols) < Mwin + 5:
            continue
        w = alpha_combo_weights(win[cols].values, d)
        nxt = dates[j + 1] if j + 1 < len(dates) else A.index[-1]
        seg = A.loc[(A.index > dt) & (A.index <= nxt), cols]
        if len(seg):
            combo.loc[seg.index] = seg.values @ w
            ew.loc[seg.index] = seg.mean(axis=1)
        latest = pd.Series(w, index=cols)
    combo, ew = combo.dropna(), ew.dropna()
    if latest is None or len(combo) < 100:
        return entry("3.20", "Alpha combos", CAT, "Combine many alphas into one 'mega-alpha'.", {"notes": ["Not enough alpha history."]})
    stock_w = sum(latest[k] * last_w[k] for k in latest.index)
    stock_w = norm_abs(stock_w)
    top = latest.reindex(latest.abs().sort_values(ascending=False).index).head(12)
    t_alpha = M.table("Largest alpha weights now", ["Alpha", "Weight in mega-alpha"], [[k, f"{v * 100:+.1f}%"] for k, v in top.items()])
    ordered = stock_w[stock_w.abs() > 1e-9].sort_values(ascending=False)
    longs = [ctx.names[k] for k in ordered[ordered > 0].index]
    shorts = [ctx.names[k] for k in ordered[ordered < 0].index[::-1]]
    blk = M.block(
        net=combo, bench=ctx.index_ret, extra_curves={"equal_weight_alphas": ew},
        signal=M.xs_signal(longs, shorts),
        tables=[position_table(ctx, stock_w, None, "", "{}"), t_alpha],
        notes=[f"{len(scores)} simple alphas (momentum, low-vol, reversal, sector reversal, MA crossovers, range/IBS reversion, 52-week high) are built as daily-rebalanced "
               f"long/short portfolios over the universe. Each month the 11-step procedure of Section 3.20 is run on the last {Mwin + 1} days of alpha returns "
               f"(d = {d}) to weight the alphas (weights ∝ residual of the expected-return regression on demeaned alpha returns, divided by volatility). "
               "The curve is the out-of-sample next-month return of the combination (no trading costs: alpha returns are pre-cost); the 'equal weight alphas' line is a naive benchmark.",
               "The table of stocks is the mega-alpha holding implied by the latest alpha weights."])
    return entry("3.20", "Alpha combos", CAT,
                 "Combine dozens of weak alphas into one 'mega-alpha' using a regression that down-weights alphas that are redundant with each other.", blk)


def run(ctx: Ctx):
    out = {}
    for fn, sid, name in ((s3_1, "3.1", "Price-momentum"), (s3_3, "3.3", "Value"), (s3_4, "3.4", "Low-volatility anomaly"),
                          (s3_6, "3.6", "Multifactor portfolio"), (s3_7, "3.7", "Residual momentum"), (s3_8, "3.8", "Pairs trading"),
                          (s3_9, "3.9", "Mean-reversion \u2013 single cluster"), (s3_9_1, "3.9.1", "Mean-reversion \u2013 multiple clusters"),
                          (s3_10, "3.10", "Mean-reversion \u2013 weighted regression"), (s3_18, "3.18", "Statistical arbitrage \u2013 optimization"),
                          (s3_18_1, "3.18.1", "Dollar-neutrality"), (s3_20, "3.20", "Alpha combos")):
        out[sid] = guarded(fn, sid, name, CAT, ctx)
    return out
