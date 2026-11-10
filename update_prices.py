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


# ---------------- Paper fund (fund.json → fund_nav.json) ----------------
FUND_IN = DATA / "fund.json"
FUND_OUT = DATA / "fund_nav.json"


def update_fund():
    """Daily NAV of the paper long/short fund, benchmarked to cash.
    Sizes are kept as fractions of NAV (no euro amounts are published). Each position holds a fixed number of
    shares from entry: P&L in euros = shares x price change / unit / today's FX (the position is financed in its own
    currency, so only the P&L carries currency risk). Running costs (financing, borrow, dividends, trading, data)
    are accrued daily at the rate modelled in the workbook."""
    import numpy as np
    if not FUND_IN.exists():
        return
    F = json.loads(FUND_IN.read_text())
    P = [p for p in F["positions"] if p.get("entry")]
    start = pd.Timestamp(F["start"])
    fxmap = F.get("fx", {})
    tickers = sorted({p["yahoo"] for p in P} | set(fxmap.values()))
    closes = fetch_closes(tickers, (start - pd.Timedelta(days=10)).strftime("%Y-%m-%d"))
    if closes.empty:
        print("Fund: no prices from Yahoo; keeping the previous fund_nav.json")
        return
    idx = closes.index[closes.index >= start - pd.Timedelta(days=5)]
    base = start - pd.Timedelta(minutes=1)          # the book starts from the close before the first day
    days = [base] + [d for d in idx if d >= start]
    C = closes.reindex(closes.index.union(days)).sort_index().ffill()

    def fx(ccy, t):
        if ccy == "EUR" or ccy not in fxmap or fxmap[ccy] not in C.columns:
            return 1.0
        v = C[fxmap[ccy]].asof(t)
        return float(v) if pd.notna(v) else 1.0

    R = F.get("rules", {})
    rows, pnl_by, val_by = [], {}, {}
    for p in P:
        y, side = p["yahoo"], (1 if p["side"] == "long" else -1)
        unit, ccy, e = float(p.get("unit") or 1), p.get("currency", "EUR"), float(p["entry"])
        ed = pd.Timestamp(p["entryDate"])
        xd = pd.Timestamp(p["exitDate"]) + EOD if p.get("exitDate") and p.get("exit") is not None else None
        s = C[y].dropna() if y in C.columns else pd.Series(dtype=float)
        first = s[s.index >= ed]
        if len(first) and abs(first.iloc[0] / e - 1) > 0.25:   # Yahoo listed in another unit / currency
            print(f"Fund: {p['id']} {y} Yahoo price {first.iloc[0]:.4g} far from entry {e}; rescaling")
            s = s * (e / first.iloc[0])
        fx0 = fx(ccy, ed - pd.Timedelta(minutes=1))
        sh = p["weight"] * fx0 * unit / e                 # local shares per 1.0 of starting NAV
        prev, path, vals = e, [], []
        for t in days:
            if t < ed or (xd is not None and t > xd):
                path.append(0.0); vals.append(0.0); continue
            px = float(p["exit"]) if xd is not None and t >= xd else (float(s.asof(t)) if len(s) and pd.notna(s.asof(t)) else prev)
            path.append(side * sh * (px - prev) / unit / fx(ccy, t))
            vals.append(0.0 if xd is not None and t >= xd else sh * px / unit / fx(ccy, t))
            prev = px
        pnl = np.array(path)
        pnl_by[p["id"]] = pnl
        val_by[p["id"]] = np.array(vals)
        last_px = prev
        live = xd is None
        value = sh * last_px / unit / fx(ccy, days[-1]) if live else 0.0
        ret = side * (last_px / e - 1)
        ml = R.get("maxLossLong", .015) if side == 1 else R.get("maxLossShort", .0125)
        stop = None if p["type"] == "future" else (p.get("stop") or e * (1 - side * ml / p["weight"]))
        rows.append({"id": p["id"], "last": round(last_px, 6), "ret": round(ret, 5),
                     "contrib": round(float(pnl.sum()), 6), "value": round(value, 5), "stop": round(stop, 6) if stop else None,
                     "toStop": round(side * (last_px / stop - 1), 5) if live and stop else None,
                     "stopHit": bool(live and stop and side * (last_px - stop) <= 0), "open": live})

    n = len(days)
    tot = sum(pnl_by.values()) if pnl_by else np.zeros(n)
    yrs = np.array([(t - base).total_seconds() / (365.25 * 86400) for t in days])
    cost = -F.get("runningCost", 0.0264) * yrs
    nav = 1 + np.cumsum(tot) + cost
    cash = (1 + F.get("cashRate", 0.025)) ** yrs
    beta_t = sum(((1 if p["side"] == "long" else -1) * p.get("beta", 1) * val_by[p["id"]] for p in P), np.zeros(n)) / nav
    gross_t = sum((val_by[p["id"]] for p in P), np.zeros(n)) / nav
    peak = np.maximum.accumulate(nav)
    dd = nav / peak - 1

    pairs = {}
    for p in P:
        pairs.setdefault(p["pair"], 0.0)
        pairs[p["pair"]] += float(pnl_by[p["id"]].sum())
    pairs["Costs"] = float(cost[-1])

    # Exposure now (positions marked to market, as a fraction of current NAV)
    by_id = {r["id"]: r for r in rows}
    sgn = {p["id"]: (1 if p["side"] == "long" else -1) for p in P}
    navN = float(nav[-1])
    gross = sum(by_id[p["id"]]["value"] for p in P) / navN
    longx = sum(by_id[p["id"]]["value"] for p in P if sgn[p["id"]] == 1) / navN
    shortx = sum(by_id[p["id"]]["value"] for p in P if sgn[p["id"]] == -1) / navN
    beta = sum(sgn[p["id"]] * by_id[p["id"]]["value"] * p.get("beta", 1) for p in P) / navN
    eu = [p for p in P if p.get("region") in ("EU", "UK", "CH") and p["type"] != "future"]
    eu_beta = sum(sgn[p["id"]] * by_id[p["id"]]["value"] * p.get("beta", 1) for p in eu) / navN
    hedge_beta = sum(sgn[p["id"]] * by_id[p["id"]]["value"] * p.get("beta", 1) for p in P if p["type"] == "future") / navN
    for r in rows:
        r["weightNow"] = round(r["value"] / navN, 5)
        del r["value"]

    # Did the hedge do its job? Daily P&L of the European stocks vs the future.
    eu_d = sum((pnl_by[p["id"]] for p in eu), np.zeros(n))
    h_d = sum((pnl_by[p["id"]] for p in P if p["type"] == "future"), np.zeros(n))
    hedge_stats = None
    m = (np.abs(eu_d) + np.abs(h_d)) > 0
    if m.sum() >= 10:
        a, b = eu_d[m], h_d[m]
        hedge_stats = {"days": int(m.sum()), "corr": round(float(np.corrcoef(a, b)[0, 1]), 3),
                       "volBefore": round(float(a.std() * np.sqrt(252)), 5), "volAfter": round(float((a + b).std() * np.sqrt(252)), 5),
                       "downDays": int((a < 0).sum()), "offsetOnDownDays": round(float(-b[a < 0].sum() / -a[a < 0].sum()), 3) if (a < 0).any() and a[a < 0].sum() else None}

    status = "OK"
    if dd[-1] <= R.get("ddClose", -0.075):
        status = "CLOSE"
    elif dd[-1] <= R.get("ddHalve", -0.05):
        status = "HALVE"
    FUND_OUT.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        # [time, fund return, cash return, net beta, gross leverage]
        "series": [[t.isoformat(timespec="minutes"), round(float(v - 1), 6), round(float(c - 1), 6), round(float(b), 4), round(float(g), 3)]
                   for t, v, c, b, g in zip(days, nav, cash, beta_t, gross_t)],
        "positions": rows,
        "attribution": {k: round(v, 6) for k, v in pairs.items()},
        "exposure": {"gross": round(gross, 4), "long": round(longx, 4), "short": round(shortx, 4), "net": round(longx - shortx, 4),
                     "beta": round(beta, 4), "euBeta": round(eu_beta, 4), "hedgeBeta": round(hedge_beta, 4)},
        "drawdown": round(float(dd[-1]), 5), "maxDrawdown": round(float(dd.min()), 5), "status": status,
        "hedge": hedge_stats,
    }, separators=(",", ":")))
    print(f"Fund: NAV {nav[-1] - 1:+.2%} vs cash {cash[-1] - 1:+.2%} over {n - 1} days; gross {gross:.2f}x, beta {beta:+.3f}")


def main():
    try:
        update_kalshi()
    except Exception as e:   # never let Kalshi break the price update
        print(f"Kalshi update failed: {e}")
    try:
        update_fund()
    except Exception as e:   # never let the fund break the price update
        print(f"Fund update failed: {e}")
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
