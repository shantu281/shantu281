import sys, hashlib
from multiprocessing import Pool
sys.path.insert(0, "/home/user/shantu281")
from deltabot.backtest import trades_frame
from deltabot.data import load_candles
from deltabot.real_backtest import RealConfig, run_real_backtest
from deltabot.strategies import GmmaOptionSeller, Leg
S = "research/out"
class Control(GmmaOptionSeller):
    """Same days and strike distance as the GMMA seller, but the side is flipped or random."""
    def legs(self, ctx):
        legs = super().legs(ctx)
        if not legs: return legs
        (l,) = legs; off = abs(l.strike - ctx.spot)
        mode = self.params["mode"]
        if mode == "opposite": flip = True
        else:
            flip = int(hashlib.md5(f"{mode}{ctx.time}".encode()).hexdigest(), 16) % 2 == 0
        if not flip: return legs
        kind = "call" if l.kind == "put" else "put"
        k = ctx.spot + off if kind == "call" else ctx.spot - off
        return [Leg(kind, round(k / ctx.strike_step) * ctx.strike_step, -1)]
CONFIGS = [("opp_h8", 8, "opposite"), ("opp_h4", 4, "opposite")] + [(f"rnd{i}_h8", 8, f"r{i}") for i in range(6)]
index = load_candles("data/BTC_index_5m.csv")
def run(c):
    name, h, mode = c
    s = Control(name, params={"width": 0.5, "mode": mode})
    trades_frame(run_real_backtest(index, "data/options", s, RealConfig(qty_btc=0.1, hours_before=h))).to_csv(f"{S}/ct_{name}.csv", index=False)
    return name
if __name__ == "__main__":
    with Pool(4) as p:
        for n in p.imap_unordered(run, CONFIGS): print("done", n, flush=True)
