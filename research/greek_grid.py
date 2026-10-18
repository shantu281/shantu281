import sys, math
from multiprocessing import Pool
sys.path.insert(0, "/home/user/shantu281")
import numpy as np, pandas as pd
from deltabot.backtest import trades_frame
from deltabot.data import load_candles
from deltabot.pricing import strike_for_delta
from deltabot.real_backtest import RealConfig, run_real_backtest
from deltabot.strategies import GmmaOptionSeller, Leg
S = "research/out"

class GmmaDelta(GmmaOptionSeller):
    """GMMA side, strike picked by target delta."""
    def legs(self, ctx):
        legs = super().legs(ctx)
        if not legs: return legs
        (l,) = legs
        return [Leg(l.kind, strike_for_delta(l.kind, ctx.spot, self.params["delta"], ctx.t_years, ctx.vol, ctx.strike_step), -1)]

index = load_candles("data/BTC_index_5m.csv")

CONFIGS = [("delta15_h8", 8, 0.15, None), ("delta25_h8", 8, 0.25, None), ("delta35_h8", 8, 0.35, None), ("delta45_h8", 8, 0.45, None),
           ("delta25_h2_stop1", 2, 0.25, 1.0), ("delta35_h2_stop1", 2, 0.35, 1.0), ("delta25_h4", 4, 0.25, None), ("delta35_h4", 4, 0.35, None)]
def run(c):
    name, h, d, stop = c
    s = GmmaDelta(name, stop_mult=stop, params={"delta": d})
    trades_frame(run_real_backtest(index, "data/options", s, RealConfig(qty_btc=0.1, hours_before=h))).to_csv(f"{S}/gg_{name}.csv", index=False)
    return name
if __name__ == "__main__":
    with Pool(4) as p:
        for n in p.imap_unordered(run, CONFIGS): print("done", n, flush=True)
