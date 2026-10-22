import json
import math
import warnings

import numpy as np
import pandas as pd
import pytest

from pipeline import config as C
from pipeline import data, options, registry as R, run as runner, universe as U
from pipeline import metrics as M
from pipeline.common import guarded
from pipeline.stocks_xs import alpha_combo_weights, mr_weights, stat_risk_model

warnings.filterwarnings("ignore")


@pytest.fixture(scope="module")
def market():
    return data.synthetic_market(seed=3, years=12)


@pytest.fixture(scope="module")
def results(market):
    strategies, errors = runner.run_all(market)
    runner.fill_missing(strategies, errors)
    return strategies, errors


# --------------------------------------------------------------- registry / integration

def test_universe_lists():
    assert len(U.NIFTY50) == 50 and len(set(U.NIFTY50)) == 50
    assert len(U.SENSEX30) == 30 and len(set(U.SENSEX30)) == 30
    assert all(k in U.STOCKS for k in U.NIFTY50 + U.SENSEX30)


def test_every_book_section_is_applied_or_excluded(results):
    strategies, _ = results
    n_impl, n_excl = R.check_coverage(set(strategies))
    assert n_impl == 94 and n_excl == 82
    assert n_impl + n_excl == len(R.BOOK)


def test_no_strategy_errors_on_synthetic_data(results):
    strategies, errors = results
    assert errors == []
    for sid, s in strategies.items():
        assert set(s["universes"]) == {"NIFTY50", "SENSEX30"}, sid


def test_output_is_strict_json(results):
    strategies, _ = results
    blob = json.dumps(runner.sanitize(list(strategies.values())), allow_nan=False)
    assert "NaN" not in blob and "Infinity" not in blob


def test_all_options_present(results):
    strategies, _ = results
    assert sum(1 for s in strategies.values() if s["category"] == "options") == 58
    assert options.OPTION_IDS == [i for i, _ in R.BOOK if i.startswith("2.")]


def test_guard_isolates_failures():
    def boom():
        raise ValueError("bad data")

    e = guarded(boom, "9.9", "Broken", "stocks")
    assert e["block"]["error"].startswith("ValueError")


# ------------------------------------------------------------------------ options maths

S0, SIG = 25000.0, 0.15
STEP = 50.0


def _spec(sid):
    return next(s for s in options.SPECS if s[0] == sid)


def _an(sid):
    legs = _spec(sid)[-1]
    a = options.analyze(legs, S0, SIG, STEP)
    return a, a["atm"], a["unit"]


def _p(kind, K, days=30):
    return float(options.bs_price(kind, S0, K, days / 365, SIG))


def test_put_call_parity():
    K, T = 25000.0, 30 / 365
    c, p = options.bs_price("C", S0, K, T, SIG), options.bs_price("P", S0, K, T, SIG)
    assert c - p == pytest.approx(S0 * math.exp(-C.DIV_YIELD * T) - K * math.exp(-C.RISK_FREE * T), abs=1e-6)


def test_covered_call_matches_book_formulas():       # Eqs. (2)-(4)
    a, atm, u = _an("2.2")
    K = atm + u
    credit = _p("C", K)
    st = a["stats"]
    assert st["net_premium"] == pytest.approx(-credit, abs=0.01)
    assert st["max_profit"] == pytest.approx(K - S0 + credit, abs=0.5)
    assert st["max_loss"] == pytest.approx(S0 - credit, abs=0.5)
    assert st["breakevens"][0] == pytest.approx(S0 - credit, abs=0.5)


def test_bull_call_spread_matches_book_formulas():  # Eqs. (17)-(20)
    a, atm, u = _an("2.6")
    K1, K2 = atm, atm + 2 * u
    D = _p("C", K1) - _p("C", K2)
    st = a["stats"]
    assert st["max_loss"] == pytest.approx(D, abs=0.01)
    assert st["max_profit"] == pytest.approx(K2 - K1 - D, abs=0.5)
    assert st["breakevens"][0] == pytest.approx(K1 + D, abs=0.5)


def test_long_straddle_matches_book_formulas():     # Eqs. (82)-(85)
    a, atm, u = _an("2.22")
    D = _p("C", atm) + _p("P", atm)
    st = a["stats"]
    assert st["max_loss"] == pytest.approx(D, abs=0.01)
    assert st["max_profit"] is None
    assert sorted(st["breakevens"]) == pytest.approx([atm - D, atm + D], abs=0.5)


def test_short_strangle_breakevens():               # Eqs. (101)-(105)
    a, atm, u = _an("2.26")
    K1, K2 = atm + u, atm - u
    C_ = _p("C", K1) + _p("P", K2)
    st = a["stats"]
    assert st["max_profit"] == pytest.approx(C_, abs=0.01)
    assert st["max_loss"] is None
    assert sorted(st["breakevens"]) == pytest.approx([K2 - C_, K1 + C_], abs=0.5)


