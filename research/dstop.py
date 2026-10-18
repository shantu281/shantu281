import sys, inspect
from multiprocessing import Pool
sys.path.insert(0, "/home/user/shantu281")
import deltabot.real_backtest as rb
src = inspect.getsource(rb.run_real_backtest)
src = src.replace("def run_real_backtest(", "def run_dstop(").replace("end: str | None = None)", "end: str | None = None, dstop: float = 9.0)")
src = src.replace('''        pnl_open, worst, reachable = value("open", "open"), value("low", "high"), value("close", "close")''',
'''        pnl_open, worst, reachable = value("open", "open"), value("low", "high"), value("close", "close")
        spot_close = index["close"].reindex(times).ffill().to_numpy()''')
old = '''            elif target is not None and (pnl_open[i] >= target or reachable[i] >= target):
                exit_reason, exit_pnl = "target", max(pnl_open[i], target)
            else:'''
assert old in src
src = src.replace(old, old.replace("            else:", '''            elif max(abs(bs_delta(l.kind, spot_close[i], l.strike, max((expiry - ts - bar).total_seconds(), 60) / SECONDS_PER_YEAR, iv)) for l in legs) > dstop:
                exit_reason, exit_pnl = "dstop", reachable[i]
            else:'''))
ns = dict(vars(rb)); from deltabot.pricing import bs_delta; ns["bs_delta"] = bs_delta
exec(src, ns); run_dstop = ns["run_dstop"]
from deltabot.backtest import trades_frame
from deltabot.data import load_candles
from deltabot.strategies import GmmaOptionSeller
from deltabot.real_backtest import RealConfig
S = "research/out"
index = load_candles("data/BTC_index_5m.csv")
CONFIGS = [(h, d) for h in (8, 4) for d in (0.5, 0.65, 0.8)] + [(2, 0.5), (2, 0.65)]
def run(c):
    h, d = c
    s = GmmaOptionSeller(f"dstop{d}_h{h}", params={"width": 0.5})
    trades_frame(run_dstop(index, "data/options", s, RealConfig(qty_btc=0.1, hours_before=h), dstop=d)).to_csv(f"{S}/ds_{d}_h{h}.csv", index=False)
    return c
if __name__ == "__main__":
    with Pool(4) as p:
        for n in p.imap_unordered(run, CONFIGS): print("done", n, flush=True)
