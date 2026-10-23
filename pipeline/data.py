"""Market-data layer.

`fetch_live()` pulls everything from Yahoo Finance (yfinance).
`synthetic_market()` generates a statistically plausible fake market so the whole
pipeline can be exercised offline (tests / CI).  Synthetic output is always flagged
(`synthetic: true`) and is never produced by the deployment workflow.
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config as C
from . import universe as U

log = logging.getLogger("pipeline.data")

FIELDS = ["Close", "Open", "High", "Low", "Volume"]


@dataclass
class MarketData:
    close: pd.DataFrame
    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    volume: pd.DataFrame
    fundamentals: dict = field(default_factory=dict)       # stock key -> dict
    symbol_used: dict = field(default_factory=dict)        # stock key -> yahoo symbol
    failures: list = field(default_factory=list)
    intraday: dict = field(default_factory=dict)           # symbol -> {"t": [...], "c": [...]}
    synthetic: bool = False
    fetched_at: str = ""

    @property
    def asof(self) -> str:
        return str(self.close.index[-1].date())


# --------------------------------------------------------------------------- live

def _to_naive_dates(idx) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(idx)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()


def _download_chunk(symbols, years, retries=4):
    import yfinance as yf

    last_err = None
    for attempt in range(retries):
        try:
            df = yf.download(
                list(symbols), period=f"{years}y", interval="1d", auto_adjust=True,
                progress=False, threads=True, group_by="column",
            )
            if df is not None and not df.empty:
                return df
            last_err = "empty response"
        except Exception as exc:  # network / rate limit
            last_err = repr(exc)
        wait = 2 ** attempt * 2
        log.warning("download retry %d for %s... (%s) sleeping %ss", attempt + 1, list(symbols)[:3], last_err, wait)
        time.sleep(wait)
    log.error("giving up on chunk %s: %s", list(symbols), last_err)
    return None


def _split_fields(df: pd.DataFrame, symbols) -> dict[str, pd.DataFrame]:
    """Normalise yfinance output into {field: wide DataFrame(columns=symbols)}."""
    out = {}
    if isinstance(df.columns, pd.MultiIndex):
        lvl0 = list(df.columns.get_level_values(0))
        for f in FIELDS:
            out[f] = df[f] if f in lvl0 else pd.DataFrame(index=df.index)
    else:  # single ticker, flat columns
        for f in FIELDS:
            out[f] = df[[f]].rename(columns={f: symbols[0]}) if f in df.columns else pd.DataFrame(index=df.index)
    for f in out:
        out[f].index = _to_naive_dates(out[f].index)
        out[f] = out[f][~out[f].index.duplicated(keep="last")]
    return out


def _fetch_fundamentals(keys_symbols: dict[str, str]) -> dict:
    import yfinance as yf

    wanted = ["priceToBook", "trailingPE", "forwardPE", "marketCap", "dividendYield", "sector", "bookValue"]

    def one(item):
        key, sym = item
        for attempt in range(3):
            try:
                info = yf.Ticker(sym).get_info() or {}
                if info:
                    return key, {k: info.get(k) for k in wanted if info.get(k) is not None}
            except Exception as exc:
                log.debug("info failed %s: %r", sym, exc)
            time.sleep(1.5 * (attempt + 1))
        return key, {}

    with ThreadPoolExecutor(max_workers=4) as ex:
        return dict(ex.map(one, keys_symbols.items()))


def _fetch_intraday(symbols=("^NSEI", "^BSESN", "^INDIAVIX")) -> dict:
    import yfinance as yf

    out = {}
    for sym in symbols:
        try:
            d = yf.download(sym, period="1d", interval="5m", progress=False, auto_adjust=True)
            if d is None or d.empty:
                continue
            close = d["Close"].iloc[:, 0] if isinstance(d.columns, pd.MultiIndex) else d["Close"]
            close = close.dropna()
            out[sym] = {"t": [t.strftime("%H:%M") for t in close.index], "c": [round(float(v), 2) for v in close.values],
                        "stamp": close.index[-1].strftime("%Y-%m-%d %H:%M")}
        except Exception as exc:
            log.warning("intraday %s failed: %r", sym, exc)
    return out


def _cached_fundamentals(symbol_used: dict, cache_dir: str | None, max_age_h: float = 12.0) -> dict:
    """P/B and market cap move slowly: reuse them across the 5-minute refresh loop."""
    import json
    import os
    path = os.path.join(cache_dir, "fundamentals.json") if cache_dir else None
    if path and os.path.exists(path) and (time.time() - os.path.getmtime(path)) / 3600 < max_age_h:
        try:
            cached = json.load(open(path))
            if sum(1 for v in cached.values() if v) >= 0.7 * len(symbol_used):
                return cached
        except Exception:
            pass
    fresh = _fetch_fundamentals(symbol_used)
    if path and sum(1 for v in fresh.values() if v) >= 0.5 * len(symbol_used):
        os.makedirs(cache_dir, exist_ok=True)
        json.dump(fresh, open(path, "w"))
    return fresh


def fetch_live(years: int = C.HISTORY_YEARS, with_fundamentals: bool = True, cache_dir: str | None = None) -> MarketData:
    stock_syms, other_syms = U.all_symbol_groups()
    symbols = stock_syms + other_syms
    chunks = [symbols[i:i + 20] for i in range(0, len(symbols), 20)]
    parts = {f: [] for f in FIELDS}
    for ch in chunks:
        df = _download_chunk(ch, years)
        if df is None:
            continue
        fields = _split_fields(df, ch)
        for f in FIELDS:
            parts[f].append(fields[f])
    if not parts["Close"]:
        raise RuntimeError("Yahoo Finance returned no data at all")
    raw = {f: pd.concat(parts[f], axis=1) for f in FIELDS}
    raw = {f: d.loc[:, ~d.columns.duplicated()] for f, d in raw.items()}

    # master calendar = NIFTY 50 trading days
    if "^NSEI" not in raw["Close"].columns or raw["Close"]["^NSEI"].dropna().empty:
        raise RuntimeError("^NSEI (NIFTY 50) could not be downloaded")
    cal = raw["Close"]["^NSEI"].dropna().index
    raw = {f: d.reindex(cal) for f, d in raw.items()}

    failures, symbol_used = [], {}
    frames = {f: {} for f in FIELDS}
    # stocks: choose the freshest/longest candidate per key
    for key, (name, cands, _sec) in U.STOCKS.items():
        best, best_rank = None, None
        for c in cands:
            if c not in raw["Close"].columns:
                continue
            s = raw["Close"][c].dropna()
            if len(s) < 60:
                continue
            rank = (s.index[-1], len(s))
            if best_rank is None or rank > best_rank:
                best, best_rank = c, rank
        if best is None:
            failures.append(f"{key} ({'/'.join(cands)})")
            continue
        symbol_used[key] = best
        for f in FIELDS:
            frames[f][key] = raw[f][best]
    for sym in other_syms:
        if sym in raw["Close"].columns and raw["Close"][sym].notna().sum() >= 60:
            for f in FIELDS:
                frames[f][sym] = raw[f][sym]
        else:
            failures.append(sym)
    md = MarketData(
        close=pd.DataFrame(frames["Close"]), open=pd.DataFrame(frames["Open"]),
        high=pd.DataFrame(frames["High"]), low=pd.DataFrame(frames["Low"]),
        volume=pd.DataFrame(frames["Volume"]),
        symbol_used=symbol_used, failures=failures,
        fetched_at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    if with_fundamentals:
        try:
            md.fundamentals = _cached_fundamentals(symbol_used, cache_dir)
        except Exception as exc:
            log.warning("fundamentals failed: %r", exc)
    md.intraday = _fetch_intraday()
    log.info("loaded %d series, %d failures, asof %s", md.close.shape[1], len(failures), md.asof)
    return md


# ----------------------------------------------------------------------- synthetic

def synthetic_market(seed: int = 7, years: int = 12) -> MarketData:
    """Plausible fake market (factor model with stochastic vol).  TEST USE ONLY."""
    rng = np.random.default_rng(seed)
    n = years * 252
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)

    # market return with persistent stochastic volatility
    logv = np.zeros(n)
    for t in range(1, n):
        logv[t] = 0.985 * logv[t - 1] + 0.12 * rng.standard_normal()
    mkt_vol = 0.0085 * np.exp(0.5 * logv)
    mkt = 0.0004 + mkt_vol * rng.standard_normal(n)

    sectors = sorted({v[2] for v in U.STOCKS.values()})
    sec_ret = {s: 0.006 * rng.standard_normal(n) for s in sectors}
    # a little momentum + sector persistence so strategies have something to find
    for s in sectors:
        for t in range(1, n):
            sec_ret[s][t] += 0.04 * sec_ret[s][t - 1]

    rets, vol_scale = {}, {}
    for key, (_n, _c, sec) in U.STOCKS.items():
        beta = rng.uniform(0.6, 1.4)
        idio = rng.uniform(0.008, 0.017)
        drift = rng.normal(0.0003, 0.0002)
        r = drift + beta * mkt + sec_ret[sec] * rng.uniform(0.6, 1.4) + idio * rng.standard_normal(n)
        # idiosyncratic mean reversion (short horizon)
        r[1:] -= 0.04 * r[:-1]
        rets[key] = r
        vol_scale[key] = idio

    def px(r, start=None):
        start = start or rng.uniform(150, 5000)
        return start * np.exp(np.cumsum(r))

    close = {k: pd.Series(px(r), index=dates) for k, r in rets.items()}
    # shorter history for recent listings
    if "JIOFIN" in close:
        close["JIOFIN"].iloc[: n - 800] = np.nan
    if "TRENT" in close:
        close["TRENT"].iloc[: n - 2800 if n > 2800 else 0] = np.nan

    def basket(keys, extra=0.0035, start=10000):
        arr = np.mean([rets[k] for k in keys if k in rets], axis=0) + extra * rng.standard_normal(n)
        return pd.Series(px(arr, start), index=dates), arr

    nsei, nsei_r = basket(U.NIFTY50, 0.0012, 8000)
    bsesn, _ = basket(U.SENSEX30, 0.0012, 27000)
    close["^NSEI"], close["^BSESN"] = nsei, bsesn

    by_sec = {}
    for k, (_nm, _c, sec) in U.STOCKS.items():
        by_sec.setdefault(sec, []).append(k)
    sec_map = {
        "^NSEBANK": by_sec["FIN"][:6], "^CNXIT": by_sec["IT"], "^CNXAUTO": by_sec["AUTO"],
        "^CNXPHARMA": ["SUNPHARMA", "CIPLA", "DRREDDY"], "^CNXFMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "TATACONSUM"],
        "^CNXMETAL": by_sec["MAT"][:4], "^CNXENERGY": ["RELIANCE", "ONGC", "COALINDIA", "NTPC"],
        "^CNXREALTY": ["LT", "ADANIENT"], "^CNXINFRA": by_sec["IND"] + ["ULTRACEMCO"],
        "^CNXPSUBANK": ["SBIN", "COALINDIA"], "^CNXMEDIA": ["TITAN", "ETERNAL"],
    }
    for sym, keys in sec_map.items():
        close[sym], _ = basket(keys, 0.004, rng.uniform(3000, 40000))
    close["^NSMIDCP"], _ = basket(list(U.STOCKS)[::2], 0.003, 20000)
    gold = 0.0002 + 0.006 * rng.standard_normal(n) + 0.1 * mkt
    close["GOLDBEES.NS"] = pd.Series(px(gold, 30), index=dates)
    silver = 0.0002 + 0.011 * rng.standard_normal(n) + 0.3 * gold
    close["SILVERBEES.NS"] = pd.Series(px(silver, 70), index=dates)
    close["SILVERBEES.NS"].iloc[: n - 1200] = np.nan
    nas = 0.0006 + 0.011 * rng.standard_normal(n) + 0.2 * mkt
    close["MON100.NS"] = pd.Series(px(nas, 60), index=dates)

    # India VIX ~ EWMA realised vol of the index with noise and a risk premium
    ewv = pd.Series(nsei_r, index=dates).ewm(span=20).std().bfill() * np.sqrt(252) * 100
    vix = (ewv * 1.18 + 2.5 + 1.3 * rng.standard_normal(n)).clip(9, 85)
    close["^INDIAVIX"] = vix.rolling(3, min_periods=1).mean()

    close = pd.DataFrame(close)

    def make_ohlc(c: pd.DataFrame):
        gap = 0.003 * rng.standard_normal(c.shape)
        o = c.shift(1) * (1 + gap)
        o = o.fillna(c)
        hi_noise = np.abs(0.006 * rng.standard_normal(c.shape))
        lo_noise = np.abs(0.006 * rng.standard_normal(c.shape))
        h = pd.DataFrame(np.maximum(o.values, c.values) * (1 + hi_noise), index=c.index, columns=c.columns)
        l = pd.DataFrame(np.minimum(o.values, c.values) * (1 - lo_noise), index=c.index, columns=c.columns)
        return o, h, l

    o, h, l = make_ohlc(close)
    vol = pd.DataFrame(
        np.exp(14 + 0.8 * rng.standard_normal(close.shape)), index=close.index, columns=close.columns
    )
    for idx in ("^NSEI", "^BSESN", "^INDIAVIX"):
        vol[idx] = 0.0
    funda = {
        k: {
            "priceToBook": float(np.exp(rng.normal(1.3, 0.8))),
            "trailingPE": float(np.exp(rng.normal(3.1, 0.5))),
            "marketCap": float(np.exp(rng.normal(27.5, 0.9))),
            "sector": U.sector_name(U.STOCKS[k][2]),
        }
        for k in U.STOCKS
    }
    intraday = {}
    for sym, base in (("^NSEI", close["^NSEI"].iloc[-1]), ("^BSESN", close["^BSESN"].iloc[-1]), ("^INDIAVIX", close["^INDIAVIX"].iloc[-1])):
        steps = rng.standard_normal(75).cumsum() * base * 0.0006
        intraday[sym] = {
            "t": [f"{9 + (15 + 5 * i) // 60:02d}:{(15 + 5 * i) % 60:02d}" for i in range(75)],
            "c": [round(float(base + s), 2) for s in steps],
        }
    return MarketData(
        close=close, open=o, high=h, low=l, volume=vol, fundamentals=funda,
        symbol_used={k: U.STOCKS[k][1][0] for k in U.STOCKS}, failures=[], intraday=intraday,
        synthetic=True, fetched_at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
