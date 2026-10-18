import sys
from multiprocessing import Pool
sys.path.insert(0, "/home/user/shantu281")
import pandas as pd
from deltabot.backtest import trades_frame
from deltabot.data import load_candles
from deltabot.pricing import SECONDS_PER_YEAR, round_strike
from deltabot.real_backtest import RealConfig, run_real_backtest
from deltabot.strategies import Leg, Strategy, gmma_state
S = "research/out"
class GmmaStrangle(Strategy):
    def legs(self, ctx):
        hourly = ctx.history["close"]
        h4 = hourly.resample("4h").last(); h4 = h4[h4.index + pd.Timedelta(hours=4) <= ctx.time].dropna()
        if len(h4) < 180: return []
        state = gmma_state(h4); mode = self.params["mode"]
        h = max(1, round(ctx.t_years * SECONDS_PER_YEAR / 3600))
        move = hourly.iloc[-7 * 24:].diff(h).abs().mean()
        wc = wp = 0.5
        if mode == "range_only" and state != "none": return []
        if mode == "trend_only" and state == "none": return []
        if mode == "skew":
            near, far = self.params.get("lean", (0.25, 1.0))
            if state == "up": wp, wc = near, far
            elif state == "down": wp, wc = far, near
        return [Leg("call", round_strike(ctx.spot + wc * move, ctx.strike_step), -1),
                Leg("put", round_strike(ctx.spot - wp * move, ctx.strike_step), -1)]
CONFIGS2 = [("skew", 4, 1.0, (0.25, 1.0)), ("skew", 6, 1.0, (0.25, 1.0)), ("skew", 2, 1.0, (0.35, 0.75)), ("skew", 2, 2.0, (0.25, 1.0))]
CONFIGS = [("range_only", 2, None), ("range_only", 8, None), ("range_only", 2, 1.0),
           ("skew", 2, None), ("skew", 8, None), ("skew", 2, 1.0),
           ("trend_only", 2, None), ("trend_only", 8, None)]
index = load_candles("data/BTC_index_5m.csv")
def run(c):
    mode, h, stop, *lean = c; name = f"gs_{mode}_h{h}" + (f"_stop{stop:g}" if stop else "") + (f"_lean{lean[0][0]}" if lean else "")
    s = GmmaStrangle(name, stop_mult=stop, params={"mode": mode, **({"lean": lean[0]} if lean else {})})
    trades_frame(run_real_backtest(index, "data/options", s, RealConfig(qty_btc=0.1, hours_before=h))).to_csv(f"{S}/{name}.csv", index=False)
    return name
if __name__ == "__main__":
    with Pool(4) as p:
        for n in p.imap_unordered(run, CONFIGS2 if 'v2' in sys.argv else CONFIGS): print("done", n, flush=True)
