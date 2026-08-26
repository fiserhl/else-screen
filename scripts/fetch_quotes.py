#!/usr/bin/env python3
"""Fetch delayed quotes from Twelve Data and write quotes.json.

Credits are charged per symbol, and the free Basic plan allows 800 a day.
Eighteen symbols per run on a 20 minute weekday-daytime cron lands near 490.
Calls are chunked to six symbols and spaced so no single minute spends more
than eight credits, which keeps us clear of the per-minute ceiling too.

Sparklines are built from our own previous runs, not from a time_series
endpoint, so the trend lines cost nothing.
"""
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

KEY = os.environ.get("TWELVE_DATA_KEY", "").strip()
if not KEY:
    sys.exit("TWELVE_DATA_KEY is not set")

OUT = "quotes.json"
CHUNK = 4
GAP_SECONDS = 65
MAX_SPARK = 14

# The Twelve Data Basic plan does not carry index symbols (GSPC, DJI, IXIC,
# RUT all came back empty on 26 Aug 2026), so the index page uses the ETF
# proxies and says so. FALLBACK_INDEXES holds the real symbols in case the
# plan is ever upgraded; swap the two lists if that happens.
GROUPS = [
    ("indexes",     "Major Indexes",          ["SPY", "DIA", "QQQ", "IWM"]),
    ("mississippi", "Mississippi & Regional", ["CALM", "TRMK", "HWC", "ETR", "SO", "FDX"]),
    ("active",      "Most Active",            ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "JPM", "WMT", "CAT"]),
]
FALLBACK_INDEXES = ["GSPC", "DJI", "IXIC", "RUT"]

NAMES = {
    "GSPC": "S&P 500", "DJI": "Dow Jones", "IXIC": "Nasdaq", "RUT": "Russell 2000",
    "SPY": "S&P 500 ETF", "DIA": "Dow ETF", "QQQ": "Nasdaq 100 ETF", "IWM": "Russell 2000 ETF",
    "CALM": "Cal-Maine Foods", "TRMK": "Trustmark", "HWC": "Hancock Whitney",
    "ETR": "Entergy", "SO": "Southern Company", "FDX": "FedEx",
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "AMZN": "Amazon",
    "GOOGL": "Alphabet", "JPM": "JPMorgan Chase", "WMT": "Walmart", "CAT": "Caterpillar",
}

_calls = 0

def api(symbols):
    global _calls
    if _calls:
        time.sleep(GAP_SECONDS)
    _calls += 1
    url = ("https://api.twelvedata.com/quote?symbol=" + ",".join(symbols)
           + "&apikey=" + KEY + "&dp=2")
    req = urllib.request.Request(url, headers={"User-Agent": "else-screen/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    return {symbols[0]: data} if len(symbols) == 1 else data

def quotes_for(symbols):
    bag = {}
    for i in range(0, len(symbols), CHUNK):
        part = symbols[i:i + CHUNK]
        try:
            got = api(part)
        except Exception as e:
            print("chunk failed %s: %s" % (part, e), file=sys.stderr)
            continue
        if isinstance(got, dict) and got.get("status") == "error":
            print("api error: %s" % got.get("message"), file=sys.stderr)
            continue
        bag.update(got)
    return bag

def row_from(sym, q):
    if not isinstance(q, dict) or q.get("status") == "error" or "close" not in q:
        return None
    try:
        pct = float(q.get("percent_change") or 0)
    except ValueError:
        pct = 0.0
    return {
        "symbol": sym,
        "name": NAMES.get(sym) or q.get("name") or sym,
        "price": q.get("close"),
        "change": q.get("change"),
        "percent": q.get("percent_change"),
        "dir": 1 if pct > 0 else (-1 if pct < 0 else 0),
        "marketOpen": q.get("is_market_open") is True,
    }

def main():
    try:
        with open(OUT) as f:
            prev = json.load(f)
    except Exception:
        prev = {}
    prev_spark = {}
    for g in prev.get("groups", []):
        for r in g.get("rows", []):
            prev_spark[r["symbol"]] = r.get("spark") or []

    groups, any_open = [], False
    for key, label, symbols in GROUPS:
        bag = quotes_for(symbols)
        rows = [r for r in (row_from(s, bag.get(s)) for s in symbols) if r]
        proxy = (key == "indexes")
        if key == "indexes" and not rows:
            print("ETF proxies unavailable, trying real index symbols", file=sys.stderr)
            bag = quotes_for(FALLBACK_INDEXES)
            rows = [r for r in (row_from(s, bag.get(s)) for s in FALLBACK_INDEXES) if r]
            proxy = False
        if not rows:
            print("group %s produced nothing, keeping previous" % key, file=sys.stderr)
            old = next((g for g in prev.get("groups", []) if g.get("key") == key), None)
            if old:
                groups.append(old)
            continue
        for r in rows:
            hist = list(prev_spark.get(r["symbol"], []))
            try:
                hist.append(round(float(r["price"]), 4))
            except (TypeError, ValueError):
                pass
            r["spark"] = hist[-MAX_SPARK:]
            any_open = any_open or r["marketOpen"]
        groups.append({"key": key, "label": label, "proxy": proxy, "rows": rows})

    payload = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "marketOpen": any_open,
        "delayNote": "Delayed 15 min",
        "source": "Twelve Data",
        "groups": groups,
    }
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=1)
        f.write("\n")
    print("wrote %s: %d groups, %d calls, marketOpen=%s"
          % (OUT, len(groups), _calls, any_open))

main()
