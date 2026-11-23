"""Pending limit orders for the portfolio page.

Reads orders.json. For every open order it downloads Yahoo Finance 5-minute bars *including pre-market and
after-hours trading* since the order was placed. When the price touches the limit, the order is marked as
filled and the position is added to positions.json:

  - open a long  / close a short (buying):  fills when the price trades at or below the limit
  - open a short / close a long  (selling): fills when the price trades at or above the limit

Stop orders ("type": "stop", with "stop" instead of "limit") work the other way round: a stop that sells
(closing a long) triggers when the price trades at or below the stop, and fills at the stop, or at the bar's
opening price if the market gapped below it. A stop that buys (closing a short) triggers at or above the stop.

Order fields: ticker, name, side ("long"/"short"), action ("open", default, or "close"), limit, leverage,
thesis, created (UTC time the order was placed), optional expires. Orders without "expires" stay open
until filled or cancelled. Checked in every session: pre-market, regular, after-hours and overnight.

The fill price is the limit, or the bar's opening price if the market gapped through the limit.
A fill during after-hours trading is dated the next weekday, so the site starts tracking it from the next
session instead of comparing it with a regular close that happened before the fill.

Overnight session (Blue Ocean ATS, 20:00–04:00 New York time): Yahoo's chart data does not include it, so the
live overnight price shown on the Yahoo quote page is read at each run instead. Overnight fills are therefore
checked every 15 minutes on that snapshot price, not on every trade.

This only records trades on the website. It does not send any order to a broker.
"""
import re
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
ORDERS = HERE / "orders.json"
POSITIONS = HERE / "positions.json"
ET = "America/New_York"


def bars_since(ticker, since_utc):
    df = yf.download(ticker, period="5d", interval="5m", prepost=True, progress=False, auto_adjust=False)
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    idx = df.index if df.index.tz is not None else df.index.tz_localize("UTC")
    df.index = idx.tz_convert(ET)
    return df[df.index >= since_utc.tz_convert(ET)]


def overnight_price(ticker):
    """Latest overnight-session price from the Yahoo quote page, or None outside the overnight session."""
    url = f"https://finance.yahoo.com/quote/{ticker}/"
    try:
        from curl_cffi import requests as creq                      # installed with yfinance; looks like a browser
        html = creq.get(url, impersonate="chrome", timeout=30).text
    except Exception:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36"})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    html = html.replace('\\"', '"')
    m = re.search(r'qsp-overnight-price"[^>]*>\s*([\d,\.]+)\s*<', html)
    if not m:
        ids = sorted(set(re.findall(r'data-testid="(qsp-[a-z-]*price)"', html)))
        print(f"Overnight price not found for {ticker}; price fields on page: {ids}")
    return float(m.group(1).replace(",", "")) if m else None


def in_overnight(now_utc):
    t = now_utc.tz_convert(ET)
    return t.hour >= 20 or t.hour < 4


def fill_date(ts_et):
    """US date of the fill; after-hours fills (16:00 ET or later) count from the next weekday."""
    d = ts_et.normalize()
    if ts_et.hour >= 16:
        d += pd.Timedelta(days=1)
        while d.weekday() >= 5:
            d += pd.Timedelta(days=1)
    return d.strftime("%Y-%m-%d")


FILL_LOG = Path("/tmp/fills.jsonl")      # read by notify.py, which emails each fill (via a GitHub issue)


def log_fill(o, price, ts):
    with FILL_LOG.open("a") as f:
        f.write(json.dumps({"ticker": o["ticker"], "name": o.get("name", o["ticker"]), "side": o["side"],
                            "action": o.get("action", "open"), "limit": o.get("stop", o.get("limit")),
                            "price": price, "leverage": o.get("leverage", 1), "time": ts.isoformat()}) + "\n")


