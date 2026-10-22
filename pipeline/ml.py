"""Machine-learning strategies: single-stock KNN (3.17) and ANN (18.2, adapted from crypto)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import config as C
from . import metrics as M
from .common import Ctx, entry, guarded

# ======================================================================= KNN (3.17)

KNN_T = 5          # prediction horizon (trading days)
KNN_TSTAR = 504    # training sample size (2 years)


def knn_features(close: pd.Series, volume: pd.Series | None) -> pd.DataFrame:
    f = pd.DataFrame({
        "p_sma5": close / close.rolling(5).mean() - 1,
        "p_sma20": close / close.rolling(20).mean() - 1,
        "p_sma60": close / close.rolling(60).mean() - 1,
        "r5": close.pct_change(5),
        "r20": close.pct_change(20),
        "vol20": close.pct_change().rolling(20).std(),
    })
    if volume is not None and (volume > 0).mean() > 0.9:
        f["vol_ratio"] = volume.rolling(5).mean() / volume.rolling(60).mean()
    return f


def knn_predict(F: np.ndarray, Y: np.ndarray, i: int, T=KNN_T, Tstar=KNN_TSTAR):
    """Predicted T-day return and threshold at position i (uses only information up to i)."""
    j1 = i - T
    j0 = j1 - Tstar + 1
    if j0 < 0:
        return np.nan, np.nan
    Xtr, Ytr = F[j0:j1 + 1], Y[j0:j1 + 1]
    ok = ~np.isnan(Xtr).any(axis=1) & ~np.isnan(Ytr)
    x = F[i]
    if ok.sum() < Tstar * 0.8 or np.isnan(x).any():
        return np.nan, np.nan
    Xtr, Ytr = Xtr[ok], Ytr[ok]
    lo, hi = Xtr.min(axis=0), Xtr.max(axis=0)
    rng = np.where(hi - lo > 0, hi - lo, 1.0)
    d = (((Xtr - lo) / rng - (x - lo) / rng) ** 2).sum(axis=1)
    k = int(math.floor(math.sqrt(Tstar)))
    nn = np.argpartition(d, k)[:k]
    return float(Ytr[nn].mean()), float(0.3 * Ytr.std())


def knn_series(close: pd.Series, volume: pd.Series | None, start: int | None = None):
    F = knn_features(close, volume).values
    Y = (close.shift(-KNN_T) / close - 1).values
    n = len(close)
    pred, thr = np.full(n, np.nan), np.full(n, np.nan)
    start = KNN_T + KNN_TSTAR + 60 if start is None else start
    for i in range(start, n):
        pred[i], thr[i] = knn_predict(F, Y, i)
    return pd.Series(pred, index=close.index), pd.Series(thr, index=close.index)


def knn_positions(pred: pd.Series, thr: pd.Series) -> pd.Series:
    p, z = pred.values, thr.values
    out = np.zeros(len(p))
    pos = 0
    for i in range(len(p)):
        if np.isnan(p[i]):
            pos = 0
        elif pos == 0:
            pos = 1 if p[i] > z[i] else (-1 if p[i] < -z[i] else 0)
        elif pos == 1 and p[i] <= 0:
            pos = -1 if p[i] < -z[i] else 0
        elif pos == -1 and p[i] >= 0:
            pos = 1 if p[i] > z[i] else 0
        out[i] = pos
    return pd.Series(out, index=pred.index)


def run_knn(ctx: Ctx):
    close = ctx.index.dropna()
    vol = ctx.md.volume[ctx.idx_sym].reindex(close.index) if ctx.idx_sym in ctx.md.volume else None
    pred, thr = knn_series(close, vol)
    pos = knn_positions(pred, thr)
    r = ctx.index_ret.reindex(close.index)
    net, gross, turn = M.run_positions(r, pos)
    lo_net, _, _ = M.run_positions(r, pos.clip(lower=0))
    # directional accuracy of the forecast
    y = (close.shift(-KNN_T) / close - 1)
    ok = pred.notna() & y.notna()
    acc = float((np.sign(pred[ok]) == np.sign(y[ok])).mean()) if ok.any() else None
    # live prediction for each constituent
    rows, nl, ns = [], 0, 0
    for k in ctx.keys:
        c = ctx.close[k].dropna()
        if len(c) < KNN_TSTAR + KNN_T + 120:
            continue
        v = ctx.volume[k].reindex(c.index)
        F = knn_features(c, v).values
        Y = (c.shift(-KNN_T) / c - 1).values
        p, z = knn_predict(F, Y, len(c) - 1)
        if np.isnan(p):
            continue
        sig = "Long" if p > z else ("Short" if p < -z else "Flat")
        nl += sig == "Long"
        ns += sig == "Short"
        rows.append([ctx.names[k], f"{p * 100:+.2f}%", sig])
    rows.sort(key=lambda r: -float(r[1].strip("%")))
    last = int(pos.iloc[-1])
    lastp = pred.iloc[-1]
    tables = [M.table(f"Live {KNN_T}-day forecasts for constituents ({nl} long / {ns} short)", ["Stock", f"Predicted {KNN_T}d return", "Signal"], rows)] if rows else []
    blk = M.block(
        net=net, gross=gross, turnover=turn, bench=r, extra_curves={"long_only": lo_net},
        signal=M.signal(f"{ {1: 'LONG', -1: 'SHORT', 0: 'FLAT'}[last] } {ctx.idx_name} (forecast {lastp * 100:+.2f}% / {KNN_T}d)" if not np.isnan(lastp) else "No forecast",
                        {1: "long", -1: "short", 0: "neutral"}[last]),
        tables=tables,
        extra_metrics={"direction_accuracy": None if acc is None else round(acc, 4)},
        notes=[f"Features (min-max normalised over the training window): price / SMA(5, 20, 60) − 1, 5- and 20-day return, 20-day volatility"
               f"{', volume ratio' if (vol is not None and (vol > 0).mean() > 0.9) else ''} (Eqs. 333-337). "
               f"Target = next {KNN_T}-day return. Walk-forward: each day the k = ⌊√{KNN_TSTAR}⌋ = {int(math.sqrt(KNN_TSTAR))} nearest neighbours in the previous {KNN_TSTAR} days "
               "(whose targets are already known) are averaged (Eq. 339). Long if forecast > z₁ (0.3σ of past returns), short if < −z₁, liquidated when the forecast crosses zero (Eq. 341).",
               "Index volume is not published by Yahoo, so the volume feature is only used for stocks with volume data."])
    return entry("3.17", "Machine learning – single-stock KNN", "ml",
                 "Predict the next-week return from price/volume features by averaging what happened after the k most similar past days (k-nearest neighbours), then trade the forecast.", blk)


# ======================================================================== ANN (18.2)

def ann_features(close: pd.Series, T1=60, taus=(5, 10, 20, 40), rsi_taus=(5, 14, 30)) -> pd.DataFrame:
    r = close.pct_change()
    mean_prev = r.rolling(T1).mean().shift(1)
    sd_prev = r.rolling(T1).std().shift(1)
    rh = (r - mean_prev) / sd_prev
    f = {"r": rh}
    for t in taus:
        lam = (t - 1) / (t + 1)
        ew = rh.ewm(alpha=1 - lam, adjust=True)
        f[f"ema{t}"] = ew.mean()
        f[f"emsd{t}"] = ew.std()
    for t in rsi_taus:
        up = rh.clip(lower=0).rolling(t).sum()
        dn = (-rh).clip(lower=0).rolling(t).sum()
        f[f"rsi{t}"] = up / (up + dn)
    return pd.DataFrame(f), rh


class _MLP:
    """Tiny ReLU MLP with softmax output, Adam, cross-entropy (Eqs. 532-536)."""

    def __init__(self, sizes, seed=0, l2=1e-3):
        rng = np.random.default_rng(seed)
        self.W = [rng.standard_normal((a, b)) * math.sqrt(2.0 / a) for a, b in zip(sizes[:-1], sizes[1:])]
        self.b = [np.zeros(b) for b in sizes[1:]]
        self.l2 = l2

    def forward(self, X):
        acts = [X]
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            z = acts[-1] @ W + b
            if i < len(self.W) - 1:
                acts.append(np.maximum(z, 0.0))
            else:
                z = z - z.max(axis=1, keepdims=True)
                e = np.exp(z)
                acts.append(e / e.sum(axis=1, keepdims=True))
        return acts

    def fit(self, X, Y, epochs=200, lr=0.01):
        m = [np.zeros_like(p) for p in self.W + self.b]
        v = [np.zeros_like(p) for p in self.W + self.b]
        n = len(X)
        b1, b2, eps = 0.9, 0.999, 1e-8
        for t in range(1, epochs + 1):
            acts = self.forward(X)
            delta = (acts[-1] - Y) / n
            gW, gb = [], []
            for i in range(len(self.W) - 1, -1, -1):
                gW.insert(0, acts[i].T @ delta + self.l2 * self.W[i])
                gb.insert(0, delta.sum(axis=0))
                if i > 0:
                    delta = (delta @ self.W[i].T) * (acts[i] > 0)
            grads = gW + gb
            params = self.W + self.b
            for j, (p, g) in enumerate(zip(params, grads)):
                m[j] = b1 * m[j] + (1 - b1) * g
                v[j] = b2 * v[j] + (1 - b2) * g * g
                p -= lr * (m[j] / (1 - b1 ** t)) / (np.sqrt(v[j] / (1 - b2 ** t)) + eps)

    def predict(self, X):
        return self.forward(X)[-1]


def ann_walk_forward(close: pd.Series, K=3, train=756, retrain=63, epochs=150):
    F, rh = ann_features(close)
    label_src = rh.shift(-1)                         # normalised return of the NEXT day
    X_all = F.values
    n = len(close)
    probs = np.full((n, K), np.nan)
    first = 60 + 40 + train + 5
    for t0 in range(first, n, retrain):
        j1 = t0 - 1                                   # last row whose label (day j+1) is known at t0
        j0 = j1 - train + 1
        Xtr, ytr = X_all[j0:j1 + 1], label_src.values[j0:j1 + 1]
        ok = ~np.isnan(Xtr).any(axis=1) & ~np.isnan(ytr)
        if ok.sum() < train * 0.7:
            continue
        Xtr, ytr = Xtr[ok], ytr[ok]
        qs = np.quantile(ytr, np.linspace(0, 1, K + 1)[1:-1])
        cls = np.searchsorted(qs, ytr, side="right")
        Y = np.eye(K)[cls]
        mu, sd = Xtr.mean(axis=0), Xtr.std(axis=0)
        sd = np.where(sd > 0, sd, 1.0)
        net = _MLP([Xtr.shape[1], 16, 8, K], seed=1)
        net.fit((Xtr - mu) / sd, Y, epochs=epochs)
        hi = min(n, t0 + retrain)
        Xp = X_all[t0:hi]
        okp = ~np.isnan(Xp).any(axis=1)
        if okp.any():
            probs[t0:hi][okp] = net.predict((Xp[okp] - mu) / sd)
        last_q = qs
    return probs, label_src, F


def run_ann(ctx: Ctx):
    close = ctx.index.dropna()
    probs, label_src, F = ann_walk_forward(close)
    K = probs.shape[1]
    ok = ~np.isnan(probs).any(axis=1)
    cls = np.where(ok, np.nanargmax(np.where(ok[:, None], probs, 0), axis=1), -1)
    pos = pd.Series(np.where(cls == K - 1, 1.0, np.where(cls == 0, -1.0, 0.0)), index=close.index)
    pos[~ok] = 0.0
    r = ctx.index_ret.reindex(close.index)
    net, gross, turn = M.run_positions(r, pos)
    lo_net, _, _ = M.run_positions(r, pos.clip(lower=0))
    # out-of-sample classification accuracy (class of next-day normalised return vs predicted class)
    nxt = label_src.values
    acc = None
    trades = ok & ((cls == K - 1) | (cls == 0)) & ~np.isnan(nxt)
    if trades.any():
        hit = np.sign(nxt[trades]) == np.where(cls[trades] == K - 1, 1, -1)
        acc = float(hit.mean())
    last = int(pos.iloc[-1])
    pl = probs[-1]
    plab = "" if np.isnan(pl).any() else f" (P low/mid/high = {pl[0]:.0%}/{pl[1]:.0%}/{pl[2]:.0%})"
    blk = M.block(
        net=net, gross=gross, turnover=turn, bench=r, extra_curves={"long_only": lo_net},
        signal=M.signal(f"{ {1: 'BUY', -1: 'SELL', 0: 'FLAT'}[last] } {ctx.idx_name}{plab}", {1: "long", -1: "short", 0: "neutral"}[last]),
        extra_metrics={"direction_accuracy": None if acc is None else round(acc, 4)},
        notes=["Adapted from the book's Bitcoin ANN: inputs are the normalised daily return, EMA and EMSD (τ = 5, 10, 20, 40, λ = (τ−1)/(τ+1)) and RSI (τ = 5, 14, 30) (Eqs. 521-529). "
               "Output = probability that the next day's normalised return falls in the low / middle / high tercile (K = 3).",
               "Network 12 → 16 → 8 → 3 (ReLU hidden layers, softmax output, cross-entropy loss, Adam). Walk-forward: retrained every 63 days on the previous 3 years only; "
               "all reported results are out-of-sample. Signal: buy if the top tercile is most likely, sell if the bottom tercile is, otherwise flat (Eq. 537).",
               "The book applies this to cryptocurrencies at 15-minute resolution; here it is daily on the index. Expect weak edge – equity indexes are far more efficient than crypto."])
    return entry("18.2", "Artificial neural network (ANN)", "ml",
                 "Train a small neural network on technical indicators to forecast which return quantile comes next, and buy/sell on the predicted class.",
                 blk, status="adapted",
                 extra={"adapted_note": "Book strategy trades Bitcoin; applied to NIFTY 50 / SENSEX daily data."})


def run(ctx: Ctx):
    return {
        "3.17": guarded(run_knn, "3.17", "Machine learning \u2013 single-stock KNN", "ml", ctx),
        "18.2": guarded(run_ann, "18.2", "Artificial neural network (ANN)", "ml", ctx),
    }
