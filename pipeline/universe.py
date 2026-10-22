"""NIFTY 50 and SENSEX 30 constituents plus the other Yahoo Finance tickers we use.

Constituent lists are a static snapshot (indices rebalance twice a year) – edit here
when they change.  Each stock may list several Yahoo symbol candidates (renames /
demergers); the loader picks the candidate with the freshest, longest history.
Tickers that cannot be downloaded are skipped and reported in meta.json.
"""

# (name, [yahoo candidates], sector cluster)
_S = {
    "FIN": "Financials", "IT": "IT", "ENU": "Energy & Utilities", "AUTO": "Auto",
    "STH": "Staples & Health", "MAT": "Materials", "IND": "Industrials & Infra",
    "CON": "Consumer & Telecom",
}

STOCKS = {
    # key: (name, candidates, sector)
    "HDFCBANK": ("HDFC Bank", ["HDFCBANK.NS"], "FIN"),
    "ICICIBANK": ("ICICI Bank", ["ICICIBANK.NS"], "FIN"),
    "SBIN": ("State Bank of India", ["SBIN.NS"], "FIN"),
    "KOTAKBANK": ("Kotak Mahindra Bank", ["KOTAKBANK.NS"], "FIN"),
    "AXISBANK": ("Axis Bank", ["AXISBANK.NS"], "FIN"),
    "INDUSINDBK": ("IndusInd Bank", ["INDUSINDBK.NS"], "FIN"),
    "BAJFINANCE": ("Bajaj Finance", ["BAJFINANCE.NS"], "FIN"),
    "BAJAJFINSV": ("Bajaj Finserv", ["BAJAJFINSV.NS"], "FIN"),
    "SHRIRAMFIN": ("Shriram Finance", ["SHRIRAMFIN.NS"], "FIN"),
    "JIOFIN": ("Jio Financial Services", ["JIOFIN.NS"], "FIN"),
    "HDFCLIFE": ("HDFC Life Insurance", ["HDFCLIFE.NS"], "FIN"),
    "SBILIFE": ("SBI Life Insurance", ["SBILIFE.NS"], "FIN"),
    "TCS": ("Tata Consultancy Services", ["TCS.NS"], "IT"),
    "INFY": ("Infosys", ["INFY.NS"], "IT"),
    "HCLTECH": ("HCL Technologies", ["HCLTECH.NS"], "IT"),
    "WIPRO": ("Wipro", ["WIPRO.NS"], "IT"),
    "TECHM": ("Tech Mahindra", ["TECHM.NS"], "IT"),
    "RELIANCE": ("Reliance Industries", ["RELIANCE.NS"], "ENU"),
    "ONGC": ("ONGC", ["ONGC.NS"], "ENU"),
    "COALINDIA": ("Coal India", ["COALINDIA.NS"], "ENU"),
    "NTPC": ("NTPC", ["NTPC.NS"], "ENU"),
    "POWERGRID": ("Power Grid Corp", ["POWERGRID.NS"], "ENU"),
    "MARUTI": ("Maruti Suzuki", ["MARUTI.NS"], "AUTO"),
    "M&M": ("Mahindra & Mahindra", ["M&M.NS"], "AUTO"),
    "BAJAJ-AUTO": ("Bajaj Auto", ["BAJAJ-AUTO.NS"], "AUTO"),
    "EICHERMOT": ("Eicher Motors", ["EICHERMOT.NS"], "AUTO"),
    "HEROMOTOCO": ("Hero MotoCorp", ["HEROMOTOCO.NS"], "AUTO"),
    "TATAMOTORS": ("Tata Motors", ["TATAMOTORS.NS", "TMPV.NS"], "AUTO"),
    "HINDUNILVR": ("Hindustan Unilever", ["HINDUNILVR.NS"], "STH"),
    "ITC": ("ITC", ["ITC.NS"], "STH"),
    "NESTLEIND": ("Nestle India", ["NESTLEIND.NS"], "STH"),
    "TATACONSUM": ("Tata Consumer Products", ["TATACONSUM.NS"], "STH"),
    "SUNPHARMA": ("Sun Pharma", ["SUNPHARMA.NS"], "STH"),
    "CIPLA": ("Cipla", ["CIPLA.NS"], "STH"),
    "DRREDDY": ("Dr. Reddy's Labs", ["DRREDDY.NS"], "STH"),
    "APOLLOHOSP": ("Apollo Hospitals", ["APOLLOHOSP.NS"], "STH"),
    "TATASTEEL": ("Tata Steel", ["TATASTEEL.NS"], "MAT"),
    "JSWSTEEL": ("JSW Steel", ["JSWSTEEL.NS"], "MAT"),
    "HINDALCO": ("Hindalco", ["HINDALCO.NS"], "MAT"),
    "GRASIM": ("Grasim", ["GRASIM.NS"], "MAT"),
    "ULTRACEMCO": ("UltraTech Cement", ["ULTRACEMCO.NS"], "MAT"),
    "LT": ("Larsen & Toubro", ["LT.NS"], "IND"),
    "ADANIENT": ("Adani Enterprises", ["ADANIENT.NS"], "IND"),
    "ADANIPORTS": ("Adani Ports & SEZ", ["ADANIPORTS.NS"], "IND"),
    "BEL": ("Bharat Electronics", ["BEL.NS"], "IND"),
    "TITAN": ("Titan Company", ["TITAN.NS"], "CON"),
    "TRENT": ("Trent", ["TRENT.NS"], "CON"),
    "ASIANPAINT": ("Asian Paints", ["ASIANPAINT.NS"], "CON"),
    "ETERNAL": ("Eternal (Zomato)", ["ETERNAL.NS", "ZOMATO.NS"], "CON"),
    "BHARTIARTL": ("Bharti Airtel", ["BHARTIARTL.NS"], "CON"),
}

