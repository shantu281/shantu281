import pandas as pd, sys
S="research/out"
files=dict(a.split("=") for a in sys.argv[1:])
rows=[]
for name,f in files.items():
    x=pd.read_csv(f"{S}/{f}"); x=x[x.strategy==x.strategy.iloc[0]] if "h2/" not in f and "h8/" not in f and "h4/" not in f else x[x.strategy=="short_straddle_noexit"]
    x["d"]=pd.to_datetime(x.entry_time,utc=True); m=x.groupby(x.d.dt.strftime("%Y-%m")).pnl.sum(); eq=x.pnl.cumsum()
    kind=x.legs.map(lambda l:"straddle" if len(l.split())==2 else ("put" if "P" in l else "call"))
    rows.append({"version":name,"trades":len(x),"puts":(kind=="put").sum(),"calls":(kind=="call").sum(),"strad":(kind=="straddle").sum(),
      "win%":round((x.pnl>0).mean()*100),"net_2yr":round(x.pnl.sum()),"last12m":round(x[x.d>="2025-10-01"].pnl.sum()),"since_feb26":round(x[x.d>="2026-02-01"].pnl.sum()),
      "put_pnl":round(x.pnl[kind=="put"].sum()),"call_pnl":round(x.pnl[kind=="call"].sum()),
      "losing_m":f"{(m<0).sum()}/{len(m)}","max_dd":round((eq-eq.cummax()).min()),"worst":round(x.pnl.min())})
print(pd.DataFrame(rows).to_string(index=False))
