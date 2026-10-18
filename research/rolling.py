"""Rolling the GMMA seller's short option instead of stopping out.
Trigger (spot touches strike / loss >= N x premium) -> buy back at the bar close, sell a new option of the same kind
at the original distance from spot scaled by sqrt(time left / 8 h), up to max_rolls; hold the last one to expiry."""
import sys, re, math
from multiprocessing import Pool
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from pathlib import Path
from deltabot.backtest import _leg_cost
from deltabot.data import load_candles
from deltabot.option_data import load_chain
from deltabot.pricing import intrinsic
from deltabot.real_backtest import RealConfig

S = sys.argv[1] if len(sys.argv) > 1 else "research/out"
base = pd.read_csv(f"{S}/fin_gmma_h8_slip5.csv"); base["entry"] = pd.to_datetime(base.entry_time, utc=True)
C = load_candles("data/BTC_index_5m.csv")["close"]
cfg = RealConfig(qty_btc=0.1)
BAR = pd.Timedelta(minutes=5)

def sim(row, trigger, max_rolls):
    kind = "call" if "C" in row.legs else "put"; k = float(re.search(r"[CP](\d+)", row.legs).group(1))
    entry = row.entry; expiry = entry + pd.Timedelta(hours=8)
    chain = load_chain(f"data/options/{expiry:%Y-%m-%d}.csv.gz")
    times = pd.date_range(entry, expiry - BAR, freq=BAR)
    dist0 = abs(k - row.spot_entry)
    def px(kk, t, col="close"):
        df = chain.get((kind, kk)); 
        if df is None: return None
        s = df[col].loc[:t]
        return float(s.iloc[-1]) if len(s) else None
    p_open = px(k, entry, "open"); pnl = 0.0; cost = _leg_cost(cfg, row.spot_entry, p_open); rolls = 0
    start = entry
    for t in times:
        if t < start: continue
        spot = float(C.loc[:t].iloc[-1]); cur = px(k, t)
        if cur is None: continue
        hit = (spot >= k if kind == "call" else spot <= k) if trigger == "touch" else (cur - p_open >= trigger * p_open)
        if hit and rolls < max_rolls and t < expiry - pd.Timedelta(minutes=30):
            pnl += p_open - cur; cost += _leg_cost(cfg, spot, cur)
            left = (expiry - t - BAR).total_seconds() / 3600
            want = spot + dist0 * math.sqrt(left / 8) * (1 if kind == "call" else -1)
            cands = [kk for (kd, kk), df in chain.items() if kd == kind and t in df.index and df.loc[t, "close"] >= 1
                     and (kk > spot if kind == "call" else kk < spot)]
            if not cands: break
            k = min(cands, key=lambda x: abs(x - want)); p_open = float(chain[(kind, k)].loc[t, "close"])
            cost += _leg_cost(cfg, spot, p_open); rolls += 1; start = t + BAR
    settle = intrinsic(kind, float(C.loc[expiry - pd.Timedelta(minutes=30): expiry - BAR].mean()), k)
    pnl += p_open - settle
    if settle > 0: cost += _leg_cost(cfg, spot, settle, settle=True)
    return (pnl - cost) * cfg.qty_btc, rolls

CONFIGS = [(tr, mr) for tr in ("touch", 1.0, 2.0) for mr in (1, 2)]
def run(c):
    tr, mr = c
    out = [sim(r, tr, mr) for r in base.itertuples()]
    return c, pd.DataFrame({"entry": base.entry, "pnl": [o[0] for o in out], "rolls": [o[1] for o in out]})
if __name__ == "__main__":
    with Pool(4) as p:
        for c, df in p.imap_unordered(run, CONFIGS):
            df.to_csv(f"research/out/roll_{c[0]}_{c[1]}.csv", index=False); print("done", c, flush=True)
