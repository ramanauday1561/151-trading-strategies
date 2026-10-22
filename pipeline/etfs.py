"""Chapter 4 – ETF / sector rotation strategies on NSE sector indices and Indian ETFs.

NSE sector indices stand in for sector ETFs (they have longer, cleaner Yahoo history than the
individual sector ETFs).  Gold/silver/Nasdaq ETFs (GOLDBEES, SILVERBEES, MON100) are used for the
multi-asset strategies.  Unavailable tickers are skipped automatically.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from . import metrics as M
from . import universe as U
from .common import Ctx, entry, guarded, xs_weights
from .stocks_xs import momentum_score

CAT = "etf"
CASH = "CASH"


class Assets:
    def __init__(self, md, mapping: dict, ctx: Ctx, min_days=500):
        self.cols = [c for c in mapping if c in md.close.columns and md.close[c].notna().sum() >= min_days]
        self.names = {c: mapping[c] for c in self.cols}
        self.close = md.close[self.cols]
        self.high, self.low = md.high[self.cols], md.low[self.cols]
        self.ret = self.close.pct_change(fill_method=None)
        self.dates = self.close.index
        self.ctx = ctx
        self.bench = ctx.index_ret
        cash = pd.Series(C.RISK_FREE / C.TRADING_DAYS, index=self.dates, name=CASH)
        self.ret_cash = pd.concat([self.ret, cash], axis=1)

    @property
    def n(self):
        return len(self.cols)


def _pick(score_row: pd.Series, n, top=True):
    s = score_row.dropna().sort_values(ascending=not top)
    return list(s.index[:n])


def _n_leg(N):
    return max(1, int(round(N * 0.3)))


def _result(ac: Assets, W: pd.DataFrame, score_last: pd.Series | None, score_label: str, fmt: str, notes, *,
            long_short=True, extra_tables=None, cost_bps=C.COST_BPS, extra_metrics=None):
    if W is None or W.empty:
        return {"notes": ["Not enough history/data to evaluate this strategy."]}
    ret = ac.ret_cash
    W = W.reindex(columns=ret.columns).fillna(0.0)
    net, gross, turn = M.run_weights(ret, W, cost_bps)
    pos = W.clip(lower=0)
    s = pos.sum(axis=1).replace(0, np.nan)
    lo, _, _ = M.run_weights(ret, pos.div(s, axis=0).fillna(0.0), cost_bps)
    last = W.iloc[-1]
    rows = []
    for k, v in last[last.abs() > 1e-9].sort_values(ascending=False).items():
        nm = "Cash" if k == CASH else ac.names.get(k, k)
        sc = "" if score_last is None or k not in score_last.index or pd.isna(score_last[k]) else fmt.format(score_last[k])
        rows.append(["Long" if v > 0 else "Short", nm, sc, f"{v * 100:+.1f}%"])
    longs = [r[1] for r in rows if r[0] == "Long"]
    shorts = [r[1] for r in rows if r[0] == "Short"]
    tables = [M.table("Target portfolio now", ["Side", "Asset", score_label, "Weight"], rows)]
    if score_last is not None:
        rank = score_last.dropna().sort_values(ascending=False)
        held = {k: ("Long" if last.get(k, 0) > 0 else "Short" if last.get(k, 0) < 0 else "") for k in rank.index}
        tables.append(M.table(f"Ranking by {score_label.lower()}", ["#", "Asset", score_label, "Position"],
                              [[i + 1, ac.names.get(k, k), fmt.format(v), held[k]] for i, (k, v) in enumerate(rank.items())]))
    if extra_tables:
        tables += extra_tables
    return M.block(
        net=net, gross=gross, turnover=turn, bench=ac.bench,
        extra_curves={"long_only": lo} if long_short else None,
        signal=M.xs_signal(longs, shorts), tables=tables, extra_metrics=extra_metrics,
        notes=notes + [f"{ac.n} assets: " + ", ".join(ac.names.values()) + f". {cost_bps:.0f} bps one-way cost. Dashed line = {ac.ctx.idx_name} buy-and-hold."])


# ------------------------------------------------------------------------ 4.1 family

def _monthly_rot(ac: Assets, score: pd.DataFrame, *, n=None, filt=None, long_short=True):
    dates = M.rebalance_dates(score.index, "M")
    n = n or _n_leg(ac.n)
    rows = {}
    for d in dates:
        s = score.loc[d].dropna()
        if len(s) < max(5, 2 * n):
            continue
        w = pd.Series(0.0, index=ac.ret_cash.columns)
        top, bot = _pick(s, n, True), _pick(s, n, False)
        if filt is not None:
            f = filt.loc[d]
            top = [k for k in top if f.get(k, False)]
            bot = [k for k in bot if not f.get(k, True)]
        if long_short:
            for k in top:
                w[k] = 0.5 / n
            for k in bot:
                w[k] = -0.5 / n
        else:
            for k in top:
                w[k] = 1.0 / n
        rows[d] = w
    return pd.DataFrame(rows).T if rows else pd.DataFrame()


def s4_1(ac: Assets, T=126):
    score = ac.close / ac.close.shift(T) - 1
    W = _monthly_rot(ac, score)
    blk = _result(ac, W, score.iloc[-1], "6m return", "{:+.1%}", [
        f"Cumulative return over the past {T} trading days (≈ 6 months, Eq. 361). Long the top {_n_leg(ac.n)}, short the bottom {_n_leg(ac.n)}, rebalanced monthly."])
    return entry("4.1", "Sector momentum rotation", CAT,
                 "Overweight the sectors that have outperformed over the past 6 months and underweight (short) the laggards, rebalancing monthly.", blk)


def s4_1_1(ac: Assets, T=126, Tma=150):
    score = ac.close / ac.close.shift(T) - 1
    above = ac.close > ac.close.rolling(Tma).mean()
    W = _monthly_rot(ac, score, filt=above)
    blk = _result(ac, W, score.iloc[-1], "6m return", "{:+.1%}", [
        f"Sector momentum with a trend filter: a top-ranked sector is bought only if its price is above its {Tma}-day moving average, and a bottom-ranked sector is shorted only if it is below it (Eq. 362). Filtered-out slots stay in cash."])
    return entry("4.1.1", "Sector momentum rotation with MA filter", CAT,
                 "Sector momentum, but only buy winners that are in an uptrend (above the 150-day average) and only short losers that are in a downtrend.", blk)


def s4_1_2(ac: Assets, T=126, Tma=200):
    score = ac.close / ac.close.shift(T) - 1
    mk = ac.ctx.index
    risk_on = mk > mk.rolling(Tma).mean()
    haven = C_HAVEN if C_HAVEN in ac.ret_cash.columns else CASH
    dates = M.rebalance_dates(score.index, "M")
    n = _n_leg(ac.n)
    rows = {}
    for d in dates:
        s = score.loc[d].dropna()
        if len(s) < 5 or pd.isna(risk_on.get(d)):
            continue
        w = pd.Series(0.0, index=ac.ret_cash.columns)
        if risk_on[d]:
            for k in _pick(s, n, True):
                w[k] = 1.0 / n
        else:
            w[haven] = 1.0
        rows[d] = w
    W = pd.DataFrame(rows).T if rows else pd.DataFrame()
    state = "RISK-ON" if bool(risk_on.iloc[-1]) else "RISK-OFF"
    blk = _result(ac, W, score.iloc[-1], "6m return", "{:+.1%}", [
        f"Relative momentum (top {n} sectors) is only used when the broad market ({ac.ctx.idx_name}) is above its {Tma}-day moving average (absolute momentum, Eq. 363). "
        f"Otherwise 100% moves to {'gold (GOLDBEES)' if haven != CASH else 'cash'}. Market regime now: {state}."], long_short=False)
    if "signal" in blk:
        blk["signal"]["detail"] = f"Market regime: {state}"
    return entry("4.1.2", "Dual-momentum sector rotation", CAT,
                 "Long-only sector rotation that switches entirely to gold/cash when the broad market is below its 200-day average.", blk)


C_HAVEN = U.UNCORRELATED_ASSET


# --------------------------------------------------------- 4.2 alpha / 4.3 R-squared

def _regress_window(R: np.ndarray, X: np.ndarray):
    """OLS with intercept. R: T x N, X: T x F.  Returns alpha (N), r2 (N)."""
    T = len(R)
    A = np.column_stack([np.ones(T), X])
    coef, *_ = np.linalg.lstsq(A, R, rcond=None)
    res = R - A @ coef
    ss_res = (res ** 2).sum(axis=0)
    ss_tot = ((R - R.mean(axis=0)) ** 2).sum(axis=0)
    r2 = 1 - ss_res / np.where(ss_tot > 0, ss_tot, np.nan)
    return coef[0], r2


def _momentum_factor(ctx: Ctx) -> pd.Series:
    score = momentum_score(ctx)
    dates = M.rebalance_dates(score.index, "M")
    W = xs_weights(score, dates, frac=0.3, long_short=True)
    g, _, _ = M.run_weights(ctx.ret, W, 0.0)
    return g.reindex(ctx.dates).fillna(0.0)


def s4_2(ac: Assets, win=252):
    pos = {d: i for i, d in enumerate(ac.dates)}
    R = ac.ret.values
    m = ac.bench.reindex(ac.dates).values
    dates = M.rebalance_dates(ac.dates, "M")
    rows = {}
    for d in dates:
        i = pos[d]
        if i < win + 5:
            continue
        r, x = R[i - win + 1:i + 1], m[i - win + 1:i + 1]
        ok = ~np.isnan(r).any(axis=0) & ~np.isnan(x).any()
        a = np.full(ac.n, np.nan)
        if ok.sum() >= 5:
            a[ok] = _regress_window(r[:, ok], x[:, None])[0] * C.TRADING_DAYS
        rows[d] = pd.Series(a, index=ac.cols)
    score = pd.DataFrame(rows).T
    W = _monthly_rot(ac, score)
    blk = _result(ac, W, score.iloc[-1] if len(score) else None, "Alpha (ann.)", "{:+.1%}", [
        f"Jensen's alpha = intercept of a 1-year daily regression of each sector's return on the {ac.ctx.idx_name} (Eq. 364; the book also uses SMB/HML, which are not published for India). Long the highest-alpha sectors, short the lowest."])
    return entry("4.2", "Alpha rotation", CAT,
                 "Rank sectors by Jensen's alpha versus the market (return left over after market beta) instead of raw return, and rotate into the highest-alpha ones.",
                 blk, status="adapted", extra={"adapted_note": "Single-factor (market) alpha instead of Fama-French 3-factor alpha."})


def s4_3(ac: Assets, win=252):
    mom = _momentum_factor(ac.ctx)
    pos = {d: i for i, d in enumerate(ac.dates)}
    R = ac.ret.values
    X = np.column_stack([ac.bench.reindex(ac.dates).values, mom.reindex(ac.dates).values])
    dates = M.rebalance_dates(ac.dates, "M")
    cols = ac.ret_cash.columns
    rows, last_tab = {}, None
    for d in dates:
        i = pos[d]
        if i < win + 5:
            continue
        r, x = R[i - win + 1:i + 1], X[i - win + 1:i + 1]
        ok = ~np.isnan(r).any(axis=0) & ~np.isnan(x).any()
        if ok.sum() < 6:
            continue
        a_, r2_ = _regress_window(r[:, ok], x)
        df = pd.DataFrame({"alpha": a_ * C.TRADING_DAYS, "r2": r2_}, index=np.array(ac.cols)[ok])
        k = max(1, int(round(len(df) * 0.34)))
        low_r2 = df.sort_values("r2").head(k)
        high_r2 = df.sort_values("r2").tail(k)
        longs = list(low_r2.sort_values("alpha", ascending=False).index[:2])
        shorts = list(high_r2.sort_values("alpha").index[:2])
        w = pd.Series(0.0, index=cols)
        for s_ in longs:
            w[s_] = 0.5 / len(longs)
        for s_ in shorts:
            w[s_] -= 0.5 / len(shorts)
        rows[d] = w
        last_tab = df
    W = pd.DataFrame(rows).T if rows else pd.DataFrame()
    extra = []
    score_last = None
    if last_tab is not None:
        extra.append(M.table("Alpha and R² (latest 1-year regression on market + momentum factors)", ["Asset", "Alpha (ann.)", "R²", "Selectivity 1−R²"],
                             [[ac.names[k], f"{v.alpha:+.1%}", f"{v.r2:.2f}", f"{1 - v.r2:.2f}"] for k, v in last_tab.sort_values("r2").iterrows()]))
        score_last = last_tab["r2"]
    blk = _result(ac, W, score_last, "R²", "{:.2f}", [
        "Each month sectors are regressed (252 days) on two factors: the market index and a momentum factor built from the constituents' own 12-1m long/short portfolio (Eq. 365 uses MKT, SMB, HML, MOM; only these two are available for India). "
        "Long the highest-alpha sectors within the lowest-R² tercile (high 'selectivity'), short the lowest-alpha sectors within the highest-R² tercile."],
        extra_tables=extra)
    return entry("4.3", "R-squared", CAT,
                 "Prefer sectors whose returns are NOT explained by common factors (low R²) and have high alpha; avoid high-R², low-alpha ones.",
                 blk, status="adapted", extra={"adapted_note": "Uses market + constructed momentum factor (Fama-French factors are not available for India)."})


# ------------------------------------------------------------------ 4.4 IBS reversion

def s4_4(ac: Assets):
    rng = (ac.high - ac.low)
    ibs = ((ac.close - ac.low) / rng).where(rng > 0)
    score = -ibs                                   # high score = close near the low = cheap
    n = max(1, int(round(ac.n * 0.2)))
    dates = ac.dates
    rows = {}
    for d in dates[1:]:
        s = score.loc[d].dropna()
        if len(s) < max(5, 2 * n):
            continue
        w = pd.Series(0.0, index=ac.ret_cash.columns)
        for k in _pick(s, n, True):
            w[k] = 0.5 / n
        for k in _pick(s, n, False):
            w[k] = -0.5 / n
        rows[d] = w
    W = pd.DataFrame(rows).T
    blk = _result(ac, W, ibs.iloc[-1], "IBS", "{:.2f}", [
        f"Internal Bar Strength IBS = (Close − Low)/(High − Low) (Eq. 370). Each day buy the {n} sectors with the lowest IBS (closed near their low) and short the {n} with the highest, holding one day. "
        "Daily turnover is very high, so costs matter: compare 'Sharpe' with 'Sharpe (gross)'."])
    return entry("4.4", "Mean-reversion", CAT,
                 "Buy the sectors that closed near the bottom of yesterday's range and short those that closed near the top, expecting a snap-back.", blk)


# ------------------------------------------------------------------ 4.6 multi-asset

def s4_6(ctx: Ctx, md, T=126, Tma=150):
    ac = Assets(md, U.MULTI_ASSET, ctx, min_days=300)
    if ac.n < 3:
        return entry("4.6", "Multi-asset trend following", CAT, "Long-only trend following.", {"notes": ["Too few of the multi-asset tickers could be downloaded from Yahoo Finance."]})
    cum = ac.close / ac.close.shift(T) - 1
    vol = ac.ret.rolling(T).std()
    ma = ac.close.rolling(Tma).mean()
    dates = M.rebalance_dates(ac.dates, "M")
    rows = {}
    for d in dates:
        c = cum.loc[d]
        ok = c.notna() & vol.loc[d].notna() & (c > 0) & (ac.close.loc[d] > ma.loc[d])
        w = pd.Series(0.0, index=ac.ret_cash.columns)
        if ok.any():
            raw = c[ok] / vol.loc[d][ok] ** 2                      # Eq. 373
            w[raw.index] = raw / raw.sum()
        else:
            w[CASH] = 1.0
        if cum.loc[d].notna().sum() >= 2:
            rows[d] = w
    W = pd.DataFrame(rows).T
    blk = _result(ac, W, cum.iloc[-1], "6m return", "{:+.1%}", [
        f"Only assets with a positive {T}-day return AND price above their {Tma}-day moving average are held; weights ∝ Rᶜᵘᵐ/σ² (Eq. 373). If nothing qualifies, the portfolio sits in cash (earning {C.RISK_FREE:.1%}). Long-only, rebalanced monthly."],
        long_short=False)
    return entry("4.6", "Multi-asset trend following", CAT,
                 "A long-only portfolio of assets in an uptrend (equity indexes, gold, silver, Nasdaq-100) weighted by trend strength over variance; cash when nothing trends.", blk)


# ------------------------------------------------------------------------- driver

def run(ctx: Ctx, md):
    ac = Assets(md, U.SECTOR_INDICES, ctx)
    import logging
    logging.getLogger("pipeline").info("sector indices usable (%d/%d): %s", ac.n, len(U.SECTOR_INDICES), ", ".join(ac.cols))
    out = {}
    if ac.n < 6:
        msg = {"notes": [f"Only {ac.n} sector indices could be downloaded from Yahoo Finance – not enough to rank sectors."]}
        for sid, nm in (("4.1", "Sector momentum rotation"), ("4.1.1", "Sector momentum rotation with MA filter"),
                        ("4.1.2", "Dual-momentum sector rotation"), ("4.2", "Alpha rotation"), ("4.3", "R-squared"), ("4.4", "Mean-reversion")):
            out[sid] = entry(sid, nm, CAT, "Sector rotation strategy.", dict(msg))
    else:
        for fn, sid, nm in ((s4_1, "4.1", "Sector momentum rotation"), (s4_1_1, "4.1.1", "Sector momentum rotation with MA filter"),
                            (s4_1_2, "4.1.2", "Dual-momentum sector rotation"), (s4_2, "4.2", "Alpha rotation"),
                            (s4_3, "4.3", "R-squared"), (s4_4, "4.4", "Mean-reversion")):
            out[sid] = guarded(fn, sid, nm, CAT, ac)
    out["4.6"] = guarded(s4_6, "4.6", "Multi-asset trend following", CAT, ctx, md)
    return out