def test_long_iron_condor_matches_book_formulas():  # Eqs. (226)-(230)
    a, atm, u = _an("2.50")
    k = 2 * u
    C_ = -(_p("P", atm - 3 * u) - _p("P", atm - u) - _p("C", atm + u) + _p("C", atm + 3 * u))
    st = a["stats"]
    assert st["max_profit"] == pytest.approx(C_, abs=0.01)
    assert st["max_loss"] == pytest.approx(k - C_, abs=0.5)


def test_box_is_riskless():
    a, atm, u = _an("2.52")
    assert a["stats"]["riskless"] is True
    pay = np.array(a["payoff"]["expiry"])
    assert pay.max() - pay.min() < 1e-6                 # constant payoff across all terminal prices


def test_calendar_spread_peaks_at_strike():
    a, atm, u = _an("2.18")
    x, y = np.array(a["payoff"]["x"]), np.array(a["payoff"]["expiry"])
    assert abs(x[y.argmax()] - atm) <= 0.01 * S0


# ------------------------------------------------------------------------ engine

def test_run_weights_has_no_lookahead():
    idx = pd.bdate_range("2020-01-01", periods=10)
    ret = pd.DataFrame({"A": [0.0, 0.0, 0.10, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}, index=idx)
    W = pd.DataFrame({"A": [1.0]}, index=[idx[2]])        # decided at the close of day 2 -> may not earn day-2's +10%
    net, gross, _ = M.run_weights(ret, W, cost_bps=0)
    assert gross.sum() == pytest.approx(0.0)
    W = pd.DataFrame({"A": [1.0]}, index=[idx[1]])        # decided at day 1 -> earns day 2
    net, gross, _ = M.run_weights(ret, W, cost_bps=0)
    assert gross.sum() == pytest.approx(0.10)


def test_run_positions_costs_and_lag():
    idx = pd.bdate_range("2020-01-01", periods=5)
    r = pd.Series([0.0, 0.01, 0.01, 0.01, 0.01], index=idx)
    pos = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0], index=idx)
    net, gross, turn = M.run_positions(r, pos, cost_bps=10)
    assert gross.sum() == pytest.approx(0.04)
    assert turn.iloc[0] == pytest.approx(1.0)             # entering costs once
    assert net.sum() == pytest.approx(0.04 - 0.001)


def test_rebalance_dates_are_period_ends():
    idx = pd.bdate_range("2021-01-01", "2021-03-31")
    m = M.rebalance_dates(idx, "M")
    assert len(m) == 3 and m[0] == pd.Timestamp("2021-01-29")


def test_mean_reversion_weights_are_neutral_and_normalised():
    rng = np.random.default_rng(0)
    R_ = pd.Series(rng.standard_normal(40), index=[f"s{i}" for i in range(40)])
    w = mr_weights(R_)
    assert abs(w.sum()) < 1e-12 and w.abs().sum() == pytest.approx(1.0)
    assert np.corrcoef(w, R_)[0, 1] < -0.99               # bets against past returns
    sec = pd.DataFrame({"a": [1.0] * 20 + [0.0] * 20, "b": [0.0] * 20 + [1.0] * 20}, index=R_.index)
    w2 = mr_weights(R_, sec, pd.Series(1.0, index=R_.index))
    assert abs((w2 * sec["a"]).sum()) < 1e-12 and abs((w2 * sec["b"]).sum()) < 1e-12   # cluster-neutral


def test_stat_risk_model_is_positive_definite():
    rng = np.random.default_rng(1)
    f = rng.standard_normal((300, 3))
    X = pd.DataFrame(f @ rng.standard_normal((3, 25)) + 0.7 * rng.standard_normal((300, 25)))
    Cm, sig, K, er, xi2 = stat_risk_model(X)
    assert np.linalg.eigvalsh(Cm).min() > 0 and 1 <= K < 25 and (xi2 > 0).all()


def test_alpha_combo_weights_normalised():
    rng = np.random.default_rng(2)
    Rw = rng.standard_normal((31, 45)) * 0.01
    w = alpha_combo_weights(Rw, d=21)
    assert w.shape == (45,) and np.abs(w).sum() == pytest.approx(1.0)


def test_sanitize_handles_nan_and_numpy():
    out = runner.sanitize({"a": np.float64("nan"), "b": np.int64(3), "c": [float("inf"), 1.5], "d": pd.Timestamp("2020-01-02")})
    assert out == {"a": None, "b": 3, "c": [None, 1.5], "d": "2020-01-02"}
    json.dumps(out, allow_nan=False)
