"""Calendar spread: sell today's daily option, buy the next Friday's weekly at the same strike; close both at the daily expiry."""
import sys
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from pathlib import Path
from deltabot.backtest import _leg_cost
from deltabot.data import load_candles
from deltabot.option_data import load_chain
from deltabot.pricing import intrinsic
from deltabot.real_backtest import RealConfig
from deltabot.strategies import gmma_state

C = load_candles("data/BTC_index_5m.csv")["close"]; h4 = C.resample("4h").last()
state = pd.Series({t + pd.Timedelta(hours=4): gmma_state(h4.loc[:t]) for t in h4.index[200:]})
import os
cfg = RealConfig(qty_btc=0.1, slippage_pct=float(os.environ.get("SLIP_PCT", "0.02"))); BAR = pd.Timedelta(minutes=5)
weekly = {pd.Timestamp(f.name[:10] + " 12:00", tz="UTC"): f for f in Path("data/options_weekly").glob("*.csv.gz")}
rows = []
for f in sorted(Path("data/options").glob("*.csv.gz")):
    D = pd.Timestamp(f.name[:10] + " 12:00", tz="UTC")
    F = next((w for w in sorted(weekly) if w > D and w - D <= pd.Timedelta(days=7)), None)
    if F is None: continue
    daily = load_chain(f); wk = load_chain(weekly[F])
    sw = C.loc[D - pd.Timedelta(minutes=30): D - BAR].mean()
    for h in (2, 8):
        t0 = D - pd.Timedelta(hours=h); spot = float(C.loc[:t0 - BAR].iloc[-1])
        st = state.loc[:t0].iloc[-1] if len(state.loc[:t0]) else "none"
        for mode in ("ATM_call", "ATM_put", "gmma_OTM0.5"):
            if mode == "gmma_OTM0.5":
                if st == "none": continue
                kind = "put" if st == "up" else "call"; want = spot * (0.995 if kind == "put" else 1.005)
            else:
                kind = mode.split("_")[1]; want = spot
            ks = [k for (kd, k), df in daily.items() if kd == kind and t0 in df.index and (kind, k) in wk and t0 in wk[(kind, k)].index]
            if not ks: continue
            k = min(ks, key=lambda x: abs(x - want))
            if abs(k - want) > 0.005 * spot: continue
            ds, wb = float(daily[(kind, k)].loc[t0, "open"]), float(wk[(kind, k)].loc[t0, "open"])
            w_exit = float(wk[(kind, k)]["close"].loc[:D - BAR].iloc[-1]); d_settle = intrinsic(kind, sw, k)
            gross = (ds - d_settle) + (w_exit - wb)
            cost = _leg_cost(cfg, spot, ds) + _leg_cost(cfg, spot, wb) + _leg_cost(cfg, sw, w_exit) + (_leg_cost(cfg, sw, d_settle, settle=True) if d_settle > 0 else 0)
            rows.append(dict(expiry=D, hours=h, mode=mode, kind=kind, K=k, daily=ds, weekly=wb, gross=gross * cfg.qty_btc, pnl=(gross - cost) * cfg.qty_btc))
out = pd.DataFrame(rows); out.to_csv("research/out/calendar.csv", index=False)
def pf(v):
    l = -v[v < 0].sum(); return v[v > 0].sum() / l if l else np.inf
res = []
for (h, m), g in out.groupby(["hours", "mode"]):
    g = g.sort_values("expiry"); eq = g.pnl.cumsum(); mm = g.groupby(g.expiry.dt.strftime("%Y-%m")).pnl.sum()
    res.append(dict(version=f"{m}, sold {h}h before", trades=len(g), win=f"{(g.pnl>0).mean()*100:.0f}%", pf=round(pf(g.pnl), 2),
                    daily_prem=round(g.daily.median()), weekly_cost=round(g.weekly.median()), before=round(g.gross.sum()), net=round(g.pnl.sum()),
                    y1=round(g.pnl[g.expiry < "2025-10-01"].sum()), y2=round(g.pnl[g.expiry >= "2025-10-01"].sum()),
                    max_dd=round((eq - eq.cummax().clip(lower=0)).min()), losing_m=f"{(mm<0).sum()}/{len(mm)}"))
print(pd.DataFrame(res).to_string(index=False))
