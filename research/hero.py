"""Hero-zero: buy cheap OTM options shortly before expiry, hold to expiry (or take profit at N x)."""
import sys
from multiprocessing import Pool
sys.path.insert(0, ".")
import pandas as pd
from deltabot.backtest import trades_frame
from deltabot.data import load_candles
from deltabot.pricing import round_strike
from deltabot.real_backtest import RealConfig, run_real_backtest
from deltabot.strategies import Leg, Strategy, gmma_state

class HeroZero(Strategy):
    def legs(self, ctx):
        d = self.params["dist"]; side = self.params["side"]
        kc = round_strike(ctx.spot * (1 + d), ctx.strike_step); kp = round_strike(ctx.spot * (1 - d), ctx.strike_step)
        if side == "both":
            return [Leg("call", kc, +1), Leg("put", kp, +1)]
        h4 = ctx.history["close"].resample("4h").last()
        h4 = h4[h4.index + pd.Timedelta(hours=4) <= ctx.time].dropna()
        if len(h4) < 180: return []
        st = gmma_state(h4)
        if side == "gmma":  # buy in the trend direction
            return [Leg("call", kc, +1)] if st == "up" else [Leg("put", kp, +1)] if st == "down" else []
        if side == "gmma_against":  # buy against the trend (the leg our sellers sell... the other side)
            return [Leg("put", kp, +1)] if st == "up" else [Leg("call", kc, +1)] if st == "down" else []
        return []

index = load_candles("data/BTC_index_5m.csv")
def run(c):
    name, h, d, side, tp, slip = c
    s = HeroZero(name, take_profit=tp, params={"dist": d, "side": side})
    cfg = RealConfig(qty_btc=0.1, hours_before=h, min_slippage=slip)
    trades_frame(run_real_backtest(index, "data/options", s, cfg)).to_csv(f"research/out/hz_{name}.csv", index=False)
    return name

GRID1 = [(f"{side}_h{h}_d{d}", h, d, side, None, 1.0) for h in (1, 2, 3) for d in (0.0075, 0.015) for side in ("both", "gmma")]
if __name__ == "__main__":
    grid = eval(sys.argv[1]) if len(sys.argv) > 1 else GRID1
    with Pool(4) as p:
        for n in p.imap_unordered(run, grid): print("done", n, flush=True)
