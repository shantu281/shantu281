"""Compare the strategies on real Delta option prices downloaded by download_options.py.

    python scripts/run_real_backtest.py
    python scripts/run_real_backtest.py --start 2025-01-01 --hours-before 6
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deltabot.backtest import monthly, summarise, trades_frame  # noqa: E402
from deltabot.data import load_candles  # noqa: E402
from deltabot.real_backtest import RealConfig, run_real_backtest  # noqa: E402
from deltabot.strategies import default_strategies  # noqa: E402

LOT_BTC = 0.001  # contract_value of Delta India BTC options (checked on the live API, 17 Oct 2026)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data")
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--strategies", nargs="*", default=None)
    p.add_argument("--lots", type=int, default=100, help="lots per leg (Delta BTC option lot = 0.001 BTC)")
    p.add_argument("--hours-before", type=float, default=24.0, help="enter this many hours before expiry")
    p.add_argument("--min-price", type=float, default=1.0, help="skip legs priced below this (USD per BTC)")
    p.add_argument("--out", default="results")
    a = p.parse_args()

    data = Path(a.data)
    index = load_candles(data / "BTC_index_5m.csv")
    cfg = RealConfig(qty_btc=a.lots * LOT_BTC, hours_before=a.hours_before, min_price=a.min_price)
    strategies = [s for s in default_strategies() if not a.strategies or s.name in a.strategies]
    out = Path(a.out)
    out.mkdir(exist_ok=True)

    frames, rows = [], []
    for s in strategies:
        print(f"running {s.name}...")
        df = trades_frame(run_real_backtest(index, data / "options", s, cfg, a.start, a.end))
        frames.append(df)
        rows.append({"strategy": s.name, **summarise(df)})
    all_trades = pd.concat(frames, ignore_index=True)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    print(f"\n=== real Delta prices, entry {a.hours_before}h before expiry, {a.lots} lots ({a.lots * LOT_BTC:g} BTC) per leg, USD ===")
    print(pd.DataFrame(rows).set_index("strategy").to_string())
    print("\nmonth by month:")
    print(monthly(all_trades).to_string())
    all_trades.to_csv(out / "real_trades.csv", index=False)
    monthly(all_trades).to_csv(out / "real_monthly.csv")
    print(f"\nsaved {out}/real_trades.csv and {out}/real_monthly.csv")


if __name__ == "__main__":
    main()
