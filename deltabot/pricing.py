"""Black-Scholes pricing for BTC options (European, cash-settled, r = 0)."""

from __future__ import annotations

import math

SECONDS_PER_YEAR = 365.0 * 24 * 3600


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _d1_d2(spot: float, strike: float, t_years: float, vol: float) -> tuple[float, float]:
    sig_t = vol * math.sqrt(t_years)
    d1 = (math.log(spot / strike) + 0.5 * vol * vol * t_years) / sig_t
    return d1, d1 - sig_t


def intrinsic(kind: str, spot: float, strike: float) -> float:
    return max(spot - strike, 0.0) if kind == "call" else max(strike - spot, 0.0)


def bs_price(kind: str, spot: float, strike: float, t_years: float, vol: float) -> float:
    """Option price in USD per 1 BTC of underlying."""
    if t_years <= 0 or vol <= 0:
        return intrinsic(kind, spot, strike)
    d1, d2 = _d1_d2(spot, strike, t_years, vol)
    if kind == "call":
        return spot * _norm_cdf(d1) - strike * _norm_cdf(d2)
    return strike * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def bs_delta(kind: str, spot: float, strike: float, t_years: float, vol: float) -> float:
    if t_years <= 0 or vol <= 0:
        if kind == "call":
            return 1.0 if spot > strike else 0.0
        return -1.0 if spot < strike else 0.0
    d1, _ = _d1_d2(spot, strike, t_years, vol)
    return _norm_cdf(d1) if kind == "call" else _norm_cdf(d1) - 1.0


def round_strike(price: float, step: float) -> float:
    return round(price / step) * step


def strike_for_delta(kind: str, spot: float, target_delta: float, t_years: float, vol: float,
                     step: float) -> float:
    """Listed strike (multiple of `step`) whose |delta| is closest to `target_delta` (e.g. 0.20)."""
    best, best_err = round_strike(spot, step), float("inf")
    atm = round_strike(spot, step)
    direction = 1 if kind == "call" else -1
    for i in range(0, 200):
        k = atm + direction * i * step
        if k <= 0:
            break
        err = abs(abs(bs_delta(kind, spot, k, t_years, vol)) - target_delta)
        if err < best_err:
            best, best_err = k, err
        elif i > 0 and abs(bs_delta(kind, spot, k, t_years, vol)) < target_delta:
            break
    return best
