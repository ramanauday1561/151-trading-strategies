"""Backtest engine, performance statistics and result-block helpers."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import config as C

TD = C.TRADING_DAYS


# ---------------------------------------------------------------- calendar helpers

def rebalance_dates(index: pd.DatetimeIndex, freq: str) -> pd.DatetimeIndex:
    """Last trading day of each period ('D' daily, 'W' weekly, 'M' monthly)."""
    if freq == "D":
        return index
    per = index.to_period("W" if freq == "W" else "M")
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby(per).last().values)


def month_starts(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """First trading day of each month."""
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby(index.to_period("M")).first().values)


# ------------------------------------------------------------------ backtest core

def run_weights(ret: pd.DataFrame, W: pd.DataFrame, cost_bps: float = C.COST_BPS):
    """Weights decided at the close of the dates in `W`'s index, held from the next day
    until the next rebalance.  Returns (net, gross, turnover) daily series, trimmed to the
    first date a position exists."""
    W = W.reindex(columns=ret.columns).fillna(0.0)
    full = pd.DataFrame(np.nan, index=ret.index, columns=ret.columns)
    common = W.index.intersection(ret.index)
    full.loc[common] = W.loc[common].values
    held = full.ffill().fillna(0.0)
    eff = held.shift(1).fillna(0.0)
    gross = (eff * ret.fillna(0.0)).sum(axis=1)
    turn = eff.diff().abs().sum(axis=1)
    turn.iloc[0] = eff.iloc[0].abs().sum()
    net = gross - turn * cost_bps / 1e4
    active = eff.abs().sum(axis=1) > 0
    if active.any():
        start = active.idxmax()
        net, gross, turn = net.loc[start:], gross.loc[start:], turn.loc[start:]
    return net, gross, turn


def run_positions(ret: pd.Series, pos: pd.Series, cost_bps: float = C.COST_BPS):
    """Single-asset: `pos` is the position decided at the close of t (held during t+1)."""
    eff = pos.shift(1).fillna(0.0)
    gross = eff * ret.fillna(0.0)
    turn = eff.diff().abs().fillna(eff.abs())
    net = gross - turn * cost_bps / 1e4
    active = eff.abs() > 0
    if active.any():
        start = active.idxmax()
        net, gross, turn = net.loc[start:], gross.loc[start:], turn.loc[start:]
    return net, gross, turn


# --------------------------------------------------------------------- statistics

def max_drawdown(eq: pd.Series) -> float:
    peak = eq.cummax()
    return float((eq / peak - 1.0).min()) if len(eq) else float("nan")


def perf(r: pd.Series, rf: float = 0.0) -> dict:
    r = r.dropna()
    if len(r) < 30:
        return {"n": int(len(r))}
    eq = (1 + r).cumprod()
    years = len(r) / TD
    cagr = eq.iloc[-1] ** (1 / years) - 1 if eq.iloc[-1] > 0 else -1.0
    vol = r.std() * math.sqrt(TD)
    sharpe = (r.mean() * TD - rf) / vol if vol > 0 else float("nan")
    dd = max_drawdown(eq)
    last = r.iloc[-TD:] if len(r) >= TD else r
    return {
        "n": int(len(r)),
        "start": str(r.index[0].date()),
        "cagr": _f(cagr),
        "vol": _f(vol),
        "sharpe": _f(sharpe),
        "max_dd": _f(dd),
        "calmar": _f(cagr / abs(dd)) if dd < 0 else None,
        "hit_rate": _f((r > 0).sum() / max(1, (r != 0).sum())),
        "ret_1y": _f((1 + last).prod() - 1),
        "total_return": _f(eq.iloc[-1] - 1),
    }


def perf_monthly(pnl: pd.Series, scale: float = 12.0) -> dict:
    """Stats for a per-cycle (monthly) additive P&L series expressed in % / vol-points."""
    p = pnl.dropna()
    if len(p) < 6:
        return {"n": int(len(p))}
    cum = p.cumsum()
    dd = (cum - cum.cummax()).min()
    sd = p.std()
    return {
        "n": int(len(p)),
        "start": str(p.index[0].date()),
        "avg": _f(p.mean()),
        "total": _f(cum.iloc[-1]),
        "sharpe": _f(p.mean() / sd * math.sqrt(scale)) if sd > 0 else None,
        "hit_rate": _f((p > 0).mean()),
        "worst": _f(p.min()),
        "best": _f(p.max()),
        "max_dd": _f(dd),
    }


def _f(x, nd=4):
    if x is None:
        return None
    try:
        x = float(x)
    except Exception:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return round(x, nd)


# ------------------------------------------------------------------ result blocks

def downsample(index: pd.DatetimeIndex, max_points: int = 520):
    n = len(index)
    if n <= max_points:
        return np.arange(n)
    step = math.ceil(n / max_points)
    pos = np.arange(0, n, step)
    if pos[-1] != n - 1:
        pos = np.append(pos, n - 1)
    return pos


def equity_curve(series: dict[str, pd.Series], base: float = 100.0, start=None, kind="ret") -> dict:
    """series: name -> daily returns (kind='ret') or cumulative additive pnl (kind='cum').
    All series are aligned on a common index starting at `start` (default: first series start)."""
    first = next(iter(series.values()))
    idx = first.index if start is None else first.index[first.index >= start]
    out = {"dates": [str(d.date()) for d in idx[downsample(idx)]]}
    pos = downsample(idx)
    for name, s in series.items():
        s = s.reindex(idx)
        if kind == "ret":
            eq = base * (1 + s.fillna(0.0)).cumprod()
        else:
            eq = base + s.ffill().fillna(0.0)
        out[name] = [round(float(v), 3) for v in eq.values[pos]]
    return out


def block(
    *,
    net: pd.Series | None = None,
    bench: pd.Series | None = None,
    extra_curves: dict[str, pd.Series] | None = None,
    gross: pd.Series | None = None,
    turnover: pd.Series | None = None,
    signal: dict | None = None,
    tables: list | None = None,
    notes: list | None = None,
    extra_metrics: dict | None = None,
    charts: list | None = None,
) -> dict:
    """Standard per-universe result block."""
    out: dict = {}
    if net is not None and len(net.dropna()) > 30:
        m = perf(net)
        if gross is not None:
            m["sharpe_gross"] = perf(gross).get("sharpe")
        if turnover is not None and len(turnover):
            m["turnover_ann"] = _f(turnover.mean() * TD)
        if bench is not None:
            b = bench.reindex(net.index)
            bp = perf(b)
            m["bench_cagr"] = bp.get("cagr")
            m["bench_sharpe"] = bp.get("sharpe")
            m["bench_max_dd"] = bp.get("max_dd")
            bn = b.fillna(0)
            if bn.std() > 0:
                m["beta"] = _f(np.cov(net.fillna(0), bn)[0, 1] / bn.var())
        out["metrics"] = m
        curves = {"strategy": net}
        if extra_curves:
            curves.update({k: v.reindex(net.index) for k, v in extra_curves.items()})
        if bench is not None:
            curves["benchmark"] = bench.reindex(net.index)
        out["curve"] = equity_curve(curves, start=net.index[0])
    if extra_metrics:
        out.setdefault("metrics", {}).update({k: v for k, v in extra_metrics.items()})
    if signal:
        out["signal"] = signal
    if tables:
        out["tables"] = tables
    if charts:
        out["charts"] = charts
    if notes:
        out["notes"] = notes
    return out


def table(title, columns, rows, fmt=None):
    return {"title": title, "columns": columns, "rows": rows, **({"fmt": fmt} if fmt else {})}


def signal(label, bias="neutral", detail=None):
    s = {"label": label, "bias": bias}
    if detail:
        s["detail"] = detail
    return s


def xs_signal(longs, shorts):
    lab = []
    if longs:
        lab.append("Long " + ", ".join(longs[:4]) + (f" +{len(longs) - 4}" if len(longs) > 4 else ""))
    if shorts:
        lab.append("Short " + ", ".join(shorts[:4]) + (f" +{len(shorts) - 4}" if len(shorts) > 4 else ""))
    bias = "mixed" if longs and shorts else ("long" if longs else "short" if shorts else "neutral")
    return signal(" | ".join(lab) if lab else "No position", bias)


def finite(x):
    return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else x