def apply_fill(o, price, ts, positions):
    """Record a filled order. Opening orders add a position; closing orders fill in the exit of the open one."""
    if o.get("action", "open") == "close":
        match = [p for p in positions if p["ticker"] == o["ticker"] and p["side"] == o["side"] and not p.get("exitDate")]
        if not match:
            o["status"] = "rejected"
            print(f"No open {o['side']} {o['ticker']} position to close")
            return False
        pos = match[-1]
        pos["exitDate"] = ts.strftime("%Y-%m-%d")       # exits keep the New York date of the fill
        pos["exit"] = price
    else:
        positions.append({
            "ticker": o["ticker"], "name": o.get("name", o["ticker"]), "side": o["side"],
            "entryDate": fill_date(ts), "entry": price, "exitDate": "", "exit": None,
            "leverage": o.get("leverage", 1), "thesis": o.get("thesis", ""),
        })
    o.update(status="filled", fillPrice=price, fillTime=ts.isoformat())
    return True


def main():
    if not ORDERS.exists():
        return
    orders = json.loads(ORDERS.read_text())
    open_orders = [o for o in orders if o.get("status", "open") == "open"]
    if not open_orders:
        return
    positions = json.loads(POSITIONS.read_text())
    now = pd.Timestamp.now(tz="UTC")
    changed = False
    for o in open_orders:
        closing = o.get("action", "open") == "close"
        # does this order fill when the price rises to the limit (selling) or falls to it (buying)?
        sells = (o["side"] == "short") != closing
        stop = o.get("type") == "stop"
        lim = float(o["stop"] if stop else o["limit"])
        # limit orders fill when the price moves in your favour to the level; stops when it moves against you
        up = sells != stop                      # True: triggers when the price rises to the level
        what = f"{'close' if closing else 'open'} {o['side']} {o['ticker']} {'stop' if stop else 'limit'} {lim}"
        exp = pd.Timestamp(o["expires"]) if o.get("expires") else None
        if exp is not None and exp.tzinfo is None:
            exp = exp.tz_localize(ET)
        try:
            bars = bars_since(o["ticker"], pd.Timestamp(o["created"]))
        except Exception as e:
            print(f"Could not check {o['ticker']}: {e}")
            bars = pd.DataFrame()
        if exp is not None and len(bars):
            bars = bars[bars.index < exp.tz_convert(ET)]
        # Trigger on 5-minute closing prices: Yahoo's bar highs and lows include stray prints that brokers don't show.
        # Outside regular hours (thin volume) Yahoo keeps stray prints that brokers' charts filter out, so there
        # the level must hold for two 5-minute closes in a row before the order counts as filled.
        if len(bars):
            cond = (bars["Close"] >= lim) if up else (bars["Close"] <= lim)
            mins = bars.index.hour * 60 + bars.index.minute
            regular = (mins >= 570) & (mins < 960)
            if "." in o["ticker"]:              # non-US listing: Yahoo only has its regular session
                regular = regular | True
            cond = cond & (regular | cond.shift(1, fill_value=False))
            hit = bars[cond]
        else:
            hit = bars
        if len(hit):
            ts, bar = hit.index[0], hit.iloc[0]
            price = round(max(lim, float(bar["Open"])) if up else min(lim, float(bar["Open"])), 4)  # gap through: open
            if apply_fill(o, price, ts, positions):
                print(f"FILLED: {what} -> {price} ({ts:%Y-%m-%d %H:%M} ET)")
                log_fill(o, price, ts)
            changed = True
            continue
        if in_overnight(now) and (exp is None or now < exp):
            try:
                px = overnight_price(o["ticker"])
            except Exception as e:
                px = None
                print(f"Could not read overnight price for {o['ticker']}: {e}")
            if px is not None and ((px >= lim) if up else (px <= lim)):
                ts = now.tz_convert(ET).floor("min")
                if apply_fill(o, px, ts, positions):
                    print(f"FILLED overnight: {what} -> {px} ({ts:%Y-%m-%d %H:%M} ET)")
                    log_fill(o, px, ts)
                changed = True
                continue
            if px is not None:
                print(f"Waiting (overnight price {px}): {what}")
        if exp is not None and now >= exp:
            o["status"] = "expired"
            changed = True
            print(f"Expired unfilled: {what}")
        elif len(bars):
            print(f"Waiting (last {float(bars['Close'].iloc[-1]):.2f}): {what}")
    if changed:
        ORDERS.write_text("[\n" + ",\n".join("  " + json.dumps(x, ensure_ascii=False) for x in orders) + "\n]\n")
        POSITIONS.write_text("[\n" + ",\n".join("  " + json.dumps(x, ensure_ascii=False) for x in positions) + "\n]\n")


if __name__ == "__main__":
    main()
