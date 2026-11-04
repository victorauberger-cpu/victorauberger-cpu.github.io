# Victor Auberger: personal site

## What to edit

| To change… | Edit this file |
|---|---|
| Your trades (add, close, remove) | `data/positions.json` |
| Bio, contact links, page text | `index.html` (the HTML near the top) |
| Research papers, recommendations | `index.html` (the block marked `EDIT YOUR CONTENT HERE`) |
| Benchmark (S&P 500) and its start level | `data/settings.json` |
| Paper PDFs | upload them into the `papers/` folder, e.g. `papers/paper-1.pdf` |

**Don't edit** `data/prices.json`. It's rewritten automatically from Yahoo Finance.

### Adding a trade (`data/positions.json`)
Copy a line, change the values, and keep the comma between lines:
```json
{"ticker": "NVDA", "name": "Nvidia", "side": "long", "entryDate": "2026-11-04", "entry": 140.10, "exitDate": "", "exit": null, "thesis": "Short reason"}
```
- `ticker` must be the **Yahoo Finance** symbol: `AAPL`, `MC.PA` (Paris), `SAP.DE` (Xetra), `VOD.L` (London)…
- `side`: `"long"` or `"short"`
- Dates are `YYYY-MM-DD`. Leave `"exitDate": ""` and `"exit": null` while the position is open.
- **Closing a trade:** fill in `exitDate` and `exit`.

### Editing on github.com (no software needed)
1. Open the file in your repository and click the ✏️ pencil icon.
2. Make the change, then click **Commit changes**.
3. About a minute later the site updates by itself.

## How prices update
`.github/workflows/deploy.yml` runs `scripts/update_prices.py` on GitHub's servers every 30 minutes on weekdays
(07:00–21:00 UTC), plus every time you commit a change. It downloads prices from Yahoo Finance and rebuilds the site.
You can also trigger it from the **Actions** tab → *Update prices & deploy* → **Run workflow**.

Prices are delayed (Yahoo's free data is ~15 min behind, plus up to 30 min between updates).
The chart weights each position by its "weight" (its % of the money invested at the time; amounts are never stored). Leave it out and positions count equally.
