import sys
from multiprocessing import Pool
sys.path.insert(0, "/home/user/shantu281"); sys.path.insert(0, "research/out")
from deltabot.backtest import trades_frame
from deltabot.data import load_candles
from deltabot.real_backtest import RealConfig, run_real_backtest
from deltabot.strategies import GmmaOptionSeller
from gfilter import GmmaStrangle
S = "research/out"
def strat(n):
    return {"gmma_h8": (GmmaOptionSeller("gmma_h8", params={"width": 0.5}), 8),
            "gmma_h2_stop1": (GmmaOptionSeller("gmma_h2_stop1", stop_mult=1.0, params={"width": 0.5}), 2),
            "lean_h2_stop1": (GmmaStrangle("lean_h2_stop1", stop_mult=1.0, params={"mode": "skew"}), 2)}[n]
CONFIGS = [(n, slip) for n in ("gmma_h8", "gmma_h2_stop1", "lean_h2_stop1") for slip in (5.0, 2.5, 10.0)]
index = load_candles("data/BTC_index_5m.csv")
def run(c):
    n, slip = c; s, h = strat(n)
    trades_frame(run_real_backtest(index, "data/options", s, RealConfig(qty_btc=0.1, hours_before=h, min_slippage=slip))).to_csv(f"{S}/fin_{n}_slip{slip:g}.csv", index=False)
    return n
if __name__ == "__main__":
    with Pool(4) as p:
        for x in p.imap_unordered(run, CONFIGS): pass
