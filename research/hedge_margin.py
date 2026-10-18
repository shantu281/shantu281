"""Far OTM wings on the GMMA seller (09:30 IST): profit cost vs portfolio-margin saving."""
import sys
from multiprocessing import Pool
sys.path.insert(0, "."); sys.path.insert(0, "research")
import pandas as pd
from deltabot.backtest import trades_frame
from deltabot.data import load_candles
from deltabot.pricing import round_strike
from deltabot.real_backtest import RealConfig, run_real_backtest
from deltabot.strategies import GmmaOptionSeller, Leg

class FarWing(GmmaOptionSeller):
    def legs(self, ctx):
        legs = super().legs(ctx)
        if not legs: return legs
        (l,) = legs; off = self.params["far"] * ctx.spot * (1 if l.kind == "call" else -1)
        return [Leg(l.kind, round_strike(l.strike + off, ctx.strike_step), +1)]

index = load_candles("data/BTC_index_5m.csv")
def run(far):
    s = FarWing(f"far{far}", params={"width": 0.5, "far": far})
    trades_frame(run_real_backtest(index, "data/options", s, RealConfig(qty_btc=0.1, hours_before=8, min_price=0.1))).to_csv(f"research/out/hm_far{far}.csv", index=False)
    return far
if __name__ == "__main__":
    with Pool(3) as p: print(list(p.imap_unordered(run, (0.01, 0.02, 0.03))))
