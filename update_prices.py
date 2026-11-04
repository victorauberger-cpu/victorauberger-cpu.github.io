"""
Fetches prices from Yahoo Finance (free, via the yfinance library) and writes data/prices.json:
  - the latest price of every ticker in data/positions.json
  - an equal-weighted performance series (in %) of the whole portfolio since inception
  - the S&P 500 (or whichever benchmark is set in data/settings.json) over the same period

Runs automatically on GitHub (see .github/workflows/deploy.yml). You never need to run it yourself,
but you can locally with:  pip install yfinance pandas && python scripts/update_prices.py

Method: every position counts equally (no amounts are used). Each day, the portfolio return is the
average daily return of the positions open that day; shorts gain when the price falls. A position
starts at your entry price (start of its entry day) and ends at your exit price (end of its exit
day), so it matches what you recorded. Returns are in each stock's own currency.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Works whether the files sit in a data/ folder or all at the top of the repository.
_here = Path(__file__).resolve().parent
_candidates = [_here.parent / "data", _here / "data", _here, _here.parent]
DATA = next((d for d in _candidates if (d / "positions.json").exists()), _here)
POSITIONS = DATA / "positions.json"
SETTINGS = DATA / "settings.json"
OUT = DATA / "prices.json"
EOD = pd.Timedelta(hours=23, minutes=59)   # daily closes are stamped at the end of their day


def _clean_index(s):
    idx = pd.to_datetime(s.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    s.index = idx.normalize() + EOD
    return s


def fetch_closes(tickers, start):
    """Batch download from Yahoo, then retry any ticker that came back empty one by one.
    Yahoo sometimes drops a symbol from a batch request; without the retry it would show no price."""
    import time
    import yfinance as yf

    try:
        df = yf.download(tickers, start=start, interval="1d", auto_adjust=False,
                         progress=False, threads=False)
        closes = df["Close"]
        if isinstance(closes, pd.Series):
            closes = closes.to_frame(tickers[0])
        closes = _clean_index(closes)
    except Exception as e:
        print("Batch download failed:", e)
        closes = pd.DataFrame()

    missing = [t for t in tickers if t not in closes.columns or closes[t].dropna().empty]
    for t in missing:
        for attempt in range(3):
            try:
                h = yf.Ticker(t).history(start=start, interval="1d", auto_adjust=False)
                if not h.empty:
                    s = _clean_index(h["Close"].copy()).rename(t)
                    closes = closes.drop(columns=[t], errors="ignore").join(s, how="outer") if not closes.empty else s.to_frame()
                    print(f"Recovered {t} on retry {attempt + 1}")
                    break
            except Exception as e:
                print(f"Retry {attempt + 1} for {t} failed:", e)
            time.sleep(3 * (attempt + 1))
        else:
            print(f"WARNING: no price for {t} from Yahoo this run")
    return closes.sort_index().ffill()


def compute(positions, closes, settings=None):
    settings = settings or {}
    last, daily_returns = {}, []
    for p in positions:
        t = p["ticker"]
        s = closes[t].dropna() if t in closes.columns else pd.Series(dtype=float)
        last[t] = round(float(s.iloc[-1]), 4) if len(s) else None

        entry = pd.Timestamp(p["entryDate"])
        exit_ = pd.Timestamp(p["exitDate"]) + EOD if p.get("exitDate") else None
        mask = s.index > entry
        if exit_ is not None:
            mask &= s.index < exit_
        inside = s[mask]
        # If Yahoo's listing trades at a different price level from the one recorded (another
        # exchange, currency or ADR ratio), use Yahoo only for the day-to-day moves, scaled to the entry.
        on_entry = s[s.index >= entry]
        if len(on_entry) and abs(on_entry.iloc[0] / float(p["entry"]) - 1) > 0.25:
            inside = inside * (float(p["entry"]) / on_entry.iloc[0])
        parts = [pd.Series({entry: float(p["entry"])}), inside]
        if exit_ is not None and p.get("exit") not in (None, ""):
            parts.append(pd.Series({exit_: float(p["exit"])}))
        path = pd.concat(parts).sort_index()
        path = path[~path.index.duplicated(keep="last")]

        # Value of 1 unit put into the trade: long = P/entry, short = 1 + (entry - P)/entry,
        # with leverage multiplying the gain or loss. A single trade's cumulative return then equals
        # the return shown on the portfolio page.
        e = float(p["entry"])
        lev = float(p.get("leverage") or 1)
        raw = path / e - 1 if p["side"].lower() != "short" else (e - path) / e
        value = 1 + lev * raw
        r = value.clip(lower=1e-6).pct_change().dropna()
        daily_returns.append(r.rename(t + "_" + p["entryDate"]))

    start = pd.Timestamp(settings.get("inception") or min(p["entryDate"] for p in positions))
    calendar = closes.index[closes.index >= start].union(pd.DatetimeIndex([start]))
    R = pd.concat(daily_returns, axis=1) if daily_returns else pd.DataFrame(index=calendar)
    R = R.reindex(R.index.union(calendar))
    R = R[R.index >= start]
    port = R.mean(axis=1, skipna=True).fillna(0.0)
    cum = (1 + port).cumprod() - 1

    # Benchmark: buy-and-hold from its level at inception.
    bench = None
    b = settings.get("benchmark")
    if b and b in closes.columns:
        bs = closes[b].dropna()
        base = settings.get("benchmarkAtInception")
        if base is None:
            prior = bs[bs.index < start]
            base = float(prior.iloc[-1]) if len(prior) else float(bs.iloc[0])
        bs = pd.concat([pd.Series({start: float(base)}), bs[bs.index > start]])
        bs = bs[~bs.index.duplicated(keep="last")].sort_index()
        bench = (bs.reindex(bs.index.union(cum.index)).ffill() / float(base) - 1).reindex(cum.index)
        last[b] = round(float(closes[b].dropna().iloc[-1]), 4)

    series = []
    for ts, v in cum.items():
        row = [ts.strftime("%Y-%m-%dT%H:%M"), round(float(v), 5)]
        if bench is not None:
            bv = bench.get(ts)
            row.append(None if pd.isna(bv) else round(float(bv), 5))
        series.append(row)
    return last, series


def main():
    positions = json.loads(POSITIONS.read_text())
    settings = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
    tickers = sorted({p["ticker"] for p in positions} | ({settings["benchmark"]} if settings.get("benchmark") else set()))
    start = min([p["entryDate"] for p in positions] + ([settings["inception"]] if settings.get("inception") else []))
    # start a few days early so the benchmark has a prior close if needed
    fetch_from = (pd.Timestamp(start) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    closes = fetch_closes(tickers, fetch_from)
    if closes.empty:
        sys.exit("Yahoo Finance returned no data; keeping the previous prices.json")
    last, series = compute(positions, closes, settings)
    OUT.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "sample": False,
        "benchmarkName": settings.get("benchmarkName"),
        "last": last,
        "series": series,
    }, indent=1))
    print(f"Wrote {OUT} with {len(series)} points, {len(last)} tickers")


if __name__ == "__main__":
    main()
