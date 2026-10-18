"""Delta India portfolio margin for short options (guide: risk margin = worst of 29 scenarios, floor)."""
import re, numpy as np, pandas as pd, sys
sys.path.insert(0, "/home/user/shantu281")
from deltabot.pricing import bs_price
def legs_of(s):  # "-C84800 -P84400" -> [("call",84800,-1),...]
    return [("call" if m[1]=="C" else "put", float(m[2]), -1 if m[0]=="-" else 1) for m in re.findall(r"([+-])([CP])(\d+)", s)]
def pm_margin(spot, iv, hours, legs):
    """USD per 1 BTC of each leg. Notional < $100K: price span 1%, vol up 9%, vol down 6%."""
    t = hours / (365 * 24); dte = hours / 24
    up, dn = 0.09 * (30 / dte) ** 0.3, 0.06 * (30 / dte) ** 0.3
    v0 = sum(sd * bs_price(k, spot, K, t, iv) for k, K, sd in legs)
    worst = 0.0
    for pm in (0, 1/3, 1/2, 2/3, 1):
        for sgn in (1, -1):
            S = spot * (1 + sgn * 0.01 * pm)
            for v in (iv + up, iv, max(iv - dn, 0.05)):
                worst = min(worst, sum(sd * bs_price(k, S, K, t, v) for k, K, sd in legs) - v0)
    for sgn in (1, -1):  # extreme: 3x span, vol up, 1/3 counted
        S = spot * (1 + sgn * 0.03)
        worst = min(worst, (sum(sd * bs_price(k, S, K, t, iv + up) for k, K, sd in legs) - v0) / 3)
    floor = sum(max(0.05 * bs_price(k, spot, K, t, iv), 0.005 * spot) for k, K, sd in legs if sd < 0)
    return max(-worst, floor)
