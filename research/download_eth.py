"""ETH index (5m, from May 2024) and daily ETH option chains (strikes within +/-5% of spot 26 h before expiry)."""
import sys
sys.path.insert(0, ".")
from pathlib import Path
import pandas as pd
from deltabot.client import DeltaClient
from deltabot.data import download_candles, load_candles
from deltabot.option_data import download_expiry, fetch_option_products

client = DeltaClient(); data = Path("data")
idx_path = data / "ETH_index_5m.csv"
if not idx_path.exists():
    download_candles(client, ".DEETHUSD", "5m", pd.Timestamp("2024-05-01", tz="UTC"), pd.Timestamp.now(tz="UTC"), idx_path)
    print("index saved", flush=True)
index = load_candles(idx_path)
prod_path = data / "eth_option_products.csv"
if not prod_path.exists():
    fetch_option_products(client, "ETH").to_csv(prod_path, index=False); print("products saved", flush=True)
products = pd.read_csv(prod_path); products["settlement_time"] = pd.to_datetime(products.settlement_time, utc=True)
exp = sorted(t for t in products.settlement_time.dropna().unique()
             if t.hour == 12 and t.minute == 0 and pd.Timestamp("2024-09-01", tz="UTC") <= t <= pd.Timestamp.now(tz="UTC"))
print(len(exp), "expiries", flush=True)
for n, e in enumerate(exp, 1):
    entry = e - pd.Timedelta(hours=26)
    if entry not in index.index: print("no index", e); continue
    p = download_expiry(client, products, e, float(index.loc[entry, "open"]), data / "eth_options", band=0.05, workers=6)
    print(f"[{n}/{len(exp)}] {e.date()} -> {p}", flush=True)
