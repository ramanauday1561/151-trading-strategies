"""Chapter 2 – all 58 option strategies on NIFTY 50 / SENSEX.

Yahoo Finance has no Indian index option chains, so options are priced theoretically:
Black-Scholes with continuous dividend yield, spot from Yahoo, and **India VIX as the flat
implied volatility** for every strike and expiry.  That is a model, not a quote – real
premiums include skew, bid/ask and liquidity effects.

Each strategy is a list of legs  (kind, qty, k, tenor)  where
  kind  : 'C' call, 'P' put, 'U' underlying (index future / ETF)
  qty   : signed quantity (+ long / - short)
  k     : strike offset from ATM in units of u (u = 1% of spot, rounded to the strike step)
  tenor : 'near' (30d) or 'far' (60d, calendar / diagonal long leg)
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm

from . import config as C
from . import metrics as M
from .common import guarded

# ------------------------------------------------------------------------ pricing


def _d1d2(S, K, T, sig, r, q):
    T = np.maximum(T, 1e-9)
    sd = sig * np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sig * sig) * T) / sd
    return d1, d1 - sd


def bs_price(kind, S, K, T, sig, r=C.RISK_FREE, q=C.DIV_YIELD):
    """Vectorised European option price. T<=0 gives intrinsic value."""
    S, K, T, sig = (np.asarray(x, dtype=float) for x in np.broadcast_arrays(S, K, T, sig))
    d1, d2 = _d1d2(S, K, T, sig, r, q)
    if kind == "C":
        v = S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        intr = np.maximum(S - K, 0.0)
    else:
        v = K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)
        intr = np.maximum(K - S, 0.0)
    return np.where(T <= 1e-9, intr, v)


def bs_greeks(kind, S, K, T, sig, r=C.RISK_FREE, q=C.DIV_YIELD):
    d1, d2 = _d1d2(S, K, T, sig, r, q)
    pdf = norm.pdf(d1)
    eqt, ert = math.exp(-q * T), math.exp(-r * T)
    gamma = eqt * pdf / (S * sig * math.sqrt(T))
    vega = S * eqt * pdf * math.sqrt(T) / 100.0           # per vol point
    if kind == "C":
        delta = eqt * norm.cdf(d1)
        theta = -S * eqt * pdf * sig / (2 * math.sqrt(T)) - r * K * ert * norm.cdf(d2) + q * S * eqt * norm.cdf(d1)
    else:
        delta = eqt * (norm.cdf(d1) - 1)
        theta = -S * eqt * pdf * sig / (2 * math.sqrt(T)) + r * K * ert * norm.cdf(-d2) - q * S * eqt * norm.cdf(-d1)
    return float(delta), float(gamma), float(vega), float(theta / 365.0)


# ------------------------------------------------------------------ strategy specs
# (id, name, outlook, style, vol, description, legs)
#   outlook: bullish | bearish | neutral
#   vol:     'long' (profits from big moves) | 'short' (profits from calm markets) | None (directional)
N, F = "near", "far"


def _L(kind, qty, k, tenor=N):
    return (kind, qty, k, tenor)


SPECS = [
    ("2.2", "Covered call", "neutral", "income", None,
     "Hold the index (via futures/ETF) and sell an OTM call. Earns premium in flat or mildly rising markets; upside is capped at the strike. Payoff equals a short put.",
     [_L("U", 1, 0), _L("C", -1, 1)]),
    ("2.3", "Covered put", "neutral", "income", None,
     "Short the index and sell an OTM put. Neutral-to-bearish income play; downside profit is capped at the put strike. Payoff equals a short call.",
     [_L("U", -1, 0), _L("P", -1, -1)]),
    ("2.4", "Protective put", "bullish", "hedging", None,
     "Hold the index and buy an OTM put as insurance against a fall. Upside unlimited; loss limited to the distance to the strike plus the premium.",
     [_L("U", 1, 0), _L("P", 1, -1)]),
    ("2.5", "Protective call", "bearish", "hedging", None,
     "Short the index and buy an OTM call to cap the loss if the market rallies. Synthetic long put.",
     [_L("U", -1, 0), _L("C", 1, 1)]),
    ("2.6", "Bull call spread", "bullish", "capital gain", None,
     "Buy a near-ATM call and sell a higher-strike call. Net-debit bullish bet with capped profit and capped loss.",
     [_L("C", 1, 0), _L("C", -1, 2)]),
    ("2.7", "Bull put spread", "bullish", "income", None,
     "Buy a far-OTM put and sell a closer-to-the-money put. Net-credit bullish income strategy; credit is the maximum profit.",
     [_L("P", 1, -3), _L("P", -1, -1)]),
    ("2.8", "Bear call spread", "bearish", "income", None,
     "Sell a lower-strike call and buy a higher-strike call. Net-credit bearish income strategy.",
     [_L("C", 1, 3), _L("C", -1, 1)]),
    ("2.9", "Bear put spread", "bearish", "capital gain", None,
     "Buy a near-ATM put and sell a lower-strike put. Net-debit bearish bet with capped profit and loss.",
     [_L("P", 1, 0), _L("P", -1, -2)]),
    ("2.10", "Long synthetic forward", "bullish", "capital gain", None,
     "Buy an ATM call and sell an ATM put: replicates a long forward / futures position at strike K.",
     [_L("C", 1, 0), _L("P", -1, 0)]),
    ("2.11", "Short synthetic forward", "bearish", "capital gain", None,
     "Buy an ATM put and sell an ATM call: replicates a short forward / futures position.",
     [_L("P", 1, 0), _L("C", -1, 0)]),
    ("2.12", "Long combo", "bullish", "capital gain", None,
     "Long risk reversal: buy an OTM call, sell an OTM put (often near zero cost). Bullish, with unlimited upside and large downside.",
     [_L("C", 1, 1), _L("P", -1, -1)]),
    ("2.13", "Short combo", "bearish", "capital gain", None,
     "Short risk reversal: buy an OTM put, sell an OTM call. Bearish with large upside risk.",
     [_L("P", 1, -1), _L("C", -1, 1)]),
    ("2.14", "Bull call ladder", "bullish", "income", None,
     "Bull call spread financed by selling a further OTM call. Conservatively bullish; loses if the index rallies far past the top strike.",
     [_L("C", 1, 0), _L("C", -1, 1), _L("C", -1, 2)]),
    ("2.15", "Bull put ladder", "bearish", "income", None,
     "Short a near-ATM put, long two lower-strike puts. Arises when a bull put spread goes wrong; profits from a sharp fall.",
     [_L("P", -1, 0), _L("P", 1, -1), _L("P", 1, -2)]),
    ("2.16", "Bear call ladder", "bullish", "income", None,
     "Short a near-ATM call, long two higher-strike calls. Arises when a bear call spread goes wrong; profits from a sharp rally.",
     [_L("C", -1, 0), _L("C", 1, 1), _L("C", 1, 2)]),
    ("2.17", "Bear put ladder", "bearish", "income", None,
     "Bear put spread financed by selling another lower-strike put. Conservatively bearish; loses on a crash below the lowest strike.",
     [_L("P", 1, 0), _L("P", -1, -1), _L("P", -1, -2)]),
    ("2.18", "Calendar call spread", "neutral", "capital gain", None,
     "Sell a near-term ATM call and buy a longer-dated call at the same strike. Benefits from faster time decay of the short leg; best if the index pins the strike.",
     [_L("C", 1, 0, F), _L("C", -1, 0, N)]),
    ("2.19", "Calendar put spread", "neutral", "capital gain", None,
     "Sell a near-term ATM put and buy a longer-dated put at the same strike. Neutral-to-bearish time-decay play.",
     [_L("P", 1, 0, F), _L("P", -1, 0, N)]),
    ("2.20", "Diagonal call spread", "bullish", "capital gain", None,
     "Buy a deep-ITM long-dated call and sell a near-term OTM call. Mimics owning the index while collecting premium.",
     [_L("C", 1, -2, F), _L("C", -1, 1, N)]),
    ("2.21", "Diagonal put spread", "bearish", "capital gain", None,
     "Buy a deep-ITM long-dated put and sell a near-term OTM put. Mimics a short index position while collecting premium.",
     [_L("P", 1, 2, F), _L("P", -1, -1, N)]),
    ("2.22", "Long straddle", "neutral", "capital gain", "long",
     "Buy an ATM call and an ATM put. Profits from a large move in either direction; loses the premium if the index stays flat.",
     [_L("C", 1, 0), _L("P", 1, 0)]),
    ("2.23", "Long strangle", "neutral", "capital gain", "long",
     "Buy an OTM call and an OTM put. Cheaper than a straddle but needs a bigger move to profit.",
     [_L("C", 1, 1), _L("P", 1, -1)]),
    ("2.24", "Long guts", "neutral", "capital gain", "long",
     "Buy an ITM call and an ITM put. A costlier straddle variant with a smaller maximum loss.",
     [_L("C", 1, -1), _L("P", 1, 1)]),
    ("2.25", "Short straddle", "neutral", "income", "short",
     "Sell an ATM call and an ATM put. Collects the maximum premium if the index stays flat; unlimited risk on a big move.",
     [_L("C", -1, 0), _L("P", -1, 0)]),
    ("2.26", "Short strangle", "neutral", "income", "short",
     "Sell an OTM call and an OTM put. Lower credit than a straddle but a wider profit zone.",
     [_L("C", -1, 1), _L("P", -1, -1)]),
    ("2.27", "Short guts", "neutral", "income", "short",
     "Sell an ITM call and an ITM put. Larger credit than a short straddle, with correspondingly higher risk.",
     [_L("C", -1, -1), _L("P", -1, 1)]),
    ("2.28", "Long call synthetic straddle", "neutral", "capital gain", "long",
     "Short the index and buy two ATM calls (a straddle whose put is replaced by a synthetic put).",
     [_L("U", -1, 0), _L("C", 2, 0)]),
    ("2.29", "Long put synthetic straddle", "neutral", "capital gain", "long",
     "Buy the index and buy two ATM puts (a straddle whose call is replaced by a synthetic call).",
     [_L("U", 1, 0), _L("P", 2, 0)]),
    ("2.30", "Short call synthetic straddle", "neutral", "capital gain", "short",
     "Buy the index and sell two ATM calls (short straddle with the put replaced by a synthetic put).",
     [_L("U", 1, 0), _L("C", -2, 0)]),
    ("2.31", "Short put synthetic straddle", "neutral", "capital gain", "short",
     "Short the index and sell two ATM puts (short straddle with the call replaced by a synthetic call).",
     [_L("U", -1, 0), _L("P", -2, 0)]),
    ("2.32", "Covered short straddle", "bullish", "income", "short",
     "Covered call plus a short put at the same strike: more income, more downside risk. Bullish.",
     [_L("U", 1, 0), _L("C", -1, 0), _L("P", -1, 0)]),
    ("2.33", "Covered short strangle", "bullish", "income", "short",
     "Covered call plus a short OTM put. Extra income with a lower put strike than the covered short straddle.",
     [_L("U", 1, 0), _L("C", -1, 1), _L("P", -1, -1)]),
    ("2.34", "Strap", "bullish", "capital gain", "long",
     "Buy two ATM calls and one ATM put. A straddle with a bullish tilt.",
     [_L("C", 2, 0), _L("P", 1, 0)]),
    ("2.35", "Strip", "bearish", "capital gain", "long",
     "Buy one ATM call and two ATM puts. A straddle with a bearish tilt.",
     [_L("C", 1, 0), _L("P", 2, 0)]),
    ("2.36", "Call ratio backspread", "bullish", "capital gain", "long",
     "Sell one near-ATM call and buy two OTM calls. Strongly bullish; the worst case is a modest rally to the long strike.",
     [_L("C", -1, 0), _L("C", 2, 2)]),
    ("2.37", "Put ratio backspread", "bearish", "capital gain", "long",
     "Sell one near-ATM put and buy two OTM puts. Strongly bearish; the worst case is a modest fall to the long strike.",
     [_L("P", -1, 0), _L("P", 2, -2)]),
    ("2.38", "Ratio call spread", "bearish", "income", None,
     "Buy one ITM call and sell two near-ATM calls (ideally for a net credit). Neutral-to-bearish; unlimited risk on a rally.",
     [_L("C", 1, -1), _L("C", -2, 1)]),
    ("2.39", "Ratio put spread", "bullish", "income", None,
     "Buy one ITM put and sell two near-ATM puts (ideally for a net credit). Neutral-to-bullish; large risk on a crash.",
     [_L("P", 1, 1), _L("P", -2, -1)]),
    ("2.40", "Long call butterfly", "neutral", "capital gain", "short",
     "Buy an ITM call, sell two ATM calls, buy an OTM call (equidistant strikes). Low-cost bet that the index pins the middle strike.",
     [_L("C", 1, -2), _L("C", -2, 0), _L("C", 1, 2)]),
    ("2.40.1", "Modified call butterfly", "neutral", "capital gain", "short",
     "Call butterfly with unequal wings (upper wing narrower). Sideways strategy with a bullish bias.",
     [_L("C", 1, -3), _L("C", -2, 0), _L("C", 1, 1)]),
    ("2.41", "Long put butterfly", "neutral", "capital gain", "short",
     "Buy an OTM put, sell two ATM puts, buy an ITM put (equidistant strikes). Low-cost bet on a pinned index.",
     [_L("P", 1, -2), _L("P", -2, 0), _L("P", 1, 2)]),
    ("2.41.1", "Modified put butterfly", "neutral", "capital gain", "short",
     "Put butterfly with unequal wings (ITM wing narrower). Sideways strategy with a bullish bias.",
     [_L("P", 1, -3), _L("P", -2, 0), _L("P", 1, 1)]),
    ("2.42", "Short call butterfly", "neutral", "capital gain", "long",
     "Sell an ITM call, buy two ATM calls, sell an OTM call. Net credit; profits if the index moves away from the middle strike.",
     [_L("C", -1, -2), _L("C", 2, 0), _L("C", -1, 2)]),
    ("2.43", "Short put butterfly", "neutral", "capital gain", "long",
     "Sell an ITM put, buy two ATM puts, sell an OTM put. Net credit; profits from a move away from the middle strike.",
     [_L("P", -1, 2), _L("P", 2, 0), _L("P", -1, -2)]),
    ("2.44", "“Long” iron butterfly", "neutral", "income", "short",
     "Bull put spread plus bear call spread sharing the ATM strike: sell an ATM straddle, buy OTM wings. Net credit, defined risk.",
     [_L("P", 1, -2), _L("P", -1, 0), _L("C", -1, 0), _L("C", 1, 2)]),
    ("2.45", "“Short” iron butterfly", "neutral", "capital gain", "long",
     "Buy an ATM straddle and sell OTM wings. Net debit; profits from a decent move in either direction with defined risk.",
     [_L("P", -1, -2), _L("P", 1, 0), _L("C", 1, 0), _L("C", -1, 2)]),
    ("2.46", "Long call condor", "neutral", "capital gain", "short",
     "Buy ITM call, sell ITM call, sell OTM call, buy OTM call (equal spacing). Low-cost bet on a range.",
     [_L("C", 1, -3), _L("C", -1, -1), _L("C", -1, 1), _L("C", 1, 3)]),
    ("2.47", "Long put condor", "neutral", "capital gain", "short",
     "Buy OTM put, sell OTM put, sell ITM put, buy ITM put (equal spacing). Low-cost bet on a range.",
     [_L("P", 1, -3), _L("P", -1, -1), _L("P", -1, 1), _L("P", 1, 3)]),
    ("2.48", "Short call condor", "neutral", "capital gain", "long",
     "Mirror of the long call condor: small credit, profits if the index leaves the range.",
     [_L("C", -1, -3), _L("C", 1, -1), _L("C", 1, 1), _L("C", -1, 3)]),
    ("2.49", "Short put condor", "neutral", "capital gain", "long",
     "Mirror of the long put condor: small credit, profits if the index leaves the range.",
     [_L("P", -1, -3), _L("P", 1, -1), _L("P", 1, 1), _L("P", -1, 3)]),
    ("2.50", "Long iron condor", "neutral", "income", "short",
     "Bull put spread plus bear call spread: sell an OTM strangle, buy further-OTM wings. Net credit, defined risk, profits in a range.",
     [_L("P", 1, -3), _L("P", -1, -1), _L("C", -1, 1), _L("C", 1, 3)]),
    ("2.51", "Short iron condor", "neutral", "capital gain", "long",
     "Buy an OTM strangle, sell further-OTM wings. Net debit; profits if the index breaks out of the range.",
     [_L("P", -1, -3), _L("P", 1, -1), _L("C", 1, 1), _L("C", -1, 3)]),
    ("2.52", "Long box", "neutral", "capital gain", None,
     "Bull call spread plus bear put spread on the same strikes: a risk-free payoff of K₂−K₁ at expiry. Profits only if the box is bought below its present value (arbitrage).",
     [_L("C", 1, -1), _L("C", -1, 1), _L("P", 1, 1), _L("P", -1, -1)]),
    ("2.53", "Collar", "bullish", "capital gain", None,
     "Hold the index, buy an OTM put and sell an OTM call. Cheap protection in exchange for capped upside. Moderately bullish.",
     [_L("U", 1, 0), _L("P", 1, -1), _L("C", -1, 1)]),
    ("2.54", "Bullish short seagull spread", "bullish", "capital gain", None,
     "Bull call spread financed by selling an OTM put. Ideally zero cost; bullish with downside risk.",
     [_L("P", -1, -1), _L("C", 1, 0), _L("C", -1, 2)]),
    ("2.55", "Bearish long seagull spread", "bearish", "capital gain", None,
     "Short combo hedged against a rally by buying a further-OTM call. Ideally zero cost; bearish.",
     [_L("P", 1, -1), _L("C", -1, 0), _L("C", 1, 2)]),
    ("2.56", "Bearish short seagull spread", "bearish", "capital gain", None,
     "Bear put spread financed by selling an OTM call. Ideally zero cost; bearish with upside risk.",
     [_L("P", -1, -2), _L("P", 1, 0), _L("C", -1, 2)]),
    ("2.57", "Bullish long seagull spread", "bullish", "capital gain", None,
     "Long combo hedged against a fall by buying a further-OTM put. Ideally zero cost; bullish.",
     [_L("P", 1, -2), _L("P", -1, 0), _L("C", 1, 2)]),
]

OPTION_IDS = [s[0] for s in SPECS]


# ----------------------------------------------------------------------- analytics

def _strikes(S, step):
    atm = np.round(np.asarray(S, dtype=float) / step) * step
    u = np.maximum(step, np.round(np.asarray(S, dtype=float) * C.OPT_UNIT_PCT / step) * step)
    return atm, u


def _leg_value(kind, K, tenor_left, ST, sig):
    """Value of an option leg (array over ST) when `tenor_left` years remain."""
    return bs_price(kind, ST, K, tenor_left, sig)


def _pnl(legs, S0, sig, step, ST, T_near, T_far):
    """P&L at the near expiry for terminal prices ST (broadcast over S0/sig arrays or a grid)."""
    atm, u = _strikes(S0, step)
    total = 0.0
    prem_net = 0.0
    for kind, qty, k, tenor in legs:
        if kind == "U":
            total = total + qty * (ST - S0)
            continue
        K = atm + k * u
        T0 = T_near if tenor == N else T_far
        p0 = bs_price(kind, S0, K, T0, sig)
        v = _leg_value(kind, K, T0 - T_near, ST, sig)
        total = total + qty * (v - p0)
        prem_net = prem_net + qty * p0
    return total, prem_net


def analyze(legs, S, sig, step):
    """Live analytics for one strategy at spot S and implied vol sig (decimal)."""
    T1, T2 = C.OPT_HORIZON_DAYS / 365.0, C.OPT_FAR_DAYS / 365.0
    atm, u = _strikes(S, step)
    atm, u = float(atm), float(u)
    leg_rows, delta, gamma, vega, theta = [], 0.0, 0.0, 0.0, 0.0
    net_prem = 0.0
    for kind, qty, k, tenor in legs:
        if kind == "U":
            leg_rows.append(["Underlying", f"{qty:+d}", "Index future / ETF", f"{S:,.0f}", "–", f"{S:,.0f}", "–"])
            delta += qty
            continue
        K = atm + k * u
        T0 = T1 if tenor == N else T2
        p = float(bs_price(kind, S, K, T0, sig))
        g = bs_greeks(kind, S, K, T0, sig)
        delta += qty * g[0]; gamma += qty * g[1]; vega += qty * g[2]; theta += qty * g[3]
        net_prem += qty * p
        mny = (K / S - 1) * 100
        leg_rows.append([
            f"{'Call' if kind == 'C' else 'Put'}", f"{qty:+d}", f"{K:,.0f}",
            f"{T0 * 365:.0f}d", f"{mny:+.1f}%", f"{p:,.1f}", f"{g[0]:+.2f}",
        ])
    # dense grid for statistics
    strikes = [atm + k * u for kind, _q, k, _t in legs if kind != "U"]
    grid = np.unique(np.concatenate([np.linspace(1e-6 * S, 4.0 * S, 4001), strikes, [S]]))
    pnl, _ = _pnl(legs, S, sig, step, grid, T1, T2)
    pnl = np.asarray(pnl, dtype=float)
    right_slope = pnl[-1] - pnl[-400]
    unl_profit = right_slope > 1e-6 * S
    unl_loss = right_slope < -1e-6 * S
    max_profit = None if unl_profit else float(pnl.max())
    max_loss = None if unl_loss else float(max(0.0, -pnl.min()))
    riskless = bool(pnl.min() > 1e-6 * S)
    sgn = np.sign(pnl)
    idx = np.where(sgn[:-1] * sgn[1:] < 0)[0]
    bes = [float(grid[i] - pnl[i] * (grid[i + 1] - grid[i]) / (pnl[i + 1] - pnl[i])) for i in idx]
    # risk-neutral probability of profit (lognormal)
    mu = (C.RISK_FREE - C.DIV_YIELD - 0.5 * sig * sig) * T1
    sd = sig * math.sqrt(T1)
    z = (np.log(np.maximum(grid, 1e-9) / S) - mu) / sd
    w = np.diff(norm.cdf(z), prepend=0.0)
    pop = float(w[pnl > 0].sum())
    ev = float((w * pnl).sum())
    # chart curves on +-18% window
    cx = np.linspace(0.82 * S, 1.18 * S, 121)
    exp_c, _ = _pnl(legs, S, sig, step, cx, T1, T2)
    # mark-to-model halfway through the life (all legs repriced at ST with half the time left)
    half = T1 / 2
    atm_, u_ = _strikes(S, step)
    mid = 0.0
    for kind, qty, k, tenor in legs:
        if kind == "U":
            mid = mid + qty * (cx - S)
            continue
        K = atm_ + k * u_
        T0 = T1 if tenor == N else T2
        p0 = bs_price(kind, S, K, T0, sig)
        mid = mid + qty * (bs_price(kind, cx, K, T0 - half, sig) - p0)
    payoff = {
        "x": [round(float(v), 1) for v in cx],
        "expiry": [round(float(v), 2) for v in np.asarray(exp_c)],
        "mid": [round(float(v), 2) for v in np.asarray(mid)],
        "spot": round(float(S), 2),
        "breakevens": [round(b, 1) for b in bes if 0.5 * S < b < 1.8 * S],
    }
    return {
        "payoff": payoff,
        "legs": leg_rows,
        "stats": {
            "net_premium": round(net_prem, 2),               # + debit / - credit (options only)
            "net_premium_pct": round(net_prem / S * 100, 3),
            "max_profit": None if max_profit is None else round(max_profit, 2),
            "max_loss": None if max_loss is None else round(max_loss, 2),
            "breakevens": [round(b, 1) for b in bes if 0.3 * S < b < 2.5 * S],
            "pop": round(pop, 4),
            "riskless": riskless,
            "ev": round(ev, 2),
            "delta": round(delta, 3), "gamma": round(gamma * S * 0.01, 3),   # delta change per 1% move
            "vega": round(vega, 2), "theta": round(theta, 2),
        },
        "atm": atm, "unit": u,
    }


# ----------------------------------------------------------------------- backtest

def backtest(legs, close: pd.Series, vix: pd.Series, step):
    """Monthly roll: enter on the first trading day of each month, hold to the next
    month's first trading day.  IV = India VIX at entry (flat).  Returns pnl in % of spot."""
    starts = M.month_starts(close.index)
    d0 = starts[:-1]
    d1 = starts[1:]
    S0 = close.reindex(d0).values
    ST = close.reindex(d1).values
    sig = vix.reindex(d0).values / 100.0
    ok = ~(np.isnan(S0) | np.isnan(ST) | np.isnan(sig))
    d0, d1, S0, ST, sig = d0[ok], d1[ok], S0[ok], ST[ok], sig[ok]
    T1 = np.array([(b - a).days for a, b in zip(d0, d1)], dtype=float) / 365.0
    T2 = T1 + 30.0 / 365.0
    pnl, _ = _pnl(legs, S0, sig, step, ST, T1, T2)
    pct = pd.Series(np.asarray(pnl) / S0 * 100.0, index=pd.DatetimeIndex(d1))
    ret = pd.Series(ST / S0 - 1.0, index=pd.DatetimeIndex(d1)) * 100.0
    return pct, ret


