"""Candidate BTC option strategies for the backtest.

Each strategy decides the legs to open at entry time and its own exit rules.
Exit thresholds are expressed relative to the entry premium:
  - short-premium (credit) trades: stop when the loss reaches `stop_mult` x credit,
    take profit when `take_profit` (fraction) of the credit has been captured.
  - long-premium (debit) trades: stop when `stop_mult` (fraction) of the debit is lost,
    take profit when the gain reaches `take_profit` x debit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .pricing import SECONDS_PER_YEAR, round_strike, strike_for_delta


@dataclass(frozen=True)
class Leg:
    kind: str      # "call" or "put"
    strike: float
    side: int      # +1 long, -1 short


@dataclass
class EntryContext:
    time: pd.Timestamp
    spot: float
    t_years: float          # time to expiry
    vol: float              # annualised vol used for pricing / strike selection
    history: pd.DataFrame   # candles strictly before entry
    strike_step: float


@dataclass
class Strategy:
    name: str
    stop_mult: float | None = None
    take_profit: float | None = None
    params: dict = field(default_factory=dict)

    def legs(self, ctx: EntryContext) -> list[Leg]:
        raise NotImplementedError


class ShortStraddle(Strategy):
    def legs(self, ctx):
        k = round_strike(ctx.spot, ctx.strike_step)
        return [Leg("call", k, -1), Leg("put", k, -1)]


class ShortStrangle(Strategy):
    def legs(self, ctx):
        d = self.params.get("delta", 0.20)
        kc = strike_for_delta("call", ctx.spot, d, ctx.t_years, ctx.vol, ctx.strike_step)
        kp = strike_for_delta("put", ctx.spot, d, ctx.t_years, ctx.vol, ctx.strike_step)
        return [Leg("call", kc, -1), Leg("put", kp, -1)]


class IronCondor(Strategy):
    def legs(self, ctx):
        ds, dw = self.params.get("short_delta", 0.20), self.params.get("wing_delta", 0.05)
        args = (ctx.t_years, ctx.vol, ctx.strike_step)
        sc = strike_for_delta("call", ctx.spot, ds, *args)
        sp = strike_for_delta("put", ctx.spot, ds, *args)
        lc = max(strike_for_delta("call", ctx.spot, dw, *args), sc + ctx.strike_step)
        lp = min(strike_for_delta("put", ctx.spot, dw, *args), sp - ctx.strike_step)
        return [Leg("call", sc, -1), Leg("put", sp, -1), Leg("call", lc, +1), Leg("put", lp, +1)]


class LongStraddle(Strategy):
    def legs(self, ctx):
        k = round_strike(ctx.spot, ctx.strike_step)
        return [Leg("call", k, +1), Leg("put", k, +1)]


class TrendBuy(Strategy):
    """Buy a call in an uptrend / a put in a downtrend (EMA fast vs slow on the history candles)."""

    def legs(self, ctx):
        fast, slow = self.params.get("fast", 20), self.params.get("slow", 50)
        closes = ctx.history["close"]
        if len(closes) < slow:
            return []
        ema_f = closes.ewm(span=fast, adjust=False).mean().iloc[-1]
        ema_s = closes.ewm(span=slow, adjust=False).mean().iloc[-1]
        last = closes.iloc[-1]
        d = self.params.get("delta", 0.40)
        if last > ema_f > ema_s:
            kind = "call"
        elif last < ema_f < ema_s:
            kind = "put"
        else:
            return []
        k = strike_for_delta(kind, ctx.spot, d, ctx.t_years, ctx.vol, ctx.strike_step)
        return [Leg(kind, k, +1)]

def market_structure(closes: pd.Series, width: int = 3, lookback: int = 72) -> str:
    """'up' (higher highs and higher lows), 'down' (lower highs and lower lows) or 'range'.

    Swing points are closes that are the highest/lowest of the `width` bars on each side,
    found in the last `lookback` bars. Only confirmed swings count (width bars after them).
    """
    c = closes.iloc[-lookback:].to_numpy()
    highs, lows = [], []
    for i in range(width, len(c) - width):
        win = c[i - width: i + width + 1]
        if c[i] == win.max():
            highs.append(c[i])
        elif c[i] == win.min():
            lows.append(c[i])
    if len(highs) < 2 or len(lows) < 2:
        return "range"
    if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
        return "up"
    if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
        return "down"
    return "range"


class StructureSeller(Strategy):
    """Sell at the money by market structure: put in an uptrend, call in a downtrend, straddle in a range.

    params["trend"] = "skip" sells the straddle in a range only and stays out of trends.
    """

    def legs(self, ctx):
        structure = market_structure(ctx.history["close"], self.params.get("width", 3),
                                     self.params.get("lookback", 72))
        k = round_strike(ctx.spot, ctx.strike_step)
        if structure == "range":
            return [Leg("call", k, -1), Leg("put", k, -1)]
        if self.params.get("trend") == "skip":
            return []
        return [Leg("put" if structure == "up" else "call", k, -1)]

class MoveAdaptiveSeller(Strategy):
    """Short call and put placed by BTC's recent movement (hourly closes before entry).

    `move` is the average absolute price change over the time left to expiry, measured
    over the last `days`. The call is sold at spot + width x move and the put at
    spot - width x move (width 0 = straddle). `shift` moves both strikes by that
    fraction of the last move over the same horizon: > 0 bets it continues, < 0 that
    it reverses.
    """

    def legs(self, ctx):
        closes = ctx.history["close"]
        h = max(1, round(ctx.t_years * SECONDS_PER_YEAR / 3600))
        recent = closes.iloc[-self.params.get("days", 7) * 24:]
        if len(recent) <= h:
            return []
        move = recent.diff(h).abs().mean()
        center = ctx.spot + self.params.get("shift", 0.0) * (closes.iloc[-1] - closes.iloc[-1 - h])
        width = self.params.get("width", 0.0) * move
        return [Leg("call", round_strike(center + width, ctx.strike_step), -1),
                Leg("put", round_strike(center - width, ctx.strike_step), -1)]

GMMA_SHORT = (3, 5, 8, 10, 12, 15)
GMMA_LONG = (30, 35, 40, 45, 50, 60)


def gmma_state(closes: pd.Series) -> str:
    """'up' when every short-group EMA is above every long-group EMA, 'down' when all below, else 'none'."""
    short = [closes.ewm(span=n, adjust=False).mean().iloc[-1] for n in GMMA_SHORT]
    long_ = [closes.ewm(span=n, adjust=False).mean().iloc[-1] for n in GMMA_LONG]
    if min(short) > max(long_):
        return "up"
    if max(short) < min(long_):
        return "down"
    return "none"


class GmmaOptionSeller(Strategy):
    """Sell options by the GMMA ribbon on completed H4 bars: a put when it points up, a call when down.

    params: "width" places the leg width x recent move out of the money (see MoveAdaptiveSeller),
    "none" = "skip" (default) or "straddle" for when the ribbons are tangled, "sides" = "both" or "put".
    """

    def legs(self, ctx):
        hourly = ctx.history["close"]
        h4 = hourly.resample("4h").last()
        h4 = h4[h4.index + pd.Timedelta(hours=4) <= ctx.time].dropna()  # completed bars only
        if len(h4) < 180:  # let the 60-EMA settle
            return []
        state = gmma_state(h4)
        h = max(1, round(ctx.t_years * SECONDS_PER_YEAR / 3600))
        move = hourly.iloc[-7 * 24:].diff(h).abs().mean()
        off = self.params.get("width", 0.0) * move
        if state == "up":
            return [Leg("put", round_strike(ctx.spot - off, ctx.strike_step), -1)]
        if state == "down" and self.params.get("sides", "both") == "both":
            return [Leg("call", round_strike(ctx.spot + off, ctx.strike_step), -1)]
        if state == "none" and self.params.get("none") == "straddle":
            k = round_strike(ctx.spot, ctx.strike_step)
            return [Leg("call", k, -1), Leg("put", k, -1)]
        return []

class IronButterfly(Strategy):
    """Sell the ATM call and put, buy a call and a put `wing` (fraction of spot) away.

    The backtest skips legs priced under RealConfig.min_price ($1/BTC), so it only trades when the
    wings have value, i.e. on the livelier days. `min_iv` skips days whose at-the-money implied vol is
    lower. Best tested: wing 2%, entered 2 h before expiry, min_iv 0.32 (cut-off set on Sep 2024-Sep 2025).
    """

    def legs(self, ctx):
        if ctx.vol < self.params.get("min_iv", 0.0):  # premiums too thin: skip the day
            return []
        k = round_strike(ctx.spot, ctx.strike_step)
        w = self.params.get("wing", 0.02) * ctx.spot
        return [Leg("call", k, -1), Leg("put", k, -1),
                Leg("call", round_strike(ctx.spot + w, ctx.strike_step), +1),
                Leg("put", round_strike(ctx.spot - w, ctx.strike_step), +1)]


def default_strategies() -> list[Strategy]:
    """The starting set to compare. Tune or add variants here."""
    return [
        ShortStraddle("short_straddle", stop_mult=1.0, take_profit=0.5),
        ShortStraddle("short_straddle_noexit"),
        ShortStrangle("short_strangle_d20", stop_mult=1.5, take_profit=0.6, params={"delta": 0.20}),
        ShortStrangle("short_strangle_d10", stop_mult=2.0, take_profit=0.7, params={"delta": 0.10}),
        IronCondor("iron_condor_20_05", stop_mult=1.5, take_profit=0.6,
                   params={"short_delta": 0.20, "wing_delta": 0.05}),
        LongStraddle("long_straddle", stop_mult=0.5, take_profit=1.0),
        TrendBuy("trend_buy_d40", stop_mult=0.5, take_profit=1.5, params={"delta": 0.40}),
        StructureSeller("structure_sell"),
        StructureSeller("structure_range_only", params={"trend": "skip"}),
        MoveAdaptiveSeller("move_strangle_025", params={"width": 0.25}),
        MoveAdaptiveSeller("move_strangle_05", params={"width": 0.5}),
        MoveAdaptiveSeller("move_strangle_1", params={"width": 1.0}),
        MoveAdaptiveSeller("move_shift_follow", params={"shift": 0.5}),
        MoveAdaptiveSeller("move_shift_revert", params={"shift": -0.5}),
        GmmaOptionSeller("gmma_sell"),
        GmmaOptionSeller("gmma_sell_straddle", params={"none": "straddle"}),
        GmmaOptionSeller("gmma_sell_otm", params={"width": 0.5}),
        GmmaOptionSeller("gmma_put_only", params={"sides": "put"}),
        IronButterfly("iron_fly_2pct", params={"wing": 0.02}),
        IronButterfly("iron_fly_2pct_iv32", params={"wing": 0.02, "min_iv": 0.32}),
    ]
