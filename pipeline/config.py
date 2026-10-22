"""Global assumptions. Everything that is a modelling choice lives here."""

HISTORY_YEARS = 12          # daily history pulled from Yahoo Finance
TRADING_DAYS = 252

# Financial assumptions (INR). Yahoo does not provide these, so they are explicit inputs.
RISK_FREE = 0.065           # annualised, ~10y G-sec / T-bill area
DIV_YIELD = 0.013           # index dividend yield used in the forward price
COST_BPS = 10.0             # one-way transaction cost for equity strategies (bps)

# Option modelling
OPT_HORIZON_DAYS = 30       # near-month option tenor
OPT_FAR_DAYS = 60           # far-leg tenor for calendar / diagonal spreads
OPT_UNIT_PCT = 0.01         # strike offset unit "u" = 1% of spot
OPT_STRIKE_STEP = {"NIFTY50": 50.0, "SENSEX30": 100.0}

# Universes: name -> (index ticker, display name)
UNIVERSES = {
    "NIFTY50": ("^NSEI", "NIFTY 50"),
    "SENSEX30": ("^BSESN", "SENSEX"),
}
VIX_TICKER = "^INDIAVIX"

# Cross-sectional portfolio construction
XS_FRACTION = 0.2           # top / bottom quintile (universe is only 30-50 names)