# ---------------------------------------------------------------- regime heuristic

def regime(close: pd.Series, vix: pd.Series):
    v = vix.dropna()
    window = v.iloc[-252:]
    ivr = float((window <= v.iloc[-1]).mean() * 100)
    px = close.dropna()
    ma50, ma200 = px.rolling(50).mean().iloc[-1], px.rolling(200).mean().iloc[-1]
    last = px.iloc[-1]
    if last > ma50 > ma200:
        trend = "bull"
    elif last < ma50 < ma200:
        trend = "bear"
    else:
        trend = "mixed"
    return {"iv_rank": round(ivr, 1), "trend": trend, "vix": round(float(v.iloc[-1]), 2),
            "ma50": float(ma50), "ma200": float(ma200)}


def fit(outlook, vol, reg):
    ivr, trend = reg["iv_rank"], reg["trend"]
    if vol == "short":
        f = "favourable" if ivr >= 60 else "unfavourable" if ivr <= 30 else "neutral"
        why = f"India VIX is at the {ivr:.0f}th percentile of its 1-year range; premium-selling pays better when implied vol is rich."
    elif vol == "long":
        f = "favourable" if ivr <= 30 else "unfavourable" if ivr >= 60 else "neutral"
        why = f"India VIX is at the {ivr:.0f}th percentile of its 1-year range; buying volatility is cheaper when implied vol is low."
    elif outlook == "bullish":
        f = "favourable" if trend == "bull" else "unfavourable" if trend == "bear" else "neutral"
        why = f"Index trend is {trend} (price vs 50/200-day averages)."
    elif outlook == "bearish":
        f = "favourable" if trend == "bear" else "unfavourable" if trend == "bull" else "neutral"
        why = f"Index trend is {trend} (price vs 50/200-day averages)."
    else:
        f = "neutral"
        why = "No volatility or trend edge flagged by the regime heuristic."
    return f, why


