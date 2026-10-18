"""Insurance for the GMMA seller (09:30 IST, 8 h): P&L stops, and long wings further OTM (same side) at 1-3x size.
Wings are run as their own long-option trades on the same days, then added with a size ratio."""
import sys
from multiprocessing import Pool
sys.path.insert(0, ".")
import pandas as pd
from deltabot.backtest import trades_frame
from deltabot.data import load_candles
from deltabot.pricing import round_strike, SECONDS_PER_YEAR
from deltabot.real_backtest import RealConfig, run_real_backtest
from deltabot.strategies import GmmaOptionSeller, Leg

class Wing(GmmaOptionSeller):
    """The GMMA seller's short leg moved `extra` x recent move further OTM, bought instead of sold."""
    def legs(self, ctx):
        legs = super().legs(ctx)
        if not legs: return legs
        (l,) = legs
        h = max(1, round(ctx.t_years * SECONDS_PER_YEAR / 3600))
        move = ctx.history["close"].iloc[-7 * 24:].diff(h).abs().mean()
        off = self.params["extra"] * move * (1 if l.kind == "call" else -1)
        return [Leg(l.kind, round_strike(l.strike + off, ctx.strike_step), +1)]

index = load_candles("data/BTC_index_5m.csv")
cfg = RealConfig(qty_btc=0.1, hours_before=8)
CONFIGS = [("stop", s) for s in (1.0, 1.5, 2.0, 3.0, 4.0, 5.0)] + [("wing", e) for e in (0.5, 1.0, 1.5, 2.0)]
def run(c):
    kind, v = c
    s = GmmaOptionSeller(f"stop{v}", stop_mult=v, params={"width": 0.5}) if kind == "stop" else Wing(f"wing{v}", params={"width": 0.5, "extra": v})
    trades_frame(run_real_backtest(index, "data/options", s, cfg)).to_csv(f"research/out/ins_{kind}{v}.csv", index=False)
    return c
if __name__ == "__main__":
    with Pool(4) as p:
        for c in p.imap_unordered(run, CONFIGS): print("done", c, flush=True)
