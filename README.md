# 151 Trading Strategies × NIFTY 50 & SENSEX

A dark-mode dashboard that runs the strategies from *151 Trading Strategies* (Z. Kakushadze & J. A. Serur, SSRN 3247865) against the **NIFTY 50** and **SENSEX** using **Yahoo Finance** data. A **GitHub Actions** workflow refreshes everything every 10 minutes during NSE hours and deploys it to **GitHub Pages**.

* **94 strategies live** – 58 option structures, 18 stock strategies, 7 sector/multi-asset, 3 index, 3 volatility, 4 futures/hedging, 1 neural-net (adapted from crypto).
* **82 book sections excluded** (fixed income, FX, commodities, structured credit, real estate, …, or anything needing data Yahoo does not carry). Each has its reason on the site's *Not applicable* page; `pipeline/registry.py` makes sure no section is silently dropped.
* Strategies marked **ADAPTED** keep the book's method but swap the factor set/asset; **PROXY DATA** means a related series stands in for data Yahoo lacks (e.g. cash index for futures, India VIX for option IV).

## Enable the site (one-time)

1. Merge this branch into `main`.
2. Repo **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. Run **Actions → Refresh & Deploy → Run workflow** (afterwards it runs on schedule).

GitHub pauses scheduled workflows after 60 days without repo activity; re-enable from the Actions tab if that happens.

## Live during market hours

`Live refresh` (`.github/workflows/live.yml`) runs `pipeline/live_loop.py`: every 5 minutes from 08:45 to 15:45 IST on weekdays it re-runs all strategies and force-pushes the JSON to the `live-data` branch. The site reads that branch when it is newer than the Pages copy and re-renders on its own (it checks every 30 s). Each job segment lasts ~170 min and starts the next one itself, so GitHub's unreliable cron only has to fire once a day. It stops by itself on weekends and exchange holidays. Run it manually from Actions with **force** ticked to test outside market hours.

## Install on your phone (PWA)

Open the Pages URL over HTTPS, then:
* **Android / Chrome:** tap **⬇ Install app** in the header (or ⋮ → Install app).
* **iPhone / iPad (Safari):** Share icon → **Add to Home Screen**.
* **Share:** the **⤴ Share** button opens the system share sheet (or copies the link); links keep the current page, e.g. `#/s/2.25`.

It opens offline with the last downloaded data (service worker `site/sw.js`, network-first so you always get fresh data when online).

## Run locally

```bash
pip install -r requirements.txt
python -m pytest -q tests                 # no network needed
python -m pipeline.run --out site/data    # live Yahoo data
python -m http.server -d site 8000        # open http://localhost:8000
python -m pipeline.run --out site/data --synthetic   # offline fake data (site shows a red banner)
```

## Layout

| Path | What |
|---|---|
| `pipeline/data.py` | Yahoo download (retries, ticker candidates, fundamentals) + synthetic test market |
| `pipeline/options.py` | Black-Scholes engine, all 58 option strategies, payoff analytics, monthly-roll backtest |
| `pipeline/stocks_xs.py`, `technical.py`, `ml.py` | Chapter 3 + KNN / ANN |
| `pipeline/etfs.py`, `indexes.py`, `volatility.py`, `futures.py` | Chapters 4, 6, 7, 10 |
| `pipeline/universe.py`, `config.py` | Constituents (static snapshot – edit when indexes rebalance) and assumptions (r, costs, …) |
| `site/` | Static dashboard (vanilla JS + vendored Chart.js); `site/data/` is generated, not committed |

## Honest limitations

* Yahoo data is delayed and occasionally wrong; the run aborts if <90% of constituents download.
* No index option chains or futures prices on Yahoo → options are theoretical (flat India VIX vol), futures strategies use spot as proxy.
* Value has no historical backtest (Yahoo has no point-in-time book values).
* Backtests ignore slippage, borrow, margin, taxes. Educational use only – not investment advice.
