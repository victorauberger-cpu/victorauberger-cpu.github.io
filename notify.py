"""Email the owner about each filled order by opening a GitHub issue that @mentions them.

GitHub sends the mention by email to the address on the GitHub account. Run by the workflow after a fill is saved.
"""
import json
import os
import urllib.request
from pathlib import Path

import pandas as pd

OWNER = "victorauberger-cpu"
LOG = Path("/tmp/fills.jsonl")


def main():
    if not LOG.exists():
        return
    repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"]
    for line in LOG.read_text().splitlines():
        f = json.loads(line)
        ts = pd.Timestamp(f["time"])
        ny, paris = ts.tz_convert("America/New_York"), ts.tz_convert("Europe/Paris")
        verb = ("Sold" if f["side"] == "long" else "Bought back") if f["action"] == "close" else \
               ("Bought" if f["side"] == "long" else "Shorted")
        title = f"Order filled: {verb} {f['ticker']} at {f['price']:g}"
        body = (f"@{OWNER} your order filled.\n\n"
                f"- **{verb} {f['name']} ({f['ticker']})** at **{f['price']:g}** (limit {f['limit']:g}), {f['leverage']}x\n"
                f"- {paris:%A %d %B %Y, %H:%M} Paris ({ny:%H:%M} New York)\n\n"
                f"The trade is on the site: https://victorauberger.com")
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/issues", method="POST",
            data=json.dumps({"title": title, "body": body}).encode(),
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req) as r:
            print("Notified:", title, r.status)


if __name__ == "__main__":
    main()
