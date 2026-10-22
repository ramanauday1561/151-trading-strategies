"""Per-universe context and helpers shared by the strategy modules."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from . import config as C
from . import metrics as M
from . import universe as U


log = logging.getLogger("pipeline")


def guarded(fn, sid, name, cat, *args, **kw):
    """Run one strategy; a failure becomes an error entry instead of aborting the whole run."""
    try:
        return fn(*args, **kw)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: isolate per-strategy failures
        log.exception("strategy %s (%s) failed", sid, name)
        return {"id": sid, "name": name, "category": cat, "status": "implemented",
                "desc": "This strategy could not be computed in the latest run.",
                "block": {"error": f"{type(exc).__name__}: {exc}",
                          "notes": ["The calculation failed for this universe in the latest run; the error is logged in the GitHub Actions output."]}}


class Ctx:
    """Everything a strategy needs about one universe (NIFTY 50 or SENSEX 30)."""

    def __init__(self, md, universe: str):
        self.md = md
        self.universe = universe
        self.idx_sym, self.idx_name = C.UNIVERSES[universe]
        keys = [k for k in U.MEMBERS[universe] if k in md.close.columns and md.close[k].notna().sum() > 300]
        self.keys = keys
        self.names = {k: U.STOCKS[k][0] for k in keys}
        self.sector = {k: U.STOCKS[k][2] for k in keys}
        self.close = md.close[keys]
        self.open = md.open[keys]
        self.high = md.high[keys]
        self.low = md.low[keys]
        self.volume = md.volume[keys]
        self.ret = self.close.pct_change(fill_method=None)
        self.logret = np.log(self.close).diff()
        self.index = md.close[self.idx_sym]
        self.index_ret = self.index.pct_change(fill_method=None)
        self.index_high = md.high[self.idx_sym]
        self.index_low = md.low[self.idx_sym]
        self.vix = md.close[C.VIX_TICKER] if C.VIX_TICKER in md.close else pd.Series(dtype=float)
        self.fund = md.fundamentals or {}
        self.dates = self.close.index
        # sector dummy matrix (N x K)
        secs = sorted(set(self.sector.values()))
        self.sector_names = secs
        self.omega_sector = pd.DataFrame(
            {s: [1.0 if self.sector[k] == s else 0.0 for k in keys] for s in secs}, index=keys
        )

    def fund_series(self, field):
        return pd.Series({k: self.fund.get(k, {}).get(field) for k in self.keys}, dtype=float)


def entry(sid, name, category, desc, block, status="implemented", extra=None):
    e = {"id": sid, "name": name, "category": category, "status": status, "desc": desc, "block": block}
    if extra:
        e.update(extra)
    return e


# -------------------------------------------------------------- cross-sectional

def xs_weights(score: pd.DataFrame, dates, frac: float = C.XS_FRACTION, long_short: bool = True,
               min_names: int = 8) -> pd.DataFrame:
    rows = {}
    for d in dates:
        if d not in score.index:
            continue
        s = score.loc[d].dropna()
        if len(s) < min_names:
            continue
        k = max(1, int(round(len(s) * frac)))
        order = s.sort_values(ascending=False)
        w = pd.Series(0.0, index=score.columns)
        if long_short:
            w[order.index[:k]] = 0.5 / k
            w[order.index[-k:]] = -0.5 / k
        else:
            w[order.index[:k]] = 1.0 / k
        rows[d] = w
    return pd.DataFrame(rows).T if rows else pd.DataFrame(columns=score.columns)


def position_table(ctx: Ctx, w: pd.Series, score: pd.Series | None = None, score_label="Score", fmt="{:.3f}"):
    w = w[w.abs() > 1e-12].sort_values(ascending=False)
    rows = []
    for k, v in w.items():
        sc = "" if score is None or pd.isna(score.get(k)) else fmt.format(score[k])
        rows.append(["Long" if v > 0 else "Short", ctx.names.get(k, k), U.sector_name(ctx.sector[k]) if k in ctx.sector else "",
                     sc, f"{v * 100:+.1f}%"])
    return M.table("Target portfolio now (rebalance at the latest close)",
                   ["Side", "Stock", "Sector", score_label, "Weight"], rows)


def xs_result(ctx: Ctx, score: pd.DataFrame, *, freq="M", frac=C.XS_FRACTION, notes=None,
              score_label="Score", fmt="{:.3f}", extra_tables=None, long_only_curve=True,
              min_names=8, cost_bps=C.COST_BPS, label_prefix=""):
    """Run a quantile long/short backtest for a score matrix and return a result block."""
    dates = M.rebalance_dates(score.index, freq)
    W_ls = xs_weights(score, dates, frac, True, min_names)
    if W_ls.empty:
        return {"notes": ["Not enough history/data to evaluate this strategy."]}
    W_lo = xs_weights(score, dates, frac, False, min_names)
    ret = ctx.ret.reindex(columns=score.columns)
    net, gross, turn = M.run_weights(ret, W_ls, cost_bps)
    lo_net, _, _ = M.run_weights(ret, W_lo, cost_bps)
    last = W_ls.iloc[-1]
    longs = [ctx.names[k] for k in last[last > 0].index]
    shorts = [ctx.names[k] for k in last[last < 0].index]
    tables = [position_table(ctx, last, score.loc[W_ls.index[-1]], score_label, fmt)]
    if extra_tables:
        tables += extra_tables
    blk = M.block(
        net=net, gross=gross, turnover=turn, bench=ctx.index_ret,
        extra_curves={"long_only": lo_net} if long_only_curve else None,
        signal=M.xs_signal(longs, shorts), tables=tables,
        notes=(notes or []) + [
            f"Dollar-neutral long/short on the top/bottom {int(frac * 100)}% of {int(score.loc[W_ls.index[-1]].notna().sum())} stocks, "
            f"rebalanced {'monthly' if freq == 'M' else 'weekly' if freq == 'W' else 'daily'}, {cost_bps:.0f} bps one-way cost. "
            "The dashed line is the index buy-and-hold; the 'long only' line holds just the long leg.",
            "Shorting single stocks in India is done through stock futures (F&O stocks) or intraday; borrow, margin and slippage are not modelled.",
        ],
        extra_metrics={f"long_only_{k}": v for k, v in M.perf(lo_net).items() if k in ("cagr", "sharpe", "max_dd")},
    )
    return blk


def demean_by_group(R: pd.Series, groups: pd.Series) -> pd.Series:
    return R - R.groupby(groups).transform("mean")


def norm_abs(w: pd.Series) -> pd.Series:
    s = w.abs().sum()
    return w / s if s > 0 else w


def ls_return_series(score: pd.DataFrame, ret: pd.DataFrame, lag: int = 1) -> pd.Series:
    """Daily-rebalanced 'alpha-style' long/short return: weights proportional to the demeaned score,
    scaled to unit gross exposure, applied with a one-day lag.  No costs (alpha series)."""
    dm = score.sub(score.mean(axis=1), axis=0)
    gross = dm.abs().sum(axis=1).replace(0, np.nan)
    w = dm.div(gross, axis=0).shift(lag)
    return (w * ret.fillna(0.0)).sum(axis=1, min_count=1)


# ------------------------------------------------------- weight-matrix strategies

def weights_result(ctx: Ctx, W: pd.DataFrame, *, notes=None, score_last: pd.Series | None = None,
                   score_label="Signal", fmt="{:.3f}", extra_tables=None, cost_bps=C.COST_BPS,
                   freq_label="weekly", bench=None, extra_metrics=None, charts=None):
    """Block for strategies that directly produce a weight matrix (rows = rebalance dates)."""
    if W is None or W.empty:
        return {"notes": ["Not enough history/data to evaluate this strategy."]}
    ret = ctx.ret.reindex(columns=W.columns)
    net, gross, turn = M.run_weights(ret, W, cost_bps)
    pos = W.clip(lower=0.0)
    s = pos.sum(axis=1).replace(0, np.nan)
    lo_net, _, _ = M.run_weights(ret, pos.div(s, axis=0).fillna(0.0), cost_bps)
    last = W.iloc[-1]
    ordered = last[last.abs() > 1e-9].sort_values(ascending=False)
    longs = [ctx.names.get(k, k) for k in ordered[ordered > 0].index]
    shorts = [ctx.names.get(k, k) for k in ordered[ordered < 0].index[::-1]]
    tables = [position_table(ctx, last, score_last, score_label, fmt)]
    if extra_tables:
        tables += extra_tables
    return M.block(
        net=net, gross=gross, turnover=turn, bench=ctx.index_ret if bench is None else bench,
        extra_curves={"long_only": lo_net}, signal=M.xs_signal(longs, shorts), tables=tables,
        notes=(notes or []) + [
            f"Rebalanced {freq_label} with {cost_bps:.0f} bps one-way cost; weights are scaled to unit gross exposure. "
            "'Sharpe (gross)' ignores costs. The dashed line is the index buy-and-hold; 'long only' holds only the positive weights.",
            "Shorting single stocks in India is done through stock futures (F&O stocks) or intraday; borrow, margin and slippage are not modelled.",
        ],
        extra_metrics=extra_metrics, charts=charts,
    )