# ----------------------------------------------------------------------- driver

def run(md, universe: str):
    idx_sym, idx_name = C.UNIVERSES[universe]
    close = md.close[idx_sym].dropna()
    vix = md.close[C.VIX_TICKER].dropna()
    step = C.OPT_STRIKE_STEP[universe]
    S = float(close.iloc[-1])
    sig = float(vix.iloc[-1]) / 100.0
    reg = regime(close, vix)
    out = {}
    for spec in SPECS:
        out[spec[0]] = guarded(_one, spec[0], spec[1], "options", spec, S, sig, step, close, vix, reg)
    return out


def _one(spec, S, sig, step, close, vix, reg):
    sid, name, outlook, style, vol, desc, legs = spec
    a = analyze(legs, S, sig, step)
    pct, ret = backtest(legs, close, vix, step)
    m = M.perf_monthly(pct)
    f_label, why = fit(outlook, vol, reg)
    cum = pct.cumsum()
    curve = M.equity_curve({"strategy": cum, "benchmark": ret.cumsum()}, base=0.0, kind="cum") if len(cum) > 6 else None
    bias = {"bullish": "long", "bearish": "short"}.get(outlook, "neutral")
    st = a["stats"]
    notes = [
        f"Theoretical Black-Scholes prices: spot {S:,.0f}, flat IV = India VIX {sig * 100:.1f}%, r = {C.RISK_FREE:.1%}, q = {C.DIV_YIELD:.1%}, "
        f"{C.OPT_HORIZON_DAYS}-day expiry, strikes in steps of {step:.0f} (offset unit u ≈ 1% of spot = {a['unit']:,.0f}).",
        "Backtest: rolled monthly since India VIX history begins, IV = VIX at entry for every strike (no skew, no bid/ask, no costs). "
        "P&L is in % of the index level; the benchmark line is the index's own monthly % move.",
    ]
    if sid == "2.52":
        notes.append("A box is a lending/borrowing trade: its payoff is fixed at K₂ − K₁, so the 'profit' above is just the interest implied by the price paid. "
                     "It only makes money if the box is mispriced. Sharpe and hit rate are not meaningful here.")
    return {
        "id": sid, "name": name, "category": "options", "status": "implemented",
        "outlook": outlook, "style": style, "vol_view": vol, "desc": desc,
        "block": {
            "signal": M.signal(f"{outlook.capitalize()} setup · {'no edge' if f_label == 'neutral' else f_label} now", bias, why),
            "metrics": {**m, "pop": st["pop"], "net_premium_pct": st["net_premium_pct"],
                        "max_loss_pct": None if st["max_loss"] is None else round(st["max_loss"] / S * 100, 2),
                        "max_profit_pct": None if st["max_profit"] is None else round(st["max_profit"] / S * 100, 2)},
            "curve": curve,
            "curve_units": "cumulative % of index level",
            "payoff": a["payoff"],
            "stats": st,
            "fit": {"label": f_label, "why": why, **{k: reg[k] for k in ("iv_rank", "trend", "vix")}},
            "tables": [M.table("Legs (priced now)", ["Type", "Qty", "Strike", "Expiry", "Moneyness", "Premium", "Delta"], a["legs"])],
            "notes": notes,
        },
    }
