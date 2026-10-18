"""Momentum burst with the GMMA H4 trend: strike / exit / premium-cap combinations.
First trend-aligned burst per expiry day (05:30-16:30 IST), buy, exit at N x or hold to expiry."""
import sys, os
from multiprocessing import Pool
sys.path.insert(0, "."); sys.path.insert(0, "research")
import numpy as np, pandas as pd
from pathlib import Path
from deltabot.backtest import _leg_cost
from deltabot.option_data import load_chain
from deltabot.pricing import intrinsic
from deltabot.real_backtest import RealConfig
import hero_signal as hs

cfg = RealConfig(qty_btc=0.1, min_slippage=1.0)
st = pd.Series({t + pd.Timedelta(hours=4): v for t, v in hs.h4_state.items()})  # state known from bar close on
SIGS = {f"mom_{n*5}m_{k}x": (n, k) for n in (1, 3, 6) for k in (2.0, 3.0, 4.0)}
OFFS = {"ATM": 0.0, "OTM0.25": 0.0025, "OTM0.5": 0.005, "OTM0.75": 0.0075, "OTM1": 0.01}
PREM = {"prem>=50": 50, "prem>=100": 100, "prem>=150": 150}  # cheapest strike still costing at least this
TPS = {"TP2x": 2.0, "TP3x": 3.0, "TP5x": 5.0, "expiry": None}

def run(name):
    n, k = SIGS[name]; sig = hs.signals("mom", (n, k)); rows = []
    trend = st.reindex(sig.index, method="ffill")
    sig = sig.where(((sig > 0) & (trend == "up")) | ((sig < 0) & (trend == "down")), 0)
    for f in sorted(Path("data/options").glob("*.csv.gz")):
        expiry = pd.Timestamp(f.name[:10] + " 12:00", tz="UTC")
        win = sig.loc[expiry - pd.Timedelta(hours=12): expiry - pd.Timedelta(hours=1, minutes=5)]
        win = win[win != 0]
        if win.empty: continue
        t0 = win.index[0]; d = int(win.iloc[0]); entry = t0 + pd.Timedelta(minutes=5)
        kind = "call" if d > 0 else "put"; spot = float(hs.C.loc[t0])
        chain = load_chain(f)
        avail = {kk: df for (kd, kk), df in chain.items() if kd == kind and entry in df.index}
        if not avail: continue
        prices = {kk: float(df.loc[entry, "open"]) for kk, df in avail.items()}
        picks = {}
        for sname, off in OFFS.items():
            want = spot * (1 + off) if kind == "call" else spot * (1 - off)
            kk = min(prices, key=lambda x: abs(x - want))
            if abs(kk - want) <= 0.005 * spot: picks[sname] = kk
        for sname, floor in PREM.items():
            ok = [kk for kk, p in prices.items() if p >= floor]
            if ok: picks[sname] = min(ok, key=lambda x: prices[x])
        sw = hs.C.loc[expiry - pd.Timedelta(minutes=30): expiry - pd.Timedelta(minutes=5)]
        for sname, kk in picks.items():
            p0 = prices[kk]
            if p0 < 1: continue
            path = avail[kk].loc[entry: expiry - pd.Timedelta(minutes=5), "close"].to_numpy()
            settle = intrinsic(kind, float(sw.mean()), kk)
            for tname, tp in TPS.items():
                exit_p, how = settle, "expiry"
                if tp:
                    hit = np.nonzero(path >= p0 * tp)[0]
                    if len(hit): exit_p, how = path[hit[0]], "target"
                cost = _leg_cost(cfg, spot, p0) + (_leg_cost(cfg, spot, exit_p) if how == "target" else (_leg_cost(cfg, spot, settle, settle=True) if settle > 0 else 0))
                rows.append(dict(signal=name, strike=sname, exit=tname, expiry=expiry, entry=entry, kind=kind, K=kk,
                                 dist=abs(kk / spot - 1) * 100, premium=p0, mult=exit_p / p0, pnl=(exit_p - p0 - cost) * cfg.qty_btc))
    return pd.DataFrame(rows)

if __name__ == "__main__":
    with Pool(4) as p:
        out = pd.concat(p.map(run, list(SIGS)))
    out.to_csv("research/out/hero_combo.csv", index=False); print(len(out))
