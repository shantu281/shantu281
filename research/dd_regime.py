"""Drawdown ideas: skip 15:30 entries when BTC already moved a lot since 09:30; half size after a big-move day."""
import sys
import numpy as np, pandas as pd
sys.path.insert(0, ".")
from deltabot.data import load_candles
S = sys.argv[1]
files = {"S1": f"{S}/fin_gmma_h8_slip5.csv", "S2": f"{S}/fin_lean_h2_stop1_slip5.csv", "S4": f"{S}/fin_gmma_h2_stop1_slip5.csv"}
LOTS = {"S1": 150, "S2": 200, "S4": 400}
d = {}
for k, f in files.items():
    x = pd.read_csv(f); x["day"] = (pd.to_datetime(x.entry_time, utc=True) + pd.Timedelta(hours=12)).dt.floor("D")
    d[k] = x.groupby("day").pnl.sum() * LOTS[k] / 100
d = pd.DataFrame(d).fillna(0); d = d[d.index >= "2024-09-01"]
C = load_candles("data/BTC_index_5m.csv")["close"]
def px(t): return float(C.loc[:t].iloc[-1])
day = d.index
morning = pd.Series([abs(px(t + pd.Timedelta(hours=10) - pd.Timedelta(minutes=5)) / px(t + pd.Timedelta(hours=4)) - 1) * 100 for t in day], index=day)  # 09:30->15:30 IST
prevday = pd.Series([abs(px(t + pd.Timedelta(hours=12) - pd.Timedelta(days=1)) / px(t + pd.Timedelta(hours=12) - pd.Timedelta(days=2)) - 1) * 100 for t in day], index=day)
def stats(p, lab):
    eq = 10000 + p.cumsum(); dd = (eq - eq.cummax()).min(); m = p.groupby(p.index.strftime("%Y-%m")).sum()
    return dict(rule=lab, per_month=round(m.mean()), y1=round(p[p.index < "2025-10-01"].sum()), y2=round(p[p.index >= "2025-10-01"].sum()),
                max_dd=round(dd), worst_day=round(p.min()), worst_month=round(m.min()), losing=int((m < 0).sum()))
rows = [stats(d.sum(axis=1), "none")]
for th in (0.75, 1.0, 1.5, 2.0):
    skip = morning > th
    p = d.S1 + d.S2.where(~skip, 0) + d.S4.where(~skip, 0)
    rows.append(stats(p, f"skip 15:30 trades if BTC moved >{th}% since 09:30 ({skip.mean()*100:.0f}% of days)"))
for th in (2.0, 3.0, 4.0):
    big = prevday > th
    p = d.sum(axis=1) * np.where(big, 0.5, 1.0)
    rows.append(stats(p, f"half size after a >{th}% BTC day ({big.mean()*100:.0f}% of days)"))
print(pd.DataFrame(rows).to_string(index=False))
