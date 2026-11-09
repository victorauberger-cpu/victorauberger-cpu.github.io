"""
Fetches prices from Yahoo Finance (free, via the yfinance library) and writes data/prices.json:
  - the latest price of every ticker in data/positions.json
  - an equal-weighted performance series (in %) of the whole portfolio since inception
  - the S&P 500 (or whichever benchmark is set in data/settings.json) over the same period

Runs automatically on GitHub (see .github/workflows/deploy.yml). You never need to run it yourself,
but you can locally with:  pip install yfinance pandas && python scripts/update_prices.py

Method: each day, the open positions' gains weighted by their size (sizes come from the private
GitHub secret POSITION_SIZES and are never published). On days with no open position, the money is
assumed to sit in the S&P 500. The benchmark line is the S&P 500 held throughout. A position
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
    """Time-weighted performance, as funds report it.
    Each day: the gain of the open positions, weighted by their size, divided by what they were worth that
    morning. On days with no open position the money is assumed to sit in the benchmark (S&P 500).
    The benchmark line is the S&P 500 held throughout."""
    settings = settings or {}
    start = pd.Timestamp(settings.get("inception") or min(p["entryDate"] for p in positions))
    b = settings.get("benchmark")
    bs = closes[b].dropna() if b and b in closes.columns else None

    last, legs = {}, []
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
        value = (1 + lev * raw).clip(lower=1e-6)       # 1 unit put into the trade
        w = float(p.get("weight") or 1)
        key = t + "_" + p["entryDate"]
        legs.append(((w * value.shift(1)).dropna().rename(key), (w * value.diff()).dropna().rename(key)))

    idx = closes.index[closes.index >= start].union(pd.DatetimeIndex([start]))
    for v, g in legs:
        idx = idx.union(v.index)
    idx = idx[idx >= start]

    if legs:
        V = pd.concat([v for v, _ in legs], axis=1).reindex(idx)
        G = pd.concat([g for _, g in legs], axis=1).reindex(idx)
        den = V.sum(axis=1, min_count=1)
        held = den > 0
        r_port = (G.sum(axis=1, min_count=1) / den).where(held)
    else:
        held = pd.Series(False, index=idx)
        r_port = pd.Series(float("nan"), index=idx)

    bench = None
    if bs is not None and len(bs):
        base = settings.get("benchmarkAtInception")
        if base is None:
            prior = bs[bs.index < start]
            base = float(prior.iloc[-1]) if len(prior) else float(bs.iloc[0])
        level = bs.reindex(bs.index.union(idx)).ffill().reindex(idx)
        level.iloc[0] = float(base) if pd.isna(level.iloc[0]) or idx[0] == start else level.iloc[0]
        level = level.ffill()
        r_bench = level.pct_change().fillna(0.0)
        bench = level / float(base) - 1
        last[b] = round(float(bs.iloc[-1]), 4)
        r_port = r_port.where(held, r_bench)            # idle money sits in the S&P 500
    port = (1 + r_port.fillna(0.0)).cumprod() - 1

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


# ---------------- Live Kalshi snapshot (for the prediction-markets paper on the Research page) ----------------
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_OUT = DATA / "kalshi.json"


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def update_kalshi(max_pages=120, budget_s=120):
    """Scans Kalshi's open events (public API, no key) and writes kalshi.json with the most-traded live
    markets plus the share of the last 24h of contracts traded in each category."""
    import time
    import urllib.parse
    import urllib.request

    t0, cursor, pages = time.time(), "", 0
    by_cat, markets, scanned = {}, [], 0
    while pages < max_pages and time.time() - t0 < budget_s:
        q = {"status": "open", "with_nested_markets": "true", "limit": "200"}
        if cursor:
            q["cursor"] = cursor
        req = urllib.request.Request(f"{KALSHI_API}/events?" + urllib.parse.urlencode(q),
                                     headers={"User-Agent": "personal-site-updater", "Accept": "application/json"})
        data = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.load(r)
                break
            except Exception as e:
                print(f"Kalshi page {pages} attempt {attempt + 1} failed: {e}")
                time.sleep(2 * (attempt + 1))
        if data is None:
            break
        pages += 1
        for ev in data.get("events") or []:
            cat = ev.get("category") or "Other"
            ms = ev.get("markets") or []
            for m in ms:
                if m.get("status") != "active":
                    continue
                scanned += 1
                vol = _num(m.get("volume_24h_fp", m.get("volume_24h")))
                by_cat[cat] = by_cat.get(cat, 0.0) + vol
                if vol <= 0 or m.get("ticker", "").startswith("KXMVE"):
                    continue   # skip dead markets and auto-generated parlay combos
                bid, ask = _num(m.get("yes_bid_dollars")), _num(m.get("yes_ask_dollars"))
                last = _num(m.get("last_price_dollars"))
                p = (bid + ask) / 2 if bid > 0 and ask > 0 and ask - bid <= 0.10 else last
                if not 0.03 <= p <= 0.97:
                    continue   # near-certain outcomes are dull to show
                title, sub = (m.get("title") or ev.get("title") or "").strip(), (m.get("yes_sub_title") or "").strip()
                if len(ms) > 1 and sub:
                    question, outcome = (ev.get("title") or title).strip(), sub
                else:
                    question, outcome = title, ""
                markets.append({"ev": ev.get("event_ticker"),
                    "q": question, "o": outcome, "p": round(p, 3), "chg": round(p - _num(m.get("previous_price_dollars")), 3)
                    if _num(m.get("previous_price_dollars")) > 0 else None,
                    "v24": round(vol), "cat": cat, "close": m.get("close_time"),
                    "url": "https://kalshi.com/markets/" + (ev.get("series_ticker") or m.get("event_ticker", "")).lower(),
                })
        cursor = data.get("cursor") or ""
        if not cursor:
            break
        time.sleep(0.1)
    if scanned == 0:
        print("Kalshi: nothing fetched; keeping the previous kalshi.json")
        return
    markets.sort(key=lambda x: -x["v24"])
    seen, top = set(), []
    for m in markets:              # one market per event, so the random pick varies
        if m["ev"] not in seen:
            seen.add(m["ev"])
            top.append({k: v for k, v in m.items() if k != "ev"})
    total = sum(by_cat.values())
    KALSHI_OUT.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "complete": not cursor,             # False if the scan stopped before the last page
        "marketsScanned": scanned,
        "volume24h": round(total),
        "byCategory": sorted([[c, round(v)] for c, v in by_cat.items() if v > 0], key=lambda x: -x[1]),
        "markets": top[:150],
    }, separators=(",", ":")))
    print(f"Kalshi: {scanned} markets on {pages} pages, {len(top)} live events, wrote {KALSHI_OUT.name}")


def main():
    try:
        update_kalshi()
    except Exception as e:   # never let Kalshi break the price update
        print(f"Kalshi update failed: {e}")
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
