"""Compare the candidate option strategies on downloaded BTC candles.

    python scripts/run_backtest.py --data data/BTCUSD_1h.csv --iv-mult 0.9 1.0 1.2
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deltabot.backtest import BacktestConfig, monthly, run_backtest, summarise, trades_frame  # noqa: E402
from deltabot.data import load_candles  # noqa: E402
from deltabot.strategies import default_strategies  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--strategies", nargs="*", default=None, help="names to run (default: all)")
    p.add_argument("--iv-mult", nargs="+", type=float, default=[1.0])
    p.add_argument("--qty", type=float, default=0.1, help="BTC per leg")
    p.add_argument("--entry-hour", type=int, default=12, help="UTC hour of entry")
    p.add_argument("--out", default="results")
    a = p.parse_args()

    candles = load_candles(a.data)
    if a.start:
        candles = candles.loc[pd.Timestamp(a.start, tz="UTC"):]
    if a.end:
        candles = candles.loc[:pd.Timestamp(a.end, tz="UTC")]
    strategies = [s for s in default_strategies() if not a.strategies or s.name in a.strategies]
    out = Path(a.out)
    out.mkdir(exist_ok=True)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    for iv in a.iv_mult:
        cfg = BacktestConfig(qty_btc=a.qty, iv_mult=iv, entry_hour_utc=a.entry_hour)
        frames, rows = [], []
        for s in strategies:
            df = trades_frame(run_backtest(candles, s, cfg))
            frames.append(df)
            rows.append({"strategy": s.name, **summarise(df)})
        all_trades = pd.concat(frames, ignore_index=True)
        print(f"\n=== iv_mult {iv}  ({candles.index[0].date()} .. {candles.index[-1].date()}, "
              f"{a.qty} BTC per leg, USD) ===")
        print(pd.DataFrame(rows).set_index("strategy").to_string())
        all_trades.to_csv(out / f"trades_iv{iv}.csv", index=False)
        monthly(all_trades).to_csv(out / f"monthly_iv{iv}.csv")
    print(f"\ntrade lists and month-wise tables saved in {out}/")


if __name__ == "__main__":
    main()
