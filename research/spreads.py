"""Debit spreads with the GMMA side, iron butterflies (both directions) on daily options."""
import sys
from multiprocessing import Pool
sys.path.insert(0, ".")
import pandas as pd
from deltabot.backtest import trades_frame
from deltabot.data import load_candles
from deltabot.pricing import round_strike
from deltabot.real_backtest import RealConfig, run_real_backtest
from deltabot.strategies import Leg, Strategy, gmma_state

def trend(ctx):
    h4 = ctx.history["close"].resample("4h").last()
    h4 = h4[h4.index + pd.Timedelta(hours=4) <= ctx.time].dropna()
    return gmma_state(h4) if len(h4) >= 180 else "none"

class DebitSpread(Strategy):
    """Bull call spread in an up trend, bear put spread in a down trend (side flipped if params['against'])."""
    def legs(self, ctx):
        st = trend(ctx)
        if st == "none": return []
        up = (st == "up") != self.params.get("against", False)
        k = round_strike(ctx.spot, ctx.strike_step); w = self.params["w"] * ctx.spot
        if up: return [Leg("call", k, +1), Leg("call", round_strike(ctx.spot + w, ctx.strike_step), -1)]
        return [Leg("put", k, +1), Leg("put", round_strike(ctx.spot - w, ctx.strike_step), -1)]

class IronFly(Strategy):
    """side -1: short iron butterfly (sell ATM straddle, buy wings); +1: the reverse."""
    def legs(self, ctx):
        s = self.params["side"]; k = round_strike(ctx.spot, ctx.strike_step); w = self.params["w"] * ctx.spot
        return [Leg("call", k, s), Leg("put", k, s),
                Leg("call", round_strike(ctx.spot + w, ctx.strike_step), -s), Leg("put", round_strike(ctx.spot - w, ctx.strike_step), -s)]

index = load_candles("data/BTC_index_5m.csv")
CONFIGS = [("debit", w, h, False) for w in (0.005, 0.01, 0.015) for h in (2, 4, 8)] + \
          [("debit", 0.01, h, True) for h in (2, 8)] + \
          [("ironfly_short", w, h, None) for w in (0.005, 0.01, 0.015) for h in (2, 4, 8)] + \
          [("ironfly_long", w, h, None) for w in (0.005, 0.01) for h in (2, 8)]
def name(c):
    kind, w, h, ag = c
    return f"{kind}{'_against' if ag else ''}_w{w*100:g}_h{h}"
def run(c):
    kind, w, h, ag = c
    s = DebitSpread(name(c), params={"w": w, "against": ag}) if kind == "debit" else IronFly(name(c), params={"w": w, "side": -1 if kind == "ironfly_short" else +1})
    trades_frame(run_real_backtest(index, "data/options", s, RealConfig(qty_btc=0.1, hours_before=h))).to_csv(f"research/out/sp_{name(c)}.csv", index=False)
    return name(c)
if __name__ == "__main__":
    with Pool(4) as p:
        for n in p.imap_unordered(run, CONFIGS): print("done", n, flush=True)
