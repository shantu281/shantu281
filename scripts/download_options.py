"""Download real BTC option prices from Delta Exchange India (run on a machine that can reach Delta).

    python scripts/download_options.py --start 2025-09-01 --end 2025-09-30     # try one month first
    python scripts/download_options.py --start 2024-09-01                      # everything

Safe to stop and re-run: finished days are skipped.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deltabot.client import DeltaAPIError, DeltaClient  # noqa: E402
from deltabot.data import download_candles, load_candles  # noqa: E402
from deltabot.option_data import download_expiry, fetch_option_products  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2024-09-01")
    p.add_argument("--end", default=None)
    p.add_argument("--band", type=float, default=0.05, help="strikes within spot +/- this fraction")
    p.add_argument("--price", choices=["mark", "trade"], default="mark")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--data", default="data")
    a = p.parse_args()

    data = Path(a.data)
    start = pd.Timestamp(a.start, tz="UTC")
    end = pd.Timestamp(a.end, tz="UTC") if a.end else pd.Timestamp.now(tz="UTC").floor("D")
    client = DeltaClient()

    # 1) BTC index, 5-minute (used for spot, strike choice and settlement)
    index_path = data / "BTC_index_5m.csv"
    if not index_path.exists():
        print("downloading BTC index candles...")
        for sym in (".DEXBTUSD", "BTCUSD"):
            try:
                download_candles(client, sym, "5m", start - pd.Timedelta(days=10), end + pd.Timedelta(days=1),
                                 index_path)
                print(f"  saved {sym} -> {index_path}")
                break
            except (DeltaAPIError, RuntimeError) as e:
                print(f"  {sym} failed: {e}")
        else:
            sys.exit("could not download the BTC index")
    index = load_candles(index_path)

    # 2) list of all BTC options
    products_path = data / "btc_option_products.csv"
    if not products_path.exists():
        print("listing BTC options (takes a minute or two)...")
        fetch_option_products(client).to_csv(products_path, index=False)
    products = pd.read_csv(products_path, parse_dates=["settlement_time"])
    products["settlement_time"] = pd.to_datetime(products["settlement_time"], utc=True)

    # 3) one chain file per daily 12:00 UTC expiry
    out_dir = data / "options"
    expiries = sorted(t for t in products["settlement_time"].dropna().unique()
                      if t.hour == 12 and t.minute == 0 and start <= t <= end)
    print(f"{len(expiries)} expiries from {start.date()} to {end.date()}")
    for n, expiry in enumerate(expiries, 1):
        entry = expiry - pd.Timedelta(hours=26)
        if entry not in index.index:
            print(f"[{n}/{len(expiries)}] {expiry.date()} no index price, skipped")
            continue
        path = download_expiry(client, products, expiry, float(index.loc[entry, "open"]), out_dir,
                               band=a.band, price=a.price, workers=a.workers)
        print(f"[{n}/{len(expiries)}] {expiry.date()} -> {path or 'no data'}")


if __name__ == "__main__":
    main()
