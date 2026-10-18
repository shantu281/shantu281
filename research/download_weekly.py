"""Download Friday-expiry BTC options for the 7 days before expiry (strikes within +/-10% of spot then)."""
import sys
sys.path.insert(0, ".")
from pathlib import Path
import pandas as pd
from deltabot.client import DeltaClient
from deltabot.data import load_candles
from deltabot.option_data import download_expiry

client = DeltaClient()
index = load_candles("data/BTC_index_5m.csv")
products = pd.read_csv("data/btc_option_products.csv"); products["settlement_time"] = pd.to_datetime(products.settlement_time, utc=True)
exp = sorted(t for t in products.settlement_time.dropna().unique()
             if t.dayofweek == 4 and t.hour == 12 and pd.Timestamp("2024-09-06", tz="UTC") <= t <= pd.Timestamp("2026-10-16", tz="UTC"))
print(len(exp), "Friday expiries", flush=True)
for n, e in enumerate(exp, 1):
    entry = e - pd.Timedelta(hours=7 * 24)
    if entry not in index.index: print("no index", e); continue
    p = download_expiry(client, products, e, float(index.loc[entry, "open"]), Path("data/options_weekly"),
                        band=0.10, hours_before=7 * 24 + 2, workers=6)
    print(f"[{n}/{len(exp)}] {e.date()} -> {p}", flush=True)
