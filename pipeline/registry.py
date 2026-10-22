"""Table of contents of "151 Trading Strategies" (Kakushadze & Serur, 2018) and the
applicability decision for NIFTY 50 / SENSEX with Yahoo Finance data.

A strategy is either produced by one of the pipeline modules, or listed in EXCLUDED
with a reason.  `check_coverage` makes sure nothing in the book is silently dropped.
"""

CHAPTERS = {
    2: "Options", 3: "Stocks", 4: "Exchange-traded funds (ETFs)", 5: "Fixed income",
    6: "Indexes", 7: "Volatility", 8: "Foreign exchange (FX)", 9: "Commodities",
    10: "Futures", 11: "Structured assets", 12: "Convertibles", 13: "Tax arbitrage",
    14: "Miscellaneous assets", 15: "Distressed assets", 16: "Real estate", 17: "Cash",
    18: "Cryptocurrencies", 19: "Global macro", 20: "Infrastructure",
}

# (section id, name)
BOOK = [
    # --- 2 Options
    ("2.2", "Covered call"), ("2.3", "Covered put"), ("2.4", "Protective put"),
    ("2.5", "Protective call"), ("2.6", "Bull call spread"), ("2.7", "Bull put spread"),
    ("2.8", "Bear call spread"), ("2.9", "Bear put spread"), ("2.10", "Long synthetic forward"),
    ("2.11", "Short synthetic forward"), ("2.12", "Long combo"), ("2.13", "Short combo"),
    ("2.14", "Bull call ladder"), ("2.15", "Bull put ladder"), ("2.16", "Bear call ladder"),
    ("2.17", "Bear put ladder"), ("2.18", "Calendar call spread"), ("2.19", "Calendar put spread"),
    ("2.20", "Diagonal call spread"), ("2.21", "Diagonal put spread"), ("2.22", "Long straddle"),
    ("2.23", "Long strangle"), ("2.24", "Long guts"), ("2.25", "Short straddle"),
    ("2.26", "Short strangle"), ("2.27", "Short guts"), ("2.28", "Long call synthetic straddle"),
    ("2.29", "Long put synthetic straddle"), ("2.30", "Short call synthetic straddle"),
    ("2.31", "Short put synthetic straddle"), ("2.32", "Covered short straddle"),
    ("2.33", "Covered short strangle"), ("2.34", "Strap"), ("2.35", "Strip"),
    ("2.36", "Call ratio backspread"), ("2.37", "Put ratio backspread"), ("2.38", "Ratio call spread"),
    ("2.39", "Ratio put spread"), ("2.40", "Long call butterfly"), ("2.40.1", "Modified call butterfly"),
    ("2.41", "Long put butterfly"), ("2.41.1", "Modified put butterfly"),
    ("2.42", "Short call butterfly"), ("2.43", "Short put butterfly"),
    ("2.44", "“Long” iron butterfly"), ("2.45", "“Short” iron butterfly"),
    ("2.46", "Long call condor"), ("2.47", "Long put condor"), ("2.48", "Short call condor"),
    ("2.49", "Short put condor"), ("2.50", "Long iron condor"), ("2.51", "Short iron condor"),
    ("2.52", "Long box"), ("2.53", "Collar"), ("2.54", "Bullish short seagull spread"),
    ("2.55", "Bearish long seagull spread"), ("2.56", "Bearish short seagull spread"),
    ("2.57", "Bullish long seagull spread"),
    # --- 3 Stocks
    ("3.1", "Price-momentum"), ("3.2", "Earnings-momentum"), ("3.3", "Value"),
    ("3.4", "Low-volatility anomaly"), ("3.5", "Implied volatility"), ("3.6", "Multifactor portfolio"),
    ("3.7", "Residual momentum"), ("3.8", "Pairs trading"), ("3.9", "Mean-reversion – single cluster"),
    ("3.9.1", "Mean-reversion – multiple clusters"), ("3.10", "Mean-reversion – weighted regression"),
    ("3.11", "Single moving average"), ("3.12", "Two moving averages"), ("3.13", "Three moving averages"),
    ("3.14", "Support and resistance"), ("3.15", "Channel"), ("3.16", "Event-driven – M&A"),
    ("3.17", "Machine learning – single-stock KNN"), ("3.18", "Statistical arbitrage – optimization"),
    ("3.18.1", "Dollar-neutrality"), ("3.19", "Market-making"), ("3.20", "Alpha combos"),
    # --- 4 ETFs
    ("4.1", "Sector momentum rotation"), ("4.1.1", "Sector momentum rotation with MA filter"),
    ("4.1.2", "Dual-momentum sector rotation"), ("4.2", "Alpha rotation"), ("4.3", "R-squared"),
    ("4.4", "Mean-reversion"), ("4.5", "Leveraged ETFs (LETFs)"), ("4.6", "Multi-asset trend following"),
    # --- 5 Fixed income
    ("5.2", "Bullets"), ("5.3", "Barbells"), ("5.4", "Ladders"), ("5.5", "Bond immunization"),
    ("5.6", "Dollar-duration-neutral butterfly"), ("5.7", "Fifty-fifty butterfly"),
    ("5.8", "Regression-weighted butterfly"), ("5.8.1", "Maturity-weighted butterfly"),
    ("5.9", "Low-risk factor"), ("5.10", "Value factor"), ("5.11", "Carry factor"),
    ("5.12", "Rolling down the yield curve"), ("5.13", "Yield curve spread (flatteners & steepeners)"),
    ("5.14", "CDS basis arbitrage"), ("5.15", "Swap-spread arbitrage"),
    # --- 6 Indexes
    ("6.2", "Cash-and-carry arbitrage"), ("6.3", "Dispersion trading in equity indexes"),
    ("6.3.1", "Dispersion trading – subset portfolio"), ("6.4", "Intraday arbitrage between index ETFs"),
    ("6.5", "Index volatility targeting with risk-free asset"),
    # --- 7 Volatility
    ("7.2", "VIX futures basis trading"), ("7.3", "Volatility carry with two ETNs"),
    ("7.3.1", "Hedging short VXX with VIX futures"), ("7.4", "Volatility risk premium"),
    ("7.4.1", "Volatility risk premium with Gamma hedging"),
    ("7.5", "Volatility skew – long risk reversal"), ("7.6", "Volatility trading with variance swaps"),
    # --- 8 FX
    ("8.1", "Moving averages with HP filter"), ("8.2", "Carry trade"), ("8.2.1", "High-minus-low carry"),
    ("8.3", "Dollar carry trade"), ("8.4", "Momentum & carry combo"), ("8.5", "FX triangular arbitrage"),
    # --- 9 Commodities
    ("9.1", "Roll yields"), ("9.2", "Trading based on hedging pressure"),
    ("9.3", "Portfolio diversification with commodities"), ("9.4", "Value"), ("9.5", "Skewness premium"),
    ("9.6", "Trading with pricing models"),
    # --- 10 Futures
    ("10.1", "Hedging risk with futures"), ("10.1.1", "Cross-hedging"), ("10.1.2", "Interest rate risk hedging"),
    ("10.2", "Calendar spread"), ("10.3", "Contrarian trading (mean-reversion)"),
    ("10.3.1", "Contrarian trading – market activity"), ("10.4", "Trend following (momentum)"),
    # --- 11 Structured assets
    ("11.2", "Carry, equity tranche – index hedging"), ("11.3", "Carry, senior/mezzanine – index hedging"),
    ("11.4", "Carry – tranche hedging"), ("11.5", "Carry – CDS hedging"), ("11.6", "CDOs – curve trades"),
    ("11.7", "Mortgage-backed security (MBS) trading"),
    # --- 12 Convertibles
    ("12.1", "Convertible arbitrage"), ("12.2", "Convertible option-adjusted spread"),
    # --- 13 Tax arbitrage
    ("13.1", "Municipal bond tax arbitrage"), ("13.2", "Cross-border tax arbitrage"),
    ("13.2.1", "Cross-border tax arbitrage with options"),
    # --- 14 Miscellaneous
    ("14.1", "Inflation hedging – inflation swaps"), ("14.2", "TIPS-Treasury arbitrage"),
    ("14.3", "Weather risk – demand hedging"), ("14.4", "Energy – spark spread"),
    # --- 15 Distressed
    ("15.1", "Buying and holding distressed debt"), ("15.2", "Active distressed investing"),
    ("15.2.1", "Planning a reorganization"), ("15.2.2", "Buying outstanding debt"),
    ("15.2.3", "Loan-to-own"), ("15.3", "Distress risk puzzle"), ("15.3.1", "Distress risk puzzle – risk management"),
    # --- 16 Real estate
    ("16.2", "Mixed-asset diversification with real estate"),
    ("16.3", "Intra-asset diversification within real estate"), ("16.3.1", "Property type diversification"),
    ("16.3.2", "Economic diversification"), ("16.3.3", "Property type and geographic diversification"),
    ("16.4", "Real estate momentum – regional approach"), ("16.5", "Inflation hedging with real estate"),
    ("16.6", "Fix-and-flip"),
    # --- 17 Cash
    ("17.2", "Money laundering – the dark side of cash"), ("17.3", "Liquidity management"),
    ("17.4", "Repurchase agreement (REPO)"), ("17.5", "Pawnbroking"), ("17.6", "Loan sharking"),
    # --- 18 Crypto
    ("18.2", "Artificial neural network (ANN)"), ("18.3", "Sentiment analysis – naïve Bayes Bernoulli"),
    # --- 19 Global macro
    ("19.2", "Fundamental macro momentum"), ("19.3", "Global macro inflation hedge"),
    ("19.4", "Global fixed-income strategy"), ("19.5", "Trading on economic announcements"),
    # --- 20 Infrastructure
    ("20", "Infrastructure"),
]

