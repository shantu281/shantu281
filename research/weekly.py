"""Selling Friday-expiry (weekly) BTC options: entry 7 or 3 days before, strikes by delta, hold or take 50% profit."""
import sys
from multiprocessing import Pool
sys.path.insert(0, "."); sys.path.insert(0, "research")
import pandas as pd
from deltabot.backtest import trades_frame
from deltabot.data import load_candles
from deltabot.pricing import strike_for_delta
from deltabot.real_backtest import RealConfig, run_real_backtest
from deltabot.strategies import GmmaOptionSeller, Leg, ShortStrangle

class GmmaDelta(GmmaOptionSeller):
    def legs(self, ctx):
        legs = super().legs(ctx)
        if not legs: return legs
        (l,) = legs
        return [Leg(l.kind, strike_for_delta(l.kind, ctx.spot, self.params["delta"], ctx.t_years, ctx.vol, ctx.strike_step), -1)]

index = load_candles("data/BTC_index_5m.csv")
STRATS = {f"strangle_d{int(d*100)}": (ShortStrangle, {"delta": d}) for d in (0.10, 0.15, 0.20)} | \
         {f"gmma_d{int(d*100)}": (GmmaDelta, {"delta": d, "width": 0.5}) for d in (0.15, 0.25)}
CONFIGS = [(n, days, tp) for n in STRATS for days in (7, 3) for tp in (None, 0.5)]
def run(c):
    n, days, tp = c; cls, params = STRATS[n]
    name = f"{n}_{days}d" + ("_tp50" if tp else "")
    s = cls(name, take_profit=tp, params=params)
    df = trades_frame(run_real_backtest(index, "data/options_weekly", s, RealConfig(qty_btc=0.1, hours_before=days * 24)))
    df.to_csv(f"research/out/wk_{name}.csv", index=False)
    return name
if __name__ == "__main__":
    with Pool(4) as p:
        for n in p.imap_unordered(run, CONFIGS): print("done", n, flush=True)
