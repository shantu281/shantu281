import pandas as pd, numpy as np, sys
S = "research/out"
FEATS = ["delta","gamma","vega","theta","iv","rv24","rv7","iv_rv24","iv_rv7","credit","credit_move","be_move","dist_pct","hour_ret"]
def analyse(f):
    x = pd.read_csv(f"{S}/feat_{f}"); x["d"] = pd.to_datetime(x.entry_time, utc=True)
    y1 = x[x.d < "2025-10-01"]; y2 = x[x.d >= "2025-10-01"]
    rows = []
    for c in FEATS:
        q1, q2 = y1[c].quantile([1/3, 2/3])
        def grp(df): return pd.cut(df[c], [-np.inf, q1, q2, np.inf], labels=["low","mid","high"])
        a = y1.groupby(grp(y1), observed=False).pnl.mean(); b = y2.groupby(grp(y2), observed=False).pnl.mean()
        worst = a.idxmin()  # chosen on year 1
        y2_skip = y2.pnl[grp(y2) != worst].sum() - y2.pnl.sum()
        same = a.idxmin() == b.idxmin() and a.idxmax() == b.idxmax()
        rows.append(dict(feature=c, y1_low=a["low"], y1_mid=a["mid"], y1_high=a["high"], y2_low=b["low"], y2_mid=b["mid"], y2_high=b["high"],
                         skip=worst, y2_gain_from_skip=y2_skip, consistent="YES" if same else ""))
    r = pd.DataFrame(rows)
    print(f"\n== {f}: avg $ per trade (100 lots) by third; year-2 net {y2.pnl.sum():.0f}")
    print(r.round(1).to_string(index=False))
for f in sys.argv[1:]: analyse(f)