_CH_REASON = {
    5: "Fixed-income strategy (bonds, yield curve, CDS, swaps) – NIFTY 50 / SENSEX are equity indexes, and Yahoo Finance has no Indian bond-curve data.",
    8: "Foreign-exchange strategy – trades currency pairs, not NIFTY 50 / SENSEX.",
    9: "Commodity strategy – trades commodity futures/spot, not NIFTY 50 / SENSEX (gold & silver appear only as asset-allocation inputs in 4.6).",
    11: "Structured credit (CDO/MBS) – not related to equity indexes; no data on Yahoo Finance.",
    12: "Convertible-bond strategy – needs convertible bond data, not available for Indian indexes on Yahoo Finance.",
    13: "Tax-arbitrage strategy (municipal bonds / cross-border dividends) – not applicable to NIFTY 50 / SENSEX trading.",
    14: "Inflation / weather / energy derivative – not an equity-index strategy; no data on Yahoo Finance.",
    15: "Distressed-debt strategy – needs bond/loan and bankruptcy data; NIFTY 50 / SENSEX constituents are large, liquid companies.",
    16: "Real-estate strategy – direct property investment, not NIFTY 50 / SENSEX.",
    17: "Cash / money-market activity (REPO, pawnbroking, ...) – not a NIFTY 50 / SENSEX trading strategy.",
    19: "Global-macro strategy – needs macro releases, inflation swaps and cross-asset futures that Yahoo Finance does not provide.",
    20: "Not a strategy (trading infrastructure discussion).",
}

