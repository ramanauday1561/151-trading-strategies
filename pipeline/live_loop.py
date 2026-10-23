"""Intraday refresh loop used by the `Live refresh` GitHub Actions workflow.

Every `--every` seconds during NSE market hours it re-runs the whole pipeline and publishes the JSON to
the `live-data` branch (a single force-pushed orphan commit), which the website reads directly.  That is
much more reliable than GitHub's cron, which routinely fires late or not at all.

    python -m pipeline.live_loop --out site/data --every 300 --max-minutes 170 --publish
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import run as runner

log = logging.getLogger("pipeline.live")
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
OPEN, CLOSE = dt.time(9, 15), dt.time(15, 30)
STOP_AFTER = dt.time(15, 45)         # one last refresh after the closing bar settles
START_BEFORE = dt.time(8, 45)        # begin early so the first bar of the day is picked up within minutes


def ist_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone(IST)


def is_trading_day(d: dt.date) -> bool:
    return d.weekday() < 5


def in_window(now: dt.datetime) -> bool:
    """True from 08:45 to 15:45 IST on weekdays."""
    return is_trading_day(now.date()) and START_BEFORE <= now.time() <= STOP_AFTER


def window_over(now: dt.datetime) -> bool:
    return (not is_trading_day(now.date())) or now.time() > STOP_AFTER


def publish(data_dir: Path, branch: str = "live-data") -> bool:
    """Force-push the JSON files as one orphan commit so the branch never grows."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        log.warning("GITHUB_REPOSITORY / GITHUB_TOKEN not set: skipping publish")
        return False
    tmp = Path(tempfile.mkdtemp(prefix="live-data-"))
    try:
        (tmp / "data").mkdir()
        for f in data_dir.glob("*.json"):
            shutil.copy(f, tmp / "data" / f.name)
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        git = lambda *a: subprocess.run(["git", *a], cwd=tmp, check=True, capture_output=True, text=True, env=env)
        git("init", "-q", "-b", branch)
        git("config", "user.name", "github-actions[bot]")
        git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
        git("add", "-A")
        git("commit", "-q", "-m", f"live data {dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ}")
        git("push", "-q", "--force", f"https://x-access-token:{token}@github.com/{repo}.git", f"{branch}:{branch}")
        return True
    except subprocess.CalledProcessError as exc:
        log.error("publish failed: %s", (exc.stderr or "").replace(token, "***"))
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/data")
    ap.add_argument("--every", type=int, default=300, help="seconds between refreshes")
    ap.add_argument("--max-minutes", type=int, default=170, help="stop this segment after N minutes (job time limit)")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--force", action="store_true", help="ignore the market-hours window (testing)")
    ap.add_argument("--cache-dir", default=".cache")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    started = time.time()
    out = Path(args.out)
    ok_runs = 0
    while True:
        now = ist_now()
        if not args.force and window_over(now):
            log.info("market window over (%s IST): stopping, chain ends", now.strftime("%a %H:%M"))
            return 0
        if not args.force and now.time() < START_BEFORE:
            wait = (dt.datetime.combine(now.date(), START_BEFORE, IST) - now).total_seconds()
            log.info("before the window, sleeping %.0fs", wait)
            time.sleep(min(wait, 600))
            continue
        t0 = time.time()
        code = runner.main(["--out", str(out), "--cache-dir", args.cache_dir])
        if code in (0,):
            ok_runs += 1
            if args.publish:
                publish(out)
        else:
            log.error("pipeline run failed with code %s; will retry next cycle", code)
        # holiday detection: after 09:45 IST the latest bar must be today
        try:
            import json
            asof = json.load(open(out / "meta.json"))["data_asof"]
            if not args.force and now.time() > dt.time(9, 45) and asof != now.date().isoformat():
                log.info("latest bar is %s, not today: exchange holiday, stopping", asof)
                return 0
        except Exception:
            pass
        elapsed_min = (time.time() - started) / 60
        if elapsed_min + args.every / 60 + 1.5 > args.max_minutes:
            log.info("segment time budget used (%.0f min): handing over to the next segment", elapsed_min)
            return 10          # signals the workflow to chain a new segment
        time.sleep(max(5, args.every - (time.time() - t0)))


if __name__ == "__main__":
    sys.exit(main())
