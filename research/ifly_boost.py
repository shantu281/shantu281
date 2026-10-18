"""Iron butterfly variations: cheap wings allowed, move-based wings, GMMA-shifted centre, entry times."""
import sys
from multiprocessing import Pool
sys.path.insert(0, ".")
import pandas as pd
from deltabot.backtest import trades_frame
from deltabot.data import load_candles
from deltabot.pricing import round_strike, SECONDS_PER_YEAR
from deltabot.real_backtest import RealConfig, run_real_backtest
from deltabot.strategies import Leg, Strategy, gmma_state

class Fly(Strategy):
    def legs(self, ctx):
        p = self.params
        h = max(1, round(ctx.t_years * SECONDS_PER_YEAR / 3600))
        move = ctx.history["close"].iloc[-7 * 24:].diff(h).abs().mean()
        center = ctx.spot
        if p.get("shift"):
            h4 = ctx.history["close"].resample("4h").last(); h4 = h4[h4.index + pd.Timedelta(hours=4) <= ctx.time].dropna()
            st = gmma_state(h4) if len(h4) >= 180 else "none"
            center += {"up": 1, "down": -1}.get(st, 0) * p["shift"] * move
        w = p["wing_move"] * move if "wing_move" in p else p["wing"] * ctx.spot
        k = round_strike(center, ctx.strike_step)
        return [Leg("call", k, -1), Leg("put", k, -1),
                Leg("call", round_strike(k + w, ctx.strike_step), +1), Leg("put", round_strike(k - w, ctx.strike_step), +1)]

index = load_candles("data/BTC_index_5m.csv")
C = []
for mp in (1.0, 0.1): C.append((f"w2pct_min{mp}", {"wing": 0.02}, 2, mp))
for m in (1.0, 1.5, 2.0, 3.0): C.append((f"wmove{m}", {"wing_move": m}, 2, 0.1))
for s in (0.25, 0.5): C.append((f"w2pct_shift{s}", {"wing": 0.02, "shift": s}, 2, 0.1))
for s in (0.25,): C.append((f"wmove2_shift{s}", {"wing_move": 2.0, "shift": s}, 2, 0.1))
for h in (1, 3, 4): C.append((f"wmove2_h{h}", {"wing_move": 2.0}, h, 0.1))
def run(c):
    n, params, h, mp = c
    trades_frame(run_real_backtest(index, "data/options", Fly(n, params=params), RealConfig(qty_btc=0.1, hours_before=h, min_price=mp))).to_csv(f"research/out/fb_{n}.csv", index=False)
    return n
if __name__ == "__main__":
    with Pool(4) as p:
        for n in p.imap_unordered(run, C): print("done", n, flush=True)
