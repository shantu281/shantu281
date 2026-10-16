"""Download BTC candles from Delta Exchange India.

    python scripts/download_data.py --symbol BTCUSD --resolution 1h --start 2023-01-01
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deltabot.client import DeltaClient  # noqa: E402
from deltabot.data import download_candles  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="BTCUSD", help="BTCUSD perpetual, or .DEXBTUSD for the index")
    p.add_argument("--resolution", default="1h")
    p.add_argument("--start", default="2023-01-01")
    p.add_argument("--end", default=None)
    p.add_argument("--out", default=None)
    a = p.parse_args()

    start = pd.Timestamp(a.start, tz="UTC")
    end = pd.Timestamp(a.end, tz="UTC") if a.end else pd.Timestamp.now(tz="UTC").floor("h")
    out = Path(a.out or f"data/{a.symbol.strip('.')}_{a.resolution}.csv")
    df = download_candles(DeltaClient(), a.symbol, a.resolution, start, end, out)
    print(f"saved {len(df)} candles {df.index[0]} .. {df.index[-1]} -> {out}")


if __name__ == "__main__":
    main()
