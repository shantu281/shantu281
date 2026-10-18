"""Our best BTC sellers on ETH daily options (same rules; costs scaled to ETH's price)."""
import sys
from multiprocessing import Pool
sys.path.insert(0, "."); sys.path.insert(0, "research")
import pandas as pd
from deltabot.backtest import trades_frame
from deltabot.data import load_candles
from deltabot.real_backtest import RealConfig, run_real_backtest
from deltabot.strategies import GmmaOptionSeller, IronButterfly
from gfilter import GmmaStrangle

index = load_candles("data/ETH_index_5m.csv")
STRATS = {"S1 GMMA 09:30, 3x stop": (lambda: GmmaOptionSeller("S1", stop_mult=3.0, params={"width": 0.5}), 8, 1.0),
          "S1 GMMA 09:30, no stop": (lambda: GmmaOptionSeller("S1n", params={"width": 0.5}), 8, 1.0),
          "S2 Lean strangle 15:30": (lambda: GmmaStrangle("S2", stop_mult=1.0, params={"mode": "skew"}), 2, 1.0),
          "S4 GMMA 15:30, 1x stop": (lambda: GmmaOptionSeller("S4", stop_mult=1.0, params={"width": 0.5}), 2, 1.0),
          "Iron fly 2%, IV>=32%": (lambda: IronButterfly("IF", params={"wing": 0.02, "min_iv": 0.32}), 2, 0.004)}
def run(name):
    make, h, minp = STRATS[name]
    cfg = RealConfig(qty_btc=1.0, hours_before=h, min_slippage=0.15, min_price=minp)  # 1 ETH = 100 ETH lots
    df = trades_frame(run_real_backtest(index, "data/eth_options", make(), cfg)); df["name"] = name
    return df
if __name__ == "__main__":
    with Pool(4) as p:
        out = pd.concat(p.map(run, list(STRATS)))
    out.to_csv("research/out/eth_best.csv", index=False); print(len(out))
