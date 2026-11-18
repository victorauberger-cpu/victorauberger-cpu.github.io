"""Pending limit orders for the portfolio page.

Reads orders.json. For every open order it downloads Yahoo Finance 5-minute bars *including pre-market and
after-hours trading* since the order was placed. When the price touches the limit, the order is marked as
filled and the position is added to positions.json:

  - buy (long):  fills when a bar trades at or below the limit
  - sell short:  fills when a bar trades at or above the limit

The fill price is the limit, or the bar's opening price if the market gapped through the limit.
A fill during after-hours trading is dated the next weekday, so the site starts tracking it from the next
session instead of comparing it with a regular close that happened before the fill.

This only records trades on the website. It does not send any order to a broker.
"""
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


def fill_date(ts_et):
    """US date of the fill; after-hours fills (16:00 ET or later) count from the next weekday."""
    d = ts_et.normalize()
    if ts_et.hour >= 16:
        d += pd.Timedelta(days=1)
        while d.weekday() >= 5:
            d += pd.Timedelta(days=1)
    return d.strftime("%Y-%m-%d")


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
        if o.get("expires") and now > pd.Timestamp(o["expires"]).tz_localize(ET) + pd.Timedelta(hours=20):
            o["status"] = "expired"
            changed = True
            print(f"Order expired: {o['side']} {o['ticker']} at {o['limit']}")
            continue
        try:
            bars = bars_since(o["ticker"], pd.Timestamp(o["created"]))
        except Exception as e:
            print(f"Could not check {o['ticker']}: {e}")
            continue
        if bars.empty:
            continue
        lim, short = float(o["limit"]), o["side"] == "short"
        hit = bars[bars["High"] >= lim] if short else bars[bars["Low"] <= lim]
        if hit.empty:
            print(f"Waiting: {o['side']} {o['ticker']} at {lim} (last {float(bars['Close'].iloc[-1]):.2f})")
            continue
        ts, bar = hit.index[0], hit.iloc[0]
        price = max(lim, float(bar["Open"])) if short else min(lim, float(bar["Open"]))
        price = round(price, 4)
        o.update(status="filled", fillPrice=price, fillTime=ts.isoformat())
        positions.append({
            "ticker": o["ticker"], "name": o.get("name", o["ticker"]), "side": o["side"],
            "entryDate": fill_date(ts), "entry": price, "exitDate": "", "exit": None,
            "leverage": o.get("leverage", 1), "thesis": o.get("thesis", ""),
        })
        changed = True
        print(f"FILLED: {o['side']} {o['ticker']} at {price} ({ts:%Y-%m-%d %H:%M} ET)")
    if changed:
        ORDERS.write_text("[\n" + ",\n".join("  " + json.dumps(x, ensure_ascii=False) for x in orders) + "\n]\n")
        POSITIONS.write_text("[\n" + ",\n".join("  " + json.dumps(x, ensure_ascii=False) for x in positions) + "\n]\n")


if __name__ == "__main__":
    main()
