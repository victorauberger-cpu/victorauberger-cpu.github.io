"""
Fetches prices from Yahoo Finance (free, via the yfinance library) and writes data/prices.json:
  - the latest price of every ticker in data/positions.json
  - an equal-weighted performance series (in %) of the whole portfolio since inception
  - the S&P 500 (or whichever benchmark is set in data/settings.json) over the same period

Runs automatically on GitHub (see .github/workflows/deploy.yml). You never need to run it yourself,
but you can locally with:  pip install yfinance pandas && python scripts/update_prices.py

Method (money-weighted): on each day, the portfolio line is the total gain in money of all trades so far
divided by the total money put into them, so bigger trades count more. The benchmark line is the same
money put into the S&P 500 on the same buy dates and taken out on the same sell dates. Sizes come from
the private GitHub secret POSITION_SIZES and are never published; only percentages are. A position
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
    """Money-weighted performance.
    Portfolio: total gain in money / total money invested in the trades opened so far.
    Benchmark: the same money put into the benchmark on the same buy dates and taken out on the same sell dates."""
    settings = settings or {}
    start = pd.Timestamp(settings.get("inception") or min(p["entryDate"] for p in positions))
    b = settings.get("benchmark")
    bs = closes[b].dropna() if b and b in closes.columns else None

    last, paths = {}, []
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

        e = float(p["entry"])
        lev = float(p.get("leverage") or 1)
        raw = path / e - 1 if p["side"].lower() != "short" else (e - path) / e
        size = float(p.get("weight") or 1)
        pnl = (size * (lev * raw).clip(lower=-1))          # money gained or lost, never more than the stake
        paths.append((entry, exit_, size, pnl))

    idx = closes.index[closes.index >= start].union(pd.DatetimeIndex([start]))
    for entry, exit_, _, pnl in paths:
        idx = idx.union(pnl.index)
    idx = idx[idx >= start]

    tot_pnl = pd.Series(0.0, index=idx)
    tot_inv = pd.Series(0.0, index=idx)
    tot_bench = pd.Series(0.0, index=idx)
    bfull = bs.reindex(bs.index.union(idx)).ffill() if bs is not None else None
    for entry, exit_, size, pnl in paths:
        live = idx >= entry
        tot_inv[live] += size
        tot_pnl += pnl.reindex(idx).ffill().fillna(0.0).where(live, 0.0)
        if bfull is not None:
            prior = bs[bs.index < entry]
            if not len(prior):
                continue
            base = float(prior.iloc[-1])
            level = bfull.reindex(idx)
            if exit_ is not None:
                level = level.where(idx <= exit_)   # frozen after the sale
                level = level.ffill()
            tot_bench += (size * (level / base - 1)).fillna(0.0).where(live, 0.0)

    port = (tot_pnl / tot_inv).where(tot_inv > 0, 0.0)
    bench = (tot_bench / tot_inv).where(tot_inv > 0, 0.0) if bfull is not None else None
    if b and bs is not None and len(bs):
        last[b] = round(float(bs.iloc[-1]), 4)

    series = []
    for ts in idx:
        row = [ts.strftime("%Y-%m-%dT%H:%M"), round(float(port[ts]), 5)]
        if bench is not None:
            row.append(round(float(bench[ts]), 5))
        series.append(row)
    return last, series


def apply_private_sizes(positions):
    """Position sizes live in the private GitHub secret POSITION_SIZES, never in the public files.
    Format: {"LDOS 2024-01-30": 8.3, "NVDA 2024-02-26": 4.1, ...} (any unit, e.g. thousands of euros).
    Trades without a size get the median size, i.e. they count as a typical position."""
    import os
    raw = os.environ.get("POSITION_SIZES", "").strip()
    sizes = {}
    if raw:
        try:
            sizes = {k.strip(): float(v) for k, v in json.loads(raw).items()}
        except Exception:
            print("POSITION_SIZES is not valid JSON; using equal sizes")
    if not sizes:
        return
    typical = float(pd.Series(list(sizes.values())).median())
    found = 0
    for p in positions:
        s = sizes.get(f'{p["ticker"]} {p["entryDate"]}')
        if s is not None:
            found += 1
        p["weight"] = s if s is not None else typical
    print(f"Private sizes applied to {found} of {len(positions)} trades")  # counts only, never the sizes


def main():
    positions = json.loads(POSITIONS.read_text())
    apply_private_sizes(positions)
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
