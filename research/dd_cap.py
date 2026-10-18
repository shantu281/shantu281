"""Drawdown-capping rules on the combined sellers (daily P&L, decisions use results up to the previous day)."""
import sys
import numpy as np, pandas as pd
S = sys.argv[1]
files = {"S1": f"{S}/fin_gmma_h8_slip5.csv", "S2": f"{S}/fin_lean_h2_stop1_slip5.csv", "S3": "research/out/ifly_iv32/real_trades.csv",
         "S4": f"{S}/fin_gmma_h2_stop1_slip5.csv", "S5": f"{S}/stop_1.0.csv"}
d = {}
for k, f in files.items():
    x = pd.read_csv(f); x["day"] = (pd.to_datetime(x.entry_time, utc=True) + pd.Timedelta(hours=12)).dt.floor("D")
    d[k] = x.groupby("day").pnl.sum()
d = pd.DataFrame(d).fillna(0); d = d[d.index >= "2024-09-01"]
d = d.reindex(pd.date_range(d.index.min(), d.index.max(), freq="D"), fill_value=0)
CAP = 10000

def run(lots, rule=None, p=None):
    base = (d * np.array([lots[k] for k in d.columns]) / 100).sum(axis=1)
    bal, peak, out, paused_until = CAP, CAP, [], None
    mstart = wstart = CAP; cur_m = cur_w = None
    for t, v in base.items():
        m, w = t.strftime("%Y-%m"), t.strftime("%G-%V")
        if m != cur_m: cur_m, mstart = m, bal
        if w != cur_w: cur_w, wstart = w, bal
        scale = 1.0
        if rule == "month" and bal <= mstart * (1 - p): scale = 0
        if rule == "week" and bal <= wstart * (1 - p): scale = 0
        if rule == "throttle" and bal <= peak * (1 - p): scale = 0.5
        if rule == "pause":
            if paused_until is not None and t < paused_until: scale = 0
            elif bal <= peak * (1 - p[0]) and (paused_until is None or t >= paused_until):
                paused_until, scale, peak = t + pd.Timedelta(days=p[1]), 0, bal  # reset peak after the pause
        pnl = v * scale; bal += pnl; peak = max(peak, bal); out.append((t, pnl, bal))
    r = pd.DataFrame(out, columns=["t", "pnl", "bal"]).set_index("t")
    eq = r.bal; dd = (eq / eq.cummax() - 1).min() * 100; ddd = (eq - eq.cummax()).min()
    mo = r.pnl.groupby(r.index.strftime("%Y-%m")).sum()
    return dict(per_month=round(mo.mean()), total=round(r.pnl.sum()), max_dd=round(ddd), max_dd_pct=round(dd, 1),
                worst_month=round(mo.min()), losing_months=int((mo < 0).sum()))

if __name__ == "__main__":
    for name, lots in (("same-risk mix", {"S1": 150, "S2": 200, "S3": 0, "S4": 400, "S5": 0}),
                       ("equal 100 each", {k: 100 for k in d.columns})):
        rows = [dict(rule="none") | run(lots)]
        for p in (0.03, 0.05): rows.append(dict(rule=f"monthly stop -{p:.0%}") | run(lots, "month", p))
        for p in (0.02, 0.03): rows.append(dict(rule=f"weekly stop -{p:.0%}") | run(lots, "week", p))
        for p in (0.03, 0.05): rows.append(dict(rule=f"half size when >{p:.0%} below peak") | run(lots, "throttle", p))
        for p in ((0.05, 7), (0.05, 14), (0.08, 14)): rows.append(dict(rule=f"pause {p[1]}d at -{p[0]:.0%} from peak") | run(lots, "pause", p))
        print(f"\n== {name}, $10,000"); print(pd.DataFrame(rows).to_string(index=False))
