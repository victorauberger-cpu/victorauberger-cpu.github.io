"""
Fetches prices from Yahoo Finance (free, via the yfinance library) and writes data/prices.json:
  - the latest price of every ticker in data/positions.json
  - an equal-weighted performance series (in %) of the whole portfolio since the first trade

Runs automatically on GitHub (see .github/workflows/deploy.yml). You never need to run it yourself,
but you can locally with:  pip install yfinance pandas && python scripts/update_prices.py

Method: every position counts equally (no amounts are used). Each day, the portfolio return is the
average daily return of the positions open that day; shorts gain when the price falls. The first
day uses your entry price and the last day your exit price, so it matches what you recorded.
Returns are in each stock's own currency.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
POSITIONS = ROOT / "data" / "positions.json"
OUT = ROOT / "data" / "prices.json"


def fetch_closes(tickers, start):
    import yfinance as yf

    df = yf.download(tickers, start=start, interval="1d", auto_adjust=False,
                     progress=False, threads=True)
    closes = df["Close"]
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(tickers[0])
    idx = pd.to_datetime(closes.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    closes.index = idx.normalize()
    return closes.sort_index().ffill()


def compute(positions, closes):
    last, daily_returns = {}, []
    for p in positions:
        t = p["ticker"]
        s = closes[t].dropna() if t in closes.columns else pd.Series(dtype=float)
        last[t] = round(float(s.iloc[-1]), 4) if len(s) else None

        entry = pd.Timestamp(p["entryDate"])
        exit_ = pd.Timestamp(p["exitDate"]) if p.get("exitDate") else None
        mask = s.index > entry
        if exit_ is not None:
            mask &= s.index < exit_
        parts = [pd.Series({entry: float(p["entry"])}), s[mask]]
        if exit_ is not None and p.get("exit") not in (None, ""):
            parts.append(pd.Series({exit_: float(p["exit"])}))
        path = pd.concat(parts).sort_index()
        path = path[~path.index.duplicated(keep="last")]

        # Value of 1 unit put into the trade: long = P/entry, short = 1 + (entry - P)/entry.
        # This makes a single trade's cumulative return equal the simple return shown on the portfolio page.
        e = float(p["entry"])
        value = path / e if p["side"].lower() != "short" else 1 + (e - path) / e
        r = value.clip(lower=1e-6).pct_change().dropna()
        daily_returns.append(r.rename(t + "_" + p["entryDate"]))

    start = min(pd.Timestamp(p["entryDate"]) for p in positions)
    calendar = closes.index[closes.index >= start].union(pd.DatetimeIndex([start]))
    R = pd.concat(daily_returns, axis=1) if daily_returns else pd.DataFrame(index=calendar)
    R = R.reindex(R.index.union(calendar))
    port = R.mean(axis=1, skipna=True).fillna(0.0)
    cum = (1 + port).cumprod() - 1

    series = [[d.strftime("%Y-%m-%d"), round(float(v), 5)] for d, v in cum.items()]
    return last, series


def main():
    positions = json.loads(POSITIONS.read_text())
    tickers = sorted({p["ticker"] for p in positions})
    start = min(p["entryDate"] for p in positions)
    closes = fetch_closes(tickers, start)
    if closes.empty:
        sys.exit("Yahoo Finance returned no data; keeping the previous prices.json")
    last, series = compute(positions, closes)
    OUT.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "sample": False,
        "last": last,
        "series": series,
    }, indent=1))
    print(f"Wrote {OUT} with {len(series)} days, {len(last)} tickers")


if __name__ == "__main__":
    main()