EXCLUDED = {
    "3.2": "Needs quarterly earnings surprises (SUE: 8 quarters of EPS history). Yahoo Finance exposes too little reliable EPS history for Indian stocks.",
    "3.5": "Needs single-stock option implied volatilities. Yahoo Finance has no option chains for Indian equities.",
    "3.16": "Event-driven M&A arbitrage needs a feed of announced deals and deal terms – not available from Yahoo Finance.",
    "3.19": "Market-making needs tick-level order-book data (bid/ask queue). Yahoo Finance only offers delayed bars.",
    "4.5": "No leveraged / inverse ETFs exist on NSE or BSE, so the LETF volatility-decay trade cannot be executed.",
    "6.2": "Cash-and-carry needs index-futures quotes to measure the basis. Yahoo Finance has no NIFTY / SENSEX futures prices.",
    "6.4": "Needs live bid/ask quotes of two ETFs on the same index (κ = 1.002 trigger). Yahoo Finance gives no order-book quotes.",
    "7.2": "VIX-futures basis: no India VIX futures prices on Yahoo Finance.",
    "7.3": "Volatility-ETN carry (VXX/VXZ): no volatility ETNs exist for NIFTY / SENSEX.",
    "7.3.1": "Needs a VIX-futures curve and VXX – no Indian equivalents on Yahoo Finance.",
    "7.5": "Needs the implied-volatility skew (OTM put vs call IV). Yahoo Finance has no NIFTY / SENSEX option chains. The risk-reversal payoff itself is covered in 2.12.",
    "10.1.2": "Interest-rate futures hedging for bonds – not an equity-index strategy.",
    "10.2": "Futures calendar spread needs prices of two futures expiries. Yahoo Finance has no NIFTY / SENSEX futures prices.",
    "10.3.1": "Needs futures open interest and volume changes – open interest is not available from Yahoo Finance.",
    "18.3": "Needs a Twitter/social-media sentiment feed (naive-Bayes text model) – not available from Yahoo Finance.",
}

# Strategies that the book defines for another asset but whose method transfers verbatim.
ADAPTED = {
    "18.2": "Book strategy trades Bitcoin. The ANN method is asset-agnostic, so it is applied here to NIFTY 50 / SENSEX daily returns (book itself notes the technique carries over to equities).",
}


def chapter_of(sid: str) -> int:
    return int(sid.split(".")[0])


def excluded_entries():
    out = []
    for sid, name in BOOK:
        ch = chapter_of(sid)
        reason = EXCLUDED.get(sid) or _CH_REASON.get(ch)
        if reason and sid not in ADAPTED and (sid in EXCLUDED or ch in _CH_REASON):
            out.append({"id": sid, "name": name, "chapter": ch, "chapter_name": CHAPTERS[ch], "reason": reason})
    return out


def check_coverage(produced_ids):
    """Raise if a book section is neither produced nor excluded (or both)."""
    excl = {e["id"] for e in excluded_entries()}
    book_ids = {sid for sid, _ in BOOK}
    produced = set(produced_ids)
    missing = sorted(book_ids - produced - excl)
    both = sorted(produced & excl)
    unknown = sorted(produced - book_ids)
    if missing or both or unknown:
        raise AssertionError(f"registry coverage problem: missing={missing} both={both} unknown={unknown}")
    return len(produced), len(excl)


def book_name(sid):
    return dict(BOOK)[sid]
