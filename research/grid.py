import sys
from multiprocessing import Pool
sys.path.insert(0, "/home/user/shantu281")
import pandas as pd
from deltabot.backtest import trades_frame
from deltabot.data import load_candles
from deltabot.real_backtest import RealConfig, run_real_backtest
from deltabot.strategies import GmmaOptionSeller
S = "research/out"
CONFIGS = [  # name, hours_before, width, stop
    ("otm05_h4", 4, 0.5, None), ("otm05_h12", 12, 0.5, None),
    ("otm025_h8", 8, 0.25, None), ("otm1_h8", 8, 1.0, None),
    ("otm05_h8_stop1", 8, 0.5, 1.0), ("otm05_h8_stop2", 8, 0.5, 2.0),
    ("otm05_h2_stop1", 2, 0.5, 1.0), ("otm05_h6", 6, 0.5, None),
]
index = load_candles("data/BTC_index_5m.csv")
def run(c):
    name, h, w, stop = c
    s = GmmaOptionSeller(name, stop_mult=stop, params={"width": w})
    trades_frame(run_real_backtest(index, "data/options", s, RealConfig(qty_btc=0.1, hours_before=h))).to_csv(f"{S}/gr_{name}.csv", index=False)
    return name
if __name__ == "__main__":
    with Pool(4) as p:
        for n in p.imap_unordered(run, CONFIGS): print("done", n, flush=True)
