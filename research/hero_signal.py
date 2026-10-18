"""Option buying on market triggers (expiry day). One trade per day: the first trigger in the window.
Entry at the next bar's open of the option (mark), exits checked on bar closes, costs as RealConfig."""
import sys
from multiprocessing import Pool
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from pathlib import Path
from deltabot.backtest import _leg_cost
from deltabot.data import load_candles
from deltabot.option_data import load_chain
from deltabot.pricing import intrinsic
from deltabot.real_backtest import RealConfig
from deltabot.strategies import gmma_state

idx = load_candles("data/BTC_index_5m.csv")
C, H, L = idx["close"], idx["high"], idx["low"]
r15 = C.pct_change(3); typ15 = r15.abs().rolling(288 * 7).mean().shift(1)
h4 = C.resample("4h").last()
h4_state = pd.Series({t: gmma_state(h4.loc[:t]) for t in h4.index[200:]})  # state of bar starting at t, known at t+4h

def signals(kind, p):
    """Series of +1 (buy call) / -1 (buy put) indexed by the bar whose CLOSE triggers."""
    if kind == "breakout":
        n = p * 12
        up = C > H.shift(1).rolling(n).max(); dn = C < L.shift(1).rolling(n).min()
    elif kind == "momentum":
        up = r15 > p * typ15; dn = r15 < -p * typ15
    elif kind == "mom":  # p = (bars, k): move over `bars` 5-min bars > k x its typical size
        n, k = p; r = C.pct_change(n); typ = r.abs().rolling(288 * 7).mean().shift(1)
        up = r > k * typ; dn = r < -k * typ
    elif kind == "squeeze":
        rng = (H.shift(1).rolling(72).max() / L.shift(1).rolling(72).min() - 1)
        tight = rng < p
        up = tight & (C > H.shift(1).rolling(72).max()); dn = tight & (C < L.shift(1).rolling(72).min())
    elif kind == "gmma_flip":
        st = h4_state.copy(); st.index = st.index + pd.Timedelta(hours=4) - pd.Timedelta(minutes=5)  # known at bar close
        prev = st.shift(1)
        s = pd.Series(0, index=C.index)
        for t, v in st.items():
            if v != prev.get(t) and v in ("up", "down") and t in s.index:
                s[t] = 1 if v == "up" else -1
        return s
    return up.astype(int) - dn.astype(int)

SIGS = {"breakout4h": ("breakout", 4), "breakout8h": ("breakout", 8), "breakout24h": ("breakout", 24),
        "momentum3x": ("momentum", 3), "squeeze0.6%": ("squeeze", 0.006), "gmma_flip": ("gmma_flip", None)}
STRIKES = {"ATM": 0.0, "OTM0.25%": 0.0025}
EXITS = {"expiry": (None, None), "SL50_TP2x": (0.5, 2.0), "TP3x": (None, 3.0)}
import os
cfg = RealConfig(qty_btc=0.1, min_slippage=float(os.environ.get("SLIP", "1.0")))
if os.environ.get("MOM"):
    SIGS = {f"mom_{n*5}m_{k}x": ("mom", (n, k)) for n in (1, 3, 6) for k in (2.0, 3.0, 4.0)}
    EXITS = {"expiry": (None, None), "TP3x": (None, 3.0), "TP2x": (None, 2.0), "SL50_TP3x": (0.5, 3.0)}
    STRIKES = {"ATM": 0.0}

def run_signal(name):
    kind, p = SIGS[name]; sig = signals(kind, p); rows = []
    for f in sorted(Path("data/options").glob("*.csv.gz")):
        expiry = pd.Timestamp(f.name[:10] + " 12:00", tz="UTC")
        win = sig.loc[expiry - pd.Timedelta(hours=12): expiry - pd.Timedelta(hours=1, minutes=5)]
        win = win[win != 0]
        if win.empty: continue
        trig_t, d = win.index[0], int(win.iloc[0]); entry = trig_t + pd.Timedelta(minutes=5)
        chain = load_chain(f); spot = float(C.loc[trig_t])
        for sname, off in STRIKES.items():
            for direction, tag in ((d, "signal"), (-d, "opposite")):
                kindo = "call" if direction > 0 else "put"
                want = spot * (1 + off) if kindo == "call" else spot * (1 - off)
                ks = [k for (kk, k), df in chain.items() if kk == kindo and entry in df.index]
                if not ks: continue
                k = min(ks, key=lambda x: abs(x - want)); df = chain[(kindo, k)]
                if abs(k - want) > 0.005 * spot: continue  # wanted strike not in the downloaded band
                p0 = float(df.loc[entry, "open"])
                if p0 < 1: continue
                path = df.loc[entry: expiry - pd.Timedelta(minutes=5), "close"]
                settle_win = C.loc[expiry - pd.Timedelta(minutes=30): expiry - pd.Timedelta(minutes=5)]
                settle = intrinsic(kindo, float(settle_win.mean()), k)
                for ename, (sl, tp) in EXITS.items():
                    exit_p, how = settle, "expiry"
                    for px in path.to_numpy():
                        if sl is not None and px <= p0 * (1 - sl): exit_p, how = px, "stop"; break
                        if tp is not None and px >= p0 * tp: exit_p, how = px, "target"; break
                    cost = _leg_cost(cfg, spot, p0) + (_leg_cost(cfg, spot, exit_p) if how != "expiry" else (_leg_cost(cfg, spot, settle, settle=True) if settle > 0 else 0))
                    rows.append(dict(signal=name, strike=sname, exit=ename, side=tag, expiry=expiry, entry=entry, kind=kindo,
                                     premium=p0, gross=(exit_p - p0) * cfg.qty_btc, pnl=(exit_p - p0 - cost) * cfg.qty_btc, mult=exit_p / p0))
    return pd.DataFrame(rows)

if __name__ == "__main__":
    with Pool(4) as pool:
        out = pd.concat(pool.map(run_signal, list(SIGS)))
    out.to_csv(os.environ.get("OUT", "research/out/hero_signal.csv"), index=False); print(len(out))
