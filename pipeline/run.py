"""Run every strategy for NIFTY 50 and SENSEX and write the JSON the website reads.

    python -m pipeline.run --out site/data            # live Yahoo Finance data (what GitHub Actions does)
    python -m pipeline.run --out /tmp/x --synthetic   # offline test data (flagged in meta.json)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import math
import os
import sys
import time
import traceback
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import data as D
from . import universe as U
from . import registry as R
from . import options, stocks_xs, technical, ml, etfs, indexes, volatility, futures
from .common import Ctx

log = logging.getLogger("pipeline.run")

CATEGORIES = [
    ("options", "Options", "Ch. 2 – 58 option strategies priced on NIFTY / SENSEX"),
    ("stocks", "Stocks", "Ch. 3 – factor, mean-reversion, stat-arb and technical strategies on the constituents"),
    ("ml", "Machine learning", "Ch. 3.17 / 18.2 – KNN and neural-network forecasts"),
    ("etf", "ETFs & sectors", "Ch. 4 – sector rotation and multi-asset trend following"),
    ("indexes", "Indexes", "Ch. 6 – dispersion and volatility targeting"),
    ("volatility", "Volatility", "Ch. 7 – volatility risk premium and variance swaps on India VIX"),
    ("futures", "Futures & hedging", "Ch. 10 – hedging, contrarian and trend following"),
]


# ----------------------------------------------------------------------------- JSON

def sanitize(o):
    if isinstance(o, dict):
        return {str(k): sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [sanitize(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        v = float(o)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, dt.date)):
        return str(o)[:10]
    return o


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sanitize(obj), f, separators=(",", ":"), allow_nan=False, ensure_ascii=False)


# ------------------------------------------------------------------------- live data

def _ret(s: pd.Series, n):
    s = s.dropna()
    return float(s.iloc[-1] / s.iloc[-1 - n] - 1) if len(s) > n else None


def live_snapshot(md):
    out = {"indices": [], "stocks": []}
    for sym, nm in (("^NSEI", "NIFTY 50"), ("^BSESN", "SENSEX"), ("^INDIAVIX", "India VIX")):
        if sym not in md.close:
            continue
        s = md.close[sym].dropna()
        hi, lo = s.iloc[-252:].max(), s.iloc[-252:].min()
        row = {
            "symbol": sym, "name": nm, "last": float(s.iloc[-1]), "prev": float(s.iloc[-2]),
            "chg": float(s.iloc[-1] - s.iloc[-2]), "chg_pct": float(s.iloc[-1] / s.iloc[-2] - 1),
            "ret_1w": _ret(s, 5), "ret_1m": _ret(s, 21), "ret_6m": _ret(s, 126), "ret_1y": _ret(s, 252),
            "hi_52w": float(hi), "lo_52w": float(lo), "from_hi": float(s.iloc[-1] / hi - 1),
            "vs_dma50": float(s.iloc[-1] / s.rolling(50).mean().iloc[-1] - 1) if len(s) > 50 else None,
            "vs_dma200": float(s.iloc[-1] / s.rolling(200).mean().iloc[-1] - 1) if len(s) > 200 else None,
            "spark": [round(float(v), 2) for v in s.iloc[-90:].values],
            "intraday": md.intraday.get(sym),
            "quote_time": (md.intraday.get(sym) or {}).get("stamp", "")[-5:] or None,
        }
        if sym == "^INDIAVIX":
            row["pctile_1y"] = float((s.iloc[-252:] <= s.iloc[-1]).mean())
        out["indices"].append(row)
    seen = set()
    for uni in ("NIFTY50", "SENSEX30"):
        for k in U.MEMBERS[uni]:
            if k in seen or k not in md.close.columns:
                continue
            seen.add(k)
            s = md.close[k].dropna()
            if len(s) < 3:
                continue
            out["stocks"].append({
                "key": k, "symbol": md.symbol_used.get(k, k), "name": U.STOCKS[k][0], "sector": U.sector_name(U.STOCKS[k][2]),
                "last": float(s.iloc[-1]), "chg_pct": float(s.iloc[-1] / s.iloc[-2] - 1),
                "ret_1m": _ret(s, 21), "ret_6m": _ret(s, 126), "ret_1y": _ret(s, 252),
                "in_nifty": k in U.NIFTY50, "in_sensex": k in U.SENSEX30,
                "pb": (md.fundamentals.get(k) or {}).get("priceToBook"),
                "mcap": (md.fundamentals.get(k) or {}).get("marketCap"),
            })
    return out


# ------------------------------------------------------------------------- main run

MODULES = {
    "options": lambda ctx, md: options.run(md, ctx.universe),
    "stocks_xs": lambda ctx, md: stocks_xs.run(ctx),
    "technical": lambda ctx, md: technical.run(ctx),
    "ml": lambda ctx, md: ml.run(ctx),
    "etfs": lambda ctx, md: etfs.run(ctx, md),
    "indexes": lambda ctx, md: indexes.run(ctx),
    "volatility": lambda ctx, md: volatility.run(ctx),
    "futures": lambda ctx, md: futures.run(ctx),
}


def check_universe_coverage(md, min_share=0.9):
    problems = []
    for uni, members in U.MEMBERS.items():
        have = [k for k in members if k in md.close.columns and md.close[k].notna().sum() > 300]
        share = len(have) / len(members)
        log.info("%s: %d/%d constituents with usable history", uni, len(have), len(members))
        if share < min_share:
            problems.append(f"{uni}: only {len(have)}/{len(members)} constituents downloaded")
    for sym in ("^NSEI", "^BSESN", C.VIX_TICKER):
        if sym not in md.close.columns or md.close[sym].notna().sum() < 500:
            problems.append(f"{sym} missing")
    return problems


def run_all(md, only=None):
    strategies: dict[str, dict] = {}
    errors = []
    for uni in C.UNIVERSES:
        ctx = Ctx(md, uni)
        for name, fn in MODULES.items():
            if only and name not in only:
                continue
            t0 = time.time()
            try:
                res = fn(ctx, md)
            except Exception as exc:
                log.error("%s failed for %s: %r\n%s", name, uni, exc, traceback.format_exc())
                errors.append({"module": name, "universe": uni, "error": repr(exc)})
                continue
            log.info("%-10s %-9s %5.1fs  %d strategies", name, uni, time.time() - t0, len(res))
            for sid, e in res.items():
                st = strategies.setdefault(sid, {k: v for k, v in e.items() if k != "block"} | {"universes": {}})
                st["universes"][uni] = e["block"]
    return strategies, errors


CHAPTER_CATEGORY = {2: "options", 3: "stocks", 4: "etf", 6: "indexes", 7: "volatility", 10: "futures", 18: "ml"}


def fill_missing(strategies, errors):
    """If a whole module crashed, keep the site complete: add error placeholders for its strategies."""
    excl = {e["id"] for e in R.excluded_entries()}
    for sid, name in R.BOOK:
        if sid in strategies or sid in excl:
            continue
        cat = "ml" if sid == "3.17" else CHAPTER_CATEGORY.get(R.chapter_of(sid), "stocks")
        msg = "module crashed before this strategy was computed"
        strategies[sid] = {"id": sid, "name": name, "category": cat, "status": "implemented",
                           "desc": "This strategy could not be computed in the latest run.",
                           "universes": {u: {"error": msg, "notes": [msg]} for u in C.UNIVERSES}}
        errors.append({"module": sid, "universe": "all", "error": msg})


def collect_errors(strategies, errors):
    for sid, st in strategies.items():
        for uni, b in st["universes"].items():
            if b.get("error"):
                errors.append({"module": sid, "universe": uni, "error": b["error"]})


def build_registry(strategies):
    items = []
    by_id = {sid: R.CHAPTERS[R.chapter_of(sid)] for sid, _ in R.BOOK}
    for sid, name in R.BOOK:
        ch = R.chapter_of(sid)
        s = strategies.get(sid)
        if s:
            items.append({"id": sid, "name": name, "chapter": ch, "chapter_name": R.CHAPTERS[ch], "status": s["status"],
                          "category": s["category"], "note": s.get("adapted_note") or R.ADAPTED.get(sid)})
        else:
            ex = {e["id"]: e for e in R.excluded_entries()}.get(sid)
            items.append({"id": sid, "name": name, "chapter": ch, "chapter_name": R.CHAPTERS[ch], "status": "excluded",
                          "reason": ex["reason"] if ex else "Not applicable."})
    return items


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/data")
    ap.add_argument("--synthetic", action="store_true", help="offline test data (never deployed)")
    ap.add_argument("--only", default="", help="comma-separated module names (testing)")
    ap.add_argument("--no-fundamentals", action="store_true")
    ap.add_argument("--cache-dir", default=None, help="reuse slow-moving fundamentals across runs")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    warnings.simplefilter("ignore")                       # yfinance floods the log with pandas deprecation warnings
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    out = Path(args.out)
    only = {x for x in args.only.split(",") if x}

    t0 = time.time()
    md = D.synthetic_market() if args.synthetic else D.fetch_live(with_fundamentals=not args.no_fundamentals, cache_dir=args.cache_dir)
    if md.failures:
        msg = f"Yahoo returned no usable data for {len(md.failures)} symbols: {', '.join(md.failures)}"
        log.warning(msg)
        print(f"::warning title=Yahoo symbols failed::{msg}" if os.environ.get("GITHUB_ACTIONS") else msg)
    log.info("symbols resolved to other candidates: %s", md.symbol_used and {k: v for k, v in md.symbol_used.items() if v != U.STOCKS[k][1][0]})
    problems = check_universe_coverage(md)
    if problems and not args.synthetic:
        log.error("data coverage too low, refusing to publish: %s", problems)
        return 2
    log.info("data ready in %.0fs (asof %s%s)", time.time() - t0, md.asof, ", SYNTHETIC" if md.synthetic else "")

    strategies, errors = run_all(md, only or None)
    if not only:
        fill_missing(strategies, errors)
        n_impl, n_excl = R.check_coverage(set(strategies))    # raises if the book and the output disagree
    else:
        n_excl = len(R.excluded_entries())
    collect_errors(strategies, errors)
    empty = [f"{sid}/{u}" for sid, st in strategies.items() for u, b in st["universes"].items()
             if not b.get("error") and not (b.get("signal") or b.get("metrics") or b.get("curve"))]
    if empty:
        msg = f"{len(empty)} strategy results came back empty (not enough data): {', '.join(empty)}"
        log.warning(msg)
        print(f"::warning title=Empty strategy results::{msg}" if os.environ.get("GITHUB_ACTIONS") else msg)

    # category files
    for cat, label, blurb in CATEGORIES:
        items = sorted([s for s in strategies.values() if s["category"] == cat], key=lambda s: [int(p) for p in s["id"].split(".")])
        if only and not items:
            continue            # partial test run: never clobber a category file with an empty one
        write_json(out / f"{cat}.json", {"category": cat, "label": label, "strategies": items})
    registry = build_registry(strategies)
    write_json(out / "registry.json", {"items": registry, "chapters": {str(k): v for k, v in R.CHAPTERS.items()}})
    live = live_snapshot(md)
    write_json(out / "live.json", live)
    cats = [{"id": c, "label": l, "blurb": b, "count": sum(1 for s in strategies.values() if s["category"] == c)} for c, l, b in CATEGORIES]
    meta = {
        "generated_at": md.fetched_at, "data_asof": md.asof, "synthetic": md.synthetic,
        "universes": {u: {"index": n, "symbol": s, "constituents": sum(1 for k in U.MEMBERS[u] if k in md.close.columns and md.close[k].notna().sum() > 300)}
                      for u, (s, n) in C.UNIVERSES.items()},
        "counts": {"implemented": len(strategies), "excluded": n_excl, "book_sections": len(R.BOOK),
                   "adapted_or_proxy": sum(1 for s in strategies.values() if s["status"] != "implemented")},
        "categories": cats,
        "assumptions": {"risk_free": C.RISK_FREE, "dividend_yield": C.DIV_YIELD, "cost_bps": C.COST_BPS, "history_years": C.HISTORY_YEARS,
                        "option_horizon_days": C.OPT_HORIZON_DAYS, "xs_fraction": C.XS_FRACTION},
        "failed_tickers": md.failures, "errors": errors,
        "symbols_used": {k: v for k, v in md.symbol_used.items() if v != U.STOCKS[k][1][0]},
    }
    write_json(out / "meta.json", meta)
    log.info("wrote %d strategies (%d excluded) to %s in %.0fs; %d errors", len(strategies), n_excl, out, time.time() - t0, len(errors))
    in_actions = bool(os.environ.get("GITHUB_ACTIONS"))
    for e in errors:
        line = f"{e['module']} / {e['universe']}: {e['error']}"
        print(f"::warning title=Strategy failed::{line}" if in_actions else f"WARNING {line}")
    total_cells = max(1, len(strategies) * len(C.UNIVERSES))
    if len(errors) / total_cells > 0.25:
        log.error("more than 25%% of strategy results failed (%d/%d) - treating the run as failed", len(errors), total_cells)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