NIFTY50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJFINANCE",
    "BAJAJFINSV", "BEL", "BHARTIARTL", "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HINDALCO", "HINDUNILVR",
    "ICICIBANK", "INDUSINDBK", "INFY", "ITC", "JIOFIN", "JSWSTEEL", "KOTAKBANK", "LT", "M&M",
    "MARUTI", "NESTLEIND", "NTPC", "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN",
    "SHRIRAMFIN", "SUNPHARMA", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TCS", "TECHM", "TITAN",
    "TRENT", "ULTRACEMCO", "WIPRO",
]

SENSEX30 = [
    "ADANIPORTS", "ASIANPAINT", "AXISBANK", "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL",
    "ETERNAL", "HCLTECH", "HDFCBANK", "HINDUNILVR", "ICICIBANK", "INFY", "ITC", "KOTAKBANK", "LT",
    "M&M", "MARUTI", "NTPC", "POWERGRID", "RELIANCE", "SBIN", "SUNPHARMA", "TATAMOTORS",
    "TATASTEEL", "TCS", "TECHM", "TITAN", "TRENT", "ULTRACEMCO",
]

MEMBERS = {"NIFTY50": NIFTY50, "SENSEX30": SENSEX30}

# NSE sector indices used as "sector ETF" proxies (4.1 - 4.4)
# NSE sector indices that Yahoo Finance still serves (verified from a live run, Oct 2026).  The other
# NSE sector indices (^CNXAUTO, ^CNXENERGY, ^CNXFMCG, ^CNXINFRA, ^CNXMEDIA, ^CNXMETAL, ^CNXPSUBANK,
# ^CNXREALTY) return no data, so sector rotation (4.1-4.4) uses constituent baskets instead (etfs.sector_baskets).
SECTOR_INDICES = {
    "^NSEBANK": "Nifty Bank",
    "^CNXIT": "Nifty IT",
    "^CNXPHARMA": "Nifty Pharma",
}

# Multi-asset trend-following universe (4.6): equity beta, mid/next-50, gold, silver, global equity, cash
MULTI_ASSET = {
    "^NSEI": "NIFTY 50",
    "^NSMIDCP": "Nifty Next 50",
    "^NSEBANK": "Nifty Bank",
    "GOLDBEES.NS": "Gold ETF (GOLDBEES)",
    "SILVERBEES.NS": "Silver ETF (SILVERBEES)",
    "MON100.NS": "Nasdaq-100 ETF (MON100)",
}
UNCORRELATED_ASSET = "GOLDBEES.NS"   # dual-momentum fallback (4.1.2)

BROAD_INDICES = {"^NSEI": "NIFTY 50", "^BSESN": "SENSEX"}


def sector_name(code: str) -> str:
    return _S[code]


def all_symbol_groups():
    """Everything that has to be downloaded, grouped for logging."""
    stocks = sorted({c for k in STOCKS for c in STOCKS[k][1]})
    others = sorted(set(BROAD_INDICES) | set(SECTOR_INDICES) | set(MULTI_ASSET) | {"^INDIAVIX"})
    return stocks, others
