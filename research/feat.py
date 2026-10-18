import sys, re, math, numpy as np, pandas as pd
sys.path.insert(0, "/home/user/shantu281")
from deltabot.pricing import bs_price
from deltabot.data import load_candles
S = "research/out"
idx = load_candles("data/BTC_index_5m.csv")["close"]
hourly = idx.resample("1h").last().dropna()
def legs_of(s):
    return [("call" if m[1]=="C" else "put", float(m[2]), -1 if m[0]=="-" else 1) for m in re.findall(r"([+-])([CP])(\d+)", s)]
def greeks(kind, S0, K, t, v):
    d1 = (math.log(S0/K) + 0.5*v*v*t) / (v*math.sqrt(t)); pdf = math.exp(-d1*d1/2)/math.sqrt(2*math.pi)
    from math import erf
    N = 0.5*(1+erf(d1/math.sqrt(2)))
    delta = N if kind=="call" else N-1
    gamma = pdf/(S0*v*math.sqrt(t)); vega = S0*pdf*math.sqrt(t)/100  # per vol point
    theta_h = -(S0*pdf*v/(2*math.sqrt(t)))/(365*24)  # per hour
    return delta, gamma, vega, theta_h
def features(f, hours):
    x = pd.read_csv(f"{S}/{f}"); x["d"] = pd.to_datetime(x.entry_time, utc=True)
    t = hours/(365*24); out = []
    for r in x.itertuples():
        legs = legs_of(r.legs); g = np.zeros(4); prem = 0
        for kind, K, sd in legs:
            g += sd*np.array(greeks(kind, r.spot_entry, K, t, r.vol)); prem += bs_price(kind, r.spot_entry, K, t, r.vol)
        h = hourly.loc[:r.d - pd.Timedelta(minutes=5)]
        lr = np.log(h).diff().dropna()
        rv24 = lr.iloc[-24:].std()*math.sqrt(24*365); rv7 = lr.iloc[-168:].std()*math.sqrt(24*365)
        mv = h.iloc[-168:].diff(max(1,hours)).abs().mean()  # avg move over the holding horizon
        dist = min(abs(K - r.spot_entry) for _, K, _ in legs)/r.spot_entry*100
        out.append(dict(delta=abs(g[0]), gamma=-g[1]*r.spot_entry**2/100, vega=-g[2], theta=-g[3]*hours,
                        iv=r.vol, rv24=rv24, rv7=rv7, iv_rv24=r.vol/rv24, iv_rv7=r.vol/rv7,
                        credit=-r.entry_premium, credit_move=-r.entry_premium/mv, dist_pct=dist,
                        be_move=math.sqrt(2*abs(g[3])/abs(g[1]))/r.spot_entry*100 if g[1] else np.nan,
                        hour_ret=(h.iloc[-1]/h.iloc[-1-hours]-1)*100, dow=r.d.dayofweek))
    return pd.concat([x, pd.DataFrame(out)], axis=1)
if __name__ == "__main__":
    for f, h in [("fin_gmma_h8_slip5.csv", 8), ("fin_gmma_h2_stop1_slip5.csv", 2), ("fin_lean_h2_stop1_slip5.csv", 2)]:
        features(f, h).to_csv(f"{S}/feat_{f}", index=False); print("ok", f)
